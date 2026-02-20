# backend/scrapers/base_adapter.py
"""
Base adapter interface for all data source types.
All adapters inherit from this class.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SourceAdapter(ABC):
    """Base class for all data source adapters"""
    
    def __init__(self, data_source):
        """
        Initialize adapter with data source configuration
        
        Args:
            data_source: DataSource model instance
        """
        self.data_source = data_source
        self.config = data_source.config or {}
        self.stats = {
            'started_at': datetime.utcnow(),
            'leads_found': 0,
            'leads_processed': 0,
            'leads_saved': 0,
            'errors': 0,
            'error_details': []
        }
    
    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test if source is reachable and configured correctly
        
        Returns:
            Dict with 'success', 'message', and optional 'details'
        """
        pass
    
    @abstractmethod
    async def fetch(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetch raw data from source
        
        Args:
            limit: Maximum number of records to fetch
            
        Returns:
            List of dictionaries containing raw lead data
        """
        pass
    
    async def run(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Main execution: fetch data and save to raw_leads
        
        Args:
            limit: Maximum number of records to process
            
        Returns:
            Statistics about the run
        """
        from app.models import RawLead
        from app.database import get_db
        
        logger.info(f"Starting data source run: {self.data_source.name}")
        
        async for db in get_db():
            try:
                # Update status to running
                self.data_source.last_run_at = datetime.utcnow()
                self.data_source.last_run_status = 'running'
                await db.commit()
                
                # Fetch raw data
                logger.info(f"Fetching data with limit: {limit}")
                raw_data = await self.fetch(limit)
                self.stats['leads_found'] = len(raw_data)
                
                logger.info(f"Found {len(raw_data)} leads")
                
                # Save to raw_leads table
                for idx, item in enumerate(raw_data):
                    try:
                        # Apply field mappings
                        mapped_data = self.apply_field_mapping(item)
                        
                        raw_lead = RawLead(
                            data_source_id=self.data_source.id,
                            tenant_id=self.data_source.tenant_id,
                            icp_id=self.data_source.icp_id,
                            raw_data=item,
                            mapped_data=mapped_data,
                            source_url=item.get('url') or item.get('source_url'),
                            status='pending'
                        )
                        db.add(raw_lead)
                        self.stats['leads_saved'] += 1
                        
                        # Commit in batches
                        if (idx + 1) % 100 == 0:
                            await db.commit()
                            logger.info(f"Saved {idx + 1} leads...")
                        
                    except Exception as e:
                        self.stats['errors'] += 1
                        self.stats['error_details'].append({
                            'lead_index': idx,
                            'error': str(e)
                        })
                        logger.error(f"Error processing lead {idx}: {e}")
                
                # Final commit
                await db.commit()
                
                # Calculate stats
                self.stats['completed_at'] = datetime.utcnow()
                self.stats['duration_seconds'] = (
                    self.stats['completed_at'] - self.stats['started_at']
                ).total_seconds()
                
                # Update data source status
                self.data_source.last_run_status = 'success'
                self.data_source.last_run_stats = {
                    'leads_found': self.stats['leads_found'],
                    'leads_saved': self.stats['leads_saved'],
                    'duration': self.stats['duration_seconds'],
                    'errors': self.stats['errors']
                }
                self.data_source.last_error = None
                
                await db.commit()
                
                logger.info(f"Completed data source run: {self.data_source.name}")
                logger.info(f"Stats: {self.stats}")
                
                return self.stats
                
            except Exception as e:
                self.stats['errors'] += 1
                self.stats['error_message'] = str(e)
                
                # Update data source with error
                self.data_source.last_run_status = 'failed'
                self.data_source.last_error = str(e)
                self.data_source.last_run_stats = self.stats
                
                await db.commit()
                
                logger.error(f"Data source run failed: {e}", exc_info=True)
                raise
    
    def apply_field_mapping(self, raw_data: Dict) -> Dict:
        """
        Apply field mappings to transform data
        
        Args:
            raw_data: Raw data from source
            
        Returns:
            Mapped data according to field_mappings configuration
        """
        if not self.data_source.field_mappings:
            return raw_data
        
        mapped = {}
        for source_field, target_field in self.data_source.field_mappings.items():
            # Handle nested fields (e.g., "person.email")
            if '.' in source_field:
                value = self._get_nested_value(raw_data, source_field)
            else:
                value = raw_data.get(source_field)
            
            if value is not None:
                mapped[target_field] = value
        
        return mapped
    
    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """
        Get value from nested dictionary using dot notation
        
        Args:
            data: Dictionary to extract from
            path: Dot-separated path (e.g., "person.contact.email")
            
        Returns:
            Value at the path, or None if not found
        """
        current = data
        for key in path.split('.'):
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current
    
    @classmethod
    @abstractmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Return JSON schema for configuration
        Used to generate UI forms
        
        Returns:
            JSON schema dictionary
        """
        pass
    
    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Return default configuration
        
        Returns:
            Default config dictionary
        """
        return {}