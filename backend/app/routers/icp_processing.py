# backend/app/api/v1/icp_processing.py
"""
API Endpoints for ICP Processing
- Manual trigger processing
- Job monitoring
- Stage metrics
"""

from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import uuid

from app.database import get_db
from app.services.batch_processor import create_batch_processor
from app.services.activity_logger import create_activity_logger
from app.models import ICPProcessingJob, ICP, RawLead
from app.auth import get_current_user  # Your auth dependency

router = APIRouter(prefix="/api/v1", tags=["ICP Processing"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ManualProcessRequest(BaseModel):
    """Request to manually trigger ICP processing"""
    raw_lead_ids: Optional[List[str]] = Field(
        None,
        description="Specific raw lead IDs to process (null = all pending)"
    )
    reprocess_existing: bool = Field(
        False,
        description="Re-run on already processed leads"
    )
    stages: Optional[List[str]] = Field(
        None,
        description="Specific stages to run (null = all stages)"
    )
    priority: str = Field(
        "normal",
        description="Job priority: high, normal, low"
    )


class JobResponse(BaseModel):
    """Processing job response"""
    job_id: str
    icp_id: str
    icp_name: str
    status: str
    total_leads: int
    processed_leads: int
    successful_leads: int
    failed_leads: int
    queued_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    estimated_completion_minutes: Optional[int]
    results_summary: Optional[dict]


class BatchTriggerRequest(BaseModel):
    """Request to trigger batch processing"""
    tenant_id: Optional[str] = Field(None, description="Specific tenant (null = current)")
    icp_ids: Optional[List[str]] = Field(None, description="Specific ICPs (null = all active)")
    max_leads: int = Field(1000, description="Max leads to process", ge=1, le=10000)


class StageCountsResponse(BaseModel):
    """Stage counts matching your exact JSON format"""
    raw_count: int
    new_count: int
    score_count: int
    enriched_count: int
    verified_count: int
    review_count: int
    qualified_count: int
    rejected_count: int
    exported_count: int
    total_count: int


# ============================================================================
# Manual Processing Endpoints
# ============================================================================

@router.post("/icps/{icp_id}/process")
async def trigger_icp_processing(
    icp_id: str,
    request: ManualProcessRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Manually trigger ICP processing
    
    **Use Cases:**
    - Process specific raw leads through an ICP
    - Re-process existing leads with updated rules
    - Run specific stages only (e.g., just re-score)
    
    **Example:**
    ```json
    {
        "raw_lead_ids": ["uuid1", "uuid2"],
        "reprocess_existing": false,
        "stages": ["score", "enrich"],
        "priority": "high"
    }
    ```
    """
    # Get ICP
    icp = db.query(ICP).filter(
        ICP.id == uuid.UUID(icp_id),
        ICP.tenant_id == current_user.tenant_id
    ).first()
    
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    # Get raw leads to process
    if request.raw_lead_ids:
        # Specific leads
        raw_leads = db.query(RawLead).filter(
            RawLead.id.in_([uuid.UUID(rid) for rid in request.raw_lead_ids]),
            RawLead.tenant_id == current_user.tenant_id
        ).all()
    else:
        # All pending leads
        raw_leads = db.query(RawLead).filter(
            RawLead.tenant_id == current_user.tenant_id,
            RawLead.processing_status == "pending"
        ).limit(1000).all()
    
    if not raw_leads:
        raise HTTPException(
            status_code=400,
            detail="No raw leads found to process"
        )
    
    # Filter if not reprocessing
    if not request.reprocess_existing:
        raw_leads = [
            rl for rl in raw_leads
            if str(icp.id) not in (rl.processed_by_icps or [])
        ]
    
    if not raw_leads:
        return {
            "message": "All leads already processed by this ICP",
            "job_id": None,
            "queued_leads": 0
        }
    
    # Create processing job
    from app.models import ICPProcessingJob
    
    job = ICPProcessingJob(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        icp_id=uuid.UUID(icp_id),
        job_type="manual_trigger",
        triggered_by="user",
        user_id=current_user.id,
        raw_lead_ids=[str(rl.id) for rl in raw_leads],
        stages_to_run=request.stages,
        status="queued",
        total_leads=len(raw_leads),
        queued_at=datetime.utcnow()
    )
    
    db.add(job)
    db.commit()
    
    # Start processing in background
    # (In production, use Celery or background tasks)
    # For now, return job ID for polling
    
    return {
        "job_id": str(job.id),
        "icp_id": icp_id,
        "icp_name": icp.name,
        "queued_leads": len(raw_leads),
        "status": "queued",
        "estimated_completion_minutes": len(raw_leads) // 20  # ~20 leads/min
    }


@router.post("/batch/trigger")
async def trigger_batch_processing(
    request: BatchTriggerRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Manually trigger batch processing
    
    **Use Cases:**
    - Force immediate batch run (don't wait for schedule)
    - Process specific tenant or ICPs
    - Control batch size
    
    **Example:**
    ```json
    {
        "icp_ids": ["uuid1", "uuid2"],
        "max_leads": 500
    }
    ```
    """
    tenant_id = request.tenant_id or str(current_user.tenant_id)
    
    # Create processor
    processor = create_batch_processor(db)
    
    # Run batch
    result = await processor.process_tenant_batch(
        tenant_id=tenant_id,
        icp_ids=request.icp_ids,
        max_leads=request.max_leads
    )
    
    return {
        "success": True,
        "jobs_created": result["jobs_created"],
        "leads_queued": result["leads_queued"],
        "tenant_id": tenant_id,
        "triggered_by": "manual"
    }


# ============================================================================
# Job Monitoring Endpoints
# ============================================================================

@router.get("/processing-jobs/{job_id}")
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get processing job status
    
    **Poll this endpoint to monitor job progress**
    """
    job = db.query(ICPProcessingJob).filter(
        ICPProcessingJob.id == uuid.UUID(job_id),
        ICPProcessingJob.tenant_id == current_user.tenant_id
    ).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Get ICP name
    icp = db.query(ICP).filter(ICP.id == job.icp_id).first()
    
    # Calculate progress
    progress_pct = 0
    if job.total_leads > 0:
        progress_pct = (job.processed_leads / job.total_leads) * 100
    
    # Estimate completion
    estimated_completion = None
    if job.status == "running" and job.started_at:
        elapsed = (datetime.utcnow() - job.started_at).total_seconds()
        if job.processed_leads > 0:
            rate = job.processed_leads / elapsed  # leads/sec
            remaining = job.total_leads - job.processed_leads
            eta_seconds = remaining / rate if rate > 0 else 0
            estimated_completion = datetime.utcnow() + timedelta(seconds=eta_seconds)
    
    return {
        "job_id": str(job.id),
        "icp_id": str(job.icp_id),
        "icp_name": icp.name if icp else None,
        "status": job.status,
        "progress_pct": round(progress_pct, 1),
        "total_leads": job.total_leads,
        "processed": job.processed_leads,
        "successful": job.successful_leads,
        "failed": job.failed_leads,
        "results_summary": job.results_summary,
        "queued_at": job.queued_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "estimated_completion": estimated_completion.isoformat() if estimated_completion else None,
        "error_message": job.error_message
    }


@router.get("/processing-jobs")
async def list_processing_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    icp_id: Optional[str] = Query(None, description="Filter by ICP"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    List processing jobs
    
    **Query Parameters:**
    - status: queued, running, completed, failed
    - icp_id: Filter by specific ICP
    - limit: Max results (1-100)
    """
    query = db.query(ICPProcessingJob).filter(
        ICPProcessingJob.tenant_id == current_user.tenant_id
    )
    
    if status:
        query = query.filter(ICPProcessingJob.status == status)
    
    if icp_id:
        query = query.filter(ICPProcessingJob.icp_id == uuid.UUID(icp_id))
    
    jobs = query.order_by(
        ICPProcessingJob.queued_at.desc()
    ).limit(limit).all()
    
    return {
        "jobs": [
            {
                "job_id": str(j.id),
                "icp_id": str(j.icp_id),
                "status": j.status,
                "total_leads": j.total_leads,
                "processed": j.processed_leads,
                "successful": j.successful_leads,
                "failed": j.failed_leads,
                "queued_at": j.queued_at.isoformat(),
                "completed_at": j.completed_at.isoformat() if j.completed_at else None
            }
            for j in jobs
        ],
        "total": len(jobs)
    }


# ============================================================================
# Stage Metrics Endpoints
# ============================================================================

@router.get("/icps/{icp_id}/stage-counts")
async def get_icp_stage_counts(
    icp_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get stage counts for a specific ICP
    
    **Returns your exact JSON format:**
    ```json
    {
        "raw_count": 0,
        "new_count": 0,
        "score_count": 0,
        "enriched_count": 1,
        "verified_count": 0,
        "review_count": 1,
        "qualified_count": 1,
        "rejected_count": 0,
        "exported_count": 0,
        "total_count": 3
    }
    ```
    """
    # Use the function we created in migration
    result = db.execute(
        "SELECT * FROM get_lead_stage_counts(:tenant_id, :icp_id)",
        {
            "tenant_id": str(current_user.tenant_id),
            "icp_id": icp_id
        }
    ).fetchone()
    
    if result:
        return dict(result[0])  # PostgreSQL returns JSONB
    
    return {
        "raw_count": 0,
        "new_count": 0,
        "score_count": 0,
        "enriched_count": 0,
        "verified_count": 0,
        "review_count": 0,
        "qualified_count": 0,
        "rejected_count": 0,
        "exported_count": 0,
        "total_count": 0
    }


@router.get("/stage-counts")
async def get_all_stage_counts(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get stage counts across all ICPs for current tenant
    """
    # Use the function without ICP filter
    result = db.execute(
        "SELECT * FROM get_lead_stage_counts(:tenant_id)",
        {"tenant_id": str(current_user.tenant_id)}
    ).fetchone()
    
    if result:
        return dict(result[0])
    
    return {
        "raw_count": 0,
        "new_count": 0,
        "score_count": 0,
        "enriched_count": 0,
        "verified_count": 0,
        "review_count": 0,
        "qualified_count": 0,
        "rejected_count": 0,
        "exported_count": 0,
        "total_count": 0
    }


@router.get("/leads/{lead_id}/history")
async def get_lead_history(
    lead_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get complete activity history for a lead
    
    **Shows every stage transition with details**
    """
    activity_logger = create_activity_logger(db)
    
    history = activity_logger.get_lead_history(lead_id)
    
    return {
        "lead_id": lead_id,
        "activity_count": len(history),
        "history": history
    }


@router.get("/metrics/stage-performance")
async def get_stage_performance(
    icp_id: Optional[str] = Query(None, description="Filter by ICP"),
    days: int = Query(7, ge=1, le=90, description="Days of data"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get stage transition performance metrics
    
    **Returns:**
    - Transition counts per stage
    - Average processing times
    - Conversion rates
    """
    activity_logger = create_activity_logger(db)
    
    from_date = datetime.utcnow() - timedelta(days=days)
    
    metrics = activity_logger.get_stage_metrics(
        tenant_id=str(current_user.tenant_id),
        icp_id=icp_id,
        from_date=from_date
    )
    
    return metrics


# ============================================================================
# Schedule Management Endpoints
# ============================================================================

@router.get("/batch-schedules")
async def list_batch_schedules(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    List batch processing schedules for current tenant
    """
    from app.models import BatchProcessingSchedule
    
    schedules = db.query(BatchProcessingSchedule).filter(
        BatchProcessingSchedule.tenant_id == current_user.tenant_id
    ).all()
    
    return {
        "schedules": [
            {
                "id": str(s.id),
                "name": s.schedule_name,
                "cron_expression": s.cron_expression,
                "is_enabled": s.is_enabled,
                "max_leads_per_batch": s.max_leads_per_batch,
                "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
                "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None
            }
            for s in schedules
        ]
    }


@router.put("/batch-schedules/{schedule_id}")
async def update_batch_schedule(
    schedule_id: str,
    enabled: Optional[bool] = None,
    max_leads: Optional[int] = None,
    cron_expression: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Update batch processing schedule
    
    **Example:**
    ```json
    {
        "enabled": true,
        "max_leads": 2000,
        "cron_expression": "*/30 * * * *"
    }
    ```
    """
    from app.models import BatchProcessingSchedule
    
    schedule = db.query(BatchProcessingSchedule).filter(
        BatchProcessingSchedule.id == uuid.UUID(schedule_id),
        BatchProcessingSchedule.tenant_id == current_user.tenant_id
    ).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    if enabled is not None:
        schedule.is_enabled = enabled
    
    if max_leads is not None:
        schedule.max_leads_per_batch = max_leads
    
    if cron_expression is not None:
        schedule.cron_expression = cron_expression
    
    schedule.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "id": str(schedule.id),
        "name": schedule.schedule_name,
        "is_enabled": schedule.is_enabled,
        "max_leads_per_batch": schedule.max_leads_per_batch,
        "cron_expression": schedule.cron_expression
    }