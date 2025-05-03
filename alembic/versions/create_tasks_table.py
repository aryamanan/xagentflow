"""create tasks table

Revision ID: create_tasks_table
Revises: 
Create Date: 2024-05-03 21:36:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from app.models.task import TaskType, TaskStatus

# revision identifiers, used by Alembic.
revision = 'create_tasks_table'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create enum types
    op.execute("CREATE TYPE tasktype AS ENUM ('RESEARCH', 'STRATEGY_DEV', 'BACKTEST')")
    op.execute("CREATE TYPE taskstatus AS ENUM ('planning', 'pending_approval', 'in_progress', 'completed', 'failed', 'rejected')")
    
    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('task_type', sa.Enum('RESEARCH', 'STRATEGY_DEV', 'BACKTEST', name='tasktype'), nullable=False),
        sa.Column('status', sa.Enum('planning', 'pending_approval', 'in_progress', 'completed', 'failed', 'rejected', name='taskstatus'), nullable=False, server_default='planning'),
        sa.Column('input_data', sa.JSON(), nullable=True),
        sa.Column('output_data', sa.JSON(), nullable=True),
        sa.Column('plan', sa.JSON(), nullable=True),
        sa.Column('error_details', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add trigger for updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    
    op.execute("""
        CREATE TRIGGER update_tasks_updated_at
            BEFORE UPDATE ON tasks
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

def downgrade():
    op.drop_table('tasks')
    op.execute("DROP TYPE tasktype")
    op.execute("DROP TYPE taskstatus")
    op.execute("DROP FUNCTION update_updated_at_column()") 