import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from uuid import uuid4

from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.models import Tenant, ICP, RawLead

async def test():
    engine = create_engine("postgresql://leadgen:leadgen123@db:5432/leadgen_test")
    Session = sessionmaker(bind=engine)
    db = Session()
    
    db.execute(text("TRUNCATE TABLE lead_stage_activity, lead_rejection_tracking, lead_icp_assignments, leads, raw_leads, icps, tenants CASCADE"))
    db.commit()
    
    tenant = Tenant(id=uuid4(), name="Test", domain="test.com", api_key_hash="test123", status="active")
    db.add(tenant)
    db.commit()
    
    icp = ICP(
        id=uuid4(), tenant_id=tenant.id,
        name="E-commerce SaaS ICP",
        is_active=True,
        enrichment_enabled=True,
        enrichment_providers={"wappalyzer": True, "serpapi": True},
        verification_enabled=True,
        auto_approve_threshold=80.0,
        review_threshold=50.0,
        auto_reject_threshold=-1.0,
        
        scoring_rules={
            "criteria_pass_threshold": 60,
            "target_industries": ["E-commerce", "Software", "SaaS", "Technology"],
            "ideal_company_size_min": 100,
            "ideal_company_size_max": 10000,
            "target_seniority_levels": ["VP", "Director", "C-Level"],
            "job_title_keywords": ["VP Engineering", "CTO", "Engineering"],
            "target_geographies": ["Canada", "USA"],
            "company_type_keywords": ["B2B", "SaaS", "Platform", "E-commerce"]
        },
        
        # ✅ NO FILTERS - let scoring handle it
        filter_rules={},
        
        weight_config={
            "industry": 30,
            "tech_stack": 20,
            "seniority": 30,
            "geography": 10,
            "company_type": 10
        }
    )
    db.add(icp)
    db.commit()
    
    raw = RawLead(
        id=uuid4(), tenant_id=tenant.id,
        email="contact@shopify.com",
        first_name="Test", last_name="User",
        company_name="Shopify",
        company_domain="shopify.com",
        company_website="https://shopify.com",
        job_title="VP Engineering",
        source_name="test", scraper_type="manual",
        status="pending", processing_status="pending", processed_by_icps=[]
    )
    db.add(raw)
    db.commit()
    
    print("🚀 Testing WITHOUT hard filters (scoring only)...\n")
    
    orchestrator = PipelineOrchestrator(db)
    result = await orchestrator.process_raw_lead(raw, icp, f"test-{uuid4()}")
    
    print(f"\n📊 RESULTS:")
    if 'scoring' in result:
        scoring = result['scoring']
        print(f"   Final Score: {scoring.get('score')}%")
        print(f"   Confidence: {scoring.get('confidence')}%")
        print(f"   Passed Criteria: {scoring.get('passed_criteria', [])}")
        print(f"   Failed Criteria: {scoring.get('failed_criteria', [])}")
    
    if 'enrichment' in result:
        print(f"\n   Enrichment:")
        print(f"   - Cost: ${result['enrichment'].get('cost', 0):.4f}")
        print(f"   - Fields: {result['enrichment'].get('fields_added', [])}")
    
    if 'verification' in result:
        ver = result['verification']
        print(f"\n   Verification: {ver.get('status')} ({ver.get('confidence')}%)")
    
    print(f"\n💰 Total Cost: ${(result.get('enrichment', {}).get('cost', 0) + result.get('verification', {}).get('cost', 0)):.4f}")
    
    db.close()

asyncio.run(test())
