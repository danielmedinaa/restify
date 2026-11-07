"""unidades kg y litro para insumos

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-29 20:00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f('ck_insumos_unidad'), 'insumos', type_='check')
    op.create_check_constraint(op.f('ck_insumos_unidad'), 'insumos', "unidad IN ('g', 'kg', 'ml', 'l', 'unidad')")


def downgrade() -> None:
    op.execute("UPDATE insumos SET unidad = 'g' WHERE unidad = 'kg'")
    op.execute("UPDATE insumos SET unidad = 'ml' WHERE unidad = 'l'")
    op.drop_constraint(op.f('ck_insumos_unidad'), 'insumos', type_='check')
    op.create_check_constraint(op.f('ck_insumos_unidad'), 'insumos', "unidad IN ('g', 'ml', 'unidad')")
