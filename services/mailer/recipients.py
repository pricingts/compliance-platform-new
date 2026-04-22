"""Recipient resolution for new-request notification emails.

The TO list is built from two sources:
  * A hardcoded tuple of compliance shared-inbox addresses (fallback if the DB
    has no compliance users).
  * Active users with ``rol = 'compliance'`` from the ``users`` table.

The combined list is de-duplicated case-insensitively and filtered to the
allowed domains in ``config.constants.ALLOWED_EMAIL_DOMAINS``.

The CC list is the creator and (optionally) the submitted-by address, minus
any overlap with the TO list. CC is *not* domain-filtered because the creator
may be a comercial or inside-sales on ``tradingsol.com`` or a whitelisted
partner (the domain filter is only applied on compliance recipients so we
never leak a request to an unintended party).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from config.constants import ALLOWED_EMAIL_DOMAINS
from services.logging_config import get_logger
from services.users import get_active_compliance_users

logger = get_logger(__name__)


DEFAULT_COMPLIANCE_RECIPIENTS: tuple[str, ...] = (
    "compliance1@tradingsolutions.com",
    "compliance2@tradingsolutions.com",
    "compliance@tradingsolutions.com",
)


def _normalize(email: Optional[str]) -> Optional[str]:
    """Return a lowercased, stripped email. None/empty -> None."""
    if not email:
        return None
    cleaned = email.strip().lower()
    return cleaned or None


def _is_allowed_domain(email: str) -> bool:
    """True iff the email ends with any of the allowed domains."""
    email_lower = email.lower()
    return any(email_lower.endswith("@" + d) for d in ALLOWED_EMAIL_DOMAINS)


def resolve_recipients(
    session: Session,
    creator_email: Optional[str],
    submitted_by_email: Optional[str] = None,
    *,
    exclude_creator_from_cc: bool = False,
) -> dict:
    """Resolve TO / CC addresses for a new-request notification.

    Args:
        session: SQLAlchemy session used to query compliance users.
        creator_email: Address of the user who filled the form.
        submitted_by_email: Address of the user who physically submitted the
            form (only different from creator_email when Inside Sales creates
            on behalf of a comercial).
        exclude_creator_from_cc: When True (e.g. when the transport will send
            with ``From = creator_email``, as the Gmail transport does), the
            creator is removed from CC to avoid appearing twice in the email
            (once as From and once as CC). Default ``False`` preserves the
            pre-Phase-8.3 behavior where the creator is always in CC.

    Returns:
        ``{"to": [...], "cc": [...]}``. Both lists are sorted. If no
        compliance recipient survives the domain filter, ``to`` is returned
        empty and an error is logged (extreme edge case — the hardcoded
        defaults are all @tradingsolutions.com so this should never happen
        in practice).
    """
    # ---- Build TO -------------------------------------------------------
    to_map: dict[str, str] = {}  # lowercased -> original
    for addr in DEFAULT_COMPLIANCE_RECIPIENTS:
        normalized = _normalize(addr)
        if not normalized:
            continue
        if not _is_allowed_domain(normalized):
            logger.warning(
                "Hardcoded compliance recipient filtered by domain",
                extra={"email": normalized},
            )
            continue
        to_map.setdefault(normalized, normalized)

    for user in get_active_compliance_users(session):
        normalized = _normalize(user.get("email"))
        if not normalized:
            continue
        if not _is_allowed_domain(normalized):
            logger.warning(
                "Compliance user filtered by disallowed domain",
                extra={"email": normalized},
            )
            continue
        to_map.setdefault(normalized, normalized)

    to_list = sorted(to_map.values())

    if not to_list:
        logger.error(
            "resolve_recipients: TO list is empty after filtering — "
            "notification cannot be delivered",
        )

    # ---- Build CC -------------------------------------------------------
    to_lower_set = {e.lower() for e in to_list}
    creator_norm = _normalize(creator_email)
    cc_map: dict[str, str] = {}
    for addr in (creator_email, submitted_by_email):
        normalized = _normalize(addr)
        if not normalized:
            continue
        if normalized in to_lower_set:
            continue
        if exclude_creator_from_cc and creator_norm and normalized == creator_norm:
            # Creator is already going to be the From of the Gmail message;
            # leaving it in CC would show up twice in the recipient's client.
            continue
        cc_map.setdefault(normalized, normalized)

    cc_list = sorted(cc_map.values())

    return {"to": to_list, "cc": cc_list}
