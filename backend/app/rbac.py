"""Enhanced role-based access control (RBAC) system."""

from enum import Enum
from typing import List
from fastapi import Depends, HTTPException, status
import logging

from app.auth import get_current_user
from app.models import User

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """User roles with hierarchical permissions."""
    ADMIN = "admin"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class Permission(str, Enum):
    """Granular permissions for different actions."""
    # Lead permissions
    VIEW_LEADS = "view_leads"
    CREATE_LEADS = "create_leads"
    EDIT_LEADS = "edit_leads"
    DELETE_LEADS = "delete_leads"
    REVIEW_LEADS = "review_leads"
    EXPORT_LEADS = "export_leads"
    
    # User management
    VIEW_USERS = "view_users"
    CREATE_USERS = "create_users"
    EDIT_USERS = "edit_users"
    DELETE_USERS = "delete_users"
    
    # Settings
    VIEW_SETTINGS = "view_settings"
    EDIT_SETTINGS = "edit_settings"
    
    # Analytics
    VIEW_ANALYTICS = "view_analytics"


# Role to permissions mapping
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [
        # All permissions
        Permission.VIEW_LEADS,
        Permission.CREATE_LEADS,
        Permission.EDIT_LEADS,
        Permission.DELETE_LEADS,
        Permission.REVIEW_LEADS,
        Permission.EXPORT_LEADS,
        Permission.VIEW_USERS,
        Permission.CREATE_USERS,
        Permission.EDIT_USERS,
        Permission.DELETE_USERS,
        Permission.VIEW_SETTINGS,
        Permission.EDIT_SETTINGS,
        Permission.VIEW_ANALYTICS,
    ],
    UserRole.REVIEWER: [
        # Can view, review, and export leads
        Permission.VIEW_LEADS,
        Permission.REVIEW_LEADS,
        Permission.EXPORT_LEADS,
        Permission.VIEW_ANALYTICS,
        Permission.VIEW_SETTINGS,
    ],
    UserRole.VIEWER: [
        # Read-only access
        Permission.VIEW_LEADS,
        Permission.VIEW_ANALYTICS,
        Permission.VIEW_SETTINGS,
    ],
}


def has_permission(user: User, permission: Permission) -> bool:
    """Check if user has a specific permission."""
    user_role = UserRole(user.role)
    return permission in ROLE_PERMISSIONS.get(user_role, [])


def check_permission(user: User, permission: Permission):
    """Raise exception if user doesn't have permission."""
    if not has_permission(user, permission):
        logger.warning(
            f"Permission denied: {user.email} (role: {user.role}) "
            f"attempted {permission.value}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied. Required permission: {permission.value}"
        )


# Dependency factories for common permission checks
def require_permission(permission: Permission):
    """Dependency factory to require a specific permission."""
    async def permission_checker(current_user: User = Depends(get_current_user)):
        check_permission(current_user, permission)
        return current_user
    return permission_checker


# Common permission dependencies
async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role."""
    if current_user.role != UserRole.ADMIN:
        logger.warning(f"Admin access denied for user: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


async def require_reviewer_or_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require reviewer or admin role."""
    if current_user.role not in [UserRole.ADMIN, UserRole.REVIEWER]:
        logger.warning(
            f"Reviewer access denied for user: {current_user.email} "
            f"(role: {current_user.role})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer or admin privileges required"
        )
    return current_user


# Specific permission dependencies
require_view_leads = require_permission(Permission.VIEW_LEADS)
require_create_leads = require_permission(Permission.CREATE_LEADS)
require_edit_leads = require_permission(Permission.EDIT_LEADS)
require_delete_leads = require_permission(Permission.DELETE_LEADS)
require_review_leads = require_permission(Permission.REVIEW_LEADS)
require_export_leads = require_permission(Permission.EXPORT_LEADS)

require_view_users = require_permission(Permission.VIEW_USERS)
require_create_users = require_permission(Permission.CREATE_USERS)
require_edit_users = require_permission(Permission.EDIT_USERS)
require_delete_users = require_permission(Permission.DELETE_USERS)

require_view_settings = require_permission(Permission.VIEW_SETTINGS)
require_edit_settings = require_permission(Permission.EDIT_SETTINGS)

require_view_analytics = require_permission(Permission.VIEW_ANALYTICS)