"""likes, reposts, bookmarks and quotes

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLES = ("likes", "reposts", "bookmarks")


def upgrade() -> None:
    for table in TABLES:
        op.create_table(
            table,
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("post_id", sa.Uuid(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), nullable=False
            ),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["post_id"], ["posts.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("user_id", "post_id"),
        )
        op.create_index(f"ix_{table}_post_id", table, ["post_id"])
    for table in ("reposts", "bookmarks"):
        op.create_index(
            f"ix_{table}_user_id_created_at",
            table,
            ["user_id", "created_at"],
        )
    with op.batch_alter_table("posts") as batch:
        batch.add_column(sa.Column("quote_of_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column(
                "is_quote",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch.create_foreign_key(
            "fk_posts_quote_of_id_posts",
            "posts",
            ["quote_of_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_posts_quote_of_id", ["quote_of_id"])


def downgrade() -> None:
    with op.batch_alter_table("posts") as batch:
        batch.drop_index("ix_posts_quote_of_id")
        batch.drop_constraint("fk_posts_quote_of_id_posts", type_="foreignkey")
        batch.drop_column("is_quote")
        batch.drop_column("quote_of_id")
    for table in ("reposts", "bookmarks"):
        op.drop_index(f"ix_{table}_user_id_created_at", table_name=table)
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_post_id", table_name=table)
        op.drop_table(table)
