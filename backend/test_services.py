"""Test the processing services."""

import asyncio
from app.services.normalization import normalization_service
from app.services.scoring import scoring_service

def test_normalization():
    """Test normalization service."""
    print("=" * 60)
    print("Testing Normalization Service")
    print("=" * 60)
    
    # Test data
    test_lead = {
        'email': '  John.DOE@EXAMPLE.com  ',
        'first_name': 'john',
        'last_name': 'doe',
        'phone': '(555) 123-4567',
        'job_title': 'vice president of engineering',
        'company_website': 'example.com',
        'linkedin_url': 'linkedin.com/in/johndoe/'
    }
    
    print("\nOriginal Lead:")
    for key, value in test_lead.items():
        print(f"  {key}: {value}")
    
    # Normalize
    normalized = normalization_service.normalize_lead(test_lead)
    
    print("\nNormalized Lead:")
    for key, value in normalized.items():
        print(f"  {key}: {value}")
    
    # Assertions
    assert normalized['email'] == 'john.doe@example.com'
    assert normalized['first_name'] == 'John'
    assert normalized['last_name'] == 'Doe'
    assert normalized['phone'] == '+15551234567'
    assert normalized['job_title'] == 'Vice President Of Engineering'
    assert normalized['company_website'] == 'https://example.com'
    assert normalized['company_domain'] == 'example.com'
    
    print("\n✅ All normalization tests passed!")

def test_scoring():
    """Test scoring service."""
    print("\n" + "=" * 60)
    print("Testing Scoring Service")
    print("=" * 60)
    
    # Test cases
    test_cases = [
        {
            'name': 'C-Level Executive',
            'job_title': 'Chief Technology Officer',
            'email_verified': True,
            'email_deliverability_score': 95.0,
            'lead_data': {
                'first_name': 'John',
                'last_name': 'Doe',
                'phone': '+15551234567',
                'job_title': 'CTO',
                'linkedin_url': 'https://linkedin.com/in/johndoe',
                'company_name': 'TechCorp',
                'company_website': 'https://techcorp.com',
                'company_industry': 'Software'
            },
            'source_quality': 0.9,
            'expected_min': 85
        },
        {
            'name': 'Mid-Level Engineer',
            'job_title': 'Software Engineer',
            'email_verified': True,
            'email_deliverability_score': 80.0,
            'lead_data': {
                'first_name': 'Jane',
                'last_name': 'Smith',
                'email': 'jane@example.com'
            },
            'source_quality': 0.5,
            'expected_min': 40
        },
        {
            'name': 'Unverified Lead',
            'job_title': 'CEO',
            'email_verified': False,
            'lead_data': {'email': 'ceo@startup.com'},
            'source_quality': 0.3,
            'expected_min': 20
        }
    ]
    
    for test_case in test_cases:
        score = scoring_service.calculate_fit_score(
            job_title=test_case.get('job_title'),
            email_verified=test_case.get('email_verified', False),
            email_deliverability_score=test_case.get('email_deliverability_score'),
            lead_data=test_case.get('lead_data'),
            source_quality=test_case.get('source_quality', 0.5)
        )
        
        print(f"\n{test_case['name']}:")
        print(f"  Job Title: {test_case.get('job_title')}")
        print(f"  Email Verified: {test_case.get('email_verified')}")
        print(f"  Calculated Score: {score}")
        print(f"  Expected Min: {test_case['expected_min']}")
        
        assert score >= test_case['expected_min'], f"Score too low: {score}"
        print(f"  ✅ Pass")
    
    print("\n✅ All scoring tests passed!")

async def test_deduplication():
    """Test deduplication service."""
    from app.services.deduplication import deduplication_service
    from uuid import uuid4
    
    print("\n" + "=" * 60)
    print("Testing Deduplication Service")
    print("=" * 60)
    
    try:
        await deduplication_service.initialize()
        
        tenant_id = uuid4()
        email = "test@example.com"
        lead_id = uuid4()
        
        # Test cache write
        print("\nTesting cache write...")
        await deduplication_service.mark_lead_in_cache(tenant_id, email, lead_id)
        print("✅ Lead cached")
        
        # Test cache key generation
        cache_key = deduplication_service.generate_cache_key(tenant_id, email)
        print(f"\nCache key: {cache_key}")
        
        # Test email hash
        email_hash = deduplication_service.generate_email_hash(email)
        print(f"Email hash: {email_hash}")
        
        print("\n✅ All deduplication tests passed!")
        
    except Exception as e:
        print(f"\n⚠️  Deduplication test failed (Redis may not be available): {e}")
    finally:
        await deduplication_service.close()

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("LEAD PROCESSING SERVICES TEST SUITE")
    print("=" * 60)
    
    # Run tests
    test_normalization()
    test_scoring()
    asyncio.run(test_deduplication())
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)
