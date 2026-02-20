"""
Generic HTTP adapter that can call any REST API.
Configuration-driven - no code changes needed for new APIs.
"""
import httpx
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from jsonpath_ng import parse as jsonpath_parse
from .base import DataSourceAdapter


class HTTPAdapter(DataSourceAdapter):
    """
    Universal HTTP adapter for any REST API.
    All configuration comes from database.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.http_config = config.get("http_config", {})
        self.variables = config.get("variables", {})
        self.field_mappings = config.get("field_mappings", {})
    
    def _render_template(self, template: Any, variables: Dict[str, Any]) -> Any:
        """
        Render template with variable substitution.
        Supports: {{variable_name}}
        
        Examples:
            "{{api_key}}" -> "actual_key_123"
            ["{{title1}}", "{{title2}}"] -> ["VP", "Director"]
        """
        if isinstance(template, str):
            # Replace {{var}} with actual value
            def replace_var(match):
                var_name = match.group(1)
                return str(variables.get(var_name, f"{{{{var_name}}}}"))
            
            return re.sub(r'\{\{(\w+)\}\}', replace_var, template)
        
        elif isinstance(template, list):
            return [self._render_template(item, variables) for item in template]
        
        elif isinstance(template, dict):
            return {
                key: self._render_template(value, variables)
                for key, value in template.items()
            }
        
        else:
            return template
    
    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers with auth."""
        headers = self.http_config.get("headers", {})
        headers = self._render_template(headers, self.variables)
        
        # Handle auth
        auth_type = self.http_config.get("auth_type")
        auth_config = self.http_config.get("auth_config", {})
        
        if auth_type == "bearer":
            token = self._render_template(auth_config.get("token"), self.variables)
            headers["Authorization"] = f"Bearer {token}"
        
        elif auth_type == "basic":
            # Basic auth handled by httpx
            pass
        
        return headers
    
    def _build_url(self) -> str:
        """Build complete URL."""
        base_url = self.http_config.get("base_url", "")
        endpoint = self.http_config.get("endpoint", "")
        
        base_url = self._render_template(base_url, self.variables)
        endpoint = self._render_template(endpoint, self.variables)
        
        return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    
    def _build_params(self, page: int = 1) -> Dict[str, Any]:
        """Build query parameters."""
        params = self.http_config.get("query_params", {})
        params = self._render_template(params, self.variables)
        
        # Handle pagination
        pagination = self.http_config.get("pagination", {})
        if pagination.get("type") == "page":
            page_param = pagination.get("page_param", "page")
            params[page_param] = page
        elif pagination.get("type") == "offset":
            limit_param = pagination.get("limit_param", "limit")
            offset_param = pagination.get("offset_param", "offset")
            limit = params.get(limit_param, 100)
            params[offset_param] = (page - 1) * limit
        
        return params
    
    def _build_body(self) -> Dict[str, Any]:
        """Build request body."""
        body = self.http_config.get("request_body", {})
        return self._render_template(body, self.variables)
    
    def _extract_value(self, data: Dict, path: str) -> Any:
        """
        Extract value from nested dict using dot notation.
        
        Examples:
            path="email" -> data["email"]
            path="organization.name" -> data["organization"]["name"]
            path="phones[0].number" -> data["phones"][0]["number"]
        """
        try:
            # Simple implementation (can be enhanced with jsonpath_ng)
            keys = path.split(".")
            value = data
            for key in keys:
                if "[" in key:
                    # Handle array indexing
                    key_name, index = key.replace("]", "").split("[")
                    value = value[key_name][int(index)]
                else:
                    value = value[key]
            return value
        except (KeyError, IndexError, TypeError):
            return None
    
    async def test_connection(self) -> bool:
        """Test API connection."""
        try:
            url = self._build_url()
            headers = self._build_headers()
            params = self._build_params(page=1)
            method = self.http_config.get("method", "GET").upper()
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method == "POST":
                    body = self._build_body()
                    response = await client.post(url, headers=headers, json=body, params=params)
                else:
                    return False
                
                return response.status_code in [200, 201]
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
    
    async def fetch_leads(
        self,
        limit: Optional[int] = None,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Fetch leads from API."""
        
        all_leads = []
        page = 1
        max_pages = self.http_config.get("pagination", {}).get("max_pages", 10)
        
        url = self._build_url()
        headers = self._build_headers()
        method = self.http_config.get("method", "GET").upper()
        
        while page <= max_pages:
            params = self._build_params(page)
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    if method == "GET":
                        response = await client.get(url, headers=headers, params=params)
                    elif method == "POST":
                        body = self._build_body()
                        # Update body with pagination if needed
                        pagination = self.http_config.get("pagination", {})
                        if pagination.get("type") == "body":
                            body[pagination.get("page_param", "page")] = page
                        
                        response = await client.post(url, headers=headers, json=body, params=params)
                    else:
                        break
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # Extract results using response_path
                    response_path = self.http_config.get("response_path", "")
                    if response_path:
                        results = self._extract_value(data, response_path)
                    else:
                        results = data if isinstance(data, list) else [data]
                    
                    if not results:
                        break
                    
                    # Map fields
                    for item in results:
                        mapped_lead = {}
                        for target_field, source_path in self.field_mappings.items():
                            mapped_lead[target_field] = self._extract_value(item, source_path)
                        
                        all_leads.append(mapped_lead)
                    
                    # Check if we have enough
                    if limit and len(all_leads) >= limit:
                        break
                    
                    # Check if there are more pages
                    pagination_config = self.http_config.get("pagination", {})
                    if not pagination_config or len(results) < params.get(pagination_config.get("limit_param", "per_page"), 100):
                        break
                    
                    page += 1
                
                except Exception as e:
                    print(f"Error fetching page {page}: {e}")
                    break
        
        return all_leads[:limit] if limit else all_leads
    
    def get_field_schema(self) -> Dict[str, str]:
        """Return available fields based on field_mappings."""
        return {field: "string" for field in self.field_mappings.keys()}
    
    def validate_config(self) -> List[str]:
        """Validate HTTP configuration."""
        errors = super().validate_config()
        
        if not self.http_config.get("base_url"):
            errors.append("http_config.base_url is required")
        
        if not self.http_config.get("endpoint"):
            errors.append("http_config.endpoint is required")
        
        if not self.http_config.get("method"):
            errors.append("http_config.method is required (GET, POST, etc.)")
        
        # Check required variables
        required_vars = self.http_config.get("required_variables", [])
        for var in required_vars:
            if var not in self.variables:
                errors.append(f"Required variable '{var}' is missing")
        
        return errors