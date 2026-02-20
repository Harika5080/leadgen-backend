"""
Ingestion Job management routes.
Handle manual runs and job monitoring.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.models import IngestionJob, DataSource, User
from app.auth import get_current_user


router = APIRouter(prefix="/api/v1/ingestion-jobs", tags=["Ingestion Jobs"])


class IngestionJobResponse(BaseModel):
    id: UUID
    data_source_id: UUID
    tenant_id: UUID
    job_type: str
    status: str
    leads_processed: int
    leads_qualified: int
    leads_rejected: int
    leads_duplicate: int
    started_at: datetime = None
    completed_at: datetime = None
    created_at: datetime
    
    class Config:
        from_attributes = True


@router.get("/", response_model=List[IngestionJobResponse])
async def list_ingestion_jobs(
    data_source_id: Optional[UUID] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List ingestion jobs."""
    stmt = select(IngestionJob).where(IngestionJob.tenant_id == current_user.tenant_id)
    
    if data_source_id:
        stmt = stmt.where(IngestionJob.data_source_id == data_source_id)
    
    stmt = stmt.order_by(desc(IngestionJob.created_at)).limit(limit)
    
    result = await db.execute(stmt)
    jobs = result.scalars().all()
    
    return jobs