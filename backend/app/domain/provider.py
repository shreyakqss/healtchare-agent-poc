"""Rules for a new practitioner, checked before anything is written anywhere. Pure: no I/O."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from app.domain.scheduling import WEEK

USERNAME = re.compile(r"^[a-z][a-z0-9._-]{2,31}$")
MIN_PASSWORD_LENGTH = 9  # OpenEMR's `gbl_minimum_password_length` on this install
EARLIEST, LATEST = time(6, 0), time(22, 0)
MAX_RANGES_PER_DAY = 3
MAX_WEEKS = 26
GENERIC_ROLE = "207Q00000X"  # Family Medicine - OpenEMR's own default taxonomy


def npi_is_valid(npi: str) -> bool:
    """A US NPI: 10 digits whose last is the Luhn check digit over "80840" + the first nine
    (CMS, "Requirements for NPI check digit")."""
    if not re.fullmatch(r"\d{10}", npi):
        return False
    digits = [int(c) for c in "80840" + npi[:9]]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10 == int(npi[9])


def password_problem(password: str, username: str) -> str | None:
    """OpenEMR's "secure password" rule (three of: lower, upper, digit, symbol), which the
    same password must also pass in Keycloak."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3:
        return "Password needs three of: a lowercase letter, an uppercase letter, a number, a symbol."
    if username and username.lower() in password.lower():
        return "Password must not contain the username."
    return None


def role_code_for(specialty_code: str, role_codes: set[str]) -> str:
    """OpenEMR's "Provider Role" for a NUCC specialty: the code itself when the role list has
    it, else its parent ("207RC0000X" -> "207R00000X"), else a generic physician."""
    if specialty_code in role_codes:
        return specialty_code
    parent = specialty_code[:4] + "00000X"
    return parent if parent in role_codes else GENERIC_ROLE


def _clock(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def hours_problems(days: list[str], ranges: list[tuple[str, str]]) -> list[str]:
    """Why a weekly pattern cannot be published, or [] when it can."""
    problems: list[str] = []
    if not days:
        problems.append("Pick at least one working day.")
    if any(d not in WEEK for d in days):
        problems.append("Unknown working day.")
    if not ranges:
        problems.append("Add at least one time range.")
    if len(ranges) > MAX_RANGES_PER_DAY:
        problems.append(f"At most {MAX_RANGES_PER_DAY} time ranges a day.")
    parsed: list[tuple[time, time]] = []
    for start, end in ranges:
        try:
            s, e = _clock(start), _clock(end)
        except ValueError:
            problems.append(f"{start}-{end} is not a valid time range.")
            continue
        if e <= s:
            problems.append(f"{start}-{end} ends before it starts.")
        elif s < EARLIEST or e > LATEST:
            problems.append(f"{start}-{end} must sit between {EARLIEST:%H:%M} and {LATEST:%H:%M}.")
        elif (datetime.combine(date.min, e) - datetime.combine(date.min, s)) < timedelta(minutes=30):
            problems.append(f"{start}-{end} is shorter than one 30-minute appointment.")
        else:
            parsed.append((s, e))
    parsed.sort()
    for (_, prev_end), (next_start, _) in zip(parsed, parsed[1:], strict=False):
        if next_start < prev_end:
            problems.append("Time ranges overlap.")
            break
    return problems


def expand_hours(days: list[str], ranges: list[tuple[str, str]], start: date, weeks: int) -> list[tuple[date, time, time]]:
    """Dated office-hour blocks for `weeks` weeks from `start`: one per working day per range.
    CareFlow reads only single-day calendar rows, never OpenEMR's repeating ones."""
    wanted = {WEEK.index(d) for d in days}
    clocks = sorted((_clock(s), _clock(e)) for s, e in ranges)
    out: list[tuple[date, time, time]] = []
    for offset in range(weeks * 7):
        day = start + timedelta(days=offset)
        if day.weekday() in wanted:
            out.extend((day, s, e) for s, e in clocks)
    return out


def repeat_last_week(blocks: list[tuple[date, time, time]], weeks: int) -> list[tuple[date, time, time]]:
    """"Extend hours": the last published week (the 7 days ending on the last block) copied
    forward `weeks` more times, so each day keeps its own ranges."""
    if not blocks:
        return []
    last = max(d for d, _, _ in blocks)
    template = sorted({b for b in blocks if b[0] > last - timedelta(days=7)})
    return [(d + timedelta(days=7 * k), s, e) for k in range(1, weeks + 1) for d, s, e in template]
