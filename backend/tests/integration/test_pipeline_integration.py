# tests/integration/test_pipeline_integration.py

import pytest
from uuid import uuid4
from sqlalchemy import text

from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.models import Lead, LeadICPAssignment, Tenant


@pytest.mark.integration
def test_database_connection(db_session):
    """Smoke test: Verify database connection works"""
    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1
    print("✅ Database connection successful!")


@pytest.mark.integration
def test_create_real_tenant(db_session):
    """Test creating a real tenant in test database"""
    tenant = Tenant(
        id=uuid4(),
        name="Test Tenant",
        domain="test.com",
        api_key_hash="hash123",
        status="active"
    )
    db_session.add(tenant)
    db_session.commit()
    
    found = db_session.query(Tenant).filter(
        Tenant.domain == "test.com"
    ).first()
    
    assert found is not None
    assert found.name == "Test Tenant"
    print(f"✅ Created tenant: {found.name}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_pipeline_with_real_db(
    db_session,
    real_tenant,
    real_icp,
    real_raw_lead
):
    """Test complete pipeline end-to-end with real database"""
    print(f"\n🚀 Testing pipeline with tenant: {real_tenant.name}")
    print(f"📧 Processing lead: {real_raw_lead.email}")
    
    orchestrator = PipelineOrchestrator(db_session)
    
    # ✅ FIXED: Use proper UUID for job_id
    job_id = str(uuid4())
    
    result = await orchestrator.process_raw_lead(
        raw_lead=real_raw_lead,
        icp=real_icp,
        job_id=job_id
    )
    
    print(f"📊 Result: {result}")
    
    # Assert result
    assert result['success'] is True, f"Pipeline failed: {result.get('error')}"
    assert result['lead_id'] is not None
    assert result['assignment_id'] is not None
    
    # Verify REAL lead was created in database
    lead = db_session.query(Lead).filter(
        Lead.email == "test@integration.com"
    ).first()
    
    assert lead is not None, "Lead was not created in database"
    assert lead.first_name == "Test"
    assert lead.last_name == "Integration"
    assert lead.company_name == "TestCorp"
    assert lead.tenant_id == real_tenant.id
    
    print(f"✅ Lead created: {lead.first_name} {lead.last_name}")
    
    # Verify REAL assignment was created
    assignment = db_session.query(LeadICPAssignment).filter(
        LeadICPAssignment.lead_id == lead.id,
        LeadICPAssignment.icp_id == real_icp.id
    ).first()
    
    assert assignment is not None, "Assignment was not created"
    assert assignment.status in ['new', 'scored', 'qualified', 'pending_review', 'rejected']
    assert assignment.tenant_id == real_tenant.id
    
    print(f"✅ Assignment created with status: {assignment.status}")
    
    # Verify raw lead was updated
    db_session.refresh(real_raw_lead)
    assert real_raw_lead.lead_id == lead.id
    assert str(real_icp.id) in real_raw_lead.processed_by_icps
    
    print(f"✅ Raw lead tracking updated")
    print(f"\n🎉 Integration test PASSED!")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lead_deduplication_real_db(db_session, real_tenant, real_icp):
    """Test that duplicate emails create only one lead"""
    from app.models import RawLead
    
    # Create first raw lead
    raw_lead_1 = RawLead(
        id=uuid4(),
        tenant_id=real_tenant.id,
        email="duplicate@test.com",
        first_name="First",
        company_name="TestCo",
        source_name="source1",
        scraper_type="manual",
        status="pending",
        processing_status="pending",
        processed_by_icps=[]
    )
    db_session.add(raw_lead_1)
    db_session.commit()
    
    # Create second raw lead with SAME email
    raw_lead_2 = RawLead(
        id=uuid4(),
        tenant_id=real_tenant.id,
        email="duplicate@test.com",
        first_name="Second",
        company_name="TestCo",
        source_name="source2",
        scraper_type="manual",
        status="pending",
        processing_status="pending",
        processed_by_icps=[]
    )
    db_session.add(raw_lead_2)
    db_session.commit()
    
    # Process both
    orchestrator = PipelineOrchestrator(db_session)
    
    result1 = await orchestrator.process_raw_lead(raw_lead_1, real_icp, job_id=str(uuid4()))
    result2 = await orchestrator.process_raw_lead(raw_lead_2, real_icp, job_id=str(uuid4()))
    
    # Both should succeed
    assert result1['success'] is True
    assert result2['success'] is True
    
    # But they should create the SAME lead
    assert result1['lead_id'] == result2['lead_id']
    
    # Verify only ONE lead in database
    lead_count = db_session.query(Lead).filter(
        Lead.email == "duplicate@test.com"
    ).count()
    
    assert lead_count == 1, f"Expected 1 lead, found {lead_count}"
    
    print(f"✅ Deduplication works! Only 1 lead created from 2 raw leads")