"""Import every model so Base.metadata is complete."""

from models.database import Base, SessionLocal, engine, get_db
from models.intake_session import IntakeSession
from models.patient_case import PatientCase
from models.patient_fact import PatientFact
from models.allergy_medication import AllergyMedication
from models.triage_rule import TriageRule
from models.triage_result import TriageResult
from models.routing_recommendation import RoutingRecommendation
from models.clinical_summary import ClinicalSummary
from models.clinical_review import ClinicalReview
from models.audit_event import AuditEvent

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "IntakeSession",
    "PatientCase",
    "PatientFact",
    "AllergyMedication",
    "TriageRule",
    "TriageResult",
    "RoutingRecommendation",
    "ClinicalSummary",
    "ClinicalReview",
    "AuditEvent",
]
