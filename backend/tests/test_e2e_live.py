"""Live end-to-end: one patient through every stage with the REAL models (no fakes) and the
real OpenEMR - intake chat, X-ray + scanned lab upload, pre-screening (file reads, AI routing,
AI differential), doctor assistant, report draft, signing, referral to another department,
the patient moving the referred booking, the specialist's assistant and sign-off, release.

Opt-in, because it spends model quota (roughly 20-40 Sonnet calls) and takes minutes:

    CAREFLOW_LIVE_E2E=1 pytest tests/test_e2e_live.py -s

Needs the synthetic files in the repo-root `test-files/` folder (gitignored).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import hospital_config
from app.services.hms import effective_doctors_config
from tests.helpers import BASE, DOCTOR_CREDENTIALS, FINALIZER_CREDENTIALS, new_identified_session, wait_for_status

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("CAREFLOW_LIVE_E2E") != "1", reason="set CAREFLOW_LIVE_E2E=1 to spend model quota"),
    pytest.mark.skipif(not settings.llm_enabled, reason="no model API key configured"),
]

FILES = Path(__file__).resolve().parents[2] / "test-files"
REPORT: list[str] = []


def log(line: str) -> None:
    REPORT.append(line)
    print(f"  {line}", flush=True)


def answer(question: str) -> str:
    """A consistent synthetic patient: community-acquired pneumonia picture."""
    q = question.lower()
    if "metformin" in q or "amlodipine" in q or "atorvastatin" in q or "prescription" in q:
        return "I take the Metformin and the Amlodipine every day, but I stopped the Atorvastatin last month."
    if "allerg" in q:
        return "No allergies that I know of."
    if "medic" in q or "tablet" in q or "taking" in q:
        return "Only paracetamol 500 mg when the fever is high."
    if "how long" in q or "when did" in q or "since" in q:
        return "About five days now, getting worse."
    if "history" in q or "condition" in q or "past" in q or "diabet" in q or "asthma" in q:
        return "No long-term illnesses. I don't smoke."
    if "chest pain" in q or "pain" in q:
        return "A sharp pain on the right side of my chest when I breathe in deeply."
    if "temperature" in q or "fever" in q:
        return "Around 101 to 102 F, with chills at night."
    if "phlegm" in q or "sputum" in q or "cough" in q:
        return "Yellow-green phlegm, no blood."
    if "breath" in q:
        return "Breathless when climbing stairs, fine at rest."
    return "Nothing else really, I just feel very tired."


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _booking_id(case_id: str) -> str | None:
    import uuid

    from app.db import db_session
    from app.models import PatientCase
    with db_session() as db:
        return db.get(PatientCase, uuid.UUID(case_id)).hms_appointment_id


def _on_calendar(event_id: str | None) -> bool:
    """Read straight from OpenEMR's calendar table (the test cleanup removes it afterwards)."""
    from app.integrations.hms.openemr import provisioning
    if not event_id:
        return False
    with provisioning._transaction() as cur:
        cur.execute("SELECT 1 FROM openemr_postcalendar_events WHERE pc_eid = %s", (int(event_id),))
        return cur.fetchone() is not None


def _timed(label: str, fn):
    start = time.perf_counter()
    result = fn()
    log(f"{label}: {time.perf_counter() - start:.1f}s")
    return result


