import asyncio
from app.database.session import get_db, init_db
from app.database.models import User
from sqlalchemy import select

async def check():
    init_db()
    
    executor = '0xC2952cc28EDf37B053188D89e6ac888B9855d132'
    
    async for session in get_db():
        # Check with lowercase
        result = await session.execute(
            select(User).where(User.user_id == executor.lower())
        )
        user = result.scalar_one_or_none()
        
        if user:
            print(f"Found user: {user.user_id}")
            print(f"CDP Wallet: {user.cdp_wallet_address}")
            print(f"CDP Wallet Name: {user.cdp_wallet_name}")
        else:
            print(f"No user found for {executor.lower()}")
        
        break

if __name__ == "__main__":
    asyncio.run(check())