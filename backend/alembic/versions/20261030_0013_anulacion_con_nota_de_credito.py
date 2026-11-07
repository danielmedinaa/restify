"""anulacion de facturas con nota de credito

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-30 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ventas', sa.Column('anulada_en', sa.DateTime(timezone=True), nullable=True))
    op.add_column('ventas', sa.Column('anulada_por_id', sa.Integer(), nullable=True))
    op.add_column('ventas', sa.Column('motivo_anulacion', sa.String(length=255), nullable=True))
    op.add_column('ventas', sa.Column('nota_credito_numero', sa.String(length=40), nullable=True))
    op.add_column('ventas', sa.Column('nota_credito_control', sa.String(length=40), nullable=True))
    op.create_foreign_key(op.f('fk_ventas_anulada_por_id_usuarios'), 'ventas', 'usuarios', ['anulada_por_id'], ['id'], ondelete='SET NULL')
    op.create_index('uq_ventas_nota_credito', 'ventas', ['sucursal_id', 'nota_credito_numero'], unique=True, postgresql_where=sa.text('nota_credito_numero IS NOT NULL'))


def downgrade() -> None:
    op.drop_index('uq_ventas_nota_credito', table_name='ventas', postgresql_where=sa.text('nota_credito_numero IS NOT NULL'))
    op.drop_constraint(op.f('fk_ventas_anulada_por_id_usuarios'), 'ventas', type_='foreignkey')
    for c in ('nota_credito_control', 'nota_credito_numero', 'motivo_anulacion', 'anulada_por_id', 'anulada_en'):
        op.drop_column('ventas', c)
