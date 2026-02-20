# backend/app/routers/conversion_routes.py
"""
Conversion Tracking & Analytics API - Phase 1
Complete implementation for conversion management and reporting
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from app.database import get_db
from app.models import LeadConversion, Lead, User, LeadActivity
from app.schemas.workflow import (
    LeadConversionCreate,
    LeadConversionResponse,
    LeadConversionList,
    ConversionReport,
    ConversionMetrics,
    UserConversionMetrics,
    SourceConversionMetrics
)
from app.auth import get_current_user

router = APIRouter(prefix="/api/v1/conversions", tags=["conversions"])


# ==================== CONVERSION ENDPOINTS ====================

@router.post("/leads/{lead_id}/convert", response_model=LeadConversionResponse, status_code=status.HTTP_201_CREATED)
async def convert_lead(
    lead_id: UUID,
    conversion_data: LeadConversionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Convert a lead.
    
    This endpoint:
    1. Creates a conversion record
    2. Updates lead status to 'converted'
    3. Sets conversion metadata on lead
    4. Logs conversion activity
    """
    # Get lead
    lead_result = await db.execute(
        select(Lead).where(
            and_(
                Lead.id == lead_id,
                Lead.tenant_id == current_user.tenant_id
            )
        )
    )
    lead = lead_result.scalar_one_or_none()
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )
    
    # Check if already converted
    existing_conversion = await db.execute(
        select(LeadConversion).where(LeadConversion.lead_id == lead_id)
    )
    if existing_conversion.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lead is already converted"
        )
    
    # Count status changes
    status_changes_result = await db.execute(
        select(func.count(LeadActivity.id)).where(
            and_(
                LeadActivity.lead_id == lead_id,
                LeadActivity.activity_type == 'status_change'
            )
        )
    )
    status_changes_count = status_changes_result.scalar() or 0
    
    # Calculate time to conversion
    time_to_conversion = int((datetime.utcnow() - lead.created_at).total_seconds())
    
    # Create conversion record
    conversion = LeadConversion(
        lead_id=lead_id,
        tenant_id=current_user.tenant_id,
        converted_by=current_user.id,
        conversion_value=conversion_data.conversion_value,
        conversion_currency=conversion_data.conversion_currency,
        campaign_id=conversion_data.campaign_id,
        first_touch_source=lead.source_name,
        last_touch_source=lead.source_name,
        time_to_conversion_seconds=time_to_conversion,
        touchpoints_count=lead.touchpoints_count or 1,
        status_changes_count=status_changes_count,
        notes=conversion_data.notes
    )
    
    db.add(conversion)
    
    # Update lead
    lead.status = 'converted'
    lead.converted_at = datetime.utcnow()
    lead.converted_by = current_user.id
    lead.conversion_value = conversion_data.conversion_value
    
    # Log activity
    activity = LeadActivity(
        lead_id=lead_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        activity_type='conversion',
        title='Lead Converted',
        description=f'Converted with value: {conversion_data.conversion_currency} {conversion_data.conversion_value or 0}',
        old_status=lead.status,
        new_status='converted',
        activity_metadata={
            'conversion_value': conversion_data.conversion_value,
            'conversion_currency': conversion_data.conversion_currency,
            'campaign_id': conversion_data.campaign_id
        },
        source='manual'
    )
    
    db.add(activity)
    
    await db.commit()
    await db.refresh(conversion)
    
    # Return with enriched data
    return LeadConversionResponse(
        **conversion.__dict__,
        converted_by_email=current_user.email,
        converted_by_name=current_user.full_name
    )


