#!/bin/sh
set -e

echo "Waiting for database to be ready..."
until flask init-db > /dev/null 2>&1; do
  echo "  database not ready, retrying in 2s..."
  sleep 2
done
echo "Database ready — tables created."

exec flask --app app run --host=0.0.0.0
