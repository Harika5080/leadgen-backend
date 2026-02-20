"""Audit log API routes (admin only)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from app.database import get_db
from app.models import AuditLog, User
from app.rbac import require_admin

router = APIRouter()


class AuditLogResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: Optional[str]
    user_email: Optional[str]
    action: str
    resource_type: str
    resource_id: Optional[str]
    old_values: Optional[dict]
    new_values: Optional[dict]
    ip_address: Optional[str]
    user_agent: Optional[str]
    request_method: Optional[str]
    request_path: Optional[str]
    meta: Optional[dict]  # Changed from metadata to meta
    status: str
    error_message: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    logs: List[AuditLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    user_email: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get audit logs (admin only).
    
    Supports filtering by:
    - action: specific action type
    - resource_type: type of resource
    - user_email: user who performed action
    - start_date/end_date: date range
    - search: search in action, resource_type, user_email
    """
    
    # Build filters
    filters = [AuditLog.tenant_id == current_user.tenant_id]
    
    if action:
        filters.append(AuditLog.action == action)
    
    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)
    
    if user_email:
        filters.append(AuditLog.user_email.ilike(f"%{user_email}%"))
    
    if start_date:
        filters.append(AuditLog.created_at >= datetime.fromisoformat(start_date))
    
    if end_date:
        filters.append(AuditLog.created_at <= datetime.fromisoformat(end_date))
    
    if search:
        search_filter = or_(
            AuditLog.action.ilike(f"%{search}%"),
            AuditLog.resource_type.ilike(f"%{search}%"),
            AuditLog.user_email.ilike(f"%{search}%"),
            AuditLog.resource_id.ilike(f"%{search}%"),
        )
        filters.append(search_filter)
    
    # Count total
    count_query = select(func.count(AuditLog.id)).where(and_(*filters))
    result = await db.execute(count_query)
    total = result.scalar() or 0
    
    # Get paginated results
    offset = (page - 1) * page_size
    query = (
        select(AuditLog)
        .where(and_(*filters))
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    
    result = await db.execute(query)
    logs = result.scalars().all()
    
    total_pages = (total + page_size - 1) // page_size
    
    return AuditLogListResponse(
        logs=[
            AuditLogResponse(
                id=str(log.id),
                tenant_id=str(log.tenant_id),
                user_id=str(log.user_id) if log.user_id else None,
                user_email=log.user_email,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                old_values=log.old_values,
                new_values=log.new_values,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                request_method=log.request_method,
                request_path=log.request_path,
                meta=log.meta,  # Changed from metadata to meta
                status=log.status,
                error_message=log.error_message,
                created_at=log.created_at.isoformat(),
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/audit-logs/actions")
async def get_audit_actions(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get list of unique action types for filtering."""
    
    query = (
        select(AuditLog.action)
        .where(AuditLog.tenant_id == current_user.tenant_id)
        .distinct()
        .order_by(AuditLog.action)
    )
    
    result = await db.execute(query)
    actions = [row[0] for row in result.all()]
    
    return {"actions": actions}


@router.get("/audit-logs/resource-types")
async def get_resource_types(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get list of unique resource types for filtering."""
    
    query = (
        select(AuditLog.resource_type)
        .where(AuditLog.tenant_id == current_user.tenant_id)
        .distinct()
        .order_by(AuditLog.resource_type)
    )
    
    result = await db.execute(query)
    resource_types = [row[0] for row in result.all()]
    
    return {"resource_types": resource_types}


@router.get("/audit-logs/users")
async def get_audit_users(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get list of unique users who have performed actions."""
    
    query = (
        select(AuditLog.user_email)
        .where(
            and_(
                AuditLog.tenant_id == current_user.tenant_id,
                AuditLog.user_email.isnot(None)
            )
        )
        .distinct()
        .order_by(AuditLog.user_email)
    )
    
    result = await db.execute(query)
    users = [row[0] for row in result.all()]
    
    return {"users": users}


@router.get("/audit-logs/stats")
async def get_audit_stats(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get audit log statistics."""
    
    start_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    start_date = start_date - timedelta(days=days)
    
    # Total actions
    query = select(func.count(AuditLog.id)).where(
        and_(
            AuditLog.tenant_id == current_user.tenant_id,
            AuditLog.created_at >= start_date
        )
    )
    result = await db.execute(query)
    total_actions = result.scalar() or 0
    
    # Actions by type
    query = (
        select(AuditLog.action, func.count(AuditLog.id))
        .where(
            and_(
                AuditLog.tenant_id == current_user.tenant_id,
                AuditLog.created_at >= start_date
            )
        )
        .group_by(AuditLog.action)
        .order_by(func.count(AuditLog.id).desc())
        .limit(10)
    )
    result = await db.execute(query)
    actions_by_type = [{"action": row[0], "count": row[1]} for row in result.all()]
    
    # Actions by user
    query = (
        select(AuditLog.user_email, func.count(AuditLog.id))
        .where(
            and_(
                AuditLog.tenant_id == current_user.tenant_id,
                AuditLog.created_at >= start_date,
                AuditLog.user_email.isnot(None)
            )
        )
        .group_by(AuditLog.user_email)
        .order_by(func.count(AuditLog.id).desc())
        .limit(10)
    )
    result = await db.execute(query)
    actions_by_user = [{"user": row[0], "count": row[1]} for row in result.all()]
    
    return {
        "total_actions": total_actions,
        "actions_by_type": actions_by_type,
        "actions_by_user": actions_by_user,
        "period_days": days,
    }