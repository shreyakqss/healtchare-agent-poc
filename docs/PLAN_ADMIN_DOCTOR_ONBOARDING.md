# Implementation plan: add doctors from the admin page

**Status:** built 2026-10-16 (Option A, approved), awaiting review · **Branch:** `feature/admin-doctor-onboarding` · **Prepared:** 2026-10-16
**Estimate:** about 5 working days for one developer (breakdown in section 6)

---

## 1. Goal

An administrator fills in **one form** in CareFlow and gets a doctor who can:
1. **receive patients.** They appear in the hospital system (OpenEMR) with the right specialty, so CareFlow routes matching complaints to them.
2. **be booked.** Their weekly consulting hours are published in the OpenEMR calendar, so patients see times.
3. **sign in.** They have a CareFlow login (Keycloak) with the doctor role, and their OpenEMR password works when they approve a case.

Today the same thing takes about 15 manual steps across three tools (see `docs/OPERATOR_GUIDE.md`, "Adding a doctor").

### Each admin manages only their own hospital
CareFlow will serve several hospitals, each with its own admins. There is **no default hospital**.
- An admin's login carries their hospital (the `clinic_id` attribute in Keycloak, which doctors already have).
  For example, a Santom Hospital admin is tagged `clinic_id = santom-hospital`.
- An admin can only list, add and extend hours for doctors **of their own hospital**. The hospital is taken
  from the admin's login and is **not** a field on the form, so it cannot be changed or forged.
- Each hospital's settings file (`data/hospitals/*.yaml`) gains a line naming its OpenEMR facility
  (`hms_facility_id`). New doctors are attached to that facility, and the doctors list only shows that facility's doctors.
- The new doctor's login gets the same `clinic_id` as the admin who created them, so they only see their own hospital's cases.
- An admin with no hospital on their login gets a clear "your account is not linked to a hospital" message, and can't add doctors.
- Example: a Santom Hospital admin creates Santom doctors only, and never sees another hospital's doctors.

---

## 2. What we found when we studied the project

### What's already in place

| Area | What exists |
|---|---|
| Admin access | Admin-only routes and a role check (`require_roles("admin")`) are already used by the hospital settings API. CSRF protection applies automatically to every form submission. |
| Keycloak | A service client, `careflow-admin`, already creates patient logins (`integrations/keycloak/admin_client.py`). Keycloak is already set to accept custom attributes such as `hms_username`. |
| OpenEMR database | Connection settings (`OPENEMR_MYSQL_*`) and the MySQL driver (PyMySQL) are already in the project, but nothing uses them yet. |
| Admin UI | The admin console has tabs, a form toolkit, dialogs and toasts we can reuse. The patient's weekly-hours display can be reused for the preview. |

### What's missing or must change

| Gap | Impact |
|---|---|
| **OpenEMR's API cannot finish the job.** It can create a practitioner (name, NPI, facility), but has no way to set a username, password, provider flags, access group, specialty role, or calendar hours. ([OpenEMR API routes](https://github.com/openemr/openemr/blob/master/apis/routes/_rest_routes_standard.inc.php), [PractitionerService](https://github.com/openemr/openemr/blob/master/src/Services/PractitionerService.php)) | The rest has to be written to OpenEMR's database (Option A, already recommended). |
| CareFlow's OpenEMR login has **read-only** scopes for practitioners and appointments. | Another reason to use the database for this one feature, rather than registering a new OpenEMR client with write access. |
| **The audit log only records actions on a patient case** (`case_id` is required). | We'll add an admin audit table, so "who added which doctor, when" is recorded. |
| The doctor role is called **`clinician`**, not "doctor". A doctor also needs the `clinic_id` and `hms_username` attributes. | The plan uses these exact names. |
| CareFlow reads **one calendar entry per day** and ignores repeating entries. | Hours are written as one entry per working day, for a fixed number of weeks. This is why the "Extend hours" button is needed. |
| Hospital settings don't say which OpenEMR facility a hospital is, and admin logins don't carry a hospital yet. | Add `hms_facility_id` to each hospital's settings and `clinic_id` to admin logins (see "Each admin manages only their own hospital"). |
| Today's hospital-settings admin pages let **any** admin edit **any** hospital's settings. | Not changed by this feature, but it's the same multi-hospital gap. We recommend a follow-up that applies the same per-hospital rule there. |
| Project rule: "never a calendar event" (CLAUDE.md). | That rule is about patient bookings. "In Office" blocks are the doctor's availability, not a booking. We'll record this as an explicit, documented exception. |

