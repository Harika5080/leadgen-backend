"""Lead enrichment service using Clearbit API."""

import logging
from typing import Dict, Any, Optional
import httpx
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


class EnrichmentService:
    """Enrich leads with data from Clearbit and other sources."""
    
    CLEARBIT_PERSON_URL = "https://person.clearbit.com/v2/combined/find"
    CLEARBIT_COMPANY_URL = "https://company.clearbit.com/v2/companies/find"
    
    def __init__(self):
        self.api_key = settings.CLEARBIT_API_KEY
        self.enabled = settings.ENABLE_ENRICHMENT and bool(self.api_key)
    
    async def enrich_person(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Enrich person data from Clearbit Person API.
        Returns enrichment data or None if not found/disabled.
        """
        if not self.enabled:
            logger.debug("Enrichment disabled or no API key")
            return None
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.CLEARBIT_PERSON_URL,
                    params={"email": email},
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Person enrichment successful: {email}")
                    return self._parse_person_data(data)
                elif response.status_code == 404:
                    logger.debug(f"No enrichment data found: {email}")
                    return None
                else:
                    logger.warning(f"Clearbit API error {response.status_code}: {email}")
                    return None
                    
        except Exception as e:
            logger.error(f"Enrichment failed for {email}: {e}")
            return None
    
    async def enrich_company(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Enrich company data from Clearbit Company API.
        Returns enrichment data or None if not found/disabled.
        """
        if not self.enabled:
            return None
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.CLEARBIT_COMPANY_URL,
                    params={"domain": domain},
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Company enrichment successful: {domain}")
                    return self._parse_company_data(data)
                elif response.status_code == 404:
                    logger.debug(f"No company data found: {domain}")
                    return None
                else:
                    logger.warning(f"Clearbit API error {response.status_code}: {domain}")
                    return None
                    
        except Exception as e:
            logger.error(f"Company enrichment failed for {domain}: {e}")
            return None
    
    def _parse_person_data(self, data: Dict) -> Dict[str, Any]:
        """Extract relevant fields from Clearbit person response."""
        person = data.get('person', {})
        company = data.get('company', {})
        
        parsed = {
            'source': 'clearbit',
            'enriched_at': datetime.utcnow().isoformat(),
            'person': {},
            'company': {}
        }
        
        # Person data
        if person:
            name = person.get('name', {})
            employment = person.get('employment', {})
            
            parsed['person'] = {
                'first_name': name.get('givenName'),
                'last_name': name.get('familyName'),
                'job_title': employment.get('title'),
                'seniority': employment.get('seniority'),
                'role': employment.get('role'),
                'linkedin_url': person.get('linkedin', {}).get('handle'),
                'twitter_url': person.get('twitter', {}).get('handle'),
                'location': person.get('location'),
                'avatar': person.get('avatar')
            }
        
        # Company data
        if company:
            parsed['company'] = self._parse_company_data(company)['company']
        
        return parsed
    
    def _parse_company_data(self, data: Dict) -> Dict[str, Any]:
        """Extract relevant fields from Clearbit company response."""
        parsed = {
            'source': 'clearbit',
            'enriched_at': datetime.utcnow().isoformat(),
            'company': {
                'name': data.get('name'),
                'domain': data.get('domain'),
                'legal_name': data.get('legalName'),
                'description': data.get('description'),
                'industry': data.get('category', {}).get('industry'),
                'sector': data.get('category', {}).get('sector'),
                'tags': data.get('tags', []),
                'employee_count': data.get('metrics', {}).get('employees'),
                'employee_range': data.get('metrics', {}).get('employeesRange'),
                'annual_revenue': data.get('metrics', {}).get('estimatedAnnualRevenue'),
                'raised': data.get('metrics', {}).get('raised'),
                'founded_year': data.get('foundedYear'),
                'location': data.get('location'),
                'phone': data.get('phone'),
                'website': data.get('url'),
                'logo_url': data.get('logo'),
                'linkedin_url': data.get('linkedin', {}).get('handle'),
                'twitter_url': data.get('twitter', {}).get('handle'),
                'tech_stack': data.get('tech', [])
            }
        }
        
        return parsed
    
    async def enrich_lead(self, email: str, domain: Optional[str] = None) -> Dict[str, Any]:
        """
        Enrich lead with both person and company data.
        Returns combined enrichment data.
        """
        enrichment_data = {
            'enriched': self.enabled,
            'enriched_at': datetime.utcnow().isoformat(),
            'person': None,
            'company': None
        }
        
        if not self.enabled:
            return enrichment_data
        
        # Enrich person data
        person_data = await self.enrich_person(email)
        if person_data:
            enrichment_data['person'] = person_data.get('person')
            # Use company from person enrichment if available
            if person_data.get('company'):
                enrichment_data['company'] = person_data['company']
        
        # Enrich company data separately if we have a domain and no company data yet
        if domain and not enrichment_data['company']:
            company_data = await self.enrich_company(domain)
            if company_data:
                enrichment_data['company'] = company_data.get('company')
        
        return enrichment_data


# Singleton instance
enrichment_service = EnrichmentService()
