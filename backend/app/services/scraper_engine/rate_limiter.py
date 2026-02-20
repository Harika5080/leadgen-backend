# backend/app/services/scraper_engine/rate_limiter.py
"""
Smart Rate Limiter for Scraping

Prevents detection and bans by:
- Random delays between requests
- Exponential backoff on errors
- Human-like behavior patterns
- Respects platform-specific limits
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Platform-aware rate limiter with human-like patterns
    """
    
    # Platform-specific configurations
    PLATFORM_CONFIGS = {
        "linkedin": {
            "min_page_delay": 3.0,      # Minimum 3 seconds between pages
            "max_page_delay": 8.0,      # Maximum 8 seconds
            "min_profile_delay": 1.5,   # Between individual profiles
            "max_profile_delay": 4.0,
            "requests_per_hour": 50,    # Conservative limit
            "cooldown_after": 20,       # Cooldown after 20 requests
            "cooldown_duration": 300,   # 5 minute cooldown
        },
        "apollo": {
            "min_request_delay": 0.5,   # Half second between API calls
            "max_request_delay": 2.0,
            "requests_per_minute": 10,  # API rate limit
            "requests_per_hour": 500,
        },
        "default": {
            "min_request_delay": 1.0,
            "max_request_delay": 3.0,
            "requests_per_hour": 100,
        }
    }
    
    def __init__(self, platform: str = "default"):
        self.platform = platform.lower()
        self.config = self.PLATFORM_CONFIGS.get(
            self.platform,
            self.PLATFORM_CONFIGS["default"]
        )
        
        # Request tracking
        self.request_count = 0
        self.requests_this_hour = []
        self.last_request_time = None
        self.consecutive_errors = 0
        
        # Cooldown tracking
        self.in_cooldown = False
        self.cooldown_until = None
    
    async def wait_before_request(self, request_type: str = "default"):
        """
        Wait appropriate amount of time before next request
        
        Args:
            request_type: 'page', 'profile', 'api', 'default'
        """
        # Check if in cooldown
        if self.in_cooldown:
            if datetime.utcnow() < self.cooldown_until:
                wait_time = (self.cooldown_until - datetime.utcnow()).total_seconds()
                logger.warning(
                    f"🛑 Rate limit cooldown: waiting {wait_time:.0f}s "
                    f"(until {self.cooldown_until.strftime('%H:%M:%S')})"
                )
                await asyncio.sleep(wait_time)
            self.in_cooldown = False
            self.cooldown_until = None
        
        # Calculate delay based on request type
        if self.platform == "linkedin":
            if request_type == "page":
                delay = self._random_delay(
                    self.config["min_page_delay"],
                    self.config["max_page_delay"]
                )
            elif request_type == "profile":
                delay = self._random_delay(
                    self.config["min_profile_delay"],
                    self.config["max_profile_delay"]
                )
            else:
                delay = self._random_delay(2.0, 5.0)
        
        elif self.platform == "apollo":
            delay = self._random_delay(
                self.config["min_request_delay"],
                self.config["max_request_delay"]
            )
        
        else:
            delay = self._random_delay(
                self.config["min_request_delay"],
                self.config["max_request_delay"]
            )
        
        # Add exponential backoff if consecutive errors
        if self.consecutive_errors > 0:
            backoff_multiplier = min(2 ** self.consecutive_errors, 10)
            delay *= backoff_multiplier
            logger.warning(
                f"⚠️ Applying backoff: {self.consecutive_errors} errors, "
                f"multiplier {backoff_multiplier}x, delay {delay:.1f}s"
            )
        
        # Wait
        if delay > 0:
            logger.debug(f"⏳ Waiting {delay:.2f}s before {request_type} request...")
            await asyncio.sleep(delay)
        
        # Update tracking
        self.request_count += 1
        self.last_request_time = datetime.utcnow()
        self.requests_this_hour.append(datetime.utcnow())
        
        # Clean old requests from tracking
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        self.requests_this_hour = [
            t for t in self.requests_this_hour if t > one_hour_ago
        ]
        
        # Check if need cooldown
        if self.platform == "linkedin":
            if self.request_count % self.config["cooldown_after"] == 0:
                self._trigger_cooldown()
        
        # Check hourly limits
        if len(self.requests_this_hour) >= self.config["requests_per_hour"]:
            logger.warning(
                f"🚨 Hourly limit reached: {len(self.requests_this_hour)} requests. "
                "Entering extended cooldown..."
            )
            self.cooldown_until = one_hour_ago + timedelta(hours=1, minutes=5)
            self.in_cooldown = True
    
    def _random_delay(self, min_delay: float, max_delay: float) -> float:
        """
        Generate human-like random delay
        
        Uses normal distribution with occasional longer delays
        to simulate human reading/thinking time
        """
        # 90% of time: normal delay
        if random.random() < 0.9:
            # Normal distribution centered between min and max
            mean = (min_delay + max_delay) / 2
            std_dev = (max_delay - min_delay) / 4
            delay = random.gauss(mean, std_dev)
            return max(min_delay, min(max_delay, delay))
        
        # 10% of time: longer delay (simulating reading/thinking)
        return random.uniform(max_delay, max_delay * 2)
    
    def _trigger_cooldown(self):
        """Trigger a cooldown period"""
        cooldown_duration = self.config.get("cooldown_duration", 300)
        self.cooldown_until = datetime.utcnow() + timedelta(seconds=cooldown_duration)
        self.in_cooldown = True
        
        logger.info(
            f"😴 Cooldown triggered: {cooldown_duration}s "
            f"(after {self.request_count} requests)"
        )
    
    def mark_success(self):
        """Mark last request as successful (reset error counter)"""
        if self.consecutive_errors > 0:
            logger.info(f"✅ Request successful, resetting error counter (was {self.consecutive_errors})")
        self.consecutive_errors = 0
    
    def mark_error(self, error_type: str = "generic"):
        """Mark last request as failed (increase backoff)"""
        self.consecutive_errors += 1
        logger.error(
            f"❌ Request failed ({error_type}): "
            f"{self.consecutive_errors} consecutive errors"
        )
        
        # Force cooldown after too many errors
        if self.consecutive_errors >= 3:
            logger.error("🚨 Too many errors, forcing cooldown...")
            self._trigger_cooldown()
    
    def get_stats(self) -> Dict:
        """Get current rate limiter stats"""
        return {
            "platform": self.platform,
            "total_requests": self.request_count,
            "requests_last_hour": len(self.requests_this_hour),
            "in_cooldown": self.in_cooldown,
            "consecutive_errors": self.consecutive_errors,
            "last_request": self.last_request_time.isoformat() if self.last_request_time else None,
        }


