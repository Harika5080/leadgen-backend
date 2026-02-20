"""Instantly.ai API v2 integration - Official implementation based on developer.instantly.ai/api/v2/"""

import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal

from app.models import Lead
from app.config import settings

logger = logging.getLogger(__name__)


def decimal_to_float(value: Any) -> Any:
    """Convert Decimal to float for JSON serialization."""
    if isinstance(value, Decimal):
        return float(value)
    return value


class InstantlyAIService:
    """Service for exporting leads to Instantly.ai using official API v2."""
    
    # Official base URL
    BASE_URL = "https://api.instantly.ai/api/v2"
    
    def __init__(self, api_key: str):
        """Initialize with API key using Bearer token authentication."""
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test API connection by getting workspace info."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/workspaces/current",
                    headers=self.headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "workspace": response.json()
                    }
                else:
                    return {
                        "success": False,
                        "error": f"API returned {response.status_code}",
                        "details": response.text
                    }
        except Exception as e:
            logger.error(f"Instantly.ai connection test failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def list_campaigns(
        self,
        status: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """List all available campaigns.
        
        Args:
            status: Filter by status (ACTIVE, PAUSED, COMPLETED, DRAFTED)
            limit: Number of campaigns to return (default 50)
        """
        try:
            params = {"limit": limit}
            if status:
                params["status"] = status
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/campaigns",
                    headers=self.headers,
                    params=params,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "campaigns": data.get("items", []),
                        "next_starting_after": data.get("next_starting_after")
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to fetch campaigns: {response.status_code}",
                        "details": response.text
                    }
        except Exception as e:
            logger.error(f"Failed to list campaigns: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Get detailed campaign information.
        
        Args:
            campaign_id: Campaign UUID
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/campaigns/{campaign_id}",
                    headers=self.headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "campaign": response.json()
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to fetch campaign: {response.status_code}",
                        "details": response.text
                    }
        except Exception as e:
            logger.error(f"Failed to get campaign: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def transform_lead_to_instantly(self, lead: Lead, campaign_id: str = None) -> Dict[str, Any]:
        """Transform lead model to Instantly.ai v2 format.
        
        Custom variables must be string, number, boolean, or null.
        NO objects or arrays allowed.
        
        Args:
            lead: Lead model instance
            campaign_id: Optional campaign ID to add to lead
        """
        
        # Build lead data
        lead_data = {
            "email": lead.email,
        }
        
        # Add campaign if provided
        if campaign_id:
            lead_data["campaign"] = campaign_id  # Note: field is 'campaign' not 'campaign_id'
        
        # Add optional core fields
        if lead.first_name:
            lead_data["first_name"] = lead.first_name
        
        if lead.last_name:
            lead_data["last_name"] = lead.last_name
        
        if lead.company_name:
            lead_data["company_name"] = lead.company_name
        
        if lead.phone:
            lead_data["phone"] = lead.phone
        
        # Custom variables - only string, number, boolean, or null
        custom_variables = {}
        
        if lead.job_title:
            custom_variables["job_title"] = lead.job_title
        
        if lead.company_website:
            custom_variables["website"] = lead.company_website
        
        if lead.company_industry:
            custom_variables["industry"] = lead.company_industry
        
        if lead.company_domain:
            custom_variables["domain"] = lead.company_domain
        
        if lead.linkedin_url:
            custom_variables["linkedin"] = lead.linkedin_url
        
        if lead.fit_score is not None:
            # Convert Decimal to float, then to percentage
            try:
                score_value = decimal_to_float(lead.fit_score)
                custom_variables["fit_score"] = round(score_value * 100, 1)
            except (TypeError, ValueError) as e:
                logger.warning(f"Could not convert fit_score for lead {lead.email}: {e}")
        
        if lead.email_deliverability_score is not None:
            # Convert Decimal to float, then to percentage
            try:
                deliverability_value = decimal_to_float(lead.email_deliverability_score)
                custom_variables["deliverability"] = round(deliverability_value * 100, 1)
            except (TypeError, ValueError) as e:
                logger.warning(f"Could not convert deliverability_score for lead {lead.email}: {e}")
        
        if lead.source_name:
            custom_variables["source"] = lead.source_name
        
        if lead.status:
            custom_variables["status"] = lead.status
        
        # Email verification flag
        if lead.email_verified:
            custom_variables["email_verified"] = True
        
        if custom_variables:
            lead_data["custom_variables"] = custom_variables
        
        return lead_data
    
    async def add_leads_to_campaign(
        self,
        campaign_id: str,
        leads: List[Lead],
        skip_if_in_workspace: bool = True
    ) -> Dict[str, Any]:
        """Add multiple leads to a campaign.
        
        Args:
            campaign_id: Target campaign UUID
            leads: List of Lead model instances
            skip_if_in_workspace: Skip if lead exists in any campaign (default True)
        
        Returns:
            Dict with success status and results
        """
        
        try:
            # Transform all leads with campaign_id embedded
            formatted_leads = []
            for lead in leads:
                try:
                    lead_data = self.transform_lead_to_instantly(lead, campaign_id)
                    # Add skip flags to each lead
                    lead_data["skip_if_in_workspace"] = skip_if_in_workspace
                    lead_data["skip_if_in_campaign"] = True  # Also skip if in campaign
                    formatted_leads.append(lead_data)
                except Exception as e:
                    logger.error(f"Error transforming lead {lead.email}: {str(e)}")
                    raise
            
            # For v2 API, we send leads array directly, not wrapped in a payload
            # Each lead has campaign, skip flags, and custom_variables embedded
            
            # Debug: Log payload structure
            logger.info(f"Exporting {len(formatted_leads)} leads to campaign {campaign_id}")
            logger.info(f"First lead structure: {formatted_leads[0] if formatted_leads else 'N/A'}")
            
            async with httpx.AsyncClient() as client:
                try:
                    # V2 API: Send each lead individually
                    added = 0
                    skipped = 0
                    failed = 0
                    errors = []
                    
                    for lead_data in formatted_leads:
                        try:
                            response = await client.post(
                                f"{self.BASE_URL}/leads",
                                headers=self.headers,
                                json=lead_data,
                                timeout=30.0
                            )
                            
                            if response.status_code in [200, 201]:
                                added += 1
                            elif response.status_code == 400:
                                # Might be duplicate
                                error_text = response.text
                                if 'already' in error_text.lower() or 'duplicate' in error_text.lower():
                                    skipped += 1
                                else:
                                    failed += 1
                                    errors.append(f"{lead_data['email']}: {error_text[:100]}")
                                    logger.warning(f"Failed to add lead {lead_data['email']}: {error_text}")
                            else:
                                failed += 1
                                errors.append(f"{lead_data['email']}: HTTP {response.status_code}")
                                logger.error(f"Failed to add lead {lead_data['email']}: {response.status_code} - {response.text}")
                        
                        except Exception as e:
                            failed += 1
                            errors.append(f"{lead_data['email']}: {str(e)}")
                            logger.error(f"Exception adding lead {lead_data['email']}: {str(e)}")
                    
                    # Return summary
                    return {
                        "success": failed == 0,
                        "total": len(leads),
                        "added": added,
                        "skipped": skipped,
                        "failed": failed,
                        "errors": errors[:10],  # Limit to first 10 errors
                        "message": f"Added {added}, skipped {skipped}, failed {failed} out of {len(leads)} leads"
                    }
                
                except TypeError as e:
                    # JSON serialization error
                    logger.error(f"JSON serialization error: {str(e)}")
                    logger.error(f"First lead sample: {formatted_leads[0] if formatted_leads else 'N/A'}")
                    raise ValueError(f"Failed to serialize lead data to JSON: {str(e)}")
        
        except Exception as e:
            logger.error(f"Error adding leads to Instantly.ai: {str(e)}")
            return {
                "success": False,
                "total": len(leads),
                "error": str(e)
            }
    
    async def get_background_job_status(self, job_id: str) -> Dict[str, Any]:
        """Check status of a background job (like bulk lead import).
        
        Args:
            job_id: Background job UUID
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/background-jobs/{job_id}",
                    headers=self.headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    job = response.json()
                    return {
                        "success": True,
                        "job": job,
                        "status": job.get("status"),  # pending, completed, failed
                        "progress": job.get("progress"),
                        "result": job.get("result")
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to get job status: {response.status_code}"
                    }
        except Exception as e:
            logger.error(f"Failed to get job status: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_campaign_analytics(
        self,
        campaign_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get analytics for campaigns.
        
        Args:
            campaign_id: Optional specific campaign UUID
        """
        try:
            params = {}
            if campaign_id:
                params["campaign_id"] = campaign_id
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/campaigns/analytics",
                    headers=self.headers,
                    params=params,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "analytics": response.json()
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to fetch analytics: {response.status_code}"
                    }
        except Exception as e:
            logger.error(f"Failed to get analytics: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def pause_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Pause a campaign.
        
        Args:
            campaign_id: Campaign UUID
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/campaigns/{campaign_id}/pause",
                    headers=self.headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": "Campaign paused successfully"
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to pause campaign: {response.status_code}"
                    }
        except Exception as e:
            logger.error(f"Failed to pause campaign: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def activate_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Activate a campaign.
        
        Args:
            campaign_id: Campaign UUID
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/campaigns/{campaign_id}/activate",
                    headers=self.headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": "Campaign activated successfully"
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to activate campaign: {response.status_code}"
                    }
        except Exception as e:
            logger.error(f"Failed to activate campaign: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def list_leads(
        self,
        campaign_id: Optional[str] = None,
        list_id: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """List leads (POST endpoint due to complex filters).
        
        Args:
            campaign_id: Filter by campaign UUID
            list_id: Filter by list UUID
            limit: Number of leads to return
        """
        try:
            payload = {"limit": limit}
            
            if campaign_id:
                payload["campaign_id"] = campaign_id
            
            if list_id:
                payload["list_id"] = list_id
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/leads/list",
                    headers=self.headers,
                    json=payload,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "leads": data.get("items", []),
                        "next_starting_after": data.get("next_starting_after")
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to list leads: {response.status_code}"
                    }
        except Exception as e:
            logger.error(f"Failed to list leads: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def delete_leads(
        self,
        campaign_id: Optional[str] = None,
        list_id: Optional[str] = None,
        lead_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Delete leads from campaign or list.
        
        Args:
            campaign_id: Campaign to delete from
            list_id: List to delete from
            lead_ids: Specific lead IDs to delete
        """
        try:
            payload = {}
            
            if campaign_id:
                payload["campaign_id"] = campaign_id
            
            if list_id:
                payload["list_id"] = list_id
            
            if lead_ids:
                payload["ids"] = lead_ids
            
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    "DELETE",
                    f"{self.BASE_URL}/leads",
                    headers=self.headers,
                    json=payload,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return {
                        "success": True,
                        "deleted": result.get("deleted", 0),
                        "message": "Leads deleted successfully"
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to delete leads: {response.status_code}"
                    }
        except Exception as e:
            logger.error(f"Failed to delete leads: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }


def get_instantly_service(api_key: Optional[str] = None) -> InstantlyAIService:
    """Get Instantly.ai service instance.
    
    Args:
        api_key: Instantly.ai API key (Bearer token)
    """
    key = api_key or settings.INSTANTLY_API_KEY
    if not key:
        raise ValueError("Instantly.ai API key not configured")
    return InstantlyAIService(key)