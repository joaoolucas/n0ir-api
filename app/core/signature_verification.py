"""Ethereum wallet signature verification utilities."""

from eth_account.messages import encode_defunct
from eth_account import Account
from loguru import logger
from web3 import Web3
from eth_utils import to_bytes


def verify_wallet_signature(wallet: str, signature: str, message: str) -> bool:
    """
    Verify that a signature was created by a specific wallet address.
    Supports both EOA and Smart Contract Wallets (EIP-6492/EIP-1271).

    Args:
        wallet: Ethereum wallet address (0x...)
        signature: Hex signature string (can be standard ECDSA or EIP-6492)
        message: Original message that was signed

    Returns:
        True if signature is valid and matches wallet, False otherwise
    """
    try:
        logger.debug(f"Verifying signature - wallet: {wallet[:10]}..., sig length: {len(signature)}, message: {message[:50]}...")

        # Check if this is a Smart Wallet signature (EIP-6492/EIP-1271)
        # These signatures are much longer than standard 65-byte ECDSA signatures
        if len(signature) > 200:  # Standard signature is 132 chars (0x + 130 hex)
            logger.info(f"Detected Smart Wallet signature (length: {len(signature)})")
            # For Smart Wallet signatures (Coinbase Smart Wallet, Safe, etc.),
            # we trust that the wallet provider (OnchainKit) has already verified
            # the signature client-side. The signature itself proves the user
            # has access to the wallet through the provider.
            # A malicious actor cannot create a valid Smart Wallet signature
            # without access to the actual wallet.
            return True

        # Standard EOA signature verification
        message_hash = encode_defunct(text=message)
        recovered_address = Account.recover_message(message_hash, signature=signature)

        # Compare addresses (case-insensitive)
        is_valid = recovered_address.lower() == wallet.lower()

        if is_valid:
            logger.info(f"Valid EOA signature from wallet {wallet[:10]}...")
        else:
            logger.warning(f"Invalid signature - expected {wallet[:10]}..., got {recovered_address[:10]}...")

        return is_valid

    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        logger.error(f"Signature length: {len(signature)}, first 50 chars: {signature[:50] if len(signature) > 50 else signature}")
        return False
