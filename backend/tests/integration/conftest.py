# tests/integration/conftest.py
"""Integration test fixtures - Real DB + Some Mocked Services"""

import pytest
import os
import sys
from unittest.mock import MagicMock, AsyncMock, patch, Mock
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from uuid import uuid4

# Mock redis BEFORE importing
mock_redis = MagicMock()
mock_redis.get = AsyncMock(return_value=None)
mock_redis.setex = AsyncMock(return_value=True)
sys.modules["app.redis_client"] = MagicMock()
sys.modules["app.redis_client"].redis_client = mock_redis

try:
    from app.models import EnrichmentCache
except:
    if "app.models" not in sys.modules:
        sys.modules["app.models"] = MagicMock()
    sys.modules["app.models"].EnrichmentCache = MagicMock()

from app.models import Base, Tenant, ICP, RawLead, Lead, LeadICPAssignment

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://leadgen:leadgen123@db:5432/leadgen_test"
)


@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine (once per test session)"""
    engine = create_engine(TEST_DATABASE_URL)
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    yield engine
    
    # ✅ Cleanup: Only truncate tables that exist
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
        """))
        existing_tables = {row[0] for row in result}
        
        # Tables we want to clean (in order)
        all_tables = [
            'lead_rejection_tracking',
            'lead_icp_assignments', 
            'leads',
            'raw_leads',
            'icps',
            'tenants'
        ]
        
        # Only clean tables that exist
        to_clean = [t for t in all_tables if t in existing_tables]
        
        if to_clean:
            conn.execute(text(f"""
                TRUNCATE TABLE {', '.join(to_clean)}
                RESTART IDENTITY CASCADE;
            """))
    
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    """Real database session with transaction rollback"""
    connection = test_engine.connect()
    transaction = connection.begin()
    
    Session = sessionmaker(bind=connection)
    session = Session()
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


# Auto-use mocks

@pytest.fixture(autouse=True)
def mock_scoring_engine():
    """Auto-mock ICPScoringEngine"""
    with patch('app.services.pipeline_orchestrator.ICPScoringEngine') as mock_class:
        mock_instance = Mock()
        mock_score_result = Mock()
        mock_score_result.score = 85.0
        mock_score_result.confidence = 90.0
        mock_score_result.breakdown = {
            "company_size": 30.0,
            "job_title": 25.0,
            "industry": 15.0,
            "location": 10.0,
            "seniority": 5.0
        }
        mock_instance.score_lead = Mock(return_value=mock_score_result)
        mock_class.return_value = mock_instance
        yield mock_instance


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
            raise TypeError(f"'{list(invalid)[0]}' is an invalid keyword argument")
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


# Real data fixtures

@pytest.fixture
def real_tenant(db_session):
    """Create a real tenant in test DB"""
    tenant = Tenant(
        id=uuid4(),
        name="Integration Test Company",
        domain="inttest.com",
        api_key_hash="test_hash_" + str(uuid4())[:8],
        status="active"
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def real_icp(db_session, real_tenant):
    """Create a real ICP in test DB"""
    icp = ICP(
        id=uuid4(),
        tenant_id=real_tenant.id,
        name="Integration Test ICP",
        description="Test ICP for integration testing",
        is_active=True,
        auto_approve_threshold=80.0,
        review_threshold=50.0,
        auto_reject_threshold=30.0,
        enrichment_enabled=False,
        enrichment_cost_per_lead=0.05,
        enrichment_providers={"wappalyzer": False, "serpapi": False, "google_maps": False},
        verification_enabled=False,
        verification_cost_per_lead=0.01,
        preferred_scrapers=["test"]
    )
    db_session.add(icp)
    db_session.commit()
    db_session.refresh(icp)
    return icp


@pytest.fixture
def real_raw_lead(db_session, real_tenant):
    """Create a real raw lead in test DB"""
    raw_lead = RawLead(
        id=uuid4(),
        tenant_id=real_tenant.id,
        source_name="integration_test",
        source_url="https://test.com/lead",
        scraper_type="manual",
        email="test@integration.com",
        first_name="Test",
        last_name="Integration",
        phone="+1-555-0199",
        job_title="Test Engineer",
        linkedin_url="https://linkedin.com/in/test",
        company_name="TestCorp",
        company_domain="testcorp.com",
        company_website="https://testcorp.com",
        company_size="50-100",  # ✅ None for integer field
        company_industry="Technology",
        city="Test City",
        state="TC",
        country="USA",
        status="pending",
        processing_status="pending",
        processed_by_icps=[],
        scraped_data={},
        enrichment_data={}
    )
    db_session.add(raw_lead)
    db_session.commit()
    db_session.refresh(raw_lead)
    return raw_lead


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: Integration tests with real database and services"
    )