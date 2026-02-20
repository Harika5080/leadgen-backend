"""CSV Import endpoint for bulk lead upload."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any, Optional
from datetime import datetime
import csv
import io
import logging
from uuid import uuid4

from app.database import get_db
from app.models import Lead, User
from app.rbac import require_create_leads
from app.schemas import LeadResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# Field mapping configuration
LEAD_FIELDS = {
    'email': {'required': True, 'type': 'string'},
    'first_name': {'required': False, 'type': 'string'},
    'last_name': {'required': False, 'type': 'string'},
    'phone': {'required': False, 'type': 'string'},
    'job_title': {'required': False, 'type': 'string'},
    'linkedin_url': {'required': False, 'type': 'string'},
    'company_name': {'required': False, 'type': 'string'},
    'company_website': {'required': False, 'type': 'string'},
    'company_domain': {'required': False, 'type': 'string'},
    'company_industry': {'required': False, 'type': 'string'},
    'source_name': {'required': False, 'type': 'string'},
    'fit_score': {'required': False, 'type': 'float'},
    'email_verified': {'required': False, 'type': 'boolean'},
    'email_deliverability_score': {'required': False, 'type': 'float'},
}


def parse_csv_file(file_content: bytes) -> tuple[List[str], List[Dict[str, Any]]]:
    """Parse CSV file and return headers and rows."""
    try:
        # Try UTF-8 first
        text_content = file_content.decode('utf-8')
    except UnicodeDecodeError:
        # Fallback to latin-1
        text_content = file_content.decode('latin-1')
    
    # Parse CSV
    csv_reader = csv.DictReader(io.StringIO(text_content))
    headers = csv_reader.fieldnames or []
    rows = list(csv_reader)
    
    return headers, rows


def validate_row(row: Dict[str, Any], row_number: int) -> Dict[str, Any]:
    """Validate a single row and return validation result."""
    errors = []
    warnings = []
    
    # Check required fields
    if not row.get('email') or not row['email'].strip():
        errors.append(f"Missing required field: email")
    else:
        # Basic email validation
        email = row['email'].strip()
        if '@' not in email or '.' not in email.split('@')[1]:
            errors.append(f"Invalid email format: {email}")
    
    # Validate fit_score range
    if row.get('fit_score'):
        try:
            score = float(row['fit_score'])
            if score < 0 or score > 1:
                errors.append(f"fit_score must be between 0 and 1, got {score}")
        except ValueError:
            errors.append(f"fit_score must be a number, got {row['fit_score']}")
    
    # Validate email_deliverability_score
    if row.get('email_deliverability_score'):
        try:
            score = float(row['email_deliverability_score'])
            if score < 0 or score > 1:
                errors.append(f"email_deliverability_score must be between 0 and 1")
        except ValueError:
            errors.append(f"email_deliverability_score must be a number")
    
    # Validate boolean fields
    if row.get('email_verified'):
        val = str(row['email_verified']).lower()
        if val not in ['true', 'false', '1', '0', 'yes', 'no', '']:
            errors.append(f"email_verified must be true/false, got {row['email_verified']}")
    
    # Check for missing recommended fields
    if not row.get('first_name') and not row.get('last_name'):
        warnings.append("Missing both first_name and last_name")
    
    if not row.get('company_name'):
        warnings.append("Missing company_name")
    
    return {
        'row_number': row_number,
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'data': row
    }


def normalize_row_data(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and convert row data to proper types."""
    normalized = {}
    
    # String fields - strip whitespace
    string_fields = ['email', 'first_name', 'last_name', 'phone', 'job_title', 
                     'linkedin_url', 'company_name', 'company_website', 
                     'company_domain', 'company_industry', 'source_name']
    
    for field in string_fields:
        value = row.get(field, '').strip() if row.get(field) else None
        if value:
            normalized[field] = value
    
    # Float fields
    if row.get('fit_score'):
        try:
            normalized['fit_score'] = float(row['fit_score'])
        except ValueError:
            pass
    
    if row.get('email_deliverability_score'):
        try:
            normalized['email_deliverability_score'] = float(row['email_deliverability_score'])
        except ValueError:
            pass
    
    # Boolean fields
    if row.get('email_verified'):
        val = str(row['email_verified']).lower()
        normalized['email_verified'] = val in ['true', '1', 'yes']
    
    return normalized


