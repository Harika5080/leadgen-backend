# backend/app/routers/schema_routes.py
"""
Schema Routes - Expose database schema information for dynamic field mapping
"""
from fastapi import APIRouter, Depends
from sqlalchemy import inspect
from typing import List, Dict, Any
from pydantic import BaseModel

from app.database import engine
from app.auth import get_current_user
from app.models import User, RawLead, Lead

router = APIRouter(prefix="/api/v1/schema", tags=["Schema"])


class FieldInfo(BaseModel):
    """Information about a database field"""
    name: str
    label: str
    data_type: str
    required: bool
    category: str
    description: str | None = None


class FieldMappingSchema(BaseModel):
    """Complete field mapping schema"""
    fields: List[FieldInfo]
    categories: List[str]


# Field metadata - maps database columns to user-friendly information
FIELD_METADATA = {
    # Contact Information
    'email': {
        'label': 'Email',
        'category': 'Contact Info',
        'required': True,
        'description': 'Primary email address'
    },
    'first_name': {
        'label': 'First Name',
        'category': 'Contact Info',
        'required': False,
        'description': 'First or given name'
    },
    'last_name': {
        'label': 'Last Name',
        'category': 'Contact Info',
        'required': False,
        'description': 'Last or family name'
    },
    'full_name': {
        'label': 'Full Name',
        'category': 'Contact Info',
        'required': False,
        'description': 'Complete name'
    },
    'phone': {
        'label': 'Phone',
        'category': 'Contact Info',
        'required': False,
        'description': 'Phone number'
    },
    'linkedin_url': {
        'label': 'LinkedIn URL',
        'category': 'Contact Info',
        'required': False,
        'description': 'LinkedIn profile URL'
    },
    
    # Professional Information
    'job_title': {
        'label': 'Job Title',
        'category': 'Professional',
        'required': False,
        'description': 'Current job title or position'
    },
    'seniority_level': {
        'label': 'Seniority Level',
        'category': 'Professional',
        'required': False,
        'description': 'Career level (e.g., Senior, Director, VP)'
    },
    'department': {
        'label': 'Department',
        'category': 'Professional',
        'required': False,
        'description': 'Department or business unit'
    },
    'job_function': {
        'label': 'Job Function',
        'category': 'Professional',
        'required': False,
        'description': 'Primary job function'
    },
    
    # Company Information
    'company_name': {
        'label': 'Company Name',
        'category': 'Company',
        'required': False,
        'description': 'Name of the company'
    },
    'company_website': {
        'label': 'Company Website',
        'category': 'Company',
        'required': False,
        'description': 'Company website URL'
    },
    'company_domain': {
        'label': 'Company Domain',
        'category': 'Company',
        'required': False,
        'description': 'Company domain name (e.g., example.com)'
    },
    'company_industry': {
        'label': 'Company Industry',
        'category': 'Company',
        'required': False,
        'description': 'Industry sector'
    },
    'company_size': {
        'label': 'Company Size',
        'category': 'Company',
        'required': False,
        'description': 'Number of employees'
    },
    'company_revenue_estimate': {
        'label': 'Company Revenue',
        'category': 'Company',
        'required': False,
        'description': 'Estimated annual revenue'
    },
    'company_linkedin_url': {
        'label': 'Company LinkedIn URL',
        'category': 'Company',
        'required': False,
        'description': 'Company LinkedIn page'
    },
    'company_employee_count': {
        'label': 'Company Employee Count',
        'category': 'Company',
        'required': False,
        'description': 'Total number of employees'
    },
    
    # Location Information
    'city': {
        'label': 'City',
        'category': 'Location',
        'required': False,
        'description': 'City name'
    },
    'state': {
        'label': 'State/Province',
        'category': 'Location',
        'required': False,
        'description': 'State or province'
    },
    'country': {
        'label': 'Country',
        'category': 'Location',
        'required': False,
        'description': 'Country name'
    },
    'zip_code': {
        'label': 'Zip/Postal Code',
        'category': 'Location',
        'required': False,
        'description': 'ZIP or postal code'
    },
    'location': {
        'label': 'Full Location',
        'category': 'Location',
        'required': False,
        'description': 'Complete location string'
    },
    
    # Demographics
    'age': {
        'label': 'Age',
        'category': 'Demographics',
        'required': False,
        'description': 'Age in years'
    },
    'gender': {
        'label': 'Gender',
        'category': 'Demographics',
        'required': False,
        'description': 'Gender'
    },
    'education_level': {
        'label': 'Education Level',
        'category': 'Demographics',
        'required': False,
        'description': 'Highest education level'
    },
    'years_of_experience': {
        'label': 'Years of Experience',
        'category': 'Demographics',
        'required': False,
        'description': 'Total years of work experience'
    },
    
    # LinkedIn Specific
    'headline': {
        'label': 'LinkedIn Headline',
        'category': 'LinkedIn',
        'required': False,
        'description': 'LinkedIn profile headline'
    },
    'connections': {
        'label': 'LinkedIn Connections',
        'category': 'LinkedIn',
        'required': False,
        'description': 'Number of LinkedIn connections'
    },
    'about': {
        'label': 'LinkedIn About',
        'category': 'LinkedIn',
        'required': False,
        'description': 'LinkedIn about/summary section'
    },
    'profile_url': {
        'label': 'LinkedIn Profile URL',
        'category': 'LinkedIn',
        'required': False,
        'description': 'Full LinkedIn profile URL'
    },
    
    # Social Media
    'twitter_url': {
        'label': 'Twitter URL',
        'category': 'Social Media',
        'required': False,
        'description': 'Twitter profile URL'
    },
    'facebook_url': {
        'label': 'Facebook URL',
        'category': 'Social Media',
        'required': False,
        'description': 'Facebook profile URL'
    },
    'instagram_url': {
        'label': 'Instagram URL',
        'category': 'Social Media',
        'required': False,
        'description': 'Instagram profile URL'
    },
}


