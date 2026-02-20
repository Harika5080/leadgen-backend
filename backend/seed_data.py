"""Seed database with test data - Async version."""

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4
import random

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.config import settings
from app.models import Lead, User, Tenant


async def seed_leads():
    """Seed test leads."""
    
    # Create async engine
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as db:
        print("🌱 Seeding database with test data...")
        
        # Get existing tenant
        result = await db.execute(select(Tenant).where(Tenant.status == "active"))
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            print("❌ No active tenant found. Run init_db.py first!")
            return
        
        tenant_id = tenant.id
        print(f"✅ Using tenant: {tenant.name} ({tenant_id})")
        
        # Check if leads already exist
        result = await db.execute(select(Lead).where(Lead.tenant_id == tenant_id))
        existing_leads = result.scalars().all()
        
        if len(existing_leads) > 0:
            print(f"⚠️  Found {len(existing_leads)} existing leads")
            print("Continuing will add MORE leads (not replace)...")
            response = input("Continue? (y/N): ")
            if response.lower() != 'y':
                print("❌ Cancelled. Exiting...")
                return
        
        # Sample data
        companies = [
            {"name": "TechCorp", "website": "techcorp.com", "industry": "Technology"},
            {"name": "DataMinds", "website": "dataminds.io", "industry": "Data Analytics"},
            {"name": "CloudServe", "website": "cloudserve.com", "industry": "Cloud Services"},
            {"name": "AI Innovations", "website": "aiinnovations.ai", "industry": "Artificial Intelligence"},
            {"name": "CyberSafe", "website": "cybersafe.net", "industry": "Cybersecurity"},
            {"name": "DevOps Pro", "website": "devopspro.com", "industry": "DevOps"},
            {"name": "Analytics Plus", "website": "analyticsplus.com", "industry": "Business Intelligence"},
            {"name": "Code Masters", "website": "codemasters.dev", "industry": "Software Development"},
        ]
        
        job_titles = [
            "CEO", "CTO", "VP of Engineering", "Head of Product",
            "Engineering Manager", "Senior Developer", "Data Scientist",
            "Product Manager", "DevOps Engineer", "Solution Architect"
        ]
        
        first_names = [
            "John", "Sarah", "Michael", "Emily", "David", "Jessica",
            "Robert", "Lisa", "James", "Jennifer", "William", "Linda"
        ]
        
        last_names = [
            "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
            "Miller", "Davis", "Rodriguez", "Martinez", "Wilson", "Anderson"
        ]
        
        sources = ["LinkedIn", "Conference", "Website", "Referral", "Cold Outreach"]
        statuses = ["new", "enriched", "verified", "pending_review", "approved", "rejected"]
        
        # Create 50 test leads
        leads_created = 0
        
        for i in range(50):
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            company = random.choice(companies)
            
            # Create unique email
            email = f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 999)}@{company['website']}"
            
            # Random dates in the last 30 days
            days_ago = random.randint(0, 30)
            created_at = datetime.utcnow() - timedelta(days=days_ago)
            
            # Status distribution: more new/pending, fewer rejected
            status_weights = [0.3, 0.2, 0.15, 0.25, 0.05, 0.05]
            status = random.choices(statuses, weights=status_weights)[0]
            
            # Review decision for reviewed leads
            review_decision = None
            reviewed_at = None
            if status in ["approved", "rejected"]:
                review_decision = status
                reviewed_at = created_at + timedelta(hours=random.randint(1, 48))
            
            lead = Lead(
                id=uuid4(),
                tenant_id=tenant_id,
                email=email,
                first_name=first_name,
                last_name=last_name,
                phone=f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
                job_title=random.choice(job_titles),
                linkedin_url=f"https://linkedin.com/in/{first_name.lower()}-{last_name.lower()}",
                company_name=company["name"],
                company_website=company["website"],
                company_domain=company["website"],
                company_industry=company["industry"],
                status=status,
                fit_score=round(random.uniform(0.60, 0.95), 2) if status != "new" else None,
                email_verified=status in ["verified", "approved"],
                email_deliverability_score=round(random.uniform(0.80, 1.00), 2) if status != "new" else None,
                reviewed_at=reviewed_at,
                reviewed_by="admin@test.com" if reviewed_at else None,
                review_decision=review_decision,
                review_notes=f"Good fit for {company['industry']}" if review_decision == "approved" else None,
                source_name=random.choice(sources),
                acquisition_timestamp=created_at,
                created_at=created_at,
                updated_at=created_at
            )
            
            db.add(lead)
            leads_created += 1
            
            if (i + 1) % 10 == 0:
                print(f"  Created {i + 1} leads...")
        
        await db.commit()
        
        print(f"\n✅ Successfully created {leads_created} test leads!")
        
        # Print summary
        print("\n📊 Summary by status:")
        for status in statuses:
            result = await db.execute(
                select(Lead).where(Lead.tenant_id == tenant_id, Lead.status == status)
            )
            leads = result.scalars().all()
            count = len(leads)
            print(f"  {status:20} {count:3} leads")
        
        print("\n🎉 Database seeded successfully!")


if __name__ == "__main__":
    asyncio.run(seed_leads())