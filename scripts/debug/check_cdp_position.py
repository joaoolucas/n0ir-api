import asyncio
from app.core.positions_service import positions_service

async def check():
    # Check CDP wallet positions
    cdp_wallet = '0x1409f9dfb8C05a31A5fb4b3fFEEA60298bEF30Bb'
    executor = '0xC2952cc28EDf37B053188D89e6ac888B9855d132'
    
    print(f"Checking CDP wallet: {cdp_wallet}")
    cdp_positions = await positions_service.get_positions_by_owner(cdp_wallet)
    print(f"Found {len(cdp_positions)} positions")
    
    for pos in cdp_positions:
        print(f"  - Token ID: {pos.nft_token_id}")
        print(f"    Pool: {pos.pool_address}")
        print(f"    Value: ${pos.current_value_usd}")
        print(f"    Status: {pos.status}")
    
    print(f"\nChecking executor: {executor}")
    exec_positions = await positions_service.get_positions_by_owner(executor)
    print(f"Found {len(exec_positions)} positions")

if __name__ == "__main__":
    asyncio.run(check())