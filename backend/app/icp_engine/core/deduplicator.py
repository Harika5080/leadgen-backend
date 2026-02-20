"""
Deduplicator for finding duplicate leads.

Checks for existing leads by email + tenant_id.
"""
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.models import Lead


logger = logging.getLogger(__name__)


class Deduplicator:
    """
    Find and handle duplicate leads.
    
    Uses email + tenant_id as the primary deduplication key.
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize deduplicator.
        
        Args:
            db: Database session
        """
        self.db = db
    
    async def find_duplicate(self, email: str, tenant_id: str) -> Optional[Lead]:
        """
        Find existing lead by email and tenant.
        
        Args:
            email: Lead email address
            tenant_id: Tenant ID
        
        Returns:
            Existing Lead object or None
        """
        try:
            stmt = select(Lead).where(
                Lead.email == email.lower(),
                Lead.tenant_id == tenant_id
            )
            result = await self.db.execute(stmt)
            lead = result.scalars().first()
            
            return lead
        
        except Exception as e:
            logger.error(f"Error finding duplicate: {e}")
            return None
    
    def merge_lead_data(
        self, 
        existing_lead: Lead, 
        new_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge new data into existing lead.
        
        Strategy: Keep most recent non-null values.
        
        Args:
            existing_lead: Existing lead record
            new_data: New lead data
        
        Returns:
            Merged data dictionary
        """
        # Start with existing lead data
        merged = {
            "first_name": existing_lead.first_name,
            "last_name": existing_lead.last_name,
            "phone": existing_lead.phone,
            "job_title": existing_lead.job_title,
            "linkedin_url": existing_lead.linkedin_url,
            "company_id": existing_lead.company_id,
            "metadata": existing_lead.metadata or {},
        }
        
        # Update with new non-null values
        for key, value in new_data.items():
            if value is not None:
                # For certain fields, prefer newer data
                if key in ["phone", "job_title", "linkedin_url"]:
                    merged[key] = value
                # For first_name, last_name, only update if existing is null
                elif key in ["first_name", "last_name"]:
                    if not merged.get(key):
                        merged[key] = value
                # For metadata, merge dictionaries
                elif key == "metadata":
                    if isinstance(value, dict):
                        merged["metadata"].update(value)
        
        # Track duplicate sources
        if "duplicate_sources" not in merged["metadata"]:
            merged["metadata"]["duplicate_sources"] = []
        
        if "source_id" in new_data:
            merged["metadata"]["duplicate_sources"].append(new_data["source_id"])
        
        return merged
    
    async def update_existing_lead(
        self, 
        lead: Lead, 
        merged_data: Dict[str, Any]
    ) -> Lead:
        """
        Update existing lead with merged data.
        
        Args:
            lead: Existing lead object
            merged_data: Merged data
        
        Returns:
            Updated lead object
        """
        # Update fields
        for key, value in merged_data.items():
            if hasattr(lead, key):
                setattr(lead, key, value)
        
        await self.db.commit()
        await self.db.refresh(lead)
        
        logger.info(f"Updated duplicate lead: {lead.email}")
        
        return lead