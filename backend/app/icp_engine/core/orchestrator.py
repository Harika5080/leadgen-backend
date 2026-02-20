"""
Ingestion orchestrator - coordinates the entire lead processing pipeline.

Pipeline: fetch → map → dedupe → score → save
"""
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from uuid import UUID
import logging

from app.models import (
    DataSource, Lead, IngestionJob, 
    LeadFitScore, LeadActivity, ICP
)
from app.icp_engine.adapters import get_adapter
from app.icp_engine.core.field_mapper import FieldMapper
from app.icp_engine.core.deduplicator import Deduplicator
from app.icp_engine.core.matcher import ICPMatcher
from app.icp_engine.core.scoring_engine import ScoringEngine


logger = logging.getLogger(__name__)


class IngestionOrchestrator:
    """
    Orchestrates the complete lead ingestion pipeline.
    
    Steps:
    1. Load data source configuration
    2. Create adapter and fetch raw leads
    3. Map fields to target schema
    4. Check for duplicates
    5. Find applicable ICPs
    6. Calculate fit scores
    7. Create/update Lead records
    8. Create LeadFitScore records
    9. Update job statistics
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize orchestrator.
        
        Args:
            db: Database session
        """
        self.db = db
        self.field_mapper = None
        self.deduplicator = Deduplicator(db)
        self.icp_matcher = ICPMatcher(db)
        self.scoring_engine = ScoringEngine(db)
    
    async def run_ingestion(
        self,
        data_source_id: str,
        job_type: str = "manual",
        limit_override: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Run complete ingestion pipeline for a data source.
        
        Args:
            data_source_id: Data source ID
            job_type: Job type ("manual" or "scheduled")
            limit_override: Override per_run_limit
        
        Returns:
            dict: Job statistics
        """
        # Load data source
        stmt = select(DataSource).where(DataSource.id == data_source_id)
        result = await self.db.execute(stmt)
        data_source = result.scalars().first()
        
        if not data_source:
            raise ValueError(f"Data source {data_source_id} not found")
        
        # Create job record
        job = IngestionJob(
            data_source_id=data_source.id,
            tenant_id=data_source.tenant_id,
            icp_id=data_source.icp_id,
            job_type=job_type,
            status="running",
            started_at=datetime.utcnow()
        )
        
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        
        try:
            # Initialize components
            self.field_mapper = FieldMapper(data_source.field_mappings)
            
            # Get limit
            limit = limit_override or data_source.per_run_limit
            
            # Step 1: Fetch raw leads
            logger.info(f"Fetching leads from {data_source.name}...")
            adapter = get_adapter(data_source.source_type, data_source)
            raw_leads = await adapter.fetch_leads(limit=limit)
            
            logger.info(f"Fetched {len(raw_leads)} raw leads")
            
            # Step 2: Map fields
            logger.info("Mapping fields...")
            mapped_leads = self.field_mapper.map_batch(raw_leads)
            
            # Step 3: Process each lead
            stats = {
                "leads_processed": 0,
                "leads_created": 0,
                "leads_updated": 0,
                "leads_duplicate": 0,
                "leads_qualified": 0,
                "leads_rejected": 0,
                "errors": []
            }
            
            for mapped_data in mapped_leads:
                try:
                    result = await self._process_single_lead(
                        mapped_data,
                        data_source,
                        job
                    )
                    
                    # Update stats
                    stats["leads_processed"] += 1
                    
                    if result["action"] == "created":
                        stats["leads_created"] += 1
                    elif result["action"] == "updated":
                        stats["leads_updated"] += 1
                    elif result["action"] == "duplicate":
                        stats["leads_duplicate"] += 1
                    
                    if result.get("qualified"):
                        stats["leads_qualified"] += 1
                    else:
                        stats["leads_rejected"] += 1
                
                except Exception as e:
                    logger.error(f"Error processing lead: {e}")
                    stats["errors"].append(str(e))
            
            # Update job as completed
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            job.stats = stats
            
            # Update data source last_run info
            data_source.last_run_at = datetime.utcnow()
            data_source.last_run_status = "success"
            data_source.last_run_stats = stats
            
            await self.db.commit()
            
            logger.info(f"Ingestion completed: {stats}")
            
            return stats
        
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            
            # Update job as failed
            job.status = "failed"
            job.completed_at = datetime.utcnow()
            job.error_message = str(e)
            
            # Update data source
            data_source.last_run_at = datetime.utcnow()
            data_source.last_run_status = "failed"
            
            await self.db.commit()
            
            raise
    
    async def _process_single_lead(
        self,
        mapped_data: Dict[str, Any],
        data_source: DataSource,
        job: IngestionJob
    ) -> Dict[str, Any]:
        """
        Process a single lead through the pipeline.
        
        Args:
            mapped_data: Mapped lead data
            data_source: Data source object
            job: Ingestion job object
        
        Returns:
            dict: Processing result
        """
        email = mapped_data.get("email")
        
        if not email:
            raise ValueError("Lead must have an email address")
        
        # Step 1: Check for duplicate
        existing_lead = await self.deduplicator.find_duplicate(
            email, 
            str(data_source.tenant_id)
        )
        
        if existing_lead:
            # Merge data and update
            merged_data = self.deduplicator.merge_lead_data(
                existing_lead, 
                mapped_data
            )
            
            await self.deduplicator.update_existing_lead(
                existing_lead,
                merged_data
            )
            
            return {
                "action": "duplicate",
                "lead_id": str(existing_lead.id),
                "qualified": False
            }
        
        # Step 2: Find applicable ICPs
        icps = await self.icp_matcher.find_applicable_icps(
            str(data_source.tenant_id),
            mapped_data
        )
        
        if not icps:
            logger.warning("No applicable ICPs found")
            # Still create the lead, just without scoring
            lead = await self._create_lead(mapped_data, data_source, job)
            return {
                "action": "created",
                "lead_id": str(lead.id),
                "qualified": False
            }
        
        # Step 3: Calculate fit scores for each ICP
        best_score = 0.0
        best_score_result = None
        qualified = False
        auto_approved = False
        
        for icp in icps:
            score_result = await self.scoring_engine.calculate_fit_score(
                str(icp.id),
                mapped_data
            )
            
            if score_result["overall_score"] > best_score:
                best_score = score_result["overall_score"]
                best_score_result = score_result
                qualified = score_result["qualified"]
                auto_approved = score_result["auto_approved"]
        
        # Step 4: Create lead record
        lead = await self._create_lead(
            mapped_data, 
            data_source, 
            job,
            best_score,
            qualified,
            auto_approved
        )
        
        # Step 5: Create fit score records
        if best_score_result:
            await self._create_fit_score(
                lead,
                data_source.icp_id,
                best_score_result
            )
        
        # Step 6: Create activity record
        await self._create_activity(lead, "ingested", job)
        
        return {
            "action": "created",
            "lead_id": str(lead.id),
            "qualified": qualified,
            "score": best_score
        }
    
    async def _create_lead(
        self,
        mapped_data: Dict[str, Any],
        data_source: DataSource,
        job: IngestionJob,
        fit_score: float = 0.0,
        qualified: bool = False,
        auto_approved: bool = False
    ) -> Lead:
        """Create a new lead record."""
        
        # Determine initial status
        if auto_approved:
            lead_status = "approved"
        elif qualified:
            lead_status = "pending_review"
        else:
            lead_status = "rejected"
        
        lead = Lead(
            tenant_id=data_source.tenant_id,
            source_id=data_source.id,
            email=mapped_data.get("email"),
            first_name=mapped_data.get("first_name"),
            last_name=mapped_data.get("last_name"),
            phone=mapped_data.get("phone"),
            job_title=mapped_data.get("job_title"),
            linkedin_url=mapped_data.get("linkedin_url"),
            status=lead_status,
            fit_score=fit_score,
            acquisition_timestamp=datetime.utcnow(),
            
            # Company fields (stored directly on Lead)
            company_name=mapped_data.get("company_name"),
            company_website=mapped_data.get("company_website"),
            company_domain=mapped_data.get("company_domain"),
            company_industry=mapped_data.get("company_industry"),
            
            enrichment_data=mapped_data.get("metadata", {})
        )
        
        self.db.add(lead)
        await self.db.commit()
        await self.db.refresh(lead)
        
        logger.info(f"Created lead: {lead.email} (status: {lead_status})")
        
        return lead
    

    async def _create_fit_score(
        self,
        lead: Lead,
        icp_id: UUID,
        score_result: Dict[str, Any]
    ) -> LeadFitScore:
        """Create a fit score record."""
        
        fit_score = LeadFitScore(
            lead_id=lead.id,
            icp_id=icp_id,
            overall_score=score_result["overall_score"],
            rule_scores=score_result["rule_scores"],
            score_explanation=score_result["score_explanation"],
            qualified=score_result["qualified"],
            auto_approved=score_result["auto_approved"]
        )
        
        self.db.add(fit_score)
        await self.db.commit()
        
        return fit_score
    
    async def _create_activity(
        self,
        lead: Lead,
        activity_type: str,
        job: IngestionJob
    ) -> LeadActivity:
        """Create a lead activity record."""
        
        activity = LeadActivity(
            lead_id=lead.id,
            activity_type=activity_type,
            description=f"Lead ingested from {job.data_source.name}",
            metadata={
                "job_id": str(job.id),
                "data_source_id": str(job.data_source_id)
            }
        )
        
        self.db.add(activity)
        await self.db.commit()
        
        return activity