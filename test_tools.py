import requests
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

BASE_URL = "http://127.0.0.1:8000/test/tools"

def test_backtesting():
    print("\n=== Testing Backtesting Tools ===")
    
    # Create sample data with realistic price movements
    dates = pd.date_range(start='2023-01-01', end='2023-12-31', freq='D')
    price = 100
    prices = []
    for _ in range(len(dates)):
        change = np.random.normal(0.0001, 0.02)  # Small upward bias with volatility
        price *= (1 + change)
        prices.append(price)
    
    data = {
        'data': {
            'date': dates.strftime('%Y-%m-%d').tolist(),
            'close': prices
        }
    }
    
    # Test moving average crossover strategy
    payload = {
        "data": data,
        "strategy_params": {
            "fast_period": 10,
            "slow_period": 30
        },
        "logic_identifier": "moving_average_crossover"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/backtest", json=payload)
        print("Moving Average Strategy Test:", response.status_code)
        if response.status_code == 200:
            result = response.json()
            if result.get("success", False):
                print("Metrics:", json.dumps(result.get("metrics", {}), indent=2))
            else:
                print("Error:", result.get("error", "Unknown error"))
        else:
            print("Error:", response.text)
    except Exception as e:
        print("Error testing backtesting:", str(e))

def test_knowledge_base():
    print("\n=== Testing Knowledge Base Tools ===")
    
    queries = [
        "technical analysis",
        "risk management",
        "trading strategy"
    ]
    
    for query in queries:
        try:
            payload = {"query": query}
            response = requests.post(f"{BASE_URL}/query_knowledge", json=payload)
            print(f"\nQuery: {query}")
            print("Status:", response.status_code)
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    print("Response:", result.get("result", ""))
                else:
                    print("Error:", result.get("error", "Unknown error"))
            else:
                print("Error:", response.text)
        except Exception as e:
            print(f"Error testing knowledge base for query '{query}':", str(e))

def test_optimization():
    print("\n=== Testing Optimization Tools ===")
    
    # Create sample data with realistic price movements
    dates = pd.date_range(start='2023-01-01', end='2023-12-31', freq='D')
    price = 100
    prices = []
    for _ in range(len(dates)):
        change = np.random.normal(0.0001, 0.02)
        price *= (1 + change)
        prices.append(price)
    
    data = {
        'data': {
            'date': dates.strftime('%Y-%m-%d').tolist(),
            'close': prices
        }
    }
    
    payload = {
        "strategy_logic": "moving_average",
        "data": data,
        "param_space": {
            "fast_period": {"type": "integer", "low": 5, "high": 20},
            "slow_period": {"type": "integer", "low": 20, "high": 50}
        },
        "method": "bayesian"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/optimize_params", json=payload)
        print("Optimization Test:", response.status_code)
        if response.status_code == 200:
            result = response.json()
            if result.get("success", False):
                print("Best Parameters:", json.dumps(result.get("best_params", {}), indent=2))
                print("Optimization Score:", result.get("optimization_score"))
            else:
                print("Error:", result.get("error", "Unknown error"))
        else:
            print("Error:", response.text)
    except Exception as e:
        print("Error testing optimization:", str(e))

def test_indicators():
    print("\n=== Testing Technical Indicators ===")
    
    # Create sample data with realistic price movements
    dates = pd.date_range(start='2023-01-01', end='2023-12-31', freq='D')
    price = 100
    prices = []
    highs = []
    lows = []
    for _ in range(len(dates)):
        change = np.random.normal(0.0001, 0.02)
        price *= (1 + change)
        prices.append(price)
        highs.append(price * (1 + abs(np.random.normal(0, 0.005))))
        lows.append(price * (1 - abs(np.random.normal(0, 0.005))))
    
    data = {
        'data': {
            'date': dates.strftime('%Y-%m-%d').tolist(),
            'Close': prices,
            'High': highs,
            'Low': lows
        },
        'indicators': ['rsi', 'macd', 'bollinger', 'sma', 'ema']
    }
    
    try:
        response = requests.post(f"{BASE_URL}/calculate_custom_indicators", json=data)
        print("Indicators Test:", response.status_code)
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                indicators = result.get("indicators", {})
                print("Available Indicators:", list(indicators.keys()))
                for name, values in indicators.items():
                    if isinstance(values, dict):
                        print(f"\n{name} components:", list(values.keys()))
                    else:
                        print(f"\n{name} length:", len(values))
            else:
                print("Error:", result.get("error", "Unknown error"))
        else:
            print("Error:", response.text)
    except Exception as e:
        print("Error testing indicators:", str(e))

if __name__ == "__main__":
    try:
        test_backtesting()
        test_knowledge_base()
        test_optimization()
        test_indicators()
    except Exception as e:
        print(f"Error running tests: {str(e)}") 