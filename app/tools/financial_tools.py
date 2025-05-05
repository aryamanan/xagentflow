import logging
import aiohttp
import pandas as pd
import numpy as np
import json
from typing import List, Dict, Any
from datetime import datetime, timedelta
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

async def fetch_historical_data(symbol: str, period: str = "1y", interval: str = "1d") -> Dict[str, Any]:
    """
    Fetch historical price data using yfapi.net API
    """
    logger.info("fetching_historical_data", symbol=symbol, period=period, interval=interval)
    
    try:
        async with aiohttp.ClientSession() as session:
            # Ensure API Key and URL are loaded correctly
            api_key = settings.EXTERNAL_MARKET_DATA_API_KEY
            api_url_base = settings.EXTERNAL_MARKET_DATA_API_URL
            if not api_key:
                logger.error("EXTERNAL_MARKET_DATA_API_KEY is not set in settings")
                return {"ticker": symbol, "status": "error", "error": "API key not configured"}
            if not api_url_base:
                logger.error("EXTERNAL_MARKET_DATA_API_URL is not set in settings")
                return {"ticker": symbol, "status": "error", "error": "API URL not configured"}

            headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
            url = f"https://{api_url_base.rstrip('/')}/v8/finance/chart/{symbol}"
            params = {"range": period, "interval": interval, "events": "div,splits"}
            
            logger.debug("Calling yfapi.net", url=url, params=params)
            
            async with session.get(url, headers=headers, params=params) as response:
                logger.info("yfapi.net response received", status_code=response.status, url=response.url)
                
                # Read response text regardless of status for debugging
                response_text = await response.text()
                
                # Check status code *after* reading text
                if response.status != 200:
                    logger.error("yfapi.net API error", 
                               status=response.status, 
                               response_preview=response_text[:500])
                    return {
                        "ticker": symbol,
                        "status": "error",
                        "error": f"API request failed with status {response.status}: {response_text[:100]}"
                    }

                try:
                    data = json.loads(response_text)
                except json.JSONDecodeError as json_err:
                    logger.error("JSON decoding failed", 
                               error=str(json_err),
                               response_preview=response_text[:500])
                    return {"ticker": symbol, "status": "error", "error": f"Failed to decode API JSON response: {json_err}"}

                logger.debug("Raw JSON structure received", 
                           keys=list(data.keys()) if isinstance(data, dict) else 'Not a dict')

                # Extract the time series data
                chart = data.get("chart", {})
                result = chart.get("result", [{}])[0]
                
                # Get timestamps and indicators
                timestamps = result.get("timestamp", [])
                indicators = result.get("indicators", {})
                quote = indicators.get("quote", [{}])[0]
                
                # Extract OHLCV data
                formatted_data = []
                for i, timestamp in enumerate(timestamps):
                    try:
                        # Get values defensively
                        o = quote.get("open", [])[i]
                        h = quote.get("high", [])[i]
                        l = quote.get("low", [])[i]
                        c = quote.get("close", [])[i]
                        v = quote.get("volume", [])[i]

                        # Check for None explicitly *before* float/int conversion
                        if any(val is None for val in [o, h, l, c, v]):
                            logger.warning("Found None value in source data", 
                                         timestamp=timestamp, 
                                         index=i)
                            continue

                        formatted_data.append({
                            "date": datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                            "open": float(o),
                            "high": float(h),
                            "low": float(l),
                            "close": float(c),
                            "volume": int(v)
                        })
                    except (TypeError, ValueError, IndexError) as format_error:
                        logger.error("Error formatting data point", 
                                   index=i,
                                   timestamp=timestamp,
                                   error=str(format_error))
                        continue

                logger.info("historical_data_fetched", 
                          symbol=symbol,
                          status="success",
                          data_points=len(formatted_data))
                return {
                    "ticker": symbol,
                    "period": period,
                    "interval": interval,
                    "data": formatted_data,
                    "status": "success"
                }

    except aiohttp.ClientError as client_error:
        logger.error("Network/Client error", 
                    symbol=symbol,
                    error=str(client_error))
        return {"ticker": symbol, "status": "error", "error": f"Network/Client error: {client_error}"}
    except Exception as e:
        logger.error("Unexpected error in fetch_historical_data", 
                    symbol=symbol,
                    error=str(e),
                    error_type=type(e).__name__)
        return {
            "ticker": symbol,
            "status": "error",
            "error": f"Unexpected error in fetch_historical_data: {str(e)}"
        }

