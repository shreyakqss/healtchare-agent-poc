# CareFlow — Progress Report

**Overall status:** Instant booking, emergency handling, the doctor worklist with past patients and the admin patient directory are implemented.

## 1. Executive summary

CareFlow helps patients describe their problem, routes them to an appropriate department and doctor, and lets a doctor review the case. The latest work focused on making appointment scheduling safer and making doctor setup easier for hospital administrators.

### What is done

- **Prevented double booking within CareFlow:** a doctor and appointment time can be held by only one patient at a time.
- **Improved appointment availability:** patients see up-to-date appointment options; unavailable times remain visible but are disabled.
- **Made consulting hours visible:** patients can see the doctor's weekly hours.
- **Added safeguards and audit records:** doctor setup is validated, hospital access is scoped to the admin's own hospital, and admin actions are recorded.
- **Added an operator guide:** includes how to run the app, roles and logins, doctor setup, and common troubleshooting.
- **Earliest-available doctor:** a patient is assigned to the department doctor who can see them soonest, and may pick any doctor in the department.
- **Instant booking:** when the patient confirms a time, it is booked straight onto the doctor's OpenEMR calendar. The doctor no longer approves bookings.
- **Emergency handling:** red-flag symptoms stop the chat and show a full-screen "Call an ambulance (108 / 112)" message. No appointment is offered, and a note is written to the patient's chart.
- **Doctor workspace:** Today, Needs action, Upcoming, Past patients and Calendar tabs. Past patients is searchable and shows only that doctor's patients.
- **Admin → Patients:** a clinic-wide patient directory with administrative details only.
- **Doctor AI assistant:** now sees the patient's age, gender, history and own words, while their identity stays hidden.
- **Fixes:**
  - past appointment times are no longer offered;
  - every doctor's consulting hours are shown to the patient;
  - "More times" works when changing a booking;
  - older bookings appear on the doctor's calendar;
  - the login link no longer errors;
  - new-patient credentials can be copied.

### TODO
- Decide whether to keep the emergency chart note in OpenEMR. Nobody is contacted in an emergency; the note only records what happened.


## 2. Status at a glance

| Workstream | Status | Plain-English result |
|---|---|---|
| Appointment holds / double-booking prevention | Implemented and tested | Two patients cannot successfully hold the same doctor's time through CareFlow. |
| Live appointment options | Implemented | The list refreshes from the doctor's current calendar when opened. Taken times are greyed out; released times can become available again. |
| Doctor consulting hours | Implemented | Patients can see weekly consulting hours on the appointment card. |
| Doctor administration | Implemented and tested against OpenEMR and Keycloak | Admins can manage doctors from one page, with validation and access controls. |
| Doctor-assignment rule | Implemented | The doctor with the earliest free time is assigned, and the patient may choose another doctor in the department. |
| Instant booking | Implemented and tested against OpenEMR | A confirmed time goes straight onto the doctor's OpenEMR calendar. Changing it moves the booking, and rejecting the case frees it. |
| Emergency (red-flag) handling | Implemented | The patient is told to call an ambulance and no booking is offered. A chart note is written; no doctor or staff member is contacted. |
| Doctor workspace and past patients | Implemented | List-first tabs; the calendar is still available as one of them. |
| Admin → Patients directory | Implemented | Administrative details only; it never opens a case. |
| Doctor AI assistant context | Implemented | Fuller clinical context, with no patient identity. |
| Git commits | Pending | Work up to the instant-booking and emergency commit (`7113c7e`) is committed; later work is not. |
| Existing test failures | Follow-up | Two prescreen tests are timing-flaky (they pass when run alone), and one external-search test fails. The new emergency test hits the same timing issue. |

## 3. Completed work

### 3.1 Appointment scheduling 

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

### 3.2 Doctor administration 

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

### 3.3 Earliest-available doctor and choosing a doctor

**Problem:** CareFlow always picked the first doctor listed in a department, so newer doctors got few patients.

**What changed:**
- The patient is assigned to the department doctor with the **earliest free time**. When two doctors are free at the same time, the one with fewer open cases is chosen.
- On the booking screen, the patient sees **every doctor in the department**, each with their next free time, open times and **consulting hours**. Picking another doctor's time moves the case to that doctor.
- For urgent cases there is no doctor choice: the patient sees a simple list of the earliest times.
- After the doctor has reviewed the case, only that doctor's times are offered.

### 3.4 Instant booking (no doctor approval)

**Problem:** confirming a time only sent a request to staff, and the doctor had to approve it. Most health apps book instantly.

**What changed:**
- **Booked on confirm:** when the patient confirms, the appointment is written to the doctor's OpenEMR calendar as an "Office Visit". The patient sees "Your appointment is booked".
- **Changing and rejecting:** changing the time moves the booking. Rejecting the case frees the time.
- **What the review does now:** the doctor's review prepares the visit and unlocks consultation notes and finalize. It no longer holds up the booking. "Approve" wording was renamed to "Reviewed".
- **Past times:** past times are never offered. A booking whose time has passed is fixed: it shows "Your appointment time has passed" and can't be changed.

**Verification:** a live test against OpenEMR books, moves and cancels an appointment. The 32 slot, scheduling and routing tests pass.

### 3.5 Emergency handling

**Problem:** a patient describing severe chest pain was shown ordinary appointment options.

**What changed:**
- **Red-flag rules:** two rules in the clinic settings (`TR-EMERG-001`, `TR-EMERG-002`) catch two groups of symptoms:
  - severe chest pain or breathlessness;
  - fainting, severe bleeding, seizure, stroke signs, or suicidal thoughts.
