import asyncio
from passlib.context import CryptContext
import sys
sys.path.insert(0, "/app")

from app.database import AsyncSessionLocal
from app.models import User, Tenant
from sqlalchemy import select

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_users():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Tenant).where(Tenant.name == "Test Tenant"))
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            print("ERROR: No tenant found")
            return
        
        print(f"Found tenant: {tenant.id}")
        
        result = await db.execute(select(User).where(User.email.in_(["admin@test.com", "reviewer@test.com"])))
        for user in result.scalars():
            await db.delete(user)
        await db.commit()
        
        admin = User(
            tenant_id=tenant.id,
            email="admin@test.com",
            password_hash=pwd_context.hash("AdminPassword123!"),
            full_name="Admin User",
            role="admin",
            is_active=True
        )
        db.add(admin)
        
        reviewer = User(
            tenant_id=tenant.id,
            email="reviewer@test.com",
            password_hash=pwd_context.hash("ReviewerPass123!"),
            full_name="Reviewer User",
            role="reviewer",
            is_active=True
        )
        db.add(reviewer)
        
        await db.commit()
        print("Users created successfully")

asyncio.run(create_users())
