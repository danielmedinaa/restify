"""posición de las mesas en el plano de la sala

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23 18:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('mesas', sa.Column('pos_x', sa.Integer(), nullable=True))
    op.add_column('mesas', sa.Column('pos_y', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('mesas', 'pos_y')
    op.drop_column('mesas', 'pos_x')
