"""
Background job for reconciling deployed capital with actual on-chain positions.

This job ensures data integrity by comparing the deployed_capital_usd field
in active_strategies with the actual capital deployed in on-chain positions.
"""

import asyncio
from decimal import Decimal
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from loguru import logger

from app.database.session import get_async_session
from app.database.models import User
from app.core.positions_service import positions_service


class CapitalReconciliationService:
    """Service for reconciling deployed capital with on-chain state."""

    # Threshold for auto-correction (5% of deployed capital)
    AUTO_CORRECT_THRESHOLD_PCT = Decimal("0.05")

    # Alert threshold for manual review (any discrepancy above 5%)
    ALERT_THRESHOLD_PCT = Decimal("0.05")

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_users_with_active_strategies(self) -> List[User]:
        """Get all users with active strategies from relational table."""
        from app.database.models import UserStrategy

        # Get distinct user_ids from user_strategies table where status is active
        stmt = select(User).join(UserStrategy).where(
            UserStrategy.status == 'active'
        ).distinct()
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_onchain_capital_for_strategy(
        self,
        user_id: str,
        strategy_code: str
    ) -> Decimal:
        """
        Get actual deployed capital from on-chain positions.

        Args:
            user_id: User wallet address
            strategy_code: Strategy short code

        Returns:
            Total capital in active positions for this strategy
        """
        # Query strategy_positions table for active positions
        result = await self.db.execute(
            text("""
                SELECT SUM(sp.capital_deployed_usd)
                FROM strategy_positions sp
                WHERE sp.user_id = :user_id
                  AND sp.strategy_code = :strategy_code
                  AND sp.closed_at IS NULL
            """),
            {"user_id": user_id, "strategy_code": strategy_code}
        )

        onchain_capital = result.scalar_one_or_none()
        return Decimal(str(onchain_capital)) if onchain_capital else Decimal(0)

    async def reconcile_user_strategy(
        self,
        user: User,
        strategy_code: str
    ) -> Tuple[bool, str, Decimal, Decimal]:
        """
        Reconcile a single user's strategy capital.

        Args:
            user: User object
            strategy_code: Strategy short code

        Returns:
            Tuple of (needs_correction, message, db_deployed, onchain_deployed)
        """
        # Get strategy from relational table
        from app.services.strategy_service import StrategyService
        strategy_service = StrategyService(self.db)

        strategy = await strategy_service.get_strategy_by_code(user.user_id, strategy_code)
        if not strategy or strategy.status != 'active':
            return False, "Strategy not active", Decimal(0), Decimal(0)

        db_deployed = Decimal(str(strategy.deployed_capital_usd))

        # Get actual on-chain capital
        onchain_deployed = await self.get_onchain_capital_for_strategy(
            user.user_id, strategy_code
        )

        # Calculate discrepancy
        discrepancy = abs(db_deployed - onchain_deployed)
        discrepancy_pct = (discrepancy / db_deployed * 100) if db_deployed > 0 else Decimal(0)

        if discrepancy_pct <= self.ALERT_THRESHOLD_PCT:
            # Within acceptable range
            return False, "OK", db_deployed, onchain_deployed

        # Discrepancy detected
        message = (
            f"Discrepancy detected: DB={db_deployed}, OnChain={onchain_deployed}, "
            f"Diff={discrepancy} ({discrepancy_pct:.2f}%)"
        )

        return True, message, db_deployed, onchain_deployed

    async def auto_correct_capital(
        self,
        user: User,
        strategy_code: str,
        correct_value: Decimal
    ) -> None:
        """
        Auto-correct deployed capital to match on-chain state.

        Args:
            user: User object
            strategy_code: Strategy short code
            correct_value: Correct value from on-chain
        """
        # Get strategy from relational table with row lock
        from app.services.strategy_service import StrategyService
        strategy_service = StrategyService(self.db)

        strategy = await strategy_service.get_strategy_by_code(
            user.user_id,
            strategy_code,
            lock_for_update=True
        )

        if not strategy:
            logger.warning(f"Strategy {strategy_code} not found for user {user.user_id}")
            return

        old_value = strategy.deployed_capital_usd

        # Update to correct value
        strategy.deployed_capital_usd = correct_value
        strategy.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.info(
            f"Auto-corrected capital for {user.user_id}/{strategy_code}: "
            f"{old_value} -> {correct_value}"
        )

    async def reconcile_all_users(self) -> Dict[str, any]:
        """
        Reconcile all users with active strategies.

        Returns:
            Dict with reconciliation results
        """
        logger.info("🔍 Starting capital reconciliation...")

        users = await self.get_users_with_active_strategies()
        logger.info(f"Found {len(users)} users with active strategies")

        results = {
            "total_users": len(users),
            "total_strategies": 0,
            "discrepancies_found": 0,
            "auto_corrected": 0,
            "manual_review_needed": 0,
            "errors": 0,
            "details": []
        }

        for user in users:
            # Get user's active strategies from relational table
            from app.services.strategy_service import StrategyService
            strategy_service = StrategyService(self.db)
            strategies = await strategy_service.get_active_strategies(user.user_id)

            for strategy in strategies:
                results["total_strategies"] += 1

                strategy_code = strategy.strategy_code

                try:
                    needs_correction, message, db_deployed, onchain_deployed = await self.reconcile_user_strategy(
                        user, strategy_code
                    )

                    if needs_correction:
                        results["discrepancies_found"] += 1

                        discrepancy = abs(db_deployed - onchain_deployed)
                        discrepancy_pct = (discrepancy / db_deployed * 100) if db_deployed > 0 else Decimal(0)

                        detail = {
                            "user_id": user.user_id,
                            "strategy_code": strategy_code,
                            "db_deployed": float(db_deployed),
                            "onchain_deployed": float(onchain_deployed),
                            "discrepancy": float(discrepancy),
                            "discrepancy_pct": float(discrepancy_pct),
                            "message": message
                        }

                        # Auto-correct if within threshold
                        if discrepancy_pct <= self.AUTO_CORRECT_THRESHOLD_PCT:
                            await self.auto_correct_capital(user, strategy_code, onchain_deployed)
                            detail["action"] = "auto_corrected"
                            results["auto_corrected"] += 1
                        else:
                            detail["action"] = "manual_review_needed"
                            results["manual_review_needed"] += 1
                            logger.warning(
                                f"❌ MANUAL REVIEW NEEDED: {user.user_id}/{strategy_code} - {message}"
                            )

                        results["details"].append(detail)

                except Exception as e:
                    results["errors"] += 1
                    logger.error(f"Error reconciling {user.user_id}/{strategy_code}: {e}")
                    results["details"].append({
                        "user_id": user.user_id,
                        "strategy_code": strategy_code,
                        "error": str(e)
                    })

        # Log summary
        logger.info(
            f"✅ Reconciliation complete: "
            f"{results['total_strategies']} strategies checked, "
            f"{results['discrepancies_found']} discrepancies found, "
            f"{results['auto_corrected']} auto-corrected, "
            f"{results['manual_review_needed']} need manual review, "
            f"{results['errors']} errors"
        )

        return results


async def run_capital_reconciliation():
    """
    Main entry point for capital reconciliation job.

    This should be called by a scheduler (e.g., cron, APScheduler) every hour.
    """
    logger.info("🚀 Starting scheduled capital reconciliation...")

    try:
        async with get_async_session() as db:
            service = CapitalReconciliationService(db)
            results = await service.reconcile_all_users()

            # If there are items needing manual review, send alerts
            if results["manual_review_needed"] > 0:
                # TODO: Implement alerting (e.g., Slack, email, PagerDuty)
                logger.error(
                    f"🚨 {results['manual_review_needed']} strategies need manual review!"
                )

                # Log details for manual review items
                for detail in results["details"]:
                    if detail.get("action") == "manual_review_needed":
                        logger.error(
                            f"  - {detail['user_id']}/{detail['strategy_code']}: "
                            f"DB={detail['db_deployed']}, OnChain={detail['onchain_deployed']}, "
                            f"Diff={detail['discrepancy']} ({detail['discrepancy_pct']:.2f}%)"
                        )

            return results

    except Exception as e:
        logger.error(f"❌ Capital reconciliation failed: {e}")
        raise


if __name__ == "__main__":
    # For manual testing
    asyncio.run(run_capital_reconciliation())
