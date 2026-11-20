"""caja automática: característica de plan y ajuste por suscripción

Revision ID: b8d4e0a2c5f1
Revises: a7c3d9e1f2b4
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8d4e0a2c5f1'
down_revision = 'a7c3d9e1f2b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('planes') as b:
        b.add_column(sa.Column('kiosko', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('suscripciones') as b:
        b.add_column(sa.Column('ajuste_kiosko', sa.Boolean(), nullable=True))
    op.execute("UPDATE planes SET kiosko = true WHERE nombre = 'Premium'")


def downgrade():
    with op.batch_alter_table('suscripciones') as b:
        b.drop_column('ajuste_kiosko')
    with op.batch_alter_table('planes') as b:
        b.drop_column('kiosko')
