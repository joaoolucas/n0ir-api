#!/usr/bin/env python3
"""Manually sync transactions for a user's CDP wallet."""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.services.wallet_transaction_service import WalletTransactionService
from app.core.config import settings

DATABASE_URL = "postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def sync_transactions():
    """Sync transactions for the user."""
    # Create async engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            # Create wallet transaction service
            wallet_service = WalletTransactionService(session)

            # User details
            user_id = "0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764"
            cdp_wallet = "0x680214379083fa0d66d1EC030A045beEFB8Ec43f"

            print(f"Syncing transactions for user {user_id}")
            print(f"CDP Wallet: {cdp_wallet}")
            print("-" * 50)

            # Fetch and sync transactions
            result = await wallet_service.fetch_and_sync_transactions(
                user_id=user_id,
                cdp_wallet_address=cdp_wallet,
                limit=100
            )

            print(f"\nSync Result:")
            print(f"  Total: {result.get('total', 0)}")
            print(f"  Deposits: {result.get('deposits', 0)}")
            print(f"  Withdrawals: {result.get('withdrawals', 0)}")
            print(f"  Stakes: {result.get('stakes', 0)}")
            print(f"  Positions Opened: {result.get('positions_opened', 0)}")
            print(f"  Positions Closed: {result.get('positions_closed', 0)}")
            print(f"  Unknown: {result.get('unknown', 0)}")

            if result.get('error'):
                print(f"  Error: {result['error']}")

            # Check specifically for the stake transaction
            from sqlalchemy import select
            from app.database.models import Transaction

            stmt = select(Transaction).where(
                Transaction.tx_hash == "0xc033aabc8da21b78e94cc24b4304e6400ebc50ce47c32dbcb20d1bf858bcbf62"
            )
            tx = await session.execute(stmt)
            stake_tx = tx.scalar_one_or_none()

            if stake_tx:
                print(f"\n✅ Found stake transaction!")
                print(f"  Type: {stake_tx.tx_type}")
                print(f"  Hash: {stake_tx.tx_hash}")
            else:
                print(f"\n⚠️ Stake transaction not found in sync")

                # List all transactions
                stmt = select(Transaction).where(
                    Transaction.user_id == user_id
                ).order_by(Transaction.block_timestamp.desc()).limit(10)
                result = await session.execute(stmt)
                txs = result.scalars().all()

                print(f"\nRecent transactions for user:")
                for tx in txs:
                    print(f"  - {tx.tx_hash[:20]}... Type: {tx.tx_type}")

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(sync_transactions())