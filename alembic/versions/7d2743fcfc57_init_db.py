"""init_db

Revision ID: 7d2743fcfc57
Revises: 
Create Date: 2022-10-18 16:20:09.050024

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '7d2743fcfc57'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('vidaq',
                    sa.Column('id', sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
                    sa.Column('chunks', sa.Integer(), nullable=False),
                    sa.Column('hash', UUID(), nullable=False),
                    sa.Column('original_name', sa.String(), nullable=False),
                    )


def downgrade() -> None:
    op.drop_table('vidaq')
