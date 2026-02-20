"""
Scorer factory and registry.
"""
from .base import BaseScorer
from .range_scorer import RangeScorer
from .match_scorer import MatchScorer
from .text_scorer import TextScorer
from .threshold_scorer import ThresholdScorer

# Registry of available scorers
SCORER_REGISTRY = {
    "range": RangeScorer,
    "match": MatchScorer,
    "text": TextScorer,
    "threshold": ThresholdScorer,
}


def get_scorer(scorer_type: str, config: dict) -> BaseScorer:
    """
    Factory function to create appropriate scorer.
    
    Args:
        scorer_type: Type of scorer (range, match, text, threshold)
        config: Scorer configuration
        
    Returns:
        Instantiated scorer
        
    Raises:
        ValueError: If scorer_type not found in registry
    """
    scorer_class = SCORER_REGISTRY.get(scorer_type)
    
    if not scorer_class:
        raise ValueError(
            f"Unknown scorer type: {scorer_type}. "
            f"Available: {list(SCORER_REGISTRY.keys())}"
        )
    
    return scorer_class(config)