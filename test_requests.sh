#!/bin/bash

# Test 1: Create a new research task with technical analysis request
echo "Testing technical analysis workflow..."
curl -X POST http://localhost:8000/tasks/ \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "research",
    "request": "Analyze AAPL technical indicators and suggest trading strategy",
    "input_data": {
      "symbol": "AAPL",
      "timeframe": "1y",
      "indicators": ["RSI", "MACD", "BB"]
    }
  }'

# Test 2: Create a backtesting task
echo "\nTesting backtesting workflow..."
curl -X POST http://localhost:8000/tasks/ \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "backtest",
    "request": "Backtest a simple moving average crossover strategy for AAPL",
    "input_data": {
      "symbol": "AAPL",
      "strategy": "sma_crossover",
      "parameters": {
        "fast_period": 50,
        "slow_period": 200
      },
      "timeframe": "5y"
    }
  }'

# Test 3: Knowledge base query
echo "\nTesting knowledge base query..."
curl -X POST http://localhost:8000/tasks/ \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "research",
    "request": "What are the best practices for risk management in algorithmic trading?",
    "input_data": {
      "context": "algorithmic_trading",
      "focus": "risk_management"
    }
  }' 