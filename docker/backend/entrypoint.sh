#!/bin/sh
set -e

# phpdotenv expects a .env file two directories above backend/public/index.php.
# In this container layout that is /var/www/.env.
# Write the required env vars so the unmodified PHP code can load them.
cat > /var/www/.env <<EOF
POSTGRES_CONNECTION_STRING=${POSTGRES_CONNECTION_STRING}
AZURE_EMAIL_CONNECTION_STRING=${AZURE_EMAIL_CONNECTION_STRING}
AZURE_EMAIL_FROM_ADDRESS=${AZURE_EMAIL_FROM_ADDRESS}
EOF

exec supervisord -c /etc/supervisord.conf
