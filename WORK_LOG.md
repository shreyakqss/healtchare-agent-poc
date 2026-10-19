# CareFlow — Progress Report

**Project:** CareFlow — AI-assisted patient intake and doctor routing (proof of concept)  
**Prepared by:** Prisha Gupta  
**Reporting period:** Progress through 16 October 2026  
**Overall status:** Core scheduling and doctor-administration work is implemented; changes still need to be committed. One product decision is needed before the next feature can begin.

## 1. Executive summary

CareFlow helps patients describe their problem, routes them to an appropriate department and doctor, and lets a doctor review the case. The latest work focused on making appointment scheduling safer and making doctor setup easier for hospital administrators.

### What is done

- **Prevented double booking within CareFlow:** a doctor and appointment time can be held by only one patient at a time.
- **Improved appointment availability:** patients see up-to-date appointment options; unavailable times remain visible but are disabled.
- **Made consulting hours visible:** patients can see the doctor's weekly hours.
- **Added safeguards and audit records:** doctor setup is validated, hospital access is scoped to the admin's own hospital, and admin actions are recorded.
- **Added an operator guide:** includes how to run the app, roles and logins, doctor setup, and common troubleshooting.

### What is not done yet

- The manager needs to choose how CareFlow should select a doctor when multiple doctors are available.
- Add in Admin → Doctors page: admins can add, view, extend the published hours of, deactivate, reactivate, or remove doctors.

## 2. Status at a glance

| Workstream | Status | Plain-English result |
|---|---|---|
| Appointment holds / double-booking prevention | Implemented and tested | Two patients cannot successfully hold the same doctor's time through CareFlow. |
| Live appointment options | Implemented | The list refreshes from the doctor's current calendar when opened. Taken times are greyed out; released times can become available again. |
| Doctor consulting hours | Implemented | Patients can see weekly consulting hours on the appointment card. |
| Doctor administration | Implemented and tested against OpenEMR and Keycloak | Admins can manage doctors from one page, with validation and access controls. |
| Git commits | Pending | The latest work still needs to be committed; some 14 October work is already on `feature/slot-hold-no-double-booking`. |
| Doctor-assignment rule | Decision needed | Current behaviour chooses the first doctor listed, not necessarily the doctor who can see the patient soonest. |
| Existing test failures | Follow-up | Two older tests fail intermittently or independently of this work; investigate separately. |

## 3. Completed work

### 3.1 Appointment scheduling — 14 October 2026

**Problem:** CareFlow sends appointment requests to hospital scheduling staff rather than booking directly in OpenEMR. Previously, CareFlow did not keep track of times already selected by its own patients. This could let two patients select the same doctor and time.

**What changed:**

- **One patient per doctor/time:** the database enforces a unique hold for each doctor and start time.
- **Automatic default:** CareFlow offers the earliest available time by default.
- **Clear conflict message:** if someone else takes a time first, the patient is asked to choose another.
- **Automatic release:** a hold is released when a case is rejected or fails. A completed visit retains its time.
- **Audit trail:** reservations and releases are recorded.
- **Live availability:** the appointment list is refreshed from the doctor's current calendar when the patient opens it. Held times are shown as unavailable, and newly freed times can reappear.
- **Eight selectable options:** patients are shown eight times they can actually select.
- **Consulting hours:** the appointment card shows weekly hours. An internal “Urgent same-day slot” label was removed from the patient view.
- **Refresh fix:** the “My visits” Refresh button now refreshes the entire page, including an open visit.

**Verification:** 10 automated tests cover slot reservation and one covers the consulting-hours display. A test with four simultaneous patients confirmed that only one could reserve the same time.

**Important boundary:** this prevents duplicate holds inside CareFlow. CareFlow still sends a request to hospital scheduling staff; it does not itself complete the booking in OpenEMR.

### 3.2 Doctor administration — 16 October 2026

**Problem:** setting up a doctor previously required around 15 manual steps across OpenEMR, its calendar and Keycloak. Small inconsistencies could stop the doctor from receiving patients or signing in.

**What changed:** a new **Doctors** page is available in the admin sidebar.

| Admin action | What it does |
|---|---|
| View doctors | Shows doctors for the admin's hospital, including department, specialty, NPI, consulting hours, how far ahead hours are published, and login status. Less than two weeks of published hours is highlighted. |
| Add doctor | Uses one form for personal details, login, NPI, department, specialty and weekly hours. An initial Review step validates the information before creation. |
| Extend hours | Copies the doctor's last published week forward by 4, 8, 12 or 26 weeks. |
| Remove doctor | Permanently deletes a doctor with no patient history. If patient history exists, the doctor is deactivated instead so records remain intact. |
| Reactivate doctor | Re-enables a deactivated doctor, including their login and hours. |

**Safeguards added:**

- Admins can manage only the hospital associated with their login. If the login has no hospital assigned, access is blocked.
- Before saving, the system checks for duplicate usernames, NPIs and email addresses; invalid NPIs; weak passwords; overlapping hours; and specialties that do not match the selected department.
- If login creation fails, earlier OpenEMR changes are rolled back to avoid leaving a partially created doctor.
- Removal is blocked while the doctor has open cases.
- The admin is warned before removing the last doctor in a department.
- Add, extend, delete, deactivate and reactivate actions are audited with the actor and time. Passwords are not stored in the audit log.

**Issue found and addressed:** OpenEMR's API still accepts a deactivated doctor's password. CareFlow's own sign-off check now rejects inactive doctors as an additional safeguard.

