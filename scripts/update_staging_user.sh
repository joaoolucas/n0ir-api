#!/bin/bash

# Update the test user with CDP wallet address
curl -X 'POST' \
  'https://n0ir-api-staging.up.railway.app/api/v1/admin/execute-sql' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer 5RRJ8kHdu5M6HL91hY5bUI0abWtbANwjqVKtmjq4BMk=' \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "UPDATE users SET cdp_wallet_address = '\''0x7b3106f56447c9c313c19f519b290ff4e293d573'\'' WHERE user_id = '\''0xdbe4e3bcb15b221324b776db6f0cbff24918ea51'\''"
  }'

echo ""
echo "User updated with CDP wallet address"