@router.get("/lead-fields", response_model=FieldMappingSchema)
async def get_lead_fields(
    current_user: User = Depends(get_current_user)
):
    """
    Get all available lead fields for field mapping.
    
    Returns a list of fields from the raw_leads table that can be mapped
    from data sources. Each field includes:
    - name: Database column name
    - label: Human-readable label
    - data_type: SQL data type
    - required: Whether the field is required
    - category: Field category for grouping
    - description: Field description
    
    This allows the UI to dynamically build field mapping forms without
    hardcoding field lists.
    """
    
    # Get RawLead table schema using SQLAlchemy inspector
    inspector = inspect(engine)
    columns = inspector.get_columns('raw_leads')
    
    # Build field list
    fields = []
    categories_set = set()
    
    # System columns to exclude from mapping
    excluded_columns = {
        'id', 'tenant_id', 'data_source_id', 'created_at', 'updated_at',
        'status', 'processing_status', 'error_message', 'processed_by_icps',
        'scraped_data', 'enrichment_data', 'source_name', 'source_url',
        'scraper_type', 'batch_id'
    }
    
    for column in columns:
        column_name = column['name']
        
        # Skip system columns
        if column_name in excluded_columns:
            continue
        
        # Get metadata or create default
        metadata = FIELD_METADATA.get(column_name, {
            'label': column_name.replace('_', ' ').title(),
            'category': 'Other',
            'required': False,
            'description': None
        })
        
        field_info = FieldInfo(
            name=column_name,
            label=metadata['label'],
            data_type=str(column['type']),
            required=metadata['required'],
            category=metadata['category'],
            description=metadata.get('description')
        )
        
        fields.append(field_info)
        categories_set.add(metadata['category'])
    
    # Sort fields by category and then by name
    fields.sort(key=lambda f: (f.category, f.name))
    
    # Get unique categories in order
    category_order = ['Contact Info', 'Professional', 'Company', 'Location', 
                      'Demographics', 'LinkedIn', 'Social Media', 'Other']
    categories = [cat for cat in category_order if cat in categories_set]
    categories.extend([cat for cat in sorted(categories_set) if cat not in category_order])
    
    return FieldMappingSchema(
        fields=fields,
        categories=categories
    )


@router.get("/data-source-preview/{data_source_id}")
async def preview_data_source_fields(
    data_source_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Preview sample data from a data source to help with field mapping.
    
    Returns the first record from the data source to show what fields
    are available for mapping.
    
    This is useful for auto-suggesting field mappings based on actual data.
    """
    # TODO: Implement data source preview
    # This would fetch a sample record and return its structure
    pass