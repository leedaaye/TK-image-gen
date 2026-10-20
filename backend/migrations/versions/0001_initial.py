"""Initial durable document, task and encrypted-setting storage."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('documents', sa.Column('id', sa.String(36), primary_key=True), sa.Column('kind', sa.String(24), nullable=False), sa.Column('data', sa.JSON(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_documents_kind', 'documents', ['kind'])
    op.create_table('tasks', sa.Column('id', sa.String(36), primary_key=True), sa.Column('project_id', sa.String(36), nullable=False), sa.Column('slide_id', sa.String(36), nullable=True), sa.Column('type', sa.String(16), nullable=False), sa.Column('status', sa.String(16), nullable=False), sa.Column('payload', sa.JSON(), nullable=False), sa.Column('error', sa.Text(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_tasks_project_id', 'tasks', ['project_id'])
    op.create_index('ix_tasks_status', 'tasks', ['status'])
    op.create_table('settings', sa.Column('key', sa.String(64), primary_key=True), sa.Column('value', sa.JSON(), nullable=False))


def downgrade():
    op.drop_table('settings')
    op.drop_table('tasks')
    op.drop_table('documents')
