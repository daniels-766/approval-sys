import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Division, User
from app.services import auth_service


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


class UserManagementTest(unittest.TestCase):
    def test_get_all_users_can_search_and_filter_role(self):
        db = make_session()
        auth_service.create_user(db, "alice", "alice@example.com", "secret123", "Alice User")
        auth_service.create_user(
            db, "admin", "admin@example.com", "secret123", "Admin User", role="admin"
        )

        users = auth_service.get_all_users(db, keyword="alice", role="user")

        self.assertEqual([user.username for user in users], ["alice"])

    def test_update_user_changes_profile_role_status_and_divisions(self):
        db = make_session()
        user = auth_service.create_user(
            db, "alice", "alice@example.com", "secret123", "Alice User"
        )
        finance = Division(name="Finance")
        operations = Division(name="Operations")
        db.add_all([finance, operations])
        db.commit()

        updated = auth_service.update_user(
            db,
            user.id,
            username="alice2",
            email="alice2@example.com",
            full_name="Alice Updated",
            role="admin",
            is_active=False,
            division_ids=[finance.id, operations.id],
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.username, "alice2")
        self.assertEqual(updated.email, "alice2@example.com")
        self.assertEqual(updated.full_name, "Alice Updated")
        self.assertEqual(updated.role, "admin")
        self.assertFalse(updated.is_active)
        self.assertEqual([division.name for division in updated.divisions], ["Finance", "Operations"])

    def test_reset_user_password_sets_new_password(self):
        db = make_session()
        user = auth_service.create_user(
            db, "alice", "alice@example.com", "secret123", "Alice User"
        )

        updated = auth_service.reset_user_password(db, user.id, "newsecret")

        self.assertIsNotNone(updated)
        self.assertTrue(auth_service.verify_password("newsecret", updated.password_hash))
        self.assertFalse(auth_service.verify_password("secret123", updated.password_hash))


if __name__ == "__main__":
    unittest.main()