class BatchProcessor:
    """
    Process items in batches with delays between batches
    """
    
    def __init__(
        self,
        batch_size: int = 50,
        delay_between_batches: float = 30.0,
        max_total_items: Optional[int] = None
    ):
        """
        Args:
            batch_size: Number of items per batch
            delay_between_batches: Seconds to wait between batches
            max_total_items: Maximum total items to process (None = unlimited)
        """
        self.batch_size = batch_size
        self.delay_between_batches = delay_between_batches
        self.max_total_items = max_total_items
        
        self.batches_processed = 0
        self.items_processed = 0
    
    async def process_in_batches(
        self,
        items: list,
        process_func,
        on_batch_complete: Optional[callable] = None
    ):
        """
        Process items in batches
        
        Args:
            items: List of items to process
            process_func: Async function to process each item
            on_batch_complete: Optional callback after each batch
        
        Returns:
            List of results
        """
        total_items = len(items)
        
        # Apply max limit if set
        if self.max_total_items:
            total_items = min(total_items, self.max_total_items)
            items = items[:total_items]
        
        results = []
        
        # Process in batches
        for i in range(0, total_items, self.batch_size):
            batch = items[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (total_items + self.batch_size - 1) // self.batch_size
            
            logger.info(
                f"📦 Processing batch {batch_num}/{total_batches} "
                f"({len(batch)} items, total: {self.items_processed + len(batch)}/{total_items})"
            )
            
            # Process batch
            batch_results = []
            for item in batch:
                try:
                    result = await process_func(item)
                    batch_results.append(result)
                    self.items_processed += 1
                except Exception as e:
                    logger.error(f"Error processing item: {e}")
                    batch_results.append(None)
            
            results.extend(batch_results)
            self.batches_processed += 1
            
            # Callback if provided
            if on_batch_complete:
                await on_batch_complete(batch_num, total_batches, batch_results)
            
            # Wait before next batch (except after last batch)
            if i + self.batch_size < total_items:
                logger.info(
                    f"⏸️  Batch {batch_num} complete. "
                    f"Waiting {self.delay_between_batches}s before next batch..."
                )
                await asyncio.sleep(self.delay_between_batches)
        
        logger.info(
            f"✅ All batches processed: {self.batches_processed} batches, "
            f"{self.items_processed} items"
        )
        
        return results
    
    def get_stats(self) -> Dict:
        """Get batch processing stats"""
        return {
            "batches_processed": self.batches_processed,
            "items_processed": self.items_processed,
            "batch_size": self.batch_size,
            "delay_between_batches": self.delay_between_batches,
        }


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

async def example_linkedin_scraping():
    """Example: LinkedIn scraping with rate limiting"""
    
    limiter = RateLimiter(platform="linkedin")
    
    # Scrape 5 pages
    for page in range(1, 6):
        # Wait before loading page
        await limiter.wait_before_request("page")
        
        print(f"Loading page {page}...")
        
        # Simulate scraping profiles on page
        for profile in range(10):
            await limiter.wait_before_request("profile")
            print(f"  Scraping profile {profile + 1}/10")
            
            # Mark success
            limiter.mark_success()
    
    print(limiter.get_stats())


async def example_batch_processing():
    """Example: Process leads in batches"""
    
    # Simulate 150 leads
    leads = [f"lead-{i}" for i in range(150)]
    
    # Process in batches of 50
    processor = BatchProcessor(
        batch_size=50,
        delay_between_batches=30,  # 30 second pause between batches
        max_total_items=150
    )
    
    async def process_lead(lead):
        # Simulate processing
        await asyncio.sleep(0.1)
        return f"processed-{lead}"
    
    results = await processor.process_in_batches(
        items=leads,
        process_func=process_lead,
        on_batch_complete=lambda b, t, r: print(f"Batch {b}/{t} done!")
    )
    
    print(f"Processed {len(results)} leads")
    print(processor.get_stats())


if __name__ == "__main__":
    # Test rate limiter
    asyncio.run(example_linkedin_scraping())
    
    # Test batch processor
    asyncio.run(example_batch_processing())