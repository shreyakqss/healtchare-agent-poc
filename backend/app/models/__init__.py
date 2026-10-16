"""Import every model here so `Base.metadata` is complete."""

from app.db.base import Base
from app.models.audit import AdminAuditEvent, AuditEvent
from app.models.care_task import CareTask
from app.models.case import PatientCase
from app.models.clinical import ClinicalDiscrepancy, ClinicalReview, ClinicalSummary, ConsultationNote
from app.models.facts import AllergyMedication, MedicalAttachment, PatientFact
from app.models.identity import ApplicationUser, AuthSession, CaseOwner, RateLimitBucket
from app.models.intake import IntakeMessage, IntakeSession
from app.models.triage import RoutingRecommendation, SlotHold, TriageResult, TriageRule
from app.models.workflow import WorkflowJob, WorkflowOperation

__all__ = [
    "Base",
    "AdminAuditEvent",
    "AuditEvent",
    "CareTask",
    "PatientCase",
    "ClinicalDiscrepancy",
    "ClinicalReview",
    "ClinicalSummary",
    "ConsultationNote",
    "AllergyMedication",
    "MedicalAttachment",
    "PatientFact",
    "ApplicationUser",
    "AuthSession",
    "CaseOwner",
    "RateLimitBucket",
    "IntakeMessage",
    "IntakeSession",
    "RoutingRecommendation",
    "SlotHold",
    "TriageResult",
    "TriageRule",
    "WorkflowJob",
    "WorkflowOperation",
]
