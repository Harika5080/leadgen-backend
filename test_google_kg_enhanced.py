# test_google_kg_enhanced.py
import asyncio
from app.services.google_kg_service import create_google_kg_service

async def test():
    service = create_google_kg_service()
    
    print("Testing Google KG with Wikipedia fallback...\n")
    
    # Test with Shopify
    result = await service.enrich_company("Shopify", "shopify.com")
    
    print("=" * 80)
    print("📊 RESULTS")
    print("=" * 80)
    for key, value in result.items():
        if key == 'company_description':
            print(f"{key}: {value[:100]}...")
        else:
            print(f"{key}: {value}")
    
    if 'company_employee_count' in result:
        print(f"\n✅ SUCCESS: Employee count extracted: {result['company_employee_count']}")
    else:
        print(f"\n❌ FAILED: Employee count not extracted")

asyncio.run(test())