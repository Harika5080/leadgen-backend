# backend/app/services/enrichment_service.py
"""
Lead Enrichment Service - Sequenced Orchestration
Uses: Wappalyzer (tech stack) + SerpApi (company info) + Google Maps
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import logging
import hashlib
import requests
import json
from sqlalchemy.orm import Session
import uuid

from app.models import EnrichmentCache
from app.redis_client import redis_client

logger = logging.getLogger(__name__)


class EnrichmentResult:
    """Result of enrichment with field-level tracking"""
    
    def __init__(
        self,
        success: bool,
        fields_added: List[str] = None,
        enriched_data: Dict = None,
        cache_hit: bool = False,
        cost: float = 0.0,
        providers_used: List[str] = None,
        error: Optional[str] = None
    ):
        self.success = success
        self.fields_added = fields_added or []
        self.enriched_data = enriched_data or {}
        self.cache_hit = cache_hit
        self.cost = cost
        self.providers_used = providers_used or []
        self.error = error
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "fields_added": self.fields_added,
            "enriched_data": self.enriched_data,
            "cache_hit": self.cache_hit,
            "cost": self.cost,
            "providers_used": self.providers_used,
            "error": self.error
        }


class EnrichmentService:
    """
    Orchestrated enrichment using multiple providers
    
    Sequence:
    1. Check cache (90-day TTL, 85% target hit rate)
    2. Wappalyzer - Tech stack detection (FREE)
    3. SerpApi - Company info from Google ($0.002/query)
    4. Google Maps - Business details (if available)
    5. Store in cache
    """
    
    def __init__(
        self,
        db: Session,
        serpapi_key: str = None,
        google_maps_key: str = None,
        enable_wappalyzer: bool = True,
        enable_serpapi: bool = True,
        enable_google_maps: bool = False
    ):
        self.db = db
        self.serpapi_key = serpapi_key
        self.google_maps_key = google_maps_key
        self.cache_ttl_days = 90
        
        # Feature flags
        self.enable_wappalyzer = enable_wappalyzer
        self.enable_serpapi = enable_serpapi
        self.enable_google_maps = enable_google_maps
        
        # Wappalyzer endpoint (self-hosted or free tier)
        self.wappalyzer_endpoint = "https://api.wappalyzer.com/v2/lookup/"
        
        # Log enabled providers
        enabled = []
        if self.enable_wappalyzer:
            enabled.append("Wappalyzer")
        if self.enable_serpapi and self.serpapi_key:
            enabled.append("SerpApi")
        if self.enable_google_maps and self.google_maps_key:
            enabled.append("Google Maps")
        
        logger.info(f"Enrichment providers enabled: {', '.join(enabled) or 'None'}")
    
    async def enrich_lead(
        self,
        email: str,
        company_domain: Optional[str],
        company_name: Optional[str],
        tenant_id: str
    ) -> EnrichmentResult:
        """Enrich lead with company data and tech stack"""
        start_time = datetime.utcnow()
        
        # Determine cache key (prioritize domain, fallback to email)
        cache_key = company_domain or email
        cache_hash = self._hash_key(cache_key)
        
        # Check cache first
        try:
            cached = await self._get_from_cache(cache_hash, tenant_id)
            if cached:
                logger.info(f"Cache hit for {cache_key}")
                return EnrichmentResult(
                    success=True,
                    fields_added=list(cached.get("enriched_data", {}).keys()),
                    enriched_data=cached.get("enriched_data", {}),
                    cache_hit=True,
                    cost=0.0,
                    providers_used=cached.get("providers_used", [])
                )
        except Exception as e:
            logger.warning(f"Cache check failed for {cache_key}: {e}")
        
        # Cache miss - enrich from sources
        logger.info(f"Cache miss for {cache_key}, enriching...")
        
        enriched_data = {}
        fields_added = []
        providers_used = []
        total_cost = 0.0
        
        # Step 1: Wappalyzer - Tech Stack (FREE)
        if self.enable_wappalyzer and company_domain:
            try:
                tech_data = await self._get_tech_stack(company_domain)
                if tech_data:
                    enriched_data.update(tech_data)
                    fields_added.extend(tech_data.keys())
                    providers_used.append("wappalyzer")
                    logger.info(f"Wappalyzer: Added {len(tech_data)} fields")
            except Exception as e:
                logger.warning(f"Wappalyzer failed for {cache_key}: {e}")
        
        # Step 2: SerpApi - Company Info ($0.002)
        if self.enable_serpapi and self.serpapi_key and (company_name or company_domain):
            try:
                serp_data = await self._get_company_info_serp(
                    company_name or company_domain
                )
                if serp_data:
                    enriched_data.update(serp_data)
                    fields_added.extend(serp_data.keys())
                    providers_used.append("serpapi")
                    total_cost += 0.002
                    logger.info(f"SerpApi: Added {len(serp_data)} fields, cost=$0.002")
            except Exception as e:
                logger.warning(f"SerpApi failed for {cache_key}: {e}")
        
        # Step 3: Google Maps - Business Info
        if self.enable_google_maps and self.google_maps_key and company_name:
            try:
                maps_data = await self._get_business_info_maps(company_name)
                if maps_data:
                    enriched_data.update(maps_data)
                    fields_added.extend(maps_data.keys())
                    providers_used.append("google_maps")
                    total_cost += 0.001
                    logger.info(f"Google Maps: Added {len(maps_data)} fields, cost=$0.001")
            except Exception as e:
                logger.warning(f"Google Maps failed for {cache_key}: {e}")
        
        # Check if we got ANY data
        if not enriched_data:
            logger.warning(f"No enrichment data obtained for {cache_key}")
            return EnrichmentResult(
                success=False,
                error="All enrichment providers failed",
                fields_added=[],
                enriched_data={},
                cache_hit=False,
                cost=total_cost,
                providers_used=[]
            )
        
        # Store in cache
        try:
            await self._save_to_cache(
                cache_hash=cache_hash,
                tenant_id=tenant_id,
                enriched_data=enriched_data,
                providers_used=providers_used,
                cost=total_cost
            )
        except Exception as e:
            logger.warning(f"Failed to save to cache for {cache_key}: {e}")
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(
            f"Enrichment complete: {len(fields_added)} fields, "
            f"cost=${total_cost:.4f}, time={elapsed:.2f}s"
        )
        
        return EnrichmentResult(
            success=True,
            fields_added=list(set(fields_added)),
            enriched_data=enriched_data,
            cache_hit=False,
            cost=total_cost,
            providers_used=providers_used
        )
    
    async def enrich_lead_with_icp_config(
        self,
        email: str,
        company_domain: Optional[str],
        company_name: Optional[str],
        tenant_id: str,
        icp_id: str
    ) -> EnrichmentResult:
        """Enrich lead with ICP-specific provider configuration"""
        from app.models import ICP
        
        # Get ICP configuration
        icp = self.db.query(ICP).filter(ICP.id == uuid.UUID(icp_id)).first()
        
        if not icp or not icp.enrichment_enabled:
            logger.info(f"Enrichment disabled for ICP {icp_id}")
            return EnrichmentResult(
                success=True,
                fields_added=[],
                enriched_data={},
                cache_hit=False,
                cost=0.0,
                providers_used=[]
            )
        
        # Get ICP-specific provider configuration
        enrichment_providers = icp.enrichment_providers or {}
        
        # Override instance flags with ICP config
        use_wappalyzer = enrichment_providers.get('wappalyzer', True)
        use_serpapi = enrichment_providers.get('serpapi', True)
        use_google_maps = enrichment_providers.get('google_maps', False)
        
        # Temporarily override flags
        original_wappalyzer = self.enable_wappalyzer
        original_serpapi = self.enable_serpapi
        original_google_maps = self.enable_google_maps
        
        self.enable_wappalyzer = use_wappalyzer and original_wappalyzer
        self.enable_serpapi = use_serpapi and original_serpapi
        self.enable_google_maps = use_google_maps and original_google_maps
        
        try:
            result = await self.enrich_lead(
                email=email,
                company_domain=company_domain,
                company_name=company_name,
                tenant_id=tenant_id
            )
            return result
        finally:
            # Restore original flags
            self.enable_wappalyzer = original_wappalyzer
            self.enable_serpapi = original_serpapi
            self.enable_google_maps = original_google_maps
    
    async def _get_tech_stack(self, domain: str) -> Dict:
        """Get tech stack using direct detection"""
        try:
            tech_data = await self._detect_tech_stack_direct(domain)
            
            if tech_data:
                return {
                    "company_tech_stack": tech_data.get("technologies", []),
                    "company_tech_categories": tech_data.get("categories", []),
                    "company_cms": tech_data.get("cms"),
                    "company_analytics": tech_data.get("analytics", [])
                }
            
            return {}
        except Exception as e:
            logger.error(f"Tech stack error for {domain}: {e}")
            return {}
    
    async def _detect_tech_stack_direct(self, domain: str) -> Dict:
        """Direct tech detection by fetching website"""
        try:
            if not domain.startswith('http'):
                domain = f"https://{domain}"
            
            response = requests.get(
                domain,
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=10,
                allow_redirects=True
            )
            
            html = response.text.lower()
            headers = {k.lower(): v for k, v in response.headers.items()}
            
            technologies = []
            categories = []
            cms = None
            analytics = []
            
            # Detect CMS
            if 'wordpress' in html or 'wp-content' in html:
                cms = "WordPress"
                technologies.append("WordPress")
                categories.append("CMS")
            
            if 'shopify' in html or 'cdn.shopify.com' in html:
                cms = "Shopify"
                technologies.append("Shopify")
                categories.append("E-commerce")
            
            # Detect analytics
            if 'google-analytics.com' in html or 'gtag' in html:
                analytics.append("Google Analytics")
                technologies.append("Google Analytics")
            
            # Detect frameworks
            if 'react' in html or '__react' in html:
                technologies.append("React")
                categories.append("JavaScript Framework")
            
            return {
                "technologies": list(set(technologies)),
                "categories": list(set(categories)),
                "cms": cms,
                "analytics": analytics
            }
        except Exception as e:
            logger.error(f"Direct tech detection failed for {domain}: {e}")
            return {}
    
    async def _get_company_info_serp(self, query: str) -> Dict:
        """Get company info using SerpApi"""
        if not self.serpapi_key:
            return {}
        
        try:
            url = "https://serpapi.com/search"
            
            params = {
                "api_key": self.serpapi_key,
                "q": f"{query} company",
                "num": 1,
                "engine": "google"
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            enriched = {}
            
            # Extract knowledge graph
            knowledge_graph = data.get("knowledge_graph", {})
            
            if knowledge_graph:
                if "description" in knowledge_graph:
                    enriched["company_description"] = knowledge_graph["description"]
                if "type" in knowledge_graph:
                    enriched["company_type"] = knowledge_graph["type"]
                if "founded" in knowledge_graph:
                    enriched["company_founded"] = knowledge_graph["founded"]
                if "headquarters" in knowledge_graph:
                    enriched["company_headquarters"] = knowledge_graph["headquarters"]
                if "employees" in knowledge_graph:
                    enriched["company_employee_count"] = knowledge_graph["employees"]
            
            return enriched
        except Exception as e:
            logger.error(f"SerpApi error for {query}: {e}")
            return {}
    
    async def _get_business_info_maps(self, company_name: str) -> Dict:
        """Get business info from Google Maps API"""
        if not self.google_maps_key:
            return {}
        
        try:
            url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
            
            params = {
                "key": self.google_maps_key,
                "query": company_name
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get("status") != "OK":
                return {}
            
            results = data.get("results", [])
            if not results:
                return {}
            
            place = results[0]
            enriched = {}
            
            if "formatted_address" in place:
                enriched["company_address"] = place["formatted_address"]
            if "rating" in place:
                enriched["company_rating"] = place["rating"]
            
            return enriched
        except Exception as e:
            logger.error(f"Google Maps error for {company_name}: {e}")
            return {}
    
    async def _get_from_cache(self, cache_hash: str, tenant_id: str) -> Optional[Dict]:
        """Get enrichment from cache"""
        cache_key = f"enrich:{tenant_id}:{cache_hash}"
        
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except:
            pass
        
        cached = self.db.query(EnrichmentCache).filter(
            EnrichmentCache.cache_key_hash == cache_hash,
            EnrichmentCache.tenant_id == uuid.UUID(tenant_id),
            EnrichmentCache.expires_at > datetime.utcnow()
        ).first()
        
        if cached:
            result = {
                "enriched_data": cached.enrichment_data,
                "providers_used": cached.enrichment_data.get("_providers", [])
            }
            
            try:
                await redis_client.setex(cache_key, 86400, json.dumps(result))
            except:
                pass
            
            cached.hit_count = (cached.hit_count or 0) + 1
            self.db.commit()
            
            return result
        
        return None
    
    async def _save_to_cache(
        self,
        cache_hash: str,
        tenant_id: str,
        enriched_data: Dict,
        providers_used: List[str],
        cost: float
    ):
        """Save enrichment to cache"""
        enriched_data["_providers"] = providers_used
        enriched_data["_cached_at"] = datetime.utcnow().isoformat()
        
        completeness = len([v for v in enriched_data.values() if v]) / len(enriched_data) * 100
        
        cache_entry = EnrichmentCache(
            id=uuid.uuid4(),
            tenant_id=uuid.UUID(tenant_id),
            cache_type="company_enrichment",
            cache_key_hash=cache_hash,
            enrichment_data=enriched_data,
            provider=",".join(providers_used),
            api_cost=Decimal(str(cost)),
            completeness_score=Decimal(str(completeness)),
            hit_count=0,
            expires_at=datetime.utcnow() + timedelta(days=self.cache_ttl_days),
            created_at=datetime.utcnow()
        )
        
        self.db.add(cache_entry)
        self.db.commit()
    
    def _hash_key(self, key: str) -> str:
        """Generate cache key hash"""
        return hashlib.sha256(key.encode()).hexdigest()


def create_enrichment_service(
    db: Session,
    serpapi_key: str = None,
    google_maps_key: str = None,
    enable_wappalyzer: bool = None,
    enable_serpapi: bool = None,
    enable_google_maps: bool = None
) -> EnrichmentService:
    """Create enrichment service instance"""
    import os
    
    if enable_wappalyzer is None:
        enable_wappalyzer = os.getenv("ENABLE_WAPPALYZER", "true").lower() == "true"
    
    if enable_serpapi is None:
        enable_serpapi = os.getenv("ENABLE_SERPAPI", "true").lower() == "true"
    
    if enable_google_maps is None:
        enable_google_maps = os.getenv("ENABLE_GOOGLE_MAPS", "false").lower() == "true"
    
    return EnrichmentService(
        db=db,
        serpapi_key=serpapi_key or os.getenv("SERPAPI_API_KEY"),
        google_maps_key=google_maps_key or os.getenv("GOOGLE_MAPS_API_KEY"),
        enable_wappalyzer=enable_wappalyzer,
        enable_serpapi=enable_serpapi,
        enable_google_maps=enable_google_maps
    )
