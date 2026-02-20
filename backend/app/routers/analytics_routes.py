"""Analytics API endpoints for dashboard metrics with RBAC."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import logging

from app.database import get_db
from app.models import Lead, User
from app.rbac import require_view_analytics
from app.services.ai_insights_generator import AIInsightsGenerator

from sqlalchemy import case, extract

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================
# EXISTING ENDPOINTS (YOUR CURRENT ONES)
# ============================================

@router.get("/funnel")
async def get_conversion_funnel(
    days: int = 30,
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """
    Get conversion funnel data showing lead progression through statuses.
    
    Returns count and conversion rate for each status stage.
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get counts for each status
        status_query = select(
            Lead.status,
            func.count(Lead.id).label('count')
        ).where(
            and_(
                Lead.tenant_id == str(current_user.tenant_id),
                Lead.created_at >= start_date
            )
        ).group_by(Lead.status)
        
        result = await db.execute(status_query)
        status_counts = {row[0]: row[1] for row in result.all()}
        
        # Define funnel stages
        funnel_stages = [
            {'name': 'New', 'status': 'new', 'color': '#667eea'},
            {'name': 'Contacted', 'status': 'contacted', 'color': '#f59e0b'},
            {'name': 'Qualified', 'status': 'qualified', 'color': '#8b5cf6'},
            {'name': 'Converted', 'status': 'converted', 'color': '#10b981'},
        ]
        
        # Calculate funnel data
        total = sum(status_counts.values())
        funnel = []
        
        for stage in funnel_stages:
            count = status_counts.get(stage['status'], 0)
            percentage = (count / total * 100) if total > 0 else 0
            
            funnel.append({
                'stage': stage['name'],
                'count': count,
                'percentage': round(percentage, 1),
                'color': stage['color']
            })
        
        # Calculate conversion rates between stages
        for i in range(len(funnel) - 1):
            current_count = funnel[i]['count']
            next_count = funnel[i + 1]['count']
            funnel[i]['conversion_rate'] = round(
                (next_count / current_count * 100) if current_count > 0 else 0,
                1
            )
        
        return {
            'funnel': funnel,
            'total_leads': total,
            'timeframe_days': days
        }
        
    except Exception as e:
        logger.error(f"Error generating funnel data: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Failed to generate funnel: {str(e)}")


