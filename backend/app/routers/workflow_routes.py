# backend/app/routers/workflow_routes.py
"""
API endpoints for workflow management (Phase 1)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import joinedload
from typing import List
from uuid import UUID

from app.database import get_db
from app.models import WorkflowStatus, WorkflowTransition, User
from app.schemas.workflow import (
    WorkflowStatusCreate,
    WorkflowStatusUpdate,
    WorkflowStatusResponse,
    WorkflowTransitionCreate,
    WorkflowTransitionResponse,
    WorkflowSummary
)
from app.auth import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


# ========================================
# WORKFLOW STATUS ENDPOINTS
# ========================================

@router.get("/statuses", response_model=List[WorkflowStatusResponse])
async def get_workflow_statuses(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all workflow statuses for current tenant.
    
    Returns statuses ordered by display order.
    """
    try:
        query = select(WorkflowStatus).where(
            WorkflowStatus.tenant_id == current_user.tenant_id
        )
        
        if not include_inactive:
            query = query.where(WorkflowStatus.is_active == True)
        
        query = query.order_by(WorkflowStatus.order)
        
        result = await db.execute(query)
        statuses = result.scalars().all()
        
        return statuses
        
    except Exception as e:
        logger.error(f"Error fetching workflow statuses: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch workflow statuses: {str(e)}"
        )


@router.get("/statuses/{status_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    status_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific workflow status by ID."""
    try:
        result = await db.execute(
            select(WorkflowStatus).where(
                and_(
                    WorkflowStatus.id == status_id,
                    WorkflowStatus.tenant_id == current_user.tenant_id
                )
            )
        )
        status_obj = result.scalar_one_or_none()
        
        if not status_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow status not found"
            )
        
        return status_obj
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workflow status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/statuses", response_model=WorkflowStatusResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow_status(
    status_data: WorkflowStatusCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new workflow status for current tenant.
    
    Only one status can be marked as initial per tenant.
    """
    try:
        # Check if status with this name already exists for tenant
        existing = await db.execute(
            select(WorkflowStatus).where(
                and_(
                    WorkflowStatus.tenant_id == current_user.tenant_id,
                    WorkflowStatus.name == status_data.name
                )
            )
        )
        
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Status with name '{status_data.name}' already exists"
            )
        
        # If marked as initial, unmark other initial statuses
        if status_data.is_initial:
            await db.execute(
                WorkflowStatus.__table__.update().where(
                    and_(
                        WorkflowStatus.tenant_id == current_user.tenant_id,
                        WorkflowStatus.is_initial == True
                    )
                ).values(is_initial=False)
            )
        
        # Create new status
        new_status = WorkflowStatus(
            **status_data.model_dump(),
            tenant_id=current_user.tenant_id,
            created_by=current_user.id
        )
        
        db.add(new_status)
        await db.commit()
        await db.refresh(new_status)
        
        logger.info(f"Created workflow status: {new_status.name} for tenant {current_user.tenant_id}")
        
        return new_status
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating workflow status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create workflow status: {str(e)}"
        )


@router.put("/statuses/{status_id}", response_model=WorkflowStatusResponse)
async def update_workflow_status(
    status_id: UUID,
    status_data: WorkflowStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an existing workflow status."""
    try:
        # Get status
        result = await db.execute(
            select(WorkflowStatus).where(
                and_(
                    WorkflowStatus.id == status_id,
                    WorkflowStatus.tenant_id == current_user.tenant_id
                )
            )
        )
        status_obj = result.scalar_one_or_none()
        
        if not status_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow status not found"
            )
        
        # Update fields
        update_data = status_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(status_obj, field, value)
        
        await db.commit()
        await db.refresh(status_obj)
        
        logger.info(f"Updated workflow status: {status_obj.name}")
        
        return status_obj
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating workflow status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/statuses/{status_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_status(
    status_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete (soft delete) a workflow status.
    
    Status is marked as inactive rather than deleted.
    """
    try:
        result = await db.execute(
            select(WorkflowStatus).where(
                and_(
                    WorkflowStatus.id == status_id,
                    WorkflowStatus.tenant_id == current_user.tenant_id
                )
            )
        )
        status_obj = result.scalar_one_or_none()
        
        if not status_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow status not found"
            )
        
        # Soft delete
        status_obj.is_active = False
        await db.commit()
        
        logger.info(f"Deleted workflow status: {status_obj.name}")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting workflow status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ========================================
# WORKFLOW TRANSITION ENDPOINTS
# ========================================

@router.get("/transitions", response_model=List[WorkflowTransitionResponse])
async def get_workflow_transitions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all workflow transitions for current tenant."""
    try:
        result = await db.execute(
            select(WorkflowTransition).where(
                WorkflowTransition.tenant_id == current_user.tenant_id
            )
        )
        transitions = result.scalars().all()
        
        return transitions
        
    except Exception as e:
        logger.error(f"Error fetching transitions: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/transitions", response_model=WorkflowTransitionResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow_transition(
    transition_data: WorkflowTransitionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new workflow transition (allowed status change)."""
    try:
        # Check if transition already exists
        existing = await db.execute(
            select(WorkflowTransition).where(
                and_(
                    WorkflowTransition.tenant_id == current_user.tenant_id,
                    WorkflowTransition.from_status_id == transition_data.from_status_id,
                    WorkflowTransition.to_status_id == transition_data.to_status_id
                )
            )
        )
        
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This transition already exists"
            )
        
        # Create transition
        new_transition = WorkflowTransition(
            **transition_data.model_dump(),
            tenant_id=current_user.tenant_id
        )
        
        db.add(new_transition)
        await db.commit()
        await db.refresh(new_transition)
        
        logger.info(f"Created workflow transition: {transition_data.from_status_id} -> {transition_data.to_status_id}")
        
        return new_transition
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating transition: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/transitions/{transition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_transition(
    transition_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a workflow transition."""
    try:
        result = await db.execute(
            select(WorkflowTransition).where(
                and_(
                    WorkflowTransition.id == transition_id,
                    WorkflowTransition.tenant_id == current_user.tenant_id
                )
            )
        )
        transition = result.scalar_one_or_none()
        
        if not transition:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow transition not found"
            )
        
        await db.delete(transition)
        await db.commit()
        
        logger.info(f"Deleted workflow transition: {transition_id}")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting transition: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ========================================
# WORKFLOW SUMMARY
# ========================================

@router.get("/summary", response_model=WorkflowSummary)
async def get_workflow_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get workflow summary for current tenant."""
    try:
        # Get all statuses
        result = await db.execute(
            select(WorkflowStatus).where(
                WorkflowStatus.tenant_id == current_user.tenant_id
            ).order_by(WorkflowStatus.order)
        )
        statuses = result.scalars().all()
        
        # Count active statuses
        active_count = sum(1 for s in statuses if s.is_active)
        
        return WorkflowSummary(
            tenant_id=current_user.tenant_id,
            total_statuses=len(statuses),
            active_statuses=active_count,
            statuses=statuses
        )
        
    except Exception as e:
        logger.error(f"Error fetching workflow summary: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )