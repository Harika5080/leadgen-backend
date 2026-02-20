"""Pydantic schemas for request/response validation."""

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

from enum import Enum

class LeadProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"

class LeadStatus(str, Enum):
    NEW = "new"
    SCORED = "scored"
    ENRICHED = "enriched"
    VERIFIED = "verified"
    QUALIFIED = "qualified"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    EXPORTED = "exported"


# Authentication Schemas
class LoginRequest(BaseModel):
    """Login request with email and password."""
    email: EmailStr
    password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserCreate(BaseModel):
    """Create new user request."""
    email: EmailStr
    password: str = Field(..., min_length=12)
    full_name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(default="reviewer", pattern="^(admin|reviewer|viewer)$")


class UserResponse(BaseModel):
    """User information response."""
    id: UUID
    tenant_id: UUID
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    last_login: Optional[datetime]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Lead Schemas
class LeadBase(BaseModel):
    """Base lead information shared across schemas."""
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    linkedin_url: Optional[str] = None
    company_name: Optional[str] = None
    company_website: Optional[str] = None


class LeadInBatch(LeadBase):
    """Individual lead in a batch (no source_name needed)."""
    acquisition_timestamp: Optional[datetime] = None


class LeadBatchCreate(BaseModel):
    """Batch lead creation request."""
    source_name: str = Field(..., min_length=1, max_length=255)
    leads: List[LeadInBatch] = Field(..., min_items=1, max_items=1000)
    
    @field_validator('leads')
    @classmethod
    def validate_batch_size(cls, v):
        if len(v) > 1000:
            raise ValueError('Batch size cannot exceed 1000 leads')
        return v


class LeadResponse(BaseModel):
    """Lead information response."""
    id: UUID
    tenant_id: UUID
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]
    job_title: Optional[str]
    linkedin_url: Optional[str]
    company_name: Optional[str]
    company_website: Optional[str]
    company_domain: Optional[str]
    company_industry: Optional[str]
    status: str
    fit_score: Optional[float]
    email_verified: bool
    email_deliverability_score: Optional[float]
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[str]
    review_decision: Optional[str]
    review_notes: Optional[str]
    exported_at: Optional[datetime]
    source_name: Optional[str]
    acquisition_timestamp: datetime
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class LeadListResponse(BaseModel):
    """Paginated lead list response."""
    leads: List[LeadResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ReviewDecision(BaseModel):
    """Lead review decision."""
    decision: str = Field(..., pattern="^(approved|rejected)$")
    notes: Optional[str] = Field(None, max_length=2000)
    edits: Optional[Dict[str, Any]] = None


class BatchResponse(BaseModel):
    """Batch processing response."""
    batch_id: str
    accepted: int
    rejected: int
    errors: List[Dict[str, Any]] = []


# Error Response
class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# Settings schemas
from app.schemas.settings import (
    TenantSettingsResponse,
    TenantSettingsUpdate,
    UserPreferencesResponse,
    UserPreferencesUpdate,
    SourceConfigCreate,
    SourceConfigUpdate,
    SourceConfigResponse,
)

from app.schemas.workflow import (
    LeadActivityCreate,
    LeadActivityResponse,
    LeadNoteCreate,
    LeadActivityListResponse,
    LeadNoteUpdate,
    LeadNoteResponse,
    LeadNoteList,
    LeadJourneyResponse
)

# Bucket system schemas
from app.schemas.bucket import (
    BucketStats,
    LeadInBucket,
    BucketLeadList,
    BucketLeadFilter,
    LeadBucketMove,
    ICPProcessingConfig,
    ICPProcessingConfigUpdate,
    BucketFlowAnalytics,
    ProcessingStageHistory,
)

# Raw leads schemas
from app.schemas.raw_lead import (
    RawLeadCreate,
    RawLeadBatch,
    RawLeadResponse,
    RawLeadList,
    RawLeadUpdate,
    ProcessingResult,
    RawLeadSummaryStats,
    RawLeadValidationError,
    RawLeadFilter,
)