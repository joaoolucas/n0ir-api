"""
API endpoints for managing per-strategy capital allocation.

Note: Position event reporting has been removed. Capital tracking is now
handled automatically via sync_blockchain_data() which fetches position
state directly from the blockchain.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/users")

# Position events endpoint removed - capital tracking now handled by blockchain sync
# See sync_blockchain_data() in user_service.py for automatic position tracking
