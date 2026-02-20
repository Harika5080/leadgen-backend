# tests/services/test_pipeline_orchestrator.py
"""
Comprehensive automated tests for PipelineOrchestrator

Coverage:
- Lead creation and deduplication
- Assignment creation (multi-ICP)
- Scoring with different thresholds
- Enrichment integration
- Email verification
- Auto-qualification logic
- Error handling
- Stage activity logging

Run with: pytest tests/services/test_pipeline_orchestrator.py -v
"""

import pytest
from datetime import datetime
from uuid import uuid4, UUID
from decimal import Decimal
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from sqlalchemy.orm import Session

from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.models import (
    Lead,
    LeadICPAssignment,
    RawLead,
    ICP,
    Tenant,
    LeadRejectionTracking,
    LeadStageActivity
)


# ============================================================================
# FIXTURES - MODULE LEVEL (NO SELF!)
# ============================================================================

@pytest.fixture
def mock_db():
    """Mock database session"""
    db = Mock(spec=Session)
    db.query = Mock()
    db.add = Mock()
    db.flush = Mock()
    db.commit = Mock()
    db.rollback = Mock()
    return db


@pytest.fixture(autouse=True)
def mock_scoring_engine():
    """Auto-mock the scoring engine for all tests"""
    with patch('app.services.pipeline_orchestrator.ICPScoringEngine') as mock:
        mock_instance = Mock()
        mock_instance.score_lead = Mock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_activity_logger():
    """Mock activity logger"""
    mock = Mock()
    mock.log_stage_transition = Mock()
    mock.log_scoring = Mock()
    mock.log_enrichment = Mock()
    mock.log_verification = Mock()
    mock.log_qualification = Mock()
    mock.log_rejection = Mock()
    return mock


@pytest.fixture
def sample_tenant():
    """Sample tenant"""
    return Tenant(
        id=uuid4(),
        name="Test Company Inc",
        domain="testcompany.com",
        api_key_hash="test_hash_" + str(uuid4())[:8],
        status='active'
    )


@pytest.fixture
def sample_raw_lead(sample_tenant):
    """Sample raw lead from scraper"""
    return RawLead(
        id=uuid4(),
        tenant_id=sample_tenant.id,
        source_name="linkedin_scraper",
        source_url="https://linkedin.com/in/johndoe",
        scraper_type="crawlee",
        email="john.doe@techcorp.com",
        first_name="John",
        last_name="Doe",
        phone="+1-555-0100",
        job_title="VP of Engineering",
        linkedin_url="https://linkedin.com/in/johndoe",
        company_name="TechCorp",
        company_domain="techcorp.com",
        company_website="https://techcorp.com",
        company_size="201-500",
        company_industry="Software",
        city="San Francisco",
        state="CA",
        country="USA",
        status="pending",
        processing_status="pending",
        processed_by_icps=[],
        scraped_data={},
        enrichment_data={}
    )


@pytest.fixture
def sample_icp(sample_tenant):
    """Sample ICP configuration"""
    return ICP(
        id=uuid4(),
        tenant_id=sample_tenant.id,
        name="Enterprise B2B SaaS",
        description="Target enterprise software companies",
        is_active=True,
        auto_approve_threshold=80.0,
        review_threshold=50.0,
        auto_reject_threshold=30.0,
        enrichment_enabled=True,
        enrichment_cost_per_lead=0.05,
        enrichment_providers={
            "wappalyzer": True,
            "serpapi": True,
            "google_maps": False
        },
        verification_enabled=True,
        verification_cost_per_lead=0.01,
        preferred_scrapers=["linkedin", "apollo"]
    )


# ============================================================================
# TEST: Lead Creation
# ============================================================================

