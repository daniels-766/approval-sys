import asyncio
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.database import Base
from app.models import Category, User
from app.routes import user as user_routes


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def make_request(path: str, query_string: str = ""):
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": query_string.encode(),
        "session": {
            "user_id": 1,
            "role": "user",
            "full_name": "Alice User",
        },
    }
    return Request(scope)


class UserDashboardRouteTest(unittest.TestCase):
    def test_create_submission_page_redirects_to_dashboard_modal(self):
        db = make_session()
        request = make_request("/user/submission/create")

        response = asyncio.run(user_routes.create_submission_page(request, db))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/user/dashboard?open_create=1")

    def test_invalid_nominal_renders_unified_dashboard_with_modal_open(self):
        db = make_session()
        user = User(
            username="alice",
            email="alice@example.com",
            password_hash="hashed",
            full_name="Alice User",
            role="user",
        )
        category = Category(name="IT", is_active=True)
        db.add_all([user, category])
        db.commit()

        request = make_request("/user/submission/create")
        response = asyncio.run(
            user_routes.create_submission(
                request=request,
                name="Laptop Request",
                purpose="Need a new laptop",
                nominal="invalid-value",
                category_id=category.id,
                document=None,
                documents=[],
                db=db,
            )
        )

        self.assertEqual(response.template.name, "user/dashboard.html")
        self.assertEqual(response.context["error"], "Invalid nominal value")
        self.assertTrue(response.context["show_create_modal"])
        self.assertEqual(response.context["form_data"]["name"], "Laptop Request")
        self.assertEqual(response.context["form_data"]["category_id"], category.id)


if __name__ == "__main__":
    unittest.main()
