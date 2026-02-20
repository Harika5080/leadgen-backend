# backend/app/schemas/workflow.py
"""
Pydantic schemas for Phase 1 - Workflow and Activity Tracking
COMPLETE IMPLEMENTATION - Ready to use!
"""
"""
Pydantic schemas for Phase 1 - Workflow and Activity Tracking
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
import re


# ========================================
# WORKFLOW STATUS SCHEMAS
# ========================================

class WorkflowStatusBase(BaseModel):
    """Base schema for workflow status"""
    name: str = Field(..., min_length=1, max_length=100, description="Internal status name")
    display_name: str = Field(..., min_length=1, max_length=100, description="Display name for UI")
    description: Optional[str] = Field(None, description="Status description")
    color: str = Field(default="#667eea", description="Hex color code")
    icon: Optional[str] = Field(None, max_length=50, description="Material-UI icon name")
    order: int = Field(default=0, ge=0, description="Display order")
    is_initial: bool = Field(default=False, description="First status for new leads")
    is_final: bool = Field(default=False, description="Terminal state (won/lost)")
    is_active: bool = Field(default=True, description="Status is active")

    @validator('color')
    def validate_color(cls, v):
        """Validate hex color format"""
        if not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError('Color must be a valid hex code (e.g., #667eea)')
        return v

    @validator('name')
    def validate_name(cls, v):
        """Validate status name (lowercase, no spaces)"""
        if not re.match(r'^[a-z][a-z0-9_]*$', v):
            raise ValueError('Name must start with letter, contain only lowercase letters, numbers, and underscores')
        return v


class WorkflowStatusCreate(WorkflowStatusBase):
    """Schema for creating new workflow status"""
    pass


class WorkflowStatusUpdate(BaseModel):
    """Schema for updating workflow status"""
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None

    @validator('color')
    def validate_color(cls, v):
        if v and not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError('Color must be a valid hex code')
        return v


class WorkflowStatusResponse(WorkflowStatusBase):
    """Schema for workflow status response"""
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None

    class Config:
        from_attributes = True


# ========================================
# WORKFLOW TRANSITION SCHEMAS
# ========================================

class WorkflowTransitionCreate(BaseModel):
    """Schema for creating workflow transition"""
    from_status_id: UUID
    to_status_id: UUID
    is_automatic: bool = False
    require_note: bool = False


class WorkflowTransitionResponse(BaseModel):
    """Schema for workflow transition response"""
    id: UUID
    tenant_id: UUID
    from_status_id: UUID
    to_status_id: UUID
    is_automatic: bool
    require_note: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ========================================
# LEAD ACTIVITY SCHEMAS
# ========================================

class LeadActivityBase(BaseModel):
    """Base schema for lead activity"""
    activity_type: str = Field(..., description="Type of activity")
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @validator('activity_type')
    def validate_activity_type(cls, v):
        """Validate activity type"""
        valid_types = [
            'status_change', 'note', 'email', 'call', 'task',
            'conversion', 'assignment', 'score_change', 'enrichment',
            'import', 'export', 'merge', 'delete'
        ]
        if v not in valid_types:
            raise ValueError(f'Activity type must be one of: {", ".join(valid_types)}')
        return v


class LeadActivityCreate(LeadActivityBase):
    """Schema for creating lead activity"""
    lead_id: UUID


class LeadActivityResponse(LeadActivityBase):
    """Schema for lead activity response"""
    id: UUID
    lead_id: UUID
    user_id: Optional[UUID] = None
    tenant_id: UUID
    source: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    
    # Additional fields from join
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None

    class Config:
        from_attributes = True


class LeadActivityListResponse(BaseModel):
    """Schema for list of activities"""
    activities: List[LeadActivityResponse]
    total: int
    page: int
    page_size: int


# ========================================
# LEAD NOTE SCHEMAS
# ========================================

class LeadNoteCreate(BaseModel):
    """Schema for creating lead note"""
    content: str = Field(..., min_length=1, description="Note content")
    is_pinned: bool = Field(default=False, description="Pin note to top")


class LeadNoteUpdate(BaseModel):
    """Schema for updating lead note"""
    content: Optional[str] = Field(None, min_length=1)
    is_pinned: Optional[bool] = None


class LeadNoteResponse(BaseModel):
    """Schema for lead note response"""
    id: UUID
    lead_id: UUID
    user_id: UUID
    tenant_id: UUID
    content: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
    
    # Additional fields from join
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None

    class Config:
        from_attributes = True


# ========================================
# LEAD CONVERSION SCHEMAS
# ========================================

class LeadConversionCreate(BaseModel):
    """Schema for creating lead conversion"""
    conversion_value: Optional[float] = Field(None, ge=0, description="Deal value")
    conversion_currency: str = Field(default="USD", max_length=3)
    campaign_id: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None

    @validator('conversion_currency')
    def validate_currency(cls, v):
        """Validate currency code"""
        if len(v) != 3:
            raise ValueError('Currency must be 3-letter ISO code (e.g., USD, EUR)')
        return v.upper()


class LeadConversionResponse(BaseModel):
    """Schema for lead conversion response"""
    id: UUID
    lead_id: UUID
    tenant_id: UUID
    converted_at: datetime
    converted_by: UUID
    conversion_value: Optional[float] = None
    conversion_currency: str
    first_touch_source: Optional[str] = None
    last_touch_source: Optional[str] = None
    campaign_id: Optional[str] = None
    time_to_conversion_seconds: Optional[int] = None
    touchpoints_count: int
    status_changes_count: int
    notes: Optional[str] = None
    
    # Additional fields from join
    converted_by_email: Optional[str] = None
    converted_by_name: Optional[str] = None
    
    # Computed fields
    time_to_conversion_days: Optional[float] = None

    class Config:
        from_attributes = True

    @validator('time_to_conversion_days', always=True)
    def compute_days(cls, v, values):
        """Compute days from seconds"""
        if 'time_to_conversion_seconds' in values and values['time_to_conversion_seconds']:
            return round(values['time_to_conversion_seconds'] / 86400, 1)
        return None


# ========================================
# LEAD UPDATE SCHEMAS (Enhanced)
# ========================================

class LeadAssignmentUpdate(BaseModel):
    """Schema for assigning lead to user"""
    assigned_to: Optional[UUID] = Field(None, description="User ID to assign to")


class LeadStatusUpdate(BaseModel):
    """Schema for updating lead status"""
    status: str = Field(..., description="New status")
    note: Optional[str] = Field(None, description="Optional note explaining change")


# ========================================
# ANALYTICS SCHEMAS
# ========================================

class ConversionMetrics(BaseModel):
    """Schema for conversion metrics"""
    total_conversions: int
    total_value: float
    avg_value: float
    avg_time_to_conversion_days: float
    conversion_rate: float



class UserConversionMetrics(BaseModel):
    """Schema for user conversion metrics"""
    user_id: UUID
    user_email: str
    user_name: Optional[str] = None
    conversions_count: int
    total_value: float
    average_value: float
    average_time_to_conversion_days: float
    conversion_rate: float




# ========================================
# WORKFLOW SUMMARY SCHEMAS
# ========================================

class WorkflowSummary(BaseModel):
    """Schema for workflow summary"""
    tenant_id: UUID
    total_statuses: int
    active_statuses: int
    statuses: List[WorkflowStatusResponse]


# ========================================
# ACTIVITY SUMMARY SCHEMAS
# ========================================

class ActivitySummary(BaseModel):
    """Schema for activity summary"""
    lead_id: UUID
    total_activities: int
    status_changes: int
    notes_count: int
    last_activity_at: Optional[datetime] = None
    last_activity_type: Optional[str] = None


# ========================================
# BULK OPERATION SCHEMAS
# ========================================

class BulkStatusUpdate(BaseModel):
    """Schema for bulk status update"""
    lead_ids: List[UUID] = Field(..., min_items=1, max_items=100)
    new_status: str
    note: Optional[str] = None


class BulkAssignment(BaseModel):
    """Schema for bulk assignment"""
    lead_ids: List[UUID] = Field(..., min_items=1, max_items=100)
    assigned_to: UUID


class BulkOperationResponse(BaseModel):
    """Schema for bulk operation response"""
    success_count: int
    failed_count: int
    failed_ids: List[UUID]
    message: str

# ========================================
# PHASE 1 RESPONSE LISTS (MISSING)
# ========================================

class LeadNoteList(BaseModel):
    """List of lead notes"""
    notes: List[LeadNoteResponse]
    total: int


class LeadConversionList(BaseModel):
    """List of lead conversions"""
    conversions: List[LeadConversionResponse]
    total: int


# ========================================
# JOURNEY & METRICS (MISSING)
# ========================================

class LeadJourneyResponse(BaseModel):
    """Lead journey summary"""
    lead_id: UUID
    created_at: datetime
    converted_at: Optional[datetime] = None
    time_to_conversion_days: Optional[float] = None
    status_changes: int
    total_activities: int
    touchpoints: int
    assigned_to_email: Optional[str] = None
    converted_by_email: Optional[str] = None


class SourceConversionMetrics(BaseModel):
    """Schema for source conversion metrics"""
    source_name: str
    conversions_count: int
    total_value: float
    average_value: float
    conversion_rate: float

class ConversionReport(BaseModel):
    """Schema for conversion report"""
    overall: ConversionMetrics  # ✅ Changed from overall_metrics
    by_user: List[UserConversionMetrics]
    by_source: List[SourceConversionMetrics]
    timeframe_days: int



class UserConversionMetrics(BaseModel):
    """User conversion metrics"""
    user_id: UUID
    user_email: str
    user_name: Optional[str] = None
    conversions_count: int
    total_value: float
    average_value: float
    average_time_to_conversion_days: float
    conversion_rate: float