class TestLeadCreation:
    """Test lead creation from raw leads"""
    
    @pytest.mark.asyncio
    async def test_create_new_lead_from_raw(
        self,
        mock_db,
        sample_raw_lead
    ):
        """Test creating new lead from raw lead"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        # Mock: No existing lead
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Execute
        lead, is_new = await orchestrator._create_or_find_lead(sample_raw_lead)
        
        # Assert
        assert is_new is True
        assert lead.email == sample_raw_lead.email
        assert lead.first_name == sample_raw_lead.first_name
        assert lead.last_name == sample_raw_lead.last_name
        assert lead.job_title == sample_raw_lead.job_title
        assert lead.company_name == sample_raw_lead.company_name
        assert lead.company_domain == sample_raw_lead.company_domain
        assert lead.company_size == sample_raw_lead.company_size
        assert lead.company_industry == sample_raw_lead.company_industry
        assert lead.raw_lead_id == sample_raw_lead.id
        assert lead.processing_started_at is not None
        assert lead.source == sample_raw_lead.source_name
        
        assert mock_db.add.call_count >= 1
        assert mock_db.flush.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_find_existing_lead_by_email(
        self,
        mock_db,
        sample_raw_lead,
        sample_tenant
    ):
        """Test finding existing lead by email (deduplication)"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        # Mock: Existing lead found
        existing_lead = Lead(
            id=uuid4(),
            tenant_id=sample_tenant.id,
            email=sample_raw_lead.email,
            first_name="Existing",
            last_name="User"
        )
        mock_db.query.return_value.filter.return_value.first.return_value = existing_lead
        
        # Execute
        lead, is_new = await orchestrator._create_or_find_lead(sample_raw_lead)
        
        # Assert
        assert is_new is False
        assert lead.id == existing_lead.id
        assert lead.email == sample_raw_lead.email
        
        # Should NOT create new lead
        mock_db.add.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_lead_field_mapping(self, mock_db, sample_raw_lead):
        """Test all fields are correctly mapped from raw lead"""
        orchestrator = PipelineOrchestrator(mock_db)
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        lead, is_new = await orchestrator._create_or_find_lead(sample_raw_lead)
        
        # Verify all important fields mapped
        assert lead.email == sample_raw_lead.email
        assert lead.first_name == sample_raw_lead.first_name
        assert lead.last_name == sample_raw_lead.last_name
        assert lead.phone == sample_raw_lead.phone
        assert lead.job_title == sample_raw_lead.job_title
        assert lead.linkedin_url == sample_raw_lead.linkedin_url
        assert lead.company_name == sample_raw_lead.company_name
        assert lead.company_domain == sample_raw_lead.company_domain
        assert lead.company_website == sample_raw_lead.company_website
        assert lead.company_size == sample_raw_lead.company_size
        assert lead.company_industry == sample_raw_lead.company_industry
        assert lead.city == sample_raw_lead.city
        assert lead.state == sample_raw_lead.state
        assert lead.country == sample_raw_lead.country
        assert lead.source == sample_raw_lead.source_name
        assert lead.source_url == sample_raw_lead.source_url


# ============================================================================
# TEST: Assignment Creation
# ============================================================================

class TestAssignmentCreation:
    """Test lead-to-ICP assignment creation"""
    
    @pytest.mark.asyncio
    async def test_create_new_assignment(
        self,
        mock_db,
        sample_tenant,
        sample_icp
    ):
        """Test creating new assignment"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        lead = Lead(
            id=uuid4(),
            tenant_id=sample_tenant.id,
            email="test@example.com"
        )
        job_id = "test-job-123"
        
        # Mock: No existing assignment
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Execute
        assignment = await orchestrator._get_or_create_assignment(lead, sample_icp, job_id)
        
        # Assert
        assert assignment.lead_id == lead.id
        assert assignment.icp_id == sample_icp.id
        assert assignment.tenant_id == lead.tenant_id
        assert assignment.status == 'new'
        assert assignment.bucket == 'new'
        assert assignment.processing_job_id == job_id
        
        assert mock_db.add.call_count >= 1
        assert mock_db.flush.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_find_existing_assignment(
        self,
        mock_db,
        sample_tenant,
        sample_icp
    ):
        """Test finding existing assignment"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        lead = Lead(id=uuid4(), tenant_id=sample_tenant.id, email="test@test.com")
        
        # Mock: Existing assignment
        existing_assignment = LeadICPAssignment(
            id=uuid4(),
            lead_id=lead.id,
            icp_id=sample_icp.id,
            tenant_id=sample_tenant.id,
            status='scored',
            bucket='scored'
        )
        mock_db.query.return_value.filter.return_value.first.return_value = existing_assignment
        
        # Execute
        assignment = await orchestrator._get_or_create_assignment(lead, sample_icp, None)
        
        # Assert
        assert assignment.id == existing_assignment.id
        assert assignment.status == 'scored'
        
        # Should NOT create new assignment
        mock_db.add.assert_not_called()


