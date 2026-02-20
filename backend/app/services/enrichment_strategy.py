# backend/app/services/enrichment_strategy.py
"""
Smart Enrichment Strategy Service - BULLETPROOF VERSION
Handles ICP as both object and dict
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentPlan:
    """Plan for enriching a lead"""
    should_enrich: bool
    reason: str
    providers_to_use: List[str]
    fields_to_enrich: List[str]
    estimated_cost: float
    priority: str


class EnrichmentStrategyService:
    """Smart enrichment decisions"""
    
    SOURCE_QUALITY = {
        "apollo": "high",
        "hunter": "high",
        "peopledatalabs": "high",
        "clearbit": "high",
        "linkedin_scraper": "medium",
        "website_scraper": "low",
        "csv_upload": "unknown",
        "webhook": "unknown",
        "manual": "unknown"
    }
    
    REFRESH_INTERVALS = {
        "high": 90,
        "medium": 60,
        "low": 30,
        "unknown": 30
    }
    
    PROVIDER_COSTS = {
        "wappalyzer": 0.0,
        "serpapi": 0.002,
        "google_kg": 0.0,
    }
    
    def create_enrichment_plan(self, raw_lead, lead, icp=None) -> EnrichmentPlan:
        """Create smart enrichment plan - BULLETPROOF"""
        
        # Get source quality
        source_name = getattr(raw_lead, 'source_name', None) or "unknown"
        source_quality = self.SOURCE_QUALITY.get(source_name, "unknown")
        
        email = getattr(lead, 'email', 'unknown')
        logger.info(f"📋 Creating enrichment plan for {email} (source: {source_name}, quality: {source_quality})")
        
        # ✅ Skip high-quality sources if fresh
        if source_quality == "high":
            enriched_at = getattr(lead, 'enriched_at', None)
            if enriched_at:
                age_days = (datetime.utcnow() - enriched_at).days
                if age_days < self.REFRESH_INTERVALS['high']:
                    return EnrichmentPlan(
                        should_enrich=False,
                        reason=f"High-quality source '{source_name}' with fresh data",
                        providers_to_use=[],
                        fields_to_enrich=[],
                        estimated_cost=0.0,
                        priority="skip"
                    )
            else:
                return EnrichmentPlan(
                    should_enrich=False,
                    reason=f"Source '{source_name}' provides pre-enriched data",
                    providers_to_use=[],
                    fields_to_enrich=[],
                    estimated_cost=0.0,
                    priority="skip"
                )
        
        # Check if stale
        is_stale = False
        age_days = 0
        enriched_at = getattr(lead, 'enriched_at', None)
        if enriched_at:
            age_days = (datetime.utcnow() - enriched_at).days
            refresh_interval = self.REFRESH_INTERVALS.get(source_quality, 30)
            is_stale = age_days >= refresh_interval
        
        # Check missing fields
        missing_fields = self._get_missing_fields(lead, icp)
        
        if not missing_fields and not is_stale:
            return EnrichmentPlan(
                should_enrich=False,
                reason="All required fields present and data is fresh",
                providers_to_use=[],
                fields_to_enrich=[],
                estimated_cost=0.0,
                priority="skip"
            )
        
        # Select providers
        providers = self._select_providers(source_name, missing_fields)
        
        if not providers:
            return EnrichmentPlan(
                should_enrich=False,
                reason="No providers available",
                providers_to_use=[],
                fields_to_enrich=missing_fields,
                estimated_cost=0.0,
                priority="skip"
            )
        
        # Calculate priority
        priority = self._calculate_priority(lead, missing_fields, source_quality, is_stale)
        estimated_cost = sum(self.PROVIDER_COSTS.get(p, 0) for p in providers)
        
        # Build reason
        reasons = []
        if is_stale:
            reasons.append(f"Data is stale ({age_days} days old)")
        elif not enriched_at:
            reasons.append("Never enriched")
        
        if source_quality in ["low", "unknown"]:
            reasons.append(f"Low-quality source '{source_name}'")
        
        if missing_fields:
            reasons.append(f"Missing {len(missing_fields)} fields")
        
        return EnrichmentPlan(
            should_enrich=True,
            reason="; ".join(reasons),
            providers_to_use=providers,
            fields_to_enrich=missing_fields,
            estimated_cost=estimated_cost,
            priority=priority
        )
    
    def _get_missing_fields(self, lead, icp) -> List[str]:
        """Check missing fields - BULLETPROOF"""
        missing = []
        
        # Check core fields
        if not getattr(lead, 'company_employee_count', None):
            missing.append("company_employee_count")
        
        if not getattr(lead, 'company_industry', None):
            missing.append("company_industry")
        
        if not getattr(lead, 'company_description', None):
            missing.append("company_description")
        
        if not getattr(lead, 'country', None):
            missing.append("country")
        
        # Tech stack
        enrichment_data = getattr(lead, 'enrichment_data', None) or {}
        if "tech_stack" not in enrichment_data:
            missing.append("company_tech_stack")
        
        # Filter based on ICP (if provided)
        if icp is not None:
            try:
                # Handle both dict and object
                if isinstance(icp, dict):
                    rules = icp.get('scoring_rules', {}) or {}
                elif hasattr(icp, 'scoring_rules'):
                    rules = getattr(icp, 'scoring_rules', {}) or {}
                else:
                    rules = {}
                
                if rules:
                    # If ICP doesn't care about tech
                    if not rules.get("required_technologies") and not rules.get("preferred_technologies"):
                        missing = [f for f in missing if f != "company_tech_stack"]
                    
                    # If ICP doesn't filter by size
                    if not rules.get("ideal_company_size_min"):
                        missing = [f for f in missing if f != "company_employee_count"]
            except Exception as e:
                logger.warning(f"Error filtering fields by ICP: {e}")
        
        return missing
    
    def _select_providers(self, source_name: str, missing_fields: List[str]) -> List[str]:
        """Select providers"""
        providers = []
        
        if source_name in ["apollo", "hunter", "peopledatalabs", "clearbit"]:
            return []
        
        if "company_tech_stack" in missing_fields:
            providers.append("wappalyzer")
        
        serpapi_fields = ["company_description", "company_industry", "country"]
        if any(f in missing_fields for f in serpapi_fields):
            providers.append("serpapi")
        
        if "company_employee_count" in missing_fields:
            providers.append("google_kg")
        
        return list(set(providers))
    
    def _calculate_priority(self, lead, missing_fields, source_quality, is_stale) -> str:
        """Calculate priority"""
        enriched_at = getattr(lead, 'enriched_at', None)
        
        if not enriched_at and len(missing_fields) >= 3:
            return "high"
        
        if source_quality in ["low", "unknown"]:
            return "high"
        
        if is_stale:
            return "high"
        
        if len(missing_fields) >= 2:
            return "medium"
        
        return "low"
    
    def calculate_next_refresh(self, source_name: str) -> datetime:
        """Calculate refresh date"""
        source_quality = self.SOURCE_QUALITY.get(source_name, "unknown")
        days = self.REFRESH_INTERVALS.get(source_quality, 30)
        return datetime.utcnow() + timedelta(days=days)


def create_enrichment_strategy_service():
    """Factory function"""
    return EnrichmentStrategyService()