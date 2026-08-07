"""Medical Record Processor — makes uploaded documents readable, nothing more.

Text extraction already happened at upload time (services/extraction.py). This
agent's whole job is to surface that text to the clinician-facing summary.

It does not interpret images, does not produce findings, and does not write
PatientFact rows — attachment content must never reach the triage engine, which
is what keeps "an attachment cannot change a priority" true by construction.
"""
from sqlalchemy.orm import Session
from models import MedicalAttachment

MAX_EXCERPT_CHARS = 2000

def collect_attachments(db: Session, case_id) -> dict:
    """Summarise what is attached and pull readable excerpts from documents."""
    attachments = (
        db.query(MedicalAttachment)
        .filter(MedicalAttachment.case_id == case_id)
        .order_by(MedicalAttachment.created_at)
        .all()
    )

    documents = []
    images = []

    for attachment in attachments:
        entry = {
            "id": str(attachment.id),
            "kind": attachment.kind,
            "filename": attachment.filename,
            "mime_type": attachment.mime_type,
        }
        if attachment.extracted_text:
            documents.append(
                {**entry, "excerpt": attachment.extracted_text[:MAX_EXCERPT_CHARS]}
            )
        else:
            # Images and anything unparsed: listed for the clinician to open,
            # never described or interpreted by the system.
            images.append({**entry, "note": "Stored for clinician review. Not interpreted."})

    return {
        "attachment_count": len(attachments),
        "documents": documents,
        "images_and_unparsed": images,
    }
