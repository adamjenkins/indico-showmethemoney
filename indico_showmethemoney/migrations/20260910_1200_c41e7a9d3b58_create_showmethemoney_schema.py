"""Create showmethemoney schema

Revision ID: c41e7a9d3b58
Revises:
Create Date: 2026-09-10 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.ddl import CreateSchema, DropSchema


# revision identifiers, used by Alembic.
revision = 'c41e7a9d3b58'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(CreateSchema('plugin_showmethemoney'))
    op.create_table(
        'gated_menu_entries',
        sa.Column('menu_entry_id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False, index=True),
        sa.ForeignKeyConstraint(['menu_entry_id'], ['events.menu_entries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['event_id'], ['events.events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('menu_entry_id'),
        schema='plugin_showmethemoney',
    )


def downgrade():
    op.drop_table('gated_menu_entries', schema='plugin_showmethemoney')
    op.execute(DropSchema('plugin_showmethemoney'))
