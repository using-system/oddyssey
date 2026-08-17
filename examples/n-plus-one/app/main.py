"""Demo FastAPI app with a deliberate N+1 query on GET /users.

The default implementation loads users, then lazily loads each user's
posts one query at a time — the classic N+1. Setting ODD_FIXED=1
switches to a single joined query. Both variants live here so the
before/after comparison stays reproducible.
"""

import os

from fastapi import FastAPI
from sqlalchemy import ForeignKey, create_engine, select
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    joinedload,
    mapped_column,
    relationship,
)

DB_URL = os.environ.get("ODD_DB_URL", "sqlite:///./demo.db")
FIXED = os.environ.get("ODD_FIXED") == "1"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list["Post"]] = relationship(back_populates="author")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    author: Mapped[User] = relationship(back_populates="posts")


engine = create_engine(DB_URL)
app = FastAPI(title="n-plus-one")


@app.get("/users")
def list_users() -> list[dict]:
    with Session(engine) as session:
        stmt = select(User)
        if FIXED:
            stmt = stmt.options(joinedload(User.posts))
        users = session.scalars(stmt).unique().all()
        return [
            {"id": user.id, "name": user.name, "posts": [post.title for post in user.posts]}
            for user in users
        ]
