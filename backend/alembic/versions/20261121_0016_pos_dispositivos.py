"""puntos de cobro (POS) configurables

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-21 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pos_dispositivos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sucursal_id', sa.Integer(), nullable=True),
        sa.Column('nombre', sa.String(length=80), nullable=False),
        sa.Column('tipo', sa.String(length=10), nullable=False),
        sa.Column('activo', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('config', sa.Text(), nullable=True),
        sa.Column('secretos', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursales.id'], name=op.f('fk_pos_dispositivos_sucursal_id_sucursales'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_pos_dispositivos')),
    )
    op.create_index(op.f('ix_pos_dispositivos_sucursal_id'), 'pos_dispositivos', ['sucursal_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_pos_dispositivos_sucursal_id'), table_name='pos_dispositivos')
    op.drop_table('pos_dispositivos')
