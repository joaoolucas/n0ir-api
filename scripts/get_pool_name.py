#!/usr/bin/env python3
"""Get pool name for a specific address."""

import asyncio
import httpx
import json

async def get_pool_name():
    """Fetch pool name from pools service."""
    pool_address = "0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59"

    async with httpx.AsyncClient() as client:
        try:
            # Call the local API to get pool info
            response = await client.get(f"http://localhost:8000/api/v1/pools/{pool_address}")
            if response.status_code == 200:
                data = response.json()
                print(f"Pool: {pool_address}")
                print(f"Symbol: {data.get('symbol')}")
                print(f"Token0: {data.get('token0_symbol')}")
                print(f"Token1: {data.get('token1_symbol')}")

                # Extract pool name from symbol
                symbol = data.get('symbol', '')
                if symbol and '-' in symbol:
                    pool_name = symbol.rsplit('-', 1)[0]
                else:
                    pool_name = symbol
                print(f"Pool Name: {pool_name}")

                return pool_name
            else:
                print(f"Failed to get pool info: {response.status_code}")
        except Exception as e:
            print(f"Error: {e}")
            # Try with base API URL
            try:
                response = await client.get(f"https://n0ir-api-staging.up.railway.app/api/v1/pools/{pool_address}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"Pool: {pool_address}")
                    print(f"Symbol: {data.get('symbol')}")

                    # Extract pool name from symbol
                    symbol = data.get('symbol', '')
                    if symbol and '-' in symbol:
                        pool_name = symbol.rsplit('-', 1)[0]
                    else:
                        pool_name = symbol
                    print(f"Pool Name: {pool_name}")

                    return pool_name
            except:
                pass

    return None

if __name__ == "__main__":
    asyncio.run(get_pool_name())