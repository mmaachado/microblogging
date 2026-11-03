"""posts and media

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column(
            "body",
            sa.String(length=120),
            server_default="",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_posts_author_id", "posts", ["author_id"])
    op.create_index("ix_posts_created_at_id", "posts", ["created_at", "id"])
    op.create_index(
        "ix_posts_author_created_at_id",
        "posts",
        ["author_id", "created_at", "id"],
    )
    op.create_table(
        "media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=5), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("mime", sa.String(length=32), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_post_id", "media", ["post_id"])


def downgrade() -> None:
    op.drop_index("ix_media_post_id", table_name="media")
    op.drop_table("media")
    op.drop_index("ix_posts_author_created_at_id", table_name="posts")
    op.drop_index("ix_posts_created_at_id", table_name="posts")
    op.drop_index("ix_posts_author_id", table_name="posts")
    op.drop_table("posts")
