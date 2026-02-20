"""
Quick diagnostic script to check model registration
"""
import sys
sys.path.insert(0, '/app')

print("=" * 60)
print("CHECKING MODEL REGISTRATION")
print("=" * 60)

# Step 1: Check Base import
try:
    from app.database import Base
    print("✓ Base imported from app.database")
except Exception as e:
    print(f"✗ Failed to import Base: {e}")
    sys.exit(1)

# Step 2: Import Lead model specifically
try:
    from app.models import Lead
    print(f"✓ Lead model imported")
    print(f"  - Table name: {Lead.__tablename__}")
    print(f"  - Has __table__: {hasattr(Lead, '__table__')}")
except Exception as e:
    print(f"✗ Failed to import Lead: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 3: Import LeadICPAssignment
try:
    from app.models import LeadICPAssignment
    print(f"✓ LeadICPAssignment model imported")
    print(f"  - Table name: {LeadICPAssignment.__tablename__}")
    print(f"  - Has __table__: {hasattr(LeadICPAssignment, '__table__')}")
except Exception as e:
    print(f"✗ Failed to import LeadICPAssignment: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 4: Check what tables are registered
print("\n" + "=" * 60)
print("REGISTERED TABLES IN BASE.METADATA")
print("=" * 60)
tables = list(Base.metadata.tables.keys())
print(f"Total tables: {len(tables)}")
for table in sorted(tables):
    print(f"  ✓ {table}")

# Step 5: Check if 'leads' is there
print("\n" + "=" * 60)
print("CRITICAL TABLE CHECK")
print("=" * 60)
if 'leads' in tables:
    print("✓ 'leads' table IS registered")
else:
    print("✗ 'leads' table NOT registered!")
    print("This is the problem!")

if 'lead_icp_assignments' in tables:
    print("✓ 'lead_icp_assignments' table IS registered")
else:
    print("✗ 'lead_icp_assignments' table NOT registered!")

# Step 6: Try to inspect the Lead table
print("\n" + "=" * 60)
print("LEAD TABLE INSPECTION")
print("=" * 60)
try:
    lead_table = Base.metadata.tables.get('leads')
    if lead_table:
        print(f"✓ Lead table found in metadata")
        print(f"  Columns: {list(lead_table.columns.keys())[:5]}...")
    else:
        print("✗ Lead table NOT in metadata!")
        print("Trying to access via Lead.__table__...")
        if hasattr(Lead, '__table__'):
            print(f"  Lead.__table__ exists: {Lead.__table__.name}")
        else:
            print("  Lead.__table__ does NOT exist!")
except Exception as e:
    print(f"✗ Error inspecting Lead table: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)