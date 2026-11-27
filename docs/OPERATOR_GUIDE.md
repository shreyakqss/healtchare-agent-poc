# CareFlow operator guide

How to run CareFlow locally, what lives on which port, and how doctors, patients and logins are set up.
Local development only, with synthetic test data. For the code itself, read [ARCHITECTURE.md](ARCHITECTURE.md).
For a step-by-step manual test, see [MANUAL_E2E_TESTING.md](MANUAL_E2E_TESTING.md).

> **Credentials are not in this file.** Real usernames and passwords live in `.creds` at the repo root.
> It is gitignored, so never commit it.

---

## 1. The pieces

| System | What it owns |
|---|---|
| **CareFlow frontend** (Next.js) | The website patients, doctors and the admin use. It is a same-origin proxy (BFF): the browser only ever talks to it, never to the backend or Keycloak tokens directly. |
| **CareFlow backend** (FastAPI) | Intake chat, triage rules, routing to a department and doctor, slot holds, clinician review, finalize. Its own Postgres database stores cases. |
| **OpenEMR** | The hospital system and **source of truth** for patients, doctors (practitioners), their office hours and chart documents. CareFlow reads it over FHIR and writes through its REST API. |
| **Keycloak** | **Logins only.** It decides who you are and your role (patient, clinician or admin). It knows nothing clinical. |
| **Langfuse** (optional) | Traces every AI agent run: prompts, tool calls, tokens and latency, grouped per case. |

In one line: Keycloak decides **who you are**, OpenEMR holds **the hospital's records**, and CareFlow
**runs the visit workflow** between them.

---

## 2. Ports and URLs

| Service | URL / port | Notes |
|---|---|---|
| CareFlow frontend | http://localhost:3000 | **Open this in the browser.** |
| CareFlow backend | http://localhost:8000 | API docs at http://localhost:8000/docs |
| CareFlow Postgres | `localhost:5435` | Database `healthcare_agent` (container port 5432) |
| OpenEMR | http://localhost:8300 | Use **http on 8300**. |
| OpenEMR (TLS) | https://localhost:8443 | **https only.** `http://…:8443` does not work. |
| OpenEMR MariaDB | `localhost:3307` | OpenEMR's own database |
| Keycloak | http://localhost:8500 | Admin console: http://localhost:8500/admin/ |
| Langfuse | http://localhost:2000 | Tracing UI (create API keys here) |
| Langfuse internals | 5436 (Postgres), 8123 / 9000 (ClickHouse), 9090 / 9091 (MinIO), 6380 (Redis) | Never opened directly |

Every port is bound to `127.0.0.1`, so nothing is reachable from other machines.

---

## 3. Starting and stopping

### Docker services (once per boot)

```bash
# from the repo root
docker compose up -d db openemr                       # CareFlow DB + OpenEMR (+ its MariaDB)
docker compose --profile auth up -d keycloak          # logins
docker compose --profile tracing up -d                # Langfuse (optional)
```

Stop: `docker compose --profile auth --profile tracing stop`. Data survives in Docker volumes.
`docker compose down -v` **deletes all data**, including OpenEMR patients and the CareFlow DB.

### Backend

```bash
cd backend
source venv/bin/activate          # Windows: .\venv\Scripts\Activate.ps1
python scripts/seed.py            # first run, or after a model change: migrations + triage rules
uvicorn app.main:app --reload     # http://localhost:8000
```

Database migrations run automatically through `seed.py` (Alembic). `--reload` picks up code changes by itself.

### Frontend

```bash
cd frontend
npm install                       # first run only
npm run dev                       # http://localhost:3000
```

Never run `npm run build` while `npm run dev` is running.

### One-time setup on a fresh OpenEMR volume

```bash
cd backend && python scripts/openemr_register_client.py
```

Copy the printed client ID and secret into `backend/.env` (`OPENEMR_CLIENT_ID`, `OPENEMR_CLIENT_SECRET`), then
**enable the client** in OpenEMR under *Admin → System → API Clients*.

---

## 4. Logins and roles

**Use a separate browser or a private window per role.** CareFlow keeps one login per browser.
Logging in as a patient in the same browser as a doctor replaces the doctor's session, and the doctor's
page then fails with **403**.

