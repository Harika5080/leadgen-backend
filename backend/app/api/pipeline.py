"""Pipeline processing endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional
import logging
from uuid import UUID

from app.database import get_db
from app.auth import get_current_user
from app.models import Lead, User
from app.services.pipeline import lead_pipeline
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class PipelineProcessRequest(BaseModel):
    """Request to process leads through pipeline."""
    lead_ids: Optional[list[UUID]] = None
    status_filter: Optional[str] = "normalized"
    limit: int = 10
    skip_enrichment: bool = False
    skip_verification: bool = False


class PipelineProcessResponse(BaseModel):
    """Response from pipeline processing."""
    total: int
    successful: int
    failed: int
    enriched: int
    verified: int


@router.post("/process", response_model=PipelineProcessResponse)
async def process_leads(
    request: PipelineProcessRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger pipeline processing for leads.
    
    This endpoint allows testing the pipeline or processing specific leads.
    In production, this will be automated by the scheduler.
    """
    
    # Build query
    if request.lead_ids:
        # Process specific leads
        query = select(Lead).where(
            and_(
                Lead.id.in_(request.lead_ids),
                Lead.tenant_id == user.tenant_id
            )
        )
    else:
        # Process leads by status
        query = select(Lead).where(
            and_(
                Lead.tenant_id == user.tenant_id,
                Lead.status == request.status_filter
            )
        ).limit(request.limit)
    
    result = await db.execute(query)
    leads = result.scalars().all()
    
    if not leads:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No leads found matching criteria"
        )
    
    logger.info(f"Processing {len(leads)} leads for tenant {user.tenant_id}")
    
    # Process through pipeline
    stats = await lead_pipeline.process_batch(
        leads=list(leads),
        db=db,
        skip_enrichment=request.skip_enrichment,
        skip_verification=request.skip_verification
    )
    
    return PipelineProcessResponse(**stats)


@router.post("/process/{lead_id}", response_model=dict)
async def process_single_lead(
    lead_id: UUID,
    skip_enrichment: bool = Query(False),
    skip_verification: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Process a single lead through the pipeline."""
    
    result = await db.execute(
        select(Lead).where(
            and_(
                Lead.id == lead_id,
                Lead.tenant_id == user.tenant_id
            )
        )
    )
    lead = result.scalar_one_or_none()
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )
    
    try:
        await lead_pipeline.process_lead(
            lead=lead,
            db=db,
            skip_enrichment=skip_enrichment,
            skip_verification=skip_verification
        )
        await db.commit()
        
        return {
            "lead_id": str(lead.id),
            "status": lead.status,
            "fit_score": lead.fit_score,
            "email_verified": lead.email_verified,
            "enriched": bool(lead.enrichment_data)
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline processing failed: {str(e)}"
        )
