"""add_spatial_indexes

Revision ID: b0910356ecc6
Revises: b9c7bd993bed
Create Date: 2026-04-18 13:45:03.523906

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0910356ecc6'
down_revision: Union[str, Sequence[str], None] = 'b9c7bd993bed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_trails_geometry")
    op.execute("CREATE INDEX idx_trails_geometry ON trails USING gist (geometry)")
    op.execute("DROP INDEX IF EXISTS idx_activities_geometry")
    op.execute("CREATE INDEX idx_activities_geometry ON activities USING gist (geometry)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_activities_geometry")
    op.execute("DROP INDEX IF EXISTS idx_trails_geometry")
