"""Service for managing hedge positions and operations."""

from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update
from app.database.models import Position, Transaction  # Use compat version
from app.integrations.avantis import AvantisClient
from app.integrations.liquidity_manager import LiquidityManagerClient
from app.services.agent_management_service import get_agent_service
from app.core.logger import logger


class HedgeService:
    """Service for hedge position management and monitoring."""
    
    def __init__(self, db: AsyncSession):
        """Initialize the hedge service."""
        self.db = db
        self.avantis = AvantisClient()
        self.liquidity_manager = LiquidityManagerClient()
        self.agent_service = get_agent_service()
    
    async def create_hedged_position(
        self,
        user_id: str,
        pool_address: str,
        usdc_amount: int,
        range_percentage: int = 500,
        enable_hedge: bool = True,
        slippage_bps: int = 30
    ) -> Dict[str, Any]:
        """
        Create a delta-neutral position with optional hedge via agent manager.
        
        Args:
            user_id: User ID creating the position
            pool_address: Pool address for LP position
            usdc_amount: Amount of USDC to invest
            range_percentage: Range percentage for LP position
            enable_hedge: Whether to enable hedge
            slippage_bps: Slippage tolerance in basis points
            
        Returns:
            Dictionary with position creation results
        """
        try:
            # Send request to agent manager via Redis
            request_data = {
                "action": "create_hedged_position",
                "user_id": user_id,
                "pool": pool_address,
                "usdc_amount": usdc_amount,
                "range_percentage": range_percentage,
                "enable_hedge": enable_hedge,
                "slippage_bps": slippage_bps
            }
            
            # Publish to agent manager
            response = await self.agent_service.send_request(
                "position:create:hedged",
                request_data
            )
            
            # If hedge was created, update position with hedge data
            if response.get("hedge_id") and response["hedge_id"] > 0:
                await self._update_position_hedge_data(
                    nft_token_id=response["token_id"],
                    hedge_id=response["hedge_id"],
                    hedge_size=response.get("hedge_size", 0),
                    collateral=response.get("hedge_collateral", 0),
                    leverage=response.get("hedge_leverage", 3),
                    pair_index=response.get("pair_index", 0)
                )
            
            return response
            
        except Exception as e:
            logger.error(f"Error creating hedged position: {e}")
            raise
    
    async def _update_position_hedge_data(
        self,
        nft_token_id: int,
        hedge_id: int,
        hedge_size: int,
        collateral: int,
        leverage: int,
        pair_index: int
    ) -> Position:
        """Update position with hedge data."""
        try:
            # Get current price from Avantis
            status = await self.avantis.get_position_status(hedge_id, pair_index)
            
            # Update position with hedge data
            stmt = update(Position).where(Position.token_id == nft_token_id).values(
                hedge_id=hedge_id,
                hedge_enabled=True,
                hedge_size_usdc=Decimal(hedge_size) / Decimal(10**6),
                hedge_collateral_usdc=Decimal(collateral) / Decimal(10**6),
                hedge_leverage=leverage,
                hedge_pair_index=pair_index,
                hedge_market=self.avantis.get_market_name(pair_index),
                hedge_entry_price=status.get("entry_price", Decimal(0)),
                hedge_current_price=status.get("current_price", Decimal(0)),
                hedge_pnl_usdc=Decimal(0),
                hedge_funding_paid_usdc=Decimal(0),
                hedge_status="active"
            )
            
            await self.db.execute(stmt)
            
            # Create hedge opening transaction
            transaction = Transaction(
                user_id=(await self._get_user_id_for_position(nft_token_id)),
                position_id=nft_token_id,
                tx_type="HEDGE_OPENED",
                status="CONFIRMED",
                amount_usdc=Decimal(hedge_size) / Decimal(10**6),
                event_data={
                    "hedge_id": hedge_id,
                    "size_usdc": str(hedge_size),
                    "collateral_usdc": str(collateral),
                    "leverage": leverage,
                    "entry_price": str(status.get("entry_price", 0))
                }
            )
            self.db.add(transaction)
            
            await self.db.commit()
            
            # Return updated position
            result = await self.db.execute(select(Position).where(Position.token_id == nft_token_id))
            return result.scalar_one()
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating position with hedge data: {e}")
            raise
    
    async def _get_user_id_for_position(self, token_id: int) -> str:
        """Get user ID for a position."""
        stmt = select(Position.user_id).where(Position.token_id == token_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()
    
    async def get_hedge_status(self, token_id: int) -> Optional[Position]:
        """
        Get current hedge status with live data.
        
        Args:
            token_id: NFT token ID of the position
            
        Returns:
            Position with updated hedge data or None
        """
        try:
            # Hedge functionality has been deprecated
            # Return None since hedge data is no longer tracked in database
            return None
            
            # Legacy code - kept for reference but not executed
            stmt = select(Position).where(Position.token_id == token_id)
            result = await self.db.execute(stmt)
            position = result.scalar_one_or_none()
            
            if not position or not position.hedge_id:
                return None
            
            # Get live data from Avantis if hedge is active
            if position.hedge_status == "active":
                live_data = await self.avantis.get_position_status(
                    position.hedge_id,
                    position.hedge_pair_index
                )
                
                # Update current values
                position.hedge_current_price = live_data["current_price"]
                position.hedge_pnl_usdc = live_data["pnl"]
                position.hedge_funding_paid_usdc = live_data["funding_paid"]
                position.updated_at = datetime.utcnow()
                
                # Update in database
                await self.db.commit()
            
            return position
            
        except Exception as e:
            logger.error(f"Error fetching hedge status for token {token_id}: {e}")
            return None
    
    async def close_hedge_position(
        self,
        token_id: int,
        min_usdc_out: int = 0,
        slippage_bps: int = 30
    ) -> Dict[str, Any]:
        """
        Close a hedge position.
        
        Args:
            token_id: NFT token ID of the position
            min_usdc_out: Minimum USDC to receive
            slippage_bps: Slippage tolerance
            
        Returns:
            Dictionary with closing results
        """
        try:
            # Get position with hedge
            position = await self.get_hedge_status(token_id)
            if not position or not position.hedge_id:
                raise ValueError(f"No hedge found for position {token_id}")
            
            # Send close request to agent manager
            request_data = {
                "action": "close_hedge",
                "token_id": token_id,
                "hedge_id": position.hedge_id,
                "min_usdc_out": min_usdc_out,
                "slippage_bps": slippage_bps
            }
            
            response = await self.agent_service.send_request(
                "position:close:hedge",
                request_data
            )
            
            # Update position
            position.hedge_status = "closed"
            position.hedge_closed_at = datetime.utcnow()
            
            # Create closing transaction
            transaction = Transaction(
                user_id=position.user_id,
                position_id=token_id,
                tx_type="HEDGE_CLOSED",
                status="CONFIRMED",
                tx_hash=response.get("tx_hash"),
                amount_usdc=Decimal(response.get("usdc_out", 0)) / Decimal(10**6),
                event_data={
                    "hedge_id": position.hedge_id,
                    "exit_price": str(position.hedge_current_price),
                    "final_pnl": str(position.hedge_pnl_usdc),
                    "total_funding_paid": str(position.hedge_funding_paid_usdc),
                    "usdc_received": str(response.get("usdc_out", 0))
                }
            )
            self.db.add(transaction)
            
            await self.db.commit()
            
            return response
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error closing hedge position: {e}")
            raise
    
    async def monitor_hedge_health(self) -> List[Dict[str, Any]]:
        """
        Monitor all active hedges for health and liquidation risk.
        
        Returns:
            List of alerts for positions needing attention
        """
        try:
            # Hedge functionality has been deprecated
            # Return empty list since hedge data is no longer tracked
            return []
            
            # Legacy code - kept for reference but not executed
            # Get all positions with active hedges
            stmt = select(Position).where(
                and_(
                    Position.hedge_status == "active",
                    Position.hedge_id.isnot(None)
                )
            )
            result = await self.db.execute(stmt)
            hedged_positions = result.scalars().all()
            
            alerts = []
            
            for position in hedged_positions:
                # Update with live data
                live_data = await self.avantis.get_position_status(
                    position.hedge_id,
                    position.hedge_pair_index
                )
                
                # Update database
                position.hedge_current_price = live_data["current_price"]
                position.hedge_pnl_usdc = live_data["pnl"]
                position.hedge_funding_paid_usdc = live_data["funding_paid"]
                
                # Check health ratio
                health_ratio = position.hedge_health_ratio
                
                if health_ratio and health_ratio < 0.2:
                    alerts.append({
                        "type": "liquidation_risk",
                        "severity": "critical",
                        "token_id": position.token_id,
                        "hedge_id": position.hedge_id,
                        "health_ratio": health_ratio,
                        "pnl": float(position.hedge_pnl_usdc),
                        "message": f"Position {position.token_id} at liquidation risk (health: {health_ratio:.2f})"
                    })
                elif health_ratio and health_ratio < 0.4:
                    alerts.append({
                        "type": "low_health",
                        "severity": "warning",
                        "token_id": position.token_id,
                        "hedge_id": position.hedge_id,
                        "health_ratio": health_ratio,
                        "pnl": float(position.hedge_pnl_usdc),
                        "message": f"Position {position.token_id} has low health (health: {health_ratio:.2f})"
                    })
                
                # Check for high funding costs
                if position.hedge_funding_paid_usdc and position.hedge_collateral_usdc:
                    if abs(position.hedge_funding_paid_usdc) > position.hedge_collateral_usdc * Decimal("0.1"):
                        alerts.append({
                            "type": "high_funding",
                            "severity": "info",
                            "token_id": position.token_id,
                            "hedge_id": position.hedge_id,
                            "funding_paid": float(position.hedge_funding_paid_usdc),
                            "message": f"Position {position.token_id} has high funding costs"
                        })
            
            # Commit updates
            await self.db.commit()
            
            return alerts
            
        except Exception as e:
            logger.error(f"Error monitoring hedge health: {e}")
            await self.db.rollback()
            return []
    
    async def get_hedge_statistics(self) -> Dict[str, Any]:
        """
        Get aggregate statistics for all hedge positions.
        
        Returns:
            Dictionary with hedge statistics
        """
        try:
            # Hedge functionality has been deprecated
            # Return zero statistics since hedge data is no longer tracked
            return {
                "total_positions": 0,
                "active_hedges": 0,
                "total_value": 0,
                "total_pnl": 0,
                "avg_leverage": 0,
                "total_funding": 0,
                "at_risk_count": 0,
                "eth_positions": 0,
                "btc_positions": 0
            }
            
            # Legacy code - kept for reference but not executed
            # Get all positions with hedges
            stmt = select(Position).where(Position.hedge_id.isnot(None))
            result = await self.db.execute(stmt)
            hedged_positions = result.scalars().all()
            
            # Calculate statistics
            total_positions = len(hedged_positions)
            active_hedges = sum(1 for p in hedged_positions if p.hedge_status == "active")
            
            total_value = sum(p.hedge_size_usdc or 0 for p in hedged_positions if p.hedge_status == "active")
            total_pnl = sum(p.hedge_pnl_usdc or 0 for p in hedged_positions if p.hedge_status == "active")
            total_funding = sum(p.hedge_funding_paid_usdc or 0 for p in hedged_positions if p.hedge_status == "active")
            
            # Average leverage for active positions
            active_with_leverage = [p for p in hedged_positions if p.hedge_status == "active" and p.hedge_leverage]
            avg_leverage = (
                sum(p.hedge_leverage for p in active_with_leverage) / len(active_with_leverage)
                if active_with_leverage else 0
            )
            
            # Count at-risk positions
            at_risk_count = sum(1 for p in hedged_positions if p.hedge_status == "active" and p.hedge_is_at_risk)
            
            # Market breakdown
            eth_positions = sum(1 for p in hedged_positions if p.hedge_market == "ETH-USD" and p.hedge_status == "active")
            btc_positions = sum(1 for p in hedged_positions if p.hedge_market == "BTC-USD" and p.hedge_status == "active")
            
            return {
                "total_positions": total_positions,
                "active_hedges": active_hedges,
                "total_value": float(total_value),
                "total_pnl": float(total_pnl),
                "avg_leverage": avg_leverage,
                "total_funding": float(total_funding),
                "at_risk_count": at_risk_count,
                "eth_positions": eth_positions,
                "btc_positions": btc_positions
            }
            
        except Exception as e:
            logger.error(f"Error calculating hedge statistics: {e}")
            return {
                "total_positions": 0,
                "active_hedges": 0,
                "total_value": 0,
                "total_pnl": 0,
                "avg_leverage": 0,
                "total_funding": 0,
                "at_risk_count": 0,
                "eth_positions": 0,
                "btc_positions": 0
            }
    
    async def calculate_hedge_performance(
        self,
        timeframe: str = "24h"
    ) -> Dict[str, Any]:
        """
        Calculate performance metrics for hedged vs unhedged positions.
        
        Args:
            timeframe: Time period for performance calculation
            
        Returns:
            Dictionary with performance metrics
        """
        try:
            # Hedge functionality has been deprecated
            # Return zero performance metrics
            return {
                "hedged_count": 0,
                "hedged_avg_return": 0,
                "hedged_pnl": 0,
                "unhedged_count": 0,
                "unhedged_avg_return": 0,
                "unhedged_pnl": 0,
                "effectiveness_ratio": 1.0,
                "volatility_reduction": 0
            }
            
            # Legacy code - kept for reference but not executed
            # Get positions with and without hedges
            stmt_hedged = select(Position).where(
                and_(
                    Position.status == "ACTIVE",
                    Position.hedge_id.isnot(None)
                )
            )
            
            stmt_unhedged = select(Position).where(
                and_(
                    Position.status == "ACTIVE",
                    Position.hedge_id.is_(None)
                )
            )
            
            result_hedged = await self.db.execute(stmt_hedged)
            hedged_positions = result_hedged.scalars().all()
            
            result_unhedged = await self.db.execute(stmt_unhedged)
            unhedged_positions = result_unhedged.scalars().all()
            
            # Calculate metrics
            hedged_count = len(hedged_positions)
            unhedged_count = len(unhedged_positions)
            
            # Calculate average returns
            hedged_pnl = sum(p.total_pnl_usdc for p in hedged_positions)
            unhedged_pnl = sum(p.net_pnl_usdc or 0 for p in unhedged_positions)
            
            hedged_avg_return = (hedged_pnl / hedged_count) if hedged_count > 0 else 0
            unhedged_avg_return = (unhedged_pnl / unhedged_count) if unhedged_count > 0 else 0
            
            # Calculate volatility reduction (simplified)
            effectiveness_ratio = 1.0
            if unhedged_avg_return != 0:
                effectiveness_ratio = abs(hedged_avg_return / unhedged_avg_return)
            
            volatility_reduction = max(0, 1 - effectiveness_ratio) * 100
            
            return {
                "hedged_count": hedged_count,
                "hedged_avg_return": float(hedged_avg_return),
                "hedged_pnl": float(hedged_pnl),
                "unhedged_count": unhedged_count,
                "unhedged_avg_return": float(unhedged_avg_return),
                "unhedged_pnl": float(unhedged_pnl),
                "effectiveness_ratio": effectiveness_ratio,
                "volatility_reduction": volatility_reduction
            }
            
        except Exception as e:
            logger.error(f"Error calculating hedge performance: {e}")
            return {
                "hedged_count": 0,
                "hedged_avg_return": 0,
                "hedged_pnl": 0,
                "unhedged_count": 0,
                "unhedged_avg_return": 0,
                "unhedged_pnl": 0,
                "effectiveness_ratio": 1.0,
                "volatility_reduction": 0
            }