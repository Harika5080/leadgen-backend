"""AI-powered insights generator for lead analytics - CUSTOMIZED VERSION."""

from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy import func, and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Lead, AuditLog
import logging

logger = logging.getLogger(__name__)


class AIInsightsGenerator:
    """Generate AI-powered insights from lead data."""
    
    # 🎨 CUSTOMIZATION SETTINGS - Edit these to tune insights!
    SETTINGS = {
        # Volume tracking
        'show_volume_insights': True,
        'significant_volume_change': 5,  # Show if volume changes by 5+ leads
        
        # Growth tracking
        'show_growth_insights': True,
        'min_leads_for_growth': 10,  # Need 10+ leads to show growth trends
        
        # Source analysis
        'show_source_insights': True,
        'min_leads_per_source': 3,  # Need 3+ leads from a source to analyze
        'significant_source_change': 30,  # % change to show insight
        
        # Industry analysis
        'show_industry_insights': True,
        'min_leads_per_industry': 5,  # Need 5+ leads in industry to analyze
        
        # Quality recommendations
        'show_quality_insights': True,
        'quality_score_threshold': 70,  # Consider "high quality" if >= 70
        'min_quality_leads': 3,  # Show if 3+ high quality leads
        
        # Stale lead warnings
        'show_stale_warnings': True,
        'stale_days': 30,  # Leads older than 30 days without action
        'min_stale_for_warning': 10,  # Warn if 10+ stale leads
        
        # Status progression
        'show_status_insights': True,
        'min_leads_for_status': 5,  # Need 5+ leads to analyze status
        
        # Milestones
        'show_milestones': True,
        'milestone_levels': [25, 50, 75, 100, 150, 200, 500],
    }
    
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
    
    async def generate_insights(self, timeframe_days: int = 7) -> List[Dict[str, Any]]:
        """Generate all insights for the dashboard."""
        insights = []
        
        # Get data for analysis
        current_period = await self._get_period_data(timeframe_days)
        previous_period = await self._get_period_data(timeframe_days, offset_days=timeframe_days)
        
        # Generate different types of insights
        if self.SETTINGS['show_volume_insights']:
            insights.extend(await self._analyze_volume(current_period, previous_period))
        
        if self.SETTINGS['show_growth_insights']:
            insights.extend(await self._analyze_growth(current_period, previous_period))
        
        if self.SETTINGS['show_source_insights']:
            insights.extend(await self._analyze_sources(current_period, previous_period))
        
        if self.SETTINGS['show_industry_insights']:
            insights.extend(await self._analyze_industries(current_period, previous_period))
        
        if self.SETTINGS['show_status_insights']:
            insights.extend(await self._analyze_status_progression(current_period, previous_period))
        
        if self.SETTINGS['show_quality_insights']:
            insights.extend(await self._generate_quality_recommendations(current_period))
        
        if self.SETTINGS['show_stale_warnings']:
            insights.extend(await self._check_stale_leads(current_period))
        
        if self.SETTINGS['show_milestones']:
            insights.extend(await self._identify_milestones(current_period, previous_period))
        
        # Sort by priority and timestamp
        insights.sort(key=lambda x: (
            {'high': 0, 'medium': 1, 'low': 2}[x['priority']],
            x['timestamp']
        ), reverse=True)
        
        return insights[:10]  # Return top 10 insights
    
    async def _get_period_data(self, days: int, offset_days: int = 0) -> Dict[str, Any]:
        """Get aggregated data for a time period."""
        end_date = datetime.utcnow() - timedelta(days=offset_days)
        start_date = end_date - timedelta(days=days)
        
        # Total leads
        total_query = select(func.count(Lead.id)).where(
            and_(
                Lead.tenant_id == self.tenant_id,
                Lead.created_at >= start_date,
                Lead.created_at < end_date
            )
        )
        total_result = await self.db.execute(total_query)
        total = total_result.scalar() or 0
        
        # Status breakdown
        status_query = select(
            Lead.status,
            func.count(Lead.id).label('count')
        ).where(
            and_(
                Lead.tenant_id == self.tenant_id,
                Lead.created_at >= start_date,
                Lead.created_at < end_date
            )
        ).group_by(Lead.status)
        
        status_result = await self.db.execute(status_query)
        statuses = {row[0]: row[1] for row in status_result.all()}
        
        # By source analysis
        source_query = select(
            Lead.source_name,
            func.count(Lead.id).label('count')
        ).where(
            and_(
                Lead.tenant_id == self.tenant_id,
                Lead.created_at >= start_date,
                Lead.created_at < end_date,
                Lead.source_name.isnot(None)
            )
        ).group_by(Lead.source_name)
        
        source_result = await self.db.execute(source_query)
        sources = source_result.all()
        
        # By industry analysis
        industry_query = select(
            Lead.company_industry,
            func.count(Lead.id).label('count')
        ).where(
            and_(
                Lead.tenant_id == self.tenant_id,
                Lead.created_at >= start_date,
                Lead.created_at < end_date,
                Lead.company_industry.isnot(None)
            )
        ).group_by(Lead.company_industry)
        
        industry_result = await self.db.execute(industry_query)
        industries = industry_result.all()
        
        return {
            'start_date': start_date,
            'end_date': end_date,
            'total_leads': total,
            'statuses': statuses,
            'sources': sources,
            'industries': industries,
        }
    
    async def _analyze_volume(
        self,
        current: Dict[str, Any],
        previous: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Analyze lead volume trends."""
        insights = []
        
        current_total = current['total_leads']
        previous_total = previous['total_leads']
        change = current_total - previous_total
        
        if abs(change) >= self.SETTINGS['significant_volume_change']:
            change_pct = (change / previous_total * 100) if previous_total > 0 else 100
            
            insights.append({
                'id': f'volume_trend_{datetime.utcnow().isoformat()}',
                'type': 'trend' if change > 0 else 'anomaly',
                'priority': 'high' if abs(change) >= 20 else 'medium',
                'title': f'Lead Volume {"Increased" if change > 0 else "Decreased"} by {abs(change)}',
                'description': (
                    f'You received {current_total} leads this week, '
                    f'{"up" if change > 0 else "down"} {abs(change)} ({abs(change_pct):.0f}%) from last week. '
                    f'{"Great job on lead generation!" if change > 0 else "Consider reviewing your lead sources."}'
                ),
                'metric': {
                    'value': f'{change:+d}',
                    'change': change
                },
                'action': {
                    'label': 'View Leads' if change > 0 else 'Check Sources',
                    'url': '/leads' if change > 0 else '/connectors'
                },
                'timestamp': datetime.utcnow().isoformat()
            })
        
        return insights
    
    async def _analyze_growth(
        self,
        current: Dict[str, Any],
        previous: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Analyze overall pipeline growth."""
        insights = []
        
        if current['total_leads'] >= self.SETTINGS['min_leads_for_growth']:
            growth = current['total_leads'] - previous['total_leads']
            
            if growth > 0:
                insights.append({
                    'id': f'growth_status_{datetime.utcnow().isoformat()}',
                    'type': 'trend',
                    'priority': 'low',
                    'title': f'Pipeline Growing: {current["total_leads"]} Total Leads',
                    'description': f'Added {growth} new {"lead" if growth == 1 else "leads"} this week. Your pipeline is growing steadily!',
                    'metric': {
                        'value': f'+{growth}',
                        'change': growth
                    },
                    'action': {
                        'label': 'View All Leads',
                        'url': '/leads'
                    },
                    'timestamp': datetime.utcnow().isoformat()
                })
        
        return insights
    
    async def _analyze_sources(
        self,
        current: Dict[str, Any],
        previous: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Analyze lead source performance."""
        insights = []
        
        current_sources = {src[0]: src[1] for src in current['sources']}
        prev_sources = {src[0]: src[1] for src in previous['sources']}
        
        for source_name, count in current_sources.items():
            if count >= self.SETTINGS['min_leads_per_source']:
                prev_count = prev_sources.get(source_name, 0)
                
                if prev_count > 0:
                    change_pct = ((count - prev_count) / prev_count * 100)
                    
                    if abs(change_pct) >= self.SETTINGS['significant_source_change']:
                        insights.append({
                            'id': f'source_{source_name}_{datetime.utcnow().isoformat()}',
                            'type': 'trend' if change_pct > 0 else 'anomaly',
                            'priority': 'medium',
                            'title': f'{source_name}: {abs(change_pct):.0f}% {"Increase" if change_pct > 0 else "Decrease"}',
                            'description': f'Leads from {source_name} {"increased" if change_pct > 0 else "decreased"} by {abs(change_pct):.0f}% ({count} this week vs {prev_count} last week).',
                            'metric': {
                                'value': f'{change_pct:+.0f}%',
                                'change': change_pct
                            },
                            'action': {
                                'label': 'Review Source',
                                'url': f'/connectors?source={source_name}'
                            },
                            'timestamp': datetime.utcnow().isoformat()
                        })
        
        return insights
    
    async def _analyze_industries(
        self,
        current: Dict[str, Any],
        previous: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Analyze industry performance."""
        insights = []
        
        for industry, count in current['industries']:
            if count >= self.SETTINGS['min_leads_per_industry']:
                insights.append({
                    'id': f'industry_{industry}_{datetime.utcnow().isoformat()}',
                    'type': 'recommendation',
                    'priority': 'low',
                    'title': f'{industry} Sector: {count} Leads',
                    'description': f'You have {count} leads from the {industry} industry. Consider creating targeted campaigns for this segment.',
                    'action': {
                        'label': f'View {industry} Leads',
                        'url': f'/leads?industry={industry}'
                    },
                    'timestamp': datetime.utcnow().isoformat()
                })
        
        return insights[:2]  # Limit to top 2 industries
    
    async def _analyze_status_progression(
        self,
        current: Dict[str, Any],
        previous: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Analyze how leads are progressing through statuses."""
        insights = []
        
        statuses = current['statuses']
        new_count = statuses.get('new', 0)
        
        if new_count >= self.SETTINGS['min_leads_for_status']:
            insights.append({
                'id': f'status_new_{datetime.utcnow().isoformat()}',
                'type': 'recommendation',
                'priority': 'high',
                'title': f'{new_count} Leads Awaiting Action',
                'description': f'You have {new_count} leads in "new" status. Review and progress these leads to keep your pipeline moving.',
                'action': {
                    'label': 'Review Leads',
                    'url': '/leads?status=new'
                },
                'timestamp': datetime.utcnow().isoformat()
            })
        
        return insights
    
    async def _generate_quality_recommendations(self, current: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate recommendations for quality leads."""
        insights = []
        
        # Count leads with quality scores
        quality_query = select(func.count(Lead.id)).where(
            and_(
                Lead.tenant_id == self.tenant_id,
                Lead.fit_score >= self.SETTINGS['quality_score_threshold'],
                Lead.status == 'new',
                Lead.created_at >= current['start_date']
            )
        )
        quality_result = await self.db.execute(quality_query)
        quality_count = quality_result.scalar() or 0
        
        if quality_count >= self.SETTINGS['min_quality_leads']:
            insights.append({
                'id': f'quality_leads_{datetime.utcnow().isoformat()}',
                'type': 'recommendation',
                'priority': 'high',
                'title': f'{quality_count} High-Quality Leads Ready',
                'description': f'You have {quality_count} leads with quality scores above {self.SETTINGS["quality_score_threshold"]}. Prioritize these for outreach.',
                'action': {
                    'label': 'Review Now',
                    'url': f'/leads?min_score={self.SETTINGS["quality_score_threshold"]}'
                },
                'timestamp': datetime.utcnow().isoformat()
            })
        
        return insights
    
    async def _check_stale_leads(self, current: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for stale leads that need attention."""
        insights = []
        
        stale_date = datetime.utcnow() - timedelta(days=self.SETTINGS['stale_days'])
        stale_query = select(func.count(Lead.id)).where(
            and_(
                Lead.tenant_id == self.tenant_id,
                Lead.status == 'new',
                Lead.created_at < stale_date
            )
        )
        stale_result = await self.db.execute(stale_query)
        stale_count = stale_result.scalar() or 0
        
        if stale_count >= self.SETTINGS['min_stale_for_warning']:
            insights.append({
                'id': f'stale_leads_{datetime.utcnow().isoformat()}',
                'type': 'anomaly',
                'priority': 'medium',
                'title': f'{stale_count} Leads Need Attention',
                'description': f'{stale_count} leads have been in "new" status for over {self.SETTINGS["stale_days"]} days. Review or archive them.',
                'action': {
                    'label': 'Review Stale Leads',
                    'url': '/leads?status=new&age=30'
                },
                'timestamp': datetime.utcnow().isoformat()
            })
        
        return insights
    
    async def _identify_milestones(
        self,
        current: Dict[str, Any],
        previous: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Identify and celebrate milestones."""
        insights = []
        
        current_total = current['total_leads']
        previous_total = previous['total_leads']
        
        # Check if we crossed any milestone
        for milestone in self.SETTINGS['milestone_levels']:
            if current_total >= milestone > previous_total:
                insights.append({
                    'id': f'milestone_{milestone}_{datetime.utcnow().isoformat()}',
                    'type': 'achievement',
                    'priority': 'low',
                    'title': f'🎉 {milestone} Leads Milestone!',
                    'description': f'Congratulations! You\'ve reached {current_total} total leads. Keep up the great work!',
                    'timestamp': datetime.utcnow().isoformat()
                })
                break  # Only show one milestone at a time
        
        return insights