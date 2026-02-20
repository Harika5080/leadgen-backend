"""Audit logging service for tracking all system actions."""

import logging
from functools import wraps
from typing import Optional, Dict, Any, Callable
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.models import AuditLog, User

logger = logging.getLogger(__name__)


class AuditService:
    """Service for creating audit log entries."""
    
    @staticmethod
    async def log_action(
        db: AsyncSession,
        tenant_id: str,
        action: str,
        resource_type: str,
        user: Optional[User] = None,
        resource_id: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_method: Optional[str] = None,
        request_path: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,  # Changed from metadata to meta
        status: str = 'success',
        error_message: Optional[str] = None,
    ):
        """Create an audit log entry."""
        try:
            audit_log = AuditLog(
                tenant_id=tenant_id,
                user_id=user.id if user else None,
                user_email=user.email if user else None,
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                old_values=old_values,
                new_values=new_values,
                ip_address=ip_address,
                user_agent=user_agent,
                request_method=request_method,
                request_path=request_path,
                meta=meta,  # Changed from metadata to meta
                status=status,
                error_message=error_message,
            )
            
            db.add(audit_log)
            await db.commit()
            
            logger.info(
                f"Audit log created: {action} on {resource_type} "
                f"by {user.email if user else 'system'} "
                f"(tenant: {tenant_id})"
            )
            
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
            await db.rollback()


def audit_action(
    action: str,
    resource_type: str,
    extract_resource_id: Optional[Callable] = None,
    extract_old_values: Optional[Callable] = None,
    extract_new_values: Optional[Callable] = None,
):
    """
    Decorator to automatically audit an endpoint action.
    
    Usage:
        @audit_action(
            action='create_lead',
            resource_type='lead',
            extract_resource_id=lambda result: str(result.id),
            extract_new_values=lambda result: {'email': result.email, 'status': result.status}
        )
        async def create_lead(...):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            request: Optional[Request] = kwargs.get('request')
            db: Optional[AsyncSession] = kwargs.get('db')
            current_user: Optional[User] = kwargs.get('current_user')
            
            if db and current_user:
                try:
                    resource_id = extract_resource_id(result) if extract_resource_id else None
                    old_values = extract_old_values(result, args, kwargs) if extract_old_values else None
                    new_values = extract_new_values(result) if extract_new_values else None
                    
                    ip_address = None
                    user_agent = None
                    request_method = None
                    request_path = None
                    
                    if request:
                        ip_address = request.client.host if request.client else None
                        user_agent = request.headers.get('user-agent')
                        request_method = request.method
                        request_path = str(request.url.path)
                    
                    await AuditService.log_action(
                        db=db,
                        tenant_id=current_user.tenant_id,
                        action=action,
                        resource_type=resource_type,
                        user=current_user,
                        resource_id=resource_id,
                        old_values=old_values,
                        new_values=new_values,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        request_method=request_method,
                        request_path=request_path,
                    )
                except Exception as e:
                    logger.error(f"Audit decorator failed: {e}")
            
            return result
        
        return wrapper
    return decorator


async def log_manual(
    db: AsyncSession,
    user: User,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    old_values: Optional[Dict] = None,
    new_values: Optional[Dict] = None,
    meta: Optional[Dict] = None,  # Changed from metadata to meta
    request: Optional[Request] = None,
):
    """Manual audit logging helper."""
    ip_address = None
    user_agent = None
    request_method = None
    request_path = None
    
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get('user-agent')
        request_method = request.method
        request_path = str(request.url.path)
    
    await AuditService.log_action(
        db=db,
        tenant_id=user.tenant_id,
        action=action,
        resource_type=resource_type,
        user=user,
        resource_id=resource_id,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
        request_method=request_method,
        request_path=request_path,
        meta=meta,  # Changed from metadata to meta
    )