**Verification:** a doctor created through the form was able to log in, pass the OpenEMR password check used by review/approval, appear under the correct department and have bookable times.

**Automated tests:** 14 doctor-management tests pass. They cover validation, access control, creation, duplicates, rollback, extension, deletion, deactivation, reactivation and blocking removal when open cases exist.

## 4. Proposed next feature — manager decision required

### Assign the doctor who can see the patient soonest

**Current behaviour:** CareFlow selects the first doctor listed in a department. That can repeatedly direct patients to an older-listed doctor even when another doctor has earlier availability.

**Why this matters:**
- Newly added doctors may receive few or no patients.
- Patients may be offered later times with one doctor while another doctor has an earlier free time.

**Recommended rule:**
1. Consider all active doctors in the relevant department.
2. Assign the patient to the doctor with the earliest free appointment time.
3. If doctors have the same earliest time, choose the one with fewer open cases.
4. Keep the existing appointment-selection and double-booking protections. Record the assignment reason for traceability.

**Other options:** assign doctors in turn (round robin), or let patients choose their doctor.

**Estimate:** about half a day after the rule is approved.  
**Status:** not started; awaiting approval. Planned branch: `feature/doctor-assignment-earliest-available`.

**Decision requested:** approve the recommended “earliest available” rule, or choose one of the alternatives.

## 5. Open actions

| Priority | Action | Owner | Target / note |
|---|---|---|---|
| High | Decide the doctor-assignment rule | Prisha / manager | Before starting the next feature |
| High | Commit the 14 and 16 October changes | Prisha | Next work session; part of 14 October work is already committed |
| Medium | Re-add Dr. Arjun Mehta (orthopedics), if still required | Prisha | Next work session; he was deleted during testing because he had no patient history |
| Medium | Extend the original six doctors' hours beyond 5 January 2027 | Prisha | Before December 2026 |
| Medium | Restrict hospital-settings pages to the admin's own hospital | Prisha | Follow-up; currently any admin can edit any hospital's settings |
| Low | Correct the database port in `docs/MANUAL_E2E_TESTING.md` | Prisha | Next work session; document says 5432, actual port is 5435 |
| Low | Investigate two older failing tests | Prisha | Follow-up |

### Test failures to keep separate from the new work

- `test_personal_record_never_calls_external_search` fails consistently and also fails without these changes.
- `test_chat_completion_fires_prescreen` is intermittent: it sometimes fails and passes when re-run.

These are not currently identified as blockers for the new scheduling and doctor-management work, but should be investigated separately.

## 6. Risks and boundaries

- **Git state:** the latest changes are not all committed yet.
- **Hospital booking boundary:** CareFlow holds times internally and sends requests to hospital scheduling staff; it does not directly make the final OpenEMR appointment booking.
- **Hospital-settings access:** the existing settings pages still need hospital-level access restrictions.
- **OpenEMR integration maintenance:** the doctor-provisioning code writes directly to the OpenEMR database and must be rechecked after an OpenEMR upgrade.
- **Doctor hours:** the original six doctors' published hours currently need extending beyond 5 January 2027.

No blocking issue was reported in the progress notes, but the items above still need follow-up.

## 7. Possible later improvements

These are ideas for later, not part of the completed work:

- Edit a doctor's details or change weekly hours, rather than only extending them.
- Support doctor leave and holidays.
- Support doctors who work at more than one hospital.

## Appendix A — Technical reference

This section is for developers; the earlier sections are intended for project and management review.

### Appointment holds and availability
- Database table: `slot_holds`; unique per doctor and start time, with one hold per case.
- Migration: `4b8d2e6f1a57_slot_holds.py`.
- Service: `backend/app/services/slot_hold_service.py`.
- Integrated with `workflows/prescreen.py`, `services/appointment_service.py`, `services/lifecycle.py`, and `GET /hms/slots`.
- Live options: `slot_hold_service.live_options` / `mark_taken`, `taken` flag on `SlotResponse`, and patient serializer in `api/v1/serializers.py`.
- Frontend slot picker: `features/intake/appointment-slot-picker.tsx`.
- Consulting hours: `domain/scheduling.weekly_hours`, `HMSClient.office_hours`, and `frontend/src/features/scheduling/doctor-hours.tsx`.

### Doctor administration
- API: `api/v1/admin_doctors.py` (admin-only, CSRF protected).
- Service: `services/doctor_onboarding_service.py`.
- Rules: `domain/provider.py`.
- OpenEMR provisioning: `integrations/hms/openemr/provisioning.py`.
- Keycloak admin client: `integrations/keycloak/admin_client.py`.
- Inactive-doctor checks: `HMSClient.list_practitioners` and `HMSClient.verify_credentials`.
- Audit table and migration: `admin_audit_events`, `6c1f3a9e2b48`.
- Frontend: `app/admin/doctors/page.tsx`, `features/admin/doctors/doctors-console.tsx`, and `features/admin/doctors/add-doctor-dialog.tsx`.
- Plan: `docs/PLAN_ADMIN_DOCTOR_ONBOARDING.md`.
- Configuration references: `hospital.hms_facility_id`, `clinic_id` on admin logins, `OPENEMR_MYSQL_*` in `backend/.env`, and `bcrypt==4.3.0`.

### Relevant tests and documentation
- Tests: `backend/tests/test_slot_holds.py`, `backend/tests/test_scheduling.py`, `backend/tests/test_doctor_onboarding.py`.
- Operator guide: `docs/OPERATOR_GUIDE.md`.
- Manual end-to-end testing guide: `docs/MANUAL_E2E_TESTING.md`.
