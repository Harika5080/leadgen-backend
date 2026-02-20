"""
Base scorer interface for scoring strategies.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseScorer(ABC):
    """Abstract base for all scoring strategies."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Scoring rule configuration (parameters, weights, etc.)
        """
        self.config = config
    
    @abstractmethod
    def calculate_score(self, value: Any) -> float:
        """
        Calculate score for given value.
        
        Args:
            value: The field value to score
            
        Returns:
            Score between 0.0 and 1.0
        """
        pass
    
    def get_explanation(self, value: Any, score: float) -> str:
        """
        Return human-readable explanation of score.
        
        Args:
            value: The value that was scored
            score: The calculated score
            
        Returns:
            Explanation string
        """
        return f"Score: {score:.2f}"