from app.database import SessionLocal
from app.models.category import Category
from app.models.division import Division

db = SessionLocal()

print("--- Categories ---")
for c in db.query(Category).all():
    div = db.query(Division).filter(Division.id == c.division_id).first()
    print(f"ID: {c.id}, Name: {c.name}, Div: {div.name if div else 'None'} ({c.division_id})")

db.close()
