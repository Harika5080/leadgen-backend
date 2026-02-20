# test_complete_pipeline.py
"""
Complete Pipeline Test with Smart Enrichment Strategy
"""

import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from uuid import uuid4

from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.models import Tenant, ICP, RawLead

async def test():
    print("=" * 80)
    print("🚀 TESTING COMPLETE PIPELINE WITH SMART ENRICHMENT")
    print("=" * 80)
    print()
    
    # Setup database
    engine = create_engine("postgresql://leadgen:leadgen123@db:5432/leadgen_test")
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Clean slate
    print("🧹 Cleaning database...")
    db.execute(text("TRUNCATE TABLE lead_stage_activity, lead_rejection_tracking, lead_icp_assignments, leads, raw_leads, icps, tenants CASCADE"))
    db.commit()
    print("✅ Database cleaned\n")
    
    # Create tenant
    tenant = Tenant(
        id=uuid4(), 
        name="Test Co", 
        domain="test.com", 
        api_key_hash="test123", 
        status="active"
    )
    db.add(tenant)
    db.commit()
    print(f"✅ Created tenant: {tenant.name}\n")
    
    # Create ICP with comprehensive criteria
    icp = ICP(
        id=uuid4(), 
        tenant_id=tenant.id,
        name="E-commerce SaaS Companies",
        is_active=True,
        
        # ✅ Enable enrichment
        enrichment_enabled=True,
        enrichment_providers={"wappalyzer": True, "serpapi": True},
        
        # ✅ Enable verification
        verification_enabled=True,
        
        # Thresholds
        auto_approve_threshold=80.0,
        review_threshold=50.0,
        auto_reject_threshold=-1.0,  # Disabled for testing
        
        # ✅ Scoring rules (NO hardcoded values!)
        scoring_rules={
            "criteria_pass_threshold": 60,
            "target_industries": ["E-commerce", "Software", "SaaS", "Technology"],
            "ideal_company_size_min": 100,
            "ideal_company_size_max": 10000,
            "target_seniority_levels": ["VP", "Director", "C-Level"],
            "job_title_keywords": ["VP Engineering", "CTO", "Engineering"],
            "target_geographies": ["Canada", "USA"],
            "company_type_keywords": ["B2B", "SaaS", "Platform", "E-commerce"],
            "preferred_technologies": ["React", "Python", "Ruby"]
        },
        
        # ✅ NO filter_rules (let scoring handle everything)
        filter_rules={},
        
        # ✅ Weights
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
    print(f"✅ Created ICP: {icp.name}")
    print(f"   - Enrichment: Enabled")
    print(f"   - Verification: Enabled")
    print(f"   - Target Industries: {icp.scoring_rules['target_industries']}")
    print(f"   - Target Geographies: {icp.scoring_rules['target_geographies']}\n")
    
    # Create raw lead from SCRAPER (not Apollo - needs enrichment!)
    raw = RawLead(
        id=uuid4(), 
        tenant_id=tenant.id,
        
        # Contact info
        email="contact@shopify.com",
        first_name="Test",
        last_name="User",
        job_title="VP Engineering",
        
        # Company info (minimal - needs enrichment)
        company_name="Shopify",
        company_domain="shopify.com",
        company_website="https://shopify.com",
        
        # ✅ Source tracking (FIXED - removed source_type)
        source_name="linkedin_scraper",
        scraper_type="manual",  # crawlee, puppeteer, api, csv, manual
        
        # Status
        status="pending",
        processing_status="pending",
        processed_by_icps=[],
        scraped_data={}
    )
    db.add(raw)
    db.commit()
    
    print(f"✅ Created raw lead:")
    print(f"   - Email: {raw.email}")
    print(f"   - Company: {raw.company_name}")
    print(f"   - Title: {raw.job_title}")
    print(f"   - Source: {raw.source_name}")
    print(f"   - Scraper Type: {raw.scraper_type}")
    print(f"   - Domain: {raw.company_domain}")
    print()
    
    print("=" * 80)
    print("🔄 PROCESSING THROUGH PIPELINE")
    print("=" * 80)
    print()
    
    # Process through pipeline
    orchestrator = PipelineOrchestrator(db)
    result = await orchestrator.process_raw_lead(
        raw_lead=raw, 
        icp=icp, 
        job_id=f"test-{uuid4()}"
    )
    
    print("\n" + "=" * 80)
    print("📊 FINAL RESULTS")
    print("=" * 80)
    
    # Overall result
    print(f"\n✅ Success: {result.get('success')}")
    print(f"📋 Lead ID: {result.get('lead_id')}")
    print(f"🎯 Assignment ID: {result.get('assignment_id')}")
    print(f"📊 Status: {result.get('status')}")
    print(f"⏱️  Processing Time: {result.get('processing_time_seconds', 0):.2f}s")
    
    # Enrichment results
    if 'enrichment' in result:
        enrich = result['enrichment']
        print(f"\n{'='*80}")
        print("🔍 ENRICHMENT DETAILS")
        print('='*80)
        
        if enrich.get('skipped'):
            print(f"⏭️  Status: SKIPPED")
            print(f"   Reason: {enrich.get('reason')}")
            print(f"   Cost: $0.00")
        else:
            print(f"✅ Status: COMPLETED")
            print(f"   Success: {enrich.get('success')}")
            print(f"   Providers Used: {', '.join(enrich.get('providers_used', []))}")
            print(f"   Fields Added: {len(enrich.get('fields_added', []))}")
            print(f"   Cost: ${enrich.get('cost', 0):.4f}")
            print(f"\n   📝 Fields Enriched:")
            for field in enrich.get('fields_added', []):
                print(f"      • {field}")
    
    # Scoring results
    if 'scoring' in result:
        score = result['scoring']
        print(f"\n{'='*80}")
        print("📊 SCORING DETAILS")
        print('='*80)
        print(f"   Score: {score.get('score')}%")
        print(f"   Confidence: {score.get('confidence')}%")
        print(f"   Rejected: {score.get('rejected', False)}")
        
        # Check if we have breakdown in Lead object
        if result.get('lead_id'):
            from app.models import Lead
            lead = db.query(Lead).filter(Lead.id == result['lead_id']).first()
            if lead:
                print(f"\n   📋 Lead Data After Enrichment:")
                print(f"      • Company Industry: {lead.company_industry or 'N/A'}")
                print(f"      • Company Description: {lead.company_description[:50] + '...' if lead.company_description else 'N/A'}")
                print(f"      • Company Employee Count: {lead.company_employee_count or 'N/A'}")
                print(f"      • Country: {lead.country or 'N/A'}")
                print(f"      • Job Title: {lead.job_title or 'N/A'}")
                if lead.enrichment_data and 'tech_stack' in lead.enrichment_data:
                    print(f"      • Tech Stack: {', '.join(lead.enrichment_data['tech_stack'][:3])}")
    
    # Verification results
    if 'verification' in result:
        verify = result['verification']
        print(f"\n{'='*80}")
        print("📧 VERIFICATION DETAILS")
        print('='*80)
        print(f"   Status: {verify.get('status')}")
        print(f"   Verified: {verify.get('verified')}")
        print(f"   Confidence: {verify.get('confidence')}%")
        print(f"   Passes Completed: {verify.get('passes_completed')}/3")
        print(f"   Cost: ${verify.get('cost', 0):.4f}")
        
        if 'field_scores' in verify:
            scores = verify['field_scores']
            print(f"\n   📊 Field Scores:")
            print(f"      • Syntax: {scores.get('syntax')}%")
            print(f"      • Domain: {scores.get('domain')}%")
            print(f"      • Mailbox: {scores.get('mailbox')}%")
            print(f"      • Deliverability: {scores.get('deliverability')}%")
        
        if 'metadata' in verify:
            meta = verify['metadata']
            print(f"\n   ℹ️  Metadata:")
            print(f"      • Disposable: {meta.get('is_disposable')}")
            print(f"      • Role Account: {meta.get('is_role')}")
            print(f"      • Free Provider: {meta.get('is_free')}")
            print(f"      • Catch-All: {meta.get('is_catch_all')}")
    
    # Qualification results
    if 'qualification' in result:
        qual = result['qualification']
        print(f"\n{'='*80}")
        print("🎯 QUALIFICATION DETAILS")
        print('='*80)
        print(f"   Decision: {qual.get('decision').upper()}")
        print(f"   Reason: {qual.get('reason')}")
        print(f"   Score: {qual.get('score')}%")
    
    # Cost summary
    print(f"\n{'='*80}")
    print("💰 COST BREAKDOWN")
    print('='*80)
    enrich_cost = result.get('enrichment', {}).get('cost', 0)
    verify_cost = result.get('verification', {}).get('cost', 0)
    total_cost = enrich_cost + verify_cost
    
    print(f"   Enrichment: ${enrich_cost:.4f}")
    print(f"   Verification: ${verify_cost:.4f}")
    print(f"   {'─'*50}")
    print(f"   TOTAL: ${total_cost:.4f}")
    
    print(f"\n{'='*80}")
    print("✅ TEST COMPLETE")
    print('='*80)
    
    db.close()

if __name__ == "__main__":
    asyncio.run(test())