async def calculate_technical_indicators(data: List[Dict[str, Any]], indicators: List[str]) -> Dict[str, Any]:
    """
    Calculate technical indicators using real market data
    """
    logger.info("calculating_indicators", indicators=indicators)
    logger.debug("Input data points", count=len(data))
    
    try:
        # data IS the list of dictionaries now
        if not data:
             logger.warning("calculate_technical_indicators called with empty data list")
             return {"status": "error", "error": "Input data list is empty"}
             
        df = pd.DataFrame(data) # Create DataFrame directly from the list
        
        # Ensure 'close' column exists and is numeric
        if 'close' not in df.columns:
             logger.error("Missing 'close' column in input data for indicators")
             return {"status": "error", "error": "Missing 'close' column in input data"}
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df.dropna(subset=['close'], inplace=True) # Drop rows where close price is invalid
        if df.empty:
             logger.error("No valid 'close' prices remaining after cleaning for indicators")
             return {"status": "error", "error": "No valid 'close' prices for indicator calculation"}

        # Ensure 'date' column exists and convert to datetime if needed for potential future use (optional here)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.sort_values(by='date') # Ensure data is sorted by date

        results = {}
        
        # Calculate RSI
        if 'rsi' in [ind.lower() for ind in indicators]:
            logger.debug("Calculating RSI")
            if len(df) >= 15: # Need enough data for rolling window + diff
                 delta = df['close'].diff()
                 gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
                 loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
                 rs = gain / loss
                 # Handle potential division by zero or infinite results
                 rsi_series = 100 - (100 / (1 + rs))
                 results['rsi'] = rsi_series.replace([float('inf'), -float('inf')], 100).fillna(50).tolist() # Replace inf/nan
            else:
                 logger.warning("Not enough data to calculate RSI (need >= 15 rows)")
                 results['rsi'] = []

        # Calculate MACD
        if 'macd' in [ind.lower() for ind in indicators]:
            logger.debug("Calculating MACD")
            if len(df) >= 26: # Need enough data for longest EMA
                 exp1 = df['close'].ewm(span=12, adjust=False).mean()
                 exp2 = df['close'].ewm(span=26, adjust=False).mean()
                 macd = exp1 - exp2
                 signal = macd.ewm(span=9, adjust=False).mean()
                 results['macd'] = {
                     'macd': macd.fillna(0).tolist(),
                     'signal': signal.fillna(0).tolist(),
                     'histogram': (macd - signal).fillna(0).tolist()
                 }
            else:
                 logger.warning("Not enough data to calculate MACD (need >= 26 rows)")
                 results['macd'] = {'macd': [], 'signal': [], 'histogram': []}

        # Calculate Bollinger Bands
        if 'bollinger' in [ind.lower() for ind in indicators]:
            logger.debug("Calculating Bollinger Bands")
            if len(df) >= 20: # Need enough data for rolling window
                 sma = df['close'].rolling(window=20, min_periods=1).mean()
                 std = df['close'].rolling(window=20, min_periods=1).std()
                 results['bollinger'] = {
                     'upper': (sma + (std * 2)).fillna(sma).tolist(), # Fill NaN with middle band
                     'middle': sma.bfill().ffill().tolist(), # Updated fillna
                     'lower': (sma - (std * 2)).fillna(sma).tolist() # Fill NaN with middle band
                 }
            else:
                 logger.warning("Not enough data to calculate Bollinger Bands (need >= 20 rows)")
                 results['bollinger'] = {'upper': [], 'middle': [], 'lower': []}

        # Add other indicators here following the pattern (e.g., SMA, EMA)
        if 'sma' in [ind.lower() for ind in indicators]:
             # Example: Calculate 50-day SMA
             logger.debug("Calculating SMA")
             if len(df) >= 50:
                 results['sma_50'] = df['close'].rolling(window=50, min_periods=1).mean().bfill().ffill().tolist()
             else:
                 logger.warning("Not enough data to calculate 50-day SMA (need >= 50 rows)")
                 results['sma_50'] = []

        if 'ema' in [ind.lower() for ind in indicators]:
             # Example: Calculate 20-day EMA
             logger.debug("Calculating EMA")
             if len(df) >= 20:
                 results['ema_20'] = df['close'].ewm(span=20, adjust=False).mean().tolist()
             else:
                 logger.warning("Not enough data to calculate 20-day EMA (need >= 20 rows)")
                 results['ema_20'] = []
        
        logger.info("indicators_calculated", 
                   status="success",
                   indicators=list(results.keys()))
        return {
            "status": "success",
            "data": {
                "input_length": len(data),
                "indicators": results
            }
        }
        
    except Exception as e:
        logger.error("indicator_calculation_error", 
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True)
        return {"status": "error", "error": f"Failed to calculate indicators: {str(e)}"}

