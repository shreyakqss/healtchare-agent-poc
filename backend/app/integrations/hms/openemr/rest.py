"""OpenEMR *standard* REST API (`/apis/default/api`) - where clinical writes live.

OpenEMR 8.3's FHIR endpoint accepts writes for `Patient` only; medical problems, allergies,
medications and document uploads go through this API, addressed by the patient's FHIR
uuid or numeric `pid` (both confirmed live). Shares the OAuth token with the FHIR client:
the registration script requests both scope families.

Quirks confirmed against OpenEMR 8.3.0 and encoded here:
- medication `begdate` must be `YYYY-MM-DD HH:MM:SS`; medical problems accept `YYYY-MM-DD`
- an empty list answers 404, and the medication list endpoint 500s - reads are best-effort
- document upload answers a bare `true` (no id), and uploads are not visible through FHIR
  `DocumentReference` on this build
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx

from app.integrations.hms.openemr.auth import TIMEOUT_SECONDS, TokenProvider

logger = logging.getLogger(__name__)

DOCUMENT_CATEGORY = "/Documents"
# OpenEMR's default office-visit calendar category, and FHIR's class for an outpatient
# visit - which is the only kind CareFlow produces.
ENCOUNTER_CATEGORY_ID = "5"
ENCOUNTER_CLASS_AMBULATORY = "AMB"
_SOAP_NOT_RECORDED = "Not recorded during intake."


def _soap_section(text: str | None) -> str:
    """OpenEMR requires every SOAP section and rejects anything shorter than two characters.
    Say a section was not collected rather than inventing clinical content for it."""
    cleaned = (text or "").strip()
    return cleaned if len(cleaned) >= 2 else _SOAP_NOT_RECORDED

# OpenEMR records "how may we contact you" as HIPAA permission flags rather than a single
# preference, and its FHIR endpoint exposes neither. CareFlow's one-of choice maps onto them.
_PREFERENCE_TO_FLAGS = {
    "phone": {"hipaa_voice": "YES", "hipaa_allowemail": "NO"},
    "email": {"hipaa_voice": "NO", "hipaa_allowemail": "YES"},
}


def contact_preference_fields(preference: str | None) -> dict[str, str]:
    """CareFlow's contact preference -> the OpenEMR columns that store it. `{}` for a
    preference OpenEMR has no flag for, so nothing is overwritten."""
    return dict(_PREFERENCE_TO_FLAGS.get((preference or "").strip().lower(), {}))


def pid_of(row: dict[str, Any]) -> int | None:
    """The patient id from a standard-API patient row.

    OpenEMR's `patient_data` carries BOTH an auto-increment `id` and the patient id `pid`,
    and the API reports both. They coincide on a fresh install and diverge as soon as any
    record is deleted - at which point using `id` makes every patient-scoped endpoint answer
    `{"validationErrors": {"pid": ["Invalid pid"]}}`. `pid` is the one to use.
    """
    for key in ("pid", "pubpid"):
        try:
            return int(row[key])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def contact_preference_from_row(row: dict[str, Any]) -> str | None:
    """The inverse. `None` when the record carries no usable preference."""
    for preference, flags in _PREFERENCE_TO_FLAGS.items():
        allowed = next(field for field, value in flags.items() if value == "YES")
        if str(row.get(allowed) or "").strip().upper() == "YES":
            return preference
    return None


class StandardApi:
    def __init__(self, base_url: str, api_path: str, tokens: TokenProvider):
        self._base = base_url.rstrip("/") + api_path
        self._tokens = tokens

    # --- transport -----------------------------------------------------------

    def _headers(self, force_refresh: bool = False) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._tokens.access_token(force_refresh)}", "Accept": "application/json"}

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self._base}/{path.lstrip('/')}"
        resp = httpx.request(method, url, headers=self._headers(), timeout=TIMEOUT_SECONDS, **kwargs)
        if resp.status_code == 401:
            resp = httpx.request(method, url, headers=self._headers(force_refresh=True), timeout=TIMEOUT_SECONDS, **kwargs)
        resp.raise_for_status()
        return resp

    @staticmethod
    def _data(resp: httpx.Response) -> Any:
        """OpenEMR wraps most answers as {"validationErrors", "internalErrors", "data"}; a
        few (medication create, document upload) answer bare JSON."""
        body = resp.json() if resp.content else {}
        if isinstance(body, dict) and "validationErrors" in body:
            errors = body.get("validationErrors")
            if errors:
                fields = ", ".join(sorted(errors)) if isinstance(errors, dict) else "unknown fields"
                raise httpx.HTTPError(f"OpenEMR rejected fields: {fields}")
            return body.get("data")
        return body

    def _create(self, path: str, payload: dict[str, Any]) -> str | None:
        """POST a clinical row; returns its id/uuid when OpenEMR reports one. A 200 with a
        validator map (field -> error) is a rejection on this build, not a success."""
        data = self._data(self._request("POST", path, json=payload))
        if isinstance(data, dict):
            if "uuid" in data or "id" in data:
                return str(data.get("uuid") or data.get("id"))
            if data and all(isinstance(v, dict) for v in data.values()):
                raise httpx.HTTPError(f"OpenEMR rejected fields: {', '.join(sorted(data))}")
        return None

    def _list(self, path: str, **params: Any) -> list[dict[str, Any]]:
        """Best-effort list: 404 means empty on this build; any other failure is logged."""
        try:
            data = self._data(self._request("GET", path, params=params))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                logger.debug("standard API list %s unavailable (%s)", path, exc.response.status_code)
            return []
        except httpx.HTTPError as exc:
            logger.debug("standard API list %s unavailable (%s)", path, type(exc).__name__)
            return []
        return data if isinstance(data, list) else []

    # --- the clinic ----------------------------------------------------------

    def facilities(self) -> list[dict[str, Any]]:
        """Facilities on file. OpenEMR flags the one that is a `service_location`."""
        return self._list("facility")

    def practitioner_usernames(self) -> dict[str, str]:
        """`{practitioner uuid: login username}` for the clinicians who have one.

        FHIR `Practitioner` carries no login name, so a clinician's username has to come from
        here - and it is the username, not the practitioner id, that the password grant
        authenticates. Keyed by uuid, which is what the FHIR resource uses as its id.

        These rows are the raw `users` table and include the bcrypt password hash: take the
        two fields wanted and nothing else, so a credential never leaves the adapter.
        """
        usernames: dict[str, str] = {}
        for row in self._list("practitioner"):
            uuid, username = row.get("uuid"), row.get("username")
            if uuid and username:
                usernames[str(uuid)] = str(username)
        return usernames

    # --- patients ------------------------------------------------------------

    def patient(self, patient_uuid: str) -> dict[str, Any] | None:
        """The standard-API patient row (numeric `id` = pid, `pubpid` = MRN) for a FHIR uuid."""
        try:
            data = self._data(self._request("GET", f"patient/{patient_uuid}"))
        except httpx.HTTPError:
            return None
        return data if isinstance(data, dict) and data.get("id") is not None else None

    def pid_for(self, patient_uuid: str) -> int | None:
        row = self.patient(patient_uuid)
        return pid_of(row) if row else None

    def update_patient(self, patient_uuid: str, fields: dict[str, Any]) -> None:
        """Patch demographic columns FHIR does not carry (country, contact preference).
        Only the given fields are sent; OpenEMR leaves the rest alone."""
        if fields:
            self._request("PUT", f"patient/{patient_uuid}", json=fields)

    # --- clinical rows ---------------------------------------------------------

    def create_medical_problem(self, patient_uuid: str, title: str, since: date | None = None) -> str | None:
        return self._create(f"patient/{patient_uuid}/medical_problem", {"title": title, "begdate": (since or date.today()).isoformat()})

    def create_allergy(self, patient_uuid: str, title: str, reaction: str | None = None, since: date | None = None) -> str | None:
        payload: dict[str, Any] = {"title": title, "begdate": (since or date.today()).isoformat()}
        if reaction:
            payload["reaction"] = reaction
        return self._create(f"patient/{patient_uuid}/allergy", payload)

    def create_medication(self, pid: int, title: str, note: str | None = None, since: date | None = None) -> str | None:
        payload: dict[str, Any] = {"title": title, "begdate": f"{(since or date.today()).isoformat()} 00:00:00"}
        if note:
            payload["comments"] = note
        return self._create(f"patient/{pid}/medication", payload)

    def medications(self, pid: int) -> list[str]:
        return [row["title"] for row in self._list(f"patient/{pid}/medication") if row.get("title")]

    def allergies(self, patient_uuid: str) -> list[str]:
        """Free-text allergy titles. FHIR AllergyIntolerance only carries a coded concept,
        which is "Unknown" for uncoded entries such as patient statements."""
        return [row["title"] for row in self._list(f"patient/{patient_uuid}/allergy") if row.get("title")]

    # --- the visit -----------------------------------------------------------------

    def create_encounter(self, patient_uuid: str, reason: str, when: date | None = None) -> int | None:
        """Open an encounter - the chart container a visit's notes hang off.

        Addressed by patient *uuid*, which this endpoint (unlike `soap_note`) resolves.
        `class_code` is FHIR's encounter class; CareFlow only ever produces ambulatory
        outpatient visits. Returns the numeric encounter number, which is what a form must
        be filed against - see `create_soap_note`.
        """
        data = self._data(self._request("POST", f"patient/{patient_uuid}/encounter", json={
            "pc_catid": ENCOUNTER_CATEGORY_ID,
            "class_code": ENCOUNTER_CLASS_AMBULATORY,
            "reason": reason,
            "date": (when or date.today()).isoformat(),
        }))
        if not isinstance(data, dict):
            return None
        try:
            return int(data["eid"])
        except (KeyError, TypeError, ValueError):
            return None

    def create_soap_note(self, pid: int, encounter: int, *, subjective: str,
                         objective: str, assessment: str, plan: str) -> None:
        """File a SOAP note against an encounter.

        Numeric `pid` and `encounter`, NOT uuids: OpenEMR's `insertSoapNote` writes both
        straight into `form_soap.pid` and `forms.encounter` with no validation or uuid
        lookup, so a uuid is silently cast to 0 - the note is accepted, answers 201, and is
        then orphaned in the database, attached to no patient and no visit (confirmed on
        8.3.0). Only the numeric ids actually put the note in the chart.

        OpenEMR requires all four sections and rejects anything under two characters, so an
        empty one is recorded as not collected rather than invented.
        """
        self._request("POST", f"patient/{pid}/encounter/{encounter}/soap_note", json={
            "subjective": _soap_section(subjective),
            "objective": _soap_section(objective),
            "assessment": _soap_section(assessment),
            "plan": _soap_section(plan),
        })

    # --- documents -----------------------------------------------------------------

    def upload_document(self, pid: int, filename: str, content: bytes, content_type: str, category: str = DOCUMENT_CATEGORY) -> bool:
        resp = self._request(
            "POST", f"patient/{pid}/document", params={"path": category},
            files={"document": (filename, content, content_type)},
        )
        return bool(self._data(resp))

    def documents(self, pid: int, category: str = DOCUMENT_CATEGORY) -> list[dict[str, Any]]:
        return self._list(f"patient/{pid}/document", path=category)
