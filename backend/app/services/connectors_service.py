"""Connector implementations for external lead sources."""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import httpx
import logging

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    """Base class for all connectors."""
    
    @abstractmethod
    async def test_connection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Test if credentials and configuration are valid."""
        pass
    
    @abstractmethod
    async def fetch_leads(self, config: Dict[str, Any], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch leads from the external source."""
        pass
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Return JSON schema for connector configuration."""
        return {}


class APIConnector(BaseConnector):
    """Generic API connector for any REST API."""
    
    async def test_connection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Test API connection."""
        try:
            endpoint = config.get('endpoint')
            auth_type = config.get('auth_type', 'bearer')
            api_key = config.get('api_key')
            
            headers = self._build_headers(auth_type, api_key, config)
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(endpoint, headers=headers)
                response.raise_for_status()
                
            return {
                'success': True,
                'message': 'Connection successful',
                'status_code': response.status_code
            }
        except Exception as e:
            logger.error(f"API connector test failed: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    async def fetch_leads(self, config: Dict[str, Any], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch leads from API endpoint."""
        try:
            endpoint = config.get('endpoint')
            method = config.get('method', 'GET').upper()
            auth_type = config.get('auth_type', 'bearer')
            api_key = config.get('api_key')
            field_mapping = config.get('field_mapping', {})
            response_path = config.get('response_path', '')  # Empty = root level array
            
            headers = self._build_headers(auth_type, api_key, config)
            params = {}
            if limit:
                params['limit'] = limit
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == 'GET':
                    response = await client.get(endpoint, headers=headers, params=params)
                elif method == 'POST':
                    response = await client.post(endpoint, headers=headers, json=params)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                response.raise_for_status()
                data = response.json()
            
            # Extract leads from response path
            leads_data = self._get_nested_value(data, response_path)
            if not isinstance(leads_data, list):
                leads_data = [leads_data]
            
            # Map fields to our schema
            mapped_leads = []
            for lead in leads_data:
                mapped_lead = self._map_fields(lead, field_mapping)
                if mapped_lead.get('email'):  # Must have email
                    mapped_leads.append(mapped_lead)
            
            logger.info(f"API connector fetched {len(mapped_leads)} leads")
            return mapped_leads
            
        except Exception as e:
            logger.error(f"API connector fetch failed: {e}")
            raise
    
    def _build_headers(self, auth_type: str, api_key: str, config: Dict) -> Dict[str, str]:
        """Build request headers based on auth type."""
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'LeadGen-Connector/1.0'
        }
        
        if auth_type == 'bearer':
            headers['Authorization'] = f'Bearer {api_key}'
        elif auth_type == 'api_key':
            key_name = config.get('api_key_header', 'X-API-Key')
            headers[key_name] = api_key
        elif auth_type == 'basic':
            import base64
            username = config.get('username', '')
            password = config.get('password', '')
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers['Authorization'] = f'Basic {credentials}'
        
        # Custom headers
        custom_headers = config.get('custom_headers', {})
        headers.update(custom_headers)
        
        return headers
    
    def _get_nested_value(self, data: Any, path: str) -> Any:
        """Get nested value from dict using dot notation (e.g., 'data.leads').
        If path is empty, return data as-is (for root-level arrays)."""
        
        # Handle empty path - return data as-is
        if not path or path.strip() == '':
            return data
        
        keys = path.split('.')
        value = data
        for key in keys:
            if key.strip() == '':  # Skip empty keys
                continue
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    logger.warning(f"Key '{key}' not found in response path '{path}'")
                    return None
            else:
                logger.warning(f"Cannot navigate path '{path}' - value is not a dict at key '{key}'")
                return None
        return value
    
    def _map_fields(self, source_lead: Dict, field_mapping: Dict) -> Dict[str, Any]:
        """Map source fields to our lead schema.
        
        field_mapping format: {"our_field": "source.field.path"}
        Example: {"email": "email", "firstName": "name", "companyName": "company.name"}
        """
        mapped = {}
        
        # If no field_mapping provided, try to map common fields automatically
        if not field_mapping:
            field_mapping = {
                'email': 'email',
                'firstName': 'name',
                'lastName': 'username',  # JSONPlaceholder doesn't have lastName
                'phone': 'phone',
                'companyName': 'company.name',
                'website': 'website',
            }
        
        # Map each field
        for our_field, source_field in field_mapping.items():
            value = self._get_nested_value(source_lead, source_field)
            if value:
                mapped[our_field] = value
        
        # Add external_id if present
        if 'id' in source_lead and 'external_id' not in mapped:
            mapped['external_id'] = str(source_lead['id'])
        
        logger.debug(f"Mapped lead: {mapped}")
        return mapped
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Return configuration schema."""
        return {
            'endpoint': {'type': 'string', 'required': True, 'label': 'API Endpoint URL'},
            'method': {'type': 'select', 'options': ['GET', 'POST'], 'default': 'GET', 'label': 'HTTP Method'},
            'auth_type': {'type': 'select', 'options': ['bearer', 'api_key', 'basic', 'none'], 'default': 'bearer', 'label': 'Authentication Type'},
            'api_key': {'type': 'password', 'required': True, 'label': 'API Key/Token'},
            'response_path': {'type': 'string', 'default': 'data', 'label': 'Response Path (e.g., data.leads)'},
            'field_mapping': {'type': 'json', 'label': 'Field Mapping (JSON)'},
        }


class MetaLeadAdsConnector(BaseConnector):
    """Meta (Facebook/Instagram) Lead Ads connector."""
    
    async def test_connection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Test Meta API connection."""
        try:
            access_token = config.get('access_token')
            
            # Test with a simple API call
            url = "https://graph.facebook.com/v18.0/me"
            params = {'access_token': access_token}
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
            
            return {
                'success': True,
                'message': f"Connected as: {data.get('name', 'Unknown')}",
                'account_id': data.get('id')
            }
        except Exception as e:
            logger.error(f"Meta connector test failed: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    async def fetch_leads(self, config: Dict[str, Any], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch leads from Meta Lead Ads."""
        try:
            access_token = config.get('access_token')
            form_id = config.get('form_id')
            
            if not form_id:
                raise ValueError("form_id is required")
            
            # Fetch leads from Meta Graph API
            url = f"https://graph.facebook.com/v18.0/{form_id}/leads"
            params = {
                'access_token': access_token,
                'fields': 'id,created_time,field_data',
            }
            if limit:
                params['limit'] = limit
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
            
            leads_data = data.get('data', [])
            
            # Transform Meta format to our format
            mapped_leads = []
            for lead in leads_data:
                lead_dict = {field['name']: field['values'][0] 
                           for field in lead.get('field_data', [])}
                
                mapped_lead = {
                    'email': lead_dict.get('email'),
                    'firstName': lead_dict.get('first_name') or lead_dict.get('full_name', '').split()[0],
                    'lastName': lead_dict.get('last_name') or ' '.join(lead_dict.get('full_name', '').split()[1:]),
                    'phone': lead_dict.get('phone_number'),
                    'companyName': lead_dict.get('company_name'),
                    'jobTitle': lead_dict.get('job_title'),
                    'external_id': lead['id'],
                    'source_name': 'Meta Lead Ads',
                }
                
                # Remove None values
                mapped_lead = {k: v for k, v in mapped_lead.items() if v}
                
                if mapped_lead.get('email'):
                    mapped_leads.append(mapped_lead)
            
            logger.info(f"Meta connector fetched {len(mapped_leads)} leads")
            return mapped_leads
            
        except Exception as e:
            logger.error(f"Meta connector fetch failed: {e}")
            raise
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Return configuration schema."""
        return {
            'access_token': {'type': 'password', 'required': True, 'label': 'Access Token'},
            'form_id': {'type': 'string', 'required': True, 'label': 'Lead Form ID'},
            'page_id': {'type': 'string', 'label': 'Page ID (optional)'},
        }


class LinkedInConnector(BaseConnector):
    """LinkedIn Lead Gen Forms connector."""
    
    async def test_connection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Test LinkedIn API connection."""
        try:
            access_token = config.get('access_token')
            
            # Test with userinfo endpoint
            url = "https://api.linkedin.com/v2/userinfo"
            headers = {'Authorization': f'Bearer {access_token}'}
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
            
            return {
                'success': True,
                'message': f"Connected as: {data.get('name', 'Unknown')}",
                'user_id': data.get('sub')
            }
        except Exception as e:
            logger.error(f"LinkedIn connector test failed: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    async def fetch_leads(self, config: Dict[str, Any], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch leads from LinkedIn Lead Gen Forms."""
        try:
            access_token = config.get('access_token')
            campaign_id = config.get('campaign_id')
            
            # Note: This is a simplified example - actual LinkedIn API may differ
            url = f"https://api.linkedin.com/v2/adForms/{campaign_id}/leads"
            headers = {'Authorization': f'Bearer {access_token}'}
            params = {}
            if limit:
                params['count'] = limit
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
            
            leads_data = data.get('elements', [])
            
            # Transform LinkedIn format
            mapped_leads = []
            for lead in leads_data:
                mapped_lead = {
                    'email': lead.get('emailAddress'),
                    'firstName': lead.get('firstName'),
                    'lastName': lead.get('lastName'),
                    'phone': lead.get('phoneNumber'),
                    'companyName': lead.get('company'),
                    'jobTitle': lead.get('jobTitle'),
                    'linkedinUrl': lead.get('linkedInProfileUrl'),
                    'external_id': lead.get('id'),
                    'source_name': 'LinkedIn',
                }
                
                mapped_lead = {k: v for k, v in mapped_lead.items() if v}
                
                if mapped_lead.get('email'):
                    mapped_leads.append(mapped_lead)
            
            logger.info(f"LinkedIn connector fetched {len(mapped_leads)} leads")
            return mapped_leads
            
        except Exception as e:
            logger.error(f"LinkedIn connector fetch failed: {e}")
            raise
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Return configuration schema."""
        return {
            'access_token': {'type': 'password', 'required': True, 'label': 'Access Token'},
            'campaign_id': {'type': 'string', 'required': True, 'label': 'Campaign/Form ID'},
        }


class ConnectorFactory:
    """Factory to get connector instances."""
    
    _connectors = {
        'api': APIConnector,
        'meta': MetaLeadAdsConnector,
        'linkedin': LinkedInConnector,
    }
    
    @classmethod
    def get_connector(cls, connector_type: str) -> BaseConnector:
        """Get connector instance by type."""
        connector_class = cls._connectors.get(connector_type)
        if not connector_class:
            raise ValueError(f"Unknown connector type: {connector_type}")
        return connector_class()
    
    @classmethod
    def get_available_types(cls) -> List[str]:
        """Get list of available connector types."""
        return list(cls._connectors.keys())