#!/usr/bin/env python3
"""
Check close transaction in more detail.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def check_details():
    """Check transaction details."""
    
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    tx_hash = '0xdc1d362097733e8f59bbb3543673501b37ad35d6afccb261c269b490ab9fd4d2'
    owner_wallet = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'
    cdp_wallet = '0x680214379083fa0d66d1EC030A045beEFB8Ec43f'
    
    print("CHECKING ALL TOKEN TRANSFERS")
    print("="*60)
    
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        
        USDC = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
        AERO = '0x940181a94A35A4569E4529A3CDfB74e38FD98631'
        ERC20_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
        
        print(f"Owner wallet: {owner_wallet}")
        print(f"CDP wallet: {cdp_wallet}")
        print(f"\nAll ERC20 transfers:")
        
        for i, log in enumerate(receipt.logs):
            if len(log.topics) >= 3 and log.topics[0].hex() == ERC20_TRANSFER:
                from_addr = '0x' + log.topics[1].hex()[-40:]
                to_addr = '0x' + log.topics[2].hex()[-40:]
                
                token = "UNKNOWN"
                amount_str = "?"
                
                if log.address.lower() == USDC.lower():
                    amount = int(log.data.hex(), 16) / 1e6
                    token = "USDC"
                    amount_str = f"{amount:.2f}"
                elif log.address.lower() == AERO.lower():
                    amount = int(log.data.hex(), 16) / 1e18
                    token = "AERO"
                    amount_str = f"{amount:.6f}"
                
                # Check if it involves either wallet
                involves_cdp = from_addr.lower() == cdp_wallet.lower() or to_addr.lower() == cdp_wallet.lower()
                involves_owner = from_addr.lower() == owner_wallet.lower() or to_addr.lower() == owner_wallet.lower()
                
                if involves_cdp or involves_owner:
                    wallet_tag = ""
                    if from_addr.lower() == cdp_wallet.lower():
                        wallet_tag = " [FROM CDP]"
                    elif to_addr.lower() == cdp_wallet.lower():
                        wallet_tag = " [TO CDP]"
                    elif from_addr.lower() == owner_wallet.lower():
                        wallet_tag = " [FROM OWNER]"
                    elif to_addr.lower() == owner_wallet.lower():
                        wallet_tag = " [TO OWNER]"
                    
                    print(f"  Log #{i}: {token} {amount_str}")
                    print(f"    From: {from_addr}{wallet_tag if from_addr.lower() in [cdp_wallet.lower(), owner_wallet.lower()] else ''}")
                    print(f"    To: {to_addr}{wallet_tag if to_addr.lower() in [cdp_wallet.lower(), owner_wallet.lower()] else ''}")
        
        # Check for DecreaseLiquidity or Collect events
        print(f"\n🔍 Position Management Events:")
        DECREASE_LIQUIDITY = '0x26f6a048ee9138f2c0ce266f322cb99228e8d619ae2bff30c67f8dcf9d2377b4'
        COLLECT = '0x40d0efd1a53d60ecbf40971b9daf7dc90178c3aadc7aab1765632738fa8b8f01'
        
        for i, log in enumerate(receipt.logs):
            if log.topics and log.topics[0].hex() in [DECREASE_LIQUIDITY, COLLECT]:
                event_name = "DecreaseLiquidity" if log.topics[0].hex() == DECREASE_LIQUIDITY else "Collect"
                print(f"  Log #{i}: {event_name} from {log.address[:10]}...")
                if len(log.topics) > 1:
                    try:
                        token_id = int(log.topics[1].hex(), 16)
                        print(f"    Position ID: {token_id}")
                    except:
                        pass
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_details()
