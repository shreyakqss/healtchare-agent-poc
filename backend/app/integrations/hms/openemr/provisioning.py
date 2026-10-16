"""Creating a practitioner in OpenEMR: the one place CareFlow writes OpenEMR's database directly.

OpenEMR 8.3's API can create a practitioner (name, NPI, facility) but cannot give them a login,
a password, an access group, a specialty role or calendar hours, and CareFlow's OAuth client is
read-only for practitioners anyway. So every row is written here, in ONE transaction, copying
what OpenEMR's own Admin > Users and calendar screens write (taken from doctors created there):

  users              provider flags, NPI, taxonomy, facility; `password` is the legacy
                     placeholder OpenEMR itself stores ("NoLongerUsed")
  users_secure       the bcrypt hash OpenEMR's login checks (PHP password_verify)
  groups             the "Default" group
  gacl_aro + map     phpGACL membership of "Physicians" (group value "doc")
  facility_user_ids  provider_id / role_code / specialty_code - what FHIR PractitionerRole
                     exposes, and so what CareFlow maps to a department
  openemr_postcalendar_events
                     "In Office" (category 2) single-day blocks, each closed by an
                     "Out Of Office" (category 3) marker, as the calendar UI writes them.
                     Availability, never a patient booking (CLAUDE.md exception).
  uuid_registry      every uuid OpenEMR would have registered

Re-check this file after an OpenEMR upgrade.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time

import bcrypt
import pymysql
from pymysql.cursors import DictCursor

from app.core.config import settings
from app.core.errors import ServiceUnavailable

IN_OFFICE, OUT_OF_OFFICE = 2, 3
PHYSICIANS_GROUP = "doc"
# OpenEMR's serialized "no repeat" spec, byte for byte as its calendar writes it.
NO_REPEAT = (
    'a:6:{s:17:"event_repeat_freq";s:1:"0";s:22:"event_repeat_freq_type";s:1:"0";'
    's:19:"event_repeat_on_num";s:1:"1";s:19:"event_repeat_on_day";s:1:"0";'
    's:20:"event_repeat_on_freq";s:1:"0";s:6:"exdate";s:0:"";}'
)
ADMIN_USER_ID = 1  # pc_informant: the OpenEMR "admin" account, as for UI-created rows


@dataclass(frozen=True)
class ProviderSpec:
    username: str
    password: str
    title: str
    first_name: str
    last_name: str
    email: str
    phone: str
    npi: str
    specialty_code: str
    role_code: str
    licence: str
    facility_id: int


@dataclass(frozen=True)
class Provider:
    id: int
    uuid: str  # the FHIR Practitioner id
    username: str
    name: str
    npi: str
    specialty_code: str
    active: bool


Block = tuple[date, time, time]


def configured() -> bool:
    return bool(settings.OPENEMR_MYSQL_USER and settings.OPENEMR_MYSQL_PASSWORD)


@contextmanager
def _connect() -> Iterator[pymysql.connections.Connection]:
    if not configured():
        raise ServiceUnavailable("OpenEMR database access is not configured (OPENEMR_MYSQL_USER/PASSWORD).")
    try:
        conn = pymysql.connect(
            host=settings.OPENEMR_MYSQL_HOST, port=settings.OPENEMR_MYSQL_PORT,
            user=settings.OPENEMR_MYSQL_USER, password=settings.OPENEMR_MYSQL_PASSWORD,
            database=settings.OPENEMR_MYSQL_DB, cursorclass=DictCursor, autocommit=False,
            connect_timeout=5, charset="utf8mb4",
        )
    except pymysql.MySQLError as exc:
        raise ServiceUnavailable("The hospital system's database is unreachable.") from exc
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _transaction() -> Iterator[DictCursor]:
    with _connect() as conn:
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def _hash(password: str) -> str:
    # PHP writes "$2y$"; "$2b$" is the same algorithm and password_verify accepts both,
    # but match OpenEMR's own rows exactly.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode().replace("$2b$", "$2y$", 1)


def _register(cur: DictCursor, table: str, id_column: str) -> bytes:
    new = uuid.uuid4().bytes
    cur.execute(
        "INSERT INTO uuid_registry (uuid, table_name, table_id, table_vertical, couchdb, document_drive, mapped, created)"
        " VALUES (%s, %s, %s, '', '', 0, 0, NOW())",
        (new, table, id_column),
    )
    return new


# --- reads -------------------------------------------------------------------------------

def facility_name(facility_id: int) -> str | None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM facility WHERE id = %s", (facility_id,))
        row = cur.fetchone()
    return row["name"] if row else None


def clashes(username: str, npi: str) -> list[str]:
    """What already exists with this username or NPI (OpenEMR usernames are case-insensitive)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT LOWER(username) = LOWER(%s) AS u, npi = %s AS n FROM users"
            " WHERE LOWER(username) = LOWER(%s) OR npi = %s",
            (username, npi, username, npi),
        )
        rows = cur.fetchall()
    out = []
    if any(r["u"] for r in rows):
        out.append("That username is already used in the hospital system.")
    if any(r["n"] for r in rows):
        out.append("A practitioner with that NPI already exists.")
    return out


