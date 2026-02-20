"""
Authentication Service Helpers
Utility functions for authentication and authorization
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException
from uuid import UUID

from app.models import ICP, Lead


def check_tenant_access(db: Session, tenant_id: UUID, icp_id: UUID):
    """
    Verify that an ICP belongs to the tenant.
    
    Raises HTTPException if access is denied.
    """
    from app.models import ICP
    
    icp = db.query(ICP).filter(
        ICP.id == icp_id,
        ICP.tenant_id == tenant_id
    ).first()
    
    if not icp:
        raise HTTPException(
            status_code=404,
            detail="ICP not found or access denied"
        )
    
    return icp


def check_lead_access(db: Session, tenant_id: UUID, lead_id: UUID):
    """
    Verify that a lead belongs to the tenant.
    
    Raises HTTPException if access is denied.
    """
    from app.models import Lead
    
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.tenant_id == tenant_id
    ).first()
    
    if not lead:
        raise HTTPException(
            status_code=404,
            detail="Lead not found or access denied"
        )
    
    return lead