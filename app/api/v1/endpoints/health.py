"""Health check endpoints for monitoring system status."""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database.session import get_async_db
from app.services.cdp.client import CDPSQLClient, CDPAPIError
from app.services.cdp.monitoring import metrics_collector, circuit_breakers
from app.core.cache import cache
from loguru import logger

router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Basic health check endpoint.
    
    Returns:
        Dictionary with service status
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "n0ir-api"
    }


@router.get("/health/detailed")
async def detailed_health_check(
    db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """Detailed health check with component status.
    
    Returns:
        Dictionary with detailed health information
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {}
    }
    
    # Check database connectivity
    try:
        result = await db.execute(text("SELECT 1"))
        health_status["components"]["database"] = {
            "status": "healthy",
            "message": "Database connection successful"
        }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Check Redis/cache connectivity
    try:
        await cache.set("health_check", "ok", ttl=1)
        cached = await cache.get("health_check")
        if cached == "ok":
            health_status["components"]["cache"] = {
                "status": "healthy",
                "message": "Cache connection successful"
            }
        else:
            raise Exception("Cache read/write mismatch")
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["cache"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Check CDP API connectivity (lightweight query)
    try:
        cdp_client = CDPSQLClient()
        # Simple query to check connectivity
        test_query = "SELECT 1 as test"
        result = await cdp_client.execute_query(test_query)
        
        health_status["components"]["cdp_api"] = {
            "status": "healthy",
            "message": "CDP API connection successful"
        }
    except CDPAPIError as e:
        health_status["status"] = "degraded"
        health_status["components"]["cdp_api"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["cdp_api"] = {
            "status": "unhealthy",
            "error": f"Unexpected error: {str(e)}"
        }
    
    # Add circuit breaker status
    circuit_status = {}
    for name, breaker in circuit_breakers.items():
        state = breaker.get_state()
        circuit_status[name] = {
            "state": state["state"],
            "failures": state["failure_count"],
            "healthy": state["state"] == "CLOSED"
        }
    
    health_status["components"]["circuit_breakers"] = circuit_status
    
    # Determine overall status
    if any(
        comp.get("status") == "unhealthy"
        for comp in health_status["components"].values()
        if isinstance(comp, dict) and "status" in comp
    ):
        health_status["status"] = "unhealthy"
    elif health_status["status"] == "degraded":
        pass  # Already set
    else:
        health_status["status"] = "healthy"
    
    return health_status


@router.get("/health/metrics")
async def get_metrics() -> Dict[str, Any]:
    """Get CDP API metrics and performance data.
    
    Returns:
        Dictionary with metrics information
    """
    return metrics_collector.get_metrics_summary()


@router.get("/health/cdp")
async def cdp_health_check() -> Dict[str, Any]:
    """Check CDP API health and capabilities.
    
    Returns:
        Dictionary with CDP API status
    """
    cdp_status = {
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }
    
    cdp_client = CDPSQLClient()
    
    # Test 1: Basic connectivity
    try:
        test_query = "SELECT 1 as test, current_timestamp() as server_time"
        result = await cdp_client.execute_query(test_query)
        cdp_status["checks"]["connectivity"] = {
            "status": "pass",
            "message": "CDP API is reachable"
        }
    except Exception as e:
        cdp_status["checks"]["connectivity"] = {
            "status": "fail",
            "error": str(e)
        }
        return cdp_status  # No point continuing if basic connectivity fails
    
    # Test 2: Table access
    tables_to_check = ["base.transactions", "base.events"]
    for table in tables_to_check:
        try:
            query = f"SELECT COUNT(*) as count FROM {table} LIMIT 1"
            result = await cdp_client.execute_query(query)
            cdp_status["checks"][f"table_{table}"] = {
                "status": "pass",
                "message": f"Access to {table} confirmed"
            }
        except Exception as e:
            cdp_status["checks"][f"table_{table}"] = {
                "status": "fail",
                "error": str(e)
            }
    
    # Test 3: Query performance
    try:
        import time
        start = time.time()
        query = """
        SELECT block_number, COUNT(*) as tx_count
        FROM base.transactions
        WHERE block_number > (SELECT MAX(block_number) - 10 FROM base.transactions)
        GROUP BY block_number
        ORDER BY block_number DESC
        LIMIT 10
        """
        result = await cdp_client.execute_query(query)
        elapsed = (time.time() - start) * 1000
        
        cdp_status["checks"]["query_performance"] = {
            "status": "pass" if elapsed < 5000 else "warn",
            "response_time_ms": round(elapsed, 2),
            "message": f"Query completed in {elapsed:.0f}ms"
        }
    except Exception as e:
        cdp_status["checks"]["query_performance"] = {
            "status": "fail",
            "error": str(e)
        }
    
    # Overall status
    statuses = [check.get("status") for check in cdp_status["checks"].values()]
    if all(s == "pass" for s in statuses):
        cdp_status["overall_status"] = "healthy"
    elif any(s == "fail" for s in statuses):
        cdp_status["overall_status"] = "unhealthy"
    else:
        cdp_status["overall_status"] = "degraded"
    
    return cdp_status