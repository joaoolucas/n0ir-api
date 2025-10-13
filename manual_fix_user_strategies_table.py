#!/usr/bin/env python3
"""
Manual fix: Create user_strategies table if it doesn't exist.
This should be run ONCE to fix the production database.
"""
import asyncio
import os
from sqlalchemy import create_engine, text, inspect

def fix_user_strategies_table():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return False

    engine = create_engine(db_url)

    with engine.begin() as conn:  # Use begin() for auto-commit
        inspector = inspect(engine)

        # Check if table exists
        if 'user_strategies' in inspector.get_table_names():
            print("✅ user_strategies table already exists!")
            return True

        print("⚠️  user_strategies table does NOT exist. Creating now...")

        # Create enums (idempotent)
        print("Creating strategy_type_enum...")
        conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE strategy_type_enum AS ENUM (
                    'hedged_weth_only',
                    'hedged_cbbtc_only',
                    'hedged_blueprint',
                    'nonhedged_weth_only',
                    'nonhedged_cbbtc_only',
                    'nonhedged_blueprint',
                    'nonhedged_cbltc_cbbtc',
                    'nonhedged_cbada_cbbtc',
                    'nonhedged_cbxrp_cbbtc',
                    'nonhedged_cbdoge_cbbtc',
                    'stable_usdc_eurc',
                    'stable_usdc_brz',
                    'stable_usdc_msusd'
                );
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))

        print("Creating strategy_status_enum...")
        conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE strategy_status_enum AS ENUM (
                    'active',
                    'paused',
                    'closed'
                );
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))

        # Create table
        print("Creating user_strategies table...")
        conn.execute(text("""
            CREATE TABLE user_strategies (
                strategy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id VARCHAR(42) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                strategy_type strategy_type_enum NOT NULL,
                status strategy_status_enum NOT NULL DEFAULT 'active',
                allocated_capital_usd NUMERIC(20, 6) NOT NULL DEFAULT 0,
                deployed_capital_usd NUMERIC(20, 6) NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Create indexes
        print("Creating indexes...")
        conn.execute(text("CREATE INDEX idx_user_strategies_user_id ON user_strategies(user_id);"))
        conn.execute(text("CREATE INDEX idx_user_strategies_status ON user_strategies(status);"))
        conn.execute(text("CREATE INDEX idx_user_strategies_user_status ON user_strategies(user_id, status);"))

        print("✅ Successfully created user_strategies table with all indexes!")
        return True

if __name__ == '__main__':
    success = fix_user_strategies_table()
    if success:
        print("\n🎉 Fix completed successfully!")
    else:
        print("\n❌ Fix failed!")
        exit(1)
