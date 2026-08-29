import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.errors import Conflict
from app.domain.lifecycle import CaseStatus
from app.services.consultation_service import assert_finalizable


def test_completed_case_cannot_be_finalized_again():
    case = SimpleNamespace(id=uuid.uuid4())
    with patch("app.services.consultation_service.case_repo.session_for", return_value=SimpleNamespace(status=CaseStatus.COMPLETED)):
        with pytest.raises(Conflict, match="Only an approved case"):
            assert_finalizable(SimpleNamespace(), case)
