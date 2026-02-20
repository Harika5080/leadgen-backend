"""Export services for integrating with campaign platforms."""

import logging
import csv
import io
from typing import List, Dict, Any, Optional
from datetime import datetime
import aiohttp
import pandas as pd

from app.config import settings

logger = logging.getLogger(__name__)


class InstantlyExporter:
    """Export leads to Instantly.ai platform."""
    
    BASE_URL = "https://api.instantly.ai/api/v1"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def export_leads(
        self,
        leads: List[Dict[str, Any]],
        campaign_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Export leads to Instantly.ai via API.
        
        Args:
            leads: List of lead dictionaries
            campaign_id: Optional campaign ID to add leads to
        
        Returns:
            Export result with success/failure counts
        """
        if not leads:
            return {"success": 0, "failed": 0, "errors": []}
        
        # Transform leads to Instantly.ai format
        instantly_leads = []
        for lead in leads:
            instantly_lead = {
                "email": lead.get("email"),
                "first_name": lead.get("first_name"),
                "last_name": lead.get("last_name"),
                "company_name": lead.get("company", {}).get("name") if isinstance(lead.get("company"), dict) else None,
                "website": lead.get("company", {}).get("website") if isinstance(lead.get("company"), dict) else None,
                "personalization": {},
                "variables": {
                    "job_title": lead.get("job_title"),
                    "phone": lead.get("phone"),
                    "linkedin_url": lead.get("linkedin_url"),
                }
            }
            instantly_leads.append(instantly_lead)
        
        # Split into batches of 100 (Instantly.ai limit)
        batch_size = 100
        results = {"success": 0, "failed": 0, "errors": []}
        
        for i in range(0, len(instantly_leads), batch_size):
            batch = instantly_leads[i:i+batch_size]
            
            payload = {
                "leads": batch
            }
            
            if campaign_id:
                payload["campaign_id"] = campaign_id
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.BASE_URL}/lead/add",
                        headers=self.headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            results["success"] += len(batch)
                            logger.info(f"Successfully exported {len(batch)} leads to Instantly.ai")
                        else:
                            error_text = await response.text()
                            results["failed"] += len(batch)
                            results["errors"].append({
                                "batch": i // batch_size,
                                "error": error_text
                            })
                            logger.error(f"Instantly.ai export failed: {error_text}")
            
            except Exception as e:
                results["failed"] += len(batch)
                results["errors"].append({
                    "batch": i // batch_size,
                    "error": str(e)
                })
                logger.error(f"Instantly.ai export error: {str(e)}")
        
        return results
    
    def generate_csv(self, leads: List[Dict[str, Any]]) -> str:
        """
        Generate CSV file for Instantly.ai upload.
        
        Args:
            leads: List of lead dictionaries
        
        Returns:
            CSV content as string
        """
        output = io.StringIO()
        
        fieldnames = [
            "Email",
            "First Name",
            "Last Name",
            "Company Name",
            "Website",
            "Job Title",
            "Phone",
            "LinkedIn URL",
            "Custom Field 1"
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        
        for lead in leads:
            row = {
                "Email": lead.get("email", ""),
                "First Name": lead.get("first_name", ""),
                "Last Name": lead.get("last_name", ""),
                "Company Name": lead.get("company", {}).get("name", "") if isinstance(lead.get("company"), dict) else "",
                "Website": lead.get("company", {}).get("website", "") if isinstance(lead.get("company"), dict) else "",
                "Job Title": lead.get("job_title", ""),
                "Phone": lead.get("phone", ""),
                "LinkedIn URL": lead.get("linkedin_url", ""),
                "Custom Field 1": lead.get("metadata", {}).get("custom1", "") if isinstance(lead.get("metadata"), dict) else ""
            }
            writer.writerow(row)
        
        return output.getvalue()


class SmartleadExporter:
    """Export leads to Smartlead.ai platform."""
    
    BASE_URL = "https://server.smartlead.ai/api/v1"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def export_leads(
        self,
        leads: List[Dict[str, Any]],
        campaign_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Export leads to Smartlead.ai via API.
        
        Args:
            leads: List of lead dictionaries
            campaign_id: Optional campaign ID
        
        Returns:
            Export result with success/failure counts
        """
        if not leads:
            return {"success": 0, "failed": 0, "errors": []}
        
        # Transform leads to Smartlead format
        smartlead_leads = []
        for lead in leads:
            smartlead_lead = {
                "email": lead.get("email"),
                "first_name": lead.get("first_name"),
                "last_name": lead.get("last_name"),
                "company_name": lead.get("company", {}).get("name") if isinstance(lead.get("company"), dict) else None,
                "title": lead.get("job_title"),
                "phone": lead.get("phone"),
                "website": lead.get("company", {}).get("website") if isinstance(lead.get("company"), dict) else None,
                "linkedin": lead.get("linkedin_url"),
                "custom_fields": lead.get("metadata", {}) if isinstance(lead.get("metadata"), dict) else {}
            }
            smartlead_leads.append(smartlead_lead)
        
        # Split into batches of 50 (Smartlead limit)
        batch_size = 50
        results = {"success": 0, "failed": 0, "errors": []}
        
        for i in range(0, len(smartlead_leads), batch_size):
            batch = smartlead_leads[i:i+batch_size]
            
            payload = {
                "lead_list": batch
            }
            
            if campaign_id:
                payload["campaign_id"] = campaign_id
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.BASE_URL}/campaigns/leads",
                        headers=self.headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status in [200, 201]:
                            result = await response.json()
                            results["success"] += len(batch)
                            logger.info(f"Successfully exported {len(batch)} leads to Smartlead.ai")
                        else:
                            error_text = await response.text()
                            results["failed"] += len(batch)
                            results["errors"].append({
                                "batch": i // batch_size,
                                "error": error_text
                            })
                            logger.error(f"Smartlead.ai export failed: {error_text}")
            
            except Exception as e:
                results["failed"] += len(batch)
                results["errors"].append({
                    "batch": i // batch_size,
                    "error": str(e)
                })
                logger.error(f"Smartlead.ai export error: {str(e)}")
        
        return results
    
    def generate_csv(self, leads: List[Dict[str, Any]]) -> str:
        """
        Generate CSV file for Smartlead.ai upload.
        
        Args:
            leads: List of lead dictionaries
        
        Returns:
            CSV content as string
        """
        output = io.StringIO()
        
        fieldnames = [
            "Email",
            "First Name",
            "Last Name",
            "Company",
            "Title",
            "Phone",
            "Website",
            "LinkedIn"
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        
        for lead in leads:
            row = {
                "Email": lead.get("email", ""),
                "First Name": lead.get("first_name", ""),
                "Last Name": lead.get("last_name", ""),
                "Company": lead.get("company", {}).get("name", "") if isinstance(lead.get("company"), dict) else "",
                "Title": lead.get("job_title", ""),
                "Phone": lead.get("phone", ""),
                "Website": lead.get("company", {}).get("website", "") if isinstance(lead.get("company"), dict) else "",
                "LinkedIn": lead.get("linkedin_url", "")
            }
            writer.writerow(row)
        
        return output.getvalue()


class GenericCSVExporter:
    """Generate generic CSV exports with configurable columns."""
    
    DEFAULT_COLUMNS = [
        "email",
        "first_name",
        "last_name",
        "job_title",
        "phone",
        "company_name",
        "company_website",
        "linkedin_url",
        "lead_fit_score",
        "lead_status",
        "acquisition_timestamp"
    ]
    
    def generate_csv(
        self,
        leads: List[Dict[str, Any]],
        columns: Optional[List[str]] = None
    ) -> str:
        """
        Generate generic CSV file.
        
        Args:
            leads: List of lead dictionaries
            columns: Optional list of column names to include
        
        Returns:
            CSV content as string
        """
        if columns is None:
            columns = self.DEFAULT_COLUMNS
        
        output = io.StringIO()
        
        # Convert to pandas DataFrame for easier manipulation
        df_data = []
        for lead in leads:
            row = {}
            for col in columns:
                if col == "company_name":
                    row[col] = lead.get("company", {}).get("name", "") if isinstance(lead.get("company"), dict) else ""
                elif col == "company_website":
                    row[col] = lead.get("company", {}).get("website", "") if isinstance(lead.get("company"), dict) else ""
                elif col == "acquisition_timestamp":
                    ts = lead.get("acquisition_timestamp")
                    if ts:
                        if isinstance(ts, str):
                            row[col] = ts
                        else:
                            row[col] = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
                    else:
                        row[col] = ""
                else:
                    row[col] = lead.get(col, "")
            df_data.append(row)
        
        df = pd.DataFrame(df_data, columns=columns)
        
        # Write to CSV
        df.to_csv(output, index=False, quoting=csv.QUOTE_ALL)
        
        return output.getvalue()


class ExportService:
    """Main export service coordinating different exporters."""
    
    def __init__(self):
        self.instantly = None
        self.smartlead = None
        self.generic = GenericCSVExporter()
    
    def set_instantly_credentials(self, api_key: str):
        """Set Instantly.ai API credentials."""
        self.instantly = InstantlyExporter(api_key)
    
    def set_smartlead_credentials(self, api_key: str):
        """Set Smartlead.ai API credentials."""
        self.smartlead = SmartleadExporter(api_key)
    
    async def export(
        self,
        leads: List[Dict[str, Any]],
        destination: str,
        method: str = "csv",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Export leads to specified destination.
        
        Args:
            leads: List of lead dictionaries
            destination: Export destination ('instantly', 'smartlead', 'csv')
            method: Export method ('api' or 'csv')
            **kwargs: Additional parameters (campaign_id, columns, etc.)
        
        Returns:
            Export result dictionary
        """
        if not leads:
            return {"success": False, "error": "No leads to export"}
        
        try:
            if destination == "instantly":
                if method == "api":
                    if not self.instantly:
                        return {"success": False, "error": "Instantly.ai credentials not set"}
                    result = await self.instantly.export_leads(
                        leads,
                        campaign_id=kwargs.get("campaign_id")
                    )
                    return {"success": True, "result": result}
                else:  # csv
                    if not self.instantly:
                        self.instantly = InstantlyExporter("")
                    csv_content = self.instantly.generate_csv(leads)
                    return {"success": True, "csv": csv_content}
            
            elif destination == "smartlead":
                if method == "api":
                    if not self.smartlead:
                        return {"success": False, "error": "Smartlead.ai credentials not set"}
                    result = await self.smartlead.export_leads(
                        leads,
                        campaign_id=kwargs.get("campaign_id")
                    )
                    return {"success": True, "result": result}
                else:  # csv
                    if not self.smartlead:
                        self.smartlead = SmartleadExporter("")
                    csv_content = self.smartlead.generate_csv(leads)
                    return {"success": True, "csv": csv_content}
            
            elif destination == "csv":
                csv_content = self.generic.generate_csv(
                    leads,
                    columns=kwargs.get("columns")
                )
                return {"success": True, "csv": csv_content}
            
            else:
                return {"success": False, "error": f"Unknown destination: {destination}"}
        
        except Exception as e:
            logger.error(f"Export error: {str(e)}")
            return {"success": False, "error": str(e)}


# Singleton instance
export_service = ExportService()