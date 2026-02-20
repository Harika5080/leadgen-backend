"""APScheduler configuration for automated batch processing."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import logging
from sqlalchemy import select

# NOTE: Commented out until ICP engine is fully implemented
from app.icp_engine.core.orchestrator import IngestionOrchestrator
from app.models import DataSource  

logger = logging.getLogger(__name__)

# Create scheduler instance
scheduler = AsyncIOScheduler()


# NOTE: Commented out until ICP engine is ready
async def run_scheduled_ingestion():
    """
    Run scheduled ingestion for all active data sources.
    Called by APScheduler.
    """
    from app.database import async_session
    
    logger.info("Running scheduled ICP ingestion...")
    
    async with async_session() as db:
        # Get all active data sources with scheduling enabled
        stmt = select(DataSource).where(
            DataSource.is_active == True,
            DataSource.schedule_enabled == True
        )
        result = await db.execute(stmt)
        sources = result.scalars().all()
        
        logger.info(f"Found {len(sources)} data sources to process")
        
        # Process each source
        for source in sources:
            try:
                orchestrator = IngestionOrchestrator(db)
                stats = await orchestrator.run_ingestion(
                    data_source_id=str(source.id),
                    job_type="scheduled"
                )
                
                logger.info(f"Processed source {source.name}: {stats}")
            except Exception as e:
                logger.error(f"Error processing source {source.name}: {e}")


async def process_lead_batches():
    """
    Process lead batches - runs 4 times daily.
    
    This job:
    1. Finds leads with status='verified'
    2. Adds them to review queue
    3. Updates lead status to 'pending_review'
    """
    try:
        logger.info("Starting batch lead processing...")
        
        # Import here to avoid circular imports
        from app.database import get_db
        from app.models import Lead
        from sqlalchemy import select
        
        async for db in get_db():
            # Find verified leads not yet in review
            result = await db.execute(
                select(Lead).where(
                    Lead.lead_status == 'verified',
                    Lead.reviewed_at == None
                )
            )
            leads = result.scalars().all()
            
            if leads:
                logger.info(f"Found {len(leads)} leads to add to review queue")
                
                # Update status to pending_review
                for lead in leads:
                    lead.lead_status = 'pending_review'
                
                await db.commit()
                logger.info(f"Added {len(leads)} leads to review queue")
            else:
                logger.info("No leads to process")
            
            break  # Only use first db session
        
    except Exception as e:
        logger.error(f"Error in batch processing: {e}")


async def cleanup_old_leads():
    """
    Clean up old leads based on retention policy.
    
    This job:
    1. Finds leads older than retention period
    2. Deletes or archives them
    """
    try:
        logger.info("Starting lead cleanup job...")
        
        from app.database import get_db
        from app.models import Lead, Tenant
        from sqlalchemy import select, and_
        from datetime import timedelta
        
        async for db in get_db():
            # Get all tenants
            result = await db.execute(select(Tenant))
            tenants = result.scalars().all()
            
            total_deleted = 0
            
            for tenant in tenants:
                # Get retention days (default 90)
                retention_days = 90  # Default
                
                # Calculate cutoff date
                cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
                
                # Find old leads
                result = await db.execute(
                    select(Lead).where(
                        and_(
                            Lead.tenant_id == tenant.id,
                            Lead.created_at < cutoff_date
                        )
                    )
                )
                old_leads = result.scalars().all()
                
                if old_leads:
                    logger.info(f"Deleting {len(old_leads)} old leads for tenant {tenant.id}")
                    
                    for lead in old_leads:
                        await db.delete(lead)
                    
                    total_deleted += len(old_leads)
            
            await db.commit()
            logger.info(f"Cleanup complete. Deleted {total_deleted} old leads")
            
            break
        
    except Exception as e:
        logger.error(f"Error in cleanup job: {e}")


def start_scheduler():
    """
    Initialize and start the APScheduler.
    
    Jobs:
    - Lead batch processing: 4x daily (00:00, 06:00, 12:00, 18:00 UTC)
    - Lead cleanup: Daily at 02:00 UTC
    """
    if scheduler.running:
        logger.info("Scheduler already running")
        return
    
    try:
        # Job 1: Batch processing (4 times daily)
        scheduler.add_job(
            process_lead_batches,
            trigger=CronTrigger(hour='0,6,12,18', minute=0),
            id='lead_batch_processing',
            name='Lead Batch Processing',
            replace_existing=True,
            max_instances=1
        )
        logger.info("✅ Scheduled: Lead Batch Processing (4x daily)")
        
        # Job 2: Cleanup old leads (daily at 02:00 UTC)
        scheduler.add_job(
            cleanup_old_leads,
            trigger=CronTrigger(hour=2, minute=0),
            id='lead_cleanup',
            name='Lead Cleanup',
            replace_existing=True,
            max_instances=1
        )
        logger.info("✅ Scheduled: Lead Cleanup (daily at 02:00 UTC)")
        
        # NOTE: ICP Ingestion job will be added once ICP engine is implemented
        scheduler.add_job(run_scheduled_ingestion, 'cron', hour='*/4',
                  id='icp_scheduled_ingestion', replace_existing=True)
        # logger.info("✅ Scheduled: ICP Ingestion (every 4 hours)")
        
        # Start the scheduler
        scheduler.start()
        logger.info("✅ APScheduler started successfully!")
        
        # Log next run times
        jobs = scheduler.get_jobs()
        for job in jobs:
            logger.info(f"   • {job.name}: Next run at {job.next_run_time}")
        
    except Exception as e:
        logger.error(f"❌ Error starting scheduler: {e}")


def stop_scheduler():
    """Stop the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")