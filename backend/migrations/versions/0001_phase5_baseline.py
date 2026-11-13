"""AURA Phase 5 baseline: ensure the current AURA schema exists.

This migration is intentionally additive. It creates missing tables from the
current SQLAlchemy metadata and never drops or renames existing student data.
"""
from alembic import op

revision = "0001_phase5_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from database import Base
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # A baseline downgrade must not delete student data. Restore a database
    # backup to roll back an installation instead of dropping application tables.
    pass
