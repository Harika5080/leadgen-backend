"""
Text/keyword-based scoring.
"""
from typing import Any, List
from .base import BaseScorer


class TextScorer(BaseScorer):
    """
    Score based on keyword presence in text.
    
    Config format:
    {
        "required_keywords": ["director", "vp", "head"],
        "bonus_keywords": ["senior", "lead"],
        "case_sensitive": false
    }
    """
    
    def calculate_score(self, value: Any) -> float:
        """
        Calculate score based on keyword matches.
        """
        if value is None:
            return 0.0
        
        value_str = str(value)
        case_sensitive = self.config.get("case_sensitive", False)
        
        if not case_sensitive:
            value_str = value_str.lower()
        
        required_keywords = self.config.get("required_keywords", [])
        bonus_keywords = self.config.get("bonus_keywords", [])
        
        if not case_sensitive:
            required_keywords = [k.lower() for k in required_keywords]
            bonus_keywords = [k.lower() for k in bonus_keywords]
        
        # Check required keywords
        required_matches = sum(
            1 for kw in required_keywords if kw in value_str
        )
        
        if not required_keywords:
            required_score = 0.5  # No requirements = neutral
        elif required_matches == 0:
            return 0.0  # Failed requirements
        else:
            required_score = min(1.0, required_matches / len(required_keywords))
        
        # Check bonus keywords
        bonus_matches = sum(
            1 for kw in bonus_keywords if kw in value_str
        )
        
        bonus_score = min(0.2, bonus_matches * 0.1)  # Up to 0.2 bonus
        
        return min(1.0, required_score + bonus_score)
    
    def get_explanation(self, value: Any, score: float) -> str:
        """Explain keyword matches."""
        required = self.config.get("required_keywords", [])
        bonus = self.config.get("bonus_keywords", [])
        
        if score == 0.0:
            return f"No required keywords found in '{value}'"
        elif score >= 0.8:
            return f"Strong match: contains required keywords and bonuses"
        else:
            return f"Partial match in '{value}'"