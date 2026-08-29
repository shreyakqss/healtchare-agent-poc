"""Pure FHIR <-> HMS schema mapping for OpenEMR. No I/O, no state.

OpenEMR's FHIR surface does not expose a clean 1:1 shape for the flat `HMSPatient` /
`HMSPractitioner` / `HMSSlot` contracts, and it bends the spec in places (see
`codeable_texts`), so everything here is best-effort and tolerant of missing fields.
Keeping it pure makes each mapping unit-testable without a server.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.domain.demographics import age_from_birth_date, parse_fhir_date
from app.integrations.hms.schemas import (
    HMSAddress,
    HMSDocument,
    HMSPatient,
    HMSPractitioner,
    HMSSlot,
    PatientRegistration,
)

Resource = dict[str, Any]

UNKNOWN_DEPARTMENT = "unknown"
FHIR_GENDERS = {"male", "female", "other", "unknown"}


# --- generic accessors -------------------------------------------------------

def bundle_entries(bundle: Resource) -> list[Resource]:
    return [entry["resource"] for entry in bundle.get("entry", []) if "resource" in entry]


def reference_id(reference: str | None) -> str:
    """`"Practitioner/abc"` or a full `.../Patient/abc` URL -> `"abc"`; a bare id passes through."""
    return (reference or "").rstrip("/").rsplit("/", 1)[-1]


def mrn_from_identifiers(identifiers: list[Resource] | None) -> str | None:
    identifiers = identifiers or []
    for ident in identifiers:
        for coding in (ident.get("type") or {}).get("coding") or []:
            if isinstance(coding, dict) and coding.get("code") == "MR":
                return ident.get("value")
    return identifiers[0].get("value") if identifiers else None


def human_name(resource: Resource) -> str:
    names = resource.get("name") or []
    if not names:
        return "Unknown"
    first = names[0]
    if first.get("text"):
        return first["text"]
    given = " ".join(first.get("given") or [])
    family = first.get("family") or ""
    return " ".join(part for part in (given, family) if part) or "Unknown"


def split_name(full_name: str) -> tuple[list[str], str]:
    """OpenEMR's Patient validator needs split given/family: last word is the family name."""
    parts = full_name.split()
    return (parts[:-1], parts[-1]) if len(parts) > 1 else ([], full_name)


def telecom_value(telecom: list[Resource] | None, system: str) -> str | None:
    for entry in telecom or []:
        if entry.get("system") == system:
            return entry.get("value")
    return None


def coding_code(coding: Any) -> str | None:
    """A coding's code. OpenEMR sometimes emits `coding: ["207RC0000X"]` - bare strings
    where FHIR specifies objects - so both shapes are accepted."""
    if isinstance(coding, str):
        return coding
    if isinstance(coding, dict):
        return coding.get("code")
    return None


def codeable_texts(node: Any) -> list[str]:
    """Every human-readable label in a CodeableConcept (or a list of them)."""
    if isinstance(node, list):
        return [text for item in node for text in codeable_texts(item)]
    if not isinstance(node, dict):
        return []
    texts = [node["text"]] if node.get("text") else []
    for coding in node.get("coding") or []:
        if isinstance(coding, dict) and (coding.get("display") or coding.get("code")):
            texts.append(coding.get("display") or coding["code"])
    return texts


def codeable_codes(node: Any) -> list[str]:
    """Every code in a CodeableConcept (or a list of them), e.g. NUCC taxonomy codes."""
    if isinstance(node, list):
        return [code for item in node for code in codeable_codes(item)]
    if not isinstance(node, dict):
        return []
    return [code for coding in node.get("coding") or [] if (code := coding_code(coding))]


