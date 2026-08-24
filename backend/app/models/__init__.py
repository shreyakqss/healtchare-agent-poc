"""Import every model here so `Base.metadata` is complete."""

from app.db.base import Base
from app.models.audit import AuditEvent
from app.models.care_task import CareTask
from app.models.case import PatientCase
from app.models.clinical import ClinicalReview, ClinicalSummary, ConsultationNote
from app.models.facts import AllergyMedication, MedicalAttachment, PatientFact
from app.models.intake import IntakeMessage, IntakeSession
from app.models.triage import RoutingRecommendation, TriageResult, TriageRule

__all__ = [
    "Base",
    "AuditEvent",
    "CareTask",
    "PatientCase",
    "ClinicalReview",
    "ClinicalSummary",
    "ConsultationNote",
    "AllergyMedication",
    "MedicalAttachment",
    "PatientFact",
    "IntakeMessage",
    "IntakeSession",
    "RoutingRecommendation",
    "TriageResult",
    "TriageRule",
]