# ============================================================================
# TEST: Scoring
# ============================================================================

class TestScoring:
    """Test lead scoring engine integration"""
    
    @pytest.mark.asyncio
    async def test_successful_scoring_high_score(
        self,
        mock_db,
        sample_raw_lead,
        sample_icp,
        sample_tenant
    ):
        """Test successful scoring with high score"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        assignment = LeadICPAssignment(
            id=uuid4(),
            lead_id=uuid4(),
            icp_id=sample_icp.id,
            tenant_id=sample_tenant.id,
            status='new'
        )
        assignment.update_status = Mock()
        
        # Mock scoring engine to return high score
        score_result = Mock()
        score_result.score = 85.5
        score_result.confidence = 92.0
        score_result.breakdown = {
            "company_size": 25.0,
            "job_title": 28.5,
            "industry": 18.0,
            "location": 10.0,
            "company_revenue": 4.0
        }
        
        with patch.object(orchestrator.scoring_engine, 'score_lead', return_value=score_result):
            # Execute
            result = await orchestrator._score_assignment(
                assignment, sample_raw_lead, sample_icp, "job-123"
            )
        
        # Assert
        assert result['rejected'] is False
        assert result['score'] == 85.5
        assert result['confidence'] == 92.0
        assert assignment.fit_score == 85.5
        assert assignment.fit_score_percentage == 85.5
        assert assignment.icp_score_confidence == 92.0
        assert assignment.scoring_details == score_result.breakdown
        
        assignment.update_status.assert_called_once_with('scored')
        mock_db.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_auto_reject_low_score(
        self,
        mock_db,
        sample_raw_lead,
        sample_icp,
        sample_tenant
    ):
        """Test auto-rejection for low scores"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        # Set rejection threshold
        sample_icp.auto_reject_threshold = 30.0
        
        assignment = LeadICPAssignment(
            id=uuid4(),
            lead_id=uuid4(),
            icp_id=sample_icp.id,
            tenant_id=sample_tenant.id,
            status='new'
        )
        assignment.update_status = Mock()
        
        # Mock low score (below threshold)
        score_result = Mock()
        score_result.score = 25.0
        score_result.confidence = 85.0
        score_result.breakdown = {
            "company_size": 10.0,
            "job_title": 8.0,
            "industry": 5.0,
            "location": 2.0
        }
        
        with patch.object(orchestrator.scoring_engine, 'score_lead', return_value=score_result):
            with patch.object(orchestrator, '_reject_assignment', new_callable=AsyncMock) as mock_reject:
                # Execute
                result = await orchestrator._score_assignment(
                    assignment, sample_raw_lead, sample_icp, "job-123"
                )
        
        # Assert
        assert result['rejected'] is True
        assert result['reason'] == "low_score"
        assert mock_reject.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_score_confidence_tracking(
        self,
        mock_db,
        sample_raw_lead,
        sample_icp,
        sample_tenant
    ):
        """Test that scoring confidence is tracked"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        assignment = LeadICPAssignment(
            id=uuid4(),
            lead_id=uuid4(),
            icp_id=sample_icp.id,
            tenant_id=sample_tenant.id,
            status='new'
        )
        assignment.update_status = Mock()
        
        score_result = Mock()
        score_result.score = 75.0
        score_result.confidence = 88.5
        score_result.breakdown = {}
        
        with patch.object(orchestrator.scoring_engine, 'score_lead', return_value=score_result):
            await orchestrator._score_assignment(
                assignment, sample_raw_lead, sample_icp, None
            )
        
        # Assert confidence is stored
        assert assignment.icp_score_confidence == 88.5


# ============================================================================
# TEST: Enrichment
# ============================================================================

class TestEnrichment:
    """Test lead enrichment integration"""
    
    @pytest.mark.asyncio
    async def test_successful_enrichment(
        self,
        mock_db,
        sample_icp,
        sample_tenant
    ):
        """Test successful lead enrichment"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        lead = Lead(
            id=uuid4(),
            tenant_id=sample_tenant.id,
            email="john@techcorp.com",
            company_domain="techcorp.com",
            company_name="TechCorp"
        )
        
        assignment = LeadICPAssignment(
            id=uuid4(),
            lead_id=lead.id,
            icp_id=sample_icp.id,
            tenant_id=sample_tenant.id,
            status='scored'
        )
        assignment.update_status = Mock()
        
        # Mock enrichment service
        mock_result = Mock()
        mock_result.success = True
        mock_result.enriched_data = {
            "company_description": "Leading enterprise software provider",
            "company_tech_stack": ["React", "Python", "AWS"],
            "company_employee_count": 350
        }
        mock_result.fields_added = ["company_description", "company_tech_stack", "company_employee_count"]
        mock_result.cache_hit = False
        mock_result.cost = 0.002
        
        with patch('app.services.pipeline_orchestrator.create_enrichment_service') as mock_create:
            mock_service = Mock()
            mock_service.enrich_lead_with_icp_config = AsyncMock(return_value=mock_result)
            mock_create.return_value = mock_service
            
            # Execute
            result = await orchestrator._enrich_lead(lead, assignment, sample_icp, "job-123")
        
        # Assert
        assert result['success'] is True
        assert result['fields_added'] == 3
        assert result['cost'] == 0.002
        
        # Verify lead was updated
        assert lead.company_description == "Leading enterprise software provider"
        assert lead.company_employee_count == 350
        assert lead.enrichment_completeness == 3
        assert "tech_stack" in lead.enrichment_data
        
        assignment.update_status.assert_called_once_with('enriched')
        mock_db.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_enrichment_disabled_for_icp(
        self,
        mock_db,
        sample_icp,
        sample_tenant
    ):
        """Test enrichment is skipped when disabled for ICP"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        # Disable enrichment
        sample_icp.enrichment_enabled = False
        
        lead = Lead(id=uuid4(), tenant_id=sample_tenant.id, email="test@test.com")
        assignment = LeadICPAssignment(
            id=uuid4(),
            lead_id=lead.id,
            icp_id=sample_icp.id,
            tenant_id=sample_tenant.id
        )
        
        # Mock to ensure enrichment is NOT called
        with patch('app.services.pipeline_orchestrator.create_enrichment_service') as mock_create:
            # Execute with enrichment stage
            result = await orchestrator._run_pipeline_stages(
                lead=lead,
                assignment=assignment,
                raw_lead=Mock(),
                icp=sample_icp,
                job_id=None,
                stages_to_run=['enrich']
            )
            
            # Assert enrichment was skipped
            mock_create.assert_not_called()


# ============================================================================
# TEST: Auto-Qualification
# ============================================================================

class TestAutoQualification:
    """Test automatic lead qualification logic"""
    
    @pytest.mark.asyncio
    async def test_auto_approve_high_score(
        self,
        mock_db,
        sample_icp,
        sample_tenant
    ):
        """Test auto-approval for high scores (>=80%)"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        lead = Lead(
            id=uuid4(),
            tenant_id=sample_tenant.id,
            email="test@test.com",
            email_verified=True
        )
        
        assignment = LeadICPAssignment(
            id=uuid4(),
            lead_id=lead.id,
            icp_id=sample_icp.id,
            tenant_id=sample_tenant.id,
            status='verified',
            fit_score_percentage=85.0
        )
        assignment.update_status = Mock()
        
        # Execute
        result = await orchestrator._auto_qualify(lead, assignment, sample_icp, None)
        
        # Assert
        assert result['decision'] == "qualified"
        assert result['reason'] == "auto_approved_high_score"
        assert assignment.qualified_at is not None
        
        assignment.update_status.assert_called_once_with("qualified")
        mock_db.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_pending_review_medium_score(
        self,
        mock_db,
        sample_icp,
        sample_tenant
    ):
        """Test pending review for medium scores (50-80%)"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        lead = Lead(
            id=uuid4(),
            tenant_id=sample_tenant.id,
            email="test@test.com",
            email_verified=True
        )
        
        assignment = LeadICPAssignment(
            id=uuid4(),
            lead_id=lead.id,
            icp_id=sample_icp.id,
            tenant_id=sample_tenant.id,
            status='verified',
            fit_score_percentage=65.0
        )
        assignment.update_status = Mock()
        
        # Execute
        result = await orchestrator._auto_qualify(lead, assignment, sample_icp, None)
        
        # Assert
        assert result['decision'] == "pending_review"
        assert result['reason'] == "requires_manual_review"
        
        assignment.update_status.assert_called_once_with("pending_review")
    
    @pytest.mark.asyncio
    async def test_reject_low_score(
        self,
        mock_db,
        sample_icp,
        sample_tenant
    ):
        """Test rejection for low scores (<50%)"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        lead = Lead(
            id=uuid4(),
            tenant_id=sample_tenant.id,
            email="test@test.com"
        )
        
        assignment = LeadICPAssignment(
            id=uuid4(),
            lead_id=lead.id,
            icp_id=sample_icp.id,
            tenant_id=sample_tenant.id,
            status='verified',
            fit_score_percentage=35.0
        )
        assignment.update_status = Mock()
        
        # Execute
        result = await orchestrator._auto_qualify(lead, assignment, sample_icp, None)
        
        # Assert
        assert result['decision'] == "rejected"
        assert result['reason'] == "auto_rejected_low_score"
        
        assignment.update_status.assert_called_once_with("rejected")


