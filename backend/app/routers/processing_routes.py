"""
ICP Processing Routes - Phase 3
================================
API endpoints to trigger and monitor ICP processing
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.services.icp_processor import ICPProcessor
from app.models import ICP, Tenant
from app.auth import get_current_user,get_current_tenant

router = APIRouter(prefix="/api/v1/processing", tags=["ICP Processing"])


# ============================================
# Request/Response Schemas
# ============================================

class ProcessLeadsRequest(BaseModel):
    """Request to process raw leads"""
    icp_id: Optional[str] = None
    limit: Optional[int] = None
    force_reprocess: bool = False


class ProcessLeadsResponse(BaseModel):
    """Response from processing"""
    status: str
    message: str
    leads_processed: int
    total_assignments: int
    by_icp: dict
    errors: list


class ProcessingStatsResponse(BaseModel):
    """Processing statistics"""
    total_leads: int
    raw_leads: int
    processed_leads: int
    error_leads: int
    orphaned_leads: int
    processing_percentage: float


# ============================================
# Endpoints
# ============================================

@router.post("/process-all", response_model=ProcessLeadsResponse)
async def process_all_leads(
    request: ProcessLeadsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    tenant = Depends(get_current_tenant)
):
    """
    Process all raw leads against active ICPs
    
    This runs in the background and returns immediately.
    Use the stats endpoint to monitor progress.
    """
    processor = ICPProcessor(db)
    
    # Run processing in background
    background_tasks.add_task(
        processor.process_raw_leads,
        tenant_id=str(tenant.id),
        icp_id=request.icp_id,
        limit=request.limit
    )
    
    return {
        "status": "started",
        "message": "Processing started in background",
        "leads_processed": 0,
        "total_assignments": 0,
        "by_icp": {},
        "errors": []
    }


@router.post("/process-sync", response_model=ProcessLeadsResponse)
async def process_leads_sync(
    request: ProcessLeadsRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    tenant = Depends(get_current_tenant)
):
    """
    Process raw leads synchronously (waits for completion)
    
    Use this for testing or when you need immediate results.
    For large batches, use /process-all (background processing).
    """
    processor = ICPProcessor(db)
    
    stats = await processor.process_raw_leads(
        tenant_id=str(tenant.id),
        icp_id=request.icp_id,
        limit=request.limit
    )
    
    return {
        "status": stats.get("status", "complete"),
        "message": stats.get("message", "Processing complete"),
        "leads_processed": stats.get("leads_processed", 0),
        "total_assignments": stats.get("total_assignments", 0),
        "by_icp": stats.get("by_icp", {}),
        "errors": stats.get("errors", [])
    }


@router.post("/icp/{icp_id}/reprocess")
async def reprocess_icp(
    icp_id: str,
    force: bool = False,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    tenant = Depends(get_current_tenant)
):
    """
    Reprocess all leads for a specific ICP
    
    Useful when ICP scoring rules change.
    
    Args:
        icp_id: ICP to reprocess
        force: If True, delete and recreate all assignments for this ICP
    """
    # Verify ICP belongs to tenant
    icp = db.query(ICP).filter(
        ICP.id == icp_id,
        ICP.tenant_id == tenant.id
    ).first()
    
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    processor = ICPProcessor(db)
    
    if background_tasks:
        # Run in background
        background_tasks.add_task(
            processor.reprocess_leads_for_icp,
            icp_id=icp_id,
            force=force
        )
        return {
            "status": "started",
            "message": f"Reprocessing ICP '{icp.name}' in background",
            "icp_id": icp_id,
            "force": force
        }
    else:
        # Run synchronously
        stats = await processor.reprocess_leads_for_icp(
            icp_id=icp_id,
            force=force
        )
        return {
            "status": "complete",
            "message": f"Reprocessed ICP '{icp.name}'",
            "icp_id": icp_id,
            "force": force,
            **stats
        }


@router.get("/stats", response_model=ProcessingStatsResponse)
async def get_processing_stats(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    tenant = Depends(get_current_tenant)
):
    """
    Get processing statistics for current tenant
    
    Shows how many leads are raw vs processed,
    and how many failed or matched no ICPs.
    """
    processor = ICPProcessor(db)
    stats = processor.get_processing_stats(str(tenant.id))
    
    return ProcessingStatsResponse(**stats)


@router.get("/raw-leads")
async def get_raw_leads(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    tenant = Depends(get_current_tenant)
):
    """
    Get list of raw (unprocessed) leads
    
    These are leads waiting to be scored against ICPs.
    """
    from app.models import Lead
    from sqlalchemy import or_
    
    raw_leads = db.query(Lead).filter(
        Lead.tenant_id == tenant.id,
        or_(
            Lead.processing_status == 'raw',
            Lead.processing_status == None
        )
    ).offset(offset).limit(limit).all()
    
    return {
        "leads": [
            {
                "id": str(lead.id),
                "email": lead.email,
                "name": lead.display_name,
                "company": lead.company_name,
                "job_title": lead.job_title,
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
                "data_source_id": str(lead.data_source_id) if lead.data_source_id else None
            }
            for lead in raw_leads
        ],
        "total": len(raw_leads),
        "offset": offset,
        "limit": limit
    }


@router.get("/orphaned-leads")
async def get_orphaned_leads(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    tenant = Depends(get_current_tenant)
):
    """
    Get leads that were processed but matched no ICPs
    
    These leads passed through the processor but didn't
    meet the criteria for any ICP.
    """
    from app.models import Lead
    
    orphaned = db.query(Lead).filter(
        Lead.tenant_id == tenant.id,
        Lead.processing_status == 'processed',
        Lead.icp_match_count == 0
    ).offset(offset).limit(limit).all()
    
    return {
        "leads": [
            {
                "id": str(lead.id),
                "email": lead.email,
                "name": lead.display_name,
                "company": lead.company_name,
                "job_title": lead.job_title,
                "processed_at": lead.last_processed_at.isoformat() if lead.last_processed_at else None
            }
            for lead in orphaned
        ],
        "total": len(orphaned),
        "offset": offset,
        "limit": limit
    }


@router.get("/error-leads")
async def get_error_leads(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    tenant = Depends(get_current_tenant)
):
    """
    Get leads that failed processing
    
    Shows which leads had errors during ICP matching.
    """
    from app.models import Lead
    
    error_leads = db.query(Lead).filter(
        Lead.tenant_id == tenant.id,
        Lead.processing_status == 'error'
    ).offset(offset).limit(limit).all()
    
    return {
        "leads": [
            {
                "id": str(lead.id),
                "email": lead.email,
                "name": lead.display_name,
                "error": lead.processing_error,
                "failed_at": lead.last_processed_at.isoformat() if lead.last_processed_at else None
            }
            for lead in error_leads
        ],
        "total": len(error_leads),
        "offset": offset,
        "limit": limit
    }