@router.get("", response_model=LeadConversionList)
async def get_conversions(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    converted_by: Optional[UUID] = None,
    campaign_id: Optional[str] = None,
    min_value: Optional[float] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of conversions with filters.
    
    Filters:
    - days: Look back period
    - converted_by: Filter by user who converted
    - campaign_id: Filter by campaign
    - min_value: Minimum conversion value
    """
    # Build query
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    query = select(LeadConversion, User.email, User.full_name).join(
        User, LeadConversion.converted_by == User.id
    ).where(
        and_(
            LeadConversion.tenant_id == current_user.tenant_id,
            LeadConversion.converted_at >= cutoff_date
        )
    )
    
    # Apply filters
    if converted_by:
        query = query.where(LeadConversion.converted_by == converted_by)
    
    if campaign_id:
        query = query.where(LeadConversion.campaign_id == campaign_id)
    
    if min_value is not None:
        query = query.where(LeadConversion.conversion_value >= min_value)
    
    # Get total count
    count_query = select(func.count(LeadConversion.id)).where(
        and_(
            LeadConversion.tenant_id == current_user.tenant_id,
            LeadConversion.converted_at >= cutoff_date
        )
    )
    if converted_by:
        count_query = count_query.where(LeadConversion.converted_by == converted_by)
    if campaign_id:
        count_query = count_query.where(LeadConversion.campaign_id == campaign_id)
    if min_value is not None:
        count_query = count_query.where(LeadConversion.conversion_value >= min_value)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Order and paginate
    query = query.order_by(LeadConversion.converted_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(query)
    rows = result.all()
    
    # Format response
    conversions = []
    for conversion, user_email, user_name in rows:
        conv_dict = {
            **conversion.__dict__,
            "converted_by_email": user_email,
            "converted_by_name": user_name
        }
        conversions.append(LeadConversionResponse(**conv_dict))
    
    return LeadConversionList(conversions=conversions, total=total)


@router.get("/{conversion_id}", response_model=LeadConversionResponse)
async def get_conversion(
    conversion_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific conversion by ID"""
    result = await db.execute(
        select(LeadConversion, User.email, User.full_name).join(
            User, LeadConversion.converted_by == User.id
        ).where(
            and_(
                LeadConversion.id == conversion_id,
                LeadConversion.tenant_id == current_user.tenant_id
            )
        )
    )
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversion not found"
        )
    
    conversion, user_email, user_name = row
    
    return LeadConversionResponse(
        **conversion.__dict__,
        converted_by_email=user_email,
        converted_by_name=user_name
    )


# ==================== ANALYTICS ENDPOINTS ====================

