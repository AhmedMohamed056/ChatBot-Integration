"""Phase 1 PostgreSQL-first platform foundation.

Revision ID: 0001_phase1_foundation
Revises:
"""

from __future__ import annotations

from typing import Optional, Sequence, Union

from alembic import op

from db.base import Base
from db import models as _legacy_models  # noqa: F401
from db import platform_models as _platform_models  # noqa: F401


revision: str = "0001_phase1_foundation"
down_revision: Optional[Union[str, Sequence[str]]] = None
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Create the complete initial schema in foreign-key dependency order."""
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    """Drop the complete initial schema in reverse dependency order."""
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        table.drop(bind=bind, checkfirst=True)
