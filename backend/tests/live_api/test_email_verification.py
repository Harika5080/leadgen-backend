# tests/live_api/test_email_verification.py
"""
Live Verifalia email verification tests

Get FREE account: https://verifalia.com/sign-up
Free tier: 25 verifications/day
Cost: ~$0.004-0.01 per email

Run with: pytest tests/live_api/test_email_verification.py -v -m live_api -s
"""

import pytest
import os

from app.services.email_verification_service import VerifaliaSer, create_verification_service


@pytest.mark.live_api
@pytest.mark.skipif(
    not os.getenv("VERIFALIA_USERNAME") or not os.getenv("VERIFALIA_PASSWORD"),
    reason="VERIFALIA_USERNAME and VERIFALIA_PASSWORD not set"
)
@pytest.mark.asyncio
async def test_verifalia_valid_email():
    """Test Verifalia with a known valid email (COSTS ~$0.005)"""
    
    service = create_verification_service()
    
    # Test with a well-known valid email
    result = await service.verify_email("support@verifalia.com")
    
    print(f"\n📧 Verifalia Results for support@verifalia.com:")
    print(f"   Valid: {result.is_valid}")
    print(f"   Status: {result.status}")
    print(f"   Confidence: {result.confidence}%")
    print(f"   Details:")
    for key, value in result.details.items():
        print(f"      {key}: {value}")
    
    # Assertions
    assert result.email == "support@verifalia.com"
    assert result.is_valid is True, f"Expected valid, got: {result.status}"
    assert result.status in ["Deliverable", "Risky"]
    assert result.confidence > 50.0
    
    print(f"\n✅ Verifalia verification works!")
    print(f"💰 Cost: ${result.cost:.4f}")


@pytest.mark.live_api
@pytest.mark.skipif(
    not os.getenv("VERIFALIA_USERNAME") or not os.getenv("VERIFALIA_PASSWORD"),
    reason="VERIFALIA_USERNAME and VERIFALIA_PASSWORD not set"
)
@pytest.mark.asyncio
async def test_verifalia_invalid_email():
    """Test Verifalia with an invalid email (COSTS ~$0.005)"""
    
    service = create_verification_service()
    
    # Test with obviously invalid email
    result = await service.verify_email("fake-email-that-does-not-exist@example.com")
    
    print(f"\n📧 Verifalia Results for fake email:")
    print(f"   Valid: {result.is_valid}")
    print(f"   Status: {result.status}")
    print(f"   Confidence: {result.confidence}%")
    print(f"   Details:")
    for key, value in result.details.items():
        print(f"      {key}: {value}")
    
    # Assertions
    assert result.is_valid is False or result.status == "Risky"
    
    print(f"\n✅ Invalid email detection works!")
    print(f"💰 Cost: ${result.cost:.4f}")


@pytest.mark.live_api
@pytest.mark.skipif(
    not os.getenv("VERIFALIA_USERNAME") or not os.getenv("VERIFALIA_PASSWORD"),
    reason="VERIFALIA_USERNAME and VERIFALIA_PASSWORD not set"
)
@pytest.mark.asyncio
async def test_verifalia_disposable_email():
    """Test Verifalia with a disposable email (COSTS ~$0.005)"""
    
    service = create_verification_service()
    
    # Test with disposable email service
    result = await service.verify_email("test@mailinator.com")
    
    print(f"\n📧 Verifalia Results for disposable email:")
    print(f"   Valid: {result.is_valid}")
    print(f"   Status: {result.status}")
    print(f"   Is Disposable: {result.details.get('is_disposable')}")
    print(f"   Confidence: {result.confidence}%")
    
    # Assertions
    assert result.details.get('is_disposable') is True, "Expected to detect disposable email"
    
    print(f"\n✅ Disposable email detection works!")
    print(f"💰 Cost: ${result.cost:.4f}")


@pytest.mark.live_api
@pytest.mark.skipif(
    not os.getenv("VERIFALIA_USERNAME") or not os.getenv("VERIFALIA_PASSWORD"),
    reason="VERIFALIA_USERNAME and VERIFALIA_PASSWORD not set"
)
@pytest.mark.asyncio
async def test_verifalia_syntax_error():
    """Test Verifalia with syntax error (COSTS ~$0.005)"""
    
    service = create_verification_service()
    
    # Test with malformed email
    result = await service.verify_email("not-an-email")
    
    print(f"\n📧 Verifalia Results for malformed email:")
    print(f"   Valid: {result.is_valid}")
    print(f"   Status: {result.status}")
    print(f"   Syntax Valid: {result.details.get('syntax_valid')}")
    
    # Assertions
    assert result.is_valid is False
    assert result.details.get('syntax_valid') is False
    
    print(f"\n✅ Syntax validation works!")
    print(f"💰 Cost: ${result.cost:.4f}")


@pytest.mark.live_api
@pytest.mark.skipif(
    not os.getenv("VERIFALIA_USERNAME") or not os.getenv("VERIFALIA_PASSWORD"),
    reason="VERIFALIA_USERNAME and VERIFALIA_PASSWORD not set"
)
@pytest.mark.asyncio
async def test_verifalia_batch_verification():
    """Test multiple emails to see cost and performance (COSTS ~$0.02)"""
    
    service = create_verification_service()
    
    test_emails = [
        "valid@gmail.com",
        "fake@nonexistent-domain-12345.com",
        "test@mailinator.com",
        "support@verifalia.com"
    ]
    
    results = []
    total_cost = 0.0
    
    print(f"\n📧 Batch Verification of {len(test_emails)} emails:")
    
    for email in test_emails:
        result = await service.verify_email(email)
        results.append(result)
        total_cost += result.cost
        
        print(f"\n   {email}:")
        print(f"      Valid: {result.is_valid}")
        print(f"      Status: {result.status}")
        print(f"      Confidence: {result.confidence}%")
    
    # Summary
    valid_count = sum(1 for r in results if r.is_valid)
    invalid_count = len(results) - valid_count
    
    print(f"\n📊 Summary:")
    print(f"   Total Emails: {len(results)}")
    print(f"   Valid: {valid_count}")
    print(f"   Invalid/Risky: {invalid_count}")
    print(f"   Total Cost: ${total_cost:.4f}")
    print(f"   Avg Cost: ${total_cost/len(results):.4f} per email")
    
    assert len(results) == len(test_emails)
    assert total_cost > 0.0
    
    print(f"\n✅ Batch verification works!")


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_verifalia_error_handling():
    """Test error handling with missing credentials (FREE)"""
    
    # Create service without credentials
    service = VerifaliaSer(username=None, password=None)
    
    result = await service.verify_email("test@example.com")
    
    print(f"\n🔧 Error Handling Test:")
    print(f"   Error: {result.error}")
    print(f"   Status: {result.status}")
    
    # Should handle gracefully
    assert result.is_valid is False
    assert result.status == "error"
    assert result.error is not None
    
    print("✅ Error handling works!")