| Who | Where to log in | Username source | What they can do |
|---|---|---|---|
| **Patient** | http://localhost:3000 → *Patient* | Self-registered (`patient-xxxxxxxx`) | Chat intake, upload documents, pick an appointment time, see their visits |
| **Clinician (doctor)** | http://localhost:3000 → *Clinician* | Lowercase first name (`ananya`, `rahul`, …) | Worklist and calendar for their clinic, review, consult notes, finalize |
| **CareFlow admin** | http://localhost:3000 → *Administrator* | `careflow-admin-user` | Edit clinic config (departments, triage rules); add doctors and extend their hours (**Doctors** page, own hospital only). **Cannot open patient cases.** |
| **OpenEMR admin** | http://localhost:8300 | `admin` | Manage doctors, office hours, patients and API clients in the hospital system |
| **Keycloak admin** | http://localhost:8500/admin/ | `admin` (realm `master`) | Manage CareFlow users in realm **`careflow`** |

All passwords are in `.creds`.

Keycloak notes:
- CareFlow users live in realm **`careflow`**, not `master`. In the console, switch realms from the top-left dropdown.
- Keycloak stores usernames **lowercase**. OpenEMR user `Rahul` logs into CareFlow as `rahul`.
- A clinician's Keycloak user carries two attributes: `clinic_id` (`qss-demo-clinic`) and `hms_username` (the
  **exact** OpenEMR username, case included). When signing off a review, the doctor re-enters their
  **OpenEMR** password. CareFlow checks it against OpenEMR, so it must match.

---

## 5. How doctors are set up

A doctor needs **three things**: an OpenEMR user, an OpenEMR calendar, and a Keycloak login.

### The normal way: Admin → Doctors

