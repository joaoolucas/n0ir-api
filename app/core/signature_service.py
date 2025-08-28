"""Service for verifying Ethereum signatures using EIP-191 standard."""
from datetime import datetime, timedelta
from typing import Optional
from eth_account import Account
from eth_account.messages import encode_defunct
from loguru import logger


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
        """Verify an Ethereum signature using EIP-191.
        
        Args:
            message: The original message that was signed
            signature: The signature to verify (hex string)
            expected_address: The expected signer's address
            
        Returns:
            True if signature is valid and from expected address, False otherwise
        """
        try:
            # Normalize the expected address to lowercase
            expected_address = expected_address.lower()
            
            # Create EIP-191 encoded message
            encoded_message = encode_defunct(text=message)
            
            # Recover the address from the signature
            recovered_address = Account.recover_message(encoded_message, signature=signature)
            
            # Compare addresses (both lowercase)
            is_valid = recovered_address.lower() == expected_address
            
            if is_valid:
                # Check timestamp to prevent replay attacks
                if not SignatureService._is_timestamp_valid(message):
                    logger.warning(f"Signature timestamp too old for address {expected_address}")
                    return False
                    
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
            # Extract timestamp from message (format: "... at YYYY-MM-DDTHH:MM:SS.ffffff")
            parts = message.split(" at ")
            if len(parts) != 2:
                return False
                
            timestamp_str = parts[-1].strip()
            message_time = datetime.fromisoformat(timestamp_str)
            
            # Check if timestamp is within acceptable range
            current_time = datetime.utcnow()
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