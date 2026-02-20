"""
Adapter for webhook-based data ingestion.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from .base import DataSourceAdapter


class WebhookAdapter(DataSourceAdapter):
    """
    Adapter for webhook-based ingestion.
    Stores incoming webhook data temporarily.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.webhook_data = config.get("webhook_data", [])  # List of leads from webhook
    
    async def test_connection(self) -> bool:
        """Webhooks are always 'connected' (passive receiver)."""
        return True
    
    async def fetch_leads(
        self,
        limit: Optional[int] = None,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Return stored webhook data."""
        leads = self.webhook_data
        
        if limit:
            leads = leads[:limit]
        
        return leads
    
    def get_field_schema(self) -> Dict[str, str]:
        """Return generic schema (fields depend on webhook sender)."""
        return {
            "email": "string",
            "first_name": "string",
            "last_name": "string",
            "company": "string",
            "job_title": "string",
            "phone": "string",
        }
    
    def validate_config(self) -> List[str]:
        """Validate webhook config."""
        errors = super().validate_config()
        # Webhooks don't require config validation
        return errors