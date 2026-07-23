#!/bin/bash
set -e

MONGO_DATA_DIR="/data/db"
REDIS_DATA_DIR="/data/redis"
MONGO_LOG="/var/log/mongodb/mongod.log"
REDIS_LOG="/var/log/redis/redis.log"

mkdir -p "$MONGO_DATA_DIR" "$REDIS_DATA_DIR" /var/log/mongodb /var/log/redis

if ! pgrep -x mongod > /dev/null; then
    if [ -f "$MONGO_DATA_DIR/WiredTiger" ]; then
        echo "Starting MongoDB with auth (existing data)..."
        mongod --dbpath "$MONGO_DATA_DIR" --logpath "$MONGO_LOG" --bind_ip 127.0.0.1 --port 27017 --auth --fork --wiredTigerCacheSizeGB 0.5
    else
        echo "Starting MongoDB without auth (first run)..."
        mongod --dbpath "$MONGO_DATA_DIR" --logpath "$MONGO_LOG" --bind_ip 127.0.0.1 --port 27017 --fork --wiredTigerCacheSizeGB 0.5
        sleep 3
        echo "Creating MongoDB user..."
        mongosh --quiet admin /docker-entrypoint-initdb.d/init-db.js 2>/dev/null || echo "Init script failed or user exists"
        echo "Restarting MongoDB with auth..."
        mongod --dbpath "$MONGO_DATA_DIR" --shutdown 2>/dev/null || true
        sleep 2
        mongod --dbpath "$MONGO_DATA_DIR" --logpath "$MONGO_LOG" --bind_ip 127.0.0.1 --port 27017 --auth --fork --wiredTigerCacheSizeGB 0.5
    fi
    sleep 2
    echo "MongoDB started on port 27017"
fi

if ! pgrep -x redis-server > /dev/null; then
    echo "Starting Redis..."
    redis-server --daemonize yes --dir "$REDIS_DATA_DIR" --logfile "$REDIS_LOG" --bind 127.0.0.1 --port 6379
    echo "Redis started on port 6379"
fi

export PLATFORM_DB_URL="${PLATFORM_DB_URL:-mongodb://appygamciur:app123ygamciur@localhost:27017/app_ygamciur?authSource=admin}"
export PLATFORM_REDIS_URL="${PLATFORM_REDIS_URL:-redis://localhost:6379}"
export PLATFORM_ENCRYPTION_PASSWORD="${PLATFORM_ENCRYPTION_PASSWORD:-enc_ygamciur_a7b3c9d2e5f1}"
export PLATFORM_ENCRYPTION_SALT="${PLATFORM_ENCRYPTION_SALT:-salt_ygamciur_x4k8m2n6p9q1}"
export PLATFORM_MAIL_ENABLED="${PLATFORM_MAIL_ENABLED:-false}"

exec "$@"
