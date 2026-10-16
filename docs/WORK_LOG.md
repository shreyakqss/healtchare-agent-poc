# CareFlow progress report

**Project:** CareFlow, AI-assisted patient intake and doctor routing (proof of concept)
**Prepared by:** Prisha Gupta · **Period covered:** up to 2026-10-16

---

## Summary

| | |
|---|---|
| **Completed** | Patients can no longer be double-booked with a doctor. Appointment times are live and show taken times greyed out. Patients see each doctor's consulting hours. The "My visits" refresh is fixed. Setup documentation is written. |
| **Proposed next** | Admins add new doctors through a single form, which creates everything the doctor needs in the hospital system and the login system. |
| **Decision needed** | How CareFlow writes the doctor details that OpenEMR's API cannot accept (section 3, "Decision needed"). Recommended: **Option A**. |
| **Risks / issues** | None blocking. Doctor office hours run out on 2027-01-05 and must be extended (the next feature adds a button for this). |

### Glossary
- **CareFlow**: our app. Patients describe their problem to an AI assistant, CareFlow decides urgency and
  the right department and doctor, and a doctor reviews the case.
- **OpenEMR**: the hospital system (open-source medical records). It holds the patients, the doctors and their calendars.
- **Keycloak**: the login system. It controls who can sign in and whether they are a patient, a doctor or an admin.
- **Slot**: a 30-minute appointment time with a doctor.

---

## 1. Completed: 

### 1.1 No double booking
**The problem.** By design, CareFlow does not book appointments in OpenEMR. It sends the hospital's
scheduling staff a *request*. As a result, CareFlow had no record of which times its own patients had already
taken. Two patients could get the same doctor at the same time, and every new patient was offered the same first time.

**What we built.** CareFlow now **reserves** ("holds") a time for each patient:
- A doctor's time can be held by **only one patient**. The database enforces this, so it holds even when two
  patients click at the same moment (tested with four simultaneous patients: exactly one succeeds).
- A new patient automatically gets the **earliest free** time.
- If a patient picks a time someone has just taken, they see: *"That time was just taken by another patient. Please pick another."*
- When a case is **rejected or fails**, its time is released for others. A **completed** visit keeps its time.
- Every reservation and release is recorded in the audit log.

**Result.** Verified with test patients: three patients routed to the same cardiologist each received a different time.

### 1.2 Live appointment times, with taken times greyed out
**The problem.** A patient's list of times was fixed when their case was created. Times freed later never
reappeared, and times taken later were still shown.

**What we built.** The time list is rebuilt from the doctor's live calendar every time the patient opens it.
- Times held by other patients stay visible but are **greyed out**, so patients understand the doctor is busy then.
- A freed time reappears immediately.
- Patients always have 8 times they can actually choose.

### 1.3 Doctor's consulting hours shown to patients
The appointment card now shows the doctor's weekly hours (for example *Mon – Fri, 10 AM – 1 PM and 4 PM – 7 PM*),
read from the hospital calendar. The internal label "Urgent same-day slot" was removed from the patient's view.

### 1.4 "My visits" refresh fixed
The **Refresh** button did not update an open visit, so patients saw stale times and statuses. It now refreshes
everything on the page and confirms with a message.

### 1.5 Documentation
`docs/OPERATOR_GUIDE.md` explains how to run the app, which service is on which port, how logins and roles
work, how doctors and their hours are set up, and how to fix common problems.

### Quality
- **10 new automated tests** for slot reservation, plus 1 for the consulting-hours display. All pass.
- Two older tests also fail on and off without this work. They are not caused by it and are tracked separately.

---

## 2. Open items

