# backend/services/scraper_engine/platforms/linkedin.py
"""
LinkedIn Scraper using Crawlee + Playwright + Oxylabs
Works alongside Apollo.io in same platform
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import re
from crawlee.playwright_crawler import PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee.proxy_configuration import ProxyConfiguration
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.services.scraper_engine.base_scraper import BaseScraper  # ✅ Correct
from app.config import settings


class LinkedInScraper(BaseScraper):
    """
    LinkedIn Sales Navigator / Regular LinkedIn scraper
    Uses Crawlee + Playwright + Oxylabs residential proxies
    """
    
    def __init__(
        self,
        proxy_username: str,
        proxy_password: str,
        proxy_country: str = "us",
        headless: bool = True
    ):
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.proxy_country = proxy_country
        self.headless = headless
        
        # Stats tracking
        self.stats = {
            "pages_scraped": 0,
            "leads_found": 0,
            "leads_extracted": 0,
            "requests_failed": 0,
            "proxy_errors": 0,
            "captcha_hits": 0,
        }
        
        self.scraped_leads: List[Dict] = []
        self.errors: List[str] = []
    
    def get_oxylabs_proxy_url(self, session_id: Optional[str] = None) -> str:
        """
        Generate Oxylabs residential proxy URL
        
        Format:
        - Rotating: customer-{user}-cc-{country}:{pass}@pr.oxylabs.io:7777
        - Sticky: customer-{user}-cc-{country}-sessid-{session}:{pass}@pr.oxylabs.io:7777
        """
        if session_id:
            proxy_user = f"customer-{self.proxy_username}-cc-{self.proxy_country}-sessid-{session_id}"
        else:
            proxy_user = f"customer-{self.proxy_username}-cc-{self.proxy_country}"
        
        return f"http://{proxy_user}:{self.proxy_password}@pr.oxylabs.io:7777"
    
    async def handle_login(self, page, email: str, password: str):
        """Handle LinkedIn login flow"""
        try:
            # Go to login page
            await page.goto("https://www.linkedin.com/login", wait_until="networkidle")
            await asyncio.sleep(2)
            
            # Fill credentials
            await page.fill("#username", email)
            await page.fill("#password", password)
            
            # Submit
            await page.click("button[type='submit']")
            await asyncio.sleep(5)
            
            # Check for 2FA or CAPTCHA
            current_url = page.url
            if "checkpoint" in current_url or "challenge" in current_url:
                self.stats["captcha_hits"] += 1
                raise Exception("LinkedIn security challenge detected - manual intervention required")
            
            # Verify login success
            if "/feed" in current_url or "/in/" in current_url:
                return True
            else:
                raise Exception("Login failed - check credentials")
                
        except Exception as e:
            self.errors.append(f"Login error: {str(e)}")
            raise
    
    async def scrape_sales_navigator(
        self,
        search_url: str,
        max_pages: int = 10,
        max_results: int = 1000,
        login_email: Optional[str] = None,
        login_password: Optional[str] = None,
        on_progress: Optional[callable] = None
    ) -> List[Dict]:
        """
        Scrape LinkedIn Sales Navigator
        
        Args:
            search_url: Full Sales Navigator search URL with filters
            max_pages: Maximum pages to scrape
            max_results: Maximum total results
            login_email: LinkedIn account email
            login_password: LinkedIn account password
            on_progress: Progress callback
        
        Returns:
            List of extracted leads
        """
        if on_progress:
            await on_progress("Initializing LinkedIn scraper...")
        
        # Setup proxy
        proxy_url = self.get_oxylabs_proxy_url()
        proxy_configuration = ProxyConfiguration(proxy_urls=[proxy_url])
        
        # Setup crawler
        crawler = PlaywrightCrawler(
            proxy_configuration=proxy_configuration,
            max_requests_per_crawl=max_pages * 25,
            headless=self.headless,
            browser_type="chromium",
            # Anti-detection settings
            launch_options={
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ]
            }
        )
        
        pages_scraped = 0
        needs_login = True
        
        @crawler.router.default_handler
        async def handler(context: PlaywrightCrawlingContext) -> None:
            nonlocal pages_scraped, needs_login
            
            self.stats["requests_made"] = self.stats.get("requests_made", 0) + 1
            page = context.page
            
            try:
                # Handle login on first page
                if needs_login and login_email and login_password:
                    if on_progress:
                        await on_progress("Logging into LinkedIn...")
                    
                    await self.handle_login(page, login_email, login_password)
                    needs_login = False
                    
                    # Navigate to search URL after login
                    await page.goto(search_url, wait_until="networkidle")
                    await asyncio.sleep(3)
                
                # Wait for results to load
                try:
                    await page.wait_for_selector(
                        ".artdeco-list__item, .search-results__result-item",
                        timeout=30000
                    )
                except PlaywrightTimeoutError:
                    self.stats["requests_failed"] += 1
                    if on_progress:
                        await on_progress(f"Page {pages_scraped + 1} timed out")
                    return
                
                pages_scraped += 1
                self.stats["pages_scraped"] = pages_scraped
                
                if on_progress:
                    await on_progress(f"Scraping page {pages_scraped}/{max_pages}...")
                
                # Extract lead cards
                lead_cards = await page.query_selector_all(
                    ".artdeco-list__item, .search-results__result-item"
                )
                
                for card in lead_cards:
                    if len(self.scraped_leads) >= max_results:
                        break
                    
                    try:
                        lead = await self.extract_lead_from_card(card)
                        if lead:
                            self.scraped_leads.append(lead)
                            self.stats["leads_extracted"] += 1
                    except Exception as e:
                        self.errors.append(f"Lead extraction error: {str(e)}")
                
                self.stats["leads_found"] = len(self.scraped_leads)
                
                # Handle pagination
                if pages_scraped < max_pages and len(self.scraped_leads) < max_results:
                    # Look for next button
                    next_button = await page.query_selector(
                        "button[aria-label='Next'], .artdeco-pagination__button--next"
                    )
                    
                    if next_button:
                        is_disabled = await next_button.get_attribute("disabled")
                        if not is_disabled:
                            next_url = await page.url()
                            # Parse page number and increment
                            if "page=" in next_url:
                                next_page = int(re.search(r"page=(\d+)", next_url).group(1)) + 1
                                next_url = re.sub(r"page=\d+", f"page={next_page}", next_url)
                            else:
                                next_url += "&page=2"
                            
                            await context.enqueue_links([next_url])
                
            except Exception as e:
                self.stats["requests_failed"] += 1
                self.errors.append(f"Page scraping error: {str(e)}")
                if on_progress:
                    await on_progress(f"Error on page {pages_scraped + 1}: {str(e)}")
        
        # Run crawler
        try:
            await crawler.run([search_url])
        except Exception as e:
            self.errors.append(f"Crawler error: {str(e)}")
            raise
        
        return self.scraped_leads
    
    async def extract_lead_from_card(self, card_element) -> Optional[Dict]:
        """
        Extract lead data from a LinkedIn result card
        
        Adapts to both Sales Navigator and regular LinkedIn layouts
        """
        try:
            lead = {}
            
            # Name
            name_elem = await card_element.query_selector(
                ".artdeco-entity-lockup__title, .actor-name, .search-result__result-link"
            )
            if name_elem:
                full_name = (await name_elem.inner_text()).strip()
                lead["full_name"] = full_name
                
                # Try to split into first/last
                name_parts = full_name.split(" ", 1)
                lead["first_name"] = name_parts[0] if name_parts else ""
                lead["last_name"] = name_parts[1] if len(name_parts) > 1 else ""
            
            # Title
            title_elem = await card_element.query_selector(
                ".artdeco-entity-lockup__subtitle, .subline-level-1"
            )
            if title_elem:
                lead["job_title"] = (await title_elem.inner_text()).strip()
            
            # Company
            company_elem = await card_element.query_selector(
                ".artdeco-entity-lockup__caption, .subline-level-2"
            )
            if company_elem:
                company_text = (await company_elem.inner_text()).strip()
                # Clean up (remove "at" prefix if present)
                lead["company_name"] = company_text.replace("at ", "").strip()
            
            # Location
            location_elem = await card_element.query_selector(
                ".artdeco-entity-lockup__metadata, .subline-level-3"
            )
            if location_elem:
                location = (await location_elem.inner_text()).strip()
                lead["location"] = location
                
                # Try to parse city, state, country
                location_parts = [p.strip() for p in location.split(",")]
                if len(location_parts) >= 2:
                    lead["city"] = location_parts[0]
                    lead["state"] = location_parts[1] if len(location_parts) > 1 else ""
                    lead["country"] = location_parts[-1] if len(location_parts) > 2 else ""
            
            # LinkedIn URL
            link_elem = await card_element.query_selector("a[href*='/in/']")
            if link_elem:
                href = await link_elem.get_attribute("href")
                if href:
                    # Clean up URL
                    linkedin_url = href.split("?")[0]  # Remove query params
                    lead["linkedin_url"] = linkedin_url
            
            # Only return if we have at least a name
            if lead.get("full_name"):
                return lead
            else:
                return None
                
        except Exception as e:
            self.errors.append(f"Card extraction error: {str(e)}")
            return None
    
    def transform_to_lead(self, raw_data: Dict) -> Dict:
        """Transform LinkedIn data to standard lead format"""
        return {
            "email": raw_data.get("email"),  # Will be None, needs verification
            "first_name": raw_data.get("first_name"),
            "last_name": raw_data.get("last_name"),
            "full_name": raw_data.get("full_name"),
            "job_title": raw_data.get("job_title"),
            "company_name": raw_data.get("company_name"),
            "city": raw_data.get("city"),
            "state": raw_data.get("state"),
            "country": raw_data.get("country"),
            "location": raw_data.get("location"),
            "linkedin_url": raw_data.get("linkedin_url"),
            "source": "linkedin",
            "source_url": raw_data.get("linkedin_url"),
            "raw_data": raw_data,
            "needs_email_finding": True,  # Flag for Verifella pipeline
        }
    
    async def run(
        self,
        config: Dict,
        run_id: str,
        on_progress: Optional[callable] = None
    ) -> Dict:
        """
        Main entry point to run LinkedIn scraper
        
        Args:
            config: {
                "search_url": "https://www.linkedin.com/sales/search/people?...",
                "max_pages": 10,
                "max_results": 1000,
                "login_email": "your@email.com",
                "login_password": "password"
            }
            run_id: Scraping run ID
            on_progress: Progress callback
        
        Returns:
            {
                "leads": [...],
                "stats": {...}
            }
        """
        search_url = config.get("search_url")
        max_pages = config.get("max_pages", 10)
        max_results = config.get("max_results", 1000)
        login_email = config.get("login_email")
        login_password = config.get("login_password")
        
        if not search_url:
            raise ValueError("search_url is required for LinkedIn scraper")
        
        if not login_email or not login_password:
            raise ValueError("LinkedIn credentials required for scraping")
        
        try:
            # Run scraper
            leads = await self.scrape_sales_navigator(
                search_url=search_url,
                max_pages=max_pages,
                max_results=max_results,
                login_email=login_email,
                login_password=login_password,
                on_progress=on_progress
            )
            
            # Transform to standard format
            transformed_leads = [self.transform_to_lead(lead) for lead in leads]
            
            return {
                "leads": transformed_leads,
                "stats": self.stats,
                "errors": self.errors
            }
            
        except Exception as e:
            self.errors.append(f"Scraper run failed: {str(e)}")
            raise


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

async def example_linkedin_scrape():
    """Example: How to use LinkedIn scraper"""
    
    scraper = LinkedInScraper(
        proxy_username="your_oxylabs_user",
        proxy_password="your_oxylabs_pass",
        proxy_country="us",
        headless=True
    )
    
    config = {
        "search_url": "https://www.linkedin.com/sales/search/people?geoIncluded=103644278&titleIncluded=VP%20Sales",
        "max_pages": 5,
        "max_results": 100,
        "login_email": "your_linkedin@email.com",
        "login_password": "your_linkedin_password"
    }
    
    result = await scraper.run(
        config=config,
        run_id="test-run-123",
        on_progress=lambda msg: print(f"Progress: {msg}")
    )
    
    print(f"Found {len(result['leads'])} leads")
    print(f"Stats: {result['stats']}")


if __name__ == "__main__":
    asyncio.run(example_linkedin_scrape())