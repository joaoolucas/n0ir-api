import requests
import json
import time
from typing import List, Dict, Any, Tuple
from datetime import datetime
from enum import Enum
from collections import defaultdict

class TransactionType(Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
    STAKING = "STAKING"
    UNKNOWN = "UNKNOWN"

class SimpleWalletAnalyzer:
    def __init__(self, api_key: str, wallet_address: str):
        self.api_key = api_key
        self.wallet_address = wallet_address.lower()
        self.base_url = "https://api.cdp.coinbase.com/platform"
        
        # Known addresses (lowercase for comparison)
        self.DEPOSIT_CONTRACT = "0xdbe4e3bcb15b221324b776db6f0cbff24918ea51".lower()
        
        # Known token addresses on Base
        self.USDC_ADDRESS = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913".lower()
        
        # Position manager contracts (for staking detection)
        self.POSITION_MANAGERS = [
            "0x827922686190790b37229fd06084350e74485b72".lower(),  # Main position manager
            "0xf33a96b5932d9e9b9a0eda447abd8c9d48d2e0c8".lower(),  # Another position manager
        ]
    
    def fetch_transactions(self, limit: int = 50, page: str = None) -> Dict[str, Any]:
        """Fetch transactions for the wallet with pagination support"""
        endpoint = f"/v1/networks/base-mainnet/addresses/{self.wallet_address}/transactions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        params = {"limit": min(limit, 100)}  # CDP allows up to 100
        if page:
            params["page"] = page
        
        try:
            response = requests.get(
                f"{self.base_url}{endpoint}",
                headers=headers,
                params=params
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                print(f"  Rate limited, waiting before retry...")
                time.sleep(5)  # Wait 5 seconds on rate limit
                return {}
            else:
                print(f"API Error ({response.status_code})")
                return {}
                
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return {}
    
    def fetch_all_transactions(self) -> List[Dict]:
        """Fetch all transactions using pagination with retry logic"""
        all_transactions = []
        page = None
        page_count = 0
        max_retries = 3
        base_delay = 2.0  # Base delay for exponential backoff
        batch_size = 20  # Smaller batch size to avoid rate limits
        
        while True:
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                print(f"📡 Fetching page {page_count + 1}...")
                data = self.fetch_transactions(limit=batch_size, page=page)  # Use smaller batch size
                
                if not data:
                    # If we got rate limited or error, retry with exponential backoff
                    retry_count += 1
                    if retry_count < max_retries:
                        delay = base_delay * (2 ** retry_count)  # Exponential backoff
                        print(f"  Retrying in {delay} seconds... (attempt {retry_count + 1}/{max_retries})")
                        time.sleep(delay)
                    continue
                
                if "data" not in data:
                    break
                    
                transactions = data.get("data", [])
                all_transactions.extend(transactions)
                page_count += 1
                success = True
                
                # Check if there are more pages
                has_more = data.get("has_more", False)
                next_page = data.get("next_page")
                
                print(f"  Found {len(transactions)} transactions (total so far: {len(all_transactions)})")
                
                if not has_more or not next_page:
                    return all_transactions
                    
                page = next_page
                
                # Add small delay between successful requests to avoid rate limiting
                time.sleep(0.5)  # Reduced delay for smaller batches
            
            if not success:
                print(f"  Failed to fetch page after {max_retries} retries. Returning what we have.")
                break
        
        return all_transactions
    
    def decode_erc20_input(self, input_data: str) -> Dict[str, Any]:
        """Decode ERC20 method calls from input data"""
        if not input_data or len(input_data) < 10:
            return None
        
        method_sig = input_data[:10]
        
        # transfer(address,uint256)
        if method_sig == "0xa9059cbb" and len(input_data) >= 138:
            return {
                "method": "transfer",
                "to": "0x" + input_data[34:74],
                "amount": int(input_data[74:138], 16) if input_data[74:138] else 0
            }
        
        # transferFrom(address,address,uint256)
        elif method_sig == "0x23b872dd" and len(input_data) >= 202:
            return {
                "method": "transferFrom",
                "from": "0x" + input_data[34:74],
                "to": "0x" + input_data[98:138],
                "amount": int(input_data[138:202], 16) if input_data[138:202] else 0
            }
        
        return None
    
    def analyze_transaction(self, tx_data: Dict) -> Tuple[TransactionType, Dict[str, Any]]:
        """Analyze transaction to identify deposits, withdrawals, or staking"""
        content = tx_data.get("content", {})
        traces = content.get("flattened_traces", [])
        
        if not traces:
            return TransactionType.UNKNOWN, {}
        
        # Basic transaction info
        details = {
            "tx_hash": traces[0].get("transaction_hash", ""),
            "block": traces[0].get("block_number", ""),
            "timestamp": content.get("block_timestamp", ""),
            "amount": 0,
            "description": ""
        }
        
        # Track what we find in this transaction
        found_deposit = False
        found_withdrawal = False
        found_staking = False
        deposit_amount = 0
        withdrawal_amount = 0
        
        # Check ALL traces for patterns
        for trace in traces:
            from_addr = trace.get("from", "").lower()
            to_addr = trace.get("to", "").lower()
            input_data = trace.get("input", "")
            
            # Decode ERC20 operations
            decoded = self.decode_erc20_input(input_data)
            
            # Check for USDC transfers
            if to_addr == self.USDC_ADDRESS and decoded:
                # For transfer method, check who's calling and where it's going
                if decoded.get("method") == "transfer":
                    recipient = decoded.get("to", "").lower()
                    
                    # DEPOSIT: Deposit contract sending USDC to wallet
                    if from_addr == self.DEPOSIT_CONTRACT and recipient == self.wallet_address:
                        found_deposit = True
                        deposit_amount += decoded.get("amount", 0)
                    
                    # WITHDRAWAL: Wallet sending USDC to deposit contract
                    if from_addr == self.wallet_address and recipient == self.DEPOSIT_CONTRACT:
                        found_withdrawal = True
                        withdrawal_amount += decoded.get("amount", 0)
                
                # For transferFrom method
                elif decoded.get("method") == "transferFrom":
                    transfer_from = decoded.get("from", "").lower()
                    transfer_to = decoded.get("to", "").lower()
                    
                    # DEPOSIT: USDC from deposit contract to wallet
                    if transfer_from == self.DEPOSIT_CONTRACT and transfer_to == self.wallet_address:
                        found_deposit = True
                        deposit_amount += decoded.get("amount", 0)
                    
                    # WITHDRAWAL: USDC from wallet to deposit contract
                    if transfer_from == self.wallet_address and transfer_to == self.DEPOSIT_CONTRACT:
                        found_withdrawal = True
                        withdrawal_amount += decoded.get("amount", 0)
            
            # STAKING: Check ALL interactions with position managers
            if from_addr == self.wallet_address:
                # Check if sending to any position manager
                for pm in self.POSITION_MANAGERS:
                    if to_addr == pm:
                        found_staking = True
                        break
        
        # Return based on what we found (prioritize deposits/withdrawals over staking)
        if found_deposit:
            details["amount"] = deposit_amount
            details["description"] = "USDC deposit from contract"
            return TransactionType.DEPOSIT, details
        
        if found_withdrawal:
            details["amount"] = withdrawal_amount
            details["description"] = "USDC withdrawal to contract"
            return TransactionType.WITHDRAW, details
            
        if found_staking:
            details["description"] = "Interaction with position manager (potential staking)"
            return TransactionType.STAKING, details
        
        return TransactionType.UNKNOWN, details
    
    def format_amount(self, amount: int, decimals: int = 6) -> str:
        """Format token amount with proper decimals"""
        if amount == 0:
            return "0"
        return f"{amount / (10 ** decimals):,.2f}"
    
    def run_analysis(self):
        """Main analysis function"""
        print(f"\n🔍 Simple Wallet Analysis")
        print(f"Wallet: {self.wallet_address}")
        print("=" * 80)
        
        # Fetch all transactions with pagination
        print("📡 Fetching all transactions with pagination...")
        transactions = self.fetch_all_transactions()
        
        if not transactions:
            print("❌ No transaction data found")
            return
        
        print(f"✅ Found {len(transactions)} total transactions\n")
        
        # Categorize all transactions
        categorized = defaultdict(list)
        
        for tx in transactions:
            tx_type, details = self.analyze_transaction(tx)
            if details:  # Only add if we have details
                categorized[tx_type].append(details)
        
        # Display results
        print("📊 TRANSACTION BREAKDOWN")
        print("-" * 60)
        
        # Deposits
        deposits = categorized[TransactionType.DEPOSIT]
        if deposits:
            print(f"\n💰 DEPOSITS ({len(deposits)} total)")
            print("-" * 40)
            total_deposited = 0
            for tx in deposits:
                amount = tx['amount']
                total_deposited += amount
                print(f"  {tx['timestamp'][:19]} - {self.format_amount(amount)} USDC")
                print(f"    Hash: {tx['tx_hash'][:10]}...{tx['tx_hash'][-6:]}")
            print(f"  Total Deposited: {self.format_amount(total_deposited)} USDC")
        
        # Withdrawals
        withdrawals = categorized[TransactionType.WITHDRAW]
        if withdrawals:
            print(f"\n💸 WITHDRAWALS ({len(withdrawals)} total)")
            print("-" * 40)
            total_withdrawn = 0
            for tx in withdrawals:
                amount = tx['amount']
                total_withdrawn += amount
                print(f"  {tx['timestamp'][:19]} - {self.format_amount(amount)} USDC")
                print(f"    Hash: {tx['tx_hash'][:10]}...{tx['tx_hash'][-6:]}")
            print(f"  Total Withdrawn: {self.format_amount(total_withdrawn)} USDC")
        
        # Staking
        stakings = categorized[TransactionType.STAKING]
        if stakings:
            print(f"\n🎯 STAKING ({len(stakings)} total)")
            print("-" * 40)
            for tx in stakings:
                print(f"  {tx['timestamp'][:19]} - NFT Staked")
                print(f"    Hash: {tx['tx_hash'][:10]}...{tx['tx_hash'][-6:]}")
        
        # Summary
        print("\n" + "=" * 80)
        print("📈 SUMMARY")
        print("=" * 80)
        
        total_deposits = sum(tx['amount'] for tx in deposits)
        total_withdrawals = sum(tx['amount'] for tx in withdrawals)
        net_flow = total_deposits - total_withdrawals
        
        print(f"Total Deposits:    {self.format_amount(total_deposits)} USDC")
        print(f"Total Withdrawals: {self.format_amount(total_withdrawals)} USDC")
        print(f"Net Flow:          {self.format_amount(net_flow)} USDC")
        print(f"Staking Events:    {len(stakings)}")
        
        # Uncategorized
        unknown = len(categorized[TransactionType.UNKNOWN])
        if unknown > 0:
            print(f"\n⚠️  {unknown} transactions were not categorized")
        
        # Save results
        output = {
            "wallet": self.wallet_address,
            "analysis_time": datetime.now().isoformat(),
            "summary": {
                "total_transactions": len(transactions),
                "deposits": len(deposits),
                "withdrawals": len(withdrawals),
                "stakings": len(stakings),
                "unknown": unknown,
                "total_deposited_usdc": total_deposits,
                "total_withdrawn_usdc": total_withdrawals,
                "net_flow_usdc": net_flow
            },
            "transactions": {
                "deposits": deposits,
                "withdrawals": withdrawals,
                "stakings": stakings
            }
        }
        
        filename = f"simple_analysis_{self.wallet_address[-6:]}.json"
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"\n💾 Analysis saved to {filename}")

def main():
    API_KEY = "PgSu2QFE67b4koEsqfe6yp831l7KCKgH"
    WALLET_ADDRESS = "0x7b3106F56447c9C313C19f519b290Ff4E293D573"
    
    analyzer = SimpleWalletAnalyzer(API_KEY, WALLET_ADDRESS)
    analyzer.run_analysis()

if __name__ == "__main__":
    main()