@router.post("/leads/import/preview")
async def preview_csv_import(
    file: UploadFile = File(...),
    current_user: User = Depends(require_create_leads),
):
    """
    Preview CSV file before import.
    Returns headers, sample rows, and validation results.
    
    **Required Permission:** CREATE_LEADS (Admin + Reviewer)
    """
    
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file"
        )
    
    # Read file content
    content = await file.read()
    
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty"
        )
    
    # Parse CSV
    try:
        headers, rows = parse_csv_file(content)
    except Exception as e:
        logger.error(f"CSV parse error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV file: {str(e)}"
        )
    
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file contains no data rows"
        )
    
    # Validate all rows
    validation_results = []
    for idx, row in enumerate(rows, start=1):
        result = validate_row(row, idx)
        validation_results.append(result)
    
    # Calculate statistics
    total_rows = len(rows)
    valid_rows = sum(1 for r in validation_results if r['valid'])
    invalid_rows = total_rows - valid_rows
    total_warnings = sum(len(r['warnings']) for r in validation_results)
    
    # Get sample of first 5 rows
    sample_rows = validation_results[:5]
    
    # Get all errors for display
    all_errors = [r for r in validation_results if not r['valid']][:20]  # First 20 errors
    
    logger.info(
        f"CSV preview: {total_rows} rows, {valid_rows} valid, "
        f"{invalid_rows} invalid, {total_warnings} warnings - {current_user.email}"
    )
    
    return {
        'headers': headers,
        'available_fields': list(LEAD_FIELDS.keys()),
        'field_config': LEAD_FIELDS,
        'total_rows': total_rows,
        'valid_rows': valid_rows,
        'invalid_rows': invalid_rows,
        'total_warnings': total_warnings,
        'sample_rows': sample_rows,
        'errors': all_errors,
        'can_import': valid_rows > 0,
    }


@router.post("/leads/import/execute")
async def execute_csv_import(
    file: UploadFile = File(...),
    source_name: str = "CSV Import",
    skip_duplicates: bool = True,
    current_user: User = Depends(require_create_leads),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute CSV import after validation.
    Creates leads in database from valid rows.
    
    **Required Permission:** CREATE_LEADS (Admin + Reviewer)
    """
    
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file"
        )
    
    # Read file content
    content = await file.read()
    
    # Parse CSV
    try:
        headers, rows = parse_csv_file(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV file: {str(e)}"
        )
    
    # Validate all rows
    validation_results = []
    for idx, row in enumerate(rows, start=1):
        result = validate_row(row, idx)
        validation_results.append(result)
    
    # Filter valid rows
    valid_rows = [r for r in validation_results if r['valid']]
    
    if not valid_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid rows to import"
        )
    
    # Import leads
    imported = 0
    skipped = 0
    errors = []
    
    for result in valid_rows:
        try:
            row_data = normalize_row_data(result['data'])
            email = row_data['email']
            
            # Check for duplicate
            if skip_duplicates:
                existing = await db.execute(
                    select(Lead).where(
                        Lead.tenant_id == current_user.tenant_id,
                        Lead.email == email
                    )
                )
                if existing.scalar_one_or_none():
                    skipped += 1
                    continue
            
            # Create lead
            lead = Lead(
                id=uuid4(),
                tenant_id=current_user.tenant_id,
                email=email,
                first_name=row_data.get('first_name'),
                last_name=row_data.get('last_name'),
                phone=row_data.get('phone'),
                job_title=row_data.get('job_title'),
                linkedin_url=row_data.get('linkedin_url'),
                company_name=row_data.get('company_name'),
                company_website=row_data.get('company_website'),
                company_domain=row_data.get('company_domain'),
                company_industry=row_data.get('company_industry'),
                source_name=row_data.get('source_name') or source_name,
                fit_score=row_data.get('fit_score'),
                email_verified=row_data.get('email_verified', False),
                email_deliverability_score=row_data.get('email_deliverability_score'),
                status='new',
                acquisition_timestamp=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            
            db.add(lead)
            imported += 1
            
            # Commit in batches of 100
            if imported % 100 == 0:
                await db.commit()
                logger.info(f"Imported {imported} leads so far...")
        
        except Exception as e:
            logger.error(f"Error importing row {result['row_number']}: {str(e)}")
            errors.append({
                'row_number': result['row_number'],
                'email': result['data'].get('email', 'unknown'),
                'error': str(e)
            })
    
    # Final commit
    await db.commit()
    
    logger.info(
        f"CSV import completed: {imported} imported, {skipped} skipped, "
        f"{len(errors)} errors - {current_user.email}"
    )
    
    return {
        'success': True,
        'imported': imported,
        'skipped': skipped,
        'failed': len(errors),
        'total_processed': len(valid_rows),
        'errors': errors[:20],  # First 20 errors
        'message': f"Successfully imported {imported} leads"
    }