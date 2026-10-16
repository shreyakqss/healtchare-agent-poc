"""`FhirHMS` - the `HMSClient` implementation for OpenEMR.

Reads come from the FHIR R4 API; clinical writes go through OpenEMR's standard REST API
(`rest.py`), because on OpenEMR 8.3 the FHIR endpoint accepts writes for `Patient` only.
Both share one OAuth token (`auth.py`).

Non-negotiables of the boundary:

- `request_appointment` never books. OpenEMR has no "proposed" appointment concept its API
  will store (FHIR Appointment is read-only here and a calendar event *is* a booking), so
  the request is filed on the chart as a document for scheduling staff to act on.
- `push_document` / `sync_reviewed_intake` are only ever called with clinician-approved
  content; the API gates that, this class does not second-guess it.

Every read is best-effort: a resource type the install does not expose, or the client is
not scoped for, degrades to an empty list rather than failing the caller.
"""

from __future__ import annotations

import base64
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx

from app.core.errors import HMSRejected
from app.domain import scheduling
from app.integrations.hms.openemr import fhir
from app.integrations.hms.openemr.auth import (
    TIMEOUT_SECONDS,
    IdTokenVerifier,
    OAuthConfig,
    TokenProvider,
    request_token,
)
from app.integrations.hms.openemr.rest import (
    StandardApi,
    contact_preference_fields,
    contact_preference_from_row,
    pid_of,
)
from app.integrations.hms.schemas import (
    AppointmentRequest,
    AppointmentRequestResult,
    HMSAddress,
    HMSDocument,
    HMSFacility,
    HMSPatient,
    HMSPractitioner,
    HMSSlot,
    HMSStatus,
    HMSWeeklyHours,
    PatientRegistration,
    VerifiedIdentity,
)

logger = logging.getLogger(__name__)

# /health is polled by every page render; counting patients/appointments on each call is
# a 3-request round-trip against OpenEMR, so the answer is cached briefly.
STATUS_CACHE_SECONDS = 30.0
# `_summary=count` and `bundle.total` are both unreliable on OpenEMR 8.3 (confirmed live:
# `total` echoes `_count`), so status() fetches a real page and counts entries.
_COUNT_PAGE_SIZE = 500
_MIME_EXTENSIONS = {"text/plain": "txt", "application/json": "json", "application/pdf": "pdf", "text/markdown": "md"}
APPOINTMENT_REQUEST_TITLE = "CareFlow appointment request"
# OpenEMR calendar: category 2 is a provider's "In Office" block; a status of "x"/"%" is a
# cancellation, so that appointment no longer occupies the provider's time.
IN_OFFICE_CATEGORY_ID = "2"
_CANCELLED_STATUSES = {"x", "%"}


def _event_interval(event: dict[str, Any], tz: ZoneInfo) -> tuple[datetime, datetime] | None:
    """`(start, end)` of a calendar row in the clinic's timezone - OpenEMR stores bare local times."""
    try:
        day = event["pc_eventDate"]
        start = datetime.fromisoformat(f"{day}T{event['pc_startTime']}").replace(tzinfo=tz)
        end = datetime.fromisoformat(f"{day}T{event['pc_endTime']}").replace(tzinfo=tz)
    except (KeyError, TypeError, ValueError):
        return None
    return (start, end) if end > start else None


def _office_hours_and_busy(
    events: list[dict[str, Any]], practitioner_id: str, tz: ZoneInfo
) -> tuple[list[tuple[datetime, datetime]], list[tuple[datetime, datetime]]]:
    """Split one practitioner's calendar rows into published office hours and booked time."""
    hours: list[tuple[datetime, datetime]] = []
    busy: list[tuple[datetime, datetime]] = []
    for event in events:
        if event.get("pce_aid_uuid") != practitioner_id:
            continue
        interval = _event_interval(event, tz)
        if interval is None:
            continue
        if str(event.get("pc_catid")) == IN_OFFICE_CATEGORY_ID:
            hours.append(interval)
        elif event.get("pc_pid") and event.get("pc_apptstatus") not in _CANCELLED_STATUSES:
            busy.append(interval)
    return hours, busy


