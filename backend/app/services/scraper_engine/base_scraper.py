# backend/app/services/scraper_engine/base_scraper.py
"""
Base scraper class and engine that integrates with PipelineOrchestrator
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import UUID
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import DataSource, ScrapingRun, ScrapingLog, RawLead

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Abstract base class for all data source integrations
    """
    
    @abstractmethod
    async def run(
        self,
        config: Dict[str, Any],
        on_progress: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Run the scraper/API integration
        
        Args:
            config: Platform-specific configuration
            on_progress: Optional callback for progress updates
        
        Returns:
            {
                "leads": List[Dict],  # Raw lead data
                "stats": {
                    "leads_found": int,
                    "pages_scraped": int,  # For scrapers
                    "api_calls": int,  # For APIs
                    ...
                }
            }
        """
        pass
    
    @abstractmethod
    def transform_to_lead(self, raw_data: Dict) -> Dict:
        """
        Transform platform-specific data to standard lead format
        
        Returns:
            {
                "email": str,
                "first_name": str,
                "last_name": str,
                "full_name": str,
                "job_title": str,
                "company_name": str,
                "company_domain": str,
                "company_website": str,
                "company_size": str,
                "company_industry": str,
                "city": str,
                "state": str,
                "country": str,
                "phone": str,
                "linkedin_url": str,
                "source": str,
                "source_url": str,
                "raw_data": dict
            }
        """
        pass


class ScraperEngine:
    """
    Main scraper engine that orchestrates scraping/API calls
    and saves to raw_leads for pipeline processing
    """
    
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
        data_source_id: UUID,
        run_id: UUID
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.data_source_id = data_source_id
        self.run_id = run_id
        
        # Stats tracking
        self.stats = {
            "platform": None,
            "started_at": None,
            "completed_at": None,
            "duration_seconds": None,
            
            # Lead stats
            "leads_found": 0,
            "leads_saved": 0,
            "leads_duplicates": 0,
            "leads_invalid": 0,
            
            # Scraping stats (LinkedIn)
            "pages_scraped": 0,
            "requests_made": 0,
            "requests_failed": 0,
            "proxy_errors": 0,
            "captcha_hits": 0,
            
            # API stats (Apollo)
            "api_calls": 0,
            "api_credits_used": 0,
        }
    
    async def log(
        self,
        level: str,
        message: str,
        details: Optional[Dict] = None,
        url: Optional[str] = None,
        page_number: Optional[int] = None
    ):
        """Log scraping activity"""
        log_entry = ScrapingLog(
            tenant_id=self.tenant_id,
            scraping_run_id=self.run_id,
            level=level,
            message=message,
            details=details or {},
            url=url,
            page_number=page_number
        )
        self.db.add(log_entry)
        self.db.commit()
        
        # Also log to Python logger
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(f"[Run {self.run_id}] {message}", extra=details or {})
    
    async def update_run_status(
        self,
        status: str,
        error_message: Optional[str] = None,
        error_details: Optional[Dict] = None
    ):
        """Update scraping run status"""
        run = self.db.query(ScrapingRun).filter(ScrapingRun.id == self.run_id).first()
        if not run:
            return
        
        run.status = status
        run.updated_at = datetime.utcnow()
        
        # Update stats
        for key, value in self.stats.items():
            if hasattr(run, key) and value is not None:
                setattr(run, key, value)
        
        if status in ["completed", "failed", "cancelled"]:
            run.completed_at = datetime.utcnow()
            
            if run.started_at:
                duration = (run.completed_at - run.started_at).total_seconds()
                run.duration_seconds = int(duration)
                self.stats["duration_seconds"] = int(duration)
        
        if error_message:
            run.error_message = error_message
            run.error_details = error_details or {}
        
        self.db.commit()
    
    async def save_lead_to_raw_leads(
        self,
        lead_data: Dict,
        source_name: str
    ) -> bool:
        """
        Save lead to raw_leads table
        
        This is where leads enter your existing pipeline!
        PipelineOrchestrator will pick them up from here.
        
        Returns:
            True if saved, False if duplicate/invalid
        """
        # Basic validation
        if not lead_data.get("email") and not lead_data.get("full_name"):
            self.stats["leads_invalid"] += 1
            await self.log("warning", f"Invalid lead: no email or name", details=lead_data)
            return False
        
        # Check for duplicate by email
        if lead_data.get("email"):
            existing = self.db.query(RawLead).filter(
                RawLead.tenant_id == self.tenant_id,
                RawLead.email == lead_data["email"]
            ).first()
            
            if existing:
                self.stats["leads_duplicates"] += 1
                await self.log("debug", f"Duplicate lead: {lead_data['email']}")
                return False
        
        # Create raw lead
        raw_lead = RawLead(
            tenant_id=self.tenant_id,
            data_source_id=self.data_source_id,
            
            # Contact info
            email=lead_data.get("email"),
            first_name=lead_data.get("first_name"),
            last_name=lead_data.get("last_name"),
            full_name=lead_data.get("full_name") or f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}".strip(),
            phone=lead_data.get("phone"),
            
            # Professional info
            job_title=lead_data.get("job_title"),
            seniority=lead_data.get("seniority"),
            
            # Company info
            company_name=lead_data.get("company_name"),
            company_website=lead_data.get("company_website"),
            company_domain=lead_data.get("company_domain"),
            company_industry=lead_data.get("company_industry"),
            company_size=lead_data.get("company_size"),
            
            # Location
            city=lead_data.get("city"),
            state=lead_data.get("state"),
            country=lead_data.get("country"),
            
            # Social
            linkedin_url=lead_data.get("linkedin_url"),
            
            # Source tracking
            source_name=source_name,
            source_url=lead_data.get("source_url"),
            raw_data=lead_data.get("raw_data", lead_data),
            
            # Status
            status="new",
            processing_status="pending",
            
            # Flags for pipeline
            needs_email_finding=lead_data.get("needs_email_finding", False),
            needs_verification=lead_data.get("needs_verification", True),
        )
        
        self.db.add(raw_lead)
        self.db.commit()
        
        self.stats["leads_saved"] += 1
        await self.log(
            "info",
            f"Saved lead: {raw_lead.email or raw_lead.full_name}",
            details={"raw_lead_id": str(raw_lead.id)}
        )
        
        return True
    
    async def run_scraper(
        self,
        scraper: BaseScraper,
        config: Dict[str, Any],
        source_name: str
    ) -> Dict[str, Any]:
        """
        Run a specific scraper implementation
        
        Args:
            scraper: BaseScraper instance (LinkedInScraper or ApolloIntegration)
            config: Platform-specific configuration
            source_name: 'linkedin', 'apollo', etc.
        
        Returns:
            Final stats dictionary
        """
        self.stats["platform"] = source_name
        self.stats["started_at"] = datetime.utcnow()
        
        try:
            # Mark as running
            await self.update_run_status("running")
            await self.log("info", f"Starting {source_name} data collection...")
            
            # Run scraper with progress callback
            result = await scraper.run(
                config=config,
                on_progress=lambda msg: asyncio.create_task(self.log("info", msg))
            )
            
            leads = result.get("leads", [])
            scraper_stats = result.get("stats", {})
            
            # Merge scraper stats
            self.stats.update(scraper_stats)
            self.stats["leads_found"] = len(leads)
            
            await self.log("info", f"Found {len(leads)} leads from {source_name}")
            
            # Save all leads to raw_leads
            for lead_raw in leads:
                # Transform to standard format
                lead_data = scraper.transform_to_lead(lead_raw)
                
                # Save to raw_leads table
                await self.save_lead_to_raw_leads(lead_data, source_name)
            
            # Mark as completed
            await self.update_run_status("completed")
            await self.log(
                "info",
                f"Completed: {self.stats['leads_saved']} leads saved, "
                f"{self.stats['leads_duplicates']} duplicates, "
                f"{self.stats['leads_invalid']} invalid",
                details=self.stats
            )
            
            # Update data source stats
            await self._update_data_source_stats()
            
            return self.stats
            
        except Exception as e:
            # Mark as failed
            import traceback
            error_details = {
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            
            await self.update_run_status("failed", error_message=str(e), error_details=error_details)
            await self.log("error", f"Scraper failed: {str(e)}", details=error_details)
            
            raise
    
    async def _update_data_source_stats(self):
        """Update data source with latest run stats"""
        data_source = self.db.query(DataSource).filter(
            DataSource.id == self.data_source_id
        ).first()
        
        if data_source:
            data_source.last_run_at = datetime.utcnow()
            data_source.last_run_status = "success"
            data_source.total_runs = (data_source.total_runs or 0) + 1
            data_source.total_leads_scraped = (data_source.total_leads_scraped or 0) + self.stats["leads_saved"]
            
            self.db.commit()


async def create_and_run_scraper(
    db: Session,
    tenant_id: UUID,
    data_source_id: UUID,
    trigger_type: str = "manual",
    user_id: Optional[UUID] = None
) -> ScrapingRun:
    """
    Create and start a scraping run
    
    This is called by the API endpoint
    """
    # Get data source
    data_source = db.query(DataSource).filter(
        DataSource.id == data_source_id
    ).first()
    
    if not data_source:
        raise ValueError(f"Data source {data_source_id} not found")
    
    # Create run record
    run = ScrapingRun(
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        status="pending",
        trigger_type=trigger_type,
        config_snapshot=data_source.scraper_config or {},
        created_by=user_id
    )
    
    db.add(run)
    db.commit()
    db.refresh(run)
    
    # Create engine
    engine = ScraperEngine(
        db=db,
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        run_id=run.id
    )
    
    # Determine platform and create scraper
    platform = (data_source.scraper_config or {}).get("platform", "apollo")
    
    if platform == "linkedin":
        from app.services.scraper_engine.platforms.linkedin import LinkedInScraper
        
        proxy_config = data_source.proxy_config or {}
        scraper = LinkedInScraper(
            proxy_username=proxy_config.get("username"),
            proxy_password=proxy_config.get("password"),
            proxy_country=proxy_config.get("country", "us"),
            headless=True
        )
        
        # Add credentials to config
        config = {
            **data_source.scraper_config,
            "login_email": data_source.scraper_config.get("login_email"),
            "login_password": data_source.scraper_config.get("login_password")
        }
        
    elif platform == "apollo":
        from app.services.scraper_engine.platforms.apollo import ApolloIntegration
        
        api_key = (data_source.proxy_config or {}).get("api_key")
        scraper = ApolloIntegration(api_key=api_key)
        config = data_source.scraper_config
        
    else:
        raise ValueError(f"Unsupported platform: {platform}")
    
    # Run asynchronously in background
    asyncio.create_task(
        engine.run_scraper(
            scraper=scraper,
            config=config,
            source_name=platform
        )
    )
    
    return run