# backend/app/services/batch_processor.py
"""
Batch Processor - Runs every 15 minutes to process pending raw leads
Handles scheduled batch processing across all tenants and ICPs
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import logging
import uuid
import asyncio

from app.models import (
    RawLead, ICP, Tenant, ICPProcessingJob,
    BatchProcessingSchedule
)
from app.services.pipeline_orchestrator import create_pipeline_orchestrator
from app.database import SessionLocal

logger = logging.getLogger(__name__)


class BatchProcessor:
    """
    Processes raw leads in batches according to schedule
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.orchestrator = create_pipeline_orchestrator(db)
    
    async def run_scheduled_batch(
        self,
        schedule_id: Optional[str] = None
    ) -> Dict:
        """
        Run scheduled batch processing
        
        Args:
            schedule_id: Optional specific schedule to run (default: all enabled)
            
        Returns:
            Summary of batch execution
        """
        start_time = datetime.utcnow()
        
        logger.info("=" * 60)
        logger.info("Starting scheduled batch processing")
        logger.info("=" * 60)
        
        # Get schedules to run
        schedules = self._get_schedules_to_run(schedule_id)
        
        if not schedules:
            logger.info("No schedules to run")
            return {
                "schedules_run": 0,
                "jobs_created": 0,
                "leads_queued": 0
            }
        
        total_jobs = 0
        total_leads = 0
        
        # Process each schedule
        for schedule in schedules:
            try:
                result = await self._process_schedule(schedule)
                total_jobs += result["jobs_created"]
                total_leads += result["leads_queued"]
                
                # Update schedule
                schedule.last_run_at = datetime.utcnow()
                schedule.next_run_at = self._calculate_next_run(schedule)
                
            except Exception as e:
                logger.error(f"Error processing schedule {schedule.id}: {e}")
        
        self.db.commit()
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info("=" * 60)
        logger.info(f"Batch processing complete: {total_jobs} jobs, {total_leads} leads")
        logger.info(f"Time: {elapsed:.2f}s")
        logger.info("=" * 60)
        
        return {
            "schedules_run": len(schedules),
            "jobs_created": total_jobs,
            "leads_queued": total_leads,
            "elapsed_seconds": elapsed
        }
    
    async def process_tenant_batch(
        self,
        tenant_id: str,
        icp_ids: Optional[List[str]] = None,
        max_leads: int = 1000
    ) -> Dict:
        """
        Process batch for a specific tenant
        
        Args:
            tenant_id: Tenant UUID
            icp_ids: Optional list of ICP UUIDs (default: all active)
            max_leads: Max leads to process
            
        Returns:
            Processing summary
        """
        logger.info(f"Processing batch for tenant {tenant_id}")
        
        # Get tenant
        tenant = self.db.query(Tenant).filter(
            Tenant.id == uuid.UUID(tenant_id)
        ).first()
        
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        
        # Get ICPs to process
        icps_query = self.db.query(ICP).filter(
            ICP.tenant_id == uuid.UUID(tenant_id),
            ICP.is_active == True
        )
        
        if icp_ids:
            icps_query = icps_query.filter(
                ICP.id.in_([uuid.UUID(iid) for iid in icp_ids])
            )
        
        icps = icps_query.all()
        
        if not icps:
            logger.warning(f"No active ICPs found for tenant {tenant_id}")
            return {"jobs_created": 0, "leads_queued": 0}
        
        # Get pending raw leads
        raw_leads = self._get_pending_raw_leads(tenant_id, max_leads)
        
        if not raw_leads:
            logger.info(f"No pending raw leads for tenant {tenant_id}")
            return {"jobs_created": 0, "leads_queued": 0}
        
        logger.info(
            f"Found {len(raw_leads)} pending leads for {len(icps)} ICPs"
        )
        
        # Create jobs for each ICP
        jobs_created = 0
        total_leads = 0
        
        for icp in icps:
            # Filter leads not yet processed by this ICP
            icp_raw_leads = [
                rl for rl in raw_leads
                if str(icp.id) not in (rl.processed_by_icps or [])
            ]
            
            if not icp_raw_leads:
                logger.info(f"All leads already processed by ICP {icp.name}")
                continue
            
            # Create processing job
            job = await self._create_processing_job(
                tenant_id=tenant_id,
                icp=icp,
                raw_lead_ids=[str(rl.id) for rl in icp_raw_leads],
                job_type="batch_scheduled"
            )
            
            jobs_created += 1
            total_leads += len(icp_raw_leads)
            
            logger.info(
                f"Created job {job.id} for ICP {icp.name}: "
                f"{len(icp_raw_leads)} leads"
            )
        
        return {
            "jobs_created": jobs_created,
            "leads_queued": total_leads,
            "tenant_id": tenant_id,
            "icps_processed": len(icps)
        }
    
    async def process_job(
        self,
        job_id: str
    ) -> Dict:
        """
        Process a specific job
        
        Args:
            job_id: Job UUID
            
        Returns:
            Job results
        """
        job = self.db.query(ICPProcessingJob).filter(
            ICPProcessingJob.id == uuid.UUID(job_id)
        ).first()
        
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        if job.status not in ["queued", "running"]:
            logger.warning(f"Job {job_id} has status {job.status}, skipping")
            return {"status": job.status, "already_processed": True}
        
        logger.info(f"Processing job {job_id} for ICP {job.icp_id}")
        
        # Update job status
        job.status = "running"
        job.started_at = datetime.utcnow()
        self.db.commit()
        
        try:
            result = await self._execute_job(job)
            
            # Update job with results
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            job.processed_leads = result["processed"]
            job.successful_leads = result["successful"]
            job.failed_leads = result["failed"]
            job.results_summary = result["summary"]
            job.total_processing_time_sec = int(
                (job.completed_at - job.started_at).total_seconds()
            )
            
            self.db.commit()
            
            logger.info(
                f"Job {job_id} completed: {result['successful']} successful, "
                f"{result['failed']} failed"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            self.db.commit()
            
            raise
    
    async def _process_schedule(
        self,
        schedule: BatchProcessingSchedule
    ) -> Dict:
        """
        Process all jobs for a schedule
        """
        logger.info(f"Processing schedule: {schedule.schedule_name}")
        
        # Determine which ICPs to process
        if schedule.process_all_icps:
            icps = self.db.query(ICP).filter(
                ICP.tenant_id == schedule.tenant_id,
                ICP.is_active == True
            ).all()
        else:
            icps = self.db.query(ICP).filter(
                ICP.id.in_(schedule.specific_icp_ids or []),
                ICP.is_active == True
            ).all()
        
        if not icps:
            return {"jobs_created": 0, "leads_queued": 0}
        
        # Get pending leads
        raw_leads = self._get_pending_raw_leads(
            str(schedule.tenant_id),
            schedule.max_leads_per_batch
        )
        
        if not raw_leads:
            return {"jobs_created": 0, "leads_queued": 0}
        
        jobs_created = 0
        total_leads = 0
        
        # Create job for each ICP
        for icp in icps:
            # Filter leads for this ICP
            icp_leads = [
                rl for rl in raw_leads
                if str(icp.id) not in (rl.processed_by_icps or [])
            ]
            
            if not icp_leads:
                continue
            
            job = await self._create_processing_job(
                tenant_id=str(schedule.tenant_id),
                icp=icp,
                raw_lead_ids=[str(rl.id) for rl in icp_leads],
                job_type="batch_scheduled"
            )
            
            jobs_created += 1
            total_leads += len(icp_leads)
        
        return {
            "jobs_created": jobs_created,
            "leads_queued": total_leads
        }
    
    async def _execute_job(
        self,
        job: ICPProcessingJob
    ) -> Dict:
        """
        Execute a processing job
        """
        # Get ICP
        icp = self.db.query(ICP).filter(ICP.id == job.icp_id).first()
        if not icp:
            raise ValueError(f"ICP {job.icp_id} not found")
        
        # Get raw leads
        raw_lead_ids = job.raw_lead_ids or []
        raw_leads = self.db.query(RawLead).filter(
            RawLead.id.in_([uuid.UUID(rid) for rid in raw_lead_ids])
        ).all()
        
        job.total_leads = len(raw_leads)
        self.db.commit()
        
        # Process each lead
        results = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "summary": {
                "scored": 0,
                "enriched": 0,
                "verified": 0,
                "qualified": 0,
                "review": 0,
                "rejected": 0
            }
        }
        
        for raw_lead in raw_leads:
            try:
                # Mark as processing
                raw_lead.processing_status = "processing"
                self.db.commit()
                
                # Process through pipeline
                pipeline_result = await self.orchestrator.process_raw_lead(
                    raw_lead=raw_lead,
                    icp=icp,
                    job_id=str(job.id),
                    stages_to_run=job.stages_to_run
                )
                
                results["processed"] += 1
                
                if pipeline_result.success:
                    results["successful"] += 1
                    
                    # Track final stage
                    final_stage = pipeline_result.final_stage
                    if final_stage in results["summary"]:
                        results["summary"][final_stage] += 1
                else:
                    results["failed"] += 1
                    logger.error(
                        f"Failed to process raw lead {raw_lead.id}: "
                        f"{pipeline_result.error}"
                    )
            
            except Exception as e:
                results["failed"] += 1
                logger.error(f"Error processing raw lead {raw_lead.id}: {e}")
                
                raw_lead.processing_status = "failed"
                raw_lead.error_message = str(e)
                self.db.commit()
        
        return results
    
    async def _create_processing_job(
        self,
        tenant_id: str,
        icp: ICP,
        raw_lead_ids: List[str],
        job_type: str
    ) -> ICPProcessingJob:
        """
        Create a new processing job
        """
        job = ICPProcessingJob(
            id=uuid.uuid4(),
            tenant_id=uuid.UUID(tenant_id),
            icp_id=icp.id,
            job_type=job_type,
            triggered_by="scheduler",
            raw_lead_ids=raw_lead_ids,
            stages_to_run=None,  # Run all stages
            status="queued",
            total_leads=len(raw_lead_ids),
            queued_at=datetime.utcnow()
        )
        
        self.db.add(job)
        self.db.commit()
        
        return job
    
    def _get_pending_raw_leads(
        self,
        tenant_id: str,
        limit: int = 1000
    ) -> List[RawLead]:
        """
        Get pending raw leads for a tenant
        """
        return self.db.query(RawLead).filter(
            RawLead.tenant_id == uuid.UUID(tenant_id),
            RawLead.processing_status == "pending"
        ).order_by(
            RawLead.created_at.asc()
        ).limit(limit).all()
    
    def _get_schedules_to_run(
        self,
        schedule_id: Optional[str] = None
    ) -> List[BatchProcessingSchedule]:
        """
        Get schedules that should run now
        """
        now = datetime.utcnow()
        
        query = self.db.query(BatchProcessingSchedule).filter(
            BatchProcessingSchedule.is_enabled == True
        )
        
        if schedule_id:
            query = query.filter(
                BatchProcessingSchedule.id == uuid.UUID(schedule_id)
            )
        else:
            # Get schedules that are due
            query = query.filter(
                or_(
                    BatchProcessingSchedule.next_run_at == None,
                    BatchProcessingSchedule.next_run_at <= now
                )
            )
        
        schedules = query.all()
        
        # Filter by hour restrictions
        current_hour = now.hour
        filtered = []
        
        for schedule in schedules:
            if schedule.only_run_during_hours:
                if current_hour in schedule.only_run_during_hours:
                    filtered.append(schedule)
            else:
                filtered.append(schedule)
        
        return filtered
    
    def _calculate_next_run(
        self,
        schedule: BatchProcessingSchedule
    ) -> datetime:
        """
        Calculate next run time based on cron expression
        
        For now, simple implementation for */15 pattern
        """
        # Parse cron expression (simplified)
        # Format: "*/15 * * * *" = every 15 minutes
        
        parts = schedule.cron_expression.split()
        
        if len(parts) >= 1:
            minute_part = parts[0]
            
            if minute_part.startswith("*/"):
                # Every N minutes
                interval = int(minute_part[2:])
                return datetime.utcnow() + timedelta(minutes=interval)
        
        # Default: 15 minutes
        return datetime.utcnow() + timedelta(minutes=15)


# Factory function
def create_batch_processor(db: Session) -> BatchProcessor:
    """Create batch processor instance"""
    return BatchProcessor(db)


# Scheduler integration (using APScheduler)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


def start_scheduler():
    """
    Start the batch processing scheduler
    Run this on app startup
    """
    logger.info("Starting batch processing scheduler")
    
    # Run every 15 minutes
    scheduler.add_job(
        run_scheduled_batch_job,
        'cron',
        minute='*/15',
        id='batch_processor',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler started - will run every 15 minutes")


async def run_scheduled_batch_job():
    """
    Job that runs on schedule
    """
    db = SessionLocal()
    try:
        processor = create_batch_processor(db)
        await processor.run_scheduled_batch()
    except Exception as e:
        logger.error(f"Scheduled batch failed: {e}")
    finally:
        db.close()