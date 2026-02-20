# backend/generate_service_token.py
"""
Generate a service token for the scraper service.

This token is used by Crawlee to authenticate with the backend API
when posting scraped results to /api/v1/scrapers/crawlee/batch

Usage:
    python generate_service_token.py
"""

import sys
import os
from datetime import timedelta

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.auth import create_access_token
from app.database import SessionLocal
from app.models import User, Tenant
import uuid


def generate_service_token():
    """Generate a long-lived service token"""
    
    print("🔐 Generating Service Token for Scraper...")
    print("-" * 50)
    
    # Option 1: Service-level token (no user required)
    print("\n📋 Option 1: Generic Service Token (Recommended)")
    print("   Use this if you want a simple token that works for all tenants")
    
    service_token = create_access_token(
        data={
            "sub": "scraper-service",
            "type": "service",
            "tenant_id": None  # Works for all tenants
        },
        expires_delta=timedelta(days=365)  # 1 year expiry
    )
    
    print(f"\n✅ Service Token Generated:")
    print(f"   {service_token}\n")
    print(f"📝 Add to .env file:")
    print(f"   SCRAPER_SERVICE_TOKEN={service_token}\n")
    
    # Option 2: User-based token
    print("\n📋 Option 2: User-Based Token (More Secure)")
    print("   Use this if you want tenant-specific tokens")
    
    db = SessionLocal()
    try:
        # Get first user (usually admin)
        user = db.query(User).first()
        
        if user:
            user_token = create_access_token(
                data={
                    "sub": user.email,
                    "user_id": str(user.id),
                    "tenant_id": str(user.tenant_id),
                    "type": "service"
                },
                expires_delta=timedelta(days=365)
            )
            
            print(f"\n✅ User Token Generated for: {user.email}")
            print(f"   Tenant: {user.tenant_id}")
            print(f"   {user_token}\n")
            print(f"📝 Add to .env file:")
            print(f"   SCRAPER_SERVICE_TOKEN={user_token}\n")
        else:
            print("\n⚠️  No users found in database")
            print("   Create a user first or use Option 1")
    
    finally:
        db.close()
    
    print("\n" + "=" * 50)
    print("🎯 Next Steps:")
    print("   1. Copy the token to backend/.env")
    print("   2. Restart the backend: docker-compose restart backend")
    print("   3. Token will be used by Crawlee to authenticate API calls")
    print("=" * 50)


if __name__ == "__main__":
    generate_service_token()