# ============================================================================
# TEST: Full Pipeline
# ============================================================================

class TestFullPipeline:
    """Test complete pipeline end-to-end"""
    
    @pytest.mark.asyncio
    async def test_complete_pipeline_success(
        self,
        mock_db,
        sample_raw_lead,
        sample_icp,
        sample_tenant
    ):
        """Test full pipeline with successful qualification"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        # Mock no existing lead or assignment
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.count.return_value = 1
        
        # Mock scoring engine
        score_result = Mock()
        score_result.score = 85.0
        score_result.confidence = 90.0
        score_result.breakdown = {"company_size": 25.0, "job_title": 30.0}
        
        with patch.object(orchestrator.scoring_engine, 'score_lead', return_value=score_result):
            with patch('app.services.pipeline_orchestrator.create_enrichment_service'):
                # Execute
                result = await orchestrator.process_raw_lead(
                    raw_lead=sample_raw_lead,
                    icp=sample_icp,
                    job_id="test-job-123"
                )
        
        # Assert
        assert result['success'] is True
        assert result['lead_id'] is not None
        assert result['assignment_id'] is not None
        assert 'processing_time_seconds' in result
        
        # Verify database interactions
        assert mock_db.add.call_count >= 2
        assert mock_db.commit.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_pipeline_skip_already_processed(
        self,
        mock_db,
        sample_raw_lead,
        sample_icp,
        sample_tenant
    ):
        """Test pipeline skips already processed leads"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        # Mock existing lead
        existing_lead = Lead(
            id=uuid4(),
            tenant_id=sample_tenant.id,
            email=sample_raw_lead.email
        )
        
        # Mock existing assignment
        existing_assignment = LeadICPAssignment(
            id=uuid4(),
            lead_id=existing_lead.id,
            icp_id=sample_icp.id,
            tenant_id=sample_tenant.id,
            status='qualified'
        )
        
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            existing_lead,
            existing_assignment
        ]
        
        # Execute
        result = await orchestrator.process_raw_lead(
            raw_lead=sample_raw_lead,
            icp=sample_icp,
            job_id="test-job-123"
        )
        
        # Assert
        assert result['success'] is True
        assert result['skipped'] is True
        assert result['status'] == 'qualified'
    
    @pytest.mark.asyncio
    async def test_pipeline_error_handling(
        self,
        mock_db,
        sample_raw_lead,
        sample_icp
    ):
        """Test pipeline handles errors gracefully"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        # Mock database error
        mock_db.query.side_effect = Exception("Database connection failed")
        
        # Execute
        result = await orchestrator.process_raw_lead(
            raw_lead=sample_raw_lead,
            icp=sample_icp,
            job_id="test-job-123"
        )
        
        # Assert
        assert result['success'] is False
        assert 'error' in result
        assert result['lead_id'] is None
        assert result['assignment_id'] is None


# ============================================================================
# TEST: Multi-ICP Processing
# ============================================================================

class TestMultiICPProcessing:
    """Test processing one lead against multiple ICPs"""
    
    @pytest.mark.asyncio
    async def test_same_lead_multiple_icps(
        self,
        mock_db,
        sample_raw_lead,
        sample_tenant
    ):
        """Test same lead scored differently by different ICPs"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        # Create two different ICPs
        icp1 = ICP(
            id=uuid4(),
            tenant_id=sample_tenant.id,
            name="Enterprise ICP",
            auto_approve_threshold=80.0,
            auto_reject_threshold=30.0,
            enrichment_enabled=True,
            verification_enabled=True,
            is_active=True
        )
        
        icp2 = ICP(
            id=uuid4(),
            tenant_id=sample_tenant.id,
            name="SMB ICP",
            auto_approve_threshold=70.0,
            auto_reject_threshold=30.0,
            enrichment_enabled=True,
            verification_enabled=True,
            is_active=True
        )
        
        # Mock: Same lead, different assignments
        lead = Lead(
            id=uuid4(),
            tenant_id=sample_tenant.id,
            email=sample_raw_lead.email
        )
        
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count in [1, 3]:
                return lead
            else:
                return None
        
        mock_db.query.return_value.filter.return_value.first.side_effect = side_effect
        mock_db.query.return_value.filter.return_value.count.return_value = 2
        
        # Mock different scores for each ICP
        score_result_1 = Mock(score=85.0, confidence=90.0, breakdown={})
        score_result_2 = Mock(score=35.0, confidence=85.0, breakdown={})
        
        with patch.object(orchestrator.scoring_engine, 'score_lead') as mock_score:
            with patch('app.services.pipeline_orchestrator.create_enrichment_service'):
                mock_score.return_value = score_result_1
                result1 = await orchestrator.process_raw_lead(sample_raw_lead, icp1, "job-1")
                
                mock_score.return_value = score_result_2
                result2 = await orchestrator.process_raw_lead(sample_raw_lead, icp2, "job-1")
        
        # Assert: Same lead, different assignments
        assert result1['success'] is True
        assert result2['success'] is True
        assert result1['lead_id'] == result2['lead_id']


