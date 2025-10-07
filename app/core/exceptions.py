"""Custom exceptions for the n0ir API application."""

from typing import Optional, Dict, Any


class N0irAPIException(Exception):
    """Base exception for all n0ir API exceptions."""
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}


# Hedge-related exceptions
class HedgeError(N0irAPIException):
    """Base exception for hedge operations."""
    pass


class InsufficientCollateralError(HedgeError):
    """Raised when hedge collateral is insufficient."""
    
    def __init__(
        self,
        required: float,
        available: float,
        message: Optional[str] = None
    ):
        if message is None:
            message = f"Insufficient collateral: required {required} USDC, available {available} USDC"
        super().__init__(
            message=message,
            code="INSUFFICIENT_COLLATERAL",
            details={
                "required_usdc": required,
                "available_usdc": available,
                "shortfall_usdc": required - available
            }
        )


class HedgeNotFoundError(HedgeError):
    """Raised when hedge position not found."""
    
    def __init__(self, token_id: int, message: Optional[str] = None):
        if message is None:
            message = f"No hedge position found for NFT token {token_id}"
        super().__init__(
            message=message,
            code="HEDGE_NOT_FOUND",
            details={"token_id": token_id}
        )


class HedgeLiquidationRiskError(HedgeError):
    """Raised when hedge position is at liquidation risk."""
    
    def __init__(
        self,
        token_id: int,
        health_ratio: float,
        message: Optional[str] = None
    ):
        if message is None:
            message = f"Hedge position {token_id} at liquidation risk (health ratio: {health_ratio:.2f})"
        super().__init__(
            message=message,
            code="LIQUIDATION_RISK",
            details={
                "token_id": token_id,
                "health_ratio": health_ratio,
                "critical": health_ratio < 0.2
            }
        )


class HedgeCreationError(HedgeError):
    """Raised when hedge creation fails."""
    
    def __init__(self, reason: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Failed to create hedge: {reason}",
            code="HEDGE_CREATION_FAILED",
            details=details or {}
        )


class HedgeClosureError(HedgeError):
    """Raised when hedge closure fails."""
    
    def __init__(self, token_id: int, reason: str):
        super().__init__(
            message=f"Failed to close hedge for position {token_id}: {reason}",
            code="HEDGE_CLOSURE_FAILED",
            details={"token_id": token_id, "reason": reason}
        )


# Position-related exceptions
class PositionError(N0irAPIException):
    """Base exception for position operations."""
    pass


class PositionNotFoundError(PositionError):
    """Raised when position not found."""
    
    def __init__(self, position_id: int):
        super().__init__(
            message=f"Position {position_id} not found",
            code="POSITION_NOT_FOUND",
            details={"position_id": position_id}
        )


class InvalidPositionRangeError(PositionError):
    """Raised when position range is invalid."""
    
    def __init__(self, tick_lower: int, tick_upper: int, reason: str):
        super().__init__(
            message=f"Invalid position range [{tick_lower}, {tick_upper}]: {reason}",
            code="INVALID_RANGE",
            details={
                "tick_lower": tick_lower,
                "tick_upper": tick_upper,
                "reason": reason
            }
        )


# Integration exceptions
class IntegrationError(N0irAPIException):
    """Base exception for external integration errors."""
    pass


class BlockchainConnectionError(IntegrationError):
    """Raised when blockchain connection fails."""
    
    def __init__(self, rpc_url: str, reason: str):
        super().__init__(
            message=f"Failed to connect to blockchain at {rpc_url}: {reason}",
            code="BLOCKCHAIN_CONNECTION_FAILED",
            details={"rpc_url": rpc_url}
        )


class ContractCallError(IntegrationError):
    """Raised when smart contract call fails."""
    
    def __init__(
        self,
        contract_address: str,
        method: str,
        reason: str
    ):
        super().__init__(
            message=f"Contract call failed: {contract_address}.{method}() - {reason}",
            code="CONTRACT_CALL_FAILED",
            details={
                "contract": contract_address,
                "method": method,
                "reason": reason
            }
        )


class AgentCommunicationError(IntegrationError):
    """Raised when agent communication fails."""
    
    def __init__(self, action: str, reason: str):
        super().__init__(
            message=f"Agent communication failed for action '{action}': {reason}",
            code="AGENT_COMMUNICATION_FAILED",
            details={"action": action}
        )


# Validation exceptions
class ValidationError(N0irAPIException):
    """Base exception for validation errors."""
    pass


class InvalidParameterError(ValidationError):
    """Raised when parameter validation fails."""
    
    def __init__(
        self,
        parameter: str,
        value: Any,
        constraint: str
    ):
        super().__init__(
            message=f"Invalid parameter '{parameter}': {constraint}",
            code="INVALID_PARAMETER",
            details={
                "parameter": parameter,
                "value": value,
                "constraint": constraint
            }
        )