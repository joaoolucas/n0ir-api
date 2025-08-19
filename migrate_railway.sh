#!/bin/bash

# Railway Database Migration Script
# IMPORTANT: Backup your database before running!

DATABASE_URL="postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

echo "🚀 n0ir Database Migration Tool"
echo "================================"
echo "Target: Railway Production Database"
echo ""

# Function to run SQL command
run_sql() {
    psql "$DATABASE_URL" -c "$1"
}

# Function to check migration status
check_status() {
    echo "📊 Checking current schema status..."
    echo ""
    
    echo "1. Users table columns:"
    psql "$DATABASE_URL" -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'users' ORDER BY ordinal_position;" 2>/dev/null
    
    echo ""
    echo "2. Protocol_fees table exists:"
    psql "$DATABASE_URL" -c "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'protocol_fees');" 2>/dev/null
    
    echo ""
    echo "3. Positions protocol fee columns:"
    psql "$DATABASE_URL" -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'positions' AND column_name LIKE 'protocol%';" 2>/dev/null
}

# Function to backup schema
backup_schema() {
    echo "💾 Creating schema backup..."
    BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).sql"
    pg_dump "$DATABASE_URL" --schema-only > "$BACKUP_FILE"
    echo "✅ Schema backed up to: $BACKUP_FILE"
}

# Function to run migration
run_migration() {
    echo "🔄 Running migration..."
    echo ""
    
    # Execute the migration SQL file
    psql "$DATABASE_URL" < migrations/simplify_schema.sql
    
    if [ $? -eq 0 ]; then
        echo "✅ Migration completed successfully!"
    else
        echo "❌ Migration failed! Check errors above."
        exit 1
    fi
}

# Main menu
case "$1" in
    status)
        check_status
        ;;
    backup)
        backup_schema
        ;;
    migrate)
        echo "⚠️  WARNING: This will modify your production database!"
        echo "Have you backed up your database? (yes/no)"
        read -r response
        if [ "$response" = "yes" ]; then
            run_migration
            echo ""
            echo "📊 New schema status:"
            check_status
        else
            echo "❌ Migration cancelled. Please backup first!"
            echo "Run: ./migrate_railway.sh backup"
        fi
        ;;
    test)
        echo "🧪 Testing connection..."
        psql "$DATABASE_URL" -c "SELECT version();" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "✅ Connection successful!"
        else
            echo "❌ Connection failed!"
        fi
        ;;
    *)
        echo "Usage: ./migrate_railway.sh [command]"
        echo ""
        echo "Commands:"
        echo "  status  - Check current schema status"
        echo "  backup  - Create schema backup"
        echo "  migrate - Run the migration (asks for confirmation)"
        echo "  test    - Test database connection"
        echo ""
        echo "Example:"
        echo "  ./migrate_railway.sh status"
        echo "  ./migrate_railway.sh backup"
        echo "  ./migrate_railway.sh migrate"
        ;;
esac