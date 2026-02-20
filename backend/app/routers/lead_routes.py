"""
Lead Routes - CORRECTED TO MATCH ACTUAL MODEL
Uses actual fields: email_verification_status, email_verification_confidence, source, created_at
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, delete, update
from typing import Optional, List
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from io import StringIO
import csv
import math

from app.database import get_db
from app.models import Lead, LeadICPAssignment, ICP, User
from app.auth import get_current_user

router = APIRouter(prefix="/api/v1/leads", tags=["Leads"])

# ============================================================================
# SCHEMAS
# ============================================================================

class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None

class ProcessLeadsRequest(BaseModel):
    lead_ids: List[UUID]

class BulkDeleteRequest(BaseModel):
    lead_ids: List[UUID]

class BulkReviewRequest(BaseModel):
    lead_ids: List[UUID]
    decision: str  # 'approved' or 'rejected'
    notes: Optional[str] = None

class ExportRequest(BaseModel):
    lead_ids: List[UUID]
    format: str = 'csv'

class AddNoteRequest(BaseModel):
    content: str

# ============================================================================
# LIST LEADS - ENHANCED WITH ADVANCED FILTERING
# ============================================================================

@router.get("/")
async def list_leads(
    # Pagination
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    
    # Bucket/Stage Filtering (uses LeadICPAssignment)
    bucket: Optional[str] = None,
    buckets: Optional[str] = None,
    
    # ICP Filtering
    icp_id: Optional[UUID] = None,
    
    # Source Filtering (uses 'source' field)
    source: Optional[str] = None,
    
    # Search
    search: Optional[str] = None,
    
    # Score Filtering (uses LeadICPAssignment)
    score_min: Optional[float] = Query(None, ge=0, le=100),
    score_max: Optional[float] = Query(None, ge=0, le=100),
    
    # Verification Filtering (uses email_verification_status)
    verification_status: Optional[str] = None,  # valid, invalid, risky, unknown
    email_verified: Optional[bool] = None,
    
    # Date Filtering
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    
    # Data Quality Filtering
    has_email: Optional[bool] = None,
    has_phone: Optional[bool] = None,
    
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Enhanced leads listing with comprehensive filtering
    Uses actual Lead model fields
    """
    
    # Start with base query
    query = select(Lead).where(Lead.tenant_id == current_user.tenant_id)
    
    # Bucket filtering (requires join with LeadICPAssignment)
    needs_assignment_join = False
    if bucket or buckets or icp_id or score_min is not None or score_max is not None:
        needs_assignment_join = True
    
    if needs_assignment_join:
        query = query.join(LeadICPAssignment, Lead.id == LeadICPAssignment.lead_id)
        
        if bucket:
            query = query.where(LeadICPAssignment.bucket == bucket)
        
        if buckets:
            bucket_list = [b.strip() for b in buckets.split(',')]
            query = query.where(LeadICPAssignment.bucket.in_(bucket_list))
        
        if icp_id:
            query = query.where(LeadICPAssignment.icp_id == icp_id)
        
        # Score filtering
        if score_min is not None:
            query = query.where(LeadICPAssignment.fit_score_percentage >= score_min)
        if score_max is not None:
            query = query.where(LeadICPAssignment.fit_score_percentage <= score_max)
        
        # Make distinct to avoid duplicates from joins
        query = query.distinct()
    
    # Source filtering (uses 'source' field)
    if source:
        query = query.where(Lead.source == source)
    
    # Search
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Lead.email.ilike(search_term),
                Lead.first_name.ilike(search_term),
                Lead.last_name.ilike(search_term),
                Lead.company_name.ilike(search_term)
            )
        )
    
    # ✅ Verification filtering (uses email_verification_status)
    if verification_status:
        query = query.where(Lead.email_verification_status == verification_status)
    
    if email_verified is not None:
        query = query.where(Lead.email_verified == email_verified)
    
    # Date filtering (uses created_at)
    if date_from:
        query = query.where(Lead.created_at >= date_from)
    if date_to:
        query = query.where(Lead.created_at <= date_to)
    
    # Data quality filtering
    if has_email is not None:
        if has_email:
            query = query.where(Lead.email.isnot(None))
        else:
            query = query.where(Lead.email.is_(None))
    
    if has_phone is not None:
        if has_phone:
            query = query.where(Lead.phone.isnot(None))
        else:
            query = query.where(Lead.phone.is_(None))
    
    # Count total (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0
    
    # Apply pagination
    query = query.order_by(Lead.created_at.desc()).offset(skip).limit(limit)
    
    # Execute
    result = await db.execute(query)
    leads = result.scalars().all()
    
    # Build response
    items = []
    for lead in leads:
        # Build name
        if lead.first_name and lead.last_name:
            full_name = f"{lead.first_name} {lead.last_name}"
        elif lead.first_name:
            full_name = lead.first_name
        else:
            full_name = lead.email.split('@')[0] if lead.email else "Unknown"
        
        # Get assignments for this lead
        assignments_result = await db.execute(
            select(LeadICPAssignment, ICP)
            .join(ICP, LeadICPAssignment.icp_id == ICP.id)
            .where(LeadICPAssignment.lead_id == lead.id)
        )
        assignment_rows = assignments_result.all()
        
        assignments = []
        for assignment, icp in assignment_rows:
            assignments.append({
                "id": str(assignment.id),
                "icp_id": str(assignment.icp_id),
                "icp_name": icp.name,
                "fit_score_percentage": float(assignment.fit_score_percentage) if assignment.fit_score_percentage else None,
                "status": assignment.status,
                "bucket": assignment.bucket
            })
        
        items.append({
            "id": str(lead.id),
            "email": lead.email,
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "full_name": full_name,
            "company_name": lead.company_name,
            "company_industry": lead.company_industry,
            "company_website": lead.company_website,
            "company_size": lead.company_size,
            "job_title": lead.job_title,
            "phone": lead.phone,
            "city": lead.city,
            "state": lead.state,
            "country": lead.country,
            "linkedin_url": lead.linkedin_url,
            "source": lead.source,  # ✅ Uses actual field
            "source_url": lead.source_url,
            "email_verified": lead.email_verified or False,
            "email_verification_status": lead.email_verification_status,  # ✅ Uses actual field
            "email_verification_confidence": float(lead.email_verification_confidence) if lead.email_verification_confidence else None,  # ✅ Uses actual field
            "verification_status": lead.email_verification_status,  # For frontend compatibility
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
            "icp_assignments": assignments
        })
    
    return {
        "leads": items,
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "skip": skip,
            "total_pages": math.ceil(total / limit) if limit > 0 else 0
        }
    }


