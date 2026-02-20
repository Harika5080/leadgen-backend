# backend/app/redis_client.py
"""
Mock Redis Client for development
In production, this would connect to actual Redis
"""

import logging

logger = logging.getLogger(__name__)


class MockRedisClient:
    """Mock Redis client that does nothing"""
    
    def __init__(self):
        self._store = {}
        logger.info("Using mock Redis client (no actual Redis connection)")
    
    async def get(self, key: str):
        """Mock get - always returns None"""
        return self._store.get(key)
    
    async def set(self, key: str, value: str):
        """Mock set - stores in memory"""
        self._store[key] = value
        return True
    
    async def setex(self, key: str, seconds: int, value: str):
        """Mock setex - stores in memory (ignores TTL)"""
        self._store[key] = value
        return True
    
    async def delete(self, key: str):
        """Mock delete"""
        if key in self._store:
            del self._store[key]
        return True
    
    def __getattr__(self, name):
        """Catch-all for any other Redis methods"""
        async def mock_method(*args, **kwargs):
            logger.debug(f"Mock Redis: {name}() called")
            return None
        return mock_method


# Create singleton instance
redis_client = MockRedisClient()
