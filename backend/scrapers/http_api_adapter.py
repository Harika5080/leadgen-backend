# backend/scrapers/http_api_adapter.py
"""
HTTP API adapter for external APIs like LinkedIn, Apollo.io, ZoomInfo, etc.
Handles authentication, pagination, rate limiting.
"""
import httpx
import asyncio
import logging
from typing import List, Dict, Any, Optional
from .base_adapter import SourceAdapter

logger = logging.getLogger(__name__)


class HttpApiAdapter(SourceAdapter):
    """Adapter for HTTP API sources (LinkedIn, Apollo, etc.)"""
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test API connection"""
        try:
            http_config = self.config.get('http_config', {})
            
            if not http_config.get('url'):
                return {
                    'success': False,
                    'message': 'No API URL configured'
                }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Try a simple request
                response = await client.request(
                    method=http_config.get('method', 'GET'),
                    url=http_config['url'],
                    headers=self._get_headers(),
                )
                
                success = 200 <= response.status_code < 400
                
                return {
                    'success': success,
                    'message': f'Connection {"successful" if success else "failed"}',
                    'status_code': response.status_code,
                    'details': {
                        'url': http_config['url'],
                        'method': http_config.get('method', 'GET')
                    }
                }
                
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return {
                'success': False,
                'message': f'Connection failed: {str(e)}'
            }
    
    async def fetch(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch data from HTTP API with pagination"""
        all_data = []
        page = 1
        
        http_config = self.config.get('http_config', {})
        pagination_config = http_config.get('pagination', {})
        
        max_pages = pagination_config.get('max_pages', 1)
        per_page = pagination_config.get('per_page', 100)
        
        # Calculate max pages based on limit
        if limit:
            max_pages = min(max_pages, (limit // per_page) + 1)
        
        logger.info(f"Fetching up to {max_pages} pages")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            while page <= max_pages:
                try:
                    # Rate limiting (wait between requests)
                    if page > 1:
                        await self._rate_limit()
                    
                    logger.info(f"Fetching page {page}/{max_pages}")
                    
                    # Make request
                    data = await self._fetch_page(client, page)
                    
                    if not data:
                        logger.info("No more data returned, stopping")
                        break
                    
                    all_data.extend(data)
                    logger.info(f"Got {len(data)} items from page {page}")
                    
                    # Check limit
                    if limit and len(all_data) >= limit:
                        all_data = all_data[:limit]
                        logger.info(f"Reached limit of {limit} items")
                        break
                    
                    # Check if we should continue
                    if len(data) < per_page:
                        logger.info("Got fewer items than per_page, stopping")
                        break
                    
                    page += 1
                    
                except Exception as e:
                    logger.error(f"Error fetching page {page}: {e}")
                    self.stats['errors'] += 1
                    self.stats['error_details'].append({
                        'page': page,
                        'error': str(e)
                    })
                    break
        
        logger.info(f"Total items fetched: {len(all_data)}")
        return all_data
    
    async def _fetch_page(self, client: httpx.AsyncClient, page: int) -> List[Dict]:
        """Fetch single page of results"""
        http_config = self.config.get('http_config', {})
        method = http_config.get('method', 'GET')
        
        # Build request data
        request_data = self._build_request_data(page)
        
        # Make request
        if method == 'GET':
            response = await client.get(
                url=http_config['url'],
                headers=self._get_headers(),
                params=request_data,
            )
        else:
            response = await client.request(
                method=method,
                url=http_config['url'],
                headers=self._get_headers(),
                json=request_data,
            )
        
        # Handle errors
        if response.status_code == 429:
            logger.warning("Rate limit hit (429), waiting...")
            await asyncio.sleep(60)  # Wait 1 minute
            return await self._fetch_page(client, page)  # Retry
        
        response.raise_for_status()
        
        # Extract data from response
        data = response.json()
        return self._extract_items(data)
    
    def _build_request_data(self, page: int) -> Dict[str, Any]:
        """Build request parameters/body with pagination"""
        http_config = self.config.get('http_config', {})
        pagination_config = http_config.get('pagination', {})
        
        # Start with base params
        if http_config.get('method', 'GET') == 'GET':
            data = http_config.get('query_params', {}).copy()
        else:
            data = http_config.get('body_template', {}).copy()
        
        # Add pagination parameters
        pagination_type = pagination_config.get('type', 'page_based')
        
        if pagination_type == 'page_based':
            page_param = pagination_config.get('page_param', 'page')
            data[page_param] = page
            
            per_page_param = pagination_config.get('per_page_param', 'per_page')
            data[per_page_param] = pagination_config.get('per_page', 100)
        
        elif pagination_type == 'offset_based':
            per_page = pagination_config.get('per_page', 100)
            offset = (page - 1) * per_page
            
            offset_param = pagination_config.get('offset_param', 'offset')
            limit_param = pagination_config.get('limit_param', 'limit')
            
            data[offset_param] = offset
            data[limit_param] = per_page
        
        elif pagination_type == 'cursor_based':
            # For cursor-based pagination, cursor is stored from previous response
            if page > 1 and hasattr(self, '_next_cursor'):
                cursor_param = pagination_config.get('cursor_param', 'cursor')
                data[cursor_param] = self._next_cursor
        
        return data
    
    def _get_headers(self) -> Dict[str, str]:
        """Build request headers with authentication"""
        http_config = self.config.get('http_config', {})
        headers = http_config.get('headers', {}).copy()
        
        # Add authentication
        auth_type = http_config.get('auth_type')
        variables = self.config.get('variables', {})
        
        if auth_type == 'bearer':
            api_key = variables.get('api_key') or variables.get('token')
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
        
        elif auth_type == 'api_key':
            api_key = variables.get('api_key')
            key_name = http_config.get('api_key_header', 'X-API-Key')
            if api_key:
                headers[key_name] = api_key
        
        elif auth_type == 'basic':
            username = variables.get('username')
            password = variables.get('password')
            if username and password:
                import base64
                credentials = base64.b64encode(f'{username}:{password}'.encode()).decode()
                headers['Authorization'] = f'Basic {credentials}'
        
        return headers
    
    def _extract_items(self, response_data: Dict) -> List[Dict]:
        """Extract items array from API response"""
        http_config = self.config.get('http_config', {})
        response_path = http_config.get('response_path', 'data')
        
        if not response_path:
            # Response itself is the array
            return response_data if isinstance(response_data, list) else [response_data]
        
        # Navigate nested path (e.g., "data.results")
        current = response_data
        for key in response_path.split('.'):
            if isinstance(current, dict):
                current = current.get(key, [])
            else:
                break
        
        # Handle cursor-based pagination
        pagination_config = http_config.get('pagination', {})
        if pagination_config.get('type') == 'cursor_based':
            cursor_path = pagination_config.get('next_cursor_path', 'paging.next')
            self._next_cursor = self._get_nested_value(response_data, cursor_path)
        
        return current if isinstance(current, list) else [current]
    
    async def _rate_limit(self):
        """Apply rate limiting between requests"""
        http_config = self.config.get('http_config', {})
        rate_limit = http_config.get('rate_limit', {})
        
        # Default: 60 requests per minute
        rpm = rate_limit.get('requests_per_minute', 60)
        delay = 60.0 / rpm
        
        await asyncio.sleep(delay)
    
    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Configuration schema for HTTP API"""
        return {
            'type': 'object',
            'required': ['url', 'method'],
            'properties': {
                'url': {
                    'type': 'string',
                    'title': 'API Endpoint URL',
                    'description': 'Full API endpoint URL'
                },
                'method': {
                    'type': 'string',
                    'title': 'HTTP Method',
                    'enum': ['GET', 'POST', 'PUT'],
                    'default': 'GET'
                },
                'auth_type': {
                    'type': 'string',
                    'title': 'Authentication Type',
                    'enum': ['bearer', 'api_key', 'basic', 'none'],
                    'default': 'bearer'
                },
                'headers': {
                    'type': 'object',
                    'title': 'HTTP Headers',
                    'description': 'Additional headers to include'
                },
                'query_params': {
                    'type': 'object',
                    'title': 'Query Parameters',
                    'description': 'For GET requests'
                },
                'body_template': {
                    'type': 'object',
                    'title': 'Request Body Template',
                    'description': 'For POST requests'
                },
                'response_path': {
                    'type': 'string',
                    'title': 'Response Data Path',
                    'description': 'JSON path to data array (e.g., "data.results")',
                    'default': 'data'
                },
                'pagination': {
                    'type': 'object',
                    'properties': {
                        'type': {
                            'type': 'string',
                            'enum': ['page_based', 'offset_based', 'cursor_based'],
                            'default': 'page_based'
                        },
                        'page_param': {'type': 'string', 'default': 'page'},
                        'per_page_param': {'type': 'string', 'default': 'per_page'},
                        'per_page': {'type': 'integer', 'default': 100},
                        'max_pages': {'type': 'integer', 'default': 5}
                    }
                },
                'rate_limit': {
                    'type': 'object',
                    'properties': {
                        'requests_per_minute': {'type': 'integer', 'default': 60}
                    }
                }
            }
        }
    
    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """Default HTTP API configuration"""
        return {
            'http_config': {
                'method': 'GET',
                'auth_type': 'bearer',
                'response_path': 'data',
                'headers': {
                    'Content-Type': 'application/json'
                },
                'pagination': {
                    'type': 'page_based',
                    'page_param': 'page',
                    'per_page_param': 'per_page',
                    'per_page': 100,
                    'max_pages': 5
                },
                'rate_limit': {
                    'requests_per_minute': 60
                }
            }
        }