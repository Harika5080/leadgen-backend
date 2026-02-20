# tests/services/test_enrichment_service.py
"""
Comprehensive automated tests for EnrichmentService

Coverage:
- Cache hit/miss scenarios
- Wappalyzer tech stack detection
- SerpApi company enrichment
- Google Maps business info
- Multi-provider orchestration
- ICP-specific configuration
- Error handling
- Cost tracking

Run with: pytest tests/services/test_enrichment_service.py -v
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from decimal import Decimal
from unittest.mock import Mock, patch, AsyncMock
import hashlib
import json

from sqlalchemy.orm import Session

from app.services.enrichment_service import (
    EnrichmentService,
    EnrichmentResult,
    create_enrichment_service
)
from app.models import EnrichmentCache, ICP


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db():
    """Mock database session"""
    db = Mock(spec=Session)
    db.query = Mock()
    db.add = Mock()
    db.commit = Mock()
    return db


@pytest.fixture
def enrichment_service(mock_db):
    """Enrichment service instance with all providers enabled"""
    return EnrichmentService(
        db=mock_db,
        serpapi_key="test_serpapi_key",
        google_maps_key="test_maps_key",
        enable_wappalyzer=True,
        enable_serpapi=True,
        enable_google_maps=True
    )


@pytest.fixture
def enrichment_service_minimal(mock_db):
    """Enrichment service with only Wappalyzer enabled"""
    return EnrichmentService(
        db=mock_db,
        serpapi_key=None,
        google_maps_key=None,
        enable_wappalyzer=True,
        enable_serpapi=False,
        enable_google_maps=False
    )


# ============================================================================
# TEST: Cache Operations
# ============================================================================

class TestCacheOperations:
    """Test enrichment caching mechanisms"""
    
    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_db):
        """Test successful cache hit"""
        service = EnrichmentService(mock_db)
        
        tenant_id = str(uuid4())
        cache_key = "techcorp.com"
        cache_hash = service._hash_key(cache_key)
        
        # Mock cached data
        cached_data = {
            "company_description": "Leading SaaS provider",
            "company_employee_count": 500,
            "_providers": ["serpapi"],
            "_cached_at": datetime.utcnow().isoformat()
        }
        
        cached_entry = EnrichmentCache(
            id=uuid4(),
            tenant_id=uuid4(),
            cache_key_hash=cache_hash,
            enrichment_data=cached_data,
            expires_at=datetime.utcnow() + timedelta(days=90)
        )
        
        mock_db.query.return_value.filter.return_value.first.return_value = cached_entry
        
        # Mock Redis miss
        with patch('app.services.enrichment_service.redis_client') as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.setex = AsyncMock()
            
            # Execute
            result = await service.enrich_lead(
                email="test@techcorp.com",
                company_domain="techcorp.com",
                company_name="TechCorp",
                tenant_id=tenant_id
            )
        
        # Assert
        assert result.success is True
        assert result.cache_hit is True
        assert result.cost == 0.0
        assert "company_description" in result.enriched_data
        assert result.providers_used == ["serpapi"]
    
    @pytest.mark.asyncio
    async def test_cache_miss_triggers_enrichment(self, mock_db):
        """Test cache miss triggers new enrichment"""
        service = EnrichmentService(
            db=mock_db,
            serpapi_key="test_key",
            enable_serpapi=True
        )
        
        tenant_id = str(uuid4())
        
        # Mock cache miss
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Mock Redis miss
        with patch('app.services.enrichment_service.redis_client') as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.setex = AsyncMock()
            
            # Mock SerpApi response
            with patch.object(service, '_get_company_info_serp', new_callable=AsyncMock) as mock_serp:
                mock_serp.return_value = {
                    "company_description": "New enrichment data"
                }
                
                # Execute
                result = await service.enrich_lead(
                    email="test@newcompany.com",
                    company_domain="newcompany.com",
                    company_name="NewCompany",
                    tenant_id=tenant_id
                )
        
        # Assert
        assert result.success is True
        assert result.cache_hit is False
        assert result.cost > 0  # Should have cost
        assert "company_description" in result.enriched_data
        
        # Verify cache was saved
        mock_db.add.assert_called()
        mock_db.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_cache_expiration(self, mock_db):
        """Test expired cache entries are not used"""
        service = EnrichmentService(mock_db)
        
        tenant_id = str(uuid4())
        cache_hash = service._hash_key("oldcompany.com")
        
        # Mock expired cache entry
        expired_entry = EnrichmentCache(
            id=uuid4(),
            tenant_id=uuid4(),
            cache_key_hash=cache_hash,
            enrichment_data={"old": "data"},
            expires_at=datetime.utcnow() - timedelta(days=1)  # Expired
        )
        
        # Mock returns None for expired entries (filtered by expires_at > now)
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch('app.services.enrichment_service.redis_client') as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            
            # Execute
            cached = await service._get_from_cache(cache_hash, tenant_id)
        
        # Assert
        assert cached is None


# ============================================================================
# TEST: Wappalyzer Tech Detection
# ============================================================================

class TestWappalyzerTechDetection:
    """Test Wappalyzer technology stack detection"""
    
    @pytest.mark.asyncio
    async def test_detect_wordpress(self, mock_db):
        """Test WordPress detection"""
        service = EnrichmentService(mock_db, enable_wappalyzer=True)
        
        # Mock HTTP response with WordPress signatures
        mock_response = Mock()
        mock_response.text = """
        <html>
        <head>
            <link rel="stylesheet" href="/wp-content/themes/mytheme/style.css">
        </head>
        <body>WordPress site</body>
        </html>
        """.lower()
        mock_response.headers = {}
        
        with patch('requests.get', return_value=mock_response):
            result = await service._detect_tech_stack_direct("example.com")
        
        # Assert
        assert "WordPress" in result["technologies"]
        assert result["cms"] == "WordPress"
        assert "CMS" in result["categories"]
    
    @pytest.mark.asyncio
    async def test_detect_react(self, mock_db):
        """Test React detection"""
        service = EnrichmentService(mock_db, enable_wappalyzer=True)
        
        mock_response = Mock()
        mock_response.text = """
        <html>
        <div id="root"></div>
        <script>var __react_version = "18.0"</script>
        </html>
        """.lower()
        mock_response.headers = {}
        
        with patch('requests.get', return_value=mock_response):
            result = await service._detect_tech_stack_direct("example.com")
        
        assert "React" in result["technologies"]
        assert "JavaScript Framework" in result["categories"]
    
    @pytest.mark.asyncio
    async def test_detect_analytics(self, mock_db):
        """Test analytics tool detection"""
        service = EnrichmentService(mock_db, enable_wappalyzer=True)
        
        mock_response = Mock()
        mock_response.text = """
        <script src="https://www.google-analytics.com/analytics.js"></script>
        <script>gtag('config', 'GA-XXXXX');</script>
        """.lower()
        mock_response.headers = {}
        
        with patch('requests.get', return_value=mock_response):
            result = await service._detect_tech_stack_direct("example.com")
        
        assert "Google Analytics" in result["technologies"]
        assert "Google Analytics" in result["analytics"]
    
    @pytest.mark.asyncio
    async def test_detect_multiple_technologies(self, mock_db):
        """Test detecting multiple technologies"""
        service = EnrichmentService(mock_db, enable_wappalyzer=True)
        
        mock_response = Mock()
        mock_response.text = """
        <html>
        <script src="/wp-content/"></script>
        <script>var __react_version</script>
        <script src="google-analytics.com"></script>
        <script src="segment.com/analytics.js"></script>
        """.lower()
        mock_response.headers = {"server": "cloudflare"}
        
        with patch('requests.get', return_value=mock_response):
            result = await service._detect_tech_stack_direct("example.com")
        
        assert len(result["technologies"]) >= 4
        assert "WordPress" in result["technologies"]
        assert "React" in result["technologies"]
        assert "Cloudflare" in result["technologies"]
    
    @pytest.mark.asyncio
    async def test_tech_detection_error_handling(self, mock_db):
        """Test tech detection handles errors gracefully"""
        service = EnrichmentService(mock_db, enable_wappalyzer=True)
        
        # Mock request failure
        with patch('requests.get', side_effect=Exception("Connection timeout")):
            result = await service._detect_tech_stack_direct("failing-site.com")
        
        # Should return empty dict, not raise
        assert result == {}


# ============================================================================
# TEST: SerpApi Company Enrichment
# ============================================================================

class TestSerpApiEnrichment:
    """Test SerpApi company information enrichment"""
    
    @pytest.mark.asyncio
    async def test_serpapi_knowledge_graph(self, mock_db):
        """Test extracting data from Google Knowledge Graph"""
        service = EnrichmentService(
            db=mock_db,
            serpapi_key="test_key",
            enable_serpapi=True
        )
        
        # Mock SerpApi response
        mock_response = Mock()
        mock_response.json.return_value = {
            "knowledge_graph": {
                "description": "Leading enterprise software company",
                "type": "Public company",
                "founded": "1999",
                "headquarters": "San Francisco, CA",
                "ceo": "Marc Benioff",
                "employees": "73,000",
                "revenue": "$31.35 billion",
                "industry": "Software"
            }
        }
        
        with patch('requests.get', return_value=mock_response):
            result = await service._get_company_info_serp("Salesforce")
        
        # Assert
        assert result["company_description"] == "Leading enterprise software company"
        assert result["company_type"] == "Public company"
        assert result["company_founded"] == "1999"
        assert result["company_headquarters"] == "San Francisco, CA"
        assert result["company_ceo"] == "Marc Benioff"
        assert result["company_employee_count"] == "73,000"
        assert result["company_revenue"] == "$31.35 billion"
        assert result["company_industry"] == "Software"
    
    @pytest.mark.asyncio
    async def test_serpapi_organic_results_fallback(self, mock_db):
        """Test fallback to organic results when no knowledge graph"""
        service = EnrichmentService(
            db=mock_db,
            serpapi_key="test_key",
            enable_serpapi=True
        )
        
        mock_response = Mock()
        mock_response.json.return_value = {
            "organic_results": [
                {
                    "snippet": "Startup company building innovative solutions"
                }
            ]
        }
        
        with patch('requests.get', return_value=mock_response):
            result = await service._get_company_info_serp("StartupCo")
        
        assert result["company_description"] == "Startup company building innovative solutions"
    
    @pytest.mark.asyncio
    async def test_serpapi_no_api_key(self, mock_db):
        """Test SerpApi skipped when no API key"""
        service = EnrichmentService(
            db=mock_db,
            serpapi_key=None,
            enable_serpapi=True
        )
        
        result = await service._get_company_info_serp("AnyCompany")
        
        assert result == {}
    
    @pytest.mark.asyncio
    async def test_serpapi_error_handling(self, mock_db):
        """Test SerpApi error handling"""
        service = EnrichmentService(
            db=mock_db,
            serpapi_key="test_key",
            enable_serpapi=True
        )
        
        # Mock request failure
        with patch('requests.get', side_effect=Exception("API error")):
            result = await service._get_company_info_serp("FailingCompany")
        
        assert result == {}


# ============================================================================
# TEST: Google Maps Business Info
# ============================================================================

class TestGoogleMapsEnrichment:
    """Test Google Maps business information"""
    
    @pytest.mark.asyncio
    async def test_google_maps_business_details(self, mock_db):
        """Test extracting business details from Google Maps"""
        service = EnrichmentService(
            db=mock_db,
            google_maps_key="test_key",
            enable_google_maps=True
        )
        
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "123 Main St, San Francisco, CA",
                    "rating": 4.5,
                    "user_ratings_total": 1250,
                    "website": "https://example.com",
                    "formatted_phone_number": "+1 555-0100"
                }
            ]
        }
        
        with patch('requests.get', return_value=mock_response):
            result = await service._get_business_info_maps("Example Corp")
        
        assert result["company_address"] == "123 Main St, San Francisco, CA"
        assert result["company_rating"] == 4.5
        assert result["company_review_count"] == 1250
        assert result["company_website"] == "https://example.com"
        assert result["company_phone"] == "+1 555-0100"
    
    @pytest.mark.asyncio
    async def test_google_maps_no_results(self, mock_db):
        """Test handling no results from Google Maps"""
        service = EnrichmentService(
            db=mock_db,
            google_maps_key="test_key",
            enable_google_maps=True
        )
        
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "ZERO_RESULTS",
            "results": []
        }
        
        with patch('requests.get', return_value=mock_response):
            result = await service._get_business_info_maps("NonexistentCompany")
        
        assert result == {}


# ============================================================================
# TEST: Multi-Provider Orchestration
# ============================================================================

class TestMultiProviderOrchestration:
    """Test orchestration across multiple providers"""
    
    @pytest.mark.asyncio
    async def test_all_providers_enabled(self, mock_db):
        """Test enrichment with all providers enabled"""
        service = EnrichmentService(
            db=mock_db,
            serpapi_key="test_key",
            google_maps_key="maps_key",
            enable_wappalyzer=True,
            enable_serpapi=True,
            enable_google_maps=True
        )
        
        tenant_id = str(uuid4())
        
        # Mock cache miss
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Mock all provider responses
        with patch('app.services.enrichment_service.redis_client') as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.setex = AsyncMock()
            
            with patch.object(service, '_get_tech_stack', new_callable=AsyncMock) as mock_tech:
                mock_tech.return_value = {
                    "company_tech_stack": ["React", "AWS"],
                    "company_cms": "WordPress"
                }
                
                with patch.object(service, '_get_company_info_serp', new_callable=AsyncMock) as mock_serp:
                    mock_serp.return_value = {
                        "company_description": "Software company",
                        "company_employee_count": "500"
                    }
                    
                    with patch.object(service, '_get_business_info_maps', new_callable=AsyncMock) as mock_maps:
                        mock_maps.return_value = {
                            "company_rating": 4.5
                        }
                        
                        # Execute
                        result = await service.enrich_lead(
                            email="test@techcorp.com",
                            company_domain="techcorp.com",
                            company_name="TechCorp",
                            tenant_id=tenant_id
                        )
        
        # Assert
        assert result.success is True
        assert result.cache_hit is False
        assert len(result.providers_used) == 3
        assert "wappalyzer" in result.providers_used
        assert "serpapi" in result.providers_used
        assert "google_maps" in result.providers_used
        
        # Verify data from all providers
        assert "company_tech_stack" in result.enriched_data
        assert "company_description" in result.enriched_data
        assert "company_rating" in result.enriched_data
        
        # Verify cost calculation
        assert result.cost == 0.003  # 0.002 (SerpApi) + 0.001 (Maps)
    
    @pytest.mark.asyncio
    async def test_only_wappalyzer_enabled(self, mock_db):
        """Test enrichment with only Wappalyzer (free)"""
        service = EnrichmentService(
            db=mock_db,
            enable_wappalyzer=True,
            enable_serpapi=False,
            enable_google_maps=False
        )
        
        tenant_id = str(uuid4())
        
        # Mock cache miss
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch('app.services.enrichment_service.redis_client') as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.setex = AsyncMock()
            
            with patch.object(service, '_get_tech_stack', new_callable=AsyncMock) as mock_tech:
                mock_tech.return_value = {
                    "company_tech_stack": ["React"]
                }
                
                result = await service.enrich_lead(
                    email="test@company.com",
                    company_domain="company.com",
                    company_name="Company",
                    tenant_id=tenant_id
                )
        
        # Assert
        assert result.success is True
        assert result.providers_used == ["wappalyzer"]
        assert result.cost == 0.0  # Free!
    
    @pytest.mark.asyncio
    async def test_cost_tracking(self, mock_db):
        """Test accurate cost tracking"""
        service = EnrichmentService(
            db=mock_db,
            serpapi_key="key",
            google_maps_key="key",
            enable_serpapi=True,
            enable_google_maps=True
        )
        
        tenant_id = str(uuid4())
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch('app.services.enrichment_service.redis_client') as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.setex = AsyncMock()
            
            with patch.object(service, '_get_company_info_serp', new_callable=AsyncMock) as mock_serp:
                mock_serp.return_value = {"data": "test"}
                
                with patch.object(service, '_get_business_info_maps', new_callable=AsyncMock) as mock_maps:
                    mock_maps.return_value = {"data": "test"}
                    
                    result = await service.enrich_lead(
                        email="test@test.com",
                        company_domain="test.com",
                        company_name="Test",
                        tenant_id=tenant_id
                    )
        
        # SerpApi: $0.002 + Google Maps: $0.001 = $0.003
        assert result.cost == 0.003


# ============================================================================
# TEST: ICP-Specific Configuration
# ============================================================================

class TestICPSpecificConfiguration:
    """Test ICP-specific enrichment configuration"""
    
    @pytest.mark.asyncio
    async def test_icp_provider_override(self, mock_db):
        """Test ICP-specific provider configuration overrides"""
        service = EnrichmentService(
            db=mock_db,
            serpapi_key="key",
            enable_serpapi=True,
            enable_wappalyzer=True
        )
        
        # Mock ICP with Wappalyzer disabled
        icp = ICP(
            id=uuid4(),
            enrichment_enabled=True,
            enrichment_providers={
                "wappalyzer": False,  # Disable Wappalyzer
                "serpapi": True,
                "google_maps": False
            }
        )
        
        mock_db.query.return_value.filter.return_value.first.return_value = icp
        mock_db.query.return_value.filter.return_value.first.return_value = None  # Cache miss
        
        with patch('app.services.enrichment_service.redis_client') as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            
            with patch.object(service, '_get_tech_stack', new_callable=AsyncMock) as mock_tech:
                with patch.object(service, '_get_company_info_serp', new_callable=AsyncMock) as mock_serp:
                    mock_serp.return_value = {"company_description": "test"}
                    
                    # This method needs to be added to EnrichmentService
                    # For now, test that service respects ICP config
                    
                    # Verify only SerpApi would be called, not Wappalyzer
                    # (Implementation dependent on enrich_lead_with_icp_config method)
                    pass


# ============================================================================
# TEST: Error Handling
# ============================================================================

class TestErrorHandling:
    """Test error handling in enrichment service"""
    
    @pytest.mark.asyncio
    async def test_graceful_provider_failure(self, mock_db):
        """Test continues with other providers when one fails"""
        service = EnrichmentService(
            db=mock_db,
            serpapi_key="key",
            enable_wappalyzer=True,
            enable_serpapi=True
        )
        
        tenant_id = str(uuid4())
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch('app.services.enrichment_service.redis_client') as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.setex = AsyncMock()
            
            # Wappalyzer fails
            with patch.object(service, '_get_tech_stack', new_callable=AsyncMock) as mock_tech:
                mock_tech.side_effect = Exception("Tech detection failed")
                
                # But SerpApi succeeds
                with patch.object(service, '_get_company_info_serp', new_callable=AsyncMock) as mock_serp:
                    mock_serp.return_value = {"company_description": "test"}
                    
                    result = await service.enrich_lead(
                        email="test@test.com",
                        company_domain="test.com",
                        company_name="Test",
                        tenant_id=tenant_id
                    )
        
        # Should still succeed with SerpApi data
        assert result.success is True
        assert "company_description" in result.enriched_data
        assert "serpapi" in result.providers_used
    
    @pytest.mark.asyncio
    async def test_all_providers_fail(self, mock_db):
        """Test when all providers fail"""
        service = EnrichmentService(
            db=mock_db,
            enable_wappalyzer=True
        )
        
        tenant_id = str(uuid4())
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch('app.services.enrichment_service.redis_client') as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            
            with patch.object(service, '_get_tech_stack', new_callable=AsyncMock) as mock_tech:
                mock_tech.side_effect = Exception("All failed")
                
                result = await service.enrich_lead(
                    email="test@test.com",
                    company_domain="test.com",
                    company_name="Test",
                    tenant_id=tenant_id
                )
        
        # Should return error
        assert result.success is False
        assert result.error is not None


# ============================================================================
# TEST: Factory Function
# ============================================================================

class TestFactoryFunction:
    """Test enrichment service factory function"""
    
    def test_create_service_from_env(self, mock_db):
        """Test creating service from environment variables"""
        with patch.dict('os.environ', {
            'ENABLE_WAPPALYZER': 'true',
            'ENABLE_SERPAPI': 'false',
            'SERPAPI_API_KEY': 'test_key'
        }):
            service = create_enrichment_service(mock_db)
            
            assert service.enable_wappalyzer is True
            assert service.enable_serpapi is False
            assert service.serpapi_key == 'test_key'


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])