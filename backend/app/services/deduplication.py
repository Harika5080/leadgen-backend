"""Lead deduplication service using Redis cache."""

import hashlib
import logging
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import redis.asyncio as redis

from app.config import settings
from app.models import Lead

logger = logging.getLogger(__name__)


class DeduplicationService:
    """Check for duplicate leads using Redis cache and database."""
    
    def __init__(self):
        """Initialize Redis connection."""
        self.redis_client = None
    
    async def initialize(self):
        """Initialize Redis connection."""
        if not self.redis_client:
            self.redis_client = await redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info("Redis connection initialized for deduplication")
    
    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
    
    @staticmethod
    def generate_cache_key(tenant_id: UUID, email: str) -> str:
        """Generate cache key for tenant+email combination."""
        return f"lead:duplicate:{tenant_id}:{email.lower()}"
    
    @staticmethod
    def generate_email_hash(email: str) -> str:
        """Generate hash of email for privacy-preserving checks."""
        return hashlib.sha256(email.lower().encode()).hexdigest()
    
    async def check_duplicate(
        self, 
        tenant_id: UUID, 
        email: str,
        db: AsyncSession
    ) -> Optional[UUID]:
        """
        Check if lead exists for this tenant.
        Returns existing lead_id if duplicate found, None otherwise.
        
        Uses two-tier checking:
        1. Redis cache (fast)
        2. Database query (if cache miss)
        """
        email_lower = email.lower()
        cache_key = self.generate_cache_key(tenant_id, email_lower)
        
        # Check Redis cache first
        if self.redis_client:
            try:
                cached_lead_id = await self.redis_client.get(cache_key)
                if cached_lead_id:
                    logger.debug(f"Cache hit for duplicate check: {email}")
                    return UUID(cached_lead_id)
            except Exception as e:
                logger.warning(f"Redis cache check failed: {e}")
        
        # Cache miss - check database
        result = await db.execute(
            select(Lead.id).where(
                and_(
                    Lead.tenant_id == tenant_id,
                    Lead.email == email_lower
                )
            )
        )
        existing_lead = result.scalar_one_or_none()
        
        if existing_lead:
            # Cache the result
            if self.redis_client:
                try:
                    await self.redis_client.setex(
                        cache_key,
                        3600,  # Cache for 1 hour
                        str(existing_lead)
                    )
                except Exception as e:
                    logger.warning(f"Redis cache write failed: {e}")
            
            logger.debug(f"Database duplicate found: {email}")
            return existing_lead
        
        return None
    
    async def mark_lead_in_cache(self, tenant_id: UUID, email: str, lead_id: UUID):
        """Add lead to cache to speed up future duplicate checks."""
        if not self.redis_client:
            return
        
        cache_key = self.generate_cache_key(tenant_id, email.lower())
        
        try:
            await self.redis_client.setex(
                cache_key,
                3600,  # Cache for 1 hour
                str(lead_id)
            )
            logger.debug(f"Lead cached for deduplication: {email}")
        except Exception as e:
            logger.warning(f"Failed to cache lead: {e}")
    
    async def invalidate_cache(self, tenant_id: UUID, email: str):
        """Remove lead from cache (e.g., after deletion)."""
        if not self.redis_client:
            return
        
        cache_key = self.generate_cache_key(tenant_id, email.lower())
        
        try:
            await self.redis_client.delete(cache_key)
            logger.debug(f"Cache invalidated for: {email}")
        except Exception as e:
            logger.warning(f"Failed to invalidate cache: {e}")


# Singleton instance
deduplication_service = DeduplicationService()
