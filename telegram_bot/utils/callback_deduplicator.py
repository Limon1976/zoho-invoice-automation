"""
Callback deduplicator to prevent race conditions in button handling.
Prevents duplicate processing of the same callback within a time window.
"""
import asyncio
from typing import Set
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class CallbackDeduplicator:
    """Thread-safe callback deduplicator with automatic cleanup"""
    
    def __init__(self, ttl_seconds: int = 5):
        self._processing: Set[str] = set()
        self._lock = asyncio.Lock()
        self._ttl = ttl_seconds
        
    async def is_duplicate(self, callback_id: str, message_id: int = None) -> bool:
        """
        Check if callback is duplicate. Returns True if already processing.
        
        Args:
            callback_id: Telegram callback query ID
            message_id: Optional message ID for additional deduplication
            
        Returns:
            True if duplicate (already processing), False otherwise
        """
        async with self._lock:
            # Create unique key combining callback_id and message_id
            key = f"{callback_id}"
            if message_id:
                key = f"{callback_id}:{message_id}"
            
            if key in self._processing:
                logger.warning(f"Duplicate callback detected: {key}")
                return True
                
            self._processing.add(key)
            
            # Schedule cleanup
            asyncio.create_task(self._cleanup_after(key, self._ttl))
            
            logger.debug(f"Processing callback: {key}")
            return False
    
    async def _cleanup_after(self, key: str, seconds: int):
        """Remove key from processing set after timeout"""
        await asyncio.sleep(seconds)
        async with self._lock:
            self._processing.discard(key)
            logger.debug(f"Cleaned up callback: {key}")
    
    async def mark_completed(self, callback_id: str, message_id: int = None):
        """Manually mark callback as completed (optional)"""
        async with self._lock:
            key = f"{callback_id}"
            if message_id:
                key = f"{callback_id}:{message_id}"
            self._processing.discard(key)


# Global instance for the bot
callback_deduplicator = CallbackDeduplicator(ttl_seconds=5)