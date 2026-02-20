"""
Pydantic schemas for raw leads
"""

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime


class RawLeadCreate(BaseModel):
    """Single raw lead data from scraper"""
    email: EmailStr
    scraped_data: Dict[str, Any]
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "john.doe@techcorp.com",
                "first_name": "John",
                "last_name": "Doe",
                "job_title": "VP of Engineering",
                "company_name": "TechCorp Inc",
                "scraped_data": {
                    "source_page": "https://linkedin.com/in/johndoe",
                    "profile_url": "https://linkedin.com/in/johndoe",
                    "headline": "VP of Engineering at TechCorp",
                    "location": "San Francisco, CA",
                    "connections": "500+",
                    "raw_html_snippet": "<div>...</div>"
                }
            }
        }


class RawLeadBatch(BaseModel):
    """Batch upload of raw leads"""
    icp_id: UUID
    source_name: str
    source_url: Optional[str] = None
    scraper_type: str = Field(..., description="Type of scraper: crawlee, puppeteer, nutch, pyspider, manual, api, csv")
    leads: List[RawLeadCreate]
    metadata: Optional[Dict[str, Any]] = {}
    
    @validator('scraper_type')
    def validate_scraper_type(cls, v):
        valid_types = ['crawlee', 'puppeteer', 'nutch', 'pyspider', 'manual', 'api', 'csv']
        if v.lower() not in valid_types:
            raise ValueError(f'scraper_type must be one of: {", ".join(valid_types)}')
        return v.lower()
    
    @validator('leads')
    def validate_leads_not_empty(cls, v):
        if len(v) == 0:
            raise ValueError('leads list cannot be empty')
        if len(v) > 1000:
            raise ValueError('Maximum 1000 leads per batch')
        return v


class RawLeadResponse(BaseModel):
    """Response model for a single raw lead"""
    id: UUID
    tenant_id: UUID
    icp_id: UUID
    source_name: str
    source_url: Optional[str]
    scraper_type: str
    
    # Extracted fields
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    job_title: Optional[str]
    company_name: Optional[str]
    
    # Full scraped data
    scraped_data: Dict[str, Any]
    
    # Status tracking
    processing_status: str
    error_message: Optional[str]
    retry_count: int
    
    # Timestamps
    created_at: datetime
    processed_at: Optional[datetime]
    
    # Related lead ID (after processing)
    lead_id: Optional[UUID]
    
    class Config:
        from_attributes = True


class RawLeadList(BaseModel):
    """Paginated list of raw leads"""
    raw_leads: List[RawLeadResponse]
    total: int
    page: int
    limit: int
    total_pages: int
    
    # Summary stats
    pending_count: int
    processing_count: int
    processed_count: int
    failed_count: int


class RawLeadUpdate(BaseModel):
    """Update raw lead data before processing"""
    scraped_data: Dict[str, Any]
    notes: Optional[str] = None


class ProcessingResult(BaseModel):
    """Result of processing raw leads"""
    success: bool
    total_submitted: int
    accepted: int
    rejected: int
    already_processed: int
    errors: List[Dict[str, Any]] = []
    
    # Processing details
    created_lead_ids: List[UUID] = []
    failed_raw_lead_ids: List[UUID] = []
    
    message: str


class RawLeadSummaryStats(BaseModel):
    """Summary statistics for raw leads"""
    total_raw_leads: int
    pending: int
    processing: int
    processed: int
    failed: int
    
    # By scraper type
    by_scraper_type: Dict[str, int]
    
    # By ICP
    by_icp: List[Dict[str, Any]]
    
    # Processing rates
    avg_processing_time_seconds: float
    success_rate: float
    
    # Recent activity
    leads_today: int
    leads_this_week: int
    leads_this_month: int


class RawLeadValidationError(BaseModel):
    """Validation error for a raw lead"""
    index: int
    email: str
    field: str
    error: str
    severity: str  # 'error' or 'warning'


class RawLeadFilter(BaseModel):
    """Filters for querying raw leads"""
    tenant_id: UUID
    icp_id: Optional[UUID] = None
    status: Optional[str] = None
    scraper_type: Optional[str] = None
    search: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = Field(1, ge=1)
    limit: int = Field(50, ge=1, le=100)