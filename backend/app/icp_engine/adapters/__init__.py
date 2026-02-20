"""
Adapter factory and registry.
"""
from .base import DataSourceAdapter
from .http_adapter import HTTPAdapter
from .csv_adapter import CSVAdapter
from .webhook import WebhookAdapter

# Registry of available adapters
ADAPTER_REGISTRY = {
    "http_api": HTTPAdapter,
    "csv": CSVAdapter,
    "webhook": WebhookAdapter,
}


def get_adapter(source_type: str, source: 'DataSource') -> DataSourceAdapter:
    """
    Factory function to create appropriate adapter.
    
    Args:
        source_type: Type of source (http_api, csv, webhook)
        source: DataSource model instance (has all config fields)
        
    Returns:
        Instantiated adapter
    """
    adapter_class = ADAPTER_REGISTRY.get(source_type)
    
    if not adapter_class:
        raise ValueError(
            f"Unknown source type: {source_type}. "
            f"Available: {list(ADAPTER_REGISTRY.keys())}"
        )
    
    # Build config dict based on source type
    if source_type == "http_api":
        config = {
            "http_config": source.http_config,
            "variables": source.variables,
            "field_mappings": source.field_mappings,
        }
    else:
        # csv, webhook use legacy config field
        config = {
            "config": source.config,
            "field_mappings": source.field_mappings,
        }
    
    return adapter_class(config)