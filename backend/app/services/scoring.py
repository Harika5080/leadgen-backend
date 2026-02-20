"""Lead scoring service to calculate lead quality scores."""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class LeadScoringService:
    """Calculate lead quality fit scores."""
    
    # Job title seniority levels and their scores
    SENIORITY_SCORES = {
        'c-level': 100,  # CEO, CTO, CFO, CMO, COO
        'vp': 90,        # VP, Vice President
        'director': 80,  # Director
        'manager': 70,   # Manager
        'lead': 60,      # Team Lead, Tech Lead
        'senior': 50,    # Senior Engineer, Senior Analyst
        'mid': 40,       # Engineer, Analyst (no prefix)
        'junior': 30,    # Junior, Associate
        'intern': 20,    # Intern, Trainee
        'unknown': 10    # Cannot determine
    }
    
    # Job title keywords for seniority detection
    SENIORITY_KEYWORDS = {
        'c-level': ['ceo', 'cto', 'cfo', 'cmo', 'coo', 'chief', 'president', 'founder', 'owner'],
        'vp': ['vp', 'vice president', 'v.p.'],
        'director': ['director', 'head of'],
        'manager': ['manager', 'mgr'],
        'lead': ['lead', 'principal'],
        'senior': ['senior', 'sr.', 'sr '],
        'junior': ['junior', 'jr.', 'jr ', 'associate'],
        'intern': ['intern', 'trainee', 'apprentice']
    }
    
    @staticmethod
    def detect_seniority(job_title: Optional[str]) -> str:
        """Detect seniority level from job title."""
        if not job_title:
            return 'unknown'
        
        title_lower = job_title.lower()
        
        # Check each seniority level
        for level, keywords in LeadScoringService.SENIORITY_KEYWORDS.items():
            if any(keyword in title_lower for keyword in keywords):
                return level
        
        return 'mid'  # Default to mid-level if no keywords match
    
    @staticmethod
    def calculate_enrichment_score(lead_data: Dict[str, Any]) -> float:
        """
        Calculate score based on data completeness.
        More complete profiles score higher.
        """
        fields_to_check = [
            'first_name',
            'last_name',
            'phone',
            'job_title',
            'linkedin_url',
            'company_name',
            'company_website',
            'company_industry'
        ]
        
        filled_fields = sum(1 for field in fields_to_check if lead_data.get(field))
        total_fields = len(fields_to_check)
        
        return (filled_fields / total_fields) * 100
    
    @staticmethod
    def calculate_email_score(email_verified: bool, deliverability_score: Optional[float]) -> float:
        """
        Calculate score based on email verification.
        """
        if not email_verified:
            return 0
        
        if deliverability_score is not None:
            return deliverability_score
        
        return 50  # Default score if verified but no deliverability score
    
    def calculate_fit_score(
        self,
        job_title: Optional[str] = None,
        email_verified: bool = False,
        email_deliverability_score: Optional[float] = None,
        enrichment_data: Optional[Dict[str, Any]] = None,
        source_quality: float = 0.5,
        lead_data: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Calculate overall lead fit score (0-100).
        
        Weighted components:
        - Job title seniority: 30%
        - Email quality: 25%
        - Data completeness: 20%
        - Source quality: 15%
        - Company size/industry fit: 10%
        """
        score = 0.0
        
        # Component 1: Job Title Seniority (30 points)
        seniority = self.detect_seniority(job_title)
        seniority_score = self.SENIORITY_SCORES.get(seniority, 10)
        score += (seniority_score / 100) * 30
        
        # Component 2: Email Quality (25 points)
        email_score = self.calculate_email_score(email_verified, email_deliverability_score)
        score += (email_score / 100) * 25
        
        # Component 3: Data Completeness (20 points)
        if lead_data:
            enrichment_score = self.calculate_enrichment_score(lead_data)
            score += (enrichment_score / 100) * 20
        
        # Component 4: Source Quality (15 points)
        score += source_quality * 15
        
        # Component 5: Company Fit (10 points)
        # This can be expanded with industry/size matching
        if enrichment_data and enrichment_data.get('company'):
            company_data = enrichment_data['company']
            company_score = 0
            
            # Bonus for known company
            if company_data.get('name'):
                company_score += 5
            
            # Bonus for company size in target range (example: 50-500 employees)
            employee_count = company_data.get('employee_count', 0)
            if 50 <= employee_count <= 500:
                company_score += 5
            
            score += company_score
        
        # Ensure score is between 0 and 100
        return round(min(max(score, 0), 100), 2)


# Singleton instance
scoring_service = LeadScoringService()
