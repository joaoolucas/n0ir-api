"""
GPT-5 Nano Strategy Service for delta-neutral position management.
Integrates with OpenAI GPT-5 Nano for fast, intelligent trading decisions.
"""
import json
import os
from typing import Dict, List, Optional, Any
from decimal import Decimal
from loguru import logger
import openai
from openai import AsyncOpenAI

from app.schemas.users import LPAllocation, Hedge
from app.core.config import settings


class GPTStrategyService:
    """Service for GPT-5 Nano powered strategy decisions."""

    def __init__(self):
        """Initialize OpenAI client."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set, GPT strategy service will use fallback logic")
            self.client = None
        else:
            # Log that we have an API key (but not the key itself for security)
            logger.info(f"OpenAI API key configured (length: {len(api_key)})")
            self.client = AsyncOpenAI(api_key=api_key)

        # Model to use - GPT-5 Nano for fast, cost-effective decisions
        self.model = "gpt-5-nano"

    async def generate_initial_strategy(
        self,
        balance: float,
        existing_positions: List[Dict],
        pool_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate initial delta-neutral strategy allocations.

        Args:
            balance: Available USDC balance
            existing_positions: Current user positions
            pool_data: Pool information including APRs

        Returns:
            Strategy with LP allocations and hedges
        """
        if not self.client:
            return self._fallback_initial_strategy(balance, existing_positions, pool_data)

        try:
            prompt = self._build_initial_strategy_prompt(balance, existing_positions, pool_data)

            logger.info(f"Attempting to use OpenAI model: {self.model}")
            # Try without response_format for GPT-5 nano compatibility
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a DeFi strategy expert. Reply with valid JSON only, no other text."},
                    {"role": "user", "content": prompt + "\n\nIMPORTANT: Reply with valid JSON only."}
                ],
                # Removed response_format as it might not be supported by GPT-5 nano
                # temperature=1 is default, GPT-5 nano only supports default
                max_completion_tokens=1000  # Changed from max_tokens for GPT-5 nano
            )

            # Debug log the raw response
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                logger.info(f"GPT response content length: {len(content) if content else 0}")
                if not content or content.strip() == "":
                    logger.warning("GPT returned empty response, using fallback")
                    return self._fallback_initial_strategy(balance, existing_positions, pool_data)

                result = json.loads(content)
                logger.info(f"GPT strategy generated successfully")
                return result
            else:
                logger.warning("GPT returned no choices, using fallback")
                return self._fallback_initial_strategy(balance, existing_positions, pool_data)

        except openai.RateLimitError as e:
            logger.error(f"OpenAI rate limit or quota error: {e}")
            logger.info("Using fallback strategy due to OpenAI quota issue")
            return self._fallback_initial_strategy(balance, existing_positions, pool_data)
        except Exception as e:
            logger.error(f"GPT strategy generation failed with model {self.model}: {e}")
            return self._fallback_initial_strategy(balance, existing_positions, pool_data)

    async def evaluate_range_break(
        self,
        position_data: Dict,
        market_data: Dict,
        current_balance: float
    ) -> Dict[str, Any]:
        """
        Evaluate action to take when position goes out of range.

        Args:
            position_data: Current position information
            market_data: Current market prices and conditions
            current_balance: Available USDC balance

        Returns:
            Action recommendation for range break
        """
        if not self.client:
            return self._fallback_range_break_action(position_data, market_data)

        try:
            prompt = self._build_range_break_prompt(position_data, market_data, current_balance)

            # Try without response_format for GPT-5 nano compatibility
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a DeFi position manager. Reply with valid JSON only, no other text."},
                    {"role": "user", "content": prompt + "\n\nIMPORTANT: Reply with valid JSON only."}
                ],
                # Removed response_format as it might not be supported by GPT-5 nano
                # temperature=1 is default, GPT-5 nano only supports default
                max_completion_tokens=800  # Changed from max_tokens for GPT-5 nano
            )

            # Check for empty response
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                if not content or content.strip() == "":
                    logger.warning("GPT returned empty response for range break, using fallback")
                    return self._fallback_range_break_action(position_data, market_data)

                result = json.loads(content)
                logger.info(f"GPT range break evaluation completed")
                return result
            else:
                logger.warning("GPT returned no choices for range break, using fallback")
                return self._fallback_range_break_action(position_data, market_data)

        except Exception as e:
            logger.error(f"GPT range break evaluation failed: {e}")
            return self._fallback_range_break_action(position_data, market_data)

    def _build_initial_strategy_prompt(
        self,
        balance: float,
        existing_positions: List[Dict],
        pool_data: Dict
    ) -> str:
        """Build prompt for initial strategy generation."""

        # Extract pool APRs
        weth_apr = pool_data.get("WETH/USDC", {}).get("apr", 100)
        btc_apr = pool_data.get("cbBTC/USDC", {}).get("apr", 80)

        prompt = f"""
        You are managing a delta-neutral DeFi strategy with the following context:

        Available Balance: ${balance:.2f} USDC
        Existing Positions: {len(existing_positions)} positions

        Pool Information:
        - WETH/USDC APR: {weth_apr}%
        - cbBTC/USDC APR: {btc_apr}%

        Current Market:
        - ETH Price: ${pool_data.get('eth_price', 3500)}
        - BTC Price: ${pool_data.get('btc_price', 65000)}
        - ETH Funding Rate: {pool_data.get('eth_funding', -0.02)}%
        - BTC Funding Rate: {pool_data.get('btc_funding', -0.01)}%

        Strategy Rules:
        1. If balance < $2000: Use single position (WETH/USDC preferred due to higher APR)
        2. If balance >= $2000: Split between WETH/USDC (priority) and cbBTC/USDC (stability)
        3. Allocate 90% to LP positions, 10% to short hedges
        4. Use 5x leverage for shorts (so 10% collateral = 50% notional hedge)
        5. Keep 1% as reserve for gas/slippage
        6. Range should be 5% around current price for concentrated liquidity

        Generate optimal allocations. Output must be valid JSON with this structure:
        {{
            "lp_allocations": [
                {{
                    "pair": "WETH/USDC or cbBTC/USDC",
                    "amount_usd": decimal,
                    "range_pct": 5
                }}
            ],
            "hedges": [
                {{
                    "asset": "ETH or BTC",
                    "side": "short",
                    "collateral_usd": decimal,
                    "leverage": 5,
                    "notional_exposure_usd": collateral * leverage
                }}
            ],
            "notes": "Brief explanation of strategy"
        }}
        """

        return prompt

    def _build_range_break_prompt(
        self,
        position_data: Dict,
        market_data: Dict,
        current_balance: float
    ) -> str:
        """Build prompt for range break evaluation."""

        prompt = f"""
        A liquidity position has gone out of range. Evaluate the best action:

        Position Details:
        - Pool: {position_data.get('pool_name')}
        - Current Value: ${position_data.get('current_value', 0):.2f}
        - Time Out of Range: {position_data.get('time_out_of_range', 0)} hours
        - APR When In Range: {position_data.get('apr_in_range', 0)}%

        Market Conditions:
        - Current Price: ${market_data.get('current_price', 0)}
        - 24h Price Change: {market_data.get('price_change_24h', 0)}%
        - Volatility: {market_data.get('volatility', 'medium')}
        - Trend: {market_data.get('trend', 'neutral')}

        Available Balance: ${current_balance:.2f}
        Estimated Gas Cost: $50

        Options:
        1. "close_and_reopen": Close position and reopen with new range (costs ~$100 gas)
        2. "wait": Wait for price to return to range (no gas cost but no APR earned)
        3. "adjust_hedge": Only adjust the hedge position (costs ~$50 gas)

        Consider:
        - Gas costs vs potential APR gains
        - Market momentum and reversal probability
        - Time value of capital

        Output must be valid JSON:
        {{
            "action": "close_and_reopen" or "wait" or "adjust_hedge",
            "new_lp_allocation": {{
                "pair": "pool pair",
                "amount_usd": decimal,
                "range_pct": 5
            }} or null,
            "hedge": {{
                "asset": "ETH or BTC",
                "side": "short",
                "collateral_usd": decimal,
                "leverage": 5,
                "notional_exposure_usd": decimal
            }} or null,
            "reason": "Explanation of decision"
        }}
        """

        return prompt

    def _fallback_initial_strategy(
        self,
        balance: float,
        existing_positions: List[Dict],
        pool_data: Dict
    ) -> Dict[str, Any]:
        """Fallback strategy when GPT is unavailable."""

        # Reserve 1% for gas
        deployable = balance * 0.99

        # 90% to LP, 10% to hedge
        lp_allocation = deployable * 0.9
        hedge_allocation = deployable * 0.1

        strategy = {
            "lp_allocations": [],
            "hedges": [],
            "notes": "Fallback strategy (GPT unavailable)"
        }

        if balance < 2000:
            # Single position strategy
            strategy["lp_allocations"].append({
                "pair": "WETH/USDC",
                "amount_usd": float(lp_allocation),
                "range_pct": 5
            })
            strategy["hedges"].append({
                "asset": "ETH",
                "side": "short",
                "collateral_usd": float(hedge_allocation),
                "leverage": 5,
                "notional_exposure_usd": float(hedge_allocation * 5)
            })
            strategy["notes"] = f"Single position strategy for balance < $2000. WETH/USDC for higher APR."
        else:
            # Two position strategy
            weth_allocation = lp_allocation * 0.6  # 60% to WETH
            btc_allocation = lp_allocation * 0.4   # 40% to BTC

            strategy["lp_allocations"].extend([
                {
                    "pair": "WETH/USDC",
                    "amount_usd": float(weth_allocation),
                    "range_pct": 5
                },
                {
                    "pair": "cbBTC/USDC",
                    "amount_usd": float(btc_allocation),
                    "range_pct": 5
                }
            ])

            # Proportional hedges
            weth_hedge = hedge_allocation * 0.6
            btc_hedge = hedge_allocation * 0.4

            strategy["hedges"].extend([
                {
                    "asset": "ETH",
                    "side": "short",
                    "collateral_usd": float(weth_hedge),
                    "leverage": 5,
                    "notional_exposure_usd": float(weth_hedge * 5)
                },
                {
                    "asset": "BTC",
                    "side": "short",
                    "collateral_usd": float(btc_hedge),
                    "leverage": 5,
                    "notional_exposure_usd": float(btc_hedge * 5)
                }
            ])
            strategy["notes"] = f"Diversified strategy for balance >= $2000. 60% WETH (higher APR), 40% BTC (stability)."

        return strategy

    def _fallback_range_break_action(
        self,
        position_data: Dict,
        market_data: Dict
    ) -> Dict[str, Any]:
        """Fallback range break action when GPT is unavailable."""

        # Simple rule-based logic
        time_out = position_data.get('time_out_of_range', 0)
        position_value = position_data.get('current_value', 0)
        apr = position_data.get('apr_in_range', 0)

        # If out of range > 24 hours and position > $1000, reopen
        if time_out > 24 and position_value > 1000:
            action = "close_and_reopen"
            reason = f"Position out of range for {time_out}h. Reopening to capture {apr}% APR."
        # If small position or recently out of range, wait
        elif position_value < 500 or time_out < 6:
            action = "wait"
            reason = f"Small position or recently out of range. Waiting for price reversal."
        # Medium case - adjust hedge only
        else:
            action = "adjust_hedge"
            reason = f"Adjusting hedge to maintain delta neutrality while waiting for range re-entry."

        return {
            "action": action,
            "reason": reason,
            "new_lp_allocation": {
                "pair": position_data.get('pool_name', 'WETH/USDC'),
                "amount_usd": float(position_value),
                "range_pct": 5
            } if action == "close_and_reopen" else None,
            "hedge": {
                "asset": "ETH" if "WETH" in position_data.get('pool_name', '') else "BTC",
                "side": "short",
                "collateral_usd": float(position_value * 0.1),
                "leverage": 5,
                "notional_exposure_usd": float(position_value * 0.5)
            } if action in ["close_and_reopen", "adjust_hedge"] else None
        }


# Singleton instance
gpt_strategy_service = GPTStrategyService()