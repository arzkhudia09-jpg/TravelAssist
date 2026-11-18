"""Create travel assistance core tables."""
from alembic import op
from app.db import Base
from app import models

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    later_tables = {"integration_configs", "user_addons", "integration_audit"}
    tables = [table for table in Base.metadata.sorted_tables if table.name not in later_tables]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables)

def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
