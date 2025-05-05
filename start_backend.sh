#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting backend setup...${NC}"

# Check for process on port 8000
echo -e "${BLUE}Checking for processes on port 8000...${NC}"
PID=$(lsof -i:8000 -t)
if [ ! -z "$PID" ]; then
    echo -e "${YELLOW}Killing process on port 8000 (PID: $PID)${NC}"
    kill -9 $PID
    sleep 1
fi

# Check and activate virtual environment
if [ -d "venv" ]; then
    echo -e "${GREEN}Activating virtual environment...${NC}"
    source venv/bin/activate
else
    echo -e "${RED}Virtual environment not found. Please create it first.${NC}"
    exit 1
fi

# Get the absolute path of the current directory
CURRENT_DIR=$(pwd)

# Start the server in a new terminal window
echo -e "${BLUE}Starting backend server in new terminal...${NC}"
osascript -e "tell application \"Terminal\"
    do script \"cd ${CURRENT_DIR} && source venv/bin/activate && python3 -m uvicorn app.main:app --port 8000 --reload\"
end tell"

# Wait for server to start
echo -e "${YELLOW}Waiting for server to start...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null; then
        echo -e "${GREEN}Backend server started successfully!${NC}"
        exit 0
    fi
    sleep 1
done

echo -e "${RED}Failed to start backend server.${NC}"
exit 1 