- **In the chat:** intake stops on that message and shows **"This may be a medical emergency. Call an ambulance now on 108 (or 112)."**
- **On the results page:** a red **EMERGENCY** screen with a call button. No booking is ever offered, and the server refuses one.
- **No one is contacted:** CareFlow does not notify any doctor or staff member (decided 28 October). A plain-text "EMERGENCY" note is written to the patient's OpenEMR chart for the record, labelled "not reviewed by a clinician". The case appears in a passive list on the doctor's worklist.
- **Emergency department removed:** there is no emergency department in CareFlow.

### 3.6 Doctor workspace: list first, with Past patients

**Problem:** doctors had to open the calendar to find any patient.

**What changed:**
- The workspace opens on tabs: **Today**, **Needs action** (emergencies, waiting for review, not yet booked), **Upcoming**, **Past patients** and **Calendar**.
- **Past patients:**
  - one row per patient, with last visit date, number of visits and last complaint;
  - search by name, MRN, complaint or doctor, and filter by date range;
  - click a patient to see all their visits.
- **Only the doctor's own patients** are shown in Past patients. The server enforces this, so another doctor's patients are never sent.
- **Calendar fix:** the calendar and worklist now load all clinic cases (up to 1,000). Older bookings, such as Amit Verma's, were missing because only the 50 newest cases were loaded.

### 3.7 Admin → Patients directory

**What changed:**
- A new **Patients** page in the admin sidebar, covering the admin's own clinic only.
- **One row per patient:** name, age, sex, MRN, department, doctor, appointment, number of visits and status. Search by name, MRN or doctor, and filter by department.
- **Administrative only:** no complaint, symptoms, history, priority, notes or AI text, and rows never open the case. This keeps the rule that admins have no clinical access, and a test checks it.

### 3.8 Doctor AI assistant: better context

**What changed:** the assistant now receives the patient's age and gender, an emergency flag, the complaint, symptoms, duration and history, allergies and medications, priority and routing, the booked time, record mismatches, the pre-screening brief, the review, all consultation notes, and the intake chat in the patient's own words. Identity is protected: the identity form is never sent, and the patient's name is masked as "[patient]".

### 3.9 Smaller fixes

- **Sign-in link:** the "Returning patient" link no longer errors in the browser.
- **Copy buttons:** new-patient username and password can be copied with one click.
- **Age shown:** the patient's most recent age or name statement is now the one displayed.
- **"More times" when changing a booking:** it now expands the doctor's times instead of closing the picker.
- **Keycloak:** a reminder that it must be started separately after Docker restarts (`docker compose --profile auth up -d keycloak`).
- **`.creds`:** rewritten and verified. It covers all 13 doctors and all patient logins, with completed appointments listed separately.

## 4. Decided since the last report

### Assign the doctor who can see the patient soonest (approved and implemented; see 3.3)

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

**Status:** done. The recommended "earliest available" rule was approved, and the patient can also choose their doctor. It was built on `feature/admin-doctor-onboarding`.

### Other decisions made

- **Booking:** instant, with no clinician approval (see 3.4).
- **Emergencies:** show the call-ambulance screen only, with no doctor or staff contact and no emergency department (see 3.5).
- **Past patients:** a doctor sees only their own past patients. The whole clinic's patients are visible only to the admin, as a directory without clinical detail (see 3.6 and 3.7).



## 7. Possible later improvements

These are ideas for later, not part of the completed work:

- Load the doctor calendar by date range (needed once a clinic passes about 1,000 cases).
- Remind doctors about today's booked patients who haven't been reviewed yet.
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

### Since 16 October
- **Instant booking:**
  - `services/appointment_service.py` (`select_slot`, `passed_booking`, `release_booking`);
  - `HMSClient.book_appointment` / `cancel_appointment`;
  - `integrations/hms/openemr/provisioning.book_appointment`;
  - `PatientCase.hms_appointment_id` (migration `9a1c5e3f7b20`).
- **Emergencies:**
  - `domain/triage_engine.py` (`emergency` rules, `any_severity`);
  - `services/emergency_service.py`;
  - `PatientCase.emergency_flagged_at` (migration `8e4b1d7c3a90`);
  - `hospital_config.ambulance_number()` / `emergency_number()`;
  - `features/intake/patient-results.tsx` (`EmergencyNotice`).
- **Past times:** `slot_hold_service.has_passed` / `upcoming`, and `slot_passed` on the patient routing response.
- **Doctor hours per card:** `hours_by_doctor` on the patient routing response.
- **Doctor workspace:**
  - `features/doctor/doctor-workspace.tsx` and `features/doctor/past-patients.tsx`;
  - `GET /cases/past-patients` and `services/past_patients.py`;
  - `appointment_booked` on the case list;
  - `GET /cases` now allows `limit` up to 1000 (`WORKSPACE_CASES`).
- **Admin directory:**
  - `GET /admin/patients` (`api/v1/admin_patients.py`) and `services/patient_directory.py`;
  - `app/admin/patients/page.tsx` and `features/admin/patients/patients-directory.tsx`.
- **AI assistant context:** `services/doctor_assistant_service._case_context` / `_intake_transcript`.
- **New tests:** `test_instant_booking.py` (live OpenEMR), `test_emergency.py`, `test_past_patients.py` and `test_patient_directory.py`.

### Relevant tests and documentation
- Tests: `backend/tests/test_slot_holds.py`, `backend/tests/test_scheduling.py`, `backend/tests/test_doctor_onboarding.py`.
- Operator guide: `docs/OPERATOR_GUIDE.md`.
- Manual end-to-end testing guide: `docs/MANUAL_E2E_TESTING.md`.