---

## 3. How it will work

```
Admin form ──► CareFlow API (admin only)
                 1. Check everything first (nothing written yet)
                 2. OpenEMR database, ONE transaction:
                      doctor record · login + password · access group
                      · specialty role · weekly "In Office" hours
                 3. Keycloak: create login, give "clinician" role,
                    set clinic_id + hms_username
                 4. If step 3 fails, undo step 2 (delete what we wrote)
                 5. Record in the admin audit log
```

**Why the order matters.** Step 2 is a single database transaction: it either fully succeeds or leaves nothing behind.
Keycloak cannot join that transaction, so it runs second and we undo step 2 if it fails. A half-created doctor
cannot happen.

**Checks before anything is written:**
- the admin's login is linked to a hospital, and that hospital has an OpenEMR facility configured;
- the username is free in both OpenEMR and Keycloak;
- the NPI is valid (10 digits, standard checksum) and not already in use;
- the specialty maps to a CareFlow department;
- no hours overlap on the same day, and each range sits within 06:00–22:00;
- the password meets the policy.

**One password, set in both systems.** It is never stored by CareFlow, never logged, and never returned by the API.

---

## 4. The work, step by step

### Phase 1: backend foundations (day 1)
1. **Admin audit table.** A new `admin_audit_events` table and migration, plus `audit.record_admin(...)`. Each entry records the hospital as well as the admin.
1b. **Per-hospital admin scope.**
   - Add `hms_facility_id` to the hospital settings schema and its validation.
   - Add a `require_clinic_admin` check: the admin role **and** a `clinic_id` on the login.
   - Give the existing test admin logins a `clinic_id` in the Keycloak realm import.
2. **OpenEMR database writer**, `integrations/hms/openemr/provisioning.py`. It is the only code that writes to OpenEMR's database.
   - `users`: name, username, NPI, specialty code, facility, and the provider/active/calendar flags.
   - `users_secure`: a bcrypt password hash and the password date, so OpenEMR does not force a reset.
   - The default user group, and the "Physicians" access group.
   - The facility role/specialty row, which OpenEMR uses to expose the doctor's specialty to CareFlow.
   - "In Office" calendar entries, one per working day per time range.
   - `delete_provider(username)`, used for rollback.
   - Before writing this, we'll create one doctor by hand in the OpenEMR screens and copy the exact rows it writes.
     That way we copy OpenEMR 8.3's own behaviour instead of guessing it.
3. **Keycloak.** Extend `admin_client` with a `create_clinician(...)` call (names, email, attributes, `clinician` role) and `delete_user(...)` for rollback.

### Phase 2: the onboarding service and API (day 2)
4. **`services/doctor_onboarding_service.py`**: the checks, the ordered steps, rollback and audit.
5. **Pure scheduling helper** in `domain/scheduling.py`: it turns "Mon–Fri, 10–13 and 16–19, for 8 weeks" into dated blocks, and checks for overlaps. It has no database and no network access, so it is easy to test.
6. **Admin API** in `api/v1/admin_doctors.py`:
   - `GET /admin/doctors`: the doctors list, with department and hours.
   - `POST /admin/doctors/preview`: validate the form and return the hours as patients will see them. Writes nothing.
   - `POST /admin/doctors`: create the doctor.
   - `POST /admin/doctors/{id}/extend-hours`: publish the same weekly hours for more weeks.

