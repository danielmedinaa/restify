"""plugins instalados (manifiesto firmado, permisos aprobados, token)

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-21 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0017'
down_revision: Union[str, Sequence[str], None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'plugins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(length=40), nullable=False),
        sa.Column('nombre', sa.String(length=80), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('autor', sa.String(length=80), nullable=False),
        sa.Column('manifiesto', sa.Text(), nullable=False),
        sa.Column('firma', sa.Text(), nullable=True),
        sa.Column('huella', sa.String(length=64), nullable=False),
        sa.Column('firmado', sa.Boolean(), nullable=False),
        sa.Column('permisos_aprobados', sa.Text(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('token_prefijo', sa.String(length=12), nullable=False),
        sa.Column('activo', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('instalado_por_id', sa.Integer(), nullable=True),
        sa.Column('ultimo_uso', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['instalado_por_id'], ['usuarios.id'], name=op.f('fk_plugins_instalado_por_id_usuarios'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_plugins')),
        sa.UniqueConstraint('slug', name=op.f('uq_plugins_slug')),
        sa.UniqueConstraint('token_hash', name=op.f('uq_plugins_token_hash')),
    )


def downgrade() -> None:
    op.drop_table('plugins')