# ============================================================================
# BULK PROCESS LEADS
# ============================================================================

@router.post("/process")
async def process_leads(
    request: ProcessLeadsRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger pipeline processing for leads
    """
    
    if not request.lead_ids:
        raise HTTPException(status_code=400, detail="No leads selected")
    
    # Verify all leads belong to tenant
    query = select(Lead).where(
        Lead.id.in_(request.lead_ids),
        Lead.tenant_id == current_user.tenant_id
    )
    result = await db.execute(query)
    leads = result.scalars().all()
    
    if len(leads) != len(request.lead_ids):
        raise HTTPException(
            status_code=400,
            detail="Some leads not found"
        )
    
    # TODO: Trigger your pipeline processing
    # background_tasks.add_task(process_leads_pipeline, request.lead_ids, current_user.tenant_id)
    
    return {
        "message": f"Processing {len(request.lead_ids)} leads",
        "lead_ids": [str(id) for id in request.lead_ids],
        "status": "queued"
    }


# ============================================================================
# BULK DELETE LEADS
# ============================================================================

@router.delete("/bulk")
async def bulk_delete_leads(
    request: BulkDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Bulk delete leads
    """
    
    if not request.lead_ids:
        raise HTTPException(status_code=400, detail="No leads selected")
    
    # Delete leads
    result = await db.execute(
        delete(Lead).where(
            Lead.id.in_(request.lead_ids),
            Lead.tenant_id == current_user.tenant_id
        )
    )
    
    deleted_count = result.rowcount
    await db.commit()
    
    return {
        "message": f"Deleted {deleted_count} leads",
        "deleted_count": deleted_count
    }


# ============================================================================
# BULK REVIEW LEADS
# ============================================================================

@router.post("/bulk-review")
async def bulk_review_leads(
    request: BulkReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Bulk approve or reject leads
    """
    
    if not request.lead_ids or not request.decision:
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    if request.decision not in ['approved', 'rejected']:
        raise HTTPException(status_code=400, detail="Invalid decision")
    
    # Update all assignments
    new_status = 'qualified' if request.decision == 'approved' else 'rejected'
    new_bucket = 'qualified' if request.decision == 'approved' else 'rejected'
    
    result = await db.execute(
        update(LeadICPAssignment)
        .where(
            LeadICPAssignment.lead_id.in_(request.lead_ids),
            LeadICPAssignment.tenant_id == current_user.tenant_id
        )
        .values(
            status=new_status,
            bucket=new_bucket,
            reviewed_at=datetime.utcnow(),
            reviewed_by=current_user.id,
            review_notes=request.notes
        )
    )
    
    updated_count = result.rowcount
    await db.commit()
    
    return {
        "message": f"{request.decision.title()} {updated_count} leads",
        "updated_count": updated_count,
        "decision": request.decision
    }


# ============================================================================
# EXPORT LEADS
# ============================================================================

@router.post("/export")
async def export_leads(
    request: ExportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Export leads to CSV
    """
    
    if not request.lead_ids:
        raise HTTPException(status_code=400, detail="No leads selected")
    
    # Fetch leads with assignments
    query = select(Lead, LeadICPAssignment).where(
        Lead.id.in_(request.lead_ids),
        Lead.tenant_id == current_user.tenant_id
    ).outerjoin(LeadICPAssignment, Lead.id == LeadICPAssignment.lead_id)
    
    result = await db.execute(query)
    leads_data = result.all()
    
    # Generate CSV
    if request.format == 'csv':
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            'Email', 'First Name', 'Last Name', 'Job Title',
            'Company', 'Industry', 'Website', 'Company Size', 'Phone',
            'City', 'State', 'Country',
            'Fit Score', 'Status', 'Bucket', 'Source', 'Email Status', 'Created At'
        ])
        
        # Rows
        for lead, assignment in leads_data:
            writer.writerow([
                lead.email,
                lead.first_name,
                lead.last_name,
                lead.job_title,
                lead.company_name,
                lead.company_industry,
                lead.company_website,
                lead.company_size,
                lead.phone,
                lead.city,
                lead.state,
                lead.country,
                float(assignment.fit_score_percentage) if assignment and assignment.fit_score_percentage else None,
                assignment.status if assignment else 'new',
                assignment.bucket if assignment else None,
                lead.source,
                lead.email_verification_status,
                lead.created_at.isoformat() if lead.created_at else None
            ])
        
        csv_content = output.getvalue()
        
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=leads_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )
    
    raise HTTPException(status_code=400, detail="Unsupported format")


