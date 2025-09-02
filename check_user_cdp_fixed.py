import asyncio
from app.database.session import get_db, init_db
from app.database.models import User
from sqlalchemy import select, or_

async def check():
    init_db()
    
    executor = '0xC2952cc28EDf37B053188D89e6ac888B9855d132'
    cdp_wallet = '0x1409f9dfb8C05a31A5fb4b3fFEEA60298bEF30Bb'
    
    async for session in get_db():
        # Try all case variations
        result = await session.execute(
            select(User).where(
                or_(
                    User.user_id == executor.lower(),
                    User.user_id == executor,
                    User.cdp_wallet_address == cdp_wallet.lower(),
                    User.cdp_wallet_address == cdp_wallet
                )
            )
        )
        users = result.scalars().all()
        
        print(f"Found {len(users)} users")
        for user in users:
            print(f"  User ID: {user.user_id}")
            print(f"  CDP Wallet: {user.cdp_wallet_address}")
            print(f"  CDP Wallet Name: {user.cdp_wallet_name}")
        
        # Also directly update the user if found
        if users:
            user = users[0]
            if user.cdp_wallet_address != cdp_wallet.lower():
                print(f"\nUpdating CDP wallet from {user.cdp_wallet_address} to {cdp_wallet.lower()}")
                user.cdp_wallet_address = cdp_wallet.lower()
                await session.commit()
                print("Updated!")
        
        break

if __name__ == "__main__":
    asyncio.run(check())