#!/usr/bin/env python3
"""
Analyze the position close transaction.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def analyze_close():
    """Analyze the close transaction."""
    
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    tx_hash = '0xdc1d362097733e8f59bbb3543673501b37ad35d6afccb261c269b490ab9fd4d2'
    cdp_wallet = '0x680214379083fa0d66d1EC030A045beEFB8Ec43f'
    
    print("ANALYZING POSITION CLOSE TRANSACTION")
    print("="*60)
    print(f"TX Hash: {tx_hash}")
    
    try:
        tx = w3.eth.get_transaction(tx_hash)
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        
        print(f"\nTransaction:")
        print(f"  From: {tx['from']}")
        print(f"  To: {tx['to']}")
        print(f"  Method: {tx.input[:10] if len(tx.input) >= 10 else 'N/A'}")
        
        # Check for NFT burns (Transfer to 0x0)
        ERC721_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
        NFT_POSITION_MANAGER = '0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1'
        
        print(f"\n🎨 NFT Events:")
        nft_found = False
        for i, log in enumerate(receipt.logs):
            if log.address.lower() == NFT_POSITION_MANAGER.lower():
                if len(log.topics) > 0 and log.topics[0].hex() == ERC721_TRANSFER:
                    if len(log.topics) >= 4:
                        from_addr = '0x' + log.topics[1].hex()[-40:]
                        to_addr = '0x' + log.topics[2].hex()[-40:]
                        token_id = int(log.topics[3].hex(), 16)
                        
                        print(f"  Log #{i}: NFT Transfer")
                        print(f"    From: {from_addr}")
                        print(f"    To: {to_addr}")
                        print(f"    Token ID: {token_id}")
                        
                        if to_addr.lower() == '0x' + '0' * 40:
                            print(f"    ✅ NFT BURN DETECTED!")
                            nft_found = True
        
        if not nft_found:
            print(f"  ❌ No NFT burn found")
        
        # Check for Liquidity Manager events
        LIQUIDITY_MANAGER = '0xBeb749B7F1149b75E79C1d818Ad3587060A3805D'.lower()
        
        print(f"\n📝 Liquidity Manager Events:")
        for i, log in enumerate(receipt.logs):
            if log.address.lower() == LIQUIDITY_MANAGER:
                if log.topics:
                    event_sig = log.topics[0].hex() if hasattr(log.topics[0], 'hex') else str(log.topics[0])
                    print(f"  Log #{i}: Event signature: {event_sig[:10]}...")
                    
                    # Check for PositionClosed event (need to find the actual signature)
                    # The PositionCreated was 0x8d53117d..., so PositionClosed might be different
        
        # Check USDC and AERO flows
        USDC = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
        AERO = '0x940181a94A35A4569E4529A3CDfB74e38FD98631'
        ERC20_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
        
        print(f"\n💰 Token Flows:")
        usdc_in = 0
        usdc_out = 0
        aero_in = 0
        aero_out = 0
        
        for log in receipt.logs:
            if len(log.topics) >= 3 and log.topics[0].hex() == ERC20_TRANSFER:
                from_addr = '0x' + log.topics[1].hex()[-40:]
                to_addr = '0x' + log.topics[2].hex()[-40:]
                
                if log.address.lower() == USDC.lower():
                    amount = int(log.data.hex(), 16) / 1e6
                    if to_addr.lower() == cdp_wallet.lower():
                        usdc_in += amount
                        print(f"  USDC IN: {amount:.2f} from {from_addr[:10]}...")
                    elif from_addr.lower() == cdp_wallet.lower():
                        usdc_out += amount
                        print(f"  USDC OUT: {amount:.2f} to {to_addr[:10]}...")
                
                elif log.address.lower() == AERO.lower():
                    amount = int(log.data.hex(), 16) / 1e18
                    if to_addr.lower() == cdp_wallet.lower():
                        aero_in += amount
                        print(f"  AERO IN: {amount:.6f} from {from_addr[:10]}...")
                    elif from_addr.lower() == cdp_wallet.lower():
                        aero_out += amount
                        print(f"  AERO OUT: {amount:.6f} to {to_addr[:10]}...")
        
        print(f"\n📊 Summary:")
        print(f"  USDC IN: {usdc_in:.2f}")
        print(f"  USDC OUT: {usdc_out:.2f}")
        print(f"  AERO IN: {aero_in:.6f}")
        print(f"  AERO OUT: {aero_out:.6f}")
        print(f"  Has NFT burn: {'Yes' if nft_found else 'No'}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    analyze_close()
