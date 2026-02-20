# backend/app/services/google_knowledge_graph_service.py
"""
Google Knowledge Graph enrichment service
FREE API - 100,000 queries/day
"""

import os
import requests
import re
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class GoogleKnowledgeGraphService:
    """Enrichment using Google Knowledge Graph API"""
    
    def __init__(self):
        self.api_key = os.getenv('GOOGLE_KG_API_KEY')
        self.base_url = "https://kgsearch.googleapis.com/v1/entities:search"
    
    async def enrich_company(self, company_name: str, domain: str = None) -> Dict:
        """
        Get company info from Google Knowledge Graph
        
        Returns:
        {
            "company_employee_count": 10000,
            "company_industry": "E-commerce",
            "company_founded": "2006",
            "company_headquarters": "Ottawa, Canada",
            "company_description": "...",
            "company_revenue": "$5.6B"
        }
        """
        try:
            # Search query
            query = company_name
            if domain:
                query = f"{company_name} {domain}"
            
            params = {
                "query": query,
                "key": self.api_key,
                "limit": 1,
                "types": "Corporation"
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('itemListElement'):
                logger.info(f"No Knowledge Graph data for {company_name}")
                return {}
            
            result = data['itemListElement'][0]['result']
            
            # Extract data
            enriched = {}
            
            # Description
            if 'detailedDescription' in result:
                article = result['detailedDescription'].get('articleBody', '')
                enriched['company_description'] = article
                
                # ✅ Extract employee count from text
                employee_count = self._extract_employee_count(article)
                if employee_count:
                    enriched['company_employee_count'] = employee_count
                
                # Extract founded year
                founded = self._extract_founded_year(article)
                if founded:
                    enriched['company_founded'] = founded
                
                # Extract revenue
                revenue = self._extract_revenue(article)
                if revenue:
                    enriched['company_revenue'] = revenue
            
            # Short description (industry/type)
            if 'description' in result:
                enriched['company_industry'] = result['description']
            
            logger.info(f"✅ Google KG enriched {company_name}: {list(enriched.keys())}")
            
            return enriched
            
        except Exception as e:
            logger.error(f"Google KG error for {company_name}: {e}")
            return {}
    
    def _extract_employee_count(self, text: str) -> Optional[int]:
        """Extract employee count from text"""
        # Patterns: "10,000 employees", "employs 10000 people", "staff of 10,000"
        patterns = [
            r'(\d+,?\d*)\s*(?:employees|staff|people)',
            r'employs?\s+(?:over|about|around)?\s*(\d+,?\d*)',
            r'staff\s+of\s+(\d+,?\d*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                count_str = match.group(1).replace(',', '')
                try:
                    return int(count_str)
                except:
                    pass
        
        return None
    
    def _extract_founded_year(self, text: str) -> Optional[str]:
        """Extract founding year"""
        # Pattern: "founded in 2006", "established 2006"
        patterns = [
            r'founded\s+in\s+(\d{4})',
            r'established\s+in?\s*(\d{4})',
            r'created\s+in\s+(\d{4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_revenue(self, text: str) -> Optional[str]:
        """Extract revenue"""
        # Pattern: "$5.6 billion", "revenue of $292M"
        patterns = [
            r'\$(\d+\.?\d*)\s*(billion|million|B|M)',
            r'revenue\s+of\s+\$(\d+\.?\d*)\s*(billion|million|B|M)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = match.group(1)
                unit = match.group(2)
                return f"${amount}{unit[0].upper()}"
        
        return None


def create_google_kg_service():
    """Factory function"""
    return GoogleKnowledgeGraphService()