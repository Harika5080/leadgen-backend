"""
Range-based scoring for numeric fields.
"""
import math
from typing import Any
from .base import BaseScorer


class RangeScorer(BaseScorer):
    """
    Score based on numeric range with ideal and acceptable zones.
    
    Config format:
    {
        "ideal_min": 100,
        "ideal_max": 500,
        "acceptable_min": 50,
        "acceptable_max": 1000
    }
    """
    
    def calculate_score(self, value: Any) -> float:
        """
        Scoring logic:
        - Perfect (1.0): value in [ideal_min, ideal_max]
        - Good (0.5-1.0): value in [acceptable_min, acceptable_max]
        - Poor (0-0.5): outside acceptable, exponential decay
        """
        if value is None:
            return 0.0
        
        try:
            value = float(value)
        except (ValueError, TypeError):
            return 0.0
        
        ideal_min = self.config.get("ideal_min", 0)
        ideal_max = self.config.get("ideal_max", 1000)
        acceptable_min = self.config.get("acceptable_min", 0)
        acceptable_max = self.config.get("acceptable_max", 10000)
        
        # Perfect score
        if ideal_min <= value <= ideal_max:
            return 1.0
        
        # Good score (interpolated)
        if acceptable_min <= value < ideal_min:
            # Linear interpolation from 0.5 to 1.0
            ratio = (value - acceptable_min) / (ideal_min - acceptable_min)
            return 0.5 + (0.5 * ratio)
        
        if ideal_max < value <= acceptable_max:
            # Linear interpolation from 1.0 to 0.5
            ratio = (acceptable_max - value) / (acceptable_max - ideal_max)
            return 0.5 + (0.5 * ratio)
        
        # Poor score (exponential decay)
        distance = min(
            abs(value - acceptable_min),
            abs(value - acceptable_max)
        )
        
        # Exponential decay: 0.5 * e^(-distance/100)
        return max(0, 0.5 * math.exp(-distance / 100))
    
    def get_explanation(self, value: Any, score: float) -> str:
        """Explain why this score was given."""
        ideal_min = self.config.get("ideal_min")
        ideal_max = self.config.get("ideal_max")
        
        if score == 1.0:
            return f"Perfect fit: {value} is in ideal range [{ideal_min}, {ideal_max}]"
        elif score >= 0.5:
            return f"Good fit: {value} is in acceptable range"
        else:
            return f"Poor fit: {value} is outside acceptable range"