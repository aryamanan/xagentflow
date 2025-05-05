#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to get task status (kept for potential direct use, but monitor_task gets it now)
get_task_status() {
    local TASK_ID=$1
    STATUS=$(curl -s "http://localhost:8000/tasks/${TASK_ID}" | grep -o '"status":"[^"]*' | cut -d'"' -f4)
    echo $STATUS
}

# Function to get task details (kept for potential direct use)
get_task_details() {
    local TASK_ID=$1
    # Get raw output first
    local RAW_OUTPUT=$(curl -s "http://localhost:8000/tasks/${TASK_ID}")
    
    # Check if output looks like JSON before formatting
    if [[ -n "$RAW_OUTPUT" && ("$RAW_OUTPUT" == \{* || "$RAW_OUTPUT" == \[*) ]]; then
        echo "$RAW_OUTPUT" | (command -v json_pp &> /dev/null && json_pp || cat) # Pretty print if json_pp exists
    else
        echo -e "${RED}Error: get_task_details received non-JSON output for task ${TASK_ID}:${NC}"
        echo "Raw Output: $RAW_OUTPUT"
        # Return non-zero status to indicate potential issue
        return 1 
    fi
}

# Function to approve task
approve_task() {
    local TASK_ID=$1
    echo -e "${YELLOW}Waiting 10 seconds before approving plan...${NC}"
    sleep 10
    echo -e "${GREEN}Approving plan now...${NC}"
    
    APPROVE_RESPONSE=$(curl -s -X POST "http://localhost:8000/tasks/${TASK_ID}/approve" \
      -H "Content-Type: application/json" \
      -d '{"approved": true}')
    
    echo -e "${BLUE}Approval response:${NC}"
    echo "$APPROVE_RESPONSE" | (command -v json_pp &> /dev/null && json_pp || cat) # Pretty print if json_pp exists
}

# Function to monitor task execution
monitor_task() {
    local TASK_ID=$1
    local INITIAL_STATUS=$2
    local CURRENT_STATUS=$INITIAL_STATUS
    local APPROVAL_DONE=false
    local MAX_POLLS=60 # Timeout after 60 polls (5 minutes with 5s sleep)
    local POLL_COUNT=0
    local SLEEP_INTERVAL=5 # Poll every 5 seconds
    local TASK_DETAILS_RAW="" # Store last raw details

    echo -e "${YELLOW}Starting task monitoring from status: ${CURRENT_STATUS}${NC}"

    while [ $POLL_COUNT -lt $MAX_POLLS ]; do
        ((POLL_COUNT++))
        echo -e "${BLUE}Polling attempt ${POLL_COUNT}/${MAX_POLLS}...${NC}"
        # Get task details first for richer logging
        TASK_DETAILS_RAW=$(curl -s "http://localhost:8000/tasks/${TASK_ID}")

        # Check if output is valid JSON
        if [[ -n "$TASK_DETAILS_RAW" && ("$TASK_DETAILS_RAW" == \{* || "$TASK_DETAILS_RAW" == \[*) ]]; then
            CURRENT_STATUS=$(echo "$TASK_DETAILS_RAW" | grep -o '"status":"[^"]*' | cut -d'"' -f4)
            echo "$(date '+%Y-%m-%d %H:%M:%S') - Current status: $CURRENT_STATUS"

            # Log Progress Data if available
            PROGRESS=$(echo "$TASK_DETAILS_RAW" | grep -o '"progress_data":{[^}]*}' || true)
             if [ ! -z "$PROGRESS" ]; then
                 # Try to pretty print progress if json_pp is available
                 if command -v json_pp &> /dev/null; then
                      PROGRESS_FORMATTED=$(echo "$PROGRESS" | json_pp 2>/dev/null || echo "$PROGRESS")
                      echo -e "${BLUE}Progress: ${PROGRESS_FORMATTED}${NC}"
                 else
                      echo -e "${BLUE}Progress: ${PROGRESS}${NC}"
                 fi
             fi

            if [ "$CURRENT_STATUS" = "pending_approval" ] && [ "$APPROVAL_DONE" = false ]; then
                approve_task "$TASK_ID"
                APPROVAL_DONE=true
                # Reset poll count after approval to give execution time
                POLL_COUNT=0 
                echo -e "${YELLOW}Approval sent. Resetting timeout count.${NC}"

            elif [ "$CURRENT_STATUS" = "COMPLETED" ]; then
                echo -e "${GREEN}Task completed successfully${NC}"
                echo -e "${BLUE}Final task details:${NC}"
                echo "$TASK_DETAILS_RAW" | (command -v json_pp &> /dev/null && json_pp || cat) # Pretty print if possible
                break

            elif [ "$CURRENT_STATUS" = "FAILED" ]; then
                echo -e "${RED}Task failed${NC}"
                echo -e "${BLUE}Final task details (showing error):${NC}"
                 echo "$TASK_DETAILS_RAW" | (command -v json_pp &> /dev/null && json_pp || cat) # Pretty print if possible
                break
            fi
        else
             echo -e "${RED}Error: Received non-JSON or empty response for task ${TASK_ID} (Attempt ${POLL_COUNT})${NC}"
             echo "Raw Response:"
             echo "$TASK_DETAILS_RAW"
             # Optional: break or continue based on preference
             # break 
        fi

        sleep $SLEEP_INTERVAL
    done

    if [ $POLL_COUNT -ge $MAX_POLLS ]; then
        echo -e "${RED}Monitoring timed out after ${MAX_POLLS} attempts (${POLL_COUNT} total). Task status might be stuck.${NC}"
        echo -e "${BLUE}Last known details:${NC}"
        echo "$TASK_DETAILS_RAW" | (command -v json_pp &> /dev/null && json_pp || cat) # Pretty print if possible
    fi
}


# Main script logic
echo -e "${BLUE}Initializing debug workflow...${NC}"

if [ "$1" ]; then
    # If task ID is provided, monitor existing task
    TASK_ID=$1
    echo -e "${GREEN}Monitoring existing task: ${TASK_ID}${NC}"
    # Fetch initial status carefully after confirming task exists (or handle error)
    INITIAL_DETAILS_RAW=$(curl -s "http://localhost:8000/tasks/${TASK_ID}")
     if [[ -n "$INITIAL_DETAILS_RAW" && ("$INITIAL_DETAILS_RAW" == \{* || "$INITIAL_DETAILS_RAW" == \[*) ]]; then
        INITIAL_STATUS=$(echo "$INITIAL_DETAILS_RAW" | grep -o '"status":"[^"]*' | cut -d'"' -f4)
        if [ -z "$INITIAL_STATUS" ]; then
             echo -e "${RED}Could not determine initial status for task ${TASK_ID}.${NC}"
             exit 1
        fi
        monitor_task "$TASK_ID" "$INITIAL_STATUS"
     else
        echo -e "${RED}Failed to fetch initial details for task ${TASK_ID}. Is the server running and task valid?${NC}"
        echo "Raw Response: $INITIAL_DETAILS_RAW"
        exit 1
     fi
else
    # Create new task
    echo -e "${GREEN}Creating new AAPL analysis task...${NC}"
    RESPONSE=$(curl -s -X POST http://localhost:8000/tasks/ \
      -H "Content-Type: application/json" \
      -d '{
        "title": "AAPL Technical Analysis",
        "task_type": "RESEARCH",
        "description": "Analyze AAPL stock momentum using technical indicators",
        "input_data": {
          "symbol": "AAPL",
          "timeframe": "1y"
        }
      }')

    TASK_ID=$(echo $RESPONSE | grep -o '"id":"[^"]*' | cut -d'"' -f4)

    if [ -z "$TASK_ID" ]; then
        echo -e "${RED}Failed to create task or extract task ID${NC}"
        echo "API Response:"
        echo "$RESPONSE" | (command -v json_pp &> /dev/null && json_pp || cat) # Pretty print if possible
        exit 1
    fi

    echo -e "${GREEN}Created task with ID: ${TASK_ID}${NC}"
    # Initial status after creation should be PLANNING or PENDING_APPROVAL
    # Let monitor_task fetch the actual initial status
    monitor_task "$TASK_ID" "PLANNING" # Start monitoring, it will fetch the real status
fi 