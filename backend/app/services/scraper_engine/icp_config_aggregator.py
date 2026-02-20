# backend/app/services/scraper_engine/icp_config_aggregator.py
"""
ICP Configuration Aggregator

Combines all active ICPs into unified search configuration
for scrapers to use ONE search instead of multiple searches
"""

from typing import Dict, List, Set, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models import ICP
import logging

logger = logging.getLogger(__name__)


class ICPConfigAggregator:
    """
    Aggregates ICP configurations into unified search criteria
    
    Instead of running separate scrapes for each ICP:
    - Aggregate all job titles from all ICPs
    - Aggregate all company sizes from all ICPs
    - Aggregate all industries from all ICPs
    - Run ONE scrape with combined criteria
    - Let pipeline score each lead against each ICP
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def aggregate_linkedin_config(
        self,
        tenant_id: str,
        include_icp_ids: Optional[List[str]] = None
    ) -> Dict:
        """
        Create unified LinkedIn search configuration from all ICPs
        
        Args:
            tenant_id: Tenant ID
            include_icp_ids: Optional list of ICP IDs to include (None = all active)
        
        Returns:
            {
                "job_titles": ["VP Sales", "Director Sales", "Head of Sales", ...],
                "seniority_levels": ["VP", "Director", "C-Level", ...],
                "company_sizes": ["500-1000", "1001-5000", ...],
                "industries": ["Technology", "SaaS", "Software", ...],
                "locations": ["United States", "United Kingdom", ...],
                "search_url": "https://www.linkedin.com/sales/search/people?...",
                "source_icps": ["icp-1", "icp-2", ...]
            }
        """
        # Get active ICPs
        query = self.db.query(ICP).filter(
            ICP.tenant_id == tenant_id,
            ICP.is_active == True
        )
        
        if include_icp_ids:
            query = query.filter(ICP.id.in_(include_icp_ids))
        
        icps = query.all()
        
        if not icps:
            raise ValueError("No active ICPs found")
        
        # Aggregate criteria
        all_job_titles = set()
        all_seniority = set()
        all_company_sizes = set()
        all_industries = set()
        all_locations = set()
        source_icps = []
        
        for icp in icps:
            source_icps.append(str(icp.id))
            
            # Extract from scoring_rules
            rules = icp.scoring_rules or {}
            
            # Job titles
            title_rules = rules.get("job_title", {})
            if isinstance(title_rules, dict):
                # Handle different formats
                if "exact_match" in title_rules:
                    all_job_titles.update(title_rules.get("exact_match", []))
                if "contains" in title_rules:
                    all_job_titles.update(title_rules.get("contains", []))
                if "values" in title_rules:
                    all_job_titles.update(title_rules.get("values", []))
            elif isinstance(title_rules, list):
                all_job_titles.update(title_rules)
            
            # Seniority
            seniority_rules = rules.get("seniority", {})
            if isinstance(seniority_rules, dict):
                if "values" in seniority_rules:
                    all_seniority.update(seniority_rules.get("values", []))
                if "levels" in seniority_rules:
                    all_seniority.update(seniority_rules.get("levels", []))
            elif isinstance(seniority_rules, list):
                all_seniority.update(seniority_rules)
            
            # Company size
            size_rules = rules.get("company_size", {})
            if isinstance(size_rules, dict):
                if "ranges" in size_rules:
                    all_company_sizes.update(size_rules.get("ranges", []))
                if "values" in size_rules:
                    all_company_sizes.update(size_rules.get("values", []))
            elif isinstance(size_rules, list):
                all_company_sizes.update(size_rules)
            
            # Industry
            industry_rules = rules.get("industry", {})
            if isinstance(industry_rules, dict):
                if "values" in industry_rules:
                    all_industries.update(industry_rules.get("values", []))
                if "keywords" in industry_rules:
                    all_industries.update(industry_rules.get("keywords", []))
            elif isinstance(industry_rules, list):
                all_industries.update(industry_rules)
            
            # Location
            location_rules = rules.get("location", {})
            if isinstance(location_rules, dict):
                if "countries" in location_rules:
                    all_locations.update(location_rules.get("countries", []))
                if "regions" in location_rules:
                    all_locations.update(location_rules.get("regions", []))
                if "values" in location_rules:
                    all_locations.update(location_rules.get("values", []))
            elif isinstance(location_rules, list):
                all_locations.update(location_rules)
        
        # Convert sets to sorted lists
        job_titles = sorted(list(all_job_titles))
        seniority = sorted(list(all_seniority))
        company_sizes = sorted(list(all_company_sizes))
        industries = sorted(list(all_industries))
        locations = sorted(list(all_locations))
        
        # Build LinkedIn search URL
        search_url = self._build_linkedin_url(
            job_titles=job_titles,
            seniority=seniority,
            company_sizes=company_sizes,
            industries=industries,
            locations=locations
        )
        
        config = {
            "job_titles": job_titles,
            "seniority_levels": seniority,
            "company_sizes": company_sizes,
            "industries": industries,
            "locations": locations,
            "search_url": search_url,
            "source_icps": source_icps,
            "total_icps": len(icps)
        }
        
        logger.info(
            f"Aggregated {len(icps)} ICPs:\n"
            f"  Job Titles: {len(job_titles)}\n"
            f"  Company Sizes: {len(company_sizes)}\n"
            f"  Industries: {len(industries)}\n"
            f"  Locations: {len(locations)}"
        )
        
        return config
    
    def aggregate_apollo_config(
        self,
        tenant_id: str,
        include_icp_ids: Optional[List[str]] = None
    ) -> Dict:
        """
        Create unified Apollo search configuration from all ICPs
        
        Returns:
            {
                "filters": {
                    "person_titles": [...],
                    "person_seniorities": [...],
                    "organization_num_employees_ranges": [...],
                    "organization_industry_tag_ids": [...],
                    "person_locations": [...]
                },
                "source_icps": ["icp-1", "icp-2", ...]
            }
        """
        # Get active ICPs
        query = self.db.query(ICP).filter(
            ICP.tenant_id == tenant_id,
            ICP.is_active == True
        )
        
        if include_icp_ids:
            query = query.filter(ICP.id.in_(include_icp_ids))
        
        icps = query.all()
        
        if not icps:
            raise ValueError("No active ICPs found")
        
        # Aggregate
        all_titles = set()
        all_seniority = set()
        all_sizes = set()
        all_industries = set()
        all_locations = set()
        source_icps = []
        
        for icp in icps:
            source_icps.append(str(icp.id))
            rules = icp.scoring_rules or {}
            
            # Same extraction logic as LinkedIn
            title_rules = rules.get("job_title", {})
            if isinstance(title_rules, dict):
                all_titles.update(title_rules.get("exact_match", []))
                all_titles.update(title_rules.get("contains", []))
                all_titles.update(title_rules.get("values", []))
            elif isinstance(title_rules, list):
                all_titles.update(title_rules)
            
            # Seniority
            seniority_rules = rules.get("seniority", {})
            if isinstance(seniority_rules, dict):
                all_seniority.update(seniority_rules.get("values", []))
            elif isinstance(seniority_rules, list):
                all_seniority.update(seniority_rules)
            
            # Company size - convert to Apollo format
            size_rules = rules.get("company_size", {})
            if isinstance(size_rules, dict):
                ranges = size_rules.get("ranges", [])
                for r in ranges:
                    all_sizes.add(r)
            elif isinstance(size_rules, list):
                all_sizes.update(size_rules)
            
            # Industry
            industry_rules = rules.get("industry", {})
            if isinstance(industry_rules, dict):
                all_industries.update(industry_rules.get("values", []))
            elif isinstance(industry_rules, list):
                all_industries.update(industry_rules)
            
            # Location
            location_rules = rules.get("location", {})
            if isinstance(location_rules, dict):
                all_locations.update(location_rules.get("countries", []))
            elif isinstance(location_rules, list):
                all_locations.update(location_rules)
        
        # Build Apollo filters
        filters = {
            "person_titles": sorted(list(all_titles)),
            "organization_num_employees_ranges": sorted(list(all_sizes)),
            "person_locations": sorted(list(all_locations)),
            "source_icps": source_icps,
            "total_icps": len(icps)
        }
        
        # Add seniority if any
        if all_seniority:
            filters["person_seniorities"] = sorted(list(all_seniority))
        
        # Add industries if any (Apollo uses tags/keywords)
        if all_industries:
            filters["q_organization_keyword_tags"] = sorted(list(all_industries))
        
        logger.info(
            f"Aggregated {len(icps)} ICPs for Apollo:\n"
            f"  Titles: {len(all_titles)}\n"
            f"  Sizes: {len(all_sizes)}\n"
            f"  Locations: {len(all_locations)}"
        )
        
        return filters
    
    def _build_linkedin_url(
        self,
        job_titles: List[str],
        seniority: List[str],
        company_sizes: List[str],
        industries: List[str],
        locations: List[str]
    ) -> str:
        """
        Build LinkedIn Sales Navigator search URL
        
        This is a simplified version - you'll need to adjust based on
        actual LinkedIn Sales Navigator URL format
        """
        import urllib.parse
        
        base_url = "https://www.linkedin.com/sales/search/people"
        params = []
        
        # Job titles
        if job_titles:
            titles_param = urllib.parse.quote(" OR ".join(job_titles))
            params.append(f"titleIncluded={titles_param}")
        
        # Company sizes (LinkedIn format: 1-10, 11-50, 51-200, etc.)
        if company_sizes:
            # Map to LinkedIn size codes
            size_codes = self._map_to_linkedin_size_codes(company_sizes)
            if size_codes:
                params.append(f"companySize={','.join(size_codes)}")
        
        # Industries
        if industries:
            # Would need LinkedIn industry IDs
            # For now, use keywords
            industry_param = urllib.parse.quote(" OR ".join(industries))
            params.append(f"industryIncluded={industry_param}")
        
        # Locations (LinkedIn uses geo codes)
        if locations:
            # Would need to map to LinkedIn geo IDs
            # For now, simplified
            if "United States" in locations:
                params.append("geoIncluded=103644278")  # US geo code
        
        url = f"{base_url}?{' & '.join(params)}"
        return url
    
    def _map_to_linkedin_size_codes(self, sizes: List[str]) -> List[str]:
        """
        Map generic size ranges to LinkedIn size codes
        
        LinkedIn codes:
        B: 1-10
        C: 11-50
        D: 51-200
        E: 201-500
        F: 501-1000
        G: 1001-5000
        H: 5001-10000
        I: 10001+
        """
        codes = set()
        
        for size in sizes:
            if "-" in size:
                low, high = size.split("-")
                low, high = int(low), int(high)
                
                if low <= 10:
                    codes.add("B")
                if 11 <= low <= 50 or 11 <= high <= 50:
                    codes.add("C")
                if 51 <= low <= 200 or 51 <= high <= 200:
                    codes.add("D")
                if 201 <= low <= 500 or 201 <= high <= 500:
                    codes.add("E")
                if 501 <= low <= 1000 or 501 <= high <= 1000:
                    codes.add("F")
                if 1001 <= low <= 5000 or 1001 <= high <= 5000:
                    codes.add("G")
                if 5001 <= low <= 10000 or 5001 <= high <= 10000:
                    codes.add("H")
                if high > 10000:
                    codes.add("I")
        
        return sorted(list(codes))


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

def example_usage():
    """Example: How to use ICP aggregator"""
    from app.core.database import SessionLocal
    
    db = SessionLocal()
    aggregator = ICPConfigAggregator(db)
    
    # Get unified Apollo config
    apollo_config = aggregator.aggregate_apollo_config(
        tenant_id="your-tenant-id"
    )
    
    print("Apollo Filters:")
    print(f"  Titles: {len(apollo_config['person_titles'])}")
    print(f"  {apollo_config['person_titles'][:5]}...")
    
    # Get unified LinkedIn config
    linkedin_config = aggregator.aggregate_linkedin_config(
        tenant_id="your-tenant-id"
    )
    
    print("\nLinkedIn Config:")
    print(f"  Job Titles: {len(linkedin_config['job_titles'])}")
    print(f"  URL: {linkedin_config['search_url'][:100]}...")
    
    db.close()