def list_titles(list_id: str) -> dict[str, str]:
    """An OpenEMR list's active options, code -> title."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT option_id, title FROM list_options WHERE list_id = %s AND activity = 1", (list_id,))
        return {r["option_id"]: r["title"] for r in cur.fetchall()}


def providers(facility_id: int) -> list[Provider]:
    """Practitioners at a facility: provider-flagged users with an NPI (FHIR lists no others)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT u.id, u.uuid, u.username, u.title, u.fname, u.lname, u.npi, u.active,"
            " COALESCE(s.field_value, u.taxonomy) AS specialty"
            " FROM users u LEFT JOIN facility_user_ids s"
            "   ON s.uid = u.id AND s.facility_id = u.facility_id AND s.field_id = 'specialty_code'"
            " WHERE u.facility_id = %s AND u.authorized = 1 AND u.npi IS NOT NULL AND u.npi <> ''"
            " ORDER BY u.lname, u.fname",
            (facility_id,),
        )
        rows = cur.fetchall()
    return [
        Provider(
            id=r["id"], uuid=str(uuid.UUID(bytes=r["uuid"])) if r["uuid"] else "", username=r["username"] or "",
            name=" ".join(p for p in (r["title"], r["fname"], r["lname"]) if p), npi=r["npi"],
            specialty_code=r["specialty"] or "", active=bool(r["active"]),
        )
        for r in rows
    ]


def provider(facility_id: int, provider_id: int) -> Provider | None:
    return next((p for p in providers(facility_id) if p.id == provider_id), None)


def office_blocks(user_id: int) -> list[Block]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT pc_eventDate, pc_startTime, pc_endTime FROM openemr_postcalendar_events"
            " WHERE pc_aid = %s AND pc_catid = %s",
            (str(user_id), IN_OFFICE),
        )
        rows = cur.fetchall()
    return [(r["pc_eventDate"], _as_time(r["pc_startTime"]), _as_time(r["pc_endTime"])) for r in rows]


def _as_time(value) -> time:
    # PyMySQL returns TIME columns as timedelta.
    if isinstance(value, time):
        return value
    seconds = int(value.total_seconds())
    return time(seconds // 3600, seconds % 3600 // 60)


# --- writes ------------------------------------------------------------------------------

def create_provider(spec: ProviderSpec, blocks: list[Block]) -> Provider:
    """Every row a working practitioner needs, all or nothing."""
    with _transaction() as cur:
        cur.execute("SELECT name FROM facility WHERE id = %s", (spec.facility_id,))
        facility = cur.fetchone()
        if facility is None:
            raise ServiceUnavailable("The hospital's facility no longer exists in the hospital system.")
        user_uuid = _register(cur, "users", "id")
        cur.execute(
            "INSERT INTO users (uuid, username, password, authorized, title, fname, lname, email, phonew1,"
            " facility, facility_id, billing_facility, billing_facility_id, see_auth, active, npi, taxonomy,"
            " state_license_number, cal_ui, calendar, main_menu_role, patient_menu_role, date_created, last_updated)"
            " VALUES (%s, %s, 'NoLongerUsed', 1, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 1, %s, %s, %s, 1, 1,"
            " 'standard', 'standard', NOW(), NOW())",
            (user_uuid, spec.username, spec.title, spec.first_name, spec.last_name, spec.email, spec.phone,
             facility["name"], spec.facility_id, facility["name"], spec.facility_id, spec.npi,
             spec.specialty_code, spec.licence),
        )
        user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO users_secure (id, username, password, last_update_password, last_update)"
            " VALUES (%s, %s, %s, NOW(), NOW())",
            (user_id, spec.username, _hash(spec.password)),
        )
        cur.execute("INSERT INTO `groups` (name, user) VALUES ('Default', %s)", (spec.username,))
        _add_to_physicians(cur, spec.username, f"{spec.first_name} {spec.last_name}")
        fuid = _register(cur, "facility_user_ids", "id")
        for field, value in (("provider_id", spec.npi), ("role_code", spec.role_code), ("specialty_code", spec.specialty_code)):
            cur.execute(
                "INSERT INTO facility_user_ids (uid, facility_id, uuid, field_id, field_value) VALUES (%s, %s, %s, %s, %s)",
                (user_id, spec.facility_id, fuid, field, value),
            )
        _insert_blocks(cur, user_id, spec.facility_id, blocks)
    return Provider(
        id=user_id, uuid=str(uuid.UUID(bytes=user_uuid)), username=spec.username,
        name=" ".join(p for p in (spec.title, spec.first_name, spec.last_name) if p),
        npi=spec.npi, specialty_code=spec.specialty_code, active=True,
    )


