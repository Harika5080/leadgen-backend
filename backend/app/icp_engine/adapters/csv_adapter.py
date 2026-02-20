"""
Adapter for CSV file uploads.
"""
import csv
import io
from typing import List, Dict, Any, Optional
from datetime import datetime
from .base import DataSourceAdapter


class CSVAdapter(DataSourceAdapter):
    """Adapter for CSV file uploads."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.csv_data = config.get("csv_data", "")  # CSV string or path
        self.delimiter = config.get("delimiter", ",")
        self.has_header = config.get("has_header", True)
    
    async def test_connection(self) -> bool:
        """Test if CSV data is valid."""
        try:
            if not self.csv_data:
                return False
            
            # Try to parse CSV
            reader = csv.DictReader(
                io.StringIO(self.csv_data),
                delimiter=self.delimiter
            )
            # Read first row to validate
            next(reader, None)
            return True
        except Exception:
            return False
    
    async def fetch_leads(
        self,
        limit: Optional[int] = None,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Parse CSV and return leads."""
        leads = []
        
        reader = csv.DictReader(
            io.StringIO(self.csv_data),
            delimiter=self.delimiter
        )
        
        for i, row in enumerate(reader):
            if limit and i >= limit:
                break
            
            # Convert CSV row to dict
            lead = {k: v for k, v in row.items() if v}
            leads.append(lead)
        
        return leads
    
    def get_field_schema(self) -> Dict[str, str]:
        """Infer schema from CSV headers."""
        try:
            reader = csv.DictReader(
                io.StringIO(self.csv_data),
                delimiter=self.delimiter
            )
            fields = reader.fieldnames or []
            
            # All fields are strings by default
            return {field: "string" for field in fields}
        except Exception:
            return {}
    
    def validate_config(self) -> List[str]:
        """Validate CSV-specific config."""
        errors = super().validate_config()
        
        if not self.config.get("csv_data"):
            errors.append("csv_data is required")
        
        return errors