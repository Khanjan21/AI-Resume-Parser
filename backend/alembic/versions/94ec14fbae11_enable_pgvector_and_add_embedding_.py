"""enable pgvector and add embedding columns

Revision ID: 94ec14fbae11
Revises: 2abc4c2babe0
Create Date: 2026-08-13 19:50:21.572681

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = '94ec14fbae11'
down_revision: Union[str, None] = '2abc4c2babe0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Must exist before any column can use the `vector` type below. The
    # Postgres image (pgvector/pgvector:pg16) ships the extension; this just
    # turns it on for this database.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column('job_descriptions', sa.Column('embedding', Vector(384), nullable=True))
    op.add_column('job_roles', sa.Column('embedding', Vector(384), nullable=True))
    op.add_column('resumes', sa.Column('embedding', Vector(384), nullable=True))


def downgrade() -> None:
    op.drop_column('resumes', 'embedding')
    op.drop_column('job_roles', 'embedding')
    op.drop_column('job_descriptions', 'embedding')
    # Extension is intentionally left enabled — dropping it is riskier than
    # useful, and pgvector has no downside just sitting there unused.
