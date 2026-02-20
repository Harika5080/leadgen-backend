# 🚀 Apollo.io Integration - Your First Data Source
# backend/services/scraper_engine/platforms/apollo.py

import httpx
from typing import List, Dict, Optional
from datetime import datetime
import asyncio

class ApolloIntegration:
    """
    Official Apollo.io API integration
    Replaces LinkedIn scraping with legal, reliable API
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.apollo.io/v1"
        self.headers = {
            "Content-Type": "application/json",
            "X-Api-Key": api_key
        }
    
    async def search_people(
        self,
        filters: Dict,
        page: int = 1,
        per_page: int = 100
    ) -> Dict:
        """
        Search for people matching filters
        
        Args:
            filters: {
                "person_titles": ["VP Sales", "Director Sales"],
                "organization_num_employees_ranges": ["500,1000", "1001,5000"],
                "person_locations": ["United States"],
                "q_organization_keyword_tags": ["saas", "b2b"],
            }
            page: Page number (starts at 1)
            per_page: Results per page (max 100)
        
        Returns:
            {
                "people": [...],
                "pagination": {...}
            }
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                **filters,
                "page": page,
                "per_page": per_page
            }
            
            response = await client.post(
                f"{self.base_url}/mixed_people/search",
                headers=self.headers,
                json=payload
            )
            
            response.raise_for_status()
            return response.json()
    
    async def enrich_person(self, email: str) -> Dict:
        """Enrich person by email"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/people/match",
                headers=self.headers,
                json={"email": email}
            )
            return response.json()
    
    async def enrich_company(self, domain: str) -> Dict:
        """Enrich company by domain"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/organizations/enrich",
                headers=self.headers,
                json={"domain": domain}
            )
            return response.json()
    
    def transform_to_lead(self, person: Dict) -> Dict:
        """
        Transform Apollo person object to our lead format
        
        Apollo person structure:
        {
            "id": "...",
            "first_name": "John",
            "last_name": "Doe",
            "name": "John Doe",
            "linkedin_url": "...",
            "title": "VP of Sales",
            "email": "john.doe@company.com",
            "phone_numbers": [{
                "raw_number": "+1...",
                "sanitized_number": "...",
                "type": "work"
            }],
            "organization": {
                "name": "TechCorp",
                "website_url": "techcorp.com",
                "industry": "Technology",
                "num_employees": 500,
                "founded_year": 2010,
                "linkedin_url": "..."
            },
            "city": "San Francisco",
            "state": "California",
            "country": "United States"
        }
        """
        org = person.get("organization") or {}
        phone_numbers = person.get("phone_numbers") or []
        
        return {
            "email": person.get("email"),
            "first_name": person.get("first_name"),
            "last_name": person.get("last_name"),
            "full_name": person.get("name"),
            "job_title": person.get("title"),
            "seniority": person.get("seniority"),
            
            # Company info
            "company_name": org.get("name"),
            "company_website": org.get("website_url"),
            "company_domain": org.get("primary_domain"),
            "company_industry": org.get("industry"),
            "company_size": str(org.get("num_employees", "")),
            "company_founded_year": org.get("founded_year"),
            "company_linkedin_url": org.get("linkedin_url"),
            
            # Location
            "city": person.get("city"),
            "state": person.get("state"),
            "country": person.get("country"),
            
            # Contact
            "phone": phone_numbers[0].get("sanitized_number") if phone_numbers else None,
            "linkedin_url": person.get("linkedin_url"),
            
            # Apollo metadata
            "apollo_id": person.get("id"),
            "source_url": f"https://app.apollo.io/people/{person.get('id')}",
            
            # Raw data for reference
            "raw_data": person
        }
    
    async def fetch_all_pages(
        self,
        filters: Dict,
        max_pages: int = 10,
        max_results: int = 1000
    ) -> List[Dict]:
        """
        Fetch multiple pages of results
        
        Args:
            filters: Search filters
            max_pages: Maximum pages to fetch
            max_results: Maximum total results
        
        Returns:
            List of transformed leads
        """
        all_leads = []
        page = 1
        
        while page <= max_pages and len(all_leads) < max_results:
            try:
                result = await self.search_people(
                    filters=filters,
                    page=page,
                    per_page=100
                )
                
                people = result.get("people", [])
                if not people:
                    break  # No more results
                
                # Transform to lead format
                leads = [self.transform_to_lead(p) for p in people]
                all_leads.extend(leads)
                
                # Check pagination
                pagination = result.get("pagination", {})
                total_pages = pagination.get("total_pages", 0)
                
                if page >= total_pages:
                    break  # Reached last page
                
                page += 1
                
                # Rate limiting (be nice to API)
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"Error fetching page {page}: {e}")
                break
        
        return all_leads[:max_results]


# ============================================================================
# INTEGRATION WITH SCRAPER ENGINE
# ============================================================================

class ApolloDataSource:
    """
    Apollo.io as a data source
    Works with your existing scraper infrastructure
    """
    
    def __init__(self, api_key: str):
        self.apollo = ApolloIntegration(api_key)
    
    async def run(
        self,
        config: Dict,
        run_id: str,
        on_progress: callable = None
    ) -> Dict:
        """
        Run Apollo data fetch
        
        Args:
            config: {
                "filters": {
                    "person_titles": [...],
                    "organization_num_employees_ranges": [...],
                    ...
                },
                "max_pages": 10,
                "max_results": 1000
            }
            run_id: Scraping run ID
            on_progress: Callback for progress updates
        
        Returns:
            {
                "leads": [...],
                "stats": {
                    "leads_found": 0,
                    "leads_saved": 0,
                    "pages_fetched": 0,
                    ...
                }
            }
        """
        filters = config.get("filters", {})
        max_pages = config.get("max_pages", 10)
        max_results = config.get("max_results", 1000)
        
        stats = {
            "leads_found": 0,
            "leads_saved": 0,
            "pages_fetched": 0,
            "api_calls": 0,
            "errors": 0
        }
        
        try:
            # Fetch leads
            if on_progress:
                await on_progress("Starting Apollo search...")
            
            leads = await self.apollo.fetch_all_pages(
                filters=filters,
                max_pages=max_pages,
                max_results=max_results
            )
            
            stats["leads_found"] = len(leads)
            stats["api_calls"] = (len(leads) // 100) + 1  # Pages called
            
            if on_progress:
                await on_progress(f"Found {len(leads)} leads")
            
            return {
                "leads": leads,
                "stats": stats
            }
            
        except Exception as e:
            stats["errors"] = 1
            raise


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

async def example_usage():
    """Example: How to use Apollo integration"""
    
    # Initialize
    apollo = ApolloIntegration(api_key="your_api_key")
    
    # Search for VP Sales at tech companies
    filters = {
        "person_titles": ["VP Sales", "Director Sales", "Head of Sales"],
        "organization_num_employees_ranges": ["500,1000", "1001,5000"],
        "person_locations": ["United States"],
        "q_organization_keyword_tags": ["saas", "b2b", "software"]
    }
    
    # Fetch results
    result = await apollo.search_people(filters, page=1)
    
    print(f"Found {len(result['people'])} people")
    
    # Transform to leads
    for person in result["people"]:
        lead = apollo.transform_to_lead(person)
        print(f"Lead: {lead['full_name']} - {lead['job_title']} at {lead['company_name']}")


if __name__ == "__main__":
    asyncio.run(example_usage())