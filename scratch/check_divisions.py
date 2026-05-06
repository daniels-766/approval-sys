from app.database import SessionLocal
from app.models.division import Division

db = SessionLocal()
print("--- Divisions ---")
for d in db.query(Division).all():
    print(f"ID: {d.id}, Name: {d.name}")
db.close()
