"""add job_description_id to resumes

Revision ID: df2e0eaa202d
Revises: 94ec14fbae11
Create Date: 2026-08-19 22:34:51.495609

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'df2e0eaa202d'
down_revision: Union[str, None] = '94ec14fbae11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('resumes', sa.Column('job_description_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_resumes_job_description_id'), 'resumes', ['job_description_id'], unique=False)
    # Autogenerate omits a name here (no naming convention is configured on
    # the metadata) — `None` would work for create but `drop_constraint`
    # requires an actual name, so downgrade would otherwise fail outright.
    op.create_foreign_key(
        'fk_resumes_job_description_id',
        'resumes', 'job_descriptions', ['job_description_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_resumes_job_description_id', 'resumes', type_='foreignkey')
    op.drop_index(op.f('ix_resumes_job_description_id'), table_name='resumes')
    op.drop_column('resumes', 'job_description_id')
