# backend/app/services/google_kg_service.py
"""
Google Knowledge Graph Service - Enhanced Employee Count Extraction
"""

import os
import requests
import re
import logging
from typing import Dict, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class GoogleKnowledgeGraphService:
    """Get company data from Google Knowledge Graph with enhanced extraction"""
    
    def __init__(self):
        self.api_key = os.getenv('GOOGLE_KG_API_KEY')
        self.base_url = "https://kgsearch.googleapis.com/v1/entities:search"
    
    async def enrich_company(self, company_name: str, domain: str = None) -> Dict:
        """
        Get company info from Google Knowledge Graph
        
        Enhanced with:
        - Multiple query strategies
        - Better employee count extraction
        - Wikipedia fallback
        """
        if not self.api_key:
            logger.warning("GOOGLE_KG_API_KEY not configured, skipping Google KG enrichment")
            return {}
        
        try:
            # Strategy 1: Try primary query
            result = await self._query_knowledge_graph(company_name, domain)
            
            if not result:
                logger.info(f"No Knowledge Graph data for {company_name}")
                return {}
            
            enriched = {}
            
            # Extract from Knowledge Graph result
            if 'detailedDescription' in result:
                article = result['detailedDescription'].get('articleBody', '')
                url = result['detailedDescription'].get('url', '')
                
                enriched['company_description'] = article
                
                # ✅ Try to extract employee count from snippet
                employee_count = self._extract_employee_count(article)
                
                # ✅ If not found in snippet, try Wikipedia directly
                if not employee_count and url and 'wikipedia.org' in url:
                    logger.info(f"  📖 Employee count not in snippet, trying Wikipedia...")
                    employee_count = await self._extract_from_wikipedia(url)
                
                if employee_count:
                    enriched['company_employee_count'] = employee_count
                    logger.info(f"  ✅ Extracted employee count: {employee_count}")
                else:
                    logger.info(f"  ⚠️ Could not extract employee count")
                
                # Extract other data
                founded = self._extract_founded_year(article)
                if founded:
                    enriched['company_founded'] = founded
                
                revenue = self._extract_revenue(article)
                if revenue:
                    enriched['company_revenue'] = revenue
            
            # Industry (from short description)
            if 'description' in result:
                enriched['company_industry'] = result['description']
            
            logger.info(f"✅ Google KG enriched {company_name}: {list(enriched.keys())}")
            
            return enriched
            
        except Exception as e:
            logger.error(f"Google KG error for {company_name}: {e}")
            return {}
    
    async def _query_knowledge_graph(self, company_name: str, domain: str = None) -> Optional[Dict]:
        """Query Google Knowledge Graph with optimized parameters"""
        try:
            # Build query
            query = company_name
            if domain:
                query = f"{company_name} {domain}"
            
            params = {
                "query": query,
                "key": self.api_key,
                "limit": 1,
                "types": "Corporation"
            }
            
            logger.info(f"🔍 Google KG: Searching for '{query}'")
            
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('itemListElement'):
                return None
            
            return data['itemListElement'][0]['result']
            
        except Exception as e:
            logger.error(f"Google KG query error: {e}")
            return None
    
    async def _extract_from_wikipedia(self, wikipedia_url: str) -> Optional[int]:
        """
        Extract employee count directly from Wikipedia page
        
        Looks in the infobox for employee data
        """
        try:
            logger.info(f"  📖 Fetching Wikipedia: {wikipedia_url}")
            
            # ✅ Add proper headers to avoid 403 Forbidden
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            response = requests.get(wikipedia_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Strategy 1: Look in infobox
            infobox = soup.find('table', {'class': 'infobox'})
            if infobox:
                # Find rows with "employees" or "staff"
                for row in infobox.find_all('tr'):
                    header = row.find('th')
                    if header:
                        header_text = header.get_text().lower()
                        if any(word in header_text for word in ['employee', 'staff', 'workforce']):
                            data = row.find('td')
                            if data:
                                text = data.get_text()
                                count = self._extract_employee_count(text)
                                if count:
                                    logger.info(f"  ✅ Found in Wikipedia infobox: {count}")
                                    return count
            
            # Strategy 2: Look in first few paragraphs
            paragraphs = soup.find_all('p', limit=5)
            for para in paragraphs:
                text = para.get_text()
                count = self._extract_employee_count(text)
                if count:
                    logger.info(f"  ✅ Found in Wikipedia paragraph: {count}")
                    return count
            
            logger.info("  ⚠️ Employee count not found in Wikipedia")
            return None
            
        except Exception as e:
            logger.error(f"Wikipedia extraction error: {e}")
            return None

    def _extract_employee_count(self, text: str) -> Optional[int]:
        """
        Extract employee count from text with enhanced patterns
        
        Handles formats like:
        - "10,000 employees"
        - "8,100 (2024)"  ← This format!
        - "employs over 10000"
        - "staff of 10,000"
        """
        # Clean text
        text = text.replace('\xa0', ' ')  # Remove non-breaking spaces
        text = text.replace('\n', ' ')
        
        # ✅ PRIORITY: Match just numbers with comma (for Wikipedia infobox)
        # Matches: "8,100" or "8,100 (2024)" or "10,000+"
        simple_number_patterns = [
            r'^(\d{1,3}(?:,\d{3})+)',  # Start of string with comma-separated number
            r'(\d{1,3}(?:,\d{3})+)\s*(?:\(|$|\+)',  # Number followed by ( or end or +
        ]
        
        for pattern in simple_number_patterns:
            match = re.search(pattern, text.strip())
            if match:
                count_str = match.group(1).replace(',', '')
                try:
                    count = int(count_str)
                    if 10 <= count <= 10_000_000:
                        logger.debug(f"Matched simple number: {pattern} -> {count}")
                        return count
                except ValueError:
                    continue
        
        # Enhanced patterns (ordered by specificity)
        patterns = [
            # Exact numbers with separators
            r'(\d{1,3}(?:,\d{3})+)\s*(?:\+)?\s*(?:employees|staff|people|workers)',
            r'(\d{4,})\s*(?:\+)?\s*(?:employees|staff|people|workers)',
            
            # "employs X" format
            r'employs?\s+(?:over|about|around|approximately|nearly)?\s*(\d{1,3}(?:,\d{3})+)',
            r'employs?\s+(?:over|about|around|approximately|nearly)?\s*(\d{4,})',
            
            # "staff of X" format
            r'staff\s+of\s+(?:over|about|around|approximately)?\s*(\d{1,3}(?:,\d{3})+)',
            r'staff\s+of\s+(?:over|about|around|approximately)?\s*(\d{4,})',
            
            # "workforce of X" format
            r'workforce\s+of\s+(?:over|about|around|approximately)?\s*(\d{1,3}(?:,\d{3})+)',
            r'workforce\s+of\s+(?:over|about|around|approximately)?\s*(\d{4,})',
            
            # "has X employees" format
            r'has\s+(?:over|about|around|approximately)?\s*(\d{1,3}(?:,\d{3})+)\s+(?:employees|staff)',
            r'has\s+(?:over|about|around|approximately)?\s*(\d{4,})\s+(?:employees|staff)',
            
            # Range format "between X and Y employees"
            r'between\s+(\d{1,3}(?:,\d{3})+)\s+and\s+\d+\s+(?:employees|staff)',
            
            # Number before "employee" word
            r'(\d{1,3}(?:,\d{3})+)\s*(?:\+|–|-)?\s*(?:full-time|full time)?\s*(?:employees|staff)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                count_str = match.group(1).replace(',', '').replace(' ', '')
                try:
                    count = int(count_str)
                    if 10 <= count <= 10_000_000:
                        logger.debug(f"Matched pattern: {pattern} -> {count}")
                        return count
                except ValueError:
                    continue
        
        # Try abbreviated formats (e.g., "10k employees", "2.5K staff")
        abbrev_patterns = [
            r'(\d+\.?\d*)\s*[kK]\s+(?:employees|staff|people)',
            r'employs?\s+(\d+\.?\d*)\s*[kK]',
        ]
        
        for pattern in abbrev_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    num = float(match.group(1))
                    count = int(num * 1000)
                    if 10 <= count <= 10_000_000:
                        logger.debug(f"Matched abbreviated pattern: {pattern} -> {count}")
                        return count
                except ValueError:
                    continue
        
        return None

    def _extract_founded_year(self, text: str) -> Optional[str]:
        """Extract founding year with enhanced patterns"""
        patterns = [
            r'founded\s+in\s+(\d{4})',
            r'established\s+in?\s*(\d{4})',
            r'created\s+in\s+(\d{4})',
            r'formed\s+in\s+(\d{4})',
            r'launched\s+in\s+(\d{4})',
            r'\((\d{4})\)',  # Year in parentheses
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                year = match.group(1)
                # Sanity check: reasonable year range
                if 1800 <= int(year) <= 2030:
                    return year
        
        return None
    
    def _extract_revenue(self, text: str) -> Optional[str]:
        """Extract revenue with enhanced patterns"""
        patterns = [
            r'\$(\d+\.?\d*)\s*(billion|million|B|M)',
            r'revenue\s+of\s+\$(\d+\.?\d*)\s*(billion|million|B|M)',
            r'annual\s+revenue\s+\$(\d+\.?\d*)\s*(billion|million|B|M)',
            r'\$(\d+\.?\d*)\s*([BM])\s+in\s+revenue',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = match.group(1)
                unit = match.group(2)
                # Normalize unit
                unit_letter = 'B' if unit.lower().startswith('b') else 'M'
                return f"${amount}{unit_letter}"
        
        return None


def create_google_kg_service():
    """Factory function"""
    return GoogleKnowledgeGraphService()