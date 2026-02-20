# backend/app/services/apollo_service.py - COMPLETE VERSION
"""
Apollo.io Service - Complete integration
1. People Search - Get leads with contact info (LEAD SOURCE)
2. Organization Search - Enrich company data (ENRICHMENT)
"""

import os
import requests
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ApolloService:
    """Apollo.io integration for leads and enrichment"""
    
    def __init__(self):
        self.api_key = os.getenv('APOLLO_API_KEY')
        self.base_url = "https://api.apollo.io/v1"
    
    # ========================================================================
    # LEAD SOURCE - Search for people/contacts
    # ========================================================================
    
    async def search_people(
        self,
        job_titles: List[str] = None,
        company_size_ranges: List[str] = None,
        industries: List[str] = None,
        locations: List[str] = None,
        technologies: List[str] = None,
        per_page: int = 25,
        page: int = 1
    ) -> Dict:
        """
        Search for people matching ICP criteria
        
        Args:
            job_titles: ["VP Engineering", "CTO", "Director Engineering"]
            company_size_ranges: ["100,500", "500,1000", "1000,5000"]
            industries: ["E-commerce", "SaaS", "Technology"]
            locations: ["United States", "Canada", "United Kingdom"]
            technologies: ["React", "Python", "AWS"]
            per_page: Results per page (max 100)
            page: Page number
        
        Returns:
        {
            "people": [
                {
                    "id": "abc123",
                    "first_name": "John",
                    "last_name": "Smith",
                    "email": "john.smith@shopify.com",
                    "title": "VP Engineering",
                    "linkedin_url": "...",
                    "organization": {
                        "name": "Shopify",
                        "website_url": "shopify.com",
                        "industry": "E-commerce",
                        "estimated_num_employees": 8100
                    }
                }
            ],
            "pagination": {"total_entries": 1500, "page": 1, "per_page": 25}
        }
        """
        if not self.api_key:
            logger.error("APOLLO_API_KEY not configured")
            return {"people": [], "error": "API key not configured"}
        
        try:
            url = f"{self.base_url}/mixed_people/search"
            
            headers = {
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": self.api_key
            }
            
            # Build search payload
            payload = {
                "page": page,
                "per_page": min(per_page, 100)  # Max 100
            }
            
            # Add filters
            if job_titles:
                payload["person_titles"] = job_titles
            
            if company_size_ranges:
                payload["organization_num_employees_ranges"] = company_size_ranges
            
            if industries:
                payload["q_organization_keyword_tags"] = industries
            
            if locations:
                payload["person_locations"] = locations
            
            if technologies:
                payload["organization_technologies"] = technologies
            
            logger.info(
                f"🔍 Apollo People Search: "
                f"titles={job_titles}, "
                f"sizes={company_size_ranges}, "
                f"industries={industries}"
            )
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            people = data.get('people', [])
            pagination = data.get('pagination', {})
            
            logger.info(
                f"✅ Apollo found {len(people)} people "
                f"(total: {pagination.get('total_entries', 0)})"
            )
            
            return {
                "people": people,
                "pagination": pagination,
                "breadcrumbs": data.get('breadcrumbs', [])
            }
            
        except Exception as e:
            logger.error(f"Apollo people search error: {e}")
            return {"people": [], "error": str(e)}
    
    async def search_people_by_icp(self, icp) -> Dict:
        """
        Search Apollo using ICP criteria
        
        Converts ICP.scoring_rules to Apollo search parameters
        """
        if not icp.scoring_rules:
            logger.warning("ICP has no scoring_rules, cannot search Apollo")
            return {"people": []}
        
        rules = icp.scoring_rules
        
        # Map ICP criteria to Apollo parameters
        job_titles = rules.get('target_seniority_levels', []) + rules.get('job_title_keywords', [])
        
        # Company size ranges
        size_ranges = []
        if rules.get('ideal_company_size_min') and rules.get('ideal_company_size_max'):
            min_size = rules['ideal_company_size_min']
            max_size = rules['ideal_company_size_max']
            size_ranges.append(f"{min_size},{max_size}")
        
        industries = rules.get('target_industries', [])
        locations = rules.get('target_geographies', [])
        technologies = rules.get('required_technologies', []) + rules.get('preferred_technologies', [])
        
        logger.info(f"🎯 Searching Apollo with ICP '{icp.name}' criteria")
        
        return await self.search_people(
            job_titles=job_titles if job_titles else None,
            company_size_ranges=size_ranges if size_ranges else None,
            industries=industries if industries else None,
            locations=locations if locations else None,
            technologies=technologies[:5] if technologies else None,  # Max 5 techs
            per_page=25
        )
    
    # ========================================================================
    # ENRICHMENT - Get company data
    # ========================================================================
    
    async def enrich_company(self, domain: str, company_name: str = None) -> Dict:
        """
        Enrich company data from Apollo
        (Keep existing implementation)
        """
        if not self.api_key:
            logger.warning("APOLLO_API_KEY not configured")
            return {}
        
        try:
            url = f"{self.base_url}/organizations/search"
            
            headers = {
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": self.api_key
            }
            
            payload = {
                "q_organization_domains": domain,
                "page": 1,
                "per_page": 1
            }
            
            logger.info(f"🔍 Apollo Org: Enriching '{domain}'")
            
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('organizations'):
                logger.info(f"No Apollo org data for {domain}")
                return {}
            
            org = data['organizations'][0]
            
            enriched = {}
            
            # Employee count
            if org.get('estimated_num_employees'):
                enriched['company_employee_count'] = org['estimated_num_employees']
            
            # Industry
            if org.get('industry'):
                enriched['company_industry'] = org['industry']
            
            # Headquarters
            if org.get('city') and org.get('country'):
                enriched['company_headquarters'] = f"{org['city']}, {org['country']}"
            
            # Founded year
            if org.get('founded_year'):
                enriched['company_founded'] = str(org['founded_year'])
            
            # Revenue
            if org.get('organization_revenue'):
                revenue = org['organization_revenue']
                if revenue >= 1_000_000_000:
                    enriched['company_revenue'] = f"${revenue/1_000_000_000:.1f}B"
                elif revenue >= 1_000_000:
                    enriched['company_revenue'] = f"${revenue/1_000_000:.1f}M"
            
            # Technologies
            if org.get('keywords'):
                # Extract tech-related keywords
                tech_keywords = [k for k in org['keywords'] if any(
                    tech in k.lower() for tech in ['api', 'software', 'cloud', 'aws', 'react', 'python']
                )]
                if tech_keywords:
                    enriched['company_tech_stack'] = tech_keywords[:10]
            
            logger.info(f"✅ Apollo enriched {domain}: {list(enriched.keys())}")
            
            return enriched
            
        except Exception as e:
            logger.error(f"Apollo enrichment error for {domain}: {e}")
            return {}
    
    # ========================================================================
    # CONVERT APOLLO PERSON TO RAW LEAD
    # ========================================================================
    
    def person_to_raw_lead(self, person: Dict, tenant_id: str) -> Dict:
        """
        Convert Apollo person to RawLead format
        
        Args:
            person: Apollo person object
            tenant_id: Your tenant ID
            
        Returns:
            Dict with RawLead fields
        """
        org = person.get('organization', {})
        
        return {
            "tenant_id": tenant_id,
            "email": person.get('email'),
            "first_name": person.get('first_name'),
            "last_name": person.get('last_name'),
            "job_title": person.get('title'),
            "linkedin_url": person.get('linkedin_url'),
            
            # Company info (already enriched!)
            "company_name": org.get('name'),
            "company_domain": org.get('primary_domain'),
            "company_website": org.get('website_url'),
            "company_industry": org.get('industry'),
            "company_employee_count": org.get('estimated_num_employees'),
            
            # Location
            "city": person.get('city'),
            "state": person.get('state'),
            "country": person.get('country'),
            
            # Source tracking
            "source_name": "apollo",
            "source_type": "api",
            "source_url": person.get('linkedin_url'),
            
            # Apollo-specific
            "apollo_person_id": person.get('id'),
            "apollo_organization_id": org.get('id'),
        }


def create_apollo_service():
    """Factory function"""
    return ApolloService()