@router.get("/velocity")
async def get_lead_velocity(
    days: int = 30,
    granularity: str = 'daily',  # daily, weekly, monthly
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """
    Get lead velocity over time - how many leads added per day/week/month.
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Determine grouping based on granularity
        if granularity == 'daily':
            time_group = func.date(Lead.created_at)
        elif granularity == 'weekly':
            time_group = func.date_trunc('week', Lead.created_at)
        else:  # monthly
            time_group = func.date_trunc('month', Lead.created_at)
        
        # Query lead counts over time
        velocity_query = select(
            time_group.label('period'),
            func.count(Lead.id).label('count'),
            func.count(case((Lead.status == 'converted', 1))).label('converted')
        ).where(
            and_(
                Lead.tenant_id == str(current_user.tenant_id),
                Lead.created_at >= start_date
            )
        ).group_by('period').order_by('period')
        
        result = await db.execute(velocity_query)
        rows = result.all()
        
        # Format data
        velocity_data = []
        for row in rows:
            period_date = row[0]
            if isinstance(period_date, datetime):
                period_str = period_date.strftime('%Y-%m-%d')
            else:
                period_str = str(period_date)
            
            velocity_data.append({
                'date': period_str,
                'leads': row[1],
                'converted': row[2],
                'conversion_rate': round((row[2] / row[1] * 100) if row[1] > 0 else 0, 1)
            })
        
        # Calculate summary stats
        total_leads = sum(d['leads'] for d in velocity_data)
        avg_per_period = round(total_leads / len(velocity_data), 1) if velocity_data else 0
        
        return {
            'data': velocity_data,
            'summary': {
                'total_leads': total_leads,
                'average_per_period': avg_per_period,
                'periods': len(velocity_data),
                'granularity': granularity
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating velocity data: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Failed to generate velocity: {str(e)}")


@router.get("/sources")
async def get_source_performance(
    days: int = 30,
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """
    Get performance metrics for each lead source.
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Query source performance
        source_query = select(
            Lead.source_name,
            func.count(Lead.id).label('total'),
            func.count(case((Lead.status == 'converted', 1))).label('converted'),
            func.avg(Lead.fit_score).label('avg_score')
        ).where(
            and_(
                Lead.tenant_id == str(current_user.tenant_id),
                Lead.created_at >= start_date,
                Lead.source_name.isnot(None)
            )
        ).group_by(Lead.source_name).order_by(func.count(Lead.id).desc())
        
        result = await db.execute(source_query)
        rows = result.all()
        
        # Format data
        sources = []
        for row in rows:
            source_name = row[0] or 'Unknown'
            total = row[1]
            converted = row[2]
            avg_score = row[3] or 0
            
            sources.append({
                'name': source_name,
                'total': total,
                'converted': converted,
                'conversion_rate': round((converted / total * 100) if total > 0 else 0, 1),
                'avg_score': round(avg_score, 1)
            })
        
        return {
            'sources': sources,
            'total_sources': len(sources)
        }
        
    except Exception as e:
        logger.error(f"Error generating source data: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Failed to generate source data: {str(e)}")


@router.get("/status-distribution")
async def get_status_distribution(
    days: Optional[int] = None,
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current distribution of leads across statuses.
    """
    try:
        # Build query
        query = select(
            Lead.status,
            func.count(Lead.id).label('count')
        ).where(
            Lead.tenant_id == str(current_user.tenant_id)
        )
        
        if days:
            start_date = datetime.utcnow() - timedelta(days=days)
            query = query.where(Lead.created_at >= start_date)
        
        query = query.group_by(Lead.status)
        
        result = await db.execute(query)
        rows = result.all()
        
        # Format data with colors
        status_colors = {
            'new': '#667eea',
            'contacted': '#f59e0b',
            'qualified': '#8b5cf6',
            'converted': '#10b981',
            'rejected': '#ef4444',
            'nurture': '#06b6d4'
        }
        
        total = sum(row[1] for row in rows)
        distribution = []
        
        for row in rows:
            status = row[0] or 'unknown'
            count = row[1]
            
            distribution.append({
                'status': status.title(),
                'count': count,
                'percentage': round((count / total * 100) if total > 0 else 0, 1),
                'color': status_colors.get(status, '#6b7280')
            })
        
        # Sort by count descending
        distribution.sort(key=lambda x: x['count'], reverse=True)
        
        return {
            'distribution': distribution,
            'total': total
        }
        
    except Exception as e:
        logger.error(f"Error generating status distribution: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Failed to generate distribution: {str(e)}")

@router.get("/lead-age-advanced")
async def get_lead_age_advanced(
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """
    NEW: Advanced lead age analysis with detailed breakdowns.
    """
    try:
        # Get all leads with age calculation
        age_query = select(
            Lead.id,
            Lead.status,
            Lead.source_name,
            extract('epoch', func.now() - Lead.created_at).label('age_seconds')
        ).where(
            Lead.tenant_id == str(current_user.tenant_id)
        )
        
        result = await db.execute(age_query)
        rows = result.all()
        
        # Define age ranges
        age_ranges = [
            {'label': '0-7 days', 'min': 0, 'max': 7, 'key': '0-7'},
            {'label': '8-14 days', 'min': 8, 'max': 14, 'key': '8-14'},
            {'label': '15-30 days', 'min': 15, 'max': 30, 'key': '15-30'},
            {'label': '31-60 days', 'min': 31, 'max': 60, 'key': '31-60'},
            {'label': '60+ days', 'min': 61, 'max': 999999, 'key': '60+'}
        ]
        
        # Age distribution
        age_distribution = []
        for age_range in age_ranges:
            count = 0
            for row in rows:
                age_days = row[3] / 86400
                if age_range['min'] <= age_days <= age_range['max']:
                    count += 1
            
            age_distribution.append({
                'range': age_range['label'],
                'count': count,
                'percentage': round((count / len(rows) * 100) if rows else 0, 1)
            })
        
        # Average age by status
        status_ages = {}
        for row in rows:
            status = row[1] or 'unknown'
            age_days = row[3] / 86400
            
            if status not in status_ages:
                status_ages[status] = []
            status_ages[status].append(age_days)
        
        avg_by_status = []
        for status, ages in status_ages.items():
            avg_by_status.append({
                'status': status.title(),
                'avg_age_days': round(sum(ages) / len(ages), 1),
                'count': len(ages),
                'oldest': round(max(ages), 1),
                'newest': round(min(ages), 1)
            })
        
        # Average age by source
        source_ages = {}
        for row in rows:
            source = row[2] or 'Unknown'
            age_days = row[3] / 86400
            
            if source not in source_ages:
                source_ages[source] = []
            source_ages[source].append(age_days)
        
        avg_by_source = []
        for source, ages in source_ages.items():
            avg_by_source.append({
                'source': source,
                'avg_age_days': round(sum(ages) / len(ages), 1),
                'count': len(ages)
            })
        
        # Overall metrics
        all_ages = [row[3] / 86400 for row in rows]
        overall_avg = round(sum(all_ages) / len(all_ages), 1) if all_ages else 0
        
        return {
            'age_distribution': age_distribution,
            'avg_by_status': avg_by_status,
            'avg_by_source': avg_by_source,
            'overall_avg_age': overall_avg,
            'total_leads': len(rows),
            'oldest_lead_days': round(max(all_ages), 1) if all_ages else 0,
            'newest_lead_days': round(min(all_ages), 1) if all_ages else 0
        }
        
    except Exception as e:
        logger.error(f"Error generating lead age data: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Failed to generate age data: {str(e)}")


@router.get("/conversion-funnel")
async def get_conversion_funnel_advanced(
    days: int = 30,
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """
    NEW: Advanced conversion funnel with stage-to-stage conversion rates.
    Different from pipeline funnel - focuses on conversion metrics.
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get counts for each status
        status_query = select(
            Lead.status,
            func.count(Lead.id).label('count')
        ).where(
            and_(
                Lead.tenant_id == str(current_user.tenant_id),
                Lead.created_at >= start_date
            )
        ).group_by(Lead.status)
        
        result = await db.execute(status_query)
        status_counts = {row[0]: row[1] for row in result.all()}
        
        # Define conversion stages with colors
        stages = [
            {'name': 'Imported', 'status': ['new', 'pending_review'], 'color': '#667eea'},
            {'name': 'Reviewed', 'status': ['approved', 'rejected'], 'color': '#f59e0b'},
            {'name': 'Approved', 'status': ['approved'], 'color': '#10b981'},
            {'name': 'Rejected', 'status': ['rejected'], 'color': '#ef4444'},
        ]
        
        # Calculate funnel data
        funnel = []
        for i, stage in enumerate(stages):
            count = sum(status_counts.get(s, 0) for s in stage['status'])
            total = sum(status_counts.values())
            
            funnel.append({
                'stage': stage['name'],
                'count': count,
                'percentage': round((count / total * 100) if total > 0 else 0, 1),
                'color': stage['color']
            })
        
        # Calculate conversion rates between stages
        for i in range(len(funnel) - 1):
            current_count = funnel[i]['count']
            next_count = funnel[i + 1]['count']
            funnel[i]['conversion_to_next'] = round(
                (next_count / current_count * 100) if current_count > 0 else 0,
                1
            )
        
        return {
            'funnel': funnel,
            'total_leads': sum(status_counts.values()),
            'timeframe_days': days,
            'approval_rate': round((status_counts.get('approved', 0) / sum(status_counts.values()) * 100) if sum(status_counts.values()) > 0 else 0, 1),
            'rejection_rate': round((status_counts.get('rejected', 0) / sum(status_counts.values()) * 100) if sum(status_counts.values()) > 0 else 0, 1)
        }
        
    except Exception as e:
        logger.error(f"Error generating conversion funnel: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Failed to generate funnel: {str(e)}")


@router.get("/summary-enhanced")
async def get_summary_enhanced(
    days: int = 30,
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """
    NEW: Enhanced summary with period-over-period comparisons.
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        previous_start = start_date - timedelta(days=days)
        
        # Current period
        current_query = select(
            func.count(Lead.id).label('total'),
            func.count(case((Lead.status == 'approved', 1))).label('approved'),
            func.count(case((Lead.status == 'pending_review', 1))).label('pending'),
            func.avg(Lead.fit_score).label('avg_score')
        ).where(
            and_(
                Lead.tenant_id == str(current_user.tenant_id),
                Lead.created_at >= start_date
            )
        )
        
        current_result = await db.execute(current_query)
        current = current_result.first()
        
        # Previous period
        previous_query = select(
            func.count(Lead.id).label('total'),
            func.count(case((Lead.status == 'approved', 1))).label('approved'),
            func.count(case((Lead.status == 'pending_review', 1))).label('pending')
        ).where(
            and_(
                Lead.tenant_id == str(current_user.tenant_id),
                Lead.created_at >= previous_start,
                Lead.created_at < start_date
            )
        )
        
        previous_result = await db.execute(previous_query)
        previous = previous_result.first()
        
        # Calculate changes
        def calc_change(current_val, previous_val):
            if previous_val == 0:
                return 100 if current_val > 0 else 0
            return round((current_val - previous_val) / previous_val * 100, 1)
        
        return {
            'current': {
                'total_leads': current[0],
                'approved': current[1],
                'pending_review': current[2],
                'avg_fit_score': round(current[3] or 0, 1),
                'approval_rate': round((current[1] / current[0] * 100) if current[0] > 0 else 0, 1)
            },
            'previous': {
                'total_leads': previous[0],
                'approved': previous[1],
                'pending_review': previous[2]
            },
            'changes': {
                'total_leads': calc_change(current[0], previous[0]),
                'approved': calc_change(current[1], previous[1]),
                'pending_review': calc_change(current[2], previous[2])
            },
            'timeframe_days': days
        }
        
    except Exception as e:
        logger.error(f"Error generating enhanced summary: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Failed to generate summary: {str(e)}")

@router.get("//lead-age")
async def get_lead_age_analysis(
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """
    Analyze how long leads have been in the pipeline and in each status.
    """
    try:
        # Get all leads with age calculation
        age_query = select(
            Lead.status,
            extract('epoch', func.now() - Lead.created_at).label('age_seconds')
        ).where(
            Lead.tenant_id == str(current_user.tenant_id)
        )
        
        result = await db.execute(age_query)
        rows = result.all()
        
        # Group by age ranges
        age_ranges = [
            {'label': '0-7 days', 'min': 0, 'max': 7},
            {'label': '8-14 days', 'min': 8, 'max': 14},
            {'label': '15-30 days', 'min': 15, 'max': 30},
            {'label': '31-60 days', 'min': 31, 'max': 60},
            {'label': '60+ days', 'min': 61, 'max': 999999}
        ]
        
        # Count leads in each age range
        age_distribution = []
        for age_range in age_ranges:
            count = 0
            for row in rows:
                age_days = row[1] / 86400  # Convert seconds to days
                if age_range['min'] <= age_days <= age_range['max']:
                    count += 1
            
            age_distribution.append({
                'range': age_range['label'],
                'count': count,
                'percentage': round((count / len(rows) * 100) if rows else 0, 1)
            })
        
        # Calculate average age by status
        status_ages = {}
        for row in rows:
            status = row[0] or 'unknown'
            age_days = row[1] / 86400
            
            if status not in status_ages:
                status_ages[status] = []
            status_ages[status].append(age_days)
        
        avg_by_status = []
        for status, ages in status_ages.items():
            avg_by_status.append({
                'status': status.title(),
                'avg_age_days': round(sum(ages) / len(ages), 1),
                'count': len(ages)
            })
        
        return {
            'age_distribution': age_distribution,
            'avg_by_status': avg_by_status,
            'total_leads': len(rows)
        }
        
    except Exception as e:
        logger.error(f"Error generating lead age data: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Failed to generate age data: {str(e)}")


@router.get("//summary")
async def get_analytics_summary(
    days: int = 30,
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive analytics summary with key metrics.
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        previous_start = start_date - timedelta(days=days)
        
        # Current period metrics
        current_query = select(
            func.count(Lead.id).label('total'),
            func.count(case((Lead.status == 'converted', 1))).label('converted'),
            func.avg(Lead.fit_score).label('avg_score')
        ).where(
            and_(
                Lead.tenant_id == str(current_user.tenant_id),
                Lead.created_at >= start_date
            )
        )
        
        current_result = await db.execute(current_query)
        current = current_result.first()
        
        # Previous period metrics
        previous_query = select(
            func.count(Lead.id).label('total'),
            func.count(case((Lead.status == 'converted', 1))).label('converted')
        ).where(
            and_(
                Lead.tenant_id == str(current_user.tenant_id),
                Lead.created_at >= previous_start,
                Lead.created_at < start_date
            )
        )
        
        previous_result = await db.execute(previous_query)
        previous = previous_result.first()
        
        # Calculate changes
        total_change = current[0] - previous[0]
        total_change_pct = round((total_change / previous[0] * 100) if previous[0] > 0 else 0, 1)
        
        converted_change = current[1] - previous[1]
        
        conversion_rate = round((current[1] / current[0] * 100) if current[0] > 0 else 0, 1)
        prev_conversion_rate = round((previous[1] / previous[0] * 100) if previous[0] > 0 else 0, 1)
        conversion_change = round(conversion_rate - prev_conversion_rate, 1)
        
        return {
            'timeframe_days': days,
            'total_leads': current[0],
            'total_change': total_change,
            'total_change_pct': total_change_pct,
            'converted': current[1],
            'converted_change': converted_change,
            'conversion_rate': conversion_rate,
            'conversion_change': conversion_change,
            'avg_score': round(current[2] or 0, 1),
            'period_comparison': {
                'current': {
                    'start': start_date.isoformat(),
                    'end': datetime.utcnow().isoformat(),
                    'leads': current[0],
                    'converted': current[1]
                },
                'previous': {
                    'start': previous_start.isoformat(),
                    'end': start_date.isoformat(),
                    'leads': previous[0],
                    'converted': previous[1]
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating analytics summary: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Failed to generate summary: {str(e)}")


@router.get("/dashboard")
async def get_dashboard_stats(
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard statistics."""
    
    tenant_id = current_user.tenant_id
    today = datetime.utcnow().date()
    
    # Total leads
    result = await db.execute(
        select(func.count(Lead.id)).where(Lead.tenant_id == tenant_id)
    )
    total_leads = result.scalar() or 0
    
    # Pending review
    result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.tenant_id == tenant_id, Lead.status == 'pending_review')
        )
    )
    pending_review = result.scalar() or 0
    
    # Verified
    result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.tenant_id == tenant_id, Lead.status == 'verified')
        )
    )
    verified = result.scalar() or 0
    
    # Rejected
    result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.tenant_id == tenant_id, Lead.review_decision == 'rejected')
        )
    )
    rejected = result.scalar() or 0
    
    # Today's count
    result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.tenant_id == tenant_id, func.date(Lead.created_at) == today)
        )
    )
    today_count = result.scalar() or 0
    
    # Calculate metrics
    conversion_rate = (verified / total_leads * 100) if total_leads > 0 else 0
    
    # Average score
    result = await db.execute(
        select(func.avg(Lead.fit_score)).where(
            and_(Lead.tenant_id == tenant_id, Lead.fit_score.isnot(None))
        )
    )
    avg_score = result.scalar() or 0
    
    # Growth rate
    week_ago = datetime.utcnow() - timedelta(days=7)
    two_weeks_ago = datetime.utcnow() - timedelta(days=14)
    
    result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.tenant_id == tenant_id, Lead.created_at >= week_ago)
        )
    )
    last_week = result.scalar() or 0
    
    result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.tenant_id == tenant_id, Lead.created_at >= two_weeks_ago, Lead.created_at < week_ago)
        )
    )
    prev_week = result.scalar() or 0
    
    growth_rate = ((last_week - prev_week) / prev_week * 100) if prev_week > 0 else 0
    
    logger.info(f"Dashboard stats requested by {current_user.email}")
    
    return {
        "total_leads": total_leads,
        "pending_review": pending_review,
        "verified": verified,
        "rejected": rejected,
        "today_count": today_count,
        "conversion_rate": round(conversion_rate, 2),
        "avg_score": round(avg_score, 2),
        "growth_rate": round(growth_rate, 2)
    }


