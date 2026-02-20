"""
Bucket Management API Router
Endpoints for bucket operations, transitions, and statistics
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.database import get_db
from app.auth import get_current_user
from app.models import User
from app.services.bucket_service import BucketService
from app.schemas.buckets import (
    BucketStats, ICPBucketOverview, BucketTransitionRequest,
    BucketTransitionResponse, ProcessingStageHistory,
    RejectionReasonCreate, RejectionResponse, RejectionOverride,
    LeadBucketFilter, BucketMetrics, ICPConfigUpdate, ICPConfigResponse
)

router = APIRouter(prefix="/api/v1/buckets", tags=["buckets"])


# ========================================
# BUCKET STATISTICS
# ========================================

@router.get("/icps/{icp_id}/overview", response_model=ICPBucketOverview)
async def get_icp_bucket_overview(
    icp_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get complete bucket overview for an ICP.
    Shows lead counts in each bucket and ICP configuration.
    """
    service = BucketService(db)
    overview = service.get_icp_bucket_overview(icp_id)
    
    if not overview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ICP {icp_id} not found"
        )
    
    return overview


@router.get("/icps/{icp_id}/stats", response_model=List[BucketStats])
async def get_bucket_stats(
    icp_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed statistics for each bucket.
    Includes lead counts and average time spent in each bucket.
    """
    service = BucketService(db)
    return service.get_bucket_stats(icp_id)


@router.get("/icps/{icp_id}/metrics", response_model=BucketMetrics)
async def get_bucket_metrics(
    icp_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive metrics for dashboard.
    Includes today's activity, costs, and conversion rates.
    """
    service = BucketService(db)
    try:
        metrics = service.get_bucket_metrics(icp_id, current_user.tenant_id)
        return metrics
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


# ========================================
# BUCKET TRANSITIONS
# ========================================

@router.post("/transition", response_model=BucketTransitionResponse)
async def move_leads_to_bucket(
    request: BucketTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Move one or more leads to a new bucket.
    Creates processing stage records and updates lead status.
    """
    service = BucketService(db)
    return service.move_leads_to_bucket(
        request=request,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )


@router.get("/leads/{lead_id}/history", response_model=ProcessingStageHistory)
async def get_lead_processing_history(
    lead_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get complete processing history for a lead.
    Shows all bucket transitions and time spent in each stage.
    """
    service = BucketService(db)
    return service.get_processing_history(lead_id)


# ========================================
# REJECTION TRACKING
# ========================================

@router.post("/rejections", response_model=RejectionResponse)
async def create_rejection(
    rejection: RejectionReasonCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a rejection record and move lead to rejected bucket.
    Tracks detailed reasons and failed criteria.
    """
    service = BucketService(db)
    try:
        return service.create_rejection(
            rejection=rejection,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/rejections/{lead_id}/override", response_model=RejectionResponse)
async def override_rejection(
    lead_id: UUID,
    override: RejectionOverride,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Override a rejection and move lead to a new bucket.
    Requires admin role.
    """
    if current_user.role not in ['admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can override rejections"
        )
    
    service = BucketService(db)
    try:
        return service.override_rejection(
            lead_id=lead_id,
            override_reason=override.override_reason,
            move_to_bucket=override.move_to_bucket,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ========================================
# LEAD FILTERING
# ========================================

@router.post("/icps/{icp_id}/leads/filter")
async def filter_leads_in_bucket(
    icp_id: UUID,
    filters: LeadBucketFilter,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Advanced filtering of leads within buckets.
    Supports demographics, company info, scores, and date ranges.
    """
    service = BucketService(db)
    leads, total = service.filter_leads_in_bucket(
        icp_id=icp_id,
        tenant_id=current_user.tenant_id,
        filters=filters
    )
    
    # Convert to response format
    from app.schemas.lead import LeadResponse
    lead_responses = [LeadResponse.from_orm(lead) for lead in leads]
    
    return {
        "leads": lead_responses,
        "total": total,
        "page": filters.page,
        "page_size": filters.page_size,
        "total_pages": (total + filters.page_size - 1) // filters.page_size
    }


# ========================================
# ICP CONFIGURATION
# ========================================

@router.get("/icps/{icp_id}/config", response_model=ICPConfigResponse)
async def get_icp_config(
    icp_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get ICP bucket configuration.
    Shows thresholds and processing toggles.
    """
    from app.models import ICP
    
    icp = db.query(ICP).filter(
        ICP.id == icp_id,
        ICP.tenant_id == current_user.tenant_id
    ).first()
    
    if not icp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ICP {icp_id} not found"
        )
    
    return ICPConfigResponse(
        icp_id=icp.id,
        enrichment_enabled=icp.enrichment_enabled,
        verification_enabled=icp.verification_enabled,
        auto_approve_threshold=float(icp.auto_approve_threshold),
        review_threshold=float(icp.review_threshold),
        auto_reject_threshold=float(icp.auto_reject_threshold),
        preferred_scrapers=icp.preferred_scrapers,
        enrichment_cost_per_lead=float(icp.enrichment_cost_per_lead),
        verification_cost_per_lead=float(icp.verification_cost_per_lead)
    )


@router.put("/icps/{icp_id}/config", response_model=ICPConfigResponse)
async def update_icp_config(
    icp_id: UUID,
    config: ICPConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update ICP bucket configuration.
    Requires admin role.
    """
    if current_user.role not in ['admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update ICP configuration"
        )
    
    service = BucketService(db)
    try:
        icp = service.update_icp_config(
            icp_id=icp_id,
            config=config,
            tenant_id=current_user.tenant_id
        )
        
        return ICPConfigResponse(
            icp_id=icp.id,
            enrichment_enabled=icp.enrichment_enabled,
            verification_enabled=icp.verification_enabled,
            auto_approve_threshold=float(icp.auto_approve_threshold),
            review_threshold=float(icp.review_threshold),
            auto_reject_threshold=float(icp.auto_reject_threshold),
            preferred_scrapers=icp.preferred_scrapers,
            enrichment_cost_per_lead=float(icp.enrichment_cost_per_lead),
            verification_cost_per_lead=float(icp.verification_cost_per_lead)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


# ========================================
# BULK OPERATIONS
# ========================================

@router.post("/bulk/approve", response_model=BucketTransitionResponse)
async def bulk_approve_leads(
    lead_ids: List[UUID],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Bulk approve leads (move to approved bucket).
    """
    request = BucketTransitionRequest(
        lead_ids=lead_ids,
        new_bucket='approved',
        reason='Bulk approval',
        metadata={'bulk_operation': True}
    )
    
    service = BucketService(db)
    return service.move_leads_to_bucket(
        request=request,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )


@router.post("/bulk/reject", response_model=BucketTransitionResponse)
async def bulk_reject_leads(
    lead_ids: List[UUID],
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Bulk reject leads (move to rejected bucket).
    """
    request = BucketTransitionRequest(
        lead_ids=lead_ids,
        new_bucket='rejected',
        reason=reason or 'Bulk rejection',
        metadata={'bulk_operation': True}
    )
    
    service = BucketService(db)
    return service.move_leads_to_bucket(
        request=request,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )


@router.post("/bulk/review", response_model=BucketTransitionResponse)
async def bulk_send_to_review(
    lead_ids: List[UUID],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Bulk send leads to review queue (move to pending_review bucket).
    """
    request = BucketTransitionRequest(
        lead_ids=lead_ids,
        new_bucket='pending_review',
        reason='Bulk send to review',
        metadata={'bulk_operation': True}
    )
    
    service = BucketService(db)
    return service.move_leads_to_bucket(
        request=request,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )