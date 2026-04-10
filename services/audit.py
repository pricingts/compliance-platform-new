"""Audit trail service for compliance-grade action logging."""
import json
from sqlalchemy import text
from sqlalchemy.orm import Session
from services.logging_config import get_logger

logger = get_logger(__name__)


def log_action(
    session: Session,
    user_email: str,
    action: str,
    entity_type: str,
    entity_id: int = None,
    old_value: dict = None,
    new_value: dict = None,
    details: str = None,
):
    """Log an action to the audit trail."""
    session.execute(
        text("""
            INSERT INTO audit_log (user_email, action, entity_type, entity_id, old_value, new_value, details)
            VALUES (:user_email, :action, :entity_type, :entity_id, :old_value, :new_value, :details)
        """),
        {
            "user_email": user_email,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "old_value": json.dumps(old_value) if old_value else None,
            "new_value": json.dumps(new_value) if new_value else None,
            "details": details,
        }
    )

    logger.info(
        f"AUDIT: {action} on {entity_type}",
        extra={
            "user_email": user_email,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
        }
    )
