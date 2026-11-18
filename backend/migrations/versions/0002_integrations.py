"""Add secure integration configuration and user add-ons."""
from alembic import op
import sqlalchemy as sa

revision = "0002_integrations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "integration_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provider_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("credentials_ciphertext", sa.Text(), nullable=False),
        sa.Column("options_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="configuration_required"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "user_addons",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("addon_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "addon_id"),
    )
    op.create_table(
        "integration_audit",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("actor_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("integration_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("integration_audit")
    op.drop_table("user_addons")
    op.drop_table("integration_configs")
