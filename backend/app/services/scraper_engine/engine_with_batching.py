# backend/app/services/scraper_engine/engine_with_batching.py
"""
Enhanced Scraper Engine with:
- ICP Configuration Aggregation
- Smart Rate Limiting  
- Batch Processing
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import UUID
import logging

from sqlalchemy.orm import Session

from app.models import DataSource, ScrapingRun, RawLead
from app.services.scraper_engine.icp_config_aggregator import ICPConfigAggregator
from app.services.scraper_engine.rate_limiter import RateLimiter, BatchProcessor
from app.services.scraper_engine.base_scraper import ScraperEngine

logger = logging.getLogger(__name__)


class EnhancedScraperEngine(ScraperEngine):
    """
    Scraper engine with ICP aggregation and rate limiting
    
    Key Features:
    1. Aggregates all ICP configs into ONE search
    2. Processes leads in batches
    3. Rate limits requests (especially LinkedIn)
    4. Saves to raw_leads for pipeline processing
    """
    
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
        data_source_id: UUID,
        run_id: UUID,
        batch_size: int = 50,
        delay_between_batches: float = 30.0
    ):
        super().__init__(db, tenant_id, data_source_id, run_id)
        
        self.icp_aggregator = ICPConfigAggregator(db)
        self.rate_limiter = None  # Set when platform is known
        self.batch_processor = BatchProcessor(
            batch_size=batch_size,
            delay_between_batches=delay_between_batches
        )
    
    async def run_with_icp_aggregation(
        self,
        platform: str,
        credentials: Dict,
        proxy_config: Optional[Dict] = None,
        include_icp_ids: Optional[List[str]] = None,
        max_results: Optional[int] = None,
        batch_size: int = 50
    ) -> Dict[str, Any]:
        """
        Run scraper with aggregated ICP configuration
        
        Args:
            platform: 'linkedin' or 'apollo'
            credentials: Login/API credentials
            proxy_config: Proxy settings (for LinkedIn)
            include_icp_ids: Optional ICP IDs to include (None = all active)
            max_results: Maximum results to fetch
            batch_size: Leads per batch
        
        Returns:
            Stats dictionary
        """
        self.stats["platform"] = platform
        self.stats["started_at"] = datetime.utcnow()
        
        # Initialize rate limiter for platform
        self.rate_limiter = RateLimiter(platform=platform)
        
        try:
            # Mark as running
            await self.update_run_status("running")
            
            # Step 1: Aggregate ICP configurations
            await self.log("info", f"Aggregating ICP configurations for {platform}...")
            
            if platform == "linkedin":
                aggregated_config = self.icp_aggregator.aggregate_linkedin_config(
                    tenant_id=str(self.tenant_id),
                    include_icp_ids=include_icp_ids
                )
            elif platform == "apollo":
                aggregated_config = self.icp_aggregator.aggregate_apollo_config(
                    tenant_id=str(self.tenant_id),
                    include_icp_ids=include_icp_ids
                )
            else:
                raise ValueError(f"Unsupported platform: {platform}")
            
            await self.log(
                "info",
                f"Aggregated {aggregated_config['total_icps']} ICPs",
                details=aggregated_config
            )
            
            # Step 2: Run scraper with aggregated config
            await self.log("info", f"Starting {platform} scraper...")
            
            if platform == "linkedin":
                leads = await self._run_linkedin_with_batching(
                    config=aggregated_config,
                    credentials=credentials,
                    proxy_config=proxy_config,
                    max_results=max_results
                )
            elif platform == "apollo":
                leads = await self._run_apollo_with_batching(
                    filters=aggregated_config,
                    credentials=credentials,
                    max_results=max_results
                )
            else:
                raise ValueError(f"Unsupported platform: {platform}")
            
            self.stats["leads_found"] = len(leads)
            
            # Step 3: Save leads in batches
            await self.log("info", f"Saving {len(leads)} leads in batches of {batch_size}...")
            
            async def save_lead_wrapper(lead_data):
                return await self.save_lead_to_raw_leads(
                    lead_data=lead_data,
                    source_name=platform
                )
            
            # Process in batches
            self.batch_processor.batch_size = batch_size
            save_results = await self.batch_processor.process_in_batches(
                items=leads,
                process_func=save_lead_wrapper,
                on_batch_complete=self._on_save_batch_complete
            )
            
            # Mark as completed
            await self.update_run_status("completed")
            await self.log(
                "info",
                f"Completed: {self.stats['leads_saved']} saved, "
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
    
    async def _run_linkedin_with_batching(
        self,
        config: Dict,
        credentials: Dict,
        proxy_config: Dict,
        max_results: Optional[int]
    ) -> List[Dict]:
        """
        Run LinkedIn scraper with rate limiting and batching
        """
        from app.services.scraper_engine.platforms.linkedin import LinkedInScraper
        
        scraper = LinkedInScraper(
            proxy_username=proxy_config.get("username"),
            proxy_password=proxy_config.get("password"),
            proxy_country=proxy_config.get("country", "us"),
            headless=True,
            rate_limiter=self.rate_limiter  # Pass rate limiter
        )
        
        # Run scraper with aggregated search URL
        result = await scraper.run(
            config={
                "search_url": config["search_url"],
                "max_pages": 20,  # Can be higher since we're using one search
                "max_results": max_results or 1000,
                "login_email": credentials.get("email"),
                "login_password": credentials.get("password"),
                "source_icps": config["source_icps"],  # Track which ICPs this is for
            },
            on_progress=lambda msg: asyncio.create_task(self.log("info", msg))
        )
        
        # Update stats
        scraper_stats = result.get("stats", {})
        self.stats.update(scraper_stats)
        
        return result.get("leads", [])
    
    async def _run_apollo_with_batching(
        self,
        filters: Dict,
        credentials: Dict,
        max_results: Optional[int]
    ) -> List[Dict]:
        """
        Run Apollo API with rate limiting
        """
        from app.services.scraper_engine.platforms.apollo import ApolloIntegration
        
        apollo = ApolloIntegration(
            api_key=credentials.get("api_key"),
            rate_limiter=self.rate_limiter  # Pass rate limiter
        )
        
        # Calculate pages needed
        per_page = 100
        total_results = max_results or 1000
        max_pages = (total_results + per_page - 1) // per_page
        
        await self.log("info", f"Fetching up to {max_pages} pages from Apollo...")
        
        # Fetch with rate limiting
        leads = await apollo.fetch_all_pages(
            filters=filters,
            max_pages=max_pages,
            max_results=total_results
        )
        
        # Update stats
        self.stats["api_calls"] = (len(leads) // per_page) + 1
        self.stats["api_credits_used"] = len(leads)
        
        # Transform leads
        transformed_leads = [apollo.transform_to_lead(lead) for lead in leads]
        
        return transformed_leads
    
    async def _on_save_batch_complete(
        self,
        batch_num: int,
        total_batches: int,
        results: List
    ):
        """Callback after each batch is saved"""
        saved = sum(1 for r in results if r)
        
        await self.log(
            "info",
            f"Batch {batch_num}/{total_batches} saved: {saved}/{len(results)} leads",
            details={
                "batch": batch_num,
                "total_batches": total_batches,
                "saved": saved,
                "total_saved_so_far": self.stats["leads_saved"],
                "rate_limiter_stats": self.rate_limiter.get_stats(),
                "batch_processor_stats": self.batch_processor.get_stats(),
            }
        )


# ============================================================================
# HELPER FUNCTION TO START RUN WITH ICP AGGREGATION
# ============================================================================

async def start_aggregated_scraping_run(
    db: Session,
    tenant_id: UUID,
    data_source_id: UUID,
    trigger_type: str = "manual",
    user_id: Optional[UUID] = None,
    include_icp_ids: Optional[List[str]] = None,
    batch_size: int = 50,
    max_results: Optional[int] = None
) -> "ScrapingRun":
    """
    Create and start a scraping run with ICP aggregation
    
    This is the NEW way to start scraper runs
    
    Args:
        db: Database session
        tenant_id: Tenant ID
        data_source_id: Data source ID
        trigger_type: 'manual', 'scheduled', etc.
        user_id: User who triggered
        include_icp_ids: Optional list of ICP IDs (None = all active)
        batch_size: Leads per batch (default 50)
        max_results: Maximum total results (default based on platform)
    
    Returns:
        ScrapingRun instance
    """
    from app.models import DataSource, ScrapingRun
    
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
    
    # Create enhanced engine
    engine = EnhancedScraperEngine(
        db=db,
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        run_id=run.id,
        batch_size=batch_size
    )
    
    # Determine platform
    platform = (data_source.scraper_config or {}).get("platform", "apollo")
    
    # Get credentials
    if platform == "linkedin":
        credentials = {
            "email": data_source.scraper_config.get("login_email"),
            "password": data_source.scraper_config.get("login_password")
        }
        proxy_config = data_source.proxy_config or {}
    elif platform == "apollo":
        credentials = {
            "api_key": (data_source.proxy_config or {}).get("api_key")
        }
        proxy_config = None
    else:
        raise ValueError(f"Unsupported platform: {platform}")
    
    # Run asynchronously in background
    asyncio.create_task(
        engine.run_with_icp_aggregation(
            platform=platform,
            credentials=credentials,
            proxy_config=proxy_config,
            include_icp_ids=include_icp_ids,
            max_results=max_results,
            batch_size=batch_size
        )
    )
    
    return run


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

async def example_usage():
    """Example: Run scraper with ICP aggregation"""
    from app.core.database import SessionLocal
    import uuid
    
    db = SessionLocal()
    
    # Start LinkedIn scraper with ICP aggregation
    run = await start_aggregated_scraping_run(
        db=db,
        tenant_id=uuid.UUID("your-tenant-id"),
        data_source_id=uuid.UUID("your-datasource-id"),
        trigger_type="manual",
        batch_size=50,  # Process 50 leads at a time
        max_results=500  # Total 500 leads
    )
    
    print(f"Started run: {run.id}")
    print(f"Status: {run.status}")
    
    db.close()


if __name__ == "__main__":
    asyncio.run(example_usage())