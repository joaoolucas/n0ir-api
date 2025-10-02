"""
Vault Contract Integration for delta-neutral position simulations.
"""
from typing import Dict, Tuple
from web3 import Web3
from loguru import logger
from app.core.config import settings


class VaultContract:
    """Service for interacting with the vault contract."""

    def __init__(self):
        """Initialize vault contract service."""
        self.w3 = Web3(Web3.HTTPProvider(settings.rpc_url))

        # Vault contract address (using liquidity manager address)
        self.vault_address = settings.liquidity_manager_address

        # Token addresses for symbol lookup
        self.token_symbols = {
            "0x4200000000000000000000000000000000000006": "WETH",
            settings.weth_address.lower(): "WETH",
            settings.cbbtc_address if hasattr(settings, 'cbbtc_address') else "": "cbBTC"
        }

        # ABI for the functions we need
        self.abi = [
            {
                "inputs": [
                    {"internalType": "address", "name": "poolAddress", "type": "address"},
                    {"internalType": "uint256", "name": "totalUSDC", "type": "uint256"},
                    {"internalType": "uint256", "name": "rangePercentage", "type": "uint256"}
                ],
                "name": "calculateOptimalUsdcAllocation",
                "outputs": [
                    {"internalType": "uint256", "name": "usdc0", "type": "uint256"},
                    {"internalType": "uint256", "name": "usdc1", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "usdcAmount", "type": "uint256"},
                    {"internalType": "address", "name": "pool", "type": "address"},
                    {"internalType": "uint256", "name": "rangePercentage", "type": "uint256"},
                    {"internalType": "uint256", "name": "collateralRatioBps", "type": "uint256"},
                    {"internalType": "uint256", "name": "hedgeRatio", "type": "uint256"}
                ],
                "name": "simulateHedge",
                "outputs": [
                    {
                        "components": [
                            {"internalType": "address", "name": "hedgeAsset", "type": "address"},
                            {"internalType": "uint8", "name": "assetDecimals", "type": "uint8"},
                            {"internalType": "uint256", "name": "currentAssetPrice", "type": "uint256"},
                            {"internalType": "uint256", "name": "assetExposureBps", "type": "uint256"},
                            {"internalType": "uint256", "name": "collateralAmount", "type": "uint256"},
                            {"internalType": "uint256", "name": "lpBaseAmount", "type": "uint256"},
                            {"internalType": "uint256", "name": "borrowAmountUSD", "type": "uint256"},
                            {"internalType": "uint256", "name": "borrowAmountAsset", "type": "uint256"},
                            {"internalType": "uint256", "name": "totalLPAmount", "type": "uint256"},
                            {"internalType": "uint256", "name": "expectedHealthFactor", "type": "uint256"},
                            {"internalType": "uint256", "name": "liquidationPrice", "type": "uint256"},
                            {"internalType": "uint256", "name": "leverageMultiplierBps", "type": "uint256"},
                            {"internalType": "bool", "name": "isHealthy", "type": "bool"}
                        ],
                        "internalType": "struct HedgeManager.HedgeSimulation",
                        "name": "",
                        "type": "tuple"
                    }
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"}
                ],
                "name": "getPositionDetails",
                "outputs": [
                    {"internalType": "address", "name": "owner", "type": "address"},
                    {"internalType": "uint256", "name": "collateral", "type": "uint256"},
                    {"internalType": "uint256", "name": "debt", "type": "uint256"},
                    {"internalType": "address", "name": "hedgedAsset", "type": "address"},
                    {"internalType": "bool", "name": "isHedged", "type": "bool"},
                    {"internalType": "uint256", "name": "collateralSupplyAPY", "type": "uint256"},
                    {"internalType": "uint256", "name": "hedgedAssetBorrowAPY", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "getGlobalHealthMetrics",
                "outputs": [
                    {"internalType": "uint256", "name": "totalCollateral", "type": "uint256"},
                    {"internalType": "uint256", "name": "totalDebtWETH", "type": "uint256"},
                    {"internalType": "uint256", "name": "totalDebtBTC", "type": "uint256"},
                    {"internalType": "uint256", "name": "healthFactor", "type": "uint256"},
                    {"internalType": "uint256", "name": "availableBorrowsUSD", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "isProtocolAtRisk",
                "outputs": [
                    {"internalType": "bool", "name": "isAtRisk", "type": "bool"},
                    {"internalType": "uint256", "name": "currentHealthFactor", "type": "uint256"},
                    {"internalType": "uint256", "name": "minSafeHealthFactor", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "user", "type": "address"}
                ],
                "name": "getUserPositions",
                "outputs": [
                    {"internalType": "uint256[]", "name": "", "type": "uint256[]"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]

        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.vault_address),
            abi=self.abi
        )

    def calculate_optimal_allocation(
        self,
        pool_address: str,
        total_usdc: float,
        range_percentage: int
    ) -> Tuple[float, float]:
        """
        Calculate optimal USDC allocation between collateral and LP.

        Args:
            pool_address: Pool address
            total_usdc: Total USDC amount
            range_percentage: Range percentage (e.g., 20 for ±10%)

        Returns:
            Tuple of (usdc_for_collateral, usdc_for_lp_base)
        """
        try:
            usdc_wei = int(total_usdc * 1e6)  # USDC has 6 decimals

            result = self.contract.functions.calculateOptimalUsdcAllocation(
                Web3.to_checksum_address(pool_address),
                usdc_wei,
                range_percentage
            ).call()

            usdc0 = result[0] / 1e6  # Convert back to USDC
            usdc1 = result[1] / 1e6

            logger.info(f"Optimal allocation: {usdc0} for collateral, {usdc1} for LP base")
            return (usdc0, usdc1)

        except Exception as e:
            logger.error(f"Error calculating optimal allocation: {e}")
            # Fallback to default allocation
            return (total_usdc * 0.6, total_usdc * 0.4)

    def simulate_hedge(
        self,
        usdc_amount: float,
        pool_address: str,
        range_percentage: int,
        collateral_ratio_bps: int,
        hedge_ratio: int
    ) -> Dict:
        """
        Simulate a hedge position.

        Args:
            usdc_amount: USDC amount
            pool_address: Pool address
            range_percentage: Range percentage (e.g., 20 for ±10%)
            collateral_ratio_bps: Collateral ratio in basis points (e.g., 6000 = 60%)
            hedge_ratio: Hedge ratio (e.g., 9500 = 95%)

        Returns:
            Simulation results as dictionary
        """
        try:
            if usdc_amount <= 0:
                raise ValueError(f"USDC amount must be greater than 0, got: {usdc_amount}")

            usdc_wei = int(usdc_amount * 1e6)

            logger.info(f"Calling simulateHedge with: usdc={usdc_wei}, pool={pool_address}, range={range_percentage}%, ratios={collateral_ratio_bps}/{hedge_ratio}")

            result = self.contract.functions.simulateHedge(
                usdc_wei,
                Web3.to_checksum_address(pool_address),
                range_percentage,
                collateral_ratio_bps,
                hedge_ratio
            ).call()

            # Parse the tuple result into a dict
            simulation = {
                'hedge_asset': result[0],
                'asset_decimals': result[1],
                'current_asset_price': result[2] / 1e8,  # Assuming 8 decimals for price
                'asset_exposure_bps': result[3],
                'collateral_amount': result[4] / 1e6,
                'lp_base_amount': result[5] / 1e6,
                'borrow_amount_usd': result[6] / 1e6,
                'borrow_amount_asset': result[7] / (10 ** result[1]),  # Use asset decimals
                'total_lp_amount': result[8] / 1e6,
                'expected_health_factor': result[9] / 1e18,
                'liquidation_price': result[10] / 1e8,
                'leverage_multiplier_bps': result[11],
                'is_healthy': result[12]
            }

            logger.debug(f"Simulation result: health={simulation['is_healthy']}, hf={simulation['expected_health_factor']:.2f}")

            return simulation

        except Exception as e:
            import traceback
            logger.error(f"Error simulating hedge: {type(e).__name__}: {e}")
            logger.error(f"  Contract address: {self.vault_address}")
            logger.error(f"  Parameters: usdc_amount={usdc_amount}, pool={pool_address}, range={range_percentage}%")
            logger.error(f"  Full traceback: {traceback.format_exc()}")
            raise

    def find_optimal_strategy(
        self,
        usdc_amount: float,
        pool_address: str,
        range_percentage: int
    ) -> Dict:
        """
        Find optimal hedge parameters using simple grid search.

        Args:
            usdc_amount: USDC amount
            pool_address: Pool address
            range_percentage: Range percentage (e.g., 20 for ±10%)

        Returns:
            Optimal strategy with simulation results
        """
        if usdc_amount <= 0:
            raise ValueError(f"USDC amount must be greater than 0, got: {usdc_amount}")

        best_score = 0
        best_strategy = None
        errors = []
        unhealthy_count = 0
        low_hf_count = 0

        # Simple grid search
        for collateral_ratio in range(5500, 7000, 500):  # 55-70% in 5% steps
            for hedge_ratio in range(9200, 10000, 200):  # 92-98% in 2% steps
                try:
                    simulation = self.simulate_hedge(
                        usdc_amount,
                        pool_address,
                        range_percentage,
                        collateral_ratio,
                        hedge_ratio
                    )

                    # Skip unhealthy positions
                    if not simulation['is_healthy']:
                        unhealthy_count += 1
                        logger.debug(f"Unhealthy position for {collateral_ratio}/{hedge_ratio}")
                        continue

                    # Skip if health factor too low
                    if simulation['expected_health_factor'] < 1.75:
                        low_hf_count += 1
                        logger.debug(f"Health factor too low ({simulation['expected_health_factor']}) for {collateral_ratio}/{hedge_ratio}")
                        continue

                    # Calculate delta-neutral score
                    exposure_usd = simulation['total_lp_amount'] * (simulation['asset_exposure_bps'] / 10000)
                    delta = abs(simulation['borrow_amount_usd'] - exposure_usd)

                    # Avoid division by zero
                    if simulation['total_lp_amount'] == 0:
                        continue

                    score = 1 - (delta / simulation['total_lp_amount'])

                    # Update best if better
                    if score > best_score:
                        best_score = score
                        best_strategy = {
                            'collateral_ratio_bps': collateral_ratio,
                            'hedge_ratio': hedge_ratio,
                            'simulation': simulation,
                            'delta_neutral_score': score,
                            'exposure_usd': exposure_usd,
                            'net_delta_usd': delta
                        }

                except Exception as e:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    if error_msg not in errors:
                        errors.append(error_msg)
                    logger.debug(f"Simulation failed for params {collateral_ratio}/{hedge_ratio}: {e}")
                    continue

        if not best_strategy:
            # Log detailed diagnostics
            total_attempts = len(range(5500, 7000, 500)) * len(range(9200, 10000, 200))
            logger.error(f"Could not find viable strategy. Diagnostics:")
            logger.error(f"  Total attempts: {total_attempts}")
            logger.error(f"  Failed with exceptions: {len(errors)}")
            logger.error(f"  Unhealthy positions: {unhealthy_count}")
            logger.error(f"  Low health factor (<1.75): {low_hf_count}")
            if errors:
                logger.error(f"  Sample errors: {errors[:3]}")
            raise ValueError("Could not find a viable hedge strategy - all simulations failed or returned unhealthy positions")

        logger.info(f"Found optimal strategy with delta-neutral score: {best_score:.4f}")
        return best_strategy

    def get_user_positions(self, wallet_address: str) -> list:
        """
        Get all position token IDs for a user.

        Args:
            wallet_address: User's wallet address

        Returns:
            List of token IDs
        """
        try:
            result = self.contract.functions.getUserPositions(
                Web3.to_checksum_address(wallet_address)
            ).call()

            return result

        except Exception as e:
            logger.error(f"Error getting user positions: {e}")
            return []

    def get_position_details(self, token_id: int) -> Dict:
        """
        Get full details for a specific position.

        Args:
            token_id: NFT token ID

        Returns:
            Dictionary with position details
        """
        try:
            result = self.contract.functions.getPositionDetails(token_id).call()

            position_details = {
                'owner': result[0],
                'collateral': result[1] / 1e6,  # USDC has 6 decimals
                'debt': result[2],  # Keep in wei for now
                'hedged_asset': result[3],
                'is_hedged': result[4],
                'collateral_supply_apy': result[5] / 1e2,  # APY in basis points (divide by 100 to get percentage)
                'hedged_asset_borrow_apy': result[6] / 1e2  # APY in basis points (divide by 100 to get percentage)
            }

            return position_details

        except Exception as e:
            logger.error(f"Error getting position details for token {token_id}: {e}")
            raise

    def get_global_health_metrics(self) -> Dict:
        """
        Get global health metrics for the protocol.

        Returns:
            Dictionary with global health metrics
        """
        try:
            result = self.contract.functions.getGlobalHealthMetrics().call()

            metrics = {
                'total_collateral': result[0] / 1e6,
                'total_debt_weth': result[1] / 1e18,
                'total_debt_btc': result[2] / 1e8,
                'health_factor': result[3] / 1e18,
                'available_borrows_usd': result[4] / 1e6
            }

            return metrics

        except Exception as e:
            logger.error(f"Error getting global health metrics: {e}")
            raise

    def is_protocol_at_risk(self) -> tuple:
        """
        Check if protocol is at risk.

        Returns:
            Tuple of (is_at_risk, current_health_factor, min_safe_health_factor)
        """
        try:
            result = self.contract.functions.isProtocolAtRisk().call()

            return (
                result[0],  # is_at_risk
                result[1] / 1e18,  # current_health_factor
                result[2] / 1e18   # min_safe_health_factor
            )

        except Exception as e:
            logger.error(f"Error checking protocol risk: {e}")
            raise

    def get_token_symbol(self, address: str) -> str:
        """Get token symbol from address."""
        return self.token_symbols.get(address.lower(), address[:8])


# Singleton instance
vault_contract = VaultContract()
