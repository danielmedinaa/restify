"""unidades dinamicas, presentaciones de reposicion y productos de reventa

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-04 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    unidades = op.create_table(
        'unidades_medida',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(length=20), nullable=False),
        sa.Column('nombre', sa.String(length=60), nullable=False),
        sa.Column('abreviatura', sa.String(length=12), nullable=False),
        sa.Column('permite_decimales', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('subunidad_abreviatura', sa.String(length=12), nullable=True),
        sa.Column('factor_subunidad', sa.Numeric(14, 3), nullable=True),
        sa.Column('es_base', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('activa', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_unidades_medida')),
        sa.UniqueConstraint('codigo', name=op.f('uq_unidades_medida_codigo')),
        sa.UniqueConstraint('nombre', name=op.f('uq_unidades_medida_nombre')),
    )
    op.bulk_insert(unidades, [
        {'codigo': 'g', 'nombre': 'gramos', 'abreviatura': 'g', 'permite_decimales': True, 'es_base': True},
        {'codigo': 'kg', 'nombre': 'kilos', 'abreviatura': 'kg', 'permite_decimales': True, 'subunidad_abreviatura': 'g', 'factor_subunidad': 1000, 'es_base': True},
        {'codigo': 'ml', 'nombre': 'mililitros', 'abreviatura': 'ml', 'permite_decimales': True, 'es_base': True},
        {'codigo': 'l', 'nombre': 'litros', 'abreviatura': 'L', 'permite_decimales': True, 'subunidad_abreviatura': 'ml', 'factor_subunidad': 1000, 'es_base': True},
        {'codigo': 'unidad', 'nombre': 'unidades', 'abreviatura': 'u', 'permite_decimales': False, 'es_base': True},
    ])
    op.drop_constraint(op.f('ck_insumos_unidad'), 'insumos', type_='check')
    op.create_foreign_key(
        op.f('fk_insumos_unidad_unidades_medida'), 'insumos', 'unidades_medida', ['unidad'], ['codigo'], onupdate='CASCADE', ondelete='RESTRICT'
    )

    op.create_table(
        'insumo_presentaciones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('insumo_id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=80), nullable=False),
        sa.Column('cantidad', sa.Numeric(14, 3), nullable=False),
        sa.CheckConstraint('cantidad > 0', name=op.f('ck_insumo_presentaciones_cantidad_positiva')),
        sa.ForeignKeyConstraint(['insumo_id'], ['insumos.id'], name=op.f('fk_insumo_presentaciones_insumo_id_insumos'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_insumo_presentaciones')),
        sa.UniqueConstraint('insumo_id', 'nombre', name=op.f('uq_insumo_presentaciones_insumo_id')),
    )
    op.create_index(op.f('ix_insumo_presentaciones_insumo_id'), 'insumo_presentaciones', ['insumo_id'])

    op.add_column('productos', sa.Column('insumo_id', sa.Integer(), nullable=True))
    op.add_column('productos', sa.Column('cantidad_por_venta', sa.Numeric(14, 3), server_default='1', nullable=False))
    op.create_foreign_key(op.f('fk_productos_insumo_id_insumos'), 'productos', 'insumos', ['insumo_id'], ['id'], ondelete='RESTRICT')
    op.create_index(op.f('ix_productos_insumo_id'), 'productos', ['insumo_id'])
    op.create_check_constraint(op.f('ck_productos_receta_o_insumo'), 'productos', 'receta_id IS NULL OR insumo_id IS NULL')
    op.create_check_constraint(op.f('ck_productos_cantidad_por_venta_positiva'), 'productos', 'cantidad_por_venta > 0')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_productos_cantidad_por_venta_positiva'), 'productos', type_='check')
    op.drop_constraint(op.f('ck_productos_receta_o_insumo'), 'productos', type_='check')
    op.drop_index(op.f('ix_productos_insumo_id'), table_name='productos')
    op.drop_constraint(op.f('fk_productos_insumo_id_insumos'), 'productos', type_='foreignkey')
    op.drop_column('productos', 'cantidad_por_venta')
    op.drop_column('productos', 'insumo_id')
    op.drop_table('insumo_presentaciones')
    op.drop_constraint(op.f('fk_insumos_unidad_unidades_medida'), 'insumos', type_='foreignkey')
    op.execute("UPDATE insumos SET unidad = 'unidad' WHERE unidad NOT IN ('g', 'kg', 'ml', 'l', 'unidad')")
    op.create_check_constraint(op.f('ck_insumos_unidad'), 'insumos', "unidad IN ('g', 'kg', 'ml', 'l', 'unidad')")
    op.drop_table('unidades_medida')