@router.get("/pipeline")
async def get_pipeline_stats(
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """Get lead pipeline statistics."""
    
    tenant_id = current_user.tenant_id
    last_24h = datetime.utcnow() - timedelta(hours=24)
    
    # New leads
    result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.tenant_id == tenant_id, Lead.created_at >= last_24h)
        )
    )
    new_leads = result.scalar() or 0
    
    # Enriched
    result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.tenant_id == tenant_id, Lead.company_name.isnot(None))
        )
    )
    enriched = result.scalar() or 0
    
    # Verified
    result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.tenant_id == tenant_id, Lead.email_verified == True)
        )
    )
    verified = result.scalar() or 0
    
    # Pending review
    result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.tenant_id == tenant_id, Lead.status == 'pending_review')
        )
    )
    pending_review = result.scalar() or 0
    
    return {
        "new_leads": new_leads,
        "enriched": enriched,
        "verified": verified,
        "pending_review": pending_review
    }


@router.get("/activity")
async def get_recent_activity(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """Get recent activity feed."""
    
    tenant_id = current_user.tenant_id
    
    # Get recent reviewed leads
    result = await db.execute(
        select(Lead).where(
            and_(Lead.tenant_id == tenant_id, Lead.reviewed_at.isnot(None))
        )
        .order_by(Lead.reviewed_at.desc())
        .limit(limit)
    )
    recent_leads = result.scalars().all()
    
    activity = []
    for lead in recent_leads:
        activity_type = 'reviewed'
        if lead.review_decision == 'approved':
            activity_type = 'verified'
        
        activity.append({
            "id": str(lead.id),
            "type": activity_type,
            "description": f"{lead.email} - {lead.review_decision or 'reviewed'}",
            "timestamp": lead.reviewed_at.isoformat() if lead.reviewed_at else lead.updated_at.isoformat()
        })
    
    # Add recent imports if needed
    if len(activity) < limit:
        remaining = limit - len(activity)
        result = await db.execute(
            select(Lead).where(Lead.tenant_id == tenant_id)
            .order_by(Lead.created_at.desc())
            .limit(remaining)
        )
        recent_imports = result.scalars().all()
        
        for lead in recent_imports:
            if lead.id not in [a["id"] for a in activity]:
                activity.append({
                    "id": str(lead.id),
                    "type": "imported",
                    "description": f"{lead.email} - imported from {lead.source_name or 'unknown'}",
                    "timestamp": lead.created_at.isoformat()
                })
    
    return activity[:limit]

@router.get("/ai-insights")
async def get_ai_insights(
    timeframe_days: int = 7,
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """Get AI-generated insights."""
    try:
        generator = AIInsightsGenerator(db, str(current_user.tenant_id))
        insights = await generator.generate_insights(timeframe_days)
        
        logger.info(f"AI insights requested by {current_user.email}")
        
        return insights
        
    except Exception as e:
        logger.error(f"Error generating AI insights: {e}")
        raise HTTPException(500, f"Failed to generate insights: {str(e)}")

# ============================================
# NEW ENDPOINT FOR CHARTS (7 CHARTS DATA)
# ============================================

class StatusDist(BaseModel):
    status: str
    count: int
    percentage: float


class SourcePerf(BaseModel):
    source: str
    count: int
    avg_fit_score: float
    approval_rate: float


class LeadsTrend(BaseModel):
    date: str
    count: int


class FitScoreDist(BaseModel):
    range: str
    count: int


class PipelineStage(BaseModel):
    stage: str
    count: int
    conversion_rate: Optional[float] = None


class ReviewMetrics(BaseModel):
    date: str
    reviewed: int
    approved: int
    rejected: int
    approval_rate: float


class AnalyticsSummary(BaseModel):
    status_distribution: List[StatusDist]
    source_performance: List[SourcePerf]
    leads_trend: List[LeadsTrend]
    fit_score_distribution: List[FitScoreDist]
    pipeline_funnel: List[PipelineStage]
    deliverability_trend: List[Dict[str, Any]]
    review_performance: List[ReviewMetrics]
    total_leads: int
    total_approved: int
    total_rejected: int
    avg_fit_score: float
    avg_deliverability: float


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: User = Depends(require_view_analytics),
    db: AsyncSession = Depends(get_db)
):
    """Get complete analytics for all 7 charts."""
    
    filters = [Lead.tenant_id == current_user.tenant_id]
    if start_date:
        filters.append(Lead.created_at >= datetime.fromisoformat(start_date))
    if end_date:
        filters.append(Lead.created_at <= datetime.fromisoformat(end_date))
    
    result = await db.execute(select(Lead).where(and_(*filters)))
    all_leads = result.scalars().all()
    total_leads = len(all_leads)
    
    # 1. Status Distribution
    status_counts = {}
    for lead in all_leads:
        status_counts[lead.status] = status_counts.get(lead.status, 0) + 1
    
    status_distribution = [
        StatusDist(
            status=status,
            count=count,
            percentage=round((count / total_leads * 100), 2) if total_leads > 0 else 0
        )
        for status, count in status_counts.items()
    ]
    
    # 2. Source Performance
    source_data = {}
    for lead in all_leads:
        source = lead.source_name or "Unknown"
        if source not in source_data:
            source_data[source] = {"count": 0, "fit_scores": [], "approved": 0, "total_reviewed": 0}
        source_data[source]["count"] += 1
        if lead.fit_score:
            # Normalize fit_score (handle both 0-1 and 0-100 formats)
            score = lead.fit_score if lead.fit_score <= 1 else lead.fit_score / 100
            source_data[source]["fit_scores"].append(score)
        if lead.review_decision == "approved":
            source_data[source]["approved"] += 1
        if lead.review_decision in ["approved", "rejected"]:
            source_data[source]["total_reviewed"] += 1
    
    source_performance = [
        SourcePerf(
            source=source,
            count=data["count"],
            avg_fit_score=round(sum(data["fit_scores"]) / len(data["fit_scores"]), 2) if data["fit_scores"] else 0,
            approval_rate=round((data["approved"] / data["total_reviewed"] * 100), 2) if data["total_reviewed"] > 0 else 0
        )
        for source, data in source_data.items()
    ]
    source_performance.sort(key=lambda x: x.count, reverse=True)
    
    # 3. Leads Trend
    trend_data = {}
    for lead in all_leads:
        date_key = lead.created_at.date().isoformat()
        trend_data[date_key] = trend_data.get(date_key, 0) + 1
    
    leads_trend = [
        LeadsTrend(date=date, count=count)
        for date, count in sorted(trend_data.items())
    ]
    
    # 4. Fit Score Distribution
    fit_ranges = {"0-20%": 0, "21-40%": 0, "41-60%": 0, "61-80%": 0, "81-100%": 0, "No Score": 0}
    for lead in all_leads:
        if lead.fit_score is None:
            fit_ranges["No Score"] += 1
        else:
            # Normalize fit_score (handle both 0-1 and 0-100 formats)
            score = lead.fit_score if lead.fit_score <= 1 else lead.fit_score / 100
            if score <= 0.2:
                fit_ranges["0-20%"] += 1
            elif score <= 0.4:
                fit_ranges["21-40%"] += 1
            elif score <= 0.6:
                fit_ranges["41-60%"] += 1
            elif score <= 0.8:
                fit_ranges["61-80%"] += 1
            else:
                fit_ranges["81-100%"] += 1
    
    fit_score_distribution = [
        FitScoreDist(range=range_name, count=count)
        for range_name, count in fit_ranges.items()
    ]
    
    # 5. Pipeline Funnel
    pipeline_stages = {
        "new": len([l for l in all_leads if l.status == "new"]),
        "enriched": len([l for l in all_leads if l.status == "enriched"]),
        "verified": len([l for l in all_leads if l.status == "verified"]),
        "pending_review": len([l for l in all_leads if l.status == "pending_review"]),
        "approved": len([l for l in all_leads if l.status == "approved"]),
    }
    
    pipeline_funnel = []
    prev_count = total_leads
    for stage, count in pipeline_stages.items():
        conversion = round((count / prev_count * 100), 2) if prev_count > 0 else 0
        pipeline_funnel.append(
            PipelineStage(
                stage=stage.replace("_", " ").title(),
                count=count,
                conversion_rate=conversion
            )
        )
        prev_count = count if count > 0 else prev_count
    
    # 6. Deliverability Trend
    deliverability_by_date = {}
    for lead in all_leads:
        if lead.email_deliverability_score:
            date_key = lead.created_at.date().isoformat()
            if date_key not in deliverability_by_date:
                deliverability_by_date[date_key] = []
            deliverability_by_date[date_key].append(lead.email_deliverability_score)
    
    deliverability_trend = [
        {
            "date": date,
            "avg_score": round(sum(scores) / len(scores), 2),
            "count": len(scores)
        }
        for date, scores in sorted(deliverability_by_date.items())
    ]
    
    # 7. Review Performance
    review_by_date = {}
    for lead in all_leads:
        if lead.reviewed_at:
            date_key = lead.reviewed_at.date().isoformat()
            if date_key not in review_by_date:
                review_by_date[date_key] = {"reviewed": 0, "approved": 0, "rejected": 0}
            review_by_date[date_key]["reviewed"] += 1
            if lead.review_decision == "approved":
                review_by_date[date_key]["approved"] += 1
            elif lead.review_decision == "rejected":
                review_by_date[date_key]["rejected"] += 1
    
    review_performance = [
        ReviewMetrics(
            date=date,
            reviewed=data["reviewed"],
            approved=data["approved"],
            rejected=data["rejected"],
            approval_rate=round((data["approved"] / data["reviewed"] * 100), 2) if data["reviewed"] > 0 else 0
        )
        for date, data in sorted(review_by_date.items())
    ]
    
    # Summary stats
    total_approved = len([l for l in all_leads if l.review_decision == "approved"])
    total_rejected = len([l for l in all_leads if l.review_decision == "rejected"])
    
    # Normalize fit_scores (handle both 0-1 and 0-100 formats)
    fit_scores = []
    for lead in all_leads:
        if lead.fit_score:
            score = lead.fit_score
            # If score > 1, it's in 0-100 format, convert to 0-1
            if score > 1:
                score = score / 100
            fit_scores.append(score)
    
    avg_fit_score = round(sum(fit_scores) / len(fit_scores), 2) if fit_scores else 0
    deliverability_scores = [l.email_deliverability_score for l in all_leads if l.email_deliverability_score]
    avg_deliverability = round(sum(deliverability_scores) / len(deliverability_scores), 2) if deliverability_scores else 0
    
    logger.info(f"Analytics summary requested by {current_user.email}")
    
    return AnalyticsSummary(
        status_distribution=status_distribution,
        source_performance=source_performance,
        leads_trend=leads_trend,
        fit_score_distribution=fit_score_distribution,
        pipeline_funnel=pipeline_funnel,
        deliverability_trend=deliverability_trend,
        review_performance=review_performance,
        total_leads=total_leads,
        total_approved=total_approved,
        total_rejected=total_rejected,
        avg_fit_score=avg_fit_score,
        avg_deliverability=avg_deliverability
    )