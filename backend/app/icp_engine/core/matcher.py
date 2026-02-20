"""
ICP matcher for determining which ICPs apply to a lead.

Currently returns all active ICPs for a tenant.
Future: Smart matching based on lead attributes.
"""
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.models import ICP


logger = logging.getLogger(__name__)


class ICPMatcher:
    """
    Determine which ICPs apply to a lead.
    
    Current implementation: Return all active ICPs for tenant.
    Future: Smart matching based on lead attributes (industry, company size, etc.)
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize ICP matcher.
        
        Args:
            db: Database session
        """
        self.db = db
    
    async def find_applicable_icps(
        self, 
        tenant_id: str, 
        lead_data: dict = None
    ) -> List[ICP]:
        """
        Find ICPs that apply to this lead.
        
        Args:
            tenant_id: Tenant ID
            lead_data: Lead data (for future smart matching)
        
        Returns:
            List of applicable ICP objects
        """
        try:
            # For now, return all active ICPs for tenant
            stmt = select(ICP).where(
                ICP.tenant_id == tenant_id,
                ICP.is_active == True
            )
            result = await self.db.execute(stmt)
            icps = result.scalars().all()
            
            logger.info(f"Found {len(icps)} applicable ICPs for tenant {tenant_id}")
            
            return list(icps)
        
        except Exception as e:
            logger.error(f"Error finding applicable ICPs: {e}")
            return []
    
    def _matches_icp_criteria(self, lead_data: dict, icp: ICP) -> bool:
        """
        Check if lead matches ICP criteria.
        
        Future implementation for smart matching.
        
        Args:
            lead_data: Lead data
            icp: ICP object
        
        Returns:
            bool: True if lead matches ICP criteria
        """
        # Future: Implement smart matching logic
        # Example:
        # - Check if company industry matches ICP target industries
        # - Check if company size is in ICP target range
        # - Check if job title matches ICP target titles
        
        return True  # For now, all leads match