"""zonas, forma y tamano de mesa, union de mesas

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-29 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('zonas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sucursal_id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=60), nullable=False),
    sa.Column('orden', sa.Integer(), server_default='0', nullable=False),
    sa.Column('activa', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['sucursal_id'], ['sucursales.id'], name=op.f('fk_zonas_sucursal_id_sucursales'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_zonas')),
    sa.UniqueConstraint('sucursal_id', 'nombre', name=op.f('uq_zonas_sucursal_id'))
    )
    op.create_index(op.f('ix_zonas_sucursal_id'), 'zonas', ['sucursal_id'], unique=False)
    op.add_column('mesas', sa.Column('zona_id', sa.Integer(), nullable=True))
    op.add_column('mesas', sa.Column('forma', sa.Enum('cuadrada', 'redonda', 'rectangular', name='formamesa', native_enum=False, length=20, create_constraint=True), server_default='cuadrada', nullable=False))
    op.add_column('mesas', sa.Column('ancho', sa.Integer(), server_default='3', nullable=False))
    op.add_column('mesas', sa.Column('alto', sa.Integer(), server_default='2', nullable=False))
    op.add_column('mesas', sa.Column('unida_a_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_mesas_zona_id'), 'mesas', ['zona_id'], unique=False)
    op.create_index(op.f('ix_mesas_unida_a_id'), 'mesas', ['unida_a_id'], unique=False)
    op.create_foreign_key(op.f('fk_mesas_zona_id_zonas'), 'mesas', 'zonas', ['zona_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_mesas_unida_a_id_mesas'), 'mesas', 'mesas', ['unida_a_id'], ['id'], ondelete='SET NULL')

    # El plano pasa de 4 columnas a 12 (x3) y las filas se parten a la mitad (x2)
    op.execute("UPDATE mesas SET pos_x = pos_x * 3, pos_y = pos_y * 2 WHERE pos_x IS NOT NULL AND pos_y IS NOT NULL")
    # Una zona "Salón" por sucursal con mesas, y todas sus mesas dentro
    op.execute("INSERT INTO zonas (sucursal_id, nombre) SELECT DISTINCT sucursal_id, 'Salón' FROM mesas")
    op.execute("UPDATE mesas SET zona_id = (SELECT z.id FROM zonas z WHERE z.sucursal_id = mesas.sucursal_id AND z.nombre = 'Salón')")


def downgrade() -> None:
    op.execute("UPDATE mesas SET pos_x = pos_x / 3, pos_y = pos_y / 2 WHERE pos_x IS NOT NULL AND pos_y IS NOT NULL")
    op.drop_constraint(op.f('fk_mesas_unida_a_id_mesas'), 'mesas', type_='foreignkey')
    op.drop_constraint(op.f('fk_mesas_zona_id_zonas'), 'mesas', type_='foreignkey')
    op.drop_index(op.f('ix_mesas_unida_a_id'), table_name='mesas')
    op.drop_index(op.f('ix_mesas_zona_id'), table_name='mesas')
    for c in ('unida_a_id', 'alto', 'ancho', 'forma', 'zona_id'):
        op.drop_column('mesas', c)
    op.drop_index(op.f('ix_zonas_sucursal_id'), table_name='zonas')
    op.drop_table('zonas')
