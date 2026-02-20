"""
Raw Leads Router
Handles raw lead ingestion from scrapers and processing triggers
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.auth import get_current_user
from app.models import User, ICP, RawLead
from app.schemas import (
    RawLeadBatch,
    RawLeadResponse,
    RawLeadList,
    RawLeadUpdate,
    ProcessingResult,
    RawLeadSummaryStats,
    RawLeadFilter,
)
from app.services.raw_lead_processor import RawLeadProcessor


router = APIRouter(prefix="/api/v1/raw-leads", tags=["Raw Leads"])


@router.post("/batch", response_model=ProcessingResult)
async def create_raw_lead_batch(
    batch: RawLeadBatch,
    background_tasks: BackgroundTasks,
    process_immediately: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a batch of raw leads from scrapers.
    
    Supports:
    - Crawlee, Puppeteer, Nutch, PySpider outputs
    - Manual uploads and API imports
    - CSV batch imports
    
    Options:
    - process_immediately: Start processing right away
    - Default: Queue for scheduled batch processing
    """
    # Verify ICP exists and user has access
    icp = db.query(ICP).filter(
        ICP.id == batch.icp_id,
        ICP.tenant_id == current_user.tenant_id
    ).first()
    
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    processor = RawLeadProcessor(db)
    
    try:
        result = await processor.create_batch(
            icp_id=batch.icp_id,
            tenant_id=current_user.tenant_id,
            source_name=batch.source_name,
            scraper_type=batch.scraper_type,
            leads=batch.leads
        )
        
        # Optionally process immediately
        if process_immediately:
            background_tasks.add_task(
                processor.process_pending_leads,
                icp_id=batch.icp_id
            )
        
        return ProcessingResult(
            success=True,
            total_submitted=len(batch.leads),
            accepted=result['accepted'],
            rejected=result['rejected'],
            created_raw_lead_ids=result['raw_lead_ids'],
            failed_raw_lead_ids=[],
            errors=result['errors']
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create batch: {str(e)}"
        )


@router.get("/", response_model=RawLeadList)
async def list_raw_leads(
    icp_id: Optional[UUID] = None,
    status: Optional[str] = Query(None, pattern="^(pending|processing|processed|failed)$"),
    scraper_type: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List raw leads with filtering and pagination.
    
    Filters:
    - icp_id: Filter by specific ICP
    - status: pending, processing, processed, failed
    - scraper_type: crawlee, puppeteer, etc.
    - date_from/date_to: Date range
    - search: Search in email or scraped data
    """
    processor = RawLeadProcessor(db)
    
    result = await processor.list_raw_leads(
        tenant_id=current_user.tenant_id,
        icp_id=icp_id,
        status=status,
        scraper_type=scraper_type,
        date_from=date_from,
        date_to=date_to,
        search=search,
        page=page,
        limit=limit
    )
    
    return result


@router.get("/{raw_lead_id}", response_model=RawLeadResponse)
async def get_raw_lead(
    raw_lead_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single raw lead by ID."""
    raw_lead = db.query(RawLead).filter(
        RawLead.id == raw_lead_id,
        RawLead.tenant_id == current_user.tenant_id
    ).first()
    
    if not raw_lead:
        raise HTTPException(status_code=404, detail="Raw lead not found")
    
    return RawLeadResponse.model_validate(raw_lead)


@router.put("/{raw_lead_id}", response_model=RawLeadResponse)
async def update_raw_lead(
    raw_lead_id: UUID,
    update: RawLeadUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a raw lead's scraped data.
    
    Useful for:
    - Correcting scraper errors
    - Adding missing fields
    - Re-scraping with updated data
    """
    raw_lead = db.query(RawLead).filter(
        RawLead.id == raw_lead_id,
        RawLead.tenant_id == current_user.tenant_id
    ).first()
    
    if not raw_lead:
        raise HTTPException(status_code=404, detail="Raw lead not found")
    
    if raw_lead.processing_status == 'processed':
        raise HTTPException(
            status_code=400,
            detail="Cannot update already processed lead"
        )
    
    # Update scraped data
    if update.scraped_data:
        raw_lead.scraped_data = update.scraped_data
    
    if update.notes:
        raw_lead.notes = update.notes
    
    raw_lead.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(raw_lead)
    
    return RawLeadResponse.model_validate(raw_lead)


@router.delete("/{raw_lead_id}")
async def delete_raw_lead(
    raw_lead_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a raw lead (soft delete)."""
    raw_lead = db.query(RawLead).filter(
        RawLead.id == raw_lead_id,
        RawLead.tenant_id == current_user.tenant_id
    ).first()
    
    if not raw_lead:
        raise HTTPException(status_code=404, detail="Raw lead not found")
    
    db.delete(raw_lead)
    db.commit()
    
    return {"success": True, "message": "Raw lead deleted"}


@router.post("/process")
async def trigger_processing(
    background_tasks: BackgroundTasks,
    icp_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually trigger processing of pending raw leads.
    
    If icp_id provided: Process only that ICP's pending leads
    If no icp_id: Process all pending leads for tenant
    """
    processor = RawLeadProcessor(db)
    
    if icp_id:
        # Verify ICP access
        icp = db.query(ICP).filter(
            ICP.id == icp_id,
            ICP.tenant_id == current_user.tenant_id
        ).first()
        
        if not icp:
            raise HTTPException(status_code=404, detail="ICP not found")
        
        background_tasks.add_task(
            processor.process_pending_leads,
            icp_id=icp_id
        )
        
        message = f"Processing started for ICP {icp.name}"
    else:
        background_tasks.add_task(
            processor.process_all_pending,
            tenant_id=current_user.tenant_id
        )
        
        message = "Processing started for all pending leads"
    
    return {
        "success": True,
        "message": message
    }


@router.post("/{raw_lead_id}/retry")
async def retry_failed_lead(
    raw_lead_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retry processing a failed raw lead."""
    raw_lead = db.query(RawLead).filter(
        RawLead.id == raw_lead_id,
        RawLead.tenant_id == current_user.tenant_id
    ).first()
    
    if not raw_lead:
        raise HTTPException(status_code=404, detail="Raw lead not found")
    
    if raw_lead.processing_status != 'failed':
        raise HTTPException(
            status_code=400,
            detail="Can only retry failed leads"
        )
    
    # Reset status to pending
    raw_lead.processing_status = 'pending'
    raw_lead.error_message = None
    raw_lead.updated_at = datetime.utcnow()
    
    db.commit()
    
    # Trigger processing
    processor = RawLeadProcessor(db)
    background_tasks.add_task(
        processor.process_single_lead,
        raw_lead_id=raw_lead_id
    )
    
    return {
        "success": True,
        "message": "Lead queued for retry",
        "raw_lead_id": str(raw_lead_id)
    }


@router.get("/stats/summary", response_model=RawLeadSummaryStats)
async def get_summary_stats(
    icp_id: Optional[UUID] = None,
    period_days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get summary statistics for raw leads.
    
    Returns:
    - Counts by status and scraper type
    - Processing success rate
    - Average processing time
    - Recent activity
    """
    processor = RawLeadProcessor(db)
    
    stats = await processor.get_summary_stats(
        tenant_id=current_user.tenant_id,
        icp_id=icp_id,
        period_days=period_days
    )
    
    return stats