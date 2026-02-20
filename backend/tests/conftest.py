# tests/conftest.py - CORRECTED

import pytest
import sys
from datetime import datetime
from uuid import uuid4
from unittest.mock import Mock, MagicMock, AsyncMock, patch

from sqlalchemy.orm import Session

# Mock redis
mock_redis = MagicMock()
mock_redis.get = AsyncMock(return_value=None)
mock_redis.setex = AsyncMock(return_value=True)
sys.modules["app.redis_client"] = MagicMock()
sys.modules["app.redis_client"].redis_client = mock_redis

# Mock EnrichmentCache
try:
    from app.models import EnrichmentCache
except:
    if "app.models" not in sys.modules:
        sys.modules["app.models"] = MagicMock()
    sys.modules["app.models"].EnrichmentCache = MagicMock()

from app.models import Tenant, ICP, RawLead, Lead, LeadICPAssignment

@pytest.fixture
def mock_db():
    """Mock DB - count() returns REAL integer 1"""
    db = Mock(spec=Session)
    
    chain = Mock()
    chain.filter = Mock(return_value=chain)
    chain.count = Mock(return_value=1)
    chain.first = Mock(return_value=None)
    chain.all = Mock(return_value=[])
    chain.order_by = Mock(return_value=chain)
    
    db.query = Mock(return_value=chain)
    db.add = Mock()
    db.flush = Mock()
    db.commit = Mock()
    db.rollback = Mock()
    
    return db


@pytest.fixture(autouse=True)
def mock_scoring_engine():
    """Auto-mock ICPScoringEngine"""
    with patch('app.services.pipeline_orchestrator.ICPScoringEngine') as m:
        m.return_value = Mock(score_lead=Mock())
        yield m.return_value


@pytest.fixture(autouse=True)
def mock_enrichment_service():
    """Mock enrichment service"""
    async def mock_enrich(*args, **kwargs):
        from app.services.enrichment_service import EnrichmentResult
        return EnrichmentResult(
            success=True,
            enriched_data={},
            fields_added=[],
            cache_hit=False,
            cost=0.0
        )
    
    with patch('app.services.pipeline_orchestrator.create_enrichment_service') as m:
        m.return_value = Mock(enrich_lead_with_icp_config=AsyncMock(side_effect=mock_enrich))
        yield m


@pytest.fixture(autouse=True)
def mock_lead_stage_activity():
    """Auto-mock LeadStageActivity"""
    def create_mock(*args, **kwargs):
        valid = {
            'id', 'tenant_id', 'lead_id', 'icp_id', 'assignment_id',
            'stage', 'from_stage', 'to_stage', 'details', 'user_id', 'timestamp'
        }
        invalid = set(kwargs.keys()) - valid
        if invalid:
            raise TypeError(f"'{list(invalid)[0]}' is an invalid keyword argument for LeadStageActivity")
        m = MagicMock()
        m.id = uuid4()
        for k, v in kwargs.items():
            setattr(m, k, v)
        return m
    
    with patch('app.models.LeadStageActivity', side_effect=create_mock):
        yield


@pytest.fixture(autouse=True)
def mock_assignment_update_status():
    """Add update_status method"""
    def update(self, new_status):
        self.status = new_status
        self.bucket = new_status
    
    if not hasattr(LeadICPAssignment, 'update_status'):
        LeadICPAssignment.update_status = update
        yield
        delattr(LeadICPAssignment, 'update_status')
    else:
        yield


@pytest.fixture(autouse=True)
def auto_generate_model_ids():
    """Auto-generate IDs for models"""
    orig_lead = Lead.__init__
    orig_assign = LeadICPAssignment.__init__
    
    def lead_init(self, *args, **kwargs):
        orig_lead(self, *args, **kwargs)
        if not hasattr(self, 'id') or self.id is None:
            self.id = uuid4()
    
    def assign_init(self, *args, **kwargs):
        orig_assign(self, *args, **kwargs)
        if not hasattr(self, 'id') or self.id is None:
            self.id = uuid4()
    
    Lead.__init__ = lead_init
    LeadICPAssignment.__init__ = assign_init
    yield
    Lead.__init__ = orig_lead
    LeadICPAssignment.__init__ = orig_assign


@pytest.fixture
def sample_tenant():
    return Tenant(
        id=uuid4(),
        name="Test Co",
        domain="test.com",
        api_key_hash="hash123",
        status="active"
    )


@pytest.fixture
def sample_icp(sample_tenant):
    return ICP(
        id=uuid4(),
        tenant_id=sample_tenant.id,
        name="Test ICP",
        is_active=True,
        auto_approve_threshold=80.0,
        review_threshold=50.0,
        auto_reject_threshold=30.0,
        enrichment_enabled=True,
        enrichment_cost_per_lead=0.05,
        enrichment_providers={"wappalyzer": True, "serpapi": True},
        verification_enabled=True,
        verification_cost_per_lead=0.01,
        preferred_scrapers=["linkedin"]
    )


@pytest.fixture
def sample_raw_lead(sample_tenant):
    return RawLead(
        id=uuid4(),
        tenant_id=sample_tenant.id,
        source_name="linkedin_scraper",
        source_url="https://linkedin.com/in/test",
        scraper_type="crawlee",
        email="test@test.com",
        first_name="Test",
        last_name="User",
        job_title="Engineer",
        company_name="TestCorp",
        company_domain="testcorp.com",
        company_size="50-100",
        company_industry="Tech",
        city="SF",
        state="CA",
        country="USA",
        status="pending",
        processing_status="pending",
        processed_by_icps=[],
        scraped_data={},
        enrichment_data={}
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: unit tests")
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "slow: slow running tests")