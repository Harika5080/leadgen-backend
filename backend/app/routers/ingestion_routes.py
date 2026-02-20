"""
Ingestion job routes - trigger and monitor data ingestion.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.models import DataSource, IngestionJob, User
from app.auth import get_current_user
from app.icp_engine.core.orchestrator import IngestionOrchestrator


router = APIRouter(prefix="/api/v1/ingestion", tags=["Ingestion"])


# ============================================================================
# SCHEMAS
# ============================================================================

class TriggerIngestionRequest(BaseModel):
    data_source_id: UUID
    limit_override: Optional[int] = None


class IngestionJobResponse(BaseModel):
    id: UUID
    data_source_id: UUID
    tenant_id: UUID
    job_type: str
    status: str
    
    # Statistics
    leads_processed: int = 0
    leads_qualified: int = 0
    leads_rejected: int = 0
    leads_duplicate: int = 0
    
    # Errors
    errors: list = []
    error_message: str = None
    
    # Timestamps
    started_at: datetime = None
    completed_at: datetime = None
    created_at: datetime
    
    # Computed
    duration_seconds: int = None
    
    class Config:
        from_attributes = True


class IngestionStatsResponse(BaseModel):
    total_jobs: int
    running_jobs: int
    completed_jobs: int
    failed_jobs: int
    total_leads_processed: int
    total_leads_qualified: int


# ============================================================================
# BACKGROUND TASK
# ============================================================================

async def run_ingestion_background(
    data_source_id: str,
    limit_override: Optional[int],
    db: AsyncSession
):
    """
    Run ingestion in background.
    """
    orchestrator = IngestionOrchestrator(db)
    try:
        await orchestrator.run_ingestion(
            data_source_id=data_source_id,
            job_type="manual",
            limit_override=limit_override
        )
    except Exception as e:
        print(f"Background ingestion error: {e}")


# ============================================================================
# ROUTES
# ============================================================================

@router.post("/trigger", response_model=IngestionJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_ingestion(
    request: TriggerIngestionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger a manual ingestion job.
    Returns immediately and runs in background.
    """
    # Verify data source exists and belongs to tenant
    stmt = select(DataSource).where(
        DataSource.id == request.data_source_id,
        DataSource.tenant_id == current_user.tenant_id
    )
    result = await db.execute(stmt)
    data_source = result.scalars().first()
    
    if not data_source:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    if not data_source.is_active:
        raise HTTPException(status_code=400, detail="Data source is not active")
    
    # Create job record
    job = IngestionJob(
        data_source_id=data_source.id,
        tenant_id=current_user.tenant_id,
        icp_id=data_source.icp_id,
        job_type="manual",
        status="pending"
    )
    
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    # Add background task
    background_tasks.add_task(
        run_ingestion_background,
        str(request.data_source_id),
        request.limit_override,
        db
    )
    
    # Return job
    response = IngestionJobResponse.from_orm(job)
    return response


@router.post("/trigger/{data_source_id}", response_model=IngestionJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_ingestion_by_id(
    data_source_id: UUID,
    background_tasks: BackgroundTasks,
    limit_override: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger ingestion for a specific data source (simplified endpoint).
    """
    request = TriggerIngestionRequest(
        data_source_id=data_source_id,
        limit_override=limit_override
    )
    
    return await trigger_ingestion(request, background_tasks, current_user, db)


@router.get("/jobs", response_model=List[IngestionJobResponse])
async def list_ingestion_jobs(
    data_source_id: UUID = None,
    status: str = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List ingestion jobs for current tenant.
    """
    stmt = select(IngestionJob).where(IngestionJob.tenant_id == current_user.tenant_id)
    
    if data_source_id:
        stmt = stmt.where(IngestionJob.data_source_id == data_source_id)
    
    if status:
        stmt = stmt.where(IngestionJob.status == status)
    
    stmt = stmt.order_by(IngestionJob.created_at.desc()).limit(limit)
    
    result = await db.execute(stmt)
    jobs = result.scalars().all()
    
    # Build responses
    responses = []
    for job in jobs:
        response = IngestionJobResponse.from_orm(job)
        
        # Calculate duration
        if job.started_at and job.completed_at:
            duration = (job.completed_at - job.started_at).total_seconds()
            response.duration_seconds = int(duration)
        
        responses.append(response)
    
    return responses


@router.get("/jobs/{job_id}", response_model=IngestionJobResponse)
async def get_ingestion_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific ingestion job.
    """
    stmt = select(IngestionJob).where(
        IngestionJob.id == job_id,
        IngestionJob.tenant_id == current_user.tenant_id
    )
    result = await db.execute(stmt)
    job = result.scalars().first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    
    response = IngestionJobResponse.from_orm(job)
    
    # Calculate duration
    if job.started_at and job.completed_at:
        duration = (job.completed_at - job.started_at).total_seconds()
        response.duration_seconds = int(duration)
    
    return response


@router.get("/stats", response_model=IngestionStatsResponse)
async def get_ingestion_stats(
    data_source_id: UUID = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get ingestion statistics for current tenant.
    """
    stmt = select(IngestionJob).where(IngestionJob.tenant_id == current_user.tenant_id)
    
    if data_source_id:
        stmt = stmt.where(IngestionJob.data_source_id == data_source_id)
    
    result = await db.execute(stmt)
    jobs = result.scalars().all()
    
    # Calculate stats
    total_jobs = len(jobs)
    running_jobs = len([j for j in jobs if j.status == "running"])
    completed_jobs = len([j for j in jobs if j.status == "completed"])
    failed_jobs = len([j for j in jobs if j.status == "failed"])
    
    total_leads_processed = sum(j.leads_processed or 0 for j in jobs)
    total_leads_qualified = sum(j.leads_qualified or 0 for j in jobs)
    
    return IngestionStatsResponse(
        total_jobs=total_jobs,
        running_jobs=running_jobs,
        completed_jobs=completed_jobs,
        failed_jobs=failed_jobs,
        total_leads_processed=total_leads_processed,
        total_leads_qualified=total_leads_qualified
    )