# ============================================================================
# TEST: Raw Lead Tracking
# ============================================================================

class TestRawLeadTracking:
    """Test raw lead processing status tracking"""
    
    @pytest.mark.asyncio
    async def test_track_processed_icps(
        self,
        mock_db,
        sample_raw_lead,
        sample_icp,
        sample_tenant
    ):
        """Test tracking which ICPs have processed a raw lead"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        lead = Lead(
            id=uuid4(),
            tenant_id=sample_tenant.id,
            email=sample_raw_lead.email
        )
        
        # ✅ Mock count BEFORE execute
        mock_db.query.return_value.filter.return_value.count.return_value = 1
        
        # Execute
        await orchestrator._update_raw_lead_tracking(sample_raw_lead, sample_icp, lead)
        
        # Assert
        assert str(sample_icp.id) in sample_raw_lead.processed_by_icps
        assert sample_raw_lead.lead_id == lead.id
        assert sample_raw_lead.processed_at is not None
        
        mock_db.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_mark_complete_when_all_icps_processed(
        self,
        mock_db,
        sample_raw_lead,
        sample_tenant
    ):
        """Test marking raw lead complete when all ICPs processed"""
        orchestrator = PipelineOrchestrator(mock_db)
        
        icp1 = ICP(id=uuid4(), tenant_id=sample_tenant.id, is_active=True, name="ICP1")
        icp2 = ICP(id=uuid4(), tenant_id=sample_tenant.id, is_active=True, name="ICP2")
        
        lead = Lead(id=uuid4(), tenant_id=sample_tenant.id, email=sample_raw_lead.email)
        
        # Process with first ICP
        sample_raw_lead.processed_by_icps = []
        mock_db.query.return_value.filter.return_value.count.return_value = 2
        await orchestrator._update_raw_lead_tracking(sample_raw_lead, icp1, lead)
        assert sample_raw_lead.processing_status != "processed"
        
        # Process with second ICP
        mock_db.query.return_value.filter.return_value.count.return_value = 2
        await orchestrator._update_raw_lead_tracking(sample_raw_lead, icp2, lead)
        assert sample_raw_lead.processing_status == "processed"


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])