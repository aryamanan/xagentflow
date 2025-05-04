import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
from app.tools.market_data_api_tool import get_market_data

logger = logging.getLogger(__name__)

def calculate_indicators(data: pd.DataFrame, indicators: List[str]) -> Dict[str, Any]:
    """
    Calculate technical indicators for the given data
    
    Args:
        data: DataFrame with OHLCV data
        indicators: List of indicators to calculate
        
    Returns:
        Dictionary with calculated indicators
    """
    logger.info(f"Calculating indicators: {indicators}")
    results = {}
    
    try:
        # Validate input data
        required_columns = ['Close', 'High', 'Low']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
        
        # Convert data to float if needed
        for col in required_columns:
            data[col] = pd.to_numeric(data[col], errors='coerce')
        
        # Remove any NaN values
        data = data.dropna()
        
        if len(data) < 2:
            raise ValueError("Not enough valid data points")
        
        for indicator in indicators:
            try:
                if indicator.lower() == 'rsi':
                    # Calculate RSI using 14-period
                    delta = data['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    results['rsi'] = rsi.fillna(50).tolist()  # Fill NaN with neutral value
                    
                elif indicator.lower() == 'macd':
                    # Calculate MACD (12,26,9)
                    exp1 = data['Close'].ewm(span=12, adjust=False).mean()
                    exp2 = data['Close'].ewm(span=26, adjust=False).mean()
                    macd = exp1 - exp2
                    signal = macd.ewm(span=9, adjust=False).mean()
                    results['macd'] = {
                        'macd': macd.fillna(0).tolist(),
                        'signal': signal.fillna(0).tolist(),
                        'histogram': (macd - signal).fillna(0).tolist()
                    }
                    
                elif indicator.lower() == 'bollinger':
                    # Calculate Bollinger Bands (20,2)
                    sma = data['Close'].rolling(window=20).mean()
                    std = data['Close'].rolling(window=20).std()
                    results['bollinger'] = {
                        'upper': (sma + (std * 2)).fillna(method='ffill').tolist(),
                        'middle': sma.fillna(method='ffill').tolist(),
                        'lower': (sma - (std * 2)).fillna(method='ffill').tolist()
                    }
                    
                elif indicator.lower() == 'sma':
                    # Calculate Simple Moving Averages
                    results['sma'] = {
                        'sma_20': data['Close'].rolling(window=20).mean().fillna(method='ffill').tolist(),
                        'sma_50': data['Close'].rolling(window=50).mean().fillna(method='ffill').tolist(),
                        'sma_200': data['Close'].rolling(window=200).mean().fillna(method='ffill').tolist()
                    }
                    
                elif indicator.lower() == 'ema':
                    # Calculate Exponential Moving Averages
                    results['ema'] = {
                        'ema_12': data['Close'].ewm(span=12, adjust=False).mean().fillna(method='ffill').tolist(),
                        'ema_26': data['Close'].ewm(span=26, adjust=False).mean().fillna(method='ffill').tolist()
                    }
                    
                elif indicator.lower() == 'atr':
                    # Calculate Average True Range (14-period)
                    high_low = data['High'] - data['Low']
                    high_close = abs(data['High'] - data['Close'].shift())
                    low_close = abs(data['Low'] - data['Close'].shift())
                    ranges = pd.concat([high_low, high_close, low_close], axis=1)
                    true_range = ranges.max(axis=1)
                    results['atr'] = true_range.rolling(window=14).mean().fillna(method='ffill').tolist()
                    
                elif indicator.lower() == 'stochastic':
                    # Calculate Stochastic Oscillator
                    low_14 = data['Low'].rolling(window=14).min()
                    high_14 = data['High'].rolling(window=14).max()
                    k = 100 * ((data['Close'] - low_14) / (high_14 - low_14))
                    d = k.rolling(window=3).mean()
                    results['stochastic'] = {
                        'k': k.fillna(50).tolist(),  # Fill NaN with neutral value
                        'd': d.fillna(50).tolist()  # Fill NaN with neutral value
                    }
                else:
                    logger.warning(f"Unknown indicator: {indicator}")
                    
            except Exception as e:
                logger.error(f"Error calculating {indicator}: {str(e)}")
                results[indicator] = None
        
        logger.info("Successfully calculated indicators")
        return results
        
    except Exception as e:
        logger.error(f"Error calculating indicators: {str(e)}")
        raise

def get_indicator_signals(data: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate trading signals based on technical indicators
    
    Args:
        data: DataFrame with OHLCV data
        indicators: Dictionary with calculated indicators
        
    Returns:
        Dictionary with trading signals for each indicator
    """
    logger.info("Generating trading signals from indicators")
    signals = {}
    
    try:
        # RSI signals
        if 'rsi' in indicators:
            rsi = indicators['rsi'].iloc[-1]
            if rsi > 70:
                signals['rsi'] = 'SELL'
            elif rsi < 30:
                signals['rsi'] = 'BUY'
            else:
                signals['rsi'] = 'HOLD'
        
        # MACD signals
        if 'macd' in indicators:
            macd = indicators['macd']['macd'].iloc[-1]
            signal = indicators['macd']['signal'].iloc[-1]
            if macd > signal:
                signals['macd'] = 'BUY'
            else:
                signals['macd'] = 'SELL'
        
        # Bollinger Bands signals
        if 'bollinger' in indicators:
            close = data['Close'].iloc[-1]
            upper = indicators['bollinger']['upper'].iloc[-1]
            lower = indicators['bollinger']['lower'].iloc[-1]
            if close > upper:
                signals['bollinger'] = 'SELL'
            elif close < lower:
                signals['bollinger'] = 'BUY'
            else:
                signals['bollinger'] = 'HOLD'
        
        logger.info(f"Generated signals: {signals}")
        return signals
        
    except Exception as e:
        logger.error(f"Error generating signals: {str(e)}")
        raise