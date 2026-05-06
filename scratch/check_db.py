from app.database import SessionLocal
from app.models.submission import Submission
from app.models.user import User
from app.models.division import UserDivision, Division

db = SessionLocal()

print("--- Submissions ---")
for s in db.query(Submission).all():
    print(f"ID: {s.id}, Code: {s.submission_code}, Div: {s.division_id}, User: {s.user.username if s.user else 'N/A'}")

print("\n--- Users ---")
for u in db.query(User).all():
    print(f"ID: {u.id}, Username: {u.username}, Global Role: {u.role}")

print("\n--- User-Division Mappings ---")
for ud in db.query(UserDivision).all():
    div = db.query(Division).filter(Division.id == ud.division_id).first()
    user = db.query(User).filter(User.id == ud.user_id).first()
    print(f"User: {user.username if user else ud.user_id}, Div: {div.name if div else ud.division_id}, Role: {ud.role}")

db.close()
