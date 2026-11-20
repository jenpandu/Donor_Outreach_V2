"""add agent triage columns to messages

Revision ID: c4e1a9d2f7b3
Revises: 6bb6c53d7a2b
Create Date: 2026-11-19 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4e1a9d2f7b3'
down_revision = '6bb6c53d7a2b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('intent', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('sentiment', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('draft_reply', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('status', sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('status')
        batch_op.drop_column('draft_reply')
        batch_op.drop_column('sentiment')
        batch_op.drop_column('intent')
