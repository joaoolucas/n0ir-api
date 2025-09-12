"""Service for managing hedge positions and operations."""

from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update
from app.database.models.hedge_position import HedgePosition
from app.database.models.hedge_event import HedgeEvent
from app.database.models.position import Position
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
            
            # If hedge was created, store in database
            if response.get("hedge_id") and response["hedge_id"] > 0:
                await self._store_hedge_position(
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
    
    async def _store_hedge_position(
        self,
        nft_token_id: int,
        hedge_id: int,
        hedge_size: int,
        collateral: int,
        leverage: int,
        pair_index: int
    ) -> HedgePosition:
        """Store hedge position in database."""
        try:
            # Get current price from Avantis
            status = await self.avantis.get_position_status(hedge_id, pair_index)
            
            # Create hedge position record
            hedge_position = HedgePosition(
                nft_token_id=nft_token_id,
                hedge_id=hedge_id,
                hedge_enabled=True,
                hedge_size_usdc=Decimal(hedge_size) / Decimal(10**6),
                collateral_usdc=Decimal(collateral) / Decimal(10**6),
                leverage=leverage,
                pair_index=pair_index,
                market=self.avantis.get_market_name(pair_index),
                entry_price=status.get("entry_price", Decimal(0)),
                current_price=status.get("current_price", Decimal(0)),
                pnl_usdc=Decimal(0),
                funding_paid_usdc=Decimal(0),
                status="active"
            )
            
            self.db.add(hedge_position)
            
            # Create opening event
            event = HedgeEvent(
                nft_token_id=nft_token_id,
                hedge_id=hedge_id,
                event_type="opened",
                data={
                    "size_usdc": str(hedge_size),
                    "collateral_usdc": str(collateral),
                    "leverage": leverage,
                    "entry_price": str(status.get("entry_price", 0))
                }
            )
            self.db.add(event)
            
            await self.db.commit()
            return hedge_position
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error storing hedge position: {e}")
            raise
    
    async def get_hedge_status(self, token_id: int) -> Optional[HedgePosition]:
        """
        Get current hedge status with live data.
        
        Args:
            token_id: NFT token ID of the position
            
        Returns:
            HedgePosition with updated live data or None
        """
        try:
            # Get hedge position from database
            stmt = select(HedgePosition).where(HedgePosition.nft_token_id == token_id)
            result = await self.db.execute(stmt)
            hedge = result.scalar_one_or_none()
            
            if not hedge:
                return None
            
            # Get live data from Avantis if position is active
            if hedge.status == "active":
                live_data = await self.avantis.get_position_status(
                    hedge.hedge_id,
                    hedge.pair_index
                )
                
                # Update current values
                hedge.current_price = live_data["current_price"]
                hedge.pnl_usdc = live_data["pnl"]
                hedge.funding_paid_usdc = live_data["funding_paid"]
                hedge.updated_at = datetime.utcnow()
                
                # Update in database
                await self.db.commit()
            
            return hedge
            
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
            # Get hedge position
            hedge = await self.get_hedge_status(token_id)
            if not hedge:
                raise ValueError(f"No hedge found for position {token_id}")
            
            # Send close request to agent manager
            request_data = {
                "action": "close_hedge",
                "token_id": token_id,
                "hedge_id": hedge.hedge_id,
                "min_usdc_out": min_usdc_out,
                "slippage_bps": slippage_bps
            }
            
            response = await self.agent_service.send_request(
                "position:close:hedge",
                request_data
            )
            
            # Update database
            hedge.status = "closed"
            hedge.closed_at = datetime.utcnow()
            
            # Create closing event
            event = HedgeEvent(
                nft_token_id=token_id,
                hedge_id=hedge.hedge_id,
                event_type="closed",
                tx_hash=response.get("tx_hash"),
                data={
                    "exit_price": str(hedge.current_price),
                    "final_pnl": str(hedge.pnl_usdc),
                    "total_funding_paid": str(hedge.funding_paid_usdc),
                    "usdc_received": str(response.get("usdc_out", 0))
                }
            )
            self.db.add(event)
            
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
            # Get all active hedge positions
            stmt = select(HedgePosition).where(HedgePosition.status == "active")
            result = await self.db.execute(stmt)
            active_hedges = result.scalars().all()
            
            alerts = []
            
            for hedge in active_hedges:
                # Update with live data
                live_data = await self.avantis.get_position_status(
                    hedge.hedge_id,
                    hedge.pair_index
                )
                
                # Update database
                hedge.current_price = live_data["current_price"]
                hedge.pnl_usdc = live_data["pnl"]
                hedge.funding_paid_usdc = live_data["funding_paid"]
                
                # Check health ratio
                health_ratio = hedge.health_ratio
                
                if health_ratio < 0.2:
                    alerts.append({
                        "type": "liquidation_risk",
                        "severity": "critical",
                        "token_id": hedge.nft_token_id,
                        "hedge_id": hedge.hedge_id,
                        "health_ratio": health_ratio,
                        "pnl": float(hedge.pnl_usdc),
                        "message": f"Position {hedge.nft_token_id} at liquidation risk (health: {health_ratio:.2f})"
                    })
                elif health_ratio < 0.4:
                    alerts.append({
                        "type": "low_health",
                        "severity": "warning",
                        "token_id": hedge.nft_token_id,
                        "hedge_id": hedge.hedge_id,
                        "health_ratio": health_ratio,
                        "pnl": float(hedge.pnl_usdc),
                        "message": f"Position {hedge.nft_token_id} has low health (health: {health_ratio:.2f})"
                    })
                
                # Check for high funding costs
                if hedge.funding_paid_usdc and abs(hedge.funding_paid_usdc) > hedge.collateral_usdc * Decimal("0.1"):
                    alerts.append({
                        "type": "high_funding",
                        "severity": "info",
                        "token_id": hedge.nft_token_id,
                        "hedge_id": hedge.hedge_id,
                        "funding_paid": float(hedge.funding_paid_usdc),
                        "message": f"Position {hedge.nft_token_id} has high funding costs"
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
            # Get all hedge positions
            stmt = select(HedgePosition)
            result = await self.db.execute(stmt)
            all_hedges = result.scalars().all()
            
            # Calculate statistics
            total_positions = len(all_hedges)
            active_hedges = sum(1 for h in all_hedges if h.status == "active")
            
            total_value = sum(h.hedge_size_usdc or 0 for h in all_hedges if h.status == "active")
            total_pnl = sum(h.pnl_usdc or 0 for h in all_hedges if h.status == "active")
            total_funding = sum(h.funding_paid_usdc or 0 for h in all_hedges if h.status == "active")
            
            # Average leverage for active positions
            active_with_leverage = [h for h in all_hedges if h.status == "active" and h.leverage]
            avg_leverage = (
                sum(h.leverage for h in active_with_leverage) / len(active_with_leverage)
                if active_with_leverage else 0
            )
            
            # Count at-risk positions
            at_risk_count = sum(1 for h in all_hedges if h.status == "active" and h.is_at_risk)
            
            # Market breakdown
            eth_positions = sum(1 for h in all_hedges if h.market == "ETH-USD" and h.status == "active")
            btc_positions = sum(1 for h in all_hedges if h.market == "BTC-USD" and h.status == "active")
            
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
            # Get positions with and without hedges
            stmt_hedged = select(Position).join(
                HedgePosition,
                Position.token_id == HedgePosition.nft_token_id
            ).where(Position.status == "ACTIVE")
            
            stmt_unhedged = select(Position).outerjoin(
                HedgePosition,
                Position.token_id == HedgePosition.nft_token_id
            ).where(
                and_(
                    Position.status == "ACTIVE",
                    HedgePosition.id.is_(None)
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
            unhedged_pnl = sum(p.total_pnl_usdc for p in unhedged_positions)
            
            hedged_avg_return = (hedged_pnl / hedged_count) if hedged_count > 0 else 0
            unhedged_avg_return = (unhedged_pnl / unhedged_count) if unhedged_count > 0 else 0
            
            # Calculate volatility reduction (simplified)
            effectiveness_ratio = 1.0
            if unhedged_avg_return != 0:
                effectiveness_ratio = abs(hedged_avg_return / unhedged_avg_return)
            
            volatility_reduction = max(0, 1 - effectiveness_ratio) * 100
            
            return {
                "hedged_count": hedged_count,
                "hedged_avg_return": hedged_avg_return,
                "hedged_pnl": hedged_pnl,
                "unhedged_count": unhedged_count,
                "unhedged_avg_return": unhedged_avg_return,
                "unhedged_pnl": unhedged_pnl,
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