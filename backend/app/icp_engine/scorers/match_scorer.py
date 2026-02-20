"""
Exact match scoring for categorical fields.
"""
from typing import Any, List
from .base import BaseScorer


class MatchScorer(BaseScorer):
    """
    Score based on exact match with allowed values.
    
    Config format:
    {
        "allowed_values": ["Enterprise", "Mid-Market"],
        "case_sensitive": false
    }
    """
    
    def calculate_score(self, value: Any) -> float:
        """
        Return 1.0 if value in allowed_values, else 0.0
        """
        if value is None:
            return 0.0
        
        allowed_values = self.config.get("allowed_values", [])
        case_sensitive = self.config.get("case_sensitive", False)
        
        value_str = str(value)
        
        if not case_sensitive:
            value_str = value_str.lower()
            allowed_values = [str(v).lower() for v in allowed_values]
        
        return 1.0 if value_str in allowed_values else 0.0
    
    def get_explanation(self, value: Any, score: float) -> str:
        """Explain the match result."""
        allowed = self.config.get("allowed_values", [])
        
        if score == 1.0:
            return f"Match: '{value}' is in allowed values"
        else:
            return f"No match: '{value}' not in {allowed}"