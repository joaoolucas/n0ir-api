"""
In-memory cooldown manager for range break positions.
Tracks recent exits and prevents re-entry during cooldown period.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
from app.core.cache import cache_manager

logger = logging.getLogger(__name__)


class CooldownManager:
    """
    Manages position cooldowns after range breaks using in-memory cache.
    """
    
    # Cooldown periods in minutes based on break type and severity
    COOLDOWN_PERIODS = {
        'upward': {
            'mild': 120,      # 2 hours
            'moderate': 240,  # 4 hours  
            'severe': 480,    # 8 hours
            'critical': 720   # 12 hours
        },
        'downward': {
            'mild': 60,       # 1 hour
            'moderate': 120,  # 2 hours
            'severe': 180,    # 3 hours
            'critical': 240   # 4 hours
        }
    }
    
    async def add_cooldown(
        self,
        user_address: str,
        pool_address: str,
        break_type: str,
        severity: str,
        exit_price: Optional[float] = None,
        exit_value_usd: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Add a cooldown for a user-pool combination after range break exit.
        
        Args:
            user_address: Address of the user/executor
            pool_address: Address of the pool
            break_type: 'upward' or 'downward'
            severity: 'mild', 'moderate', 'severe', or 'critical'
            exit_price: Price at exit (optional)
            exit_value_usd: USD value at exit (optional)
            
        Returns:
            Cooldown information including expiry time
        """
        # Get cooldown duration
        cooldown_minutes = self.COOLDOWN_PERIODS.get(break_type, {}).get(severity, 120)
        cooldown_seconds = cooldown_minutes * 60
        
        # Create cooldown entry
        cooldown_entry = {
            'user_address': user_address.lower(),
            'pool_address': pool_address.lower(),
            'break_type': break_type,
            'severity': severity,
            'exit_timestamp': datetime.utcnow().isoformat(),
            'cooldown_minutes': cooldown_minutes,
            'expires_at': (datetime.utcnow() + timedelta(minutes=cooldown_minutes)).isoformat(),
            'exit_price': exit_price,
            'exit_value_usd': exit_value_usd
        }
        
        # Store in cache with expiry
        cache_key = f"cooldown:{user_address.lower()}:{pool_address.lower()}"
        await cache_manager.set_custom(cache_key, cooldown_entry, ttl=cooldown_seconds)
        
        # Also maintain a list of all cooldowns for the user
        user_cooldowns_key = f"user_cooldowns:{user_address.lower()}"
        existing_cooldowns = await cache_manager.get_custom(user_cooldowns_key) or []
        
        # Add new cooldown to list (remove duplicates for same pool)
        existing_cooldowns = [c for c in existing_cooldowns if c['pool_address'] != pool_address.lower()]
        existing_cooldowns.append(cooldown_entry)
        
        # Store user's cooldown list with a longer TTL (24 hours)
        await cache_manager.set_custom(user_cooldowns_key, existing_cooldowns, ttl=86400)
        
        logger.info(f"Added {cooldown_minutes}-minute cooldown for {user_address[:8]}...{user_address[-4:]} "
                   f"on pool {pool_address[:8]}...{pool_address[-4:]} due to {severity} {break_type} break")
        
        return cooldown_entry
    
    async def check_cooldown(self, user_address: str, pool_address: str) -> Optional[Dict[str, Any]]:
        """
        Check if a user has an active cooldown for a specific pool.
        
        Args:
            user_address: Address of the user/executor
            pool_address: Address of the pool
            
        Returns:
            Cooldown information if active, None otherwise
        """
        cache_key = f"cooldown:{user_address.lower()}:{pool_address.lower()}"
        cooldown = await cache_manager.get_custom(cache_key)
        
        if cooldown:
            # Check if still valid (redundant but safe)
            expires_at = datetime.fromisoformat(cooldown['expires_at'])
            if expires_at > datetime.utcnow():
                # Calculate remaining time
                remaining = expires_at - datetime.utcnow()
                cooldown['remaining_minutes'] = int(remaining.total_seconds() / 60)
                cooldown['is_active'] = True
                return cooldown
        
        return None
    
    async def get_user_cooldowns(self, user_address: str) -> List[Dict[str, Any]]:
        """
        Get all active cooldowns for a user.
        
        Args:
            user_address: Address of the user/executor
            
        Returns:
            List of active cooldowns with remaining time
        """
        user_cooldowns_key = f"user_cooldowns:{user_address.lower()}"
        cooldowns = await cache_manager.get_custom(user_cooldowns_key) or []
        
        # Filter and update active cooldowns
        active_cooldowns = []
        now = datetime.utcnow()
        
        for cooldown in cooldowns:
            expires_at = datetime.fromisoformat(cooldown['expires_at'])
            if expires_at > now:
                remaining = expires_at - now
                cooldown['remaining_minutes'] = int(remaining.total_seconds() / 60)
                cooldown['is_active'] = True
                active_cooldowns.append(cooldown)
        
        return active_cooldowns
    
    async def get_pools_on_cooldown(self, user_address: str) -> List[str]:
        """
        Get list of pool addresses currently on cooldown for a user.
        
        Args:
            user_address: Address of the user/executor
            
        Returns:
            List of pool addresses on cooldown
        """
        cooldowns = await self.get_user_cooldowns(user_address)
        return [c['pool_address'] for c in cooldowns]
    
    async def clear_cooldown(self, user_address: str, pool_address: str) -> bool:
        """
        Manually clear a cooldown (e.g., for admin override).
        
        Args:
            user_address: Address of the user/executor
            pool_address: Address of the pool
            
        Returns:
            True if cooldown was cleared, False if not found
        """
        cache_key = f"cooldown:{user_address.lower()}:{pool_address.lower()}"
        cooldown = await cache_manager.get_custom(cache_key)
        
        if cooldown:
            # Remove from cache
            await cache_manager.cache.delete(cache_key)
            
            # Remove from user's list
            user_cooldowns_key = f"user_cooldowns:{user_address.lower()}"
            existing_cooldowns = await cache_manager.get_custom(user_cooldowns_key) or []
            existing_cooldowns = [c for c in existing_cooldowns if c['pool_address'] != pool_address.lower()]
            await cache_manager.set_custom(user_cooldowns_key, existing_cooldowns, ttl=86400)
            
            logger.info(f"Cleared cooldown for {user_address[:8]}...{user_address[-4:]} on pool {pool_address[:8]}...{pool_address[-4:]}")
            return True
        
        return False
    
    async def should_allow_entry(self, user_address: str, pool_address: str) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if a user should be allowed to enter a position in a pool.
        
        Args:
            user_address: Address of the user/executor
            pool_address: Address of the pool
            
        Returns:
            Tuple of (allowed: bool, cooldown_info: Optional[Dict])
        """
        cooldown = await self.check_cooldown(user_address, pool_address)
        
        if cooldown and cooldown.get('is_active'):
            return False, cooldown
        
        return True, None


# Singleton instance
cooldown_manager = CooldownManager()