# ============================================================================
# GET LEAD ACTIVITY TIMELINE
# ============================================================================

@router.get("/{lead_id}/activity")
async def get_lead_activity(
    lead_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get activity timeline for a lead
    TODO: Implement using LeadStageActivity table
    """
    
    # Verify lead belongs to tenant
    lead_query = select(Lead).where(
        Lead.id == lead_id,
        Lead.tenant_id == current_user.tenant_id
    )
    lead = await db.scalar(lead_query)
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # TODO: Use LeadStageActivity relationship
    return {
        "data": []
    }


# ============================================================================
# GET LEAD NOTES
# ============================================================================

@router.get("/{lead_id}/notes")
async def get_lead_notes(
    lead_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get notes for a lead
    TODO: Implement notes table
    """
    
    # Verify lead belongs to tenant
    lead_query = select(Lead).where(
        Lead.id == lead_id,
        Lead.tenant_id == current_user.tenant_id
    )
    lead = await db.scalar(lead_query)
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return {
        "data": []
    }


# ============================================================================
# ADD LEAD NOTE
# ============================================================================

@router.post("/{lead_id}/notes")
async def add_lead_note(
    lead_id: UUID,
    request: AddNoteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a note to a lead
    TODO: Implement notes table
    """
    
    if not request.content or not request.content.strip():
        raise HTTPException(status_code=400, detail="Note content required")
    
    # Verify lead belongs to tenant
    lead_query = select(Lead).where(
        Lead.id == lead_id,
        Lead.tenant_id == current_user.tenant_id
    )
    lead = await db.scalar(lead_query)
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # TODO: Implement notes storage
    return {
        "message": "Note added successfully (TODO: implement database storage)",
        "content": request.content
    }


# ============================================================================
# GET SINGLE LEAD
# ============================================================================

@router.get("/{lead_id}")
async def get_lead(
    lead_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get single lead"""
    
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == current_user.tenant_id)
    )
    lead = result.scalar_one_or_none()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Get assignments
    assignments_result = await db.execute(
        select(LeadICPAssignment, ICP)
        .join(ICP, LeadICPAssignment.icp_id == ICP.id)
        .where(LeadICPAssignment.lead_id == lead_id)
    )
    assignment_rows = assignments_result.all()
    
    assignments = []
    for assignment, icp in assignment_rows:
        assignments.append({
            "id": str(assignment.id),
            "icp_id": str(assignment.icp_id),
            "icp_name": icp.name,
            "fit_score_percentage": float(assignment.fit_score_percentage) if assignment.fit_score_percentage else None,
            "status": assignment.status,
            "bucket": assignment.bucket,
            "scoring_details": assignment.scoring_details,
            "qualified_at": assignment.qualified_at.isoformat() if assignment.qualified_at else None,
            "reviewed_at": assignment.reviewed_at.isoformat() if assignment.reviewed_at else None,
            "review_notes": assignment.review_notes,
            "created_at": assignment.created_at.isoformat() if assignment.created_at else None
        })
    
    return {
        "id": str(lead.id),
        "tenant_id": str(lead.tenant_id),
        "email": lead.email,
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "phone": lead.phone,
        "job_title": lead.job_title,
        "seniority_level": lead.seniority_level,
        "linkedin_url": lead.linkedin_url,
        "company_name": lead.company_name,
        "company_website": lead.company_website,
        "company_domain": lead.company_domain,
        "company_industry": lead.company_industry,
        "company_size": lead.company_size,
        "company_employee_count": lead.company_employee_count,
        "city": lead.city,
        "state": lead.state,
        "country": lead.country,
        "enrichment_data": lead.enrichment_data,
        "email_verified": lead.email_verified or False,
        "email_verification_status": lead.email_verification_status,
        "email_verification_confidence": float(lead.email_verification_confidence) if lead.email_verification_confidence else None,
        "verification_status": lead.email_verification_status,  # For frontend compatibility
        "source": lead.source,
        "source_url": lead.source_url,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "icp_assignments": assignments,
        "total_icps": len(assignments),
        "qualified_icps": sum(1 for a in assignments if a["status"] == "qualified"),
        "pending_review_icps": sum(1 for a in assignments if a["status"] == "pending_review")
    }