def codeable_text(resource: Resource, field: str) -> str | None:
    """First human-readable label of `resource[field]`."""
    texts = codeable_texts(resource.get(field))
    return texts[0] if texts else None


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def fallback_reference(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


# --- read-side mappers -------------------------------------------------------

def address_from_resource(resource: Resource) -> HMSAddress | None:
    addresses = resource.get("address") or []
    if not addresses:
        return None
    # Prefer the home address; OpenEMR records one, other servers may list several.
    chosen = next((a for a in addresses if a.get("use") == "home"), addresses[0])
    lines = [line for line in (chosen.get("line") or []) if line]
    return HMSAddress(
        line1=lines[0] if lines else "",
        line2=" ".join(lines[1:]) or None,
        city=chosen.get("city") or "",
        state=chosen.get("state") or "",
        postal_code=chosen.get("postalCode") or "",
        country=chosen.get("country") or "",
    )


def patient_from_resource(
    resource: Resource,
    *,
    conditions: list[str] | None = None,
    medications: list[str] | None = None,
    allergies: list[str] | None = None,
    last_visit: datetime | None = None,
    fallback_mrn: str | None = None,
    country_fallback: str | None = None,
    contact_preference: str | None = None,
) -> HMSPatient:
    birth_date = parse_fhir_date(resource.get("birthDate"))
    telecom = resource.get("telecom")
    address = address_from_resource(resource)
    # OpenEMR drops address.country on a FHIR write but keeps it on the patient row, so the
    # caller can hand it back in rather than the patient re-entering it every visit. A record
    # with no FHIR address at all still gets one, so the country is not lost either.
    if country_fallback and not (address and address.country):
        address = (address or HMSAddress()).model_copy(update={"country": country_fallback})
    return HMSPatient(
        mrn=mrn_from_identifiers(resource.get("identifier")) or fallback_mrn or resource.get("id", ""),
        name=human_name(resource),
        age=age_from_birth_date(birth_date) if birth_date else 0,
        sex=resource.get("gender", "unknown"),
        birth_date=birth_date,
        phone=telecom_value(telecom, "phone"),
        email=telecom_value(telecom, "email"),
        address=address,
        contact_preference=contact_preference,
        conditions=conditions or [],
        medications=medications or [],
        allergies=allergies or [],
        last_visit=last_visit.date() if last_visit else None,
    )


def document_from_resource(resource: Resource) -> HMSDocument:
    contents = resource.get("content") or []
    attachment = (contents[0] or {}).get("attachment") if contents else {}
    return HMSDocument(
        reference=resource.get("id") or fallback_reference("DOC"),
        title=(resource.get("type") or {}).get("text") or resource.get("description") or "Document",
        content_type=(attachment or {}).get("contentType") or "text/plain",
        created=parse_datetime(resource.get("date")),
    )


def slot_from_resource(resource: Resource, *, department_id: str, practitioner_id: str | None) -> HMSSlot:
    return HMSSlot(
        id=resource.get("id", ""),
        practitioner_id=practitioner_id or "",
        department_id=department_id,
        start=datetime.fromisoformat(resource["start"]),
        end=datetime.fromisoformat(resource["end"]),
    )


def practitioner_from_resource(resource: Resource, role: Resource | None = None,
                               username: str | None = None) -> HMSPractitioner:
    """`username` comes from the standard API - FHIR carries no login name for a practitioner."""
    role = role or {}
    return HMSPractitioner(
        id=resource.get("id") or "",
        name=human_name(resource),
        department_id=role.get("department_id", UNKNOWN_DEPARTMENT),
        specialty=role.get("specialty"),
        working_days=list(role.get("working_days", [])),
        username=username,
    )


# --- specialty -> department -------------------------------------------------

def role_specialties(resource: Resource) -> tuple[list[str], list[str]]:
    """`(codes, texts)` a PractitionerRole claims.

    OpenEMR 8.3 leaves `specialty` null and puts the taxonomy in `code[]` instead
    (confirmed live), so both fields are read. Codes are NUCC taxonomy ids such as
    `207RC0000X`; texts are their names ("Cardiovascular Disease").
    """
    codes: list[str] = []
    texts: list[str] = []
    for field in ("specialty", "code"):
        node = resource.get(field)
        codes += codeable_codes(node)
        texts += codeable_texts(node)
    return codes, texts


def match_department(codes: list[str], texts: list[str], departments: list[Resource]) -> str:
    """Which configured department a practitioner's specialty belongs to.

    In order: an exact NUCC taxonomy code from the department's `specialty_codes`, an exact
    (case-insensitive) name from its `specialty_names`, then a substring match on the
    department's own name/id. A practitioner usually carries several specialties - OpenEMR
    tacks a generic one onto every role - so a non-default department always wins over the
    default one. Returns `UNKNOWN_DEPARTMENT` when nothing matches.
    """
    wanted_codes = {code.strip().upper() for code in codes if code}
    wanted_texts = {text.strip().lower() for text in texts if text}
    matches: list[Resource] = []
    for department in departments:
        configured_codes = {str(c).strip().upper() for c in department.get("specialty_codes") or []}
        configured_names = {str(n).strip().lower() for n in department.get("specialty_names") or []}
        name = (department.get("name") or "").strip().lower()
        dept_id = (department.get("id") or "").strip().lower()
        substring = any(
            (name and (name in text or text in name)) or (dept_id and (dept_id in text or text in dept_id))
            for text in wanted_texts
        )
        if (wanted_codes & configured_codes) or (wanted_texts & configured_names) or substring:
            matches.append(department)
    if not matches:
        return UNKNOWN_DEPARTMENT
    specific = next((d for d in matches if not d.get("default")), None)
    return (specific or matches[0])["id"]


def roles_by_practitioner(role_resources: list[Resource], departments: list[Resource]) -> dict[str, Resource]:
    """PractitionerRole bundle -> {practitioner_id: {department_id, specialty, working_days}}.

    A practitioner can hold several roles; every specialty they carry is considered together
    (see `match_department`). Working days come from FHIR `availableTime.daysOfWeek`, which
    already uses the same mon/tue/... codes the rest of the app does, and are unioned.
    """
    collected: dict[str, dict[str, Any]] = {}
    for resource in role_resources:
        practitioner_id = reference_id((resource.get("practitioner") or {}).get("reference"))
        if not practitioner_id:
            continue
        entry = collected.setdefault(practitioner_id, {"codes": [], "texts": [], "working_days": []})
        codes, texts = role_specialties(resource)
        entry["codes"] += codes
        entry["texts"] += texts
        for available in resource.get("availableTime") or []:
            for day in available.get("daysOfWeek") or []:
                if day not in entry["working_days"]:
                    entry["working_days"].append(day)

    roles: dict[str, Resource] = {}
    for practitioner_id, entry in collected.items():
        department_id = match_department(entry["codes"], entry["texts"], departments)
        # The most specific label the EMR gave us, for display: the last text is the
        # specialty proper, since OpenEMR lists the generic one first.
        roles[practitioner_id] = {
            "department_id": department_id,
            "specialty": entry["texts"][-1] if entry["texts"] else None,
            "working_days": entry["working_days"],
        }
    return roles


# --- write-side builders -----------------------------------------------------

def patient_body(existing: Resource | None, registration: PatientRegistration) -> Resource:
    """Patient resource for create/update from a CareFlow registration.

    Unknown fields on an existing resource are preserved. `extension` is dropped because
    this OpenEMR release 500s on ANY extension array in a Patient write (confirmed live).
    `contact_preference` is intentionally not written - CareFlow's own fact row is its
    source of truth.
    """
    body: Resource = dict(existing or {"resourceType": "Patient"})
    body.pop("extension", None)
    given, family = split_name(registration.name)
    body["name"] = [{"use": "official", "given": given, "family": family}]
    body["birthDate"] = registration.birth_date.isoformat()
    body["gender"] = registration.gender if registration.gender in FHIR_GENDERS else "unknown"
    telecom = [t for t in body.get("telecom", []) if t.get("system") not in {"phone", "email"}]
    if registration.phone:
        telecom.append({"system": "phone", "value": registration.phone, "use": "mobile"})
    if registration.email:
        telecom.append({"system": "email", "value": registration.email, "use": "home"})
    body["telecom"] = telecom
    lines = [registration.address_line1] + ([registration.address_line2] if registration.address_line2 else [])
    body["address"] = [{
        "use": "home", "line": lines, "city": registration.city, "state": registration.state,
        "postalCode": registration.postal_code, "country": registration.country,
    }]
    return body


def document_reference_body(title: str, content_b64: str, content_type: str, patient_id: str | None) -> Resource:
    body: Resource = {
        "resourceType": "DocumentReference",
        "status": "current",
        "type": {"text": title},
        "content": [{"attachment": {"contentType": content_type, "data": content_b64, "title": title}}],
    }
    if patient_id:
        body["subject"] = {"reference": f"Patient/{patient_id}"}
    return body


def proposed_appointment_body(
    *, department_id: str, reason: str, patient_id: str | None, practitioner_id: str | None, slot_id: str | None
) -> Resource:
    """FHIR Appointment with status `proposed` - never `booked`. Confirming an appointment
    is outside the POC's scope; staff do that in the hospital system."""
    participants = []
    if patient_id:
        participants.append({"actor": {"reference": f"Patient/{patient_id}"}, "status": "needs-action"})
    if practitioner_id:
        participants.append({"actor": {"reference": f"Practitioner/{practitioner_id}"}, "status": "needs-action"})
    body: Resource = {
        "resourceType": "Appointment",
        "status": "proposed",
        "serviceType": [{"text": department_id}],
        "reasonCode": [{"text": reason}],
        "participant": participants or [{"status": "needs-action"}],
    }
    if slot_id:
        body["slot"] = [{"reference": f"Slot/{slot_id}"}]
    return body
