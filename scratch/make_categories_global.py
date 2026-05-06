from app.database import SessionLocal
from app.models.category import Category

db = SessionLocal()
print("Making all categories global...")
for c in db.query(Category).all():
    c.division_id = None
    print(f"Category {c.name} is now Global")
db.commit()
db.close()
