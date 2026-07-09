"""organization hierarchy and admin enhancements

Revision ID: 0002_org_hierarchy_and_admin_enhancements
Revises: 0001_initial_schema
Create Date: 2026-07-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_org_hierarchy_and_admin_enhancements"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


designation_scope = sa.Enum(
    "SYSTEM_ADMINISTRATOR",
    "OPERATING_HEAD",
    "DIVISION_HEAD",
    "DEPARTMENT_HEAD",
    "TEAM_MEMBER",
    name="designation_scope",
)


def upgrade() -> None:
    designation_scope.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "divisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_divisions_name", "divisions", ["name"], unique=True)

    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("division_id", sa.Integer(), sa.ForeignKey("divisions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_departments_name", "departments", ["name"], unique=False)
    op.create_index("ix_departments_division_id", "departments", ["division_id"], unique=False)

    op.create_table(
        "designations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scope_level", designation_scope, nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_designations_name", "designations", ["name"], unique=True)
    op.create_index("ix_designations_scope_level", "designations", ["scope_level"], unique=False)

    op.add_column("teams", sa.Column("department_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("designation_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("department_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("division_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("reports_to_user_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("manager_chain", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("is_protected", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_index("ix_users_designation_id", "users", ["designation_id"], unique=False)
    op.create_index("ix_users_department_id", "users", ["department_id"], unique=False)
    op.create_index("ix_users_division_id", "users", ["division_id"], unique=False)
    op.create_index("ix_users_reports_to_user_id", "users", ["reports_to_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_reports_to_user_id", table_name="users")
    op.drop_index("ix_users_division_id", table_name="users")
    op.drop_index("ix_users_department_id", table_name="users")
    op.drop_index("ix_users_designation_id", table_name="users")

    op.drop_column("users", "is_protected")
    op.drop_column("users", "manager_chain")
    op.drop_column("users", "reports_to_user_id")
    op.drop_column("users", "division_id")
    op.drop_column("users", "department_id")
    op.drop_column("users", "designation_id")
    op.drop_column("teams", "department_id")

    op.drop_index("ix_designations_scope_level", table_name="designations")
    op.drop_index("ix_designations_name", table_name="designations")
    op.drop_table("designations")

    op.drop_index("ix_departments_division_id", table_name="departments")
    op.drop_index("ix_departments_name", table_name="departments")
    op.drop_table("departments")

    op.drop_index("ix_divisions_name", table_name="divisions")
    op.drop_table("divisions")
    designation_scope.drop(op.get_bind(), checkfirst=True)
