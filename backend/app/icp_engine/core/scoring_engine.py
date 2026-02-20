"""
Scoring engine for calculating lead fit scores.

Applies scoring rules and calculates weighted overall score.
"""
from typing import Dict, Any, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.models import ICP, ScoringRule
from app.icp_engine.scorers import get_scorer


logger = logging.getLogger(__name__)


class ScoringEngine:
    """
    Calculate lead fit scores based on ICP scoring rules.
    
    Applies all active scoring rules for an ICP and calculates
    a weighted overall score.
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize scoring engine.
        
        Args:
            db: Database session
        """
        self.db = db
    
    async def calculate_fit_score(
        self, 
        icp_id: str, 
        lead_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate fit score for a lead against an ICP.
        
        Args:
            icp_id: ICP ID
            lead_data: Mapped lead data
        
        Returns:
            dict: {
                "overall_score": float (0-100),
                "rule_scores": [
                    {
                        "rule_id": str,
                        "field_name": str,
                        "score": float,
                        "weight": float,
                        "explanation": str
                    }
                ],
                "score_explanation": str,
                "qualified": bool,
                "auto_approved": bool
            }
        """
        try:
            # Load ICP
            icp_stmt = select(ICP).where(ICP.id == icp_id)
            icp_result = await self.db.execute(icp_stmt)
            icp = icp_result.scalars().first()
            
            if not icp:
                logger.error(f"ICP {icp_id} not found")
                return self._default_score()
            
            # Load scoring rules
            rules_stmt = select(ScoringRule).where(
                ScoringRule.icp_id == icp_id,
                ScoringRule.is_active == True
            ).order_by(ScoringRule.weight.desc())
            
            rules_result = await self.db.execute(rules_stmt)
            rules = rules_result.scalars().all()
            
            if not rules:
                logger.warning(f"No scoring rules found for ICP {icp_id}")
                return self._default_score()
            
            # Calculate individual rule scores
            rule_scores = []
            total_weighted_score = 0.0
            total_weight = 0.0
            
            for rule in rules:
                # Get value from lead data
                value = lead_data.get(rule.field_name)
                
                # Create scorer
                try:
                    scorer = get_scorer(rule.scorer_type, rule.config)
                    score = scorer.calculate_score(value)
                    explanation = scorer.get_explanation(value, score)
                except Exception as e:
                    logger.error(f"Error applying rule {rule.id}: {e}")
                    score = 0.0
                    explanation = f"Error: {str(e)}"
                
                # Add to rule scores
                rule_scores.append({
                    "rule_id": str(rule.id),
                    "field_name": rule.field_name,
                    "scorer_type": rule.scorer_type,
                    "score": score,
                    "weight": rule.weight,
                    "explanation": explanation,
                    "value": value
                })
                
                # Add to weighted sum
                total_weighted_score += score * rule.weight
                total_weight += rule.weight
            
            # Calculate overall score
            overall_score = (
                total_weighted_score / total_weight 
                if total_weight > 0 
                else 0.0
            )
            
            # Determine if qualified
            qualified = overall_score >= icp.qualification_threshold
            
            # Determine if auto-approved
            auto_approved = (
                icp.auto_approval_threshold is not None 
                and overall_score >= icp.auto_approval_threshold
            )
            
            # Build explanation
            score_explanation = self._build_explanation(
                overall_score, 
                qualified, 
                auto_approved,
                icp
            )
            
            return {
                "overall_score": round(overall_score, 2),
                "rule_scores": rule_scores,
                "score_explanation": score_explanation,
                "qualified": qualified,
                "auto_approved": auto_approved
            }
        
        except Exception as e:
            logger.error(f"Error calculating fit score: {e}")
            return self._default_score()
    
    def _default_score(self) -> Dict[str, Any]:
        """Return default score when calculation fails."""
        return {
            "overall_score": 0.0,
            "rule_scores": [],
            "score_explanation": "Error calculating score",
            "qualified": False,
            "auto_approved": False
        }
    
    def _build_explanation(
        self, 
        score: float, 
        qualified: bool, 
        auto_approved: bool,
        icp: ICP
    ) -> str:
        """Build human-readable score explanation."""
        parts = [f"Overall fit score: {score:.1f}/100"]
        
        if auto_approved:
            parts.append(
                f"✓ Auto-approved (score >= {icp.auto_approval_threshold})"
            )
        elif qualified:
            parts.append(
                f"✓ Qualified (score >= {icp.qualification_threshold})"
            )
        else:
            parts.append(
                f"✗ Not qualified (score < {icp.qualification_threshold})"
            )
        
        return ". ".join(parts)
    
    async def calculate_scores_for_multiple_icps(
        self, 
        icp_ids: List[str], 
        lead_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Calculate scores for multiple ICPs.
        
        Args:
            icp_ids: List of ICP IDs
            lead_data: Mapped lead data
        
        Returns:
            List of score results
        """
        results = []
        
        for icp_id in icp_ids:
            score_result = await self.calculate_fit_score(icp_id, lead_data)
            score_result["icp_id"] = icp_id
            results.append(score_result)
        
        return results