Log in as the CareFlow admin and open **Doctors** in the sidebar (http://localhost:3000/admin/doctors).
**Add doctor** collects the doctor's details, login, NPI, department/specialty and weekly consulting hours,
shows a review of what patients will see, then creates **all three things below in one step**. If any
step fails, nothing is kept. Each row's **Extend hours** publishes the last week of hours for more weeks.

**Remove** (bin icon on a row):
- A doctor who was **never used** (no visits, notes, appointments or CareFlow cases) is **permanently deleted**
  from OpenEMR and Keycloak.
- A doctor **with history** is **deactivated** instead. Their records keep their name. OpenEMR marks them
  inactive, CareFlow stops routing to them and refuses their sign-off, and their Keycloak login is disabled.
  Their hours are kept, so **Reactivate** restores them fully.
- Removal is **blocked while the doctor has open CareFlow cases**. Finish or reject those cases first.

Requirements:
- The admin's Keycloak user has a `clinic_id` attribute (e.g. `qss-demo-clinic`). An admin only sees and
  adds doctors for that hospital. **Log out and back in** after the attribute is set.
- That hospital's YAML has `hospital.hms_facility_id` (the OpenEMR `facility.id`; Santom Hospital is `3`).
- `backend/.env` has `OPENEMR_MYSQL_USER` / `OPENEMR_MYSQL_PASSWORD` (the `openemr` DB user from
  `docker-compose.yml`). CareFlow writes OpenEMR's database directly for the parts OpenEMR's API cannot do.
- Every addition is recorded in the `admin_audit_events` table. Passwords are never stored or logged.

The sections below are the **manual** route, kept as a fallback and as a reference for what the form creates.

### 5.1 OpenEMR user (the practitioner)

*Admin → Users → Add User* in OpenEMR (http://localhost:8300):

1. **Username / password**: the doctor's OpenEMR login (also used to sign off reviews).
2. **Provider** checked, and an **NPI** filled in. OpenEMR lists someone as a FHIR Practitioner **only if
   they have an NPI**, and without that CareFlow cannot see them.
3. **Facility**: *Santom Hospital*.
4. **Role / specialty** (*facility user* settings): a NUCC taxonomy code. **This is what puts the doctor in a
   department.** CareFlow matches it against `specialty_codes` in the clinic YAML:

| Department | Accepted NUCC codes | Current doctor |
|---|---|---|
| General Medicine (default) | 207R00000X, 208D00000X, 207Q00000X | Rahul Kumar |
| Cardiology | 207RC0000X | Ananya Sharma |
| Pulmonology | 207RP1001X | Vikram Rao |
| Orthopedics | 207X00000X | Arjun Mehta |
| Dermatology | 207N00000X | Priya Nair |
| ENT | 207Y00000X | Sanjay Iyer |

> If a doctor shows department **"unknown"**, their role code is missing from OpenEMR's
> `us-core-provider-role` list. Set the role to a listed code (e.g. `207R00000X`) and keep the subspecialty in
> the specialty field.

The admin page in CareFlow shows only YAML doctors, not live OpenEMR ones. **OpenEMR is where doctors are
managed.** CareFlow merges the live list in automatically at routing time.

### 5.2 Office hours (the doctor's calendar)

CareFlow builds appointment times **from the doctor's OpenEMR calendar**. In OpenEMR's *Calendar*, add
events for the doctor with:

- **Category: "In Office"** (category 2). Each event is a block of hours the doctor sits.
- **No patient** attached.
- One event per block per day, **non-repeating**. OpenEMR's API does not return repeat rules, so
  repeating events are invisible to CareFlow.

CareFlow cuts these blocks into **30-minute slots**, in the clinic timezone (`Asia/Kolkata`). The patient's time
picker shows the doctor's **Consulting hours** card, built from the next two weeks of these blocks.

Current hours (entered through 2027-01-05; extend them before then):

| Doctor | Days | Hours |
|---|---|---|
| Rahul Kumar | Mon – Fri | 11:00 – 14:00, 17:00 – 20:00 |
| Ananya Sharma | Mon – Fri | 10:00 – 13:00, 16:00 – 19:00 |
| Vikram Rao | Mon, Wed, Fri | 09:00 – 12:00 |
| Priya Nair | Mon, Wed, Fri | 09:00 – 12:00 |
| Arjun Mehta | Tue, Thu, Sat | 12:00 – 16:00 |
| Sanjay Iyer | Tue, Thu, Sat | 11:00 – 18:00 |

A doctor with no In Office blocks falls back to a generic 09:00 – 17:00 weekday window.
A **patient appointment** booked directly in OpenEMR's calendar for that doctor blocks that time in CareFlow too.

### 5.3 Keycloak login

In Keycloak, realm **`careflow`** → *Users → Add user*:

1. Username: the doctor's name in lowercase (e.g. `ananya`), and set a password under *Credentials*
   (temporary **off**).
2. *Attributes*: `clinic_id` = `qss-demo-clinic`, `hms_username` = the exact OpenEMR username.
3. *Role mapping*: realm role **`clinician`**.

---

## 6. How a patient moves through the system

```
Patient registers ─► consent ─► identity form ─► intake chat ─► documents (upload / skip)
        │                          │
        │                          └─ creates the patient in OpenEMR (one record per form)
        ▼
  Pre-screening (automatic)
     1. Triage:   fixed rules in the clinic YAML set priority (low / medium / high). No AI.
     2. Routing:  department ← rule's specialty hint, else routing keywords, else General Medicine
                  doctor     ← first live OpenEMR practitioner in that department
     3. Slots:    the doctor's free 30-min times; the earliest free one is HELD for this case
     4. Summary:  AI draft for the clinician
        ▼
  Status NEEDS_REVIEW ─► doctor reviews (approve / edit / reject) ─► consult notes ─► finalize
                                                                        │
                                           visit summary + appointment REQUEST (chart note in OpenEMR)
```

**Patient registration:** a patient clicks *Patient* at http://localhost:3000 and registers. Keycloak
creates a `patient-xxxxxxxx` account, with the password shown once. Enter **both a first and last name** on
the identity form: OpenEMR rejects a one-word name (`422 fname`).

**Which doctor sees the case:** every clinician sees **all cases in their clinic** (by `clinic_id`).
The routing step decides the department and doctor *suggestion*, and the appointment appears on that
doctor's CareFlow calendar.

### Appointment times and slot holds

CareFlow **never books** in OpenEMR's calendar. Finalize files an *appointment request* note on the chart
for scheduling staff. To keep two patients off the same doctor at the same time, CareFlow keeps its own
**slot holds** (table `slot_holds`):

- Each open case holds **one** time. The database refuses a second hold on the same doctor and time, even if
  two patients click at the same instant.
- At routing, the case holds the **earliest free** time as its default.
- In the patient's picker, times other patients hold are shown **greyed out**. The list is built fresh each
  time it opens, so a freed time comes back.
- Picking a held time returns *"That time was just taken by another patient."*
- A **rejected** or **failed** case releases its time. A **completed** case keeps it.

### Removing a test case

Delete its intake session from the CareFlow DB. The case, holds, facts and so on cascade. The patient's
OpenEMR record stays and has to be removed in OpenEMR separately.

---

## 7. Configuration

### `backend/.env`

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | CareFlow Postgres, port **5435** |
| `AUTH_SESSION_SECRET`, `AUTH_COOKIE_SECURE` | Browser session cookie (`false` for local http) |
| `KEYCLOAK_ADMIN_CLIENT_ID` / `_SECRET` | Client `careflow-admin`, used to create patient accounts on self-register |
| `OPENEMR_CLIENT_ID` / `_SECRET` | The OAuth client from `openemr_register_client.py` |
| `OPENEMR_USERNAME` / `_PASSWORD` | The OpenEMR user the backend acts as |
| `OPENAI_API_KEY` | Intake and summary agents |
| `LLM_MODEL` | Default `gpt-4.1-mini` |
| `LLM_SUPPORTS_EFFORT` | `true` only for reasoning models (gpt-5*, o-series); `false` for gpt-4.1* |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | Tracing (`LANGFUSE_HOST=http://localhost:2000`); unset = no tracing |

URL defaults (override only if you change ports): `OPENEMR_BASE_URL=http://localhost:8300`,
`OIDC_ISSUER_URL=http://localhost:8500/realms/careflow`, `KEYCLOAK_ADMIN_URL=http://localhost:8500`.

### `frontend/.env.local`

`BACKEND_URL` (server-side only, never exposed to the browser) and `IDENTITY_PROVIDER_ORIGIN` (Keycloak origin,
used for the logout redirect).

### Root `.env`

Bootstrap passwords for Docker: OpenEMR admin, Keycloak admin, and Langfuse.

### Clinic policy: `backend/data/hospitals/qss-demo-clinic.yaml`

The clinic (*Santom Hospital*, timezone `Asia/Kolkata`), **departments** with their `specialty_codes` and
routing keywords, **appointment types**, and **triage rules**. A fallback rule (empty condition) is mandatory.
Edit it in the CareFlow admin page or by hand, then run `python scripts/seed.py` to sync triage rules.
Saving from the admin page rewrites the file **without comments**.

### Langfuse API keys

http://localhost:2000 → create an organisation and project → *Settings → API Keys*. Put the keys in `backend/.env`.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| OpenEMR `invalid_client` | Fresh OpenEMR volume, or the client is disabled | Re-run `openemr_register_client.py`, update `.env`, enable the client |
| OpenEMR `invalid_grant` | `OPENEMR_USERNAME` / `PASSWORD` empty or wrong | Set them in `backend/.env` |
| `http://127.0.0.1:8443` fails | 8443 is TLS | Use https://localhost:8443 or http://localhost:8300 |
| Patient register gives **500** | Keycloak admin client secret missing | Set `KEYCLOAK_ADMIN_CLIENT_ID` / `_SECRET` |
| `422 … fname` | One-word name on the identity form | Enter first and last name |
| Doctor login "incorrect" | Keycloak usernames are lowercase, or wrong realm | Use `rahul`, not `Rahul`; user must be in realm `careflow` |
| Doctor page **403** | Another role logged in in the same browser | Separate browser or private window per role |
| Doctor missing from routing | No NPI, no facility, or a NUCC code not in any department | Fix the OpenEMR user (section 5.1) |
| Doctor department "unknown" | Role code not in OpenEMR's provider-role list | Use a listed role code (section 5.1) |
| No times / generic 9–5 times | No In Office blocks, or they repeat | Add non-repeating In Office events (section 5.2) |
| Office hours invisible in OpenEMR day view | Event end date stored as `0000-00-00` | Set end date = event date |
| A doctor calendar is empty | No case routed to that doctor yet | Run a patient through intake |
| AI replies missing | `OPENAI_API_KEY` missing / quota | Transcript is kept; nothing is guessed |
| `reasoning_effort` rejected | `LLM_SUPPORTS_EFFORT=true` with gpt-4.1 | Set it to `false` |
| `minio/minio` image pull denied | Image no longer on Docker Hub | Compose uses `cgr.dev/chainguard/minio` |



langfuse :http://localhost:2000/
openemr: http://localhost:8300/
keyclock: http://localhost:8500/admin/
