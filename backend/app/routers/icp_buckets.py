"""
ICP Bucket System Router
Handles bucket navigation, filtering, and lead movement
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.auth import get_current_user
from app.models import User, ICP, Lead
from app.schemas import (
    BucketStats,
    BucketLeadList,
    LeadBucketMove,
    ICPProcessingConfig,
    ICPProcessingConfigUpdate,
    BucketFlowAnalytics,
)
from app.services.bucket_manager import BucketManager


router = APIRouter(prefix="/api/v1/icps", tags=["ICP Buckets"])


@router.get("/{icp_id}/buckets", response_model=List[BucketStats])
async def get_bucket_statistics(
    icp_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get statistics for all buckets in an ICP."""
    icp = db.query(ICP).filter(
        ICP.id == icp_id,
        ICP.tenant_id == current_user.tenant_id
    ).first()
    
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    bucket_manager = BucketManager(db)
    stats = await bucket_manager.get_bucket_stats(icp_id)
    
    return stats


@router.get("/{icp_id}/buckets/{bucket}", response_model=BucketLeadList)
async def get_leads_in_bucket(
    icp_id: UUID,
    bucket: str,
    search: Optional[str] = None,
    company_size: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None,
    score_min: Optional[float] = Query(None, ge=0, le=100),
    score_max: Optional[float] = Query(None, ge=0, le=100),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get paginated list of leads in a specific bucket with filters."""
    icp = db.query(ICP).filter(
        ICP.id == icp_id,
        ICP.tenant_id == current_user.tenant_id
    ).first()
    
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    valid_buckets = ['raw_landing', 'scored', 'enriched', 'verified', 
                     'approved', 'pending_review', 'rejected']
    if bucket not in valid_buckets:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid bucket. Must be one of: {', '.join(valid_buckets)}"
        )
    
    bucket_manager = BucketManager(db)
    result = await bucket_manager.get_filtered_leads(
        icp_id=icp_id,
        bucket=bucket,
        search=search,
        company_size=company_size,
        city=city,
        state=state,
        country=country,
        score_min=score_min,
        score_max=score_max,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit
    )
    
    return result


@router.post("/{icp_id}/leads/move")
async def move_lead_to_bucket(
    icp_id: UUID,
    move_request: LeadBucketMove,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Move a lead to a different bucket."""
    icp = db.query(ICP).filter(
        ICP.id == icp_id,
        ICP.tenant_id == current_user.tenant_id
    ).first()
    
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    lead = db.query(Lead).filter(
        Lead.id == move_request.lead_id,
        Lead.tenant_id == current_user.tenant_id
    ).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    bucket_manager = BucketManager(db)
    
    try:
        await bucket_manager.move_lead_to_bucket(
            lead_id=move_request.lead_id,
            target_bucket=move_request.target_bucket,
            reason=move_request.reason,
            user_id=current_user.id,
            metadata=move_request.metadata
        )
        
        return {
            "success": True,
            "lead_id": str(move_request.lead_id),
            "new_bucket": move_request.target_bucket,
            "message": f"Lead moved to {move_request.target_bucket}"
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{icp_id}/processing-config", response_model=ICPProcessingConfig)
async def get_processing_config(
    icp_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get ICP processing configuration."""
    icp = db.query(ICP).filter(
        ICP.id == icp_id,
        ICP.tenant_id == current_user.tenant_id
    ).first()
    
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    return ICPProcessingConfig(
        icp_id=icp.id,
        enrichment_enabled=icp.enrichment_enabled,
        verification_enabled=icp.verification_enabled,
        auto_approve_threshold=float(icp.auto_approve_threshold),
        review_threshold=float(icp.review_threshold),
        auto_reject_threshold=float(icp.auto_reject_threshold),
        preferred_scrapers=icp.preferred_scrapers or ['crawlee', 'puppeteer'],
        enrichment_cost_per_lead=float(icp.enrichment_cost_per_lead),
        verification_cost_per_lead=float(icp.verification_cost_per_lead)
    )


@router.put("/{icp_id}/processing-config")
async def update_processing_config(
    icp_id: UUID,
    config: ICPProcessingConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update ICP processing configuration."""
    icp = db.query(ICP).filter(
        ICP.id == icp_id,
        ICP.tenant_id == current_user.tenant_id
    ).first()
    
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    if config.enrichment_enabled is not None:
        icp.enrichment_enabled = config.enrichment_enabled
    
    if config.verification_enabled is not None:
        icp.verification_enabled = config.verification_enabled
    
    if config.auto_approve_threshold is not None:
        icp.auto_approve_threshold = config.auto_approve_threshold
    
    if config.review_threshold is not None:
        icp.review_threshold = config.review_threshold
    
    if config.auto_reject_threshold is not None:
        icp.auto_reject_threshold = config.auto_reject_threshold
    
    if config.preferred_scrapers is not None:
        icp.preferred_scrapers = config.preferred_scrapers
    
    if config.enrichment_cost_per_lead is not None:
        icp.enrichment_cost_per_lead = config.enrichment_cost_per_lead
    
    if config.verification_cost_per_lead is not None:
        icp.verification_cost_per_lead = config.verification_cost_per_lead
    
    if (icp.auto_reject_threshold >= icp.review_threshold or
        icp.review_threshold >= icp.auto_approve_threshold):
        raise HTTPException(
            status_code=400,
            detail="Thresholds must be: reject < review < approve"
        )
    
    db.commit()
    db.refresh(icp)
    
    return {
        "success": True,
        "message": "Processing configuration updated"
    }


@router.get("/{icp_id}/bucket-flow", response_model=BucketFlowAnalytics)
async def get_bucket_flow_analytics(
    icp_id: UUID,
    period_days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get analytics for lead flow through buckets."""
    icp = db.query(ICP).filter(
        ICP.id == icp_id,
        ICP.tenant_id == current_user.tenant_id
    ).first()
    
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    bucket_manager = BucketManager(db)
    analytics = await bucket_manager.get_flow_analytics(icp_id, period_days)
    
    return analytics