| Item | Owner | When |
|---|---|---|
| Commit the 2026-10-14 work (part is already committed on `feature/slot-hold-no-double-booking`) | Prisha | Next session |
| Extend doctor office hours past 2027-01-05 | Prisha | Before Dec 2026 (or via the next feature's button) |
| Correct the database port in `docs/MANUAL_E2E_TESTING.md` (says 5432, is 5435) | Prisha | Next session |

---

## 3. Proposed next feature: add doctors from the admin page

**Status:** awaiting approval · **Branch:** `feature/admin-doctor-onboarding`

### Why
Adding a doctor today takes **three separate manual jobs in three different tools**: the hospital system, its
calendar and the login system. Small mistakes are easy to make and hard to spot, for example a missing licence
number, a wrong specialty code, a capital letter in the username, or a repeating calendar entry. Each one silently
stops the doctor from receiving patients or from logging in. We hit several of these while setting up the six
demo doctors.

### What the admin will be able to do
The CareFlow administrator, **and only the administrator**, opens **Admin → Doctors → Add doctor**, fills in
one form and presses Save. CareFlow then creates, automatically:
1. **The doctor in the hospital system**, with their professional details, so CareFlow can route patients to them.
2. **Their weekly consulting hours** in the hospital calendar, which become the appointment times patients pick from.
3. **Their login**, so they can sign in to CareFlow as a doctor straight away.

### What the form collects

| Section | Details |
|---|---|
| Personal | Title, first name, last name, email, phone |
| Login | Username and password (one password for both systems) |
| Professional | NPI (US national provider ID), department, specialty, licence number (optional) |
| Consulting hours | Working days, up to 3 time ranges per day, start date, number of weeks to publish |

Before saving, the admin sees a **preview** of the hours exactly as patients will see them.

### Safeguards
- **Everything is checked first** (duplicate usernames or licence numbers, invalid NPI, overlapping hours,
  missing names). If anything is wrong, nothing is created.
- **No half-created doctors.** If one step fails, the steps already done are undone, and the admin is told which step failed.
- **Audited.** Each new doctor is recorded with who added them and when. Passwords are never stored in logs.
- **Access.** Only the admin role can use it. The admin still cannot view patient records.

### Also included
- **Doctors list** on the admin page, showing all doctors from the hospital system with their department and hours.
  Today the admin page doesn't show them.
- **"Extend hours" button** to publish a doctor's same weekly hours for more weeks, so they never run out.

### Not included (possible follow-ups)
- Editing or deactivating an existing doctor.
- Leave and holidays.
- Doctors working at more than one hospital.

### Decision needed
OpenEMR's official interface can create the doctor, but it **cannot** set their login password or specialty,
and **cannot** add consulting hours. Three ways forward:

| Option | How | Pros | Cons |
|---|---|---|---|
| **A (recommended)** | Use OpenEMR's interface where possible, and write the remaining details directly into OpenEMR's database, in one contained part of our code | Fully automatic. Fastest to deliver. | Depends on this OpenEMR version's internal structure, so an OpenEMR upgrade would need a re-check. |
| **B** | Use OpenEMR's interface only | Simplest and safest technically | **Not fully automatic.** The admin must still set the password and hours by hand in OpenEMR. |
| **C** | Build a small add-on inside OpenEMR that exposes the missing functions | Cleanest long-term | Most effort, and adds an OpenEMR add-on to maintain |

**Recommendation: Option A for the proof of concept.** The direct-write code is isolated, so it can move to
Option C if CareFlow goes beyond the POC.

### How we will verify it
- Adding a doctor through the form results in a doctor who can log in, has bookable times, and receives a
  patient with a matching complaint.
- Invalid or duplicate details are rejected, with nothing created.
- A simulated failure halfway through leaves no partial doctor behind.
- Non-admin users are blocked, and passwords never appear in logs.

---

## Appendix: technical reference (for developers)

**Slot reservation:** new table `slot_holds` (unique per doctor and start time, one per case), service
`backend/app/services/slot_hold_service.py`, migration `4b8d2e6f1a57_slot_holds.py`. Wired into routing
(`workflows/prescreen.py`), slot selection (`services/appointment_service.py`, row lock plus a 409 on conflict),
case lifecycle (`services/lifecycle.py`, release on reject or fail), and `GET /hms/slots`.

**Live list and greyed-out times:** `slot_hold_service.live_options` / `mark_taken`, a `taken` flag on
`SlotResponse`, and the patient serializer in `api/v1/serializers.py`. Frontend:
`features/intake/appointment-slot-picker.tsx`.

**Consulting hours:** `domain/scheduling.weekly_hours`, `HMSClient.office_hours` (OpenEMR "In Office"
calendar blocks, next 14 days), and a `doctor_hours` field on the patient routing response.

**Refresh fix:** `frontend/src/features/intake/visits-panel.tsx`.

**Tests:** `backend/tests/test_slot_holds.py` (10), `backend/tests/test_scheduling.py`.

**Next feature (planned):** `services/doctor_onboarding_service.py`, OpenEMR writes kept in
`integrations/hms/openemr/`, Keycloak through the existing `careflow-admin` service client, and admin-only
API routes with CSRF.