### Phase 3: admin screens (days 3–4)
7. A new **Doctors** tab in the admin console, with a table of doctors (name, department, NPI, hours, login status).
8. An **Add doctor** form in four sections:
   - Personal: title, first and last name, email, phone.
   - Login: username, password, confirm password.
   - Professional: NPI, specialty (a drop-down of the clinic's departments and their specialty codes), licence number.
   - Consulting hours: day checkboxes, up to 3 time ranges, start date, and number of weeks.
9. A **live preview** of the hours, using the same card patients see, and a clear summary of what will be created.
10. An **Extend hours** button on each doctor row.

### Phase 4: testing and documentation (day 5)
11. Automated tests (section 5).
12. Update `OPERATOR_GUIDE.md`: the manual steps become "use Admin → Doctors"; keep the manual route as a fallback.
13. Add the `OPENEMR_MYSQL_*` settings to `.env.example`, and document the CLAUDE.md exception.

---

## 5. How we will test it

| Test | Proves |
|---|---|
| Scheduling helper unit tests | Weeks, days and ranges expand correctly; overlaps are rejected. |
| Validation tests | Duplicate username or NPI, a bad NPI, and an unknown specialty are each refused, with nothing written. |
| **End-to-end against the local OpenEMR and Keycloak** | A new doctor: (a) is in CareFlow's doctor list under the right department, (b) has bookable times, (c) can log in, and (d) passes the OpenEMR password check that review/approve uses. |
| Forced failure in Keycloak | The OpenEMR rows are removed, and there's no partial doctor. |
| Hospital isolation | Two test hospitals, each with its own admin. Admin A can't see or extend hospital B's doctors (403/404). A's new doctor is tagged with A's hospital and facility only. An admin with no hospital is refused. |
| Access tests | Patient and clinician accounts get 403. Requests without CSRF are refused. The password never appears in logs, audit or responses. |
| Manual check | Add a doctor in the browser, register a test patient with a matching complaint, and confirm they're routed to the new doctor. |

All tests use test data only. Test doctors are removed afterwards.

---

## 6. Timeline

| Day | Deliverable |
|---|---|
| 1 | Admin audit, OpenEMR database writer (built from a hand-made reference doctor), Keycloak calls |
| 2 | Onboarding service, scheduling helper, admin API, backend tests |
| 3 | Doctors tab and list, Add doctor form |
| 4 | Hours preview, Extend hours, error messages, polish |
| 5 | End-to-end tests, documentation, demo to the reviewer |

---

## 7. Risks and how we handle them

| Risk | Mitigation |
|---|---|
| OpenEMR's internal tables change in a future upgrade | All direct writes live in one file. End-to-end tests will catch breakage. Moving to an OpenEMR add-on (Option C) remains possible later. |
| Exact access-group rows are hard to get right | We copy them from a doctor created through OpenEMR's own screens, then confirm the new doctor can log in. |
| Doctor's hours run out | The form publishes hours for a chosen number of weeks (default 12), and "Extend hours" adds more. |
| A password could leak | It is sent only over the existing secure session, never stored or logged, and covered by an automated test. |

## 8. Out of scope (possible follow-ups)
- Editing or deactivating a doctor.
- Leave and holidays.
- Doctors at more than one facility.
- Repeating calendar entries.

## 9. Decisions needed before starting
1. **Approve Option A**: writing to OpenEMR's database for the parts its API can't handle.
2. **Approve the CLAUDE.md exception**: CareFlow may write the doctor's "In Office" availability blocks, while patient appointments stay requests only.
3. **Confirm the defaults**: 30-minute slots and 12 weeks of hours published. ~~Default facility~~: replaced by per-hospital admins (section 1); each admin adds doctors only to their own hospital.
4. **Follow-up (optional):** apply the same per-hospital rule to the existing hospital-settings admin pages.
