"""Strategy factory for configuring different strategy types."""

from typing import List, Dict
from app.schemas.strategy import StrategyTypeEnum

# Pool address constants
WETH_USDC_POOL = "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"
CBBTC_USDC_POOL = "0x4e962bb3889bf030368f56810a9c96b83cb3e778"
USDC_EURC_POOL = "0xE846373C1a92B167b4E9cd5d8E4d6B1Db9E90EC7"
USDC_MSUSD_POOL = "0x7501bc8Bb51616F79bfA524E464fb7B41f0B10fB"
CBLTC_CBBTC_POOL = "0x6044c817e55a03dadc5f6b8b7045af1985ae90fa"
CBADA_CBBTC_POOL = "0x8782d97c8b25b4d17dbfbaa03f25dc18e51e909d"
CBXRP_CBBTC_POOL = "0x95ff4985af7ed78421215be100c18a2b987f7e90"
CBDOGE_CBBTC_POOL = "0x363d1607b8da83d6b6ea76d017ceecf1316bb08a"


class StrategyConfig:
    """
    Configuration for a specific strategy type.

    Provides pool addresses, hedge settings, and allocation splits
    based on the strategy type.
    """

    def __init__(self, strategy_type: StrategyTypeEnum):
        """
        Initialize strategy configuration.

        Args:
            strategy_type: The type of strategy to configure
        """
        self.strategy_type = strategy_type
        self.pools = self._get_pools()
        self.hedged = self._is_hedged()
        self.is_stable = self._is_stable()  # Set is_stable before calling _get_ltv()
        self.hedge_ratio = self._get_hedge_ratio()
        self.allocation_split = self._get_allocation_split()
        self.ltv = self._get_ltv()
        self.slippage_bps = self._get_slippage_bps()

    def _get_pools(self) -> List[str]:
        """
        Return pool addresses for this strategy.

        Returns:
            List of pool contract addresses
        """
        mapping = {
            StrategyTypeEnum.HEDGED_WETH: [WETH_USDC_POOL],
            StrategyTypeEnum.HEDGED_CBBTC: [CBBTC_USDC_POOL],
            StrategyTypeEnum.NONHEDGED_WETH: [WETH_USDC_POOL],
            StrategyTypeEnum.NONHEDGED_CBBTC: [CBBTC_USDC_POOL],
            StrategyTypeEnum.NONHEDGED_CBLTC: [CBLTC_CBBTC_POOL],
            StrategyTypeEnum.NONHEDGED_CBADA: [CBADA_CBBTC_POOL],
            StrategyTypeEnum.NONHEDGED_CBXRP: [CBXRP_CBBTC_POOL],
            StrategyTypeEnum.NONHEDGED_CBDOGE: [CBDOGE_CBBTC_POOL],
            StrategyTypeEnum.STABLE_USDC_EURC: [USDC_EURC_POOL],
            StrategyTypeEnum.STABLE_USDC_MSUSD: [USDC_MSUSD_POOL],
        }
        return mapping[self.strategy_type]

    def _is_hedged(self) -> bool:
        """
        Check if strategy uses hedging.

        Returns:
            True if strategy requires Moonwell hedging
        """
        return self.strategy_type.value.startswith("hedged_")

    def _is_stable(self) -> bool:
        """
        Check if strategy is for stable pairs.

        Returns:
            True if strategy is for stable pairs
        """
        return self.strategy_type.value.startswith("stable_")

    def _get_hedge_ratio(self) -> int:
        """
        Return hedge ratio in basis points.

        For hedged strategies, this determines how much of the
        asset exposure should be hedged via borrowing.

        Returns:
            Hedge ratio in basis points (10000 = 100%)
        """
        if not self.hedged:
            return 0

        # For hedged strategies, aim for full hedge (100%)
        # This neutralizes price risk from the LP position
        return 10000

    def _get_ltv(self) -> float:
        """
        Return loan-to-value ratio for hedged strategies.

        NOTE: This is NOT used for actual position creation. The vault contract's
        find_optimal_strategy() function determines optimal collateral/hedge ratios
        via grid search simulation. This is kept for informational purposes only.

        Stable pairs don't use hedging at all (no Aave borrowing).

        Returns:
            LTV ratio as decimal (0.0 for all, as optimization is done by vault)
        """
        # Stable pairs never use hedging
        if self.is_stable:
            return 0.0

        # For hedged strategies, optimal ratios are determined by vault contract
        # via find_optimal_strategy() which does grid search (55-70% collateral, 92-98% hedge)
        # This value is not used in actual position creation
        return 0.0

    def _get_allocation_split(self) -> Dict[str, float]:
        """
        Return capital allocation percentages per pool.

        For blueprint strategies (multiple pools), splits capital evenly.
        For single-pool strategies, allocates 100% to that pool.

        Returns:
            Dictionary mapping pool address to allocation percentage (0.0-1.0)
        """
        pools = self.pools

        # Blueprint strategies split 50/50 between pools
        if "blueprint" in self.strategy_type.value:
            return {pool: 0.5 for pool in pools}

        # Single-pool strategies allocate 100% to that pool
        return {pools[0]: 1.0}

    def _get_slippage_bps(self) -> int:
        """
        Return slippage tolerance in basis points for this strategy.

        Returns:
            Slippage in basis points (e.g., 300 = 3%)
        """
        # USDC/EURC (s1) gets 3% slippage due to lower liquidity
        if self.strategy_type == StrategyTypeEnum.STABLE_USDC_EURC:
            return 300  # 3%

        # All other strategies get 0.5% slippage
        return 50  # 0.5%

    def get_pool_allocation(self, pool_address: str, total_capital: float) -> float:
        """
        Get capital allocation for a specific pool.

        Args:
            pool_address: Pool contract address
            total_capital: Total capital available in USDC

        Returns:
            Capital allocated to this pool in USDC
        """
        allocation_pct = self.allocation_split.get(pool_address, 0.0)
        return total_capital * allocation_pct

    def __repr__(self):
        return (
            f"<StrategyConfig("
            f"type={self.strategy_type.value}, "
            f"hedged={self.hedged}, "
            f"pools={len(self.pools)}, "
            f"ltv={self.ltv})>"
        )


def get_strategy_config(strategy_type: StrategyTypeEnum) -> StrategyConfig:
    """
    Factory function to create a StrategyConfig.

    Args:
        strategy_type: The type of strategy to configure

    Returns:
        StrategyConfig instance
    """
    return StrategyConfig(strategy_type)