def _add_to_physicians(cur: DictCursor, username: str, name: str) -> None:
    """phpGACL: an ARO for the user (ids come from gacl_aro_seq) mapped into "Physicians"."""
    cur.execute("SELECT id FROM gacl_aro_groups WHERE value = %s", (PHYSICIANS_GROUP,))
    group = cur.fetchone()
    if group is None:
        raise ServiceUnavailable("OpenEMR has no Physicians access group.")
    cur.execute("SELECT id FROM gacl_aro_seq FOR UPDATE")
    aro_id = cur.fetchone()["id"] + 1
    cur.execute("UPDATE gacl_aro_seq SET id = %s", (aro_id,))
    cur.execute(
        "INSERT INTO gacl_aro (id, section_value, value, order_value, name, hidden) VALUES (%s, 'users', %s, 10, %s, 0)",
        (aro_id, username, name),
    )
    cur.execute("INSERT INTO gacl_groups_aro_map (group_id, aro_id) VALUES (%s, %s)", (group["id"], aro_id))


def _insert_blocks(cur: DictCursor, user_id: int, facility_id: int, blocks: list[Block]) -> None:
    for day, start, end in blocks:
        duration = (datetime.combine(day, end) - datetime.combine(day, start)).seconds
        for category, title, begin, finish, length in (
            (IN_OFFICE, "In Office", start, end, duration),
            (OUT_OF_OFFICE, "Out Of Office", end, end, 0),
        ):
            cur.execute(
                "INSERT INTO openemr_postcalendar_events (pc_catid, pc_multiple, pc_aid, pc_pid, pc_title, pc_time,"
                " pc_hometext, pc_informant, pc_eventDate, pc_endDate, pc_duration, pc_recurrtype, pc_recurrspec,"
                " pc_startTime, pc_endTime, pc_eventstatus, pc_sharing, pc_apptstatus, pc_facility,"
                " pc_billing_location, pc_room, uuid)"
                " VALUES (%s, 0, %s, '', %s, NOW(), '', %s, %s, %s, %s, 0, %s, %s, %s, 1, 1, '-', %s, %s, '', %s)",
                (category, str(user_id), title, ADMIN_USER_ID, day, day, length, NO_REPEAT,
                 begin, finish, facility_id, facility_id, _register(cur, "openemr_postcalendar_events", "pc_eid")),
            )


def add_office_blocks(user_id: int, facility_id: int, blocks: list[Block]) -> None:
    with _transaction() as cur:
        _insert_blocks(cur, user_id, facility_id, blocks)


def delete_provider(user_id: int) -> None:
    """Undo `create_provider` - the rollback when a later step (Keycloak) fails."""
    with _transaction() as cur:
        cur.execute("SELECT username, uuid FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if user is None:
            return
        cur.execute(
            "DELETE r FROM uuid_registry r JOIN openemr_postcalendar_events e ON e.uuid = r.uuid WHERE e.pc_aid = %s",
            (str(user_id),),
        )
        cur.execute("DELETE FROM openemr_postcalendar_events WHERE pc_aid = %s", (str(user_id),))
        cur.execute(
            "DELETE r FROM uuid_registry r JOIN facility_user_ids f ON f.uuid = r.uuid WHERE f.uid = %s", (user_id,),
        )
        cur.execute("DELETE FROM facility_user_ids WHERE uid = %s", (user_id,))
        cur.execute(
            "DELETE m FROM gacl_groups_aro_map m JOIN gacl_aro a ON a.id = m.aro_id"
            " WHERE a.section_value = 'users' AND a.value = %s", (user["username"],),
        )
        cur.execute("DELETE FROM gacl_aro WHERE section_value = 'users' AND value = %s", (user["username"],))
        cur.execute("DELETE FROM `groups` WHERE user = %s", (user["username"],))
        cur.execute("DELETE FROM users_secure WHERE id = %s", (user_id,))
        cur.execute("DELETE FROM uuid_registry WHERE uuid = %s", (user["uuid"],))
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))


def usage(user_id: int, username: str) -> dict[str, int]:
    """What in OpenEMR already points at this practitioner. All zero = safe to erase."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM form_encounter WHERE provider_id = %s", (user_id,))
        encounters = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM forms WHERE user = %s AND deleted = 0", (username,))
        forms = cur.fetchone()["n"]
        cur.execute(
            "SELECT COUNT(*) AS n FROM openemr_postcalendar_events WHERE pc_aid = %s AND pc_pid <> '' AND pc_pid IS NOT NULL",
            (str(user_id),),
        )
        appointments = cur.fetchone()["n"]
    return {"encounters": encounters, "forms": forms, "appointments": appointments}


def set_active(user_id: int, active: bool) -> None:
    """Deactivate or reactivate. Inactive, FHIR reports `active: false` (CareFlow then never
    routes to them or accepts their sign-off) and `calendar = 0` hides them from OpenEMR's
    calendar. Their published hours are kept, so reactivating restores their schedule."""
    with _transaction() as cur:
        cur.execute("UPDATE users SET active = %s, calendar = %s, last_updated = NOW() WHERE id = %s",
                    (int(active), int(active), user_id))
