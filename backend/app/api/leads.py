"""Lead management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional
from datetime import datetime
import logging
from uuid import uuid4, UUID

from app.database import get_db
from app.auth import get_current_tenant, get_current_user
from app.models import Lead, Tenant, User, AuditLog
from app.schemas import (
    LeadBatchCreate, BatchResponse, LeadResponse,
    LeadListResponse, ReviewDecision
)
from app.services.normalization import normalization_service
from app.services.deduplication import deduplication_service
from app.services.scoring import scoring_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/batch", response_model=BatchResponse)
async def create_lead_batch(
    batch: LeadBatchCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Ingest a batch of leads with normalization and deduplication.
    
    - Normalizes all lead data
    - Checks for duplicates
    - Calculates initial fit scores
    - Returns summary of accepted/rejected leads
    
    **Authentication**: API Key required
    """
    
    # Initialize deduplication service
    await deduplication_service.initialize()
    
    batch_id = str(uuid4())
    accepted = 0
    rejected = 0
    errors = []
    
    logger.info(f"Batch ingestion started for tenant {tenant.id}: {len(batch.leads)} leads")
    
    for idx, lead_data in enumerate(batch.leads):
        try:
            # Step 1: Normalize lead data
            lead_dict = lead_data.model_dump()
            normalized = normalization_service.normalize_lead(lead_dict)
            
            # Step 2: Check for duplicates
            duplicate_id = await deduplication_service.check_duplicate(
                tenant_id=tenant.id,
                email=normalized['email'],
                db=db
            )
            
            if duplicate_id:
                logger.debug(f"Duplicate lead skipped: {normalized['email']}")
                rejected += 1
                errors.append({
                    "index": idx,
                    "email": normalized['email'],
                    "reason": "Duplicate email for this tenant",
                    "existing_lead_id": str(duplicate_id)
                })
                continue
            
            # Step 3: Calculate initial fit score
            initial_score = scoring_service.calculate_fit_score(
                job_title=normalized.get('job_title'),
                email_verified=False,
                lead_data=normalized,
                source_quality=0.5  # Default source quality
            )
            
            # Step 4: Create new lead
            lead = Lead(
                tenant_id=tenant.id,
                email=normalized['email'],
                first_name=normalized.get('first_name'),
                last_name=normalized.get('last_name'),
                phone=normalized.get('phone'),
                job_title=normalized.get('job_title'),
                linkedin_url=normalized.get('linkedin_url'),
                company_name=normalized.get('company_name'),
                company_website=normalized.get('company_website'),
                company_domain=normalized.get('company_domain'),
                source_name=batch.source_name,
                status="normalized",  # Updated status
                fit_score=initial_score,
                acquisition_timestamp=lead_data.acquisition_timestamp or datetime.utcnow()
            )
            
            db.add(lead)
            await db.flush()  # Get the lead ID
            
            # Cache the lead for deduplication
            await deduplication_service.mark_lead_in_cache(
                tenant_id=tenant.id,
                email=normalized['email'],
                lead_id=lead.id
            )
            
            accepted += 1
            
            # Create audit log entry
            audit = AuditLog(
                tenant_id=tenant.id,
                action="lead.created",
                entity_type="lead",
                entity_id=lead.id,
                details={
                    "source": batch.source_name,
                    "email": normalized['email'],
                    "batch_id": batch_id,
                    "initial_fit_score": initial_score
                }
            )
            db.add(audit)
            
        except Exception as e:
            logger.error(f"Lead creation failed at index {idx}: {e}", exc_info=True)
            rejected += 1
            errors.append({
                "index": idx,
                "email": lead_data.email,
                "reason": f"Processing error: {str(e)}"
            })
    
    # Commit all accepted leads
    try:
        await db.commit()
        logger.info(f"Batch {batch_id} completed: {accepted} accepted, {rejected} rejected")
    except Exception as e:
        await db.rollback()
        logger.error(f"Batch commit failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save leads"
        )
    finally:
        await deduplication_service.close()
    
    return BatchResponse(
        batch_id=batch_id,
        accepted=accepted,
        rejected=rejected,
        errors=errors
    )


@router.get("", response_model=LeadListResponse)
async def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    source_name: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List leads with pagination and filtering."""
    
    query = select(Lead).where(Lead.tenant_id == user.tenant_id)
    
    if status:
        query = query.where(Lead.status == status)
    
    if source_name:
        query = query.where(Lead.source_name == source_name)
    
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    offset = (page - 1) * page_size
    query = query.order_by(Lead.created_at.desc()).offset(offset).limit(page_size)
    
    result = await db.execute(query)
    leads = result.scalars().all()
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    
    return LeadListResponse(
        leads=[LeadResponse.model_validate(lead) for lead in leads],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed information for a specific lead."""
    
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
    
    return LeadResponse.model_validate(lead)


@router.put("/{lead_id}/review", response_model=LeadResponse)
async def review_lead(
    lead_id: UUID,
    decision: ReviewDecision,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit a review decision for a lead."""
    
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
    
    lead.review_decision = decision.decision
    lead.review_notes = decision.notes
    lead.reviewed_at = datetime.utcnow()
    lead.reviewed_by = user.email
    lead.status = "approved" if decision.decision == "approved" else "rejected"
    
    if decision.edits:
        for field, value in decision.edits.items():
            if hasattr(lead, field) and field not in ['id', 'tenant_id', 'created_at']:
                setattr(lead, field, value)
    
    audit = AuditLog(
        tenant_id=user.tenant_id,
        user_email=user.email,
        action="lead.reviewed",
        entity_type="lead",
        entity_id=lead.id,
        details={
            "decision": decision.decision,
            "notes": decision.notes,
            "edits": decision.edits
        }
    )
    db.add(audit)
    
    try:
        await db.commit()
        await db.refresh(lead)
        
        logger.info(f"Lead {lead_id} reviewed as {decision.decision} by {user.email}")
        
        return LeadResponse.model_validate(lead)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Review commit failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save review"
        )
