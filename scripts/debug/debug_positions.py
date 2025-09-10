import asyncio
from sqlalchemy import select
from app.database.session import get_db, init_db
from app.database.models import Position
from app.core.logger import logger

async def debug():
    address = '0xC2952cc28EDf37B053188D89e6ac888B9855d132'
    
    # Initialize database
    init_db()
    
    # Check database directly
    async for session in get_db():
        # Try different case variations
        addresses_to_check = [
            address,
            address.lower(),
            address.upper()
        ]
        
        for addr in addresses_to_check:
            result = await session.execute(
                select(Position).where(Position.user_id == addr)
            )
            positions = result.scalars().all()
            print(f"Address {addr}: Found {len(positions)} positions in DB")
            
            for pos in positions:
                print(f"  - NFT: {pos.nft_token_id}, Pool: {pos.pool_address}, Status: {pos.status}")
        
        break  # Exit after first iteration
    
    # Also check via positions service
    from app.core.positions_service import positions_service
    print(f"\nChecking via positions_service for {address}")
    positions = await positions_service.get_positions_by_owner(address)
    print(f"Positions service returned {len(positions)} positions")
    
    # Check blockchain
    from app.core.blockchain_service import blockchain_service
    print(f"\nChecking blockchain positions for {address}")
    try:
        # Get NFT token IDs owned by user
        position_manager = await blockchain_service._get_position_manager()
        liquidity_manager = await blockchain_service._get_liquidity_manager()
        
        from web3 import Web3
        owner_address = Web3.to_checksum_address(address)
        
        # Get NFT balance
        balance = await position_manager.functions.balanceOf(owner_address).call()
        print(f"User owns {balance} position NFTs")
        
        if balance > 0:
            # Get token IDs
            for i in range(min(balance, 5)):  # Check first 5
                token_id = await position_manager.functions.tokenOfOwnerByIndex(owner_address, i).call()
                print(f"  - Token ID: {token_id}")
                
                # Get position details
                position = await position_manager.functions.positions(token_id).call()
                print(f"    Liquidity: {position[7]}")
                
    except Exception as e:
        print(f"Blockchain error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug())