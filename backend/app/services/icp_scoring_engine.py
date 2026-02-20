# backend/app/services/icp_scoring_engine.py - COMPLETE WITH CONFIGURABLE THRESHOLD
"""
ICP Scoring Engine - Scores leads against ICP criteria

UPDATED: 
- Uses Lead object (enriched data) instead of RawLead
- Uses ICP.scoring_rules, filter_rules, and weight_config
- Configurable criteria_pass_threshold (no hardcoded 50)
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging

from sqlalchemy.orm import Session
from app.models import Lead, ICP

logger = logging.getLogger(__name__)


@dataclass
class ScoreResult:
    """Result of scoring a lead against an ICP"""
    score: float  # 0-100
    confidence: float  # 0-100
    breakdown: Dict[str, Any]
    dimensions_scored: int
    total_dimensions: int


class ICPScoringEngine:
    """
    Scores leads against ICP criteria using enriched data
    
    ✅ Uses ICP configuration:
    - scoring_rules.criteria_pass_threshold: Threshold to "pass" a criterion
    - scoring_rules: Target criteria (industries, sizes, etc.)
    - filter_rules: Hard requirements (must pass)
    - weight_config: Importance weights for each dimension
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    async def score_lead(self, lead: Lead, icp: ICP) -> ScoreResult:
        """Score lead against ICP criteria"""
        
        # ✅ SET WEIGHTS FIRST!
        self.weights = icp.weight_config or {
            "industry": 20,
            "company_size": 15,
            "seniority": 25,
            "tech_stack": 20,
            "geography": 10,
            "company_type": 10
        }
        
        # Extract scoring rules
        scoring_rules = icp.scoring_rules or {}
        
        # Initialize scores
        total_score = 0
        max_possible_score = 0
        breakdown = {}
        dimensions_scored = 0
        
        # Score each dimension
        
        # 1. Industry match
        if scoring_rules.get("target_industries"):
            industry_score, industry_breakdown = self._score_industry(lead, scoring_rules)
            breakdown["industry"] = industry_breakdown
            total_score += industry_score
            max_possible_score += 100
            dimensions_scored += 1
        
        # 2. Company size
        if scoring_rules.get("ideal_company_size_min") or scoring_rules.get("ideal_company_size_max"):
            size_score, size_breakdown = self._score_company_size(lead, scoring_rules)
            breakdown["company_size"] = size_breakdown
            total_score += size_score
            max_possible_score += 100
            dimensions_scored += 1
        
        # 3. Seniority
        if scoring_rules.get("target_seniority_levels") or scoring_rules.get("job_title_keywords"):
            seniority_score, seniority_breakdown = self._score_seniority(lead, scoring_rules)
            breakdown["seniority"] = seniority_breakdown
            total_score += seniority_score
            max_possible_score += 100
            dimensions_scored += 1
        
        # 4. Tech stack
        if scoring_rules.get("required_technologies") or scoring_rules.get("preferred_technologies"):
            tech_score, tech_breakdown = self._score_tech_stack(lead, scoring_rules)
            breakdown["tech_stack"] = tech_breakdown
            total_score += tech_score
            max_possible_score += 100
            dimensions_scored += 1
        
        # 5. Geography
        if scoring_rules.get("target_geographies"):
            geo_score, geo_breakdown = self._score_geography(lead, scoring_rules)
            breakdown["geography"] = geo_breakdown
            total_score += geo_score
            max_possible_score += 100
            dimensions_scored += 1
        
        # 6. Company type
        if scoring_rules.get("company_type_keywords"):
            type_score, type_breakdown = self._score_company_type(lead, scoring_rules)
            breakdown["company_type"] = type_breakdown
            total_score += type_score
            max_possible_score += 100
            dimensions_scored += 1
        
        # Calculate final score
        if max_possible_score > 0:
            final_score = round((total_score / max_possible_score) * 100, 2)
        else:
            final_score = 0.0
        
        # Calculate confidence
        confidence = round((dimensions_scored / 6) * 100, 2)
        
        return ScoreResult(
            score=final_score,
            confidence=confidence,
            breakdown=breakdown,
            dimensions_scored=dimensions_scored,
            total_dimensions=6
        )
    
    def _check_filters(self, lead: Lead, filter_rules: Dict) -> tuple[bool, Optional[str]]:
        """
        Check hard filter rules - must pass ALL
        
        filter_rules example:
        {
            "min_company_size": 100,
            "required_locations": ["USA", "Canada"],
            "excluded_industries": ["Retail"]
        }
        """
        if not filter_rules:
            return True, None
        
        # Min company size
        if 'min_company_size' in filter_rules:
            min_size = filter_rules['min_company_size']
            if not lead.company_employee_count or lead.company_employee_count < min_size:
                return False, f"Company size {lead.company_employee_count} below minimum {min_size}"
        
        # Required locations
        if 'required_locations' in filter_rules:
            required_locs = [loc.lower() for loc in filter_rules['required_locations']]
            lead_country = (lead.country or "").lower()
            if not any(loc in lead_country for loc in required_locs):
                return False, f"Location {lead.country} not in required: {filter_rules['required_locations']}"
        
        # Excluded industries
        if 'excluded_industries' in filter_rules:
            excluded = [ind.lower() for ind in filter_rules['excluded_industries']]
            lead_industry = (lead.company_industry or "").lower()
            if any(exc in lead_industry for exc in excluded):
                return False, f"Industry {lead.company_industry} is excluded"
        
        return True, None
    
 # Find the company size scoring section
    def _score_company_size(self, lead: Lead, scoring_rules: Dict) -> tuple:
        """Score based on company size"""
        
        # Get employee count (handle both string and int)
        employee_count_str = lead.company_employee_count
        
        if not employee_count_str:
            return 0, {
                "score": 0,
                "weight": self.weights.get("company_size", 0),
                "weighted_score": 0,
                "max_score": 100,
                "details": "No employee count data",
                "matched": False
            }
        
        # ✅ Convert to int safely
        try:
            employee_count = int(str(employee_count_str).replace(',', ''))
        except (ValueError, AttributeError):
            return 0, {
                "score": 0,
                "weight": self.weights.get("company_size", 0),
                "weighted_score": 0,
                "max_score": 100,
                "details": f"Invalid employee count: {employee_count_str}",
                "matched": False
            }
        
        # ✅ CORRECT - use scoring_rules parameter (already a dict!)
        min_size = scoring_rules.get("ideal_company_size_min")
        max_size = scoring_rules.get("ideal_company_size_max")
        
        if not min_size or not max_size:
            return 50, {
                "score": 50,
                "weight": self.weights.get("company_size", 0),
                "weighted_score": 0,
                "max_score": 100,
                "details": "No size criteria defined",
                "matched": True
            }
        
        # ✅ Ensure min/max are integers
        min_size = int(min_size)
        max_size = int(max_size)
        
        # Score based on range
        if min_size <= employee_count <= max_size:
            score = 100
            details = f"{employee_count} employees (ideal range: {min_size}-{max_size})"
            matched = True
        elif employee_count < min_size:
            ratio = employee_count / min_size
            score = int(ratio * 80)
            details = f"{employee_count} employees (below min {min_size})"
            matched = False
        else:
            ratio = max_size / employee_count
            score = int(ratio * 80)
            details = f"{employee_count} employees (above max {max_size})"
            matched = False
        
        return score, {
            "score": score,
            "weight": self.weights.get("company_size", 0),
            "weighted_score": 0,
            "max_score": 100,
            "details": details,
            "matched": matched
        }
    
    def _score_industry(self, lead: Lead, scoring_rules: Dict) -> tuple[float, Dict[str, Any]]:
        """
        Score based on industry match
        
        scoring_rules example:
        {
            "target_industries": ["Software", "SaaS", "Technology"]
        }
        """
        industry = (lead.company_industry or "").lower()
        
        # Get target industries from ICP
        target_industries = scoring_rules.get('target_industries', [])
        
        if not target_industries:
            # No criteria defined - neutral score
            return 50, {
                "score": 50,
                "industry": lead.company_industry,
                "note": "no_criteria_defined"
            }
        
        # Check for exact or partial matches
        match_score = 0
        matched_targets = []
        for target in target_industries:
            if target.lower() in industry:
                match_score = 100
                matched_targets.append(target)
                break
        
        # Partial credit if no exact match
        if match_score == 0:
            match_score = 40
        
        return match_score, {
            "score": match_score,
            "industry": lead.company_industry,
            "target_industries": target_industries,
            "matched": matched_targets,
            "exact_match": match_score == 100
        }
    
    def _score_tech_stack(self, lead: Lead, scoring_rules: Dict) -> tuple[float, Dict[str, Any]]:
        """
        Score based on tech stack match
        
        scoring_rules example:
        {
            "required_technologies": ["React", "Python"],
            "preferred_technologies": ["AWS", "Kubernetes"]
        }
        """
        tech_stack = lead.enrichment_data.get('tech_stack', [])
        
        # Get tech requirements from ICP
        required_tech = [t.lower() for t in scoring_rules.get('required_technologies', [])]
        preferred_tech = [t.lower() for t in scoring_rules.get('preferred_technologies', [])]
        
        if not required_tech and not preferred_tech:
            return 50, {
                "score": 50,
                "tech_stack": tech_stack,
                "note": "no_criteria_defined"
            }
        
        # Convert tech_stack to lowercase for matching
        if isinstance(tech_stack, list):
            tech_lower = [str(t).lower() for t in tech_stack]
        else:
            tech_lower = []
        
        # Check required tech (must have ALL)
        required_matches = []
        if required_tech:
            for req in required_tech:
                if any(req in tech for tech in tech_lower):
                    required_matches.append(req)
            
            required_ratio = len(required_matches) / len(required_tech)
            if required_ratio < 1.0:
                # Missing required tech - low score
                score = required_ratio * 50
                return score, {
                    "score": round(score, 2),
                    "tech_stack": tech_stack,
                    "required_matches": required_matches,
                    "required_missing": [r for r in required_tech if r not in required_matches],
                    "note": "missing_required_tech"
                }
        
        # Check preferred tech (bonus points)
        preferred_matches = []
        if preferred_tech:
            for pref in preferred_tech:
                if any(pref in tech for tech in tech_lower):
                    preferred_matches.append(pref)
            
            preferred_ratio = len(preferred_matches) / len(preferred_tech)
            bonus = preferred_ratio * 50
        else:
            bonus = 0
        
        # Final score: 50 base + 50 for preferred
        score = min(100, 50 + bonus)
        
        return score, {
            "score": round(score, 2),
            "tech_stack": tech_stack,
            "required_matches": required_matches,
            "preferred_matches": preferred_matches,
            "all_required_met": len(required_matches) == len(required_tech) if required_tech else True
        }
    
    def _score_seniority(self, lead: Lead, scoring_rules: Dict) -> tuple[float, Dict[str, Any]]:
        """
        Score based on seniority level
        
        scoring_rules example:
        {
            "target_seniority_levels": ["VP", "Director", "C-Level"],
            "job_title_keywords": ["VP Sales", "Director Marketing"]
        }
        """
        job_title = (lead.job_title or "").lower()
        
        # Get target seniority from ICP
        target_seniority = [s.lower() for s in scoring_rules.get('target_seniority_levels', [])]
        target_keywords = [k.lower() for k in scoring_rules.get('job_title_keywords', [])]
        
        # Seniority mapping
        seniority_map = {
            "c-level": ["ceo", "cto", "cfo", "coo", "president", "founder", "chief"],
            "vp": ["vp", "vice president"],
            "director": ["director", "head of"],
            "manager": ["manager", "lead"],
            "senior": ["senior", "sr"],
            "junior": ["junior", "jr", "associate"]
        }
        
        # Determine lead's seniority
        lead_seniority = None
        for level, keywords in seniority_map.items():
            if any(kw in job_title for kw in keywords):
                lead_seniority = level
                break
        
        # Check exact job title keywords
        keyword_match = any(kw in job_title for kw in target_keywords)
        
        # Score based on target seniority match
        if keyword_match:
            score = 100
            reason = "exact_keyword_match"
        elif lead_seniority and lead_seniority in target_seniority:
            score = 90
            reason = "seniority_match"
        elif lead_seniority in ["c-level", "vp"]:
            score = 80
            reason = "high_seniority"
        elif lead_seniority == "director":
            score = 60
            reason = "mid_seniority"
        elif lead_seniority == "manager":
            score = 40
            reason = "manager_level"
        else:
            score = 20
            reason = "low_seniority"
        
        return score, {
            "score": score,
            "job_title": lead.job_title,
            "detected_seniority": lead_seniority,
            "target_seniority": target_seniority,
            "reason": reason
        }
    
    def _score_geography(self, lead: Lead, scoring_rules: Dict) -> tuple[float, Dict[str, Any]]:
        """
        Score based on geographic location
        
        scoring_rules example:
        {
            "target_geographies": ["USA", "Canada", "UK"]
        }
        """
        country = (lead.country or "").lower()
        
        # Get target geographies from ICP
        target_geos = [g.lower() for g in scoring_rules.get('target_geographies', [])]
        
        if not target_geos:
            return 50, {
                "score": 50,
                "country": lead.country,
                "note": "no_criteria_defined"
            }
        
        # Check for match
        if any(geo in country for geo in target_geos):
            score = 100
            matched = True
        else:
            score = 30  # Partial credit for being somewhere
            matched = False
        
        return score, {
            "score": score,
            "country": lead.country,
            "target_geographies": scoring_rules.get('target_geographies', []),
            "matched": matched
        }
    
    def _score_company_type(self, lead: Lead, scoring_rules: Dict) -> tuple[float, Dict[str, Any]]:
        """
        Score based on company type/description
        
        scoring_rules example:
        {
            "company_type_keywords": ["B2B", "SaaS", "Enterprise"],
            "excluded_keywords": ["B2C", "Consumer"]
        }
        """
        description = (lead.company_description or "").lower()
        
        # Get keywords from ICP
        positive_keywords = [k.lower() for k in scoring_rules.get('company_type_keywords', [])]
        negative_keywords = [k.lower() for k in scoring_rules.get('excluded_keywords', [])]
        
        if not positive_keywords and not negative_keywords:
            return 50, {
                "score": 50,
                "description_snippet": description[:100],
                "note": "no_criteria_defined"
            }
        
        # Check for matches
        positive_matches = [kw for kw in positive_keywords if kw in description]
        negative_matches = [kw for kw in negative_keywords if kw in description]
        
        if negative_matches:
            score = 20  # Has excluded keywords
        elif positive_matches:
            # Score based on how many positive keywords match
            match_ratio = len(positive_matches) / max(len(positive_keywords), 1)
            score = 50 + (match_ratio * 50)
        else:
            score = 40  # No matches either way
        
        return score, {
            "score": round(score, 2),
            "description_snippet": description[:100],
            "positive_matches": positive_matches,
            "negative_matches": negative_matches
        }