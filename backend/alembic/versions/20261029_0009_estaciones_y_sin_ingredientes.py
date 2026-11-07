"""estaciones de preparacion e ingredientes quitados

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-29 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('estaciones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=60), nullable=False),
    sa.Column('orden', sa.Integer(), server_default='0', nullable=False),
    sa.Column('activa', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_estaciones')),
    sa.UniqueConstraint('nombre', name=op.f('uq_estaciones_nombre'))
    )
    op.add_column('productos', sa.Column('estacion_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_productos_estacion_id'), 'productos', ['estacion_id'], unique=False)
    op.create_foreign_key(op.f('fk_productos_estacion_id_estaciones'), 'productos', 'estaciones', ['estacion_id'], ['id'], ondelete='SET NULL')
    op.add_column('comanda_items', sa.Column('estacion_id', sa.Integer(), nullable=True))
    op.add_column('comanda_items', sa.Column('sin_insumo_ids', sa.JSON(), server_default='[]', nullable=False))
    op.create_index(op.f('ix_comanda_items_estacion_id'), 'comanda_items', ['estacion_id'], unique=False)
    op.create_foreign_key(op.f('fk_comanda_items_estacion_id_estaciones'), 'comanda_items', 'estaciones', ['estacion_id'], ['id'], ondelete='SET NULL')
    op.add_column('receta_insumos', sa.Column('removible', sa.Boolean(), server_default='true', nullable=False))

    op.create_table('mensajes_comanda',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('comanda_id', sa.Integer(), nullable=False),
    sa.Column('autor', sa.Enum('cliente', 'personal', name='autormensaje', native_enum=False, length=20, create_constraint=True), nullable=False),
    sa.Column('autor_nombre', sa.String(length=120), nullable=True),
    sa.Column('texto', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['comanda_id'], ['comandas.id'], name=op.f('fk_mensajes_comanda_comanda_id_comandas'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_mensajes_comanda'))
    )
    op.create_index(op.f('ix_mensajes_comanda_comanda_id'), 'mensajes_comanda', ['comanda_id'], unique=False)

    # Estaciones iniciales; todo lo existente sigue yendo a Cocina
    op.execute("INSERT INTO estaciones (nombre, orden) VALUES ('Cocina', 0), ('Barra', 1)")
    op.execute("UPDATE productos SET estacion_id = (SELECT id FROM estaciones WHERE nombre = 'Cocina')")
    op.execute("UPDATE comanda_items SET estacion_id = (SELECT id FROM estaciones WHERE nombre = 'Cocina')")


def downgrade() -> None:
    op.drop_table('mensajes_comanda')
    op.drop_column('receta_insumos', 'removible')
    op.drop_constraint(op.f('fk_comanda_items_estacion_id_estaciones'), 'comanda_items', type_='foreignkey')
    op.drop_index(op.f('ix_comanda_items_estacion_id'), table_name='comanda_items')
    op.drop_column('comanda_items', 'sin_insumo_ids')
    op.drop_column('comanda_items', 'estacion_id')
    op.drop_constraint(op.f('fk_productos_estacion_id_estaciones'), 'productos', type_='foreignkey')
    op.drop_index(op.f('ix_productos_estacion_id'), table_name='productos')
    op.drop_column('productos', 'estacion_id')
    op.drop_table('estaciones')
