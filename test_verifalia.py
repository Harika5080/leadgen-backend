import asyncio
import os
from app.services.email_verification_service import create_verification_service

async def test():
    print("Testing Verifalia...")
    print(f"Username: {os.getenv('VERIFALIA_USERNAME')}")
    print(f"Password: {'SET' if os.getenv('VERIFALIA_PASSWORD') else 'NOT SET'}")
    
    service = create_verification_service()
    result = await service.verify_email("test@example.com")
    
    print(f"\nResult:")
    print(f"  Email: {result.email}")
    print(f"  Valid: {result.is_valid}")
    print(f"  Status: {result.status}")
    print(f"  Error: {result.error}")
    print(f"  Details: {result.details}")

asyncio.run(test())