async def optimize_strategy_parameters(
    strategy_type: str,
    data: Dict[str, Any],
    params_space: Dict[str, Any],
    optimization_target: str = "sharpe_ratio"
) -> Dict[str, Any]:
    """
    Optimize strategy parameters using real market data
    """
    logger.info("optimizing_strategy", 
                strategy_type=strategy_type,
                optimization_target=optimization_target)
    
    try:
        df = pd.DataFrame(data["data"])
        
        # Define the objective function based on strategy type
        def objective(params):
            if strategy_type == "moving_average_crossover":
                fast_period = int(params[0])
                slow_period = int(params[1])
                fast_ma = df['close'].rolling(window=fast_period).mean()
                slow_ma = df['close'].rolling(window=slow_period).mean()
                signals = np.where(fast_ma > slow_ma, 1, -1)
            elif strategy_type == "rsi":
                period = int(params[0])
                oversold = params[1]
                overbought = params[2]
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                signals = np.where(rsi < oversold, 1, np.where(rsi > overbought, -1, 0))
            
            # Calculate returns and align arrays
            returns = df['close'].pct_change()
            signals = signals[~np.isnan(returns)]  # Remove NaN entries from signals
            returns = returns[~np.isnan(returns)]  # Remove NaN entries from returns
            
            if len(returns) == 0 or len(signals) == 0:
                return 0  # Return 0 if no valid data
                
            # Calculate Sharpe ratio
            strategy_returns = returns * signals
            sharpe_ratio = np.sqrt(252) * strategy_returns.mean() / strategy_returns.std()
            return -sharpe_ratio if not np.isnan(sharpe_ratio) else 0  # Negative because we're minimizing
        
        # Optimize using scipy
        from scipy.optimize import minimize
        
        if strategy_type == "moving_average_crossover":
            bounds = [(params_space["fast_period"][0], params_space["fast_period"][1]), 
                     (params_space["slow_period"][0], params_space["slow_period"][1])]
            result = minimize(
                objective,
                x0=[20, 50],
                bounds=bounds,
                method='SLSQP'
            )
            optimal_params = {
                'fast_period': int(result.x[0]),
                'slow_period': int(result.x[1])
            }
        elif strategy_type == "rsi":
            bounds = [(params_space["period"][0], params_space["period"][1]),
                     (params_space["oversold"][0], params_space["oversold"][1]),
                     (params_space["overbought"][0], params_space["overbought"][1])]
            result = minimize(
                objective,
                x0=[14, 30, 70],
                bounds=bounds,
                method='SLSQP'
            )
            optimal_params = {
                'period': int(result.x[0]),
                'oversold': result.x[1],
                'overbought': result.x[2]
            }
        
        logger.info("strategy_optimized", 
                   strategy_type=strategy_type,
                   optimal_params=optimal_params,
                   optimization_score=-result.fun)
        
        return {
            "status": "success",
            "optimal_parameters": optimal_params,
            "optimization_score": -result.fun  # Convert back to positive Sharpe ratio
        }
        
    except Exception as e:
        logger.error("optimization_error", 
                    strategy_type=strategy_type,
                    error=str(e),
                    error_type=type(e).__name__)
        raise