def test_full_journey_with_real_models(client):
    assert FILES.is_dir(), f"missing {FILES}"
    sid, cid = new_identified_session(client)
    log(f"patient case {cid}")

    # 1. Intake chat (real extractor / planner / interviewer).
    r = _timed("intake turn 1", lambda: client.post(f"{BASE}/intake-sessions/{sid}/messages", json={
        "content": "I have had fever, a cough with yellow phlegm and breathlessness for 5 days"}).json())
    # Upload before intake closes, so pre-screening reads the files.
    for name, kind, mime in (("chest_xray_synthetic.png", "radiology", "image/png"),
                             ("lab_report_scanned.pdf", "lab_report", "application/pdf"),
                             ("prescription_photo.png", "prescription", "image/png")):
        with open(FILES / name, "rb") as fh:
            started = time.perf_counter()
            up = client.post(f"{BASE}/cases/{cid}/attachments", files={"file": (name, fh, mime)},
                             data={"kind": kind, "uploaded_by": "patient"})
            log(f"upload {name}: {time.perf_counter() - started:.1f}s")
        assert up.status_code == 201, up.text
        if kind == "prescription":
            meds = up.json()["extracted_medications"]
            log(f"medicines read off the prescription photo: {meds}")
            assert {"metformin", "amlodipine", "atorvastatin"} <= {m.split()[0].lower() for m in meds}, meds
    turns = 1
    asked_about_rx = False
    while not r["intake_complete"] and turns < 20:
        asked_about_rx |= "metformin" in r["reply"].lower()
        if "metformin" in r["reply"].lower():
            log(f"intake asked about the prescription: {r['reply'][:200]}")
        reply = answer(r["reply"])
        r = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": reply}).json()
        turns += 1
    assert r["intake_complete"], f"intake did not close in {turns} turns: last reply {r['reply']!r}"
    assert asked_about_rx, "the intake never asked about the prescription's medicines"
    log(f"intake closed after {turns} turns; still missing: {r['missing_fields'] or 'none'}")

    # 2. Pre-screening with every agent live.
    detail = _timed("pre-screening", lambda: wait_for_status(client, cid, "NEEDS_REVIEW", timeout_s=300))
    log(f"triage: {detail['triage']['priority']} {detail['triage']['rule_codes']}")
    log(f"routing: {detail['routing']['department_name']} / {detail['routing']['doctor_name']}")
    log(f"routing rationale: {detail['routing']['rationale'][:200]}")
    reads = (detail.get("file_reads") or {}).get("sections", {}).get("reads", [])
    for rd in reads:
        log(f"file read {rd['filename']}: {rd['status']} - {rd.get('impression') or rd.get('note') or ''}")
    assert reads and all(rd["status"] == "read" for rd in reads), reads
    diffs = (detail.get("ai_diagnosis") or {}).get("sections", {}).get("differentials", [])
    log("AI differential: " + "; ".join(f"{d['condition']} ({d['likelihood']})" for d in diffs))
    assert diffs, "no AI differential"
    assert detail["prescreening_summary"], "no pre-screening briefing"
    meds_on_file = [e["name"] for e in detail["allergies_medications"] if e["kind"] == "medication"]
    log(f"patient medicines recorded from the answer: {meds_on_file}")
    brief = detail["prescreening_summary"]["sections"].get("context_for_clinician", "")
    log(f"briefing context: {brief[:400]}")
    assert "metformin" in brief.lower() or "prescription" in brief.lower(), brief

    # 3. Doctor tools on the first visit.
    reply = _timed("doctor assistant", lambda: client.post(f"{BASE}/cases/{cid}/assistant", json={
        "message": "What does the chest X-ray show, and do the labs support infection?",
        "doctor_context": "General Medicine"}).json()["reply"])
    log(f"assistant: {reply[:220]}")
    draft = _timed("report draft", lambda: client.post(f"{BASE}/cases/{cid}/report/draft").json())
    log(f"draft diagnosis: {(draft.get('diagnosis') or '')[:120]}")
    note = client.post(f"{BASE}/cases/{cid}/consultation-notes", json={
        **DOCTOR_CREDENTIALS, "notes": draft.get("notes") or "Fever, productive cough, R lower zone opacity.",
        "diagnosis": "Community-acquired pneumonia, right lower lobe",
        "prescription": "Amoxicillin-clavulanate 625 mg PO TDS x 7 days",
        "tests_ordered": "Repeat CBC, CRP in 3 days",
        "follow_up_instructions": "Follow-up: 3 days",
        "referral_notes": "Persistent exertional breathlessness out of proportion; please assess cardiac cause."})
    assert note.status_code == 201, note.text

    # 4. Referral to another staffed department.
    config = effective_doctors_config(hospital_config.load())
    staffed = {d["department_id"] for d in config.get("doctors") or []}
    target = next(d for d in config["departments"] if d["id"] in staffed and d["id"] != detail["routing"]["department_id"])
    res = _timed("referral", lambda: client.post(f"{BASE}/cases/{cid}/referrals", json={
        **DOCTOR_CREDENTIALS, "to_department_id": target["id"], "urgency": "soon",
        "reason": "Exertional breathlessness out of proportion to the pneumonia",
        "question": "Please rule out a cardiac cause"}))
    assert res.status_code == 201, res.text
    made = res.json()["referrals_made"][0]
    log(f"referral -> {made['to_department_name']}: {made['status']}, {made['doctor_name']}, {made['appointment_start']}, "
        f"OpenEMR record: {made['hms_recorded']}")
    child_id = made["case_id"]

    # 5. Patient side: sees it, moves the time.
    visits = client.get(f"{BASE}/cases/my-visits").json()
    mine = next(v for v in visits if v["case_id"] == child_id)
    log(f"patient sees: {mine['visit_type']} by {mine['referred_by']} at {mine['department_name']}")
    view = client.get(f"{BASE}/cases/{child_id}/patient-view").json()
    assert "breathlessness out of proportion" not in str(view)  # the reason stays clinician-only
    other = next((s for s in view["routing"]["slot_options"]
                  if s["id"] != view["routing"]["selected_slot_id"] and not s.get("taken")), None)
    first_booking = _booking_id(child_id)
    assert _on_calendar(first_booking), "the referral's booking is not on the OpenEMR calendar"
    log(f"referral booking on the OpenEMR calendar: event {first_booking}")
    if other:
        moved = client.post(f"{BASE}/cases/{child_id}/appointment-slot", json={"slot_id": other["id"]})
        assert moved.status_code == 200, moved.text
        new_booking = _booking_id(child_id)
        assert new_booking != first_booking and _on_calendar(new_booking) and not _on_calendar(first_booking)
        log(f"patient moved the referred visit to {other['start']} with {other.get('doctor_name')}: "
            f"event {first_booking} removed, {new_booking} on the calendar")

    # 6. Specialist side, live agents on the referred visit.
    diag = _timed("AI differential on referred visit", lambda: client.post(f"{BASE}/cases/{child_id}/ai-diagnosis"))
    assert diag.status_code == 200, diag.text
    log("specialist differential: " + "; ".join(
        f"{d['condition']} ({d['likelihood']})" for d in diag.json()["sections"].get("differentials", [])))
    reply = _timed("specialist assistant", lambda: client.post(f"{BASE}/cases/{child_id}/assistant", json={
        "message": "What did the referring doctor diagnose and prescribe, and what is my question?",
        "doctor_context": target["name"]}).json()["reply"])
    log(f"specialist assistant: {reply[:260]}")
    assert "amoxicillin" in reply.lower() or "pneumonia" in reply.lower(), reply

    seen = client.post(f"{BASE}/cases/{child_id}/consultation-notes", json={
        **DOCTOR_CREDENTIALS, "notes": "ECG sinus tachycardia, no ischaemic change. Echo normal.",
        "diagnosis": "No cardiac cause; breathlessness from pneumonia",
        "follow_up_instructions": "Follow-up: with General Medicine as planned"})
    assert seen.status_code == 201, seen.text
    fin = _timed("release referred visit", lambda: client.post(f"{BASE}/cases/{child_id}/finalize", json=FINALIZER_CREDENTIALS))
    assert fin.status_code == 200 and fin.json()["status"] == "COMPLETED", fin.text
    back = client.get(f"{BASE}/cases/{cid}").json()["referrals_made"][0]
    log(f"loop closed on the first visit: {back['status']} - {back['outcome_diagnosis']}")
    assert back["status"] == "completed"

    print("\nLIVE E2E REPORT\n" + "\n".join(REPORT))


