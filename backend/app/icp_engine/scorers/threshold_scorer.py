"""
Threshold-based scoring for numeric values.
"""
from typing import Any
from .base import BaseScorer


class ThresholdScorer(BaseScorer):
    """
    Score based on threshold (above/below).
    
    Config format:
    {
        "threshold": 1000,
        "mode": "above"  # or "below"
    }
    """
    
    def calculate_score(self, value: Any) -> float:
        """
        Return 1.0 if passes threshold, else 0.0
        """
        if value is None:
            return 0.0
        
        try:
            value = float(value)
        except (ValueError, TypeError):
            return 0.0
        
        threshold = self.config.get("threshold", 0)
        mode = self.config.get("mode", "above")
        
        if mode == "above":
            return 1.0 if value >= threshold else 0.0
        else:  # below
            return 1.0 if value <= threshold else 0.0
    
    def get_explanation(self, value: Any, score: float) -> str:
        """Explain threshold result."""
        threshold = self.config.get("threshold")
        mode = self.config.get("mode", "above")
        
        if score == 1.0:
            return f"Pass: {value} is {mode} {threshold}"
        else:
            return f"Fail: {value} is not {mode} {threshold}"