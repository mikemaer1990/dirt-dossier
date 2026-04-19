"""osm_trail_columns

Revision ID: e79d2edab4f2
Revises: b0910356ecc6
Create Date: 2026-04-19 06:17:58.753007

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e79d2edab4f2'
down_revision: Union[str, Sequence[str], None] = 'b0910356ecc6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("trails_trailforks_id_key", "trails", type_="unique")
    op.alter_column("trails", "trailforks_id", new_column_name="osm_way_id")
    op.alter_column(
        "trails",
        "osm_way_id",
        type_=sa.BigInteger(),
        postgresql_using="osm_way_id::bigint",
    )
    op.create_unique_constraint("trails_osm_way_id_key", "trails", ["osm_way_id"])
    op.add_column(
        "trails",
        sa.Column("source", sa.Text(), nullable=False, server_default="osm"),
    )
    op.add_column(
        "trails",
        sa.Column("raw_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trails", "raw_tags")
    op.drop_column("trails", "source")
    op.drop_constraint("trails_osm_way_id_key", "trails", type_="unique")
    op.alter_column(
        "trails",
        "osm_way_id",
        type_=sa.Text(),
        postgresql_using="osm_way_id::text",
    )
    op.alter_column("trails", "osm_way_id", new_column_name="trailforks_id")
    op.create_unique_constraint("trails_trailforks_id_key", "trails", ["trailforks_id"])
