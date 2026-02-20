"""
COMPLETE END-TO-END PIPELINE TEST
Tests: Scoring → Enrichment (SerpApi) → 3-Pass Verification → Qualification

Cost: ~$0.007 per lead
- SerpApi: $0.002
- Verifalia: $0.005
"""

import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from uuid import uuid4
from datetime import datetime

from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.models import Tenant, ICP, RawLead, Lead, LeadICPAssignment, LeadStageActivity

async def test():
    print("=" * 80)
    print("🚀 COMPLETE PIPELINE TEST - REAL APIs")
    print("=" * 80)
    print(f"⏰ Started: {datetime.utcnow().isoformat()}")
    print()
    
    # Connect to test DB
    engine = create_engine("postgresql://leadgen:leadgen123@db:5432/leadgen_test")
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Cleanup
    print("🧹 Cleaning up test data...")
    db.execute(text("""
        TRUNCATE TABLE 
            lead_stage_activities,
            lead_rejection_tracking,
            lead_icp_assignments,
            leads,
            raw_leads,
            icps,
            tenants
        CASCADE
    """))
    db.commit()
    print("   ✅ Cleanup complete\n")
    
    # Create tenant
    print("1️⃣  Creating Test Tenant...")
    tenant = Tenant(
        id=uuid4(),
        name="Test Company",
        domain="test.com",
        api_key_hash="test_" + str(uuid4())[:8],
        status="active"
    )
    db.add(tenant)
    db.commit()
    print(f"   ✅ Tenant: {tenant.name}\n")
    
    # Create ICP with ALL features
    print("2️⃣  Creating ICP (Full Features)...")
    icp = ICP(
        id=uuid4(),
        tenant_id=tenant.id,
        name="Enterprise SaaS Companies",
        description="High-value B2B SaaS with verified contacts",
        is_active=True,
        
        # Enrichment
        enrichment_enabled=True,
        enrichment_providers={
            "wappalyzer": True,
            "serpapi": True,
            "google_maps": False
        },
        enrichment_cost_per_lead=0.05,
        
        # Verification
        verification_enabled=True,
        verification_cost_per_lead=0.005,
        
        # Thresholds
        auto_approve_threshold=80.0,
        review_threshold=50.0,
        auto_reject_threshold=30.0
    )
    db.add(icp)
    db.commit()
    print(f"   ✅ ICP: {icp.name}")
    print(f"      💰 Enrichment: Wappalyzer (FREE) + SerpApi ($0.002)")
    print(f"      📧 Verification: 3-Pass System ($0.005)")
    print(f"      🎯 Thresholds: Approve≥80%, Review 50-80%, Reject<30%\n")
    
    # Create test leads
    print("3️⃣  Creating Test Leads...")
    
    test_cases = [
        {
            "email": "contact@shopify.com",
            "company": "Shopify",
            "domain": "shopify.com",
            "title": "VP Engineering",
            "expected": "✅ Valid business email - should pass all 3 verification passes"
        },
        {
            "email": "test@gmail.com", 
            "company": "Personal",
            "domain": "gmail.com",
            "title": "Developer",
            "expected": "⚠️  Free email - should verify but lower confidence"
        },
        {
            "email": "invalid-syntax",
            "company": "Test",
            "domain": None,
            "title": "Manager",
            "expected": "❌ Invalid syntax - should fail Pass 1 immediately (FREE)"
        }
    ]
    
    raw_leads = []
    for idx, case in enumerate(test_cases, 1):
        raw = RawLead(
            id=uuid4(),
            tenant_id=tenant.id,
            email=case["email"],
            first_name="Test",
            last_name=f"User{idx}",
            company_name=case["company"],
            company_domain=case["domain"],
            company_website=f"https://{case['domain']}" if case['domain'] else None,
            job_title=case["title"],
            source_name="manual_test",
            scraper_type="manual",
            status="pending",
            processing_status="pending",
            processed_by_icps=[]
        )
        db.add(raw)
        raw_leads.append((raw, case["expected"]))
        print(f"   📧 Lead {idx}: {case['email']}")
        print(f"      {case['expected']}")
    
    db.commit()
    print()
    
    # Process leads
    print("4️⃣  Processing Pipeline (30-90 seconds)...")
    print("   " + "-" * 76)
    
    orchestrator = PipelineOrchestrator(db)
    results = []
    
    for idx, (raw_lead, expected) in enumerate(raw_leads, 1):
        print(f"\n   📧 Lead {idx}/{len(raw_leads)}: {raw_lead.email}")
        print(f"      Expected: {expected}")
        
        start = datetime.utcnow()
        
        result = await orchestrator.process_raw_lead(
            raw_lead=raw_lead,
            icp=icp,
            job_id=f"test-{uuid4()}"
        )
        
        elapsed = (datetime.utcnow() - start).total_seconds()
        
        results.append((raw_lead.email, result, expected))
        
        # Quick summary
        if result['success']:
            print(f"      ✅ Processed in {elapsed:.1f}s")
            print(f"         Status: {result.get('status')}")
            
            if 'scoring' in result:
                print(f"         Score: {result['scoring'].get('score')}%")
            
            if 'verification' in result:
                ver = result['verification']
                print(f"         Verification: {ver.get('status')} "
                      f"({ver.get('confidence')}% confidence)")
                print(f"         Passes: {ver.get('passes_completed', 0)}/3")
        else:
            print(f"      ❌ Failed: {result.get('error')}")
    
    print("\n   " + "-" * 76)
    
    # Detailed Results
    print("\n" + "=" * 80)
    print("📊 DETAILED RESULTS")
    print("=" * 80)
    
    total_cost = 0.0
    
    for idx, (email, result, expected) in enumerate(results, 1):
        print(f"\n{'='*80}")
        print(f"LEAD {idx}: {email}")
        print(f"Expected: {expected}")
        print(f"{'='*80}")
        
        if not result['success']:
            print(f"❌ FAILED: {result.get('error')}")
            continue
        
        print(f"✅ SUCCESS")
        print(f"   Final Status: {result.get('status')}")
        print(f"   Processing Time: {result.get('processing_time_seconds', 0):.2f}s")
        
        # Scoring
        if 'scoring' in result:
            scoring = result['scoring']
            print(f"\n   📈 SCORING:")
            print(f"      Score: {scoring.get('score')}%")
            print(f"      Confidence: {scoring.get('confidence')}%")
            print(f"      Rejected: {scoring.get('rejected', False)}")
        
        # Enrichment
        if 'enrichment' in result:
            enr = result['enrichment']
            print(f"\n   🔍 ENRICHMENT:")
            print(f"      Success: {enr.get('success')}")
            print(f"      Fields Added: {enr.get('fields_added')}")
            print(f"      Providers: {', '.join(enr.get('providers_used', []))}")
            print(f"      Cost: ${enr.get('cost', 0):.4f}")
            total_cost += enr.get('cost', 0)
        
        # Verification (DETAILED)
        if 'verification' in result:
            ver = result['verification']
            print(f"\n   📧 EMAIL VERIFICATION (3-PASS):")
            print(f"      Overall Status: {ver.get('status')}")
            print(f"      Overall Confidence: {ver.get('confidence')}%")
            print(f"      Passes Completed: {ver.get('passes_completed', 0)}/3")
            print(f"      Verified: {'✅' if ver.get('verified') else '❌'}")
            
            if 'field_scores' in ver:
                scores = ver['field_scores']
                print(f"\n      Field-Level Confidence Scores:")
                print(f"         • Syntax:        {scores.get('syntax', 0):.1f}%")
                print(f"         • Domain:        {scores.get('domain', 0):.1f}%")
                print(f"         • Mailbox:       {scores.get('mailbox', 0):.1f}%")
                print(f"         • Deliverability: {scores.get('deliverability', 0):.1f}%")
            
            if 'metadata' in ver:
                meta = ver['metadata']
                print(f"\n      Metadata:")
                print(f"         • Disposable:    {'Yes ❌' if meta.get('is_disposable') else 'No ✅'}")
                print(f"         • Role Account:  {'Yes' if meta.get('is_role') else 'No'}")
                print(f"         • Free Provider: {'Yes' if meta.get('is_free') else 'No'}")
                print(f"         • Catch-All:     {'Yes' if meta.get('is_catch_all') else 'No'}")
            
            print(f"\n      Cost: ${ver.get('cost', 0):.4f}")
            print(f"      Time: {ver.get('time_ms', 0)}ms")
            total_cost += ver.get('cost', 0)
        
        # Qualification
        if 'qualification' in result:
            qual = result['qualification']
            print(f"\n   ✅ QUALIFICATION:")
            print(f"      Decision: {qual.get('decision')}")
            print(f"      Reason: {qual.get('reason')}")
            print(f"      Score: {qual.get('score')}%")
    
    # Cost Summary
    print(f"\n{'='*80}")
    print(f"💰 TOTAL API COSTS: ${total_cost:.4f}")
    print(f"{'='*80}")
    
    # Database Check
    print(f"\n🗄️  DATABASE VERIFICATION")
    print(f"{'='*80}")
    
    lead_count = db.query(Lead).count()
    assignment_count = db.query(LeadICPAssignment).count()
    activity_count = db.query(LeadStageActivity).count()
    
    print(f"   Leads Created:       {lead_count}")
    print(f"   Assignments Created: {assignment_count}")
    print(f"   Activity Logs:       {activity_count}")
    
    # Activity Log Details
    print(f"\n   📝 Activity Log Timeline:")
    activities = db.query(LeadStageActivity).order_by(
        LeadStageActivity.timestamp
    ).all()
    
    for activity in activities:
        print(f"      {activity.timestamp.strftime('%H:%M:%S')} - "
              f"Lead ...{str(activity.lead_id)[-8:]} - "
              f"{activity.from_stage or 'START'} → {activity.to_stage}")
        
        if activity.details:
            if 'score' in activity.details:
                print(f"         💯 Score: {activity.details['score']}")
            if 'verification_status' in activity.details:
                print(f"         📧 Verification: {activity.details['verification_status']}")
            if 'decision' in activity.details:
                print(f"         🎯 Decision: {activity.details['decision']}")
    
    # Verification Data in DB
    print(f"\n   🔬 Verification Data Stored:")
    leads = db.query(Lead).filter(Lead.verification_data.isnot(None)).all()
    
    for lead in leads:
        print(f"\n      📧 {lead.email}")
        print(f"         DB Status: {lead.email_verification_status}")
        print(f"         DB Confidence: {lead.email_verification_confidence}%")
        
        if lead.verification_data:
            vdata = lead.verification_data
            print(f"         Passes: {vdata.get('passes_completed', 'N/A')}/3")
            print(f"         Syntax Score: {vdata.get('syntax_score', 'N/A')}%")
            print(f"         Domain Score: {vdata.get('domain_score', 'N/A')}%")
            print(f"         Mailbox Score: {vdata.get('mailbox_score', 'N/A')}%")
            print(f"         Deliverability: {vdata.get('deliverability_score', 'N/A'):.1f}%")
            print(f"         Is Disposable: {vdata.get('is_disposable', 'N/A')}")
            print(f"         Is Role: {vdata.get('is_role_account', 'N/A')}")
            print(f"         Is Free: {vdata.get('is_free_provider', 'N/A')}")
    
    print()
    print("=" * 80)
    print("🎉 COMPLETE PIPELINE TEST FINISHED!")
    print("=" * 80)
    print(f"⏰ Finished: {datetime.utcnow().isoformat()}")
    print(f"💰 Total Cost: ${total_cost:.4f}")
    print()
    
    db.close()

if __name__ == "__main__":
    asyncio.run(test())
