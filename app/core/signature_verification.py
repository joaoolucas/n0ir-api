"""Ethereum wallet signature verification utilities."""

from eth_account.messages import encode_defunct
from eth_account import Account
from loguru import logger


def verify_wallet_signature(wallet: str, signature: str, message: str) -> bool:
    """
    Verify that a signature was created by a specific wallet address.

    Args:
        wallet: Ethereum wallet address (0x...)
        signature: Hex signature string
        message: Original message that was signed

    Returns:
        True if signature is valid and matches wallet, False otherwise
    """
    try:
        # Encode message for eth_sign
        message_hash = encode_defunct(text=message)

        # Recover the address that signed this message
        recovered_address = Account.recover_message(message_hash, signature=signature)

        # Compare addresses (case-insensitive)
        is_valid = recovered_address.lower() == wallet.lower()

        if is_valid:
            logger.info(f"Valid signature from wallet {wallet[:10]}...")
        else:
            logger.warning(f"Invalid signature - expected {wallet[:10]}..., got {recovered_address[:10]}...")

        return is_valid

    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False
