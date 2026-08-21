"""Create and populate demo.db deterministically: 50 users x 5 posts."""

from app.main import Base, Post, User, engine
from sqlalchemy.orm import Session

USER_COUNT = 50
POSTS_PER_USER = 5


def main() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for user_index in range(1, USER_COUNT + 1):
            user = User(name=f"user-{user_index:03d}")
            user.posts = [
                Post(title=f"post-{user_index:03d}-{post_index}")
                for post_index in range(1, POSTS_PER_USER + 1)
            ]
            session.add(user)
        session.commit()
    print(f"seeded {USER_COUNT} users with {POSTS_PER_USER} posts each")


if __name__ == "__main__":
    main()
