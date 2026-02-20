"""
Field mapper for transforming source data to target schema.

Maps fields from various data sources to a standardized lead schema.
"""
from typing import Dict, Any, Callable
import logging


logger = logging.getLogger(__name__)


class FieldMapper:
    """
    Maps source fields to target schema with transformations.
    
    Supports:
    - Direct mapping: {"email": "email"}
    - Nested paths: {"company_name": "organization.name"}
    - Transformations: {"email": "email|lowercase"}
    """
    
    def __init__(self, field_mappings: Dict[str, str]):
        """
        Initialize field mapper.
        
        Args:
            field_mappings: Dict mapping target_field -> source_path
            Example: {
                "email": "email",
                "first_name": "first_name",
                "company_name": "organization.name",
                "phone": "phones[0].number"
            }
        """
        self.field_mappings = field_mappings
        self.transformers = {}
        self._register_default_transformers()
    
    def _register_default_transformers(self):
        """Register built-in transformation functions."""
        self.transformers["lowercase"] = lambda x: str(x).lower() if x else None
        self.transformers["uppercase"] = lambda x: str(x).upper() if x else None
        self.transformers["trim"] = lambda x: str(x).strip() if x else None
        self.transformers["email_domain"] = lambda x: str(x).split("@")[1] if x and "@" in str(x) else None
    
    def register_transformer(self, name: str, func: Callable):
        """
        Register a custom transformer function.
        
        Args:
            name: Transformer name
            func: Function that takes a value and returns transformed value
        """
        self.transformers[name] = func
    
    def _extract_value(self, data: Dict[str, Any], path: str) -> Any:
        """
        Extract value from nested dict using dot notation.
        
        Args:
            data: Source data dictionary
            path: Path like "organization.name" or "phones[0].number"
        
        Returns:
            Extracted value or None
        """
        try:
            # Handle array indices like "phones[0].number"
            if "[" in path and "]" in path:
                # Split by array notation
                parts = path.replace("]", "").split("[")
                value = data
                
                for i, part in enumerate(parts):
                    if i == 0:
                        # First part is the field name
                        value = value.get(part)
                    else:
                        # This part has format: "index.remaining.path" or just "index"
                        if "." in part:
                            index_str, remaining = part.split(".", 1)
                            index = int(index_str)
                            if isinstance(value, list) and len(value) > index:
                                value = value[index]
                                # Continue with remaining path
                                for key in remaining.split("."):
                                    if isinstance(value, dict):
                                        value = value.get(key)
                                    else:
                                        return None
                            else:
                                return None
                        else:
                            # Just an index
                            index = int(part)
                            if isinstance(value, list) and len(value) > index:
                                value = value[index]
                            else:
                                return None
                
                return value
            
            # Simple dot notation
            keys = path.split(".")
            value = data
            
            for key in keys:
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    return None
            
            return value
        
        except Exception as e:
            logger.debug(f"Error extracting path '{path}': {e}")
            return None
    
    def _apply_transformations(self, value: Any, transformations: str) -> Any:
        """
        Apply transformation pipeline.
        
        Args:
            value: Input value
            transformations: Pipe-separated transformations like "trim|lowercase"
        
        Returns:
            Transformed value
        """
        if not transformations or value is None:
            return value
        
        result = value
        
        for transformer_name in transformations.split("|"):
            transformer = self.transformers.get(transformer_name.strip())
            if transformer:
                result = transformer(result)
        
        return result
    
    def map_fields(self, source_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map source data to target schema.
        
        Args:
            source_data: Raw data from source
        
        Returns:
            Mapped data with target field names
        """
        mapped = {}
        
        for target_field, mapping in self.field_mappings.items():
            # Check if mapping includes transformations
            if "|" in mapping:
                source_path, transformations = mapping.split("|", 1)
            else:
                source_path = mapping
                transformations = None
            
            # Extract value from source
            value = self._extract_value(source_data, source_path.strip())
            
            # Apply transformations
            if transformations:
                value = self._apply_transformations(value, transformations)
            
            # Only set if value is not None
            if value is not None:
                mapped[target_field] = value
        
        return mapped
    
    def map_batch(self, source_data_list: list) -> list:
        """
        Map a batch of source records.
        
        Args:
            source_data_list: List of raw data dictionaries
        
        Returns:
            List of mapped dictionaries
        """
        return [self.map_fields(data) for data in source_data_list]