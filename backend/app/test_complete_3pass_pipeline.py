# test_complete_3pass_pipeline.py
"""
Complete End-to-End Pipeline Test
Tests EVERYTHING: Scoring → Enrichment (SerpApi) → 3-Pass Verification → Qualification

This will cost approximately:
- Enrichment (SerpApi): $0.002
- Verification (Verifalia): $0.005
- Total: $0.007 per lead
"""

import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from uuid import uuid4
from datetime import datetime

from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.models import Tenant, ICP, RawLead, Lead, LeadICPAssignment, LeadStageActivity, Base

async def test():
    print("=" * 80)
    print("🚀 COMPLETE 3-PASS VERIFICATION + ENRICHMENT PIPELINE TEST")
    print("=" * 80)
    print(f"Started: {datetime.utcnow().isoformat()}")
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
    
    # Create test tenant
    print("1️⃣  Creating Test Tenant...")
    tenant = Tenant(
        id=uuid4(),
        name="Test Company Inc",
        domain="testcompany.com",
        api_key_hash="test_hash_" + str(uuid4())[:8],
        status="active"
    )
    db.add(tenant)
    db.commit()
    print(f"   ✅ Tenant: {tenant.name} ({tenant.id})\n")
    
    # Create ICP with ALL features enabled
    print("2️⃣  Creating ICP (All Features Enabled)...")
    icp = ICP(
        id=uuid4(),
        tenant_id=tenant.id,
        name="High-Value Enterprise SaaS",
        description="Enterprise SaaS companies with verified emails",
        is_active=True,
        
        # ✅ Enable enrichment
        enrichment_enabled=True,
        enrichment_providers={
            "wappalyzer": True,   # FREE - tech stack
            "serpapi": True,      # $0.002 - company info
            "google_maps": False  # Skip to save cost
        },
        enrichment_cost_per_lead=0.05,
        
        # ✅ Enable verification
        verification_enabled=True,
        verification_cost_per_lead=0.005,
        
        # Scoring thresholds
        auto_approve_threshold=80.0,
        review_threshold=50.0,
        auto_reject_threshold=30.0,
        
        preferred_scrapers=["linkedin"]
    )
    db.add(icp)
    db.commit()
    print(f"   ✅ ICP: {icp.name}")
    print(f"      - Enrichment: Wappalyzer + SerpApi")
    print(f"      - Verification: 3-Pass System")
    print(f"      - Auto-Approve: ≥{icp.auto_approve_threshold}%")
    print(f"      - Review: {icp.review_threshold}-{icp.auto_approve_threshold}%")
    print(f"      - Reject: <{icp.auto_reject_threshold}%\n")
    
    # Create test raw leads (different scenarios)
    print("3️⃣  Creating Test Raw Leads...")
    
    test_leads = [
        {
            "email": "contact@shopify.com",
            "company_name": "Shopify",
            "company_domain": "shopify.com",
            "job_title": "VP of Engineering",
            "expected": "Valid business email, should verify"
        },
        {
            "email": "test@gmail.com",
            "company_name": "Personal",
            "company_domain": "gmail.com",
            "job_title": "Developer",
            "expected": "Free email provider, may verify but lower score"
        },
        {
            "email": "invalid-email-format",
            "company_name": "Test Co",
            "company_domain": None,
            "job_title": "Manager",
            "expected": "Invalid syntax, should fail Pass 1"
        }
    ]
    
    raw_leads = []
    for idx, lead_data in enumerate(test_leads, 1):
        raw_lead = RawLead(
            id=uuid4(),
            tenant_id=tenant.id,
            email=lead_data["email"],
            first_name="Test",
            last_name=f"Lead{idx}",
            company_name=lead_data["company_name"],
            company_domain=lead_data["company_domain"],
            company_website=f"https://{lead_data['company_domain']}" if lead_data['company_domain'] else None,
            job_title=lead_data["job_title"],
            source_name="manual_test",
            scraper_type="manual",
            status="pending",
            processing_status="pending",
            processed_by_icps=[]
        )
        db.add(raw_lead)
        raw_leads.append((raw_lead, lead_data["expected"]))
        print(f"   ✅ Lead {idx}: {lead_data['email']}")
        print(f"      Expected: {lead_data['expected']}")
    
    db.commit()
    print()
    
    # Process each lead through pipeline
    print("4️⃣  Running Complete Pipeline (This will take 30-120 seconds)...")
    print("   " + "-" * 76)
    
    orchestrator = PipelineOrchestrator(db)
    results = []
    
    for idx, (raw_lead, expected_outcome) in enumerate(raw_leads, 1):
        print(f"\n   📧 Processing Lead {idx}/{len(raw_leads)}: {raw_lead.email}")
        print(f"      Expected: {expected_outcome}")
        print(f"      Processing... ", end="", flush=True)
        
        start = datetime.utcnow()
        
        result = await orchestrator.process_raw_lead(
            raw_lead=raw_lead,
            icp=icp,
            job_id=f"test-job-{uuid4()}"
        )
        
        elapsed = (datetime.utcnow() - start).total_seconds()
        print(f"({elapsed:.1f}s)")
        
        results.append((raw_lead.email, result, expected_outcome))
        
        # Print summary
        if result['success']:
            print(f"      ✅ Success")
            print(f"         Status: {result.get('status')}")
            print(f"         Score: {result.get('score')}")
            
            if 'verification' in result:
                ver = result['verification']
                print(f"         Verification: {ver.get('status')} ({ver.get('confidence')}%)")
                print(f"         Passes: {ver.get('passes_completed', 0)}/3")
                if 'field_scores' in ver:
                    scores = ver['field_scores']
                    print(f"         Field Scores:")
                    print(f"            - Syntax: {scores.get('syntax', 0)}%")
                    print(f"            - Domain: {scores.get('domain', 0)}%")
                    print(f"            - Mailbox: {scores.get('mailbox', 0)}%")
                    print(f"            - Deliverability: {scores.get('deliverability', 0):.1f}%")
        else:
            print(f"      ❌ Failed: {result.get('error')}")
    
    print()
    print("   " + "-" * 76)
    
    # Final Results Summary
    print("\n" + "=" * 80)
    print("📊 FINAL RESULTS SUMMARY")
    print("=" * 80)
    
    total_cost = 0.0
    
    for idx, (email, result, expected) in enumerate(results, 1):
        print(f"\n{idx}. {email}")
        print(f"   Expected: {expected}")
        
        if result['success']:
            print(f"   ✅ Result: SUCCESS")
            print(f"      Final Status: {result.get('status')}")
            print(f"      Score: {result.get('score')}%")
            
            # Scoring
            if 'scoring' in result:
                scoring = result['scoring']
                print(f"      Scoring: {scoring.get('score')}% (confidence: {scoring.get('confidence')}%)")
            
            # Enrichment
            if 'enrichment' in result:
                enr = result['enrichment']
                print(f"      Enrichment: {enr.get('fields_added')} fields added")
                print(f"         Providers: {', '.join(enr.get('providers_used', []))}")
                print(f"         Cost: ${enr.get('cost', 0):.4f}")
                total_cost += enr.get('cost', 0)
            
            # Verification
            if 'verification' in result:
                ver = result['verification']
                print(f"      Verification:")
                print(f"         Status: {ver.get('status')}")
                print(f"         Overall Confidence: {ver.get('confidence')}%")
                print(f"         Passes Completed: {ver.get('passes_completed', 0)}/3")
                
                if 'field_scores' in ver:
                    scores = ver['field_scores']
                    print(f"         Field-Level Scores:")
                    print(f"            • Syntax: {scores.get('syntax', 0)}%")
                    print(f"            • Domain: {scores.get('domain', 0)}%")
                    print(f"            • Mailbox: {scores.get('mailbox', 0)}%")
                    print(f"            • Deliverability: {scores.get('deliverability', 0):.1f}%")
                
                if 'metadata' in ver:
                    meta = ver['metadata']
                    print(f"         Metadata:")
                    print(f"            • Disposable: {meta.get('is_disposable', False)}")
                    print(f"            • Role Account: {meta.get('is_role', False)}")
                    print(f"            • Free Provider: {meta.get('is_free', False)}")
                    print(f"            • Catch-All: {meta.get('is_catch_all', False)}")
                
                print(f"         Cost: ${ver.get('cost', 0):.4f}")
                print(f"         Time: {ver.get('time_ms', 0)}ms")
                total_cost += ver.get('cost', 0)
            
            # Qualification
            if 'qualification' in result:
                qual = result['qualification']
                print(f"      Qualification: {qual.get('decision')}")
                print(f"         Reason: {qual.get('reason')}")
        else:
            print(f"   ❌ Result: FAILED")
            print(f"      Error: {result.get('error')}")
    
    # Cost Summary
    print(f"\n💰 TOTAL API COSTS: ${total_cost:.4f}")
    
    # Database Verification
    print(f"\n🗄️  DATABASE VERIFICATION")
    print("   " + "-" * 76)
    
    lead_count = db.query(Lead).count()
    assignment_count = db.query(LeadICPAssignment).count()
    activity_count = db.query(LeadStageActivity).count()
    
    print(f"   Leads created: {lead_count}")
    print(f"   Assignments created: {assignment_count}")
    print(f"   Activity logs created: {activity_count}")
    
    # Show activity logs
    print(f"\n   📝 Activity Log Entries:")
    activities = db.query(LeadStageActivity).order_by(LeadStageActivity.timestamp).all()
    
    for activity in activities:
        print(f"      • {activity.timestamp.strftime('%H:%M:%S')} - "
              f"Lead {str(activity.lead_id)[:8]}... - "
              f"{activity.from_stage or 'START'} → {activity.to_stage}")
        if activity.details:
            if 'score' in activity.details:
                print(f"        Score: {activity.details['score']}")
            if 'verification_status' in activity.details:
                print(f"        Verification: {activity.details['verification_status']}")
            if 'decision' in activity.details:
                print(f"        Decision: {activity.details['decision']}")
    
    # Detailed verification data check
    print(f"\n   🔍 Verification Data Stored in Database:")
    leads_with_verification = db.query(Lead).filter(
        Lead.verification_data.isnot(None)
    ).all()
    
    for lead in leads_with_verification:
        print(f"\n      Lead: {lead.email}")
        print(f"         Verified: {lead.email_verified}")
        print(f"         Status: {lead.email_verification_status}")
        print(f"         Confidence: {lead.email_verification_confidence}%")
        
        if lead.verification_data:
            vdata = lead.verification_data
            print(f"         Passes Completed: {vdata.get('passes_completed', 'N/A')}")
            print(f"         Syntax Score: {vdata.get('syntax_score', 'N/A')}%")
            print(f"         Domain Score: {vdata.get('domain_score', 'N/A')}%")
            print(f"         Mailbox Score: {vdata.get('mailbox_score', 'N/A')}%")
            print(f"         Deliverability: {vdata.get('deliverability_score', 'N/A')}%")
    
    print()
    print("=" * 80)
    print("🎉 END-TO-END TEST COMPLETE!")
    print("=" * 80)
    print(f"Finished: {datetime.utcnow().isoformat()}")
    print()
    
    db.close()

# Run test
if __name__ == "__main__":
    asyncio.run(test())