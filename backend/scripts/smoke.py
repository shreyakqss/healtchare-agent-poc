"""End-to-end smoke test over the HTTP API. Run with the API up: python scripts/smoke.py

Walks one case through every stage: session -> consent -> identity form -> clinical chat
(streamed and drained) -> upload -> prescreen -> review -> consultation note -> finalise,
asserting the human-review gates along the way.

This registers a real patient in the connected hospital system and leaves the record,
documents and appointment request behind - point it only at a test instance.

Environment:
  SMOKE_API       API origin, default http://localhost:8000
  SMOKE_SESSION / SMOKE_CSRF
                  opaque cookies from a synthetic Keycloak user carrying both patient and
                  clinician roles, the active clinic_id, and the mapped hms_username.
  SMOKE_USER / SMOKE_PASSWORD
                  clinician login the hospital system verifies (a real OpenEMR user).
"""

from __future__ import annotations

import os
import sys
import time

import httpx

API = os.environ.get("SMOKE_API", "http://localhost:8000")
BASE = f"{API}/api/v1/healthcare"
CLINICIAN = {"username": os.environ.get("SMOKE_USER", "dr_mehta"), "password": os.environ.get("SMOKE_PASSWORD", "demo")}

IDENTITY = {
    "name": "Synthetic Patient",
    "birth_date": "1985-04-02",
    "gender": "female",
    "phone": "+91 90000 00001",
    "address_line1": "12 Demo Road",
    "city": "Pune",
    "state": "Maharashtra",
    "postal_code": "411001",
    "country": "India",
    "contact_preference": "phone",
}


def main() -> int:
    session, csrf = os.environ.get("SMOKE_SESSION"), os.environ.get("SMOKE_CSRF")
    if not session or not csrf:
        print("Set SMOKE_SESSION and SMOKE_CSRF from a signed-in synthetic test account.", file=sys.stderr)
        return 2
    c = httpx.Client(
        base_url=BASE,
        timeout=120,
        cookies={"careflow_session": session, "careflow_csrf": csrf},
        headers={"x-csrf-token": csrf},
    )
    health = httpx.get(f"{API}/health").json()
    print("health", health["status"], health["version"])

    s = c.post("/intake-sessions", json={}).raise_for_status().json()
    sid, cid = s["session_id"], s["case_id"]
    print("session", s["status"], s["missing_fields"])
    print("consent", c.post(f"/intake-sessions/{sid}/consent", json={"granted": True}).json()["status"])

    ident = c.post(f"/intake-sessions/{sid}/identity", json=IDENTITY)
    ident.raise_for_status()
    print("identity", ident.json()["status"], "missing:", ident.json()["missing_fields"])

    for msg in ["I have had a bad headache for three weeks.", "It is mostly behind my eyes.", "No", "No medication", "No allergies"]:
        body = c.post(f"/intake-sessions/{sid}/messages", json={"content": msg}).raise_for_status().json()
        print(f"  > {msg!r:45} -> asks={body['asks_field']!s:20} missing={len(body['missing_fields'])} complete={body['intake_complete']}")
        if body["intake_complete"]:
            break

    with c.stream("POST", f"/intake-sessions/{sid}/messages/stream", json={"content": "anything else?"}) as r:
        frames = [line for line in r.iter_lines() if line.startswith("data:")]
    print("stream frames", len(frames), frames[-1][:80])

    up = c.post(
        f"/cases/{cid}/attachments",
        files={"file": ("report.txt", b"Synthetic lab report. Hb 13.2 g/dl, reference range normal", "text/plain")},
        data={"kind": "lab_report"},
    )
    print("upload", up.status_code, up.json()["has_text"])
    c.post(f"/cases/{cid}/attachments/skip", json={"kind": "prescription", "reason": "smoke test"})

    note_body = {"doctor_username": CLINICIAN["username"], "doctor_password": CLINICIAN["password"], "notes": "x"}
    assert c.post(f"/cases/{cid}/consultation-notes", json=note_body).status_code == 409, "consultation gate failed"

    # Resolving the last required document started pre-screening in the background.
    for _ in range(120):
        d = c.get(f"/cases/{cid}").raise_for_status().json()
        if d["status"] == "NEEDS_REVIEW":
            break
        time.sleep(1)
    assert d["status"] == "NEEDS_REVIEW", f"prescreen did not complete: {d['status']}"
    slot = d["routing"]["suggested_slot"]
    print("prescreen", d["status"], d["triage"]["priority"], d["triage"]["rule_codes"], d["routing"]["department_name"], slot and slot["id"])
    assert d["prescreening_summary"] is not None

    finalize_body = {"finalizer_username": CLINICIAN["username"], "finalizer_password": CLINICIAN["password"]}
    assert c.post(f"/cases/{cid}/finalize", json=finalize_body).status_code == 409, "finalize gate failed"

    rv = c.post(f"/cases/{cid}/review", json={
        "decision": "edit", "reviewer_username": CLINICIAN["username"], "reviewer_password": CLINICIAN["password"],
        "edits": {"reported_symptoms": "headache behind the eyes, 3 weeks"},
    })
    print("review", rv.status_code, rv.json()["decision"])

    n = c.post(f"/cases/{cid}/consultation-notes", json={
        **note_body, "consultation_mode": "in_person", "notes": "Tension-type pattern. Advised hydration and sleep.",
        "prescription": "Paracetamol 500mg as needed", "follow_up_instructions": "Review in 2 weeks if persisting.",
    })
    print("note", n.status_code)

    f = c.post(f"/cases/{cid}/finalize", json=finalize_body).raise_for_status().json()
    print("finalize", f["status"], f["final_summary"]["generated_by"], f["care_tasks"][0]["hms_reference"], f["care_tasks"][0]["status"])
    assert f["care_tasks"][0]["status"] == "draft"

    a = c.get(f"/cases/{cid}/audit").json()
    print("audit events", len(a), [e["action"] for e in a][:6], "...")
    print("cases", len(c.get("/cases").json()))
    roster = c.get("/hospital/roster").json()
    print("roster", roster["source"], len(roster["doctors"]))
    print("hms requests", len(c.get("/hms/appointment-requests").json()))
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
