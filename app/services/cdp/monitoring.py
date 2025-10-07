"""Monitoring and metrics for CDP SQL API integration."""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque
import asyncio
from loguru import logger


class CDPMetricsCollector:
    """Collects and tracks metrics for CDP API operations."""
    
    def __init__(self, window_size_minutes: int = 5):
        self.window_size = timedelta(minutes=window_size_minutes)
        self.request_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.response_times = defaultdict(lambda: deque(maxlen=100))
        self.last_errors = defaultdict(lambda: deque(maxlen=10))
        self.circuit_breaker_states = {}
        
    def record_request(
        self,
        endpoint: str,
        success: bool,
        response_time_ms: float,
        error: Optional[str] = None
    ):
        """Record API request metrics.
        
        Args:
            endpoint: API endpoint or query type
            success: Whether request succeeded
            response_time_ms: Response time in milliseconds
            error: Error message if failed
        """
        now = datetime.utcnow()
        
        # Update counts
        self.request_counts[endpoint] += 1
        if not success:
            self.error_counts[endpoint] += 1
            if error:
                self.last_errors[endpoint].append({
                    'timestamp': now,
                    'error': error
                })
        
        # Track response times
        self.response_times[endpoint].append({
            'timestamp': now,
            'duration_ms': response_time_ms,
            'success': success
        })
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of collected metrics.
        
        Returns:
            Dictionary with metrics summary
        """
        now = datetime.utcnow()
        cutoff = now - self.window_size
        
        summary = {
            'timestamp': now.isoformat(),
            'window_minutes': self.window_size.total_seconds() / 60,
            'endpoints': {}
        }
        
        for endpoint in self.request_counts:
            # Calculate recent metrics
            recent_times = [
                rt for rt in self.response_times[endpoint]
                if rt['timestamp'] > cutoff
            ]
            
            success_times = [
                rt['duration_ms'] for rt in recent_times
                if rt['success']
            ]
            
            endpoint_metrics = {
                'total_requests': self.request_counts[endpoint],
                'total_errors': self.error_counts[endpoint],
                'error_rate': self.error_counts[endpoint] / max(1, self.request_counts[endpoint]),
                'recent_requests': len(recent_times),
                'recent_errors': len([rt for rt in recent_times if not rt['success']]),
                'avg_response_time_ms': sum(success_times) / max(1, len(success_times)),
                'p95_response_time_ms': self._calculate_percentile(success_times, 95),
                'last_errors': [
                    {'timestamp': e['timestamp'].isoformat(), 'error': e['error']}
                    for e in self.last_errors[endpoint][-5:]
                ]
            }
            
            # Add circuit breaker state if exists
            if endpoint in self.circuit_breaker_states:
                endpoint_metrics['circuit_breaker'] = self.circuit_breaker_states[endpoint]
            
            summary['endpoints'][endpoint] = endpoint_metrics
        
        return summary
    
    def _calculate_percentile(self, values: list, percentile: int) -> float:
        """Calculate percentile of values.
        
        Args:
            values: List of numeric values
            percentile: Percentile to calculate (0-100)
            
        Returns:
            Percentile value
        """
        if not values:
            return 0
        
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        return sorted_values[min(index, len(sorted_values) - 1)]
    
    def update_circuit_breaker_state(self, endpoint: str, state: str):
        """Update circuit breaker state for an endpoint.
        
        Args:
            endpoint: API endpoint
            state: Circuit breaker state (CLOSED, OPEN, HALF_OPEN)
        """
        self.circuit_breaker_states[endpoint] = {
            'state': state,
            'updated_at': datetime.utcnow().isoformat()
        }


class CircuitBreaker:
    """Circuit breaker pattern for CDP API calls."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception
    ):
        """Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception type to catch
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        
    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection.
        
        Args:
            func: Async function to call
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        if self.state == 'OPEN':
            if self._should_attempt_reset():
                self.state = 'HALF_OPEN'
                logger.info(f"Circuit breaker entering HALF_OPEN state")
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker is OPEN (failures: {self.failure_count})"
                )
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
            
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset the circuit.
        
        Returns:
            True if recovery timeout has passed
        """
        if self.last_failure_time is None:
            return False
        
        time_since_failure = (
            datetime.utcnow() - self.last_failure_time
        ).total_seconds()
        
        return time_since_failure >= self.recovery_timeout
    
    def _on_success(self):
        """Handle successful call."""
        if self.state == 'HALF_OPEN':
            logger.info("Circuit breaker reset to CLOSED state")
        
        self.failure_count = 0
        self.state = 'CLOSED'
    
    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )
        elif self.state == 'HALF_OPEN':
            self.state = 'OPEN'
            logger.warning("Circuit breaker reopened after failure in HALF_OPEN state")
    
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state.
        
        Returns:
            Dictionary with state information
        """
        return {
            'state': self.state,
            'failure_count': self.failure_count,
            'last_failure': self.last_failure_time.isoformat() if self.last_failure_time else None,
            'threshold': self.failure_threshold,
            'recovery_timeout': self.recovery_timeout
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


# Global metrics collector instance
metrics_collector = CDPMetricsCollector()

# Circuit breakers for different query types
circuit_breakers = {
    'wallet_history': CircuitBreaker(failure_threshold=3, recovery_timeout=30),
    'liquidity_events': CircuitBreaker(failure_threshold=3, recovery_timeout=30),
    'usdc_transfers': CircuitBreaker(failure_threshold=3, recovery_timeout=30),
}


def get_circuit_breaker(query_type: str) -> CircuitBreaker:
    """Get or create circuit breaker for query type.
    
    Args:
        query_type: Type of query
        
    Returns:
        Circuit breaker instance
    """
    if query_type not in circuit_breakers:
        circuit_breakers[query_type] = CircuitBreaker()
    return circuit_breakers[query_type]


async def monitor_metrics_periodically(interval_seconds: int = 60):
    """Background task to log metrics periodically.
    
    Args:
        interval_seconds: Interval between metric logs
    """
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            
            metrics = metrics_collector.get_metrics_summary()
            
            # Log summary
            for endpoint, data in metrics['endpoints'].items():
                if data['recent_requests'] > 0:
                    logger.info(
                        f"CDP Metrics - {endpoint}: "
                        f"requests={data['recent_requests']}, "
                        f"errors={data['recent_errors']}, "
                        f"avg_time={data['avg_response_time_ms']:.1f}ms, "
                        f"p95={data['p95_response_time_ms']:.1f}ms"
                    )
                    
                    # Log circuit breaker state if not closed
                    if 'circuit_breaker' in data and data['circuit_breaker']['state'] != 'CLOSED':
                        logger.warning(
                            f"Circuit breaker for {endpoint}: {data['circuit_breaker']['state']}"
                        )
                        
        except Exception as e:
            logger.error(f"Error in metrics monitoring: {e}")