"""Setup test data using the application's own functions."""
import asyncio
from app.database import AsyncSessionLocal
from app.models import Tenant, User
from app.auth import hash_password, hash_api_key
from sqlalchemy import select, delete

async def setup_test_data():
    """Create test tenant and users."""
    async with AsyncSessionLocal() as session:
        print("Setting up test data...")
        
        # Clean up existing test data
        await session.execute(
            delete(User).where(User.email.in_(['admin@test.com', 'reviewer@test.com']))
        )
        await session.execute(
            delete(Tenant).where(Tenant.name == 'Test Tenant')
        )
        await session.commit()
        print("✓ Cleaned up existing test data")
        
        # Create tenant with API key
        api_key = "sk_live_test_key_12345"
        tenant = Tenant(
            name="Test Tenant",
            api_key_hash=hash_api_key(api_key),
            status="active",
            settings={},
            branding={}
        )
        session.add(tenant)
        await session.flush()  # Get the tenant ID
        print(f"✓ Created tenant: {tenant.name} (ID: {tenant.id})")
        
        # Create admin user
        admin = User(
            tenant_id=tenant.id,
            email="admin@test.com",
            password_hash=hash_password("AdminPassword123!"),
            full_name="Admin User",
            role="admin",
            is_active=True
        )
        session.add(admin)
        print(f"✓ Created admin user: {admin.email}")
        
        # Create reviewer user
        reviewer = User(
            tenant_id=tenant.id,
            email="reviewer@test.com",
            password_hash=hash_password("ReviewerPass123!"),
            full_name="Reviewer User",
            role="reviewer",
            is_active=True
        )
        session.add(reviewer)
        print(f"✓ Created reviewer user: {reviewer.email}")
        
        # Commit all changes
        await session.commit()
        
        print("\n" + "="*50)
        print("Test Data Created Successfully!")
        print("="*50)
        print("\nCredentials:")
        print(f"  API Key: {api_key}")
        print(f"  Admin Email: {admin.email}")
        print(f"  Admin Password: AdminPassword123!")
        print(f"  Reviewer Email: {reviewer.email}")
        print(f"  Reviewer Password: ReviewerPass123!")
        print("\nTenant ID:", tenant.id)
        print("="*50)

if __name__ == "__main__":
    asyncio.run(setup_test_data())
