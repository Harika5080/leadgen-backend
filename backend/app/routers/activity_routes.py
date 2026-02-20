# backend/app/routers/activity_routes.py
"""
Activity & Notes API - Phase 1
Complete implementation for activity tracking and notes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta

from app.database import get_db
from app.models import LeadActivity, LeadNote, Lead, User
from app.schemas.workflow import (
    LeadActivityCreate,
    LeadActivityResponse,
    LeadActivityListResponse,
    LeadNoteCreate,
    LeadNoteUpdate,
    LeadNoteResponse,
    LeadNoteList,
    LeadJourneyResponse
)
from app.auth import get_current_user

router = APIRouter(prefix="/api/v1/leads", tags=["activities"])


# ==================== ACTIVITY ENDPOINTS ====================

@router.get("/{lead_id}/activities", response_model=LeadActivityListResponse)
async def get_lead_activities(
    lead_id: UUID,
    activity_type: Optional[str] = None,
    user_id: Optional[UUID] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get activity timeline for a lead.
    
    Supports filtering by:
    - activity_type: Filter by specific activity type
    - user_id: Filter by user who performed the activity
    """
    # Verify lead exists and belongs to tenant
    lead_result = await db.execute(
        select(Lead).where(
            and_(
                Lead.id == lead_id,
                Lead.tenant_id == current_user.tenant_id
            )
        )
    )
    lead = lead_result.scalar_one_or_none()
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )
    
    # Build query
    query = select(LeadActivity, User.email, User.full_name).outerjoin(
        User, LeadActivity.user_id == User.id
    ).where(
        and_(
            LeadActivity.lead_id == lead_id,
            LeadActivity.tenant_id == current_user.tenant_id
        )
    )
    
    # Apply filters
    if activity_type:
        query = query.where(LeadActivity.activity_type == activity_type)
    
    if user_id:
        query = query.where(LeadActivity.user_id == user_id)
    
    # Get total count
    count_query = select(func.count(LeadActivity.id)).where(
        and_(
            LeadActivity.lead_id == lead_id,
            LeadActivity.tenant_id == current_user.tenant_id
        )
    )
    if activity_type:
        count_query = count_query.where(LeadActivity.activity_type == activity_type)
    if user_id:
        count_query = count_query.where(LeadActivity.user_id == user_id)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Order and paginate
    query = query.order_by(LeadActivity.created_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(query)
    rows = result.all()
    
    # Format response
    activities = []
    for activity, user_email, user_name in rows:
        activity_dict = {
            "id": activity.id,
            "lead_id": activity.lead_id,
            "user_id": activity.user_id,
            "tenant_id": activity.tenant_id,
            "activity_type": activity.activity_type,
            "title": activity.title,
            "description": activity.description,
            "old_status": activity.old_status,
            "new_status": activity.new_status,
            "metadata": activity.metadata,
            "source": activity.source,
            "created_at": activity.created_at,
            "user_email": user_email,
            "user_name": user_name
        }
        activities.append(LeadActivityResponse(**activity_dict))
    
    return LeadActivityListResponse(activities=activities, total=total)


@router.post("/{lead_id}/activities", response_model=LeadActivityResponse, status_code=status.HTTP_201_CREATED)
async def create_lead_activity(
    lead_id: UUID,
    activity_data: LeadActivityCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Log a custom activity on a lead.
    
    Use for manual logging of calls, emails, meetings, etc.
    """
    # Verify lead exists and belongs to tenant
    lead_result = await db.execute(
        select(Lead).where(
            and_(
                Lead.id == lead_id,
                Lead.tenant_id == current_user.tenant_id
            )
        )
    )
    lead = lead_result.scalar_one_or_none()
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )
    
    # Create activity
    new_activity = LeadActivity(
        lead_id=lead_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        activity_type=activity_data.activity_type,
        title=activity_data.title,
        description=activity_data.description,
        old_status=activity_data.old_status,
        new_status=activity_data.new_status,
        metadata=activity_data.metadata,
        source='manual'
    )
    
    db.add(new_activity)
    
    # Update lead touchpoints count
    lead.touchpoints_count = (lead.touchpoints_count or 0) + 1
    
    await db.commit()
    await db.refresh(new_activity)
    
    # Return with user info
    return LeadActivityResponse(
        **new_activity.__dict__,
        user_email=current_user.email,
        user_name=current_user.full_name
    )


@router.get("/{lead_id}/journey", response_model=LeadJourneyResponse)
async def get_lead_journey(
    lead_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get complete lead journey summary.
    
    Provides high-level overview of lead's path through pipeline.
    """
    # Get lead with related data
    query = select(
        Lead,
        User.email.label('assigned_to_email'),
        func.count(LeadActivity.id).label('total_activities')
    ).outerjoin(
        User, Lead.assigned_to == User.id
    ).outerjoin(
        LeadActivity, and_(
            LeadActivity.lead_id == Lead.id,
            LeadActivity.tenant_id == Lead.tenant_id
        )
    ).where(
        and_(
            Lead.id == lead_id,
            Lead.tenant_id == current_user.tenant_id
        )
    ).group_by(Lead.id, User.email)
    
    result = await db.execute(query)
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )
    
    lead, assigned_email, total_activities = row
    
    # Get status changes count
    status_changes = await db.execute(
        select(func.count(LeadActivity.id)).where(
            and_(
                LeadActivity.lead_id == lead_id,
                LeadActivity.activity_type == 'status_change'
            )
        )
    )
    status_changes_count = status_changes.scalar()
    
    # Get converted by email if converted
    converted_by_email = None
    if lead.converted_by:
        converted_user = await db.execute(
            select(User.email).where(User.id == lead.converted_by)
        )
        converted_by_email = converted_user.scalar()
    
    # Calculate time to conversion
    time_to_conversion_days = None
    if lead.converted_at and lead.created_at:
        delta = lead.converted_at - lead.created_at
        time_to_conversion_days = round(delta.total_seconds() / 86400, 1)
    
    return LeadJourneyResponse(
        lead_id=lead.id,
        created_at=lead.created_at,
        converted_at=lead.converted_at,
        time_to_conversion_days=time_to_conversion_days,
        status_changes=status_changes_count,
        total_activities=total_activities,
        touchpoints=lead.touchpoints_count or 0,
        assigned_to_email=assigned_email,
        converted_by_email=converted_by_email
    )


# ==================== NOTES ENDPOINTS ====================

@router.get("/{lead_id}/notes", response_model=LeadNoteList)
async def get_lead_notes(
    lead_id: UUID,
    include_unpinned: bool = True,
    limit: int = Query(100, le=500),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get notes for a lead.
    
    Notes are ordered by: pinned first, then by creation date (newest first)
    """
    # Verify lead exists and belongs to tenant
    lead_result = await db.execute(
        select(Lead).where(
            and_(
                Lead.id == lead_id,
                Lead.tenant_id == current_user.tenant_id
            )
        )
    )
    lead = lead_result.scalar_one_or_none()
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )
    
    # Build query
    query = select(LeadNote, User.email, User.full_name).join(
        User, LeadNote.user_id == User.id
    ).where(
        and_(
            LeadNote.lead_id == lead_id,
            LeadNote.tenant_id == current_user.tenant_id
        )
    )
    
    # Get total count
    count_query = select(func.count(LeadNote.id)).where(
        and_(
            LeadNote.lead_id == lead_id,
            LeadNote.tenant_id == current_user.tenant_id
        )
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Order: pinned first, then by created_at desc
    query = query.order_by(
        LeadNote.is_pinned.desc(),
        LeadNote.created_at.desc()
    ).limit(limit).offset(offset)
    
    result = await db.execute(query)
    rows = result.all()
    
    # Format response
    notes = []
    for note, user_email, user_name in rows:
        note_dict = {
            "id": note.id,
            "lead_id": note.lead_id,
            "user_id": note.user_id,
            "tenant_id": note.tenant_id,
            "content": note.content,
            "is_pinned": note.is_pinned,
            "created_at": note.created_at,
            "updated_at": note.updated_at,
            "user_email": user_email,
            "user_name": user_name
        }
        notes.append(LeadNoteResponse(**note_dict))
    
    return LeadNoteList(notes=notes, total=total)


@router.post("/{lead_id}/notes", response_model=LeadNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_lead_note(
    lead_id: UUID,
    note_data: LeadNoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a note to a lead.
    
    Also creates a 'note' activity in the activity timeline.
    """
    # Verify lead exists and belongs to tenant
    lead_result = await db.execute(
        select(Lead).where(
            and_(
                Lead.id == lead_id,
                Lead.tenant_id == current_user.tenant_id
            )
        )
    )
    lead = lead_result.scalar_one_or_none()
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )
    
    # Create note
    new_note = LeadNote(
        lead_id=lead_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        content=note_data.content,
        is_pinned=note_data.is_pinned
    )
    
    db.add(new_note)
    
    # Also create activity
    note_activity = LeadActivity(
        lead_id=lead_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        activity_type='note',
        title='Note added',
        description=note_data.content[:200],  # First 200 chars
        source='manual'
    )
    
    db.add(note_activity)
    
    await db.commit()
    await db.refresh(new_note)
    
    return LeadNoteResponse(
        **new_note.__dict__,
        user_email=current_user.email,
        user_name=current_user.full_name
    )


@router.put("/notes/{note_id}", response_model=LeadNoteResponse)
async def update_lead_note(
    note_id: UUID,
    note_data: LeadNoteUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a lead note (content or pin status)"""
    # Get note
    result = await db.execute(
        select(LeadNote, User.email, User.full_name).join(
            User, LeadNote.user_id == User.id
        ).where(
            and_(
                LeadNote.id == note_id,
                LeadNote.tenant_id == current_user.tenant_id
            )
        )
    )
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found"
        )
    
    note, user_email, user_name = row
    
    # Only allow owner or admin to edit
    if note.user_id != current_user.id and current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own notes"
        )
    
    # Update fields
    update_data = note_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)
    
    note.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(note)
    
    return LeadNoteResponse(
        **note.__dict__,
        user_email=user_email,
        user_name=user_name
    )


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead_note(
    note_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a lead note"""
    # Get note
    result = await db.execute(
        select(LeadNote).where(
            and_(
                LeadNote.id == note_id,
                LeadNote.tenant_id == current_user.tenant_id
            )
        )
    )
    note = result.scalar_one_or_none()
    
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found"
        )
    
    # Only allow owner or admin to delete
    if note.user_id != current_user.id and current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own notes"
        )
    
    await db.delete(note)
    await db.commit()
    
    return None


@router.post("/notes/{note_id}/pin")
async def pin_lead_note(
    note_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Pin a note (quick action)"""
    result = await db.execute(
        select(LeadNote).where(
            and_(
                LeadNote.id == note_id,
                LeadNote.tenant_id == current_user.tenant_id
            )
        )
    )
    note = result.scalar_one_or_none()
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    note.is_pinned = True
    await db.commit()
    
    return {"message": "Note pinned", "note_id": str(note_id)}


@router.delete("/notes/{note_id}/pin")
async def unpin_lead_note(
    note_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Unpin a note (quick action)"""
    result = await db.execute(
        select(LeadNote).where(
            and_(
                LeadNote.id == note_id,
                LeadNote.tenant_id == current_user.tenant_id
            )
        )
    )
    note = result.scalar_one_or_none()
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    note.is_pinned = False
    await db.commit()
    
    return {"message": "Note unpinned", "note_id": str(note_id)}