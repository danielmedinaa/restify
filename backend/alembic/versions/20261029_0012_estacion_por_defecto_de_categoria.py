"""estacion por defecto de la categoria

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-29 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('categorias', sa.Column('estacion_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_categorias_estacion_id_estaciones'), 'categorias', 'estaciones', ['estacion_id'], ['id'], ondelete='SET NULL')
    # Las categorías de bebidas ya existentes pasan a la barra; el resto, a la cocina
    op.execute("UPDATE categorias SET estacion_id = (SELECT id FROM estaciones WHERE nombre = 'Barra') WHERE lower(nombre) LIKE 'bebida%'")
    op.execute("UPDATE categorias SET estacion_id = (SELECT id FROM estaciones WHERE nombre = 'Cocina') WHERE estacion_id IS NULL")


def downgrade() -> None:
    op.drop_constraint(op.f('fk_categorias_estacion_id_estaciones'), 'categorias', type_='foreignkey')
    op.drop_column('categorias', 'estacion_id')
