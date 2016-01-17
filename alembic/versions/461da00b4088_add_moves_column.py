"""add moves column

Revision ID: 461da00b4088
Revises: 960e5e3b4593
Create Date: 2016-01-16 16:18:08.569991

"""

# revision identifiers, used by Alembic.
revision = '461da00b4088'
down_revision = '960e5e3b4593'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('games', sa.Column('moves', sa.String(), nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('games', 'moves')
    ### end Alembic commands ###