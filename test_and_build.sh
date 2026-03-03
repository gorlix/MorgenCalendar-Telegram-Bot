#!/bin/bash

# REMINDER: Make sure to make this script executable before running it:
# chmod +x test_and_build.sh

echo "======================================="
echo " Morgen Telegram Bot - Local Test Tool "
echo "======================================="

TEMP_ENV_CREATED=0

# 1. Check if the .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  WARNING: .env file not found in the root directory!"
    echo "🛠️  Creating a temporary .env file with dummy variables for the build process..."
    echo "TELEGRAM_TOKEN=dummy_token_for_testing" > .env
    TEMP_ENV_CREATED=1
else
    echo "✅ .env file found."
fi

# 2. Export test environment variable
export APP_VERSION="local-test"
echo "✅ Exported APP_VERSION=${APP_VERSION}"

# 3. Run docker-compose build 
echo "🔨 Building Docker image..."
docker-compose build

# 4. Start the container in detached mode
echo "🚀 Starting containers..."
docker-compose up -d

# 5. Pause for 5 seconds to let the bot initialize
echo "⏳ Waiting 5 seconds for the bot to initialize..."
sleep 5

# 6. Check if the container is running and hasn't crashed
echo "🔍 Checking if the container is running..."
# Filter `docker-compose ps` to see if the state contains 'Up' or checking exit code
if [ "$(docker inspect -f '{{.State.Running}}' morgen_bot 2>/dev/null)" == "true" ]; then
    echo "✅ Container 'morgen_bot' is healthy and running!"
else
    echo "❌ ERROR: Container 'morgen_bot' is NOT running. It may have crashed."
fi

# 7. Fetch and display the last 15 lines of the container logs
echo ""
echo "📜 --- Container Logs (Last 15 lines) ---"
docker-compose logs --tail=15
echo "-----------------------------------------"
echo ""

# 8. Automatically clean up by running docker-compose down
echo "🧹 Cleaning up... stopping and removing containers."
docker-compose down

# Remove the temporary .env if we created it
if [ "$TEMP_ENV_CREATED" -eq 1 ]; then
    echo "🗑️ Removing the temporary .env file..."
    rm .env
fi

echo "✅ Local build and test process completed."
