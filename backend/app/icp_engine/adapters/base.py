"""
Base adapter interface for data sources.
All adapters must implement this interface.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime


class DataSourceAdapter(ABC):
    """
    Abstract base class for all data source adapters.
    Every new source must implement these methods.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize adapter with configuration from database.
        
        Args:
            config: Source config (API keys, endpoints, filters, etc.)
        """
        self.config = config
        self.source_type = self.__class__.__name__
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test if connection/authentication works.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def fetch_leads(
        self, 
        limit: Optional[int] = None,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch leads from data source.
        
        Args:
            limit: Max number of leads to fetch
            since: Only fetch leads updated after this time
            
        Returns:
            List of raw lead dictionaries (source format)
        """
        pass
    
    @abstractmethod
    def get_field_schema(self) -> Dict[str, str]:
        """
        Return available fields from this source.
        
        Returns:
            Dict of field_name: data_type
        """
        pass
    
    def get_rate_limit(self) -> Dict[str, int]:
        """Return rate limit info for this source."""
        return {
            "requests_per_minute": self.config.get("rate_limit_rpm", 60),
            "concurrent_requests": self.config.get("concurrent_limit", 5)
        }
    
    def validate_config(self) -> List[str]:
        """
        Validate configuration, return list of errors.
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        # Subclasses override to add specific validation
        return errors