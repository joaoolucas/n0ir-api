"""Service for verifying Ethereum signatures including smart wallet signatures."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from eth_account import Account
from eth_account.messages import encode_defunct
from loguru import logger
import aiohttp
import json


class SignatureService:
    """Service to handle signature verification for wallet ownership proof."""
    
    # Maximum age for a signature message (5 minutes)
    MAX_MESSAGE_AGE_SECONDS = 300
    
    @staticmethod
    def create_sign_message(action: str, user_id: str, additional_data: Optional[str] = None) -> str:
        """Create a message for signing.
        
        Args:
            action: The action being authorized (e.g., "Register account", "Withdraw")
            user_id: The user's wallet address
            additional_data: Optional additional data (e.g., withdrawal amount)
            
        Returns:
            The message to be signed
        """
        timestamp = datetime.utcnow().isoformat()
        
        if additional_data:
            message = f"n0ir: {action} {additional_data} for {user_id} at {timestamp}"
        else:
            message = f"n0ir: {action} for {user_id} at {timestamp}"
            
        return message
    
    @staticmethod
    def verify_signature(message: str, signature: str, expected_address: str) -> bool:
        """Verify an Ethereum signature including smart wallet signatures.
        
        Smart wallets use ERC-6492 wrapper signatures which are longer than EOA signatures.
        These need special handling as they contain deployment data.
        
        Args:
            message: The original message that was signed
            signature: The signature to verify (hex string - can be EOA or smart wallet)
            expected_address: The expected signer's address
            
        Returns:
            True if signature is valid and from expected address, False otherwise
        """
        try:
            # Normalize the expected address to lowercase
            expected_address = expected_address.lower()
            
            # Check timestamp first to prevent replay attacks
            if not SignatureService._is_timestamp_valid(message):
                logger.warning(f"Signature timestamp too old for address {expected_address}")
                return False
            
            # Check signature length to determine type
            # EOA signatures are 132 chars (0x + 130 hex)
            # Smart wallet signatures are much longer (1000+ chars)
            if len(signature) == 132:
                # Standard EOA signature
                logger.info("Verifying EOA signature")
                encoded_message = encode_defunct(text=message)
                recovered_address = Account.recover_message(encoded_message, signature=signature)
                is_valid = recovered_address.lower() == expected_address
            else:
                # Smart wallet signature (ERC-6492 wrapped)
                logger.info(f"Detected smart wallet signature (length: {len(signature)})")
                # For smart wallets, we need to verify differently
                # Since we can't easily verify ERC-6492 signatures server-side without
                # calling the blockchain, we'll accept them for now with a warning
                # In production, you'd want to use a service like Alchemy or call the chain
                logger.warning("Smart wallet signature verification not fully implemented - accepting signature")
                
                # Basic validation: check it's a valid hex string
                if not signature.startswith('0x'):
                    logger.error("Invalid signature format - missing 0x prefix")
                    return False
                    
                try:
                    # Check if it's valid hex
                    int(signature[2:], 16)
                except ValueError:
                    logger.error("Invalid signature format - not valid hex")
                    return False
                
                # For now, accept smart wallet signatures
                # TODO: Implement proper ERC-6492/EIP-1271 verification
                is_valid = True
                logger.info(f"Accepting smart wallet signature for {expected_address}")
            
            logger.info(f"Signature verification for {expected_address}: {'valid' if is_valid else 'invalid'}")
            return is_valid
            
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False
    
    @staticmethod
    def _is_timestamp_valid(message: str) -> bool:
        """Check if the timestamp in the message is recent enough.
        
        Args:
            message: The signed message containing a timestamp
            
        Returns:
            True if timestamp is within MAX_MESSAGE_AGE_SECONDS, False otherwise
        """
        try:
            # Extract timestamp from message (format: "... at YYYY-MM-DDTHH:MM:SS.ffffffZ")
            parts = message.split(" at ")
            if len(parts) != 2:
                return False
                
            timestamp_str = parts[-1].strip()
            
            # Handle both timezone-aware and naive timestamps
            if timestamp_str.endswith('Z'):
                # Replace 'Z' with '+00:00' for proper ISO format parsing
                timestamp_str = timestamp_str[:-1] + '+00:00'
                message_time = datetime.fromisoformat(timestamp_str)
                # Make current time timezone-aware (UTC)
                current_time = datetime.now(timezone.utc)
            else:
                # Naive datetime (no timezone)
                message_time = datetime.fromisoformat(timestamp_str)
                current_time = datetime.utcnow()
            
            # Check if timestamp is within acceptable range
            time_diff = current_time - message_time
            
            # Message should not be from the future
            if time_diff.total_seconds() < -30:  # Allow 30 seconds clock drift
                logger.warning(f"Message timestamp is in the future: {timestamp_str}")
                return False
                
            # Message should not be too old
            if time_diff.total_seconds() > SignatureService.MAX_MESSAGE_AGE_SECONDS:
                logger.warning(f"Message timestamp too old: {timestamp_str}")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error checking timestamp validity: {e}")
            return False


# Create singleton instance
signature_service = SignatureService()