@router.get("/reports/overview", response_model=ConversionReport)
async def get_conversion_report(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive conversion report.
    
    Includes:
    - Overall metrics (total conversions, value, avg time)
    - Metrics by user
    - Metrics by source
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Overall metrics
    overall_query = select(
        func.count(LeadConversion.id).label('total_conversions'),
        func.sum(LeadConversion.conversion_value).label('total_value'),
        func.avg(LeadConversion.conversion_value).label('avg_value'),
        func.avg(LeadConversion.time_to_conversion_seconds).label('avg_time_seconds')
    ).where(
        and_(
            LeadConversion.tenant_id == current_user.tenant_id,
            LeadConversion.converted_at >= cutoff_date
        )
    )
    
    overall_result = await db.execute(overall_query)
    overall_row = overall_result.one()
    
    # Get total leads for conversion rate
    total_leads_query = select(func.count(Lead.id)).where(
        and_(
            Lead.tenant_id == current_user.tenant_id,
            Lead.created_at >= cutoff_date
        )
    )
    total_leads_result = await db.execute(total_leads_query)
    total_leads = total_leads_result.scalar() or 1
    
    # Calculate conversion rate
    conversion_rate = (overall_row.total_conversions / total_leads * 100) if total_leads > 0 else 0
    
    # Build overall metrics
    overall_metrics = ConversionMetrics(
        total_conversions=overall_row.total_conversions or 0,
        total_value=float(overall_row.total_value or 0),
        avg_value=float(overall_row.avg_value or 0),
        avg_time_to_conversion_days=round((overall_row.avg_time_seconds or 0) / 86400, 1),
        conversion_rate=round(conversion_rate, 2)
    )
    
    # Metrics by user
    user_query = select(
        User.id,
        User.email,
        User.full_name,
        func.count(LeadConversion.id).label('conversions_count'),
        func.sum(LeadConversion.conversion_value).label('total_value'),
        func.avg(LeadConversion.conversion_value).label('avg_value'),
        func.avg(LeadConversion.time_to_conversion_seconds).label('avg_time_seconds')
    ).join(
        LeadConversion, User.id == LeadConversion.converted_by
    ).where(
        and_(
            LeadConversion.tenant_id == current_user.tenant_id,
            LeadConversion.converted_at >= cutoff_date
        )
    ).group_by(User.id, User.email, User.full_name)
    
    user_result = await db.execute(user_query)
    user_rows = user_result.all()
    
    user_metrics = []
    for row in user_rows:
        # Get leads assigned to this user for conversion rate
        user_leads_query = select(func.count(Lead.id)).where(
            and_(
                Lead.tenant_id == current_user.tenant_id,
                Lead.assigned_to == row.id,
                Lead.created_at >= cutoff_date
            )
        )
        user_leads_result = await db.execute(user_leads_query)
        user_leads = user_leads_result.scalar() or row.conversions_count
        
        user_conversion_rate = (row.conversions_count / user_leads * 100) if user_leads > 0 else 0
        
        user_metrics.append(UserConversionMetrics(
            user_id=row.id,
            user_email=row.email,
            user_name=row.full_name,
            conversions_count=row.conversions_count,
            total_value=float(row.total_value or 0),
            average_value=float(row.avg_value or 0),
            average_time_to_conversion_days=round((row.avg_time_seconds or 0) / 86400, 1),
            conversion_rate=round(user_conversion_rate, 2)
        ))
    
    # Metrics by source
    source_query = select(
        LeadConversion.first_touch_source,
        func.count(LeadConversion.id).label('conversions_count'),
        func.sum(LeadConversion.conversion_value).label('total_value'),
        func.avg(LeadConversion.conversion_value).label('avg_value')
    ).where(
        and_(
            LeadConversion.tenant_id == current_user.tenant_id,
            LeadConversion.converted_at >= cutoff_date,
            LeadConversion.first_touch_source.isnot(None)
        )
    ).group_by(LeadConversion.first_touch_source)
    
    source_result = await db.execute(source_query)
    source_rows = source_result.all()
    
    source_metrics = []
    for row in source_rows:
        # Get total leads from this source
        source_leads_query = select(func.count(Lead.id)).where(
            and_(
                Lead.tenant_id == current_user.tenant_id,
                Lead.source_name == row.first_touch_source,
                Lead.created_at >= cutoff_date
            )
        )
        source_leads_result = await db.execute(source_leads_query)
        source_leads = source_leads_result.scalar() or row.conversions_count
        
        source_conversion_rate = (row.conversions_count / source_leads * 100) if source_leads > 0 else 0
        
        source_metrics.append(SourceConversionMetrics(
            source_name=row.first_touch_source,
            conversions_count=row.conversions_count,
            total_value=float(row.total_value or 0),
            average_value=float(row.avg_value or 0),
            conversion_rate=round(source_conversion_rate, 2)
        ))
    
    return ConversionReport(
        overall=overall_metrics,
        by_user=user_metrics,
        by_source=source_metrics,
        timeframe_days=days
    )


@router.get("/reports/timeline")
async def get_conversion_timeline(
    days: int = Query(30, ge=1, le=365),
    granularity: str = Query("day", regex="^(day|week|month)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get conversion timeline (conversions over time).
    
    Useful for charts showing conversion trends.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Different grouping based on granularity
    if granularity == "day":
        date_trunc = func.date_trunc('day', LeadConversion.converted_at)
    elif granularity == "week":
        date_trunc = func.date_trunc('week', LeadConversion.converted_at)
    else:  # month
        date_trunc = func.date_trunc('month', LeadConversion.converted_at)
    
    query = select(
        date_trunc.label('period'),
        func.count(LeadConversion.id).label('conversions'),
        func.sum(LeadConversion.conversion_value).label('total_value')
    ).where(
        and_(
            LeadConversion.tenant_id == current_user.tenant_id,
            LeadConversion.converted_at >= cutoff_date
        )
    ).group_by('period').order_by('period')
    
    result = await db.execute(query)
    rows = result.all()
    
    timeline = [
        {
            "period": row.period.isoformat(),
            "conversions": row.conversions,
            "total_value": float(row.total_value or 0)
        }
        for row in rows
    ]
    
    return {
        "timeline": timeline,
        "granularity": granularity,
        "timeframe_days": days
    }