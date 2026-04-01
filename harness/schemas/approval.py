"""Human approval decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    """Discrete approval outcomes."""

    APPROVED = "approved"
    REJECTED = "rejected"
    EDITING_LATER = "editing_later"


class ApprovalDecision(BaseModel):
    """Record of a human gate decision."""

    status: ApprovalStatus
    actor: str = ""
    note: str = ""
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
