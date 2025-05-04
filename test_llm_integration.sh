#!/bin/bash

# Test 1: Research Task with Technical Analysis
echo "Testing LLM tool integration for technical analysis..."
TASK_1_RESPONSE=$(curl -s -X POST http://localhost:8000/tasks/ \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "research",
    "request": "Analyze AAPL using RSI, MACD, and Bollinger Bands. Focus on recent price action and potential entry points.",
    "input_data": {
      "symbol": "AAPL",
      "timeframe": "3mo",
      "indicators": ["RSI", "MACD", "BB"],
      "focus": "technical_analysis"
    }
  }')
TASK_1_ID=$(echo $TASK_1_RESPONSE | jq -r '.task_id')
echo "Task 1 ID: $TASK_1_ID"

# Wait for initial processing
sleep 5

# Test 2: Check if LLM uses knowledge base for interpretation
echo "Testing knowledge base integration..."
curl -s -X POST http://localhost:8000/tasks/ \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "research",
    "request": "Explain the significance of RSI divergence and MACD crossovers in technical analysis",
    "input_data": {
      "context": "technical_analysis",
      "focus": "indicator_interpretation"
    }
  }'

# Test 3: Complex workflow with multiple tool usage
echo "Testing multi-tool workflow..."
TASK_3_RESPONSE=$(curl -s -X POST http://localhost:8000/tasks/ \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "strategy",
    "request": "Create a mean reversion strategy for AAPL using Bollinger Bands and RSI",
    "input_data": {
      "symbol": "AAPL",
      "strategy_type": "mean_reversion",
      "indicators": ["BB", "RSI"],
      "timeframe": "1y",
      "risk_profile": "moderate"
    }
  }')
TASK_3_ID=$(echo $TASK_3_RESPONSE | jq -r '.task_id')
echo "Task 3 ID: $TASK_3_ID"

# Monitor task progress and tool usage
echo "Monitoring task execution and tool usage..."
for task_id in "$TASK_1_ID" "$TASK_3_ID"; do
  for i in {1..5}; do
    echo "Checking status for task $task_id (attempt $i)..."
    curl -s "http://localhost:8000/tasks/$task_id" | jq '.'
    sleep 10
  done
done 