def _document_filename(title: str, content_type: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "document"
    ext = _MIME_EXTENSIONS.get(content_type.split(";")[0].strip()) or content_type.rsplit("/", 1)[-1] or "bin"
    return f"{stem}.{ext}"


def _render_note(title: str, sections: dict[str, Any]) -> bytes:
    """Human-readable plain text for the chart. OpenEMR's upload guard declines content it
    sniffs as JSON ("insecure patient document"), and staff read these notes, so structured
    payloads are rendered rather than serialised."""
    lines = [title, "=" * len(title), ""]
    for key, value in sections.items():
        label = key.replace("_", " ").capitalize()
        if isinstance(value, list):
            lines.append(f"{label}:")
            lines.extend(f"  - {_render_item(item)}" for item in value) if value else lines.append("  (none)")
        elif isinstance(value, dict):
            lines.append(f"{label}:")
            lines.extend(f"  {k}: {v}" for k, v in value.items())
        else:
            lines.append(f"{label}: {value if value not in (None, '') else '(none)'}")
    return "\n".join(lines).encode("utf-8")


def _rejection_detail(exc: httpx.HTTPStatusError) -> str:
    """A short, readable reason from an OpenEMR rejection - its validator map when there is
    one, else the status. Never the whole response body: it can echo submitted PHI."""
    try:
        body = exc.response.json()
    except ValueError:
        return f"HTTP {exc.response.status_code}"
    if isinstance(body, dict) and isinstance(body.get("validationErrors"), dict):
        return ", ".join(sorted(body["validationErrors"]))[:200]
    for key in ("error_description", "message", "error"):
        if isinstance(body, dict) and body.get(key):
            return f"HTTP {exc.response.status_code} ({key})"
    return f"HTTP {exc.response.status_code}"


def _render_item(item: Any) -> str:
    if isinstance(item, dict):
        return ", ".join(f"{k}={v}" for k, v in item.items() if v not in (None, ""))
    return str(item)


class FhirHMS:
    provider = "openemr"

    def __init__(
        self,
        base_url: str,
        fhir_path: str,
        token_url: str,
        client_id: str | None,
        client_secret: str | None,
        scopes: str,
        username: str | None = None,
        password: str | None = None,
        api_path: str = "/apis/default/api",
        status_cache_seconds: float = STATUS_CACHE_SECONDS,
    ):
        self._fhir_base = base_url.rstrip("/") + fhir_path
        self._oauth = OAuthConfig(
            token_url=token_url, client_id=client_id, client_secret=client_secret,
            scopes=scopes, username=username, password=password,
        )
        self._tokens = TokenProvider(self._oauth)
        self._verifier = IdTokenVerifier(self._oauth)
        self._rest = StandardApi(base_url, api_path, self._tokens)
        self._status_ttl = status_cache_seconds
        self._status_cache: tuple[float, HMSStatus] | None = None
        self._status_lock = threading.Lock()

    # --- transport (FHIR) -------------------------------------------------------

    def _headers(self, force_refresh: bool = False) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._tokens.access_token(force_refresh)}",
            "Accept": "application/fhir+json",
        }

    def _request_url(self, path: str) -> str:
        if not path.startswith(("http://", "https://", "//")):
            return f"{self._fhir_base}/{path.lstrip('/')}"

        base = urlsplit(self._fhir_base)
        target = urlsplit(path if not path.startswith("//") else f"{base.scheme}:{path}")
        try:
            target_origin = (target.scheme.lower(), target.hostname, target.port)
            base_origin = (base.scheme.lower(), base.hostname, base.port)
        except ValueError as exc:
            raise HMSRejected("OpenEMR returned an invalid document URL.") from exc
        if target_origin != base_origin:
            raise HMSRejected("OpenEMR returned a document URL outside its configured FHIR endpoint.")
        fhir_path = base.path.rstrip("/")
        if target.path != fhir_path and not target.path.startswith(f"{fhir_path}/"):
            raise HMSRejected("OpenEMR returned a document URL outside its configured FHIR endpoint.")
        return target.geturl()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = self._request_url(path)
        resp = httpx.request(method, url, headers=self._headers(), timeout=TIMEOUT_SECONDS, **kwargs)
        if resp.status_code == 401:
            # Token revoked/expired server-side ahead of the cached expiry - one retry.
            resp = httpx.request(method, url, headers=self._headers(force_refresh=True), timeout=TIMEOUT_SECONDS, **kwargs)
        resp.raise_for_status()
        return resp

    def _search(self, resource_type: str, **params: Any) -> list[fhir.Resource]:
        return fhir.bundle_entries(self._request("GET", resource_type, params=params).json())

    def _search_or_empty(self, resource_type: str, **params: Any) -> list[fhir.Resource]:
        """Best-effort search: a resource the install does not expose is an empty list."""
        try:
            return self._search(resource_type, **params)
        except httpx.HTTPError as exc:
            logger.debug("%s search unavailable (%s)", resource_type, type(exc).__name__)
            return []

    # --- patient addressing ------------------------------------------------------

    def _read_patient(self, patient_id: str) -> fhir.Resource | None:
        try:
            resource = self._request("GET", f"Patient/{patient_id}").json()
        except httpx.HTTPError:
            return None
        return resource if resource.get("resourceType") == "Patient" else None

    def _find_patient_resource(self, mrn: str) -> fhir.Resource | None:
        """By identifier first (OpenEMR's public patient id); a record that carries no
        identifier is addressed by its FHIR resource id instead."""
        entries = self._search("Patient", identifier=mrn, _count=1)
        if entries:
            return entries[0]
        return self._read_patient(mrn)

    def _require_patient(self, mrn: str) -> fhir.Resource:
        patient = self._find_patient_resource(mrn)
        if patient is None:
            raise httpx.HTTPError(f"Linked OpenEMR patient was not found for {mrn!r}")
        return patient

    def _pid(self, patient: fhir.Resource) -> int:
        pid = self._rest.pid_for(patient["id"])
        if pid is None:
            raise httpx.HTTPError("OpenEMR standard API could not resolve the patient's pid")
        return pid

    def _read_patient_after_write(self, resp: httpx.Response) -> fhir.Resource:
        """OpenEMR answers a Patient create with `{"pid": N, "uuid": "<fhir id>"}` (confirmed
        live on 8.3) rather than the resource; other servers use a `Location` header. Re-read
        the record so the public identifier (MRN) is populated."""
        body: fhir.Resource = resp.json() if resp.content else {}
        if body.get("resourceType") == "Patient" and body.get("identifier"):
            return body
        patient_id = body.get("id") or body.get("uuid") or fhir.reference_id(resp.headers.get("Location"))
        if not patient_id:
            return body
        return self._read_patient(patient_id) or {**body, "id": patient_id}

    # --- read side -------------------------------------------------------------

    def status(self) -> HMSStatus:
        cached = self._status_cache
        if cached and time.monotonic() - cached[0] < self._status_ttl:
            return cached[1]
        with self._status_lock:
            cached = self._status_cache
            if cached and time.monotonic() - cached[0] < self._status_ttl:
                return cached[1]
            status = self._probe_status()
            self._status_cache = (time.monotonic(), status)
            return status

    def _probe_status(self) -> HMSStatus:
        try:
            patients = self._search("Patient", _count=_COUNT_PAGE_SIZE)
            practitioners = self.list_practitioners(limit=_COUNT_PAGE_SIZE, include_usernames=False)
            pending = self._search_or_empty("Appointment", status="proposed", _count=_COUNT_PAGE_SIZE)
        except Exception as exc:  # noqa: BLE001 - status must never raise
            logger.warning("OpenEMR status probe failed (%s)", type(exc).__name__)
            return HMSStatus(provider=self.provider, connected=False, patients=0, practitioners=0, pending_requests=0)
        return HMSStatus(
            provider=self.provider, connected=True,
            patients=len(patients), practitioners=len(practitioners), pending_requests=len(pending),
        )

    def get_facility(self) -> HMSFacility | None:
        """The clinic OpenEMR is configured for: the first facility marked a service
        location, else the first on file. Best-effort - returns None when unavailable."""
        try:
            facilities = self._rest.facilities()
        except Exception as exc:  # noqa: BLE001 - cosmetic data; never break a page over it
            logger.debug("facility lookup unavailable (%s)", type(exc).__name__)
            return None
        if not facilities:
            return None
        row = next((f for f in facilities if str(f.get("service_location")) == "1"), facilities[0])
        return HMSFacility(
            id=str(row.get("uuid") or row.get("id") or ""),
            name=row.get("name") or "Clinic",
            phone=row.get("phone") or None,
            email=row.get("email") or None,
            website=row.get("website") or None,
            address=HMSAddress(
                line1=row.get("street") or "", line2=row.get("street2") or None, city=row.get("city") or "",
                state=row.get("state") or "", postal_code=row.get("postal_code") or "",
                country=row.get("country_code") or "",
            ),
        )

    def search_patients(self, query: str, limit: int = 10) -> list[HMSPatient]:
        query = query.strip()
        params: dict[str, Any] = {"_count": limit}
        if query:
            params["name"] = query
        entries = self._search("Patient", **params)
        if query and not entries:
            # A record-number search ("MRN-1", "10021") matches identifiers, not names.
            entries = self._search_or_empty("Patient", identifier=query, _count=limit)
        return [fhir.patient_from_resource(res) for res in entries]

    def _labels(self, resource_type: str, patient_id: str, field: str) -> list[str]:
        labels = []
        for res in self._search_or_empty(resource_type, patient=patient_id):
            label = fhir.codeable_text(res, field)
            if label:
                labels.append(label)
        return labels

    def _medications(self, patient_id: str, row: dict[str, Any]) -> list[str]:
        """FHIR MedicationStatement where the install offers it, else the standard API's
        medication list (best-effort - 8.3.0 500s on some rows). `row` is the already-fetched
        standard-API patient record, so this costs no extra round-trip."""
        labels = self._labels("MedicationStatement", patient_id, "medicationCodeableConcept")
        if labels:
            return labels
        pid = pid_of(row)
        return self._rest.medications(pid) if pid is not None else []

    def _allergies(self, patient_id: str) -> list[str]:
        """Standard-API titles first (the patient's words); FHIR AllergyIntolerance reduces an
        uncoded allergy to "Unknown", so it is only the fallback."""
        return self._rest.allergies(patient_id) or self._labels("AllergyIntolerance", patient_id, "code")

    def _last_visit(self, patient_id: str) -> datetime | None:
        """Most recent Encounter start, when the install exposes Encounter (scope permitting)."""
        for res in self._search_or_empty("Encounter", patient=patient_id, _sort="-date", _count=1):
            return fhir.parse_datetime((res.get("period") or {}).get("start"))
        return None

    def get_patient(self, mrn: str) -> HMSPatient | None:
        res = self._find_patient_resource(mrn)
        if res is None:
            return None
        patient_id = res.get("id", "")
        # Independent OpenEMR round-trips - each one is slow on its own (no opcache on this
        # install), so run them concurrently rather than paying for all of them in sequence.
        with ThreadPoolExecutor(max_workers=4) as pool:
            row_future = pool.submit(self._rest.patient, patient_id)
            conditions_future = pool.submit(self._labels, "Condition", patient_id, "code")
            allergies_future = pool.submit(self._allergies, patient_id)
            last_visit_future = pool.submit(self._last_visit, patient_id)
            # The standard-API row carries what FHIR omits (country, contact preference) and
            # the numeric pid; fetch it once and reuse. Medications needs it only for its
            # standard-API fallback, so it waits on row_future rather than fetching twice.
            row = row_future.result() or {}
            medications = self._medications(patient_id, row)
            conditions = conditions_future.result()
            allergies = allergies_future.result()
            last_visit = last_visit_future.result()
        return fhir.patient_from_resource(
            res,
            conditions=conditions,
            medications=medications,
            allergies=allergies,
            last_visit=last_visit,
            fallback_mrn=mrn,
            country_fallback=row.get("country_code") or None,
            contact_preference=contact_preference_from_row(row),
        )

    def register_patient(self, existing_mrn: str | None, registration: PatientRegistration) -> HMSPatient:
        """Create a Patient, or update an explicitly linked one without dropping unknown fields."""
        existing = self._find_patient_resource(existing_mrn) if existing_mrn else None
        body = fhir.patient_body(existing, registration)
        try:
            if existing and existing.get("id"):
                resp = self._request("PUT", f"Patient/{existing['id']}", json=body)
            else:
                resp = self._request("POST", "Patient", json=body)
        except httpx.HTTPStatusError as exc:
            # OpenEMR validates demographics itself (it rejects an empty name, a malformed
            # date...). That is the caller's data being wrong, so surface it as such instead
            # of letting a raw upstream error become a 500.
            if exc.response.status_code in (400, 422):
                raise HMSRejected(f"The hospital system rejected these patient details: {_rejection_detail(exc)}") from exc
            raise
        written = self._read_patient_after_write(resp)
        self._store_demographics_fhir_drops(written.get("id"), registration)
        patient = fhir.patient_from_resource(
            written,
            country_fallback=registration.country,
            contact_preference=registration.contact_preference,
        )
        if not patient.mrn:
            raise httpx.HTTPError("OpenEMR did not return an identifier for the registered patient")
        return patient

    def _store_demographics_fhir_drops(self, patient_id: str | None, registration: PatientRegistration) -> None:
        """Persist the two demographics OpenEMR's FHIR write silently discards - the address
        country and the contact preference - through the standard API, which does keep them.

        Best-effort: the patient is registered by this point, so failing here must not fail
        the intake. It only means the patient re-picks those two next visit.
        """
        if not patient_id:
            return
        fields: dict[str, str] = {}
        if registration.country:
            fields["country_code"] = registration.country
        fields.update(contact_preference_fields(registration.contact_preference))
        try:
            self._rest.update_patient(patient_id, fields)
        except Exception as exc:  # noqa: BLE001 - see docstring
            logger.warning("Could not store country/contact preference in OpenEMR (%s)", type(exc).__name__)

    def list_documents(self, mrn: str, limit: int = 20) -> list[HMSDocument]:
        patient = self._find_patient_resource(mrn)
        if patient is None:
            return []
        entries = self._search_or_empty("DocumentReference", patient=patient.get("id"), _count=limit, _sort="-date")
        return [fhir.document_from_resource(res) for res in entries[:limit]]

    def get_document_content(self, mrn: str, reference: str) -> tuple[bytes, str, str]:
        patient = self._find_patient_resource(mrn)
        if patient is None:
            raise FileNotFoundError("Patient not found")
        document = self._request("GET", f"DocumentReference/{reference}").json()
        subject = (document.get("subject") or {}).get("reference", "")
        if subject != f"Patient/{patient.get('id')}":
            raise PermissionError("Document does not belong to the linked patient")
        attachment = ((document.get("content") or [{}])[0].get("attachment") or {})
        title = attachment.get("title") or (document.get("type") or {}).get("text") or "document"
        mime = attachment.get("contentType") or "application/octet-stream"
        if attachment.get("data"):
            return base64.b64decode(attachment["data"]), mime, title
        if attachment.get("url"):
            return self._request("GET", attachment["url"]).content, mime, title
        raise FileNotFoundError("Document has no downloadable attachment")

    def list_practitioners(self, limit: int = 100, include_usernames: bool = True) -> list[HMSPractitioner]:
        """`include_usernames=False` keeps this to FHIR alone - for callers that only need the
        people, such as the status probe, which would otherwise pay for a lookup it discards."""
        from app.services import hospital_config  # department names for the specialty join

        roles = fhir.roles_by_practitioner(
            self._search_or_empty("PractitionerRole", _count=limit), hospital_config.departments()
        )
        # Logins live outside FHIR, so they cost one extra standard-API call. Best-effort:
        # without them the roster still lists everyone, they just have no username to offer
        # the clinician when they sign an action.
        usernames: dict[str, str] = {}
        if include_usernames:
            try:
                usernames = self._rest.practitioner_usernames()
            except Exception as exc:  # noqa: BLE001 - advisory lookup, never fails the roster
                logger.warning("Practitioner username lookup failed (%s)", type(exc).__name__)
        out: list[HMSPractitioner] = []
        seen: set[str] = set()
        # OpenEMR's PractitionerService LEFT JOINs list_options twice, fanning each
        # practitioner out into duplicate bundle rows (confirmed live) - dedupe by id.
        for res in self._search("Practitioner", _count=limit):
            pid = res.get("id")
            if pid is not None:
                if pid in seen:
                    continue
                seen.add(pid)
            if res.get("active") is False:  # deactivated in Admin > Doctors: never routed to again
                continue
            out.append(fhir.practitioner_from_resource(res, roles.get(pid or ""), usernames.get(pid or "")))
        return out

    def available_slots(self, department_id: str, practitioner_id: str | None = None, limit: int = 5) -> list[HMSSlot]:
        """Advisory only. A practitioner's "In Office" calendar blocks come first: OpenEMR 8.3
        has no Slot endpoint (404), so those published hours are the real schedule. Without
        blocks, a FHIR Slot search; an install with neither simply offers no slot."""
        if practitioner_id:
            from app.services import hospital_config  # the clinic's timezone for OpenEMR's bare times

            tz = ZoneInfo(hospital_config.hospital().get("timezone") or "UTC")
            hours, busy = _office_hours_and_busy(self._rest.calendar_events(), practitioner_id, tz)
            if hours:
                return scheduling.slots_within_hours(
                    hours, busy, department_id, practitioner_id, datetime.now(UTC), count=limit
                )
        params: dict[str, Any] = {"status": "free", "_count": limit}
        if practitioner_id:
            params["schedule.actor"] = f"Practitioner/{practitioner_id}"
        return [
            fhir.slot_from_resource(res, department_id=department_id, practitioner_id=practitioner_id)
            for res in self._search_or_empty("Slot", **params)
        ]

    def office_hours(self, practitioner_id: str) -> list[HMSWeeklyHours]:
        """The weekly pattern of the practitioner's "In Office" blocks over the next two weeks
        (two, so a day off this week or a one-off block cannot hide a regular working day)."""
        from app.services import hospital_config  # the clinic's timezone for OpenEMR's bare times

        tz = ZoneInfo(hospital_config.hospital().get("timezone") or "UTC")
        hours, _ = _office_hours_and_busy(self._rest.calendar_events(), practitioner_id, tz)
        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        window = [(start, end) for start, end in hours if today <= start < today + timedelta(days=14)]
        return scheduling.weekly_hours(window)

    # --- write side (standard API; drafts only) --------------------------------------

    def push_document(self, mrn: str, title: str, content: bytes, content_type: str = "text/plain") -> str:
        """Upload to the patient's chart (Documents category). OpenEMR's upload answers a bare
        `true`, so the reference is the chart location rather than a server id."""
        patient = self._require_patient(mrn)
        pid = self._pid(patient)
        filename = _document_filename(title, content_type)
        if not self._rest.upload_document(pid, filename, content, content_type):
            raise httpx.HTTPError("OpenEMR did not accept the document upload")
        return f"openemr:patient/{pid}/document/{filename}"

    def request_appointment(self, request: AppointmentRequest) -> AppointmentRequestResult:
        """File the request on the chart for scheduling staff. Never creates a calendar
        event - in OpenEMR that would be a booking, which is outside the POC's scope."""
        if not request.patient_mrn:
            raise httpx.HTTPError("An appointment request needs a linked OpenEMR patient")
        note = _render_note(APPOINTMENT_REQUEST_TITLE, {
            "status": "requested - to be scheduled by staff",
            "case_id": request.case_id, "patient": request.patient_name, "department": request.department_id,
            "practitioner": request.practitioner_id, "appointment_type": request.appointment_type_id,
            "priority": request.priority, "preferred_slot": request.preferred_slot_id, "reason": request.reason,
        })
        reference = self.push_document(request.patient_mrn, APPOINTMENT_REQUEST_TITLE, note, "text/plain")
        return AppointmentRequestResult(reference=reference, status="requested")

    def list_requests(self, limit: int = 100) -> list[AppointmentRequestResult]:
        return [
            AppointmentRequestResult(reference=res.get("id", ""), status="requested")
            for res in self._search_or_empty("Appointment", status="proposed", _count=limit)
        ]

    def sync_reviewed_intake(self, mrn: str, payload: dict) -> None:
        """Write clinician-approved intake as chart rows plus a faithful JSON note.

        Only ever called from finalisation, after a clinician approved the case and
        recorded consultation notes. Patient-stated rows only - HMS imports are not
        echoed back to the HMS.
        """
        patient = self._require_patient(mrn)
        patient_uuid = patient["id"]
        pid = self._pid(patient)
        self._record_visit(patient_uuid, pid, payload)
        for fact in payload.get("facts", []):
            if fact.get("source") == "patient" and fact.get("kind") in {"history", "condition"}:
                self._rest.create_medical_problem(patient_uuid, fact["value"])
        for entry in payload.get("entries", []):
            if entry.get("source") != "patient":
                continue
            if entry.get("kind") == "allergy":
                self._rest.create_allergy(patient_uuid, entry["name"], entry.get("reaction_or_dose"))
            elif entry.get("kind") == "medication":
                self._rest.create_medication(pid, entry["name"], entry.get("reaction_or_dose"))
        # The narrative, triage context and clinician note travel as one readable artifact,
        # so model output is never presented as a diagnosis.
        self.push_document(mrn, "CareFlow reviewed intake", _render_note("CareFlow reviewed intake", payload), "text/plain")

    def _record_visit(self, patient_uuid: str, pid: int, payload: dict) -> None:
        """Open an encounter for this visit and attach the clinician's note to it as a SOAP form.

        The encounter is the chart container the rest of a visit hangs off, and it is what
        makes the visit show up in the patient's history at all (it is also where
        `last_visit` comes from). Best-effort: the reviewed intake and its document are the
        record of record, so a hospital system that cannot take an encounter must not fail
        finalisation.

        Nothing here is generated: subjective is the patient's stated reason for the visit,
        assessment is the clinician's own note, plan is their prescription and follow-up.
        CareFlow collects no examination findings, so objective is marked not recorded.
        """
        notes = payload.get("consultation_notes") or []
        if not notes:
            return
        latest = notes[-1]
        reason = next(
            (f["value"] for f in reversed(payload.get("facts", [])) if f.get("kind") == "reason_for_visit"),
            "CareFlow intake",
        )
        plan = "\n".join(
            part for part in (latest.get("prescription"), latest.get("follow_up_instructions")) if part
        )
        try:
            # The encounter endpoint takes the patient uuid, the SOAP note the numeric ids -
            # OpenEMR is inconsistent here, and a uuid orphans the note. See create_soap_note.
            encounter = self._rest.create_encounter(patient_uuid, reason)
            if encounter:
                self._rest.create_soap_note(
                    pid, encounter,
                    subjective=reason, objective="", assessment=latest.get("notes") or "", plan=plan,
                )
        except Exception as exc:  # noqa: BLE001 - see docstring
            logger.warning("Could not record the visit encounter in OpenEMR (%s)", type(exc).__name__)

    # --- identity ----------------------------------------------------------------

    def verify_credentials(self, username: str, password: str) -> VerifiedIdentity | None:
        """Validate a clinician's own OpenEMR login via the password grant and verify the
        returned id_token. Never raises. The `sub` claim is the FHIR Practitioner id on
        this install, so the display name is looked up from it when possible."""
        try:
            resp = request_token(self._oauth, self._oauth.password_grant(username, password))
            if resp.status_code != 200:
                return None
            id_token = resp.json().get("id_token")
        except Exception as exc:  # noqa: BLE001 - a login check must never raise
            logger.warning("verify_credentials: token request failed (%s)", type(exc).__name__)
            return None
        if not id_token:
            return None
        claims = self._verifier.claims(id_token)
        if claims is None:
            return None
        sub = claims.get("sub")
        if not sub:
            return VerifiedIdentity(id=username, name=username)
        try:
            practitioner = self._request("GET", f"Practitioner/{sub}").json()
        except Exception:  # noqa: BLE001 - the name is cosmetic; the verified id is what matters
            return VerifiedIdentity(id=sub, name=username)
        # OpenEMR's password grant still succeeds for a deactivated user (confirmed live), so a
        # doctor deactivated in Admin > Doctors is refused here.
        if practitioner.get("active") is False:
            logger.info("verify_credentials: practitioner is deactivated")
            return None
        return VerifiedIdentity(id=sub, name=fhir.human_name(practitioner))
