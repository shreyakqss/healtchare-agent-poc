import uuid

import pytest
from sqlalchemy import event

from app.api.v1 import serializers
from app.core.errors import Unprocessable
from app.db import SessionLocal, engine
from app.models import IntakeSession, PatientCase
from app.security import CurrentPrincipal, cases_for_principal


@pytest.fixture
def cases():
    session_ids = []
    with SessionLocal() as db:
        for index in range(5):
            session = IntakeSession(status="INGESTING", consent_status="GRANTED", channel="web")
            db.add(session)
            db.flush()
            db.add(
                PatientCase(
                    session_id=session.id,
                    hospital_id="qss-demo-clinic",
                )
            )
            session_ids.append(session.id)
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(IntakeSession).filter(IntakeSession.id.in_(session_ids)).delete(synchronize_session=False)
        db.commit()


def _clinician() -> CurrentPrincipal:
    return CurrentPrincipal(
        user_id=uuid.uuid4(),
        subject="pagination-test",
        roles=frozenset({"clinician"}),
        clinic_id="qss-demo-clinic",
    )


def test_cursor_pagination_has_no_overlap_and_rejects_invalid_cursor(cases):
    with SessionLocal() as db:
        first = cases_for_principal(db, _clinician(), "clinician", limit=2)
        second = cases_for_principal(db, _clinician(), "clinician", limit=2, cursor=first.next_cursor)
        assert len(first.items) == len(second.items) == 2
        assert {case.id for case in first.items}.isdisjoint(case.id for case in second.items)
        assert first.next_cursor and second.next_cursor
        with pytest.raises(Unprocessable):
            cases_for_principal(db, _clinician(), "clinician", limit=2, cursor="not-a-cursor")


def test_case_list_projection_uses_constant_query_count(cases):
    with SessionLocal() as db:
        page = cases_for_principal(db, _clinician(), "clinician", limit=5)
        statements = 0

        def count_query(*_):
            nonlocal statements
            statements += 1

        event.listen(engine, "before_cursor_execute", count_query)
        try:
            result = serializers.case_list(db, page.items)
        finally:
            event.remove(engine, "before_cursor_execute", count_query)

    assert len(result) == 5
    assert statements == 7
