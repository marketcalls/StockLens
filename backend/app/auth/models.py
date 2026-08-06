"""Account tables and the role hierarchy."""

from __future__ import annotations

from enum import IntEnum

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

auth_metadata = MetaData()


class Role(IntEnum):
    """Strictly hierarchical: each level is a superset of the one below.

    Stored as an integer so a permission check is `user.role >= required`
    rather than a set membership test that has to be kept in step with the
    hierarchy. See docs/prd/04-roles-and-access.md.
    """

    PUBLIC = 0
    USER = 10
    ADMIN = 20
    SUPER_ADMIN = 30

    @classmethod
    def from_name(cls, name: str) -> Role:
        try:
            return cls[name.upper()]
        except KeyError as exc:
            raise ValueError(f"Unknown role: {name}") from exc

    @property
    def label(self) -> str:
        return self.name.lower()


app_user = Table(
    "app_user",
    auth_metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, nullable=False),
    Column("password_hash", String, nullable=False),
    Column("display_name", String),
    Column("role", Integer, nullable=False, server_default=str(int(Role.USER))),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    Column("email_verified", Boolean, nullable=False, server_default="0"),
    Column("created_at", String, nullable=False),
    Column("last_login_at", String),
    # SQLite compares TEXT case-sensitively, so store the address lowercased and
    # index it that way rather than relying on a collation.
    UniqueConstraint("email", name="uq_user_email"),
)


saved_screen = Table(
    "saved_screen",
    auth_metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
    Column("name", String, nullable=False),
    Column("description", String),
    Column("query", String, nullable=False),
    Column("columns", String),  # JSON list
    Column("is_public", Boolean, nullable=False, server_default="0"),
    Column("share_token", String),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Index("idx_screen_user", "user_id"),
    UniqueConstraint("user_id", "name", name="uq_screen_name_per_user"),
)


watchlist = Table(
    "watchlist",
    auth_metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
    Column("name", String, nullable=False),
    Column("created_at", String, nullable=False),
    Index("idx_watchlist_user", "user_id"),
    UniqueConstraint("user_id", "name", name="uq_watchlist_name_per_user"),
)


watchlist_item = Table(
    "watchlist_item",
    auth_metadata,
    Column(
        "watchlist_id", Integer, ForeignKey("watchlist.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("symbol", String, primary_key=True),
    Column("note", String),
    Column("added_at", String, nullable=False),
)


audit_log = Table(
    "audit_log",
    auth_metadata,
    Column("id", Integer, primary_key=True),
    Column("actor_id", Integer),
    Column("action", String, nullable=False),
    Column("target", String),
    Column("detail", String),
    Column("created_at", String, nullable=False),
    Index("idx_audit_created", "created_at"),
)


def create_auth(engine: object) -> None:
    auth_metadata.create_all(engine)  # type: ignore[arg-type]
