import asyncio
from app.services.email_verification_service import create_verification_service

async def test():
    print("🔍 Minimal Verifalia Test (Uses 2 credits)")
    print("=" * 60)
    
    service = create_verification_service()
    
    # Test 1: Valid email (1 credit)
    print("\n✅ Test 1: Valid Email")
    print("   Email: support@verifalia.com")
    print("   Testing... (this may take 10-30 seconds)")
    
    result1 = await service.verify_email("support@verifalia.com")
    
    print(f"\n   Status: {result1.status}")
    print(f"   Valid: {result1.is_valid}")
    print(f"   Confidence: {result1.confidence}%")
    print(f"   Cost: ${result1.cost:.4f}")
    
    if result1.details:
        print(f"   Classification: {result1.details.get('classification')}")
        print(f"   Is Disposable: {result1.details.get('is_disposable')}")
        print(f"   Is Role Account: {result1.details.get('is_role')}")
    
    # Test 2: Invalid email (1 credit)
    print("\n❌ Test 2: Invalid Email")
    print("   Email: fake123@nonexistentdomain99999.com")
    print("   Testing... (this may take 10-30 seconds)")
    
    result2 = await service.verify_email("fake123@nonexistentdomain99999.com")
    
    print(f"\n   Status: {result2.status}")
    print(f"   Valid: {result2.is_valid}")
    print(f"   Confidence: {result2.confidence}%")
    print(f"   Cost: ${result2.cost:.4f}")
    
    if result2.details:
        print(f"   Classification: {result2.details.get('classification')}")
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Summary:")
    print(f"   Total Credits Used: 2")
    print(f"   Total Cost: ${result1.cost + result2.cost:.4f}")
    print(f"   Valid Email Detected: {'✅' if result1.is_valid else '❌'}")
    print(f"   Invalid Email Detected: {'✅' if not result2.is_valid else '❌'}")
    
    # Verdict
    print("\n🎯 Verdict:")
    if result1.is_valid and not result2.is_valid:
        print("   ✅ Verifalia integration works correctly!")
        print("   Ready for production!")
    elif result1.status == "timeout" or result2.status == "timeout":
        print("   ⏱️  Timeout issue - may need to increase wait time")
    elif result1.error or result2.error:
        print("   ❌ API errors - check credentials")
    else:
        print("   ⚠️  Unexpected results - review output above")
    
    print("\n💰 Remaining Credits: ~23 (started with 25)")
    print("=" * 60)

asyncio.run(test())
