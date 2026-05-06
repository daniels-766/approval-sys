from app.database import SessionLocal
from app.models.submission import Submission
from app.models.category import Category
from app.models.division import Division, UserDivision
from app.models.user import User

db = SessionLocal()

# Fix Submissions
print("Fixing Submissions...")
for s in db.query(Submission).filter(Submission.division_id == None).all():
    if s.user and s.user.divisions:
        s.division_id = s.user.divisions[0].id
        print(f"Updated Submission {s.submission_code} to Division {s.division_id}")

# Fix Categories
print("\nFixing Categories...")
first_div = db.query(Division).first()
if first_div:
    for c in db.query(Category).filter(Category.division_id == None).all():
        c.division_id = first_div.id
        print(f"Updated Category {c.name} to Division {first_div.name}")

db.commit()
db.close()
print("\nDone!")
