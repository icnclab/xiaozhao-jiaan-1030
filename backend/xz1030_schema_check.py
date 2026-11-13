from app.models import Base
from sqlalchemy import inspect

print("=== SERVICE RELATED TABLES ===")
for table in Base.metadata.sorted_tables:
    name = table.name.lower()
    if any(k in name for k in (
        "service", "template", "category",
        "form", "care", "respite"
    )):
        print(table.name)
        for col in table.columns:
            print("  ", col.name, str(col.type))

print("PASS: SERVICE_SCHEMA_INVENTORY")
print("DATABASE_UNCHANGED")
