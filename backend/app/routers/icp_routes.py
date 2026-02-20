"""
ICP Routes - COMPLETE RESPONSE FIELDS
Returns ALL fields needed by frontend components
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.models import ICP, Lead, LeadICPAssignment, User
from app.auth import get_current_user

router = APIRouter(prefix="/api/v1/icps", tags=["ICPs"])


# ============================================================================
# SPECIFIC ROUTES FIRST
# ============================================================================

@router.api_route("/validate-name", methods=["GET", "POST"])
async def validate_icp_name(
    name: str = Query(..., description="ICP name to validate"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Validate ICP name uniqueness"""
    result = await db.execute(
        select(ICP).where(
            ICP.tenant_id == current_user.tenant_id,
            func.lower(ICP.name) == name.lower()
        )
    )
    existing = result.scalar_one_or_none()
    
    return {
        "available": not bool(existing),
        "message": f"ICP name '{name}' is {'already in use' if existing else 'available'}"
    }


@router.get("/")
async def list_icps(
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all ICPs"""
    query = select(ICP).where(ICP.tenant_id == current_user.tenant_id)
    if is_active is not None:
        query = query.where(ICP.is_active == is_active)
    query = query.order_by(ICP.created_at.desc())
    
    result = await db.execute(query)
    icps = result.scalars().all()
    
    response_list = []
    for icp in icps:
        count_result = await db.execute(
            select(LeadICPAssignment.status).where(LeadICPAssignment.icp_id == icp.id)
        )
        statuses = [row[0] for row in count_result.all()]
        
        response_list.append({
            "id": str(icp.id),
            "name": icp.name,
            "description": icp.description,
            "tenant_id": str(icp.tenant_id),
            "is_active": icp.is_active,
            "created_at": icp.created_at.isoformat() if icp.created_at else None,
            "lead_count": len(statuses),
            "qualified_count": statuses.count("qualified"),
            "pending_review_count": statuses.count("pending_review")
        })
    
    return response_list


@router.post("/")
async def create_icp(
    icp_data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new ICP"""
    if not icp_data.get('name'):
        raise HTTPException(status_code=400, detail="ICP name is required")
    
    existing_result = await db.execute(
        select(ICP).where(
            ICP.tenant_id == current_user.tenant_id,
            func.lower(ICP.name) == icp_data.get('name', '').lower()
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"ICP name '{icp_data.get('name')}' already exists")
    
    new_icp = ICP(
        name=icp_data.get('name'),
        description=icp_data.get('description'),
        tenant_id=current_user.tenant_id,
        scoring_rules=icp_data.get('scoring_rules', {}),
        filter_rules=icp_data.get('filter_rules', {}),
        weight_config=icp_data.get('weight_config', {}),
        auto_approve_threshold=icp_data.get('auto_approve_threshold', 80.0),
        review_threshold=icp_data.get('review_threshold', 50.0),
        auto_reject_threshold=icp_data.get('auto_reject_threshold', 30.0),
        is_active=icp_data.get('is_active', True),
        created_by=current_user.id
    )
    
    db.add(new_icp)
    await db.commit()
    await db.refresh(new_icp)
    
    # ✅ RETURN COMPLETE OBJECT (for redirect to overview)
    return {
        "id": str(new_icp.id),
        "name": new_icp.name,
        "description": new_icp.description,
        "tenant_id": str(new_icp.tenant_id),
        
        # Configuration
        "scoring_rules": new_icp.scoring_rules or {},
        "weight_config": new_icp.weight_config or {},
        "auto_approve_threshold": float(new_icp.auto_approve_threshold) if new_icp.auto_approve_threshold else 80.0,
        "review_threshold": float(new_icp.review_threshold) if new_icp.review_threshold else 50.0,
        "auto_reject_threshold": float(new_icp.auto_reject_threshold) if new_icp.auto_reject_threshold else 30.0,
        
        "is_active": new_icp.is_active,
        "created_at": new_icp.created_at.isoformat() if new_icp.created_at else None,
        "lead_count": 0,
        "qualified_count": 0,
        "pending_review_count": 0
    }


# ============================================================================
# PARAMETERIZED ROUTES
# ============================================================================

@router.get("/{icp_id}")
async def get_icp(
    icp_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get single ICP - COMPLETE RESPONSE"""
    result = await db.execute(
        select(ICP).where(ICP.id == icp_id, ICP.tenant_id == current_user.tenant_id)
    )
    icp = result.scalar_one_or_none()
    
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    count_result = await db.execute(
        select(LeadICPAssignment.status).where(LeadICPAssignment.icp_id == icp.id)
    )
    statuses = [row[0] for row in count_result.all()]
    
    # ✅ RETURN COMPLETE OBJECT (all fields frontend needs)
    return {
        "id": str(icp.id),
        "name": icp.name,
        "description": icp.description,
        "tenant_id": str(icp.tenant_id),
        
        # ✅ Configuration (needed by ICPDetail component)
        "scoring_rules": icp.scoring_rules or {},
        "weight_config": icp.weight_config or {},
        "auto_approve_threshold": float(icp.auto_approve_threshold) if icp.auto_approve_threshold else 80.0,
        "review_threshold": float(icp.review_threshold) if icp.review_threshold else 50.0,
        "auto_reject_threshold": float(icp.auto_reject_threshold) if icp.auto_reject_threshold else 30.0,
        
        "is_active": icp.is_active,
        "created_at": icp.created_at.isoformat() if icp.created_at else None,
        "lead_count": len(statuses),
        "qualified_count": statuses.count("qualified"),
        "pending_review_count": statuses.count("pending_review")
    }


@router.put("/{icp_id}")
async def update_icp(
    icp_id: UUID,
    icp_data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an ICP"""
    result = await db.execute(
        select(ICP).where(ICP.id == icp_id, ICP.tenant_id == current_user.tenant_id)
    )
    icp = result.scalar_one_or_none()
    
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    if 'name' in icp_data:
        icp.name = icp_data['name']
    if 'description' in icp_data:
        icp.description = icp_data['description']
    if 'scoring_rules' in icp_data:
        icp.scoring_rules = icp_data['scoring_rules']
    if 'weight_config' in icp_data:
        icp.weight_config = icp_data['weight_config']
    if 'auto_approve_threshold' in icp_data:
        icp.auto_approve_threshold = icp_data['auto_approve_threshold']
    if 'review_threshold' in icp_data:
        icp.review_threshold = icp_data['review_threshold']
    if 'auto_reject_threshold' in icp_data:
        icp.auto_reject_threshold = icp_data['auto_reject_threshold']
    if 'is_active' in icp_data:
        icp.is_active = icp_data['is_active']
    
    icp.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(icp)
    
    return {
        "id": str(icp.id),
        "name": icp.name,
        "description": icp.description,
        "scoring_rules": icp.scoring_rules,
        "weight_config": icp.weight_config,
        "auto_approve_threshold": float(icp.auto_approve_threshold),
        "review_threshold": float(icp.review_threshold),
        "auto_reject_threshold": float(icp.auto_reject_threshold),
        "is_active": icp.is_active,
        "updated_at": icp.updated_at.isoformat() if icp.updated_at else None
    }


@router.delete("/{icp_id}")
async def delete_icp(
    icp_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an ICP"""
    result = await db.execute(
        select(ICP).where(ICP.id == icp_id, ICP.tenant_id == current_user.tenant_id)
    )
    icp = result.scalar_one_or_none()
    
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    await db.delete(icp)
    await db.commit()
    
    return {"message": "ICP deleted successfully", "id": str(icp_id)}


@router.get("/{icp_id}/stats")
async def get_bucket_stats(
    icp_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get bucket stats"""
    icp_result = await db.execute(
        select(ICP).where(ICP.id == icp_id, ICP.tenant_id == current_user.tenant_id)
    )
    if not icp_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="ICP not found")
    
    all_assignments_result = await db.execute(
        select(LeadICPAssignment.bucket).where(LeadICPAssignment.icp_id == icp_id)
    )
    all_buckets = [row[0] for row in all_assignments_result.all()]
    
    return {
        "raw_count": 0,
        "new_count": all_buckets.count("new"),
        "score_count": all_buckets.count("score"),
        "enriched_count": all_buckets.count("enriched"),
        "verified_count": all_buckets.count("verified"),
        "review_count": all_buckets.count("review"),
        "qualified_count": all_buckets.count("qualified"),
        "rejected_count": all_buckets.count("rejected"),
        "exported_count": all_buckets.count("exported"),
        "total_count": len(all_buckets)
    }


@router.get("/{icp_id}/leads")
async def get_icp_leads(
    icp_id: UUID,
    status: Optional[str] = None,
    bucket: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all leads for an ICP
    ONLY uses columns that exist in your database
    """
    icp_result = await db.execute(
        select(ICP).where(ICP.id == icp_id, ICP.tenant_id == current_user.tenant_id)
    )
    icp = icp_result.scalar_one_or_none()
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    limit = min(limit, 1000)
    
    # Build query
    query = select(LeadICPAssignment).where(LeadICPAssignment.icp_id == icp_id)
    
    if status:
        query = query.where(LeadICPAssignment.status == status)
    if bucket:
        query = query.where(LeadICPAssignment.bucket == bucket)
    
    query = query.order_by(
        LeadICPAssignment.fit_score_percentage.desc(),
        LeadICPAssignment.created_at.desc()
    ).offset(skip).limit(limit)
    
    result = await db.execute(query)
    assignments = result.scalars().all()
    
    # Build response with ONLY existing columns
    leads_data = []
    for assignment in assignments:
        lead_result = await db.execute(
            select(Lead).where(Lead.id == assignment.lead_id)
        )
        lead = lead_result.scalar_one_or_none()
        
        if lead:
            if lead.first_name and lead.last_name:
                full_name = f"{lead.first_name} {lead.last_name}"
            elif lead.first_name:
                full_name = lead.first_name
            else:
                full_name = lead.email.split('@')[0] if lead.email else "Unknown"
            
            # ONLY columns from your working SQL query
            leads_data.append({
                # IDs
                "lead_id": str(lead.id),
                "assignment_id": str(assignment.id),
                "icp_id": str(assignment.icp_id),
                "tenant_id": str(assignment.tenant_id),
                
                # Lead info
                "email": lead.email,
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "full_name": full_name,
                "job_title": lead.job_title,
                "company_name": lead.company_name,
                "company_industry": lead.company_industry,
                "company_size": lead.company_size,
                "city": lead.city,
                "state": lead.state,
                "country": lead.country,
                
                # === ONLY THESE ASSIGNMENT COLUMNS (from your SQL) ===
                "fit_score": float(assignment.fit_score) if assignment.fit_score else None,
                "fit_score_percentage": float(assignment.fit_score_percentage) if assignment.fit_score_percentage else None,
                "scoring_details": assignment.scoring_details,
                "scoring_version": assignment.scoring_version,
                "status": assignment.status,
                "bucket": assignment.bucket,
                "processed_at": assignment.processed_at.isoformat() if assignment.processed_at else None,
                "qualified_at": assignment.qualified_at.isoformat() if assignment.qualified_at else None,
                "reviewed_at": assignment.reviewed_at.isoformat() if assignment.reviewed_at else None,
                "reviewed_by": str(assignment.reviewed_by) if assignment.reviewed_by else None,
                "review_notes": assignment.review_notes,
                "exported_to_crm": assignment.exported_to_crm or False,
                "exported_at": assignment.exported_at.isoformat() if assignment.exported_at else None,
                "export_metadata": assignment.export_metadata,
                "created_at": assignment.created_at.isoformat() if assignment.created_at else None,
                "updated_at": assignment.updated_at.isoformat() if assignment.updated_at else None,
                
                # NOT INCLUDED (don't exist in DB):
                # - icp_score_confidence
                # - stage_updated_at  
                # - processing_job_id
            })
    
    count_query = select(func.count(LeadICPAssignment.id)).where(
        LeadICPAssignment.icp_id == icp_id
    )
    if status:
        count_query = count_query.where(LeadICPAssignment.status == status)
    if bucket:
        count_query = count_query.where(LeadICPAssignment.bucket == bucket)
    
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0
    
    return {
        "icp_id": str(icp_id),
        "icp_name": icp.name,
        "filters": {"status": status, "bucket": bucket},
        "pagination": {
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": (skip + limit) < total
        },
        "leads": leads_data
    }


@router.get("/{icp_id}/leads/{bucket}")
async def get_leads_by_bucket(
    icp_id: UUID,
    bucket: str,
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get leads by bucket"""
    icp_result = await db.execute(
        select(ICP).where(ICP.id == icp_id, ICP.tenant_id == current_user.tenant_id)
    )
    icp = icp_result.scalar_one_or_none()
    if not icp:
        raise HTTPException(status_code=404, detail="ICP not found")
    
    assignments_query = select(LeadICPAssignment).where(
        LeadICPAssignment.icp_id == icp_id,
        LeadICPAssignment.bucket == bucket
    ).order_by(
        LeadICPAssignment.fit_score_percentage.desc()
    ).offset(skip).limit(limit)
    
    assignments_result = await db.execute(assignments_query)
    assignments = assignments_result.scalars().all()
    
    leads_data = []
    for assignment in assignments:
        lead_result = await db.execute(
            select(Lead).where(Lead.id == assignment.lead_id)
        )
        lead = lead_result.scalar_one_or_none()
        
        if lead:
            if lead.first_name and lead.last_name:
                full_name = f"{lead.first_name} {lead.last_name}"
            elif lead.first_name:
                full_name = lead.first_name
            else:
                full_name = lead.email.split('@')[0] if lead.email else "Unknown"
            
            leads_data.append({
                "id": str(lead.id),
                "email": lead.email,
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "full_name": full_name,
                "job_title": lead.job_title,
                "company_name": lead.company_name,
                "company_industry": lead.company_industry,
                "company_size": lead.company_size,
                "city": lead.city,
                "state": lead.state,
                "country": lead.country,
                "fit_score_percentage": float(assignment.fit_score_percentage) if assignment.fit_score_percentage else None,
                "status": assignment.status,
                "bucket": assignment.bucket,
                "created_at": lead.created_at.isoformat() if lead.created_at else None
            })
    
    count_result = await db.execute(
        select(func.count(LeadICPAssignment.id)).where(
            LeadICPAssignment.icp_id == icp_id,
            LeadICPAssignment.bucket == bucket
        )
    )
    total = count_result.scalar() or 0
    
    return {
        "icp_id": str(icp_id),
        "icp_name": icp.name,
        "bucket": bucket,
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": leads_data
    }


@router.put("/{icp_id}/leads/{lead_id}/review")
async def review_lead(
    icp_id: UUID,
    lead_id: UUID,
    action: str,
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Review a lead"""
    result = await db.execute(
        select(LeadICPAssignment).where(
            LeadICPAssignment.lead_id == lead_id,
            LeadICPAssignment.icp_id == icp_id
        )
    )
    assignment = result.scalar_one_or_none()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    if action == 'approve':
        assignment.status = 'qualified'
        assignment.qualified_at = datetime.utcnow()
    elif action == 'reject':
        assignment.status = 'rejected'
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    assignment.reviewed_at = datetime.utcnow()
    assignment.reviewed_by = current_user.id
    if notes:
        assignment.review_notes = notes
    
    await db.commit()
    
    return {
        "message": f"Lead {action}d",
        "lead_id": str(lead_id),
        "icp_id": str(icp_id),
        "status": assignment.status
    }