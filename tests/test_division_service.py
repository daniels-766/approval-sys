import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Division, User
from app.services import division_service


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def make_user(username):
    return User(
        username=username,
        email=f"{username}@example.com",
        password_hash="hashed",
        full_name=username.title(),
        role="user",
    )


class DivisionServiceTest(unittest.TestCase):
    def test_assign_users_to_division_replaces_existing_users(self):
        db = make_session()
        division = Division(name="Finance")
        alice = make_user("alice")
        bob = make_user("bob")
        cindy = make_user("cindy")
        division.users = [alice]
        db.add_all([division, bob, cindy])
        db.commit()

        updated = division_service.assign_users_to_division(
            db,
            division.id,
            [bob.id, cindy.id],
        )

        self.assertIsNotNone(updated)
        self.assertEqual(
            [user.username for user in updated.users],
            ["bob", "cindy"],
        )

    def test_assign_users_to_division_can_clear_all_users(self):
        db = make_session()
        division = Division(name="Operations")
        alice = make_user("alice")
        division.users = [alice]
        db.add(division)
        db.commit()

        updated = division_service.assign_users_to_division(db, division.id, [])

        self.assertIsNotNone(updated)
        self.assertEqual(updated.users, [])

    def test_assign_users_to_division_returns_none_for_missing_division(self):
        db = make_session()
        alice = make_user("alice")
        db.add(alice)
        db.commit()

        updated = division_service.assign_users_to_division(db, 999, [alice.id])

        self.assertIsNone(updated)


if __name__ == "__main__":
    unittest.main()
