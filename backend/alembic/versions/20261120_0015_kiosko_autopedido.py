"""caja automática (autopedido): origen kiosko y número de turno

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-20 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('comandas', sa.Column('turno', sa.Integer(), nullable=True))
    op.drop_constraint(op.f('ck_comandas_origencomanda'), 'comandas', type_='check')
    op.create_check_constraint(op.f('ck_comandas_origencomanda'), 'comandas', "origen IN ('qr', 'caja', 'kiosko')")


def downgrade() -> None:
    op.execute("DELETE FROM comandas WHERE origen = 'kiosko'")
    op.drop_constraint(op.f('ck_comandas_origencomanda'), 'comandas', type_='check')
    op.create_check_constraint(op.f('ck_comandas_origencomanda'), 'comandas', "origen IN ('qr', 'caja')")
    op.drop_column('comandas', 'turno')
