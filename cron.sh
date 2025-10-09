#!/bin/bash
# Cron job runner for APR snapshots
# This script runs hourly to capture APR snapshots

while true; do
    echo "$(date): Starting APR snapshot capture..."
    python scripts/capture_apr_snapshots.py
    echo "$(date): APR snapshot capture completed. Sleeping for 1 hour..."
    sleep 3600  # Sleep for 1 hour
done
