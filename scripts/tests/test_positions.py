import asyncio
from app.core.positions_service import positions_service

async def test():
    address = '0xC2952cc28EDf37B053188D89e6ac888B9855d132'
    print(f"Testing positions for: {address}")
    
    positions = await positions_service.get_positions_by_owner(address)
    print(f'Found {len(positions)} positions')
    
    for pos in positions:
        print(f'  - Token ID: {pos.nft_token_id}')
        print(f'    Pool: {pos.pool_address}')
        print(f'    Value: {pos.current_value_usd}')
        print(f'    Status: {pos.status}')
    
    # Also test what pools would be excluded
    exclude_addresses = list(set([pos.pool_address for pos in positions if pos.pool_address]))
    print(f'\nPools to exclude from screening: {exclude_addresses}')
    
    # Check if WETH/USDC pool is in the list
    weth_usdc_pool = '0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59'
    if weth_usdc_pool in [addr.lower() for addr in exclude_addresses]:
        print(f"✓ WETH/USDC pool IS in exclude list")
    else:
        print(f"✗ WETH/USDC pool NOT in exclude list")

if __name__ == "__main__":
    asyncio.run(test())