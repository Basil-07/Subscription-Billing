import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app import models

def get_reconciliation_records(db: Session):
    """
    Fetches all reconciliation records.
    """
    return db.query(models.ReconciliationRecord).order_by(models.ReconciliationRecord.created_at.desc()).all()

def resolve_reconciliation_record(db: Session, record_id: str, resolution_notes: str):
    """
    Manually resolves a reconciliation record and posts the corresponding ledger entry.
    """
    rec_uuid = uuid.UUID(record_id) if isinstance(record_id, str) else record_id
    record = db.query(models.ReconciliationRecord).filter(
        models.ReconciliationRecord.id == rec_uuid
    ).first()
    
    if not record:
        return None

    record.status = "RESOLVED"
    record.resolved_at = datetime.now(timezone.utc)
    record.resolution_notes = resolution_notes

    # Post the ledger entry associated with the reconciliation
    ledger_entry = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.id == record.ledger_entry_id
    ).first()
    
    if ledger_entry:
        ledger_entry.status = "POSTED"
        ledger_entry.posted_at = datetime.now(timezone.utc)

    db.commit()
    return record