def test_late_upload_is_read_when_the_doctor_regenerates(client):
    """An X-ray added after pre-screening reaches the AI differential on Regenerate."""
    sid, cid = new_identified_session(client)
    r = client.post(f"{BASE}/intake-sessions/{sid}/messages",
                    json={"content": "fever and cough with yellow phlegm for five days"}).json()
    for _ in range(20):
        if r["intake_complete"]:
            break
        r = client.post(f"{BASE}/intake-sessions/{sid}/messages", json={"content": answer(r["reply"])}).json()
    assert r["intake_complete"]
    detail = wait_for_status(client, cid, "NEEDS_REVIEW", timeout_s=300)
    assert not (detail.get("file_reads") or {}).get("sections", {}).get("reads")  # nothing uploaded yet

    with open(FILES / "chest_xray_synthetic.png", "rb") as fh:
        up = client.post(f"{BASE}/cases/{cid}/attachments", files={"file": ("late_xray.png", fh, "image/png")},
                         data={"kind": "radiology", "uploaded_by": "patient"})
    assert up.status_code == 201, up.text
    diag = _timed("regenerate with a late upload", lambda: client.post(f"{BASE}/cases/{cid}/ai-diagnosis"))
    assert diag.status_code == 200, diag.text
    reads = client.get(f"{BASE}/cases/{cid}").json()["file_reads"]["sections"]["reads"]
    late = next(r for r in reads if r["filename"] == "late_xray.png")
    log(f"late upload read on regenerate: {late['status']} - {late.get('impression')}")
    assert late["status"] == "read"
    text = str(diag.json()["sections"]).lower()
    log("differential after the late X-ray: " + "; ".join(d["condition"] for d in diag.json()["sections"]["differentials"]))
    assert "x-ray" in text or "opacity" in text or "consolidation" in text, text[:500]
