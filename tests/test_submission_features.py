import csv
import io
import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Category, Division, Submission, User
from app.services import submission_service


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def make_user(username, role="user"):
    return User(
        username=username,
        email=f"{username}@example.com",
        password_hash="hashed",
        full_name=username.title(),
        role=role,
    )


def seed_submission(db, username="alice", name="Laptop", nominal=Decimal("100.00")):
    user = make_user(username)
    admin = make_user("admin", role="admin")
    category = Category(name="IT")
    db.add_all([user, admin, category])
    db.commit()
    submission = submission_service.create_submission(
        db=db,
        user_id=user.id,
        name=name,
        purpose="Business need",
        nominal=nominal,
        category_id=category.id,
        attachments=[("a.pdf", "A.pdf"), ("b.pdf", "B.pdf")],
    )
    return user, admin, category, submission


class SubmissionFeatureTest(unittest.TestCase):
    def test_create_submission_saves_attachments_and_created_audit(self):
        db = make_session()
        _, _, _, submission = seed_submission(db)

        self.assertEqual(len(submission.attachments), 2)
        self.assertEqual(submission.attachments[0].original_name, "A.pdf")
        self.assertEqual(len(submission.audit_entries), 1)
        self.assertEqual(submission.audit_entries[0].action, "created")
        self.assertIsNone(submission.audit_entries[0].status_from)
        self.assertEqual(submission.audit_entries[0].status_to, "pending")

    def test_need_revision_updates_status_and_records_audit(self):
        db = make_session()
        _, admin, _, submission = seed_submission(db)

        updated = submission_service.request_revision_submission(
            db,
            submission.id,
            admin.id,
            "Please attach invoice",
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, "need_revision")
        self.assertEqual(updated.admin_notes, "Please attach invoice")
        self.assertEqual(len(updated.audit_entries), 2)
        self.assertEqual(updated.audit_entries[-1].action, "need_revision")
        self.assertEqual(updated.audit_entries[-1].status_from, "pending")
        self.assertEqual(updated.audit_entries[-1].status_to, "need_revision")

    def test_stats_include_need_revision(self):
        db = make_session()
        _, admin, _, submission = seed_submission(db)
        submission_service.request_revision_submission(db, submission.id, admin.id, "Fix")

        stats = submission_service.get_submission_stats(db)

        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["pending"], 0)
        self.assertEqual(stats["need_revision"], 1)

    def test_filtered_submissions_match_keyword_status_category_and_nominal(self):
        db = make_session()
        _, admin, category, first = seed_submission(
            db, username="alice", name="Laptop request", nominal=Decimal("1500.00")
        )
        submission_service.request_revision_submission(db, first.id, admin.id, "Fix")
        user = make_user("bob")
        other_category = Category(name="Travel")
        db.add_all([user, other_category])
        db.commit()
        submission_service.create_submission(
            db=db,
            user_id=user.id,
            name="Taxi",
            purpose="Client visit",
            nominal=Decimal("50.00"),
            category_id=other_category.id,
        )

        submissions = submission_service.get_all_submissions(
            db,
            status_filter="need_revision",
            keyword="laptop",
            category_id=category.id,
            min_nominal=Decimal("1000.00"),
            max_nominal=Decimal("2000.00"),
        )

        self.assertEqual([submission.id for submission in submissions], [first.id])

    def test_filtered_submissions_can_filter_by_user_division(self):
        db = make_session()
        alice = make_user("alice")
        bob = make_user("bob")
        category = Category(name="IT")
        finance = Division(name="Finance")
        operations = Division(name="Operations")
        finance.users = [alice]
        operations.users = [bob]
        db.add_all([category, finance, operations])
        db.commit()
        first = submission_service.create_submission(
            db=db,
            user_id=alice.id,
            name="Laptop",
            purpose="Business need",
            nominal=Decimal("1500.00"),
            category_id=category.id,
        )
        submission_service.create_submission(
            db=db,
            user_id=bob.id,
            name="Taxi",
            purpose="Client visit",
            nominal=Decimal("50.00"),
            category_id=category.id,
        )

        submissions = submission_service.get_all_submissions(
            db,
            division_id=finance.id,
        )

        self.assertEqual([submission.id for submission in submissions], [first.id])

    def test_export_submissions_csv_contains_filtered_rows(self):
        db = make_session()
        _, admin, _, submission = seed_submission(db)
        submission_service.approve_submission(db, submission.id, admin.id, "OK")

        csv_text = submission_service.export_submissions_csv(
            submission_service.get_all_submissions(db, status_filter="approved")
        )
        rows = list(csv.DictReader(io.StringIO(csv_text)))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["code"], submission.submission_code)
        self.assertEqual(rows[0]["status"], "approved")

    def test_revise_submission_updates_need_revision_submission_and_returns_to_pending(self):
        db = make_session()
        user, admin, category, submission = seed_submission(db)
        submission_service.request_revision_submission(db, submission.id, admin.id, "Fix it")

        updated = submission_service.revise_submission(
            db=db,
            submission_id=submission.id,
            user_id=user.id,
            name="Updated laptop",
            purpose="Updated business need",
            nominal=Decimal("2500.00"),
            category_id=category.id,
            attachments=[("invoice.pdf", "Invoice.pdf")],
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, "pending")
        self.assertEqual(updated.name, "Updated laptop")
        self.assertEqual(updated.purpose, "Updated business need")
        self.assertEqual(updated.nominal, Decimal("2500.00"))
        self.assertEqual(len(updated.attachments), 3)
        self.assertEqual(updated.attachments[-1].original_name, "Invoice.pdf")
        self.assertEqual(updated.audit_entries[-1].action, "revised")
        self.assertEqual(updated.audit_entries[-1].status_from, "need_revision")
        self.assertEqual(updated.audit_entries[-1].status_to, "pending")

    def test_revise_submission_rejects_non_owner_or_wrong_status(self):
        db = make_session()
        user, _, category, submission = seed_submission(db)
        other_user = make_user("mallory")
        db.add(other_user)
        db.commit()

        wrong_status = submission_service.revise_submission(
            db=db,
            submission_id=submission.id,
            user_id=user.id,
            name="Updated",
            purpose="Updated",
            nominal=Decimal("10.00"),
            category_id=category.id,
        )
        wrong_owner = submission_service.revise_submission(
            db=db,
            submission_id=submission.id,
            user_id=other_user.id,
            name="Updated",
            purpose="Updated",
            nominal=Decimal("10.00"),
            category_id=category.id,
        )

        self.assertIsNone(wrong_status)
        self.assertIsNone(wrong_owner)


if __name__ == "__main__":
    unittest.main()
