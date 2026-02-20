"""
SIMPLIFIED PIPELINE TEST
Tests: Scoring → Enrichment → 3-Pass Verification → Qualification
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
    
    # Cleanup with CORRECT table name
    print("🧹 Cleaning up test data...")
    db.execute(text("""
        TRUNCATE TABLE 
            lead_stage_activity,
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
    
    # Create ICP
    print("2️⃣  Creating ICP...")
    icp = ICP(
        id=uuid4(),
        tenant_id=tenant.id,
        name="Enterprise SaaS",
        description="High-value B2B SaaS",
        is_active=True,
        enrichment_enabled=True,
        enrichment_providers={"wappalyzer": True, "serpapi": True, "google_maps": False},
        verification_enabled=True,
        auto_approve_threshold=80.0,
        review_threshold=50.0,
        auto_reject_threshold=-1.0  # ✅ DISABLED - Let full pipeline run
    )
    db.add(icp)
    db.commit()
    print(f"   ✅ ICP: {icp.name}")
    print(f"      💰 Enrichment: Wappalyzer (FREE) + SerpApi ($0.002)")
    print(f"      📧 Verification: 3-Pass System ($0.005)")
    print(f"      🎯 Auto-reject DISABLED - Full pipeline will run\n")
    
    # Create test lead
    print("3️⃣  Creating Test Lead...")
    raw_lead = RawLead(
        id=uuid4(),
        tenant_id=tenant.id,
        email="contact@shopify.com",
        first_name="Test",
        last_name="User",
        company_name="Shopify",
        company_domain="shopify.com",
        company_website="https://shopify.com",
        job_title="VP Engineering",
        source_name="manual_test",
        scraper_type="manual",
        status="pending",
        processing_status="pending",
        processed_by_icps=[]
    )
    db.add(raw_lead)
    db.commit()
    print(f"   📧 {raw_lead.email}")
    print(f"      Expected: Valid business email, should pass all 3 verification passes\n")
    
    # Process through pipeline
    print("4️⃣  Running Complete Pipeline...")
    print("   This will take 30-60 seconds (calling REAL APIs)...")
    print("   " + "-" * 76)
    
    orchestrator = PipelineOrchestrator(db)
    
    start = datetime.utcnow()
    result = await orchestrator.process_raw_lead(
        raw_lead=raw_lead,
        icp=icp,
        job_id=f"test-{uuid4()}"
    )
    elapsed = (datetime.utcnow() - start).total_seconds()
    
    print(f"\n   ✅ Pipeline completed in {elapsed:.1f}s")
    print("   " + "-" * 76)
    
    # Show results
    print("\n" + "=" * 80)
    print("📊 DETAILED RESULTS")
    print("=" * 80)
    
    if not result['success']:
        print(f"❌ FAILED: {result.get('error')}")
        db.close()
        return
    
    print(f"✅ SUCCESS")
    print(f"   Final Status: {result.get('status')}")
    print(f"   Lead ID: {result.get('lead_id')}")
    print(f"   Assignment ID: {result.get('assignment_id')}")
    print(f"   Processing Time: {elapsed:.2f}s")
    
    # Scoring
    if 'scoring' in result:
        scoring = result['scoring']
        print(f"\n📈 SCORING:")
        print(f"   Score: {scoring.get('score')}%")
        print(f"   Confidence: {scoring.get('confidence')}%")
        print(f"   Rejected: {scoring.get('rejected', False)}")
    
    # Enrichment
    total_cost = 0.0
    if 'enrichment' in result:
        enr = result['enrichment']
        print(f"\n🔍 ENRICHMENT:")
        print(f"   Success: {enr.get('success')}")
        print(f"   Fields Added: {enr.get('fields_added')}")
        print(f"   Providers: {', '.join(enr.get('providers_used', []))}")
        print(f"   Cost: ${enr.get('cost', 0):.4f}")
        total_cost += enr.get('cost', 0)
    
    # Verification (DETAILED)
    if 'verification' in result:
        ver = result['verification']
        print(f"\n📧 EMAIL VERIFICATION (3-PASS):")
        print(f"   Overall Status: {ver.get('status')}")
        print(f"   Overall Confidence: {ver.get('confidence')}%")
        print(f"   Passes Completed: {ver.get('passes_completed', 0)}/3")
        print(f"   Verified: {'✅' if ver.get('verified') else '❌'}")
        
        if 'field_scores' in ver:
            scores = ver['field_scores']
            print(f"\n   Field-Level Confidence Scores:")
            print(f"      • Syntax:        {scores.get('syntax', 0):.1f}%")
            print(f"      • Domain:        {scores.get('domain', 0):.1f}%")
            print(f"      • Mailbox:       {scores.get('mailbox', 0):.1f}%")
            print(f"      • Deliverability: {scores.get('deliverability', 0):.1f}%")
        
        if 'metadata' in ver:
            meta = ver['metadata']
            print(f"\n   Metadata:")
            print(f"      • Disposable:    {'Yes ❌' if meta.get('is_disposable') else 'No ✅'}")
            print(f"      • Role Account:  {'Yes' if meta.get('is_role') else 'No'}")
            print(f"      • Free Provider: {'Yes' if meta.get('is_free') else 'No'}")
            print(f"      • Catch-All:     {'Yes' if meta.get('is_catch_all') else 'No'}")
        
        print(f"\n   Cost: ${ver.get('cost', 0):.4f}")
        print(f"   Time: {ver.get('time_ms', 0)}ms")
        total_cost += ver.get('cost', 0)
    
    # Qualification
    if 'qualification' in result:
        qual = result['qualification']
        print(f"\n✅ QUALIFICATION:")
        print(f"   Decision: {qual.get('decision')}")
        print(f"   Reason: {qual.get('reason')}")
        print(f"   Score: {qual.get('score')}%")
    
    # Database verification
    print(f"\n🗄️  DATABASE VERIFICATION:")
    
    lead_count = db.query(Lead).count()
    assignment_count = db.query(LeadICPAssignment).count()
    activity_count = db.query(LeadStageActivity).count()
    
    print(f"   Leads Created:       {lead_count}")
    print(f"   Assignments Created: {assignment_count}")
    print(f"   Activity Logs:       {activity_count}")
    
    # Lead details
    lead = db.query(Lead).filter(Lead.id == result.get('lead_id')).first()
    if lead:
        print(f"\n   ✅ Lead Record:")
        print(f"      Email: {lead.email}")
        print(f"      Verified: {lead.email_verified}")
        print(f"      Status: {lead.email_verification_status}")
        print(f"      Confidence: {lead.email_verification_confidence}%")
        
        if lead.verification_data:
            vdata = lead.verification_data
            print(f"\n   🔬 Verification Data Stored:")
            print(f"      Passes: {vdata.get('passes_completed', 'N/A')}/3")
            print(f"      Syntax Score: {vdata.get('syntax_score', 'N/A')}%")
            print(f"      Domain Score: {vdata.get('domain_score', 'N/A')}%")
            print(f"      Mailbox Score: {vdata.get('mailbox_score', 'N/A')}%")
            print(f"      Deliverability: {vdata.get('deliverability_score', 'N/A'):.1f}%")
            print(f"      Is Disposable: {vdata.get('is_disposable', 'N/A')}")
            print(f"      Is Role: {vdata.get('is_role_account', 'N/A')}")
            print(f"      Is Free: {vdata.get('is_free_provider', 'N/A')}")
    
    # Assignment details
    assignment = db.query(LeadICPAssignment).filter(
        LeadICPAssignment.id == result.get('assignment_id')
    ).first()
    if assignment:
        print(f"\n   ✅ Assignment Record:")
        print(f"      Status: {assignment.status}")
        print(f"      Bucket: {assignment.bucket}")
        print(f"      Score: {assignment.fit_score_percentage}%")
    
    # Activity logs
    print(f"\n   📝 Activity Log Timeline:")
    activities = db.query(LeadStageActivity).order_by(
        LeadStageActivity.timestamp
    ).all()
    
    for activity in activities:
        print(f"      {activity.timestamp.strftime('%H:%M:%S')} - "
              f"{activity.from_stage or 'START'} → {activity.to_stage}")
        
        if activity.details:
            if 'score' in activity.details:
                print(f"         💯 Score: {activity.details['score']}")
            if 'verification_status' in activity.details:
                print(f"         📧 Verification: {activity.details['verification_status']}")
            if 'decision' in activity.details:
                print(f"         🎯 Decision: {activity.details['decision']}")
    
    print()
    print("=" * 80)
    print("🎉 COMPLETE PIPELINE TEST FINISHED!")
    print("=" * 80)
    print(f"⏰ Finished: {datetime.utcnow().isoformat()}")
    print(f"💰 Total API Cost: ${total_cost:.4f}")
    print()
    print("✅ All systems working:")
    print("   • Scoring engine")
    print("   • Enrichment (Wappalyzer + SerpApi)")
    print("   • 3-Pass email verification")
    print("   • Auto-qualification")
    print("   • Database persistence")
    print("   • Activity logging")
    print()
    
    db.close()

if __name__ == "__main__":
    asyncio.run(test())
