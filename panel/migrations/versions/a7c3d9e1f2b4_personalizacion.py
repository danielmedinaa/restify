"""personalización: característica de plan y ajuste por suscripción

Revision ID: a7c3d9e1f2b4
Revises: 1e136540566e
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7c3d9e1f2b4'
down_revision = '1e136540566e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('planes') as b:
        b.add_column(sa.Column('personalizacion', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('suscripciones') as b:
        b.add_column(sa.Column('ajuste_personalizacion', sa.Boolean(), nullable=True))
    # El plan más caro (Premium) ya la incluye
    op.execute("UPDATE planes SET personalizacion = true WHERE nombre = 'Premium'")


def downgrade():
    with op.batch_alter_table('suscripciones') as b:
        b.drop_column('ajuste_personalizacion')
    with op.batch_alter_table('planes') as b:
        b.drop_column('personalizacion')
