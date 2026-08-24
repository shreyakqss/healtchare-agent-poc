"""End-to-end smoke test over the HTTP API. Run with the API up: python scripts/smoke.py"""

from __future__ import annotations

import sys

import httpx

BASE = "http://localhost:8000/api/v1/healthcare"


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=120)
    print("health", httpx.get("http://localhost:8000/health").json()["llm"])

    s = c.post("/intake-sessions", json={"mrn": "MRN-10024"}).json()
    sid, cid = s["session_id"], s["case_id"]
    print("session", s["status"], s["missing_fields"])

    print("consent", c.post(f"/intake-sessions/{sid}/consent", json={"granted": True}).json()["status"])

    for msg in ["I have had a bad headache for three weeks.", "It is mostly behind my eyes.", "No", "No medication", "No allergies", "Phone please"]:
        r = c.post(f"/intake-sessions/{sid}/messages", json={"content": msg})
        r.raise_for_status()
        body = r.json()
        print(f"  > {msg!r:45} -> asks={body['asks_field']!s:20} missing={len(body['missing_fields'])} complete={body['intake_complete']}")
        if body["intake_complete"]:
            break

    # streaming variant
    with c.stream("POST", f"/intake-sessions/{sid}/messages/stream", json={"content": "anything else?"}) as r:
        frames = [line for line in r.iter_lines() if line.startswith("data:")]
    print("stream frames", len(frames), frames[-1][:80])

    # upload a text report
    up = c.post(f"/cases/{cid}/attachments", files={"file": ("report.txt", b"Synthetic lab report. Hb 13.2", "text/plain")}, data={"kind": "lab_report"})
    print("upload", up.status_code, up.json()["has_text"])

    assert c.post(f"/cases/{cid}/consultation-notes", json={"doctor_id": "dr_mehta", "notes": "x"}).status_code == 409, "gate failed"

    d = c.post(f"/cases/{cid}/prescreen").json()
    print("prescreen", d["status"], d["triage"]["priority"], d["triage"]["rule_codes"], d["routing"]["department_name"], d["routing"]["suggested_slot"] and d["routing"]["suggested_slot"]["id"])
    assert d["prescreening_summary"] is not None

    assert c.post(f"/cases/{cid}/finalize").status_code == 409, "finalize gate failed"

    rv = c.post(f"/cases/{cid}/review", json={"decision": "edit", "reviewer_id": "dr_mehta", "reviewer_role": "doctor", "edits": {"reported_symptoms": "headache behind the eyes, 3 weeks"}})
    print("review", rv.status_code, rv.json()["decision"])

    n = c.post(f"/cases/{cid}/consultation-notes", json={"doctor_id": "dr_mehta", "consultation_mode": "in_person", "notes": "Tension-type pattern. Advised hydration and sleep.", "prescription": "Paracetamol 500mg as needed", "follow_up_instructions": "Review in 2 weeks if persisting."})
    print("note", n.status_code)

    f = c.post(f"/cases/{cid}/finalize").json()
    print("finalize", f["status"], f["final_summary"]["generated_by"], f["care_tasks"][0]["hms_reference"], f["care_tasks"][0]["status"])

    a = c.get(f"/cases/{cid}/audit").json()
    print("audit events", len(a), [e["action"] for e in a][:6], "...")
    print("cases", len(c.get("/cases").json()), "overview", c.get("/cases/overview").json()["by_priority"])
    print("hms requests", len(c.get("/hms/appointment-requests").json()))
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())