# Manual end-to-end testing

How to log in as each role and walk the full flow by hand. Local dev only.

## Services and ports

| Service | URL | Notes |
|---|---|---|
| Frontend (Next.js) | http://localhost:3000 | what you open in the browser |
| Backend (FastAPI) | http://localhost:8000 | `/docs` for the OpenAPI UI |
| Keycloak (identity) | http://localhost:8500 | admin console at `/admin/master/console/` |
| OpenEMR (HMS) | http://localhost:8300 | the hospital system CareFlow talks to |
| Postgres | localhost:5432 | CareFlow's own `healthcare_agent` database |

Start everything: `docker compose --profile auth up -d db openemr keycloak`,
then backend (`uvicorn app.main:app --reload` from `backend/`) and frontend
(`npm run dev` from `frontend/`). See the root [README](../README.md) for the
full one-time setup.

Keycloak admin login: `admin` / value of `KEYCLOAK_ADMIN_PASSWORD` in your
root `.env` (default in `.env.example` is `CareflowKcAdmin@2026`).

OpenEMR admin login: `admin` / value of `OPENEMR_ADMIN_PASSWORD` in your root
`.env` (default in `.env.example` is `Careflow@2026`) - this is only the
bootstrap login for a fresh install; `backend/.env`'s `OPENEMR_USERNAME` /
`OPENEMR_PASSWORD` is a separate, ordinary OpenEMR user the backend
authenticates as.

## How login works

There is no username/password form inside CareFlow itself. `http://localhost:3000`
is a role picker: each card ("Patient sign in", "Clinician sign in",
"Administrator sign in") redirects to Keycloak's login page, and Keycloak
redirects back once you authenticate. This page is required, not optional -
a single Keycloak realm serves three different roles, so the app needs
somewhere to send you before it knows which login to start (each card carries
a different `return_to`). Once signed in, only the cards matching your actual
Keycloak roles are shown, your username appears bottom-right, and the header
turns into "Sign out" - so you never see the role picker again until you sign
out. The signed-in workspace header (top bar) shows your username, not a role
label; the role is implicit in which workspace you're on ("Patient intake",
"Doctor workspace", "Admin").

## One-time setup: creating test users in Keycloak

The `careflow` realm ships with zero users. Create one per role you want to
test, at http://localhost:8500/admin/master/console/#/careflow/users
(sign in to Keycloak admin first).

**Patient** - Users -> Create user -> any username/email/name -> Credentials tab
-> Set password (turn **Temporary** off) -> Role mapping tab -> Assign role ->
Realm roles -> `patient`.

**Clinician** - same, but:
- Role mapping -> assign `clinician`.
- The clinician needs two extra attributes, set on the Details tab (or via
  the admin REST API): `clinic_id` = `qss-demo-clinic`, and `hms_username` =
  the username of a real OpenEMR practitioner (see roster below). Without
  both, `/doctor` shows "Hospital identity is not linked" or a clinic error.
- **Sign out and back in after setting attributes** - Keycloak only puts
  `clinic_id`/`hms_username` in the token at login time, so an existing
  session won't pick up a later attribute change.

**Admin** - same, but Role mapping -> assign `admin`. No `clinic_id`/
`hms_username` needed; admins manage clinic config only, no clinical case
access.

If a fresh clinician gets "Please specify this field" on first login (a
Keycloak "verify profile" step), just fill in email/first/last name again -
that's Keycloak's own required-profile check, unrelated to CareFlow.

## The clinic's practitioner roster (for `hms_username` / HMS password)

These are real OpenEMR users already seeded in the demo instance. Use one of
these as a clinician's `hms_username`; the password below is what you type
into CareFlow's "Your HMS password" field during review/consultation/finalize
(CareFlow verifies it against OpenEMR directly, every time - it is never
stored).

| `hms_username` | Name | Department | OpenEMR password |
|---|---|---|---|
| `dr_mehta` | Meera Nair | General Medicine | `Careflow@2026` |
| `dr_khan` | Arjun Kapoor | Cardiology | ask whoever set it up |
| `dr_sharma` | Rhea Sharma | Pulmonology | ask whoever set it up |
| `dr_desai` | Vikram Desai | Orthopedics | ask whoever set it up |
| `dr_siddiqui` | Ayesha Siddiqui | Dermatology | ask whoever set it up |
| `dr_malhotra` | Karan Malhotra | ENT | ask whoever set it up |

Only `dr_mehta`'s password is confirmed working as of this doc. To check or
reset any of them: OpenEMR admin (`admin` / `OPENEMR_ADMIN_PASSWORD`) -> **Administration
-> Users** -> click the user -> enter *your own* (admin) password in "Your
Password" plus the new one in "User's New Password" -> Save.

## Walking the flow

**As a patient** (`/patient`): fill the identity form (name, DOB, gender,
address, contact preference) -> Continue. This registers the patient in
OpenEMR. Then chat with the intake assistant - it asks for reason for visit,
symptoms, duration, medical history, medications, allergies one at a time.
When the progress panel hits the total field count, the assistant hands off
to pre-screening automatically. "My visits" tab shows past visits and, once a
clinician releases it, the visit summary and follow-up instructions.

**As a clinician** (`/doctor`): the worklist has three buckets - *Awaiting
your review*, *Ready to consult*, *Completed*. Open a case awaiting review to
see the AI-drafted clinician briefing, the rule-based administrative
priority with evidence, any HMS discrepancies, and the proposed routing.
Pick Approve / Approve with edits / Reject, enter your HMS username +
password, and submit - this both unlocks the consultation step and records
who signed off. Once approved, the same panel becomes "Record the
consultation": your own findings/assessment/plan, optional prescription and
follow-up instructions, HMS password again, Save. Then "Release visit
summary" (HMS password once more) generates the patient-facing summary and
drafts the HMS follow-up task - after that the case moves to *Completed*.

**As an admin** (`/admin`): clinic configuration only (departments, routing
keywords, triage rules, roster/doctors YAML) - no patient or case data is
visible from this role, by design.

## Cleaning up test data afterward

Test patients/cases leave rows in three places - delete all three or they
accumulate:

1. **OpenEMR** (mariadb container, `docker exec <openemr-mariadb container> mysql -u openemr -popenemr openemr`):
   `delete from documents where foreign_id=<pid>; delete from forms where pid=<pid>; delete from form_encounter where pid=<pid>; delete from lists where pid=<pid>; delete from patient_data where pid=<pid>;`
2. **Postgres** (`healthcare_agent` db): `delete from patient_cases where id='<case-id>';` (cascades to
   reviews, notes, audit events, etc. automatically) and `delete from intake_sessions where id='<session-id>';`.
3. **Keycloak**: delete the test user(s) from Users in the `careflow` realm
   (or via `DELETE /admin/realms/careflow/users/<id>` on the admin API).

**Never delete the `Prashant Tomar` patient or their cases** - that record is
kept intentionally as standing test data.
