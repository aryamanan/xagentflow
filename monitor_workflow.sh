#!/bin/bash

# Function to monitor task status and tool usage
monitor_task() {
    local task_id=$1
    local max_attempts=${2:-10}
    local sleep_interval=${3:-5}
    
    echo "Monitoring task: $task_id"
    echo "------------------------"
    
    for ((i=1; i<=max_attempts; i++)); do
        echo "Check $i of $max_attempts"
        
        # Get task status
        response=$(curl -s "http://localhost:8000/tasks/$task_id")
        
        # Extract and display status
        status=$(echo $response | jq -r '.status')
        current_step=$(echo $response | jq -r '.current_step')
        
        echo "Status: $status"
        echo "Current Step: $current_step"
        
        # Display tool usage if available
        tool_usage=$(echo $response | jq -r '.tool_usage[]? | "Tool: \(.tool_name) Status: \(.status)"')
        if [ ! -z "$tool_usage" ]; then
            echo "Tool Usage:"
            echo "$tool_usage"
        fi
        
        # Display any validation errors
        validation_errors=$(echo $response | jq -r '.validation_errors[]?')
        if [ ! -z "$validation_errors" ]; then
            echo "Validation Errors:"
            echo "$validation_errors"
        fi
        
        # Check if task is complete or failed
        if [[ "$status" == "COMPLETED" || "$status" == "FAILED" ]]; then
            echo "Task finished with status: $status"
            
            # Display final results or error
            if [[ "$status" == "COMPLETED" ]]; then
                echo "Results:"
                echo $response | jq '.results'
            else
                echo "Error:"
                echo $response | jq '.error'
            fi
            break
        fi
        
        sleep $sleep_interval
    done
}

# Check command line arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 <task_id> [max_attempts] [sleep_interval]"
    exit 1
fi

# Start monitoring
monitor_task "$@" 