# ============================================================================
# UPDATE LEAD
# ============================================================================

@router.put("/{lead_id}")
async def update_lead(
    lead_id: UUID,
    update: LeadUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update lead"""
    
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == current_user.tenant_id)
    )
    lead = result.scalar_one_or_none()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Update fields
    if update.first_name is not None:
        lead.first_name = update.first_name
    if update.last_name is not None:
        lead.last_name = update.last_name
    if update.phone is not None:
        lead.phone = update.phone
    if update.job_title is not None:
        lead.job_title = update.job_title
    if update.company_name is not None:
        lead.company_name = update.company_name
    
    lead.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return {"message": "Lead updated", "lead_id": str(lead.id)}


# ============================================================================
# STATS
# ============================================================================

@router.get("/stats/overview")
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get overview stats for tenant's leads"""
    
    # Total leads for this tenant
    total_result = await db.execute(
        select(func.count(Lead.id)).where(Lead.tenant_id == current_user.tenant_id)
    )
    total_leads = total_result.scalar() or 0
    
    # Get assignments for tenant's leads
    assignments_result = await db.execute(
        select(func.count(LeadICPAssignment.id))
        .join(Lead, LeadICPAssignment.lead_id == Lead.id)
        .where(Lead.tenant_id == current_user.tenant_id)
    )
    total_assignments = assignments_result.scalar() or 0
    
    # Get statuses for tenant's leads
    status_result = await db.execute(
        select(LeadICPAssignment.status)
        .join(Lead, LeadICPAssignment.lead_id == Lead.id)
        .where(Lead.tenant_id == current_user.tenant_id)
    )
    all_statuses = [row[0] for row in status_result.all()]
    
    by_status = {}
    for status in set(all_statuses):
        by_status[status] = all_statuses.count(status)
    
    return {
        "total_leads": total_leads,
        "total_assignments": total_assignments,
        "by_status": by_status,
        "average_icps_per_lead": round(total_assignments / total_leads, 2) if total_leads > 0 else 0
    }