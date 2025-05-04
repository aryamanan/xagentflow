from typing import Dict, Any
import pandas as pd
import numpy as np

def run_vectorbt_backtest(
    data_dict: Dict[str, Any],
    strategy_params: dict,
    logic_identifier: str
) -> Dict[str, Any]:
    try:
        # Validate input data
        if not isinstance(data_dict, dict) or 'data' not in data_dict:
            return {
                "success": False,
                "error": "Invalid data format: must contain 'data' key",
                "metrics": {}
            }
            
        data = data_dict['data']
        if not isinstance(data, dict) or 'date' not in data or 'close' not in data:
            return {
                "success": False,
                "error": "Data must contain 'date' and 'close' columns",
                "metrics": {}
            }
            
        # Convert data to DataFrame
        df = pd.DataFrame(data)
        df.set_index('date', inplace=True)
        
        if df.empty:
            return {
                "success": False,
                "error": "Empty dataframe provided",
                "metrics": {}
            }
            
        # Ensure close prices are numeric
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        if df['close'].isna().all():
            return {
                "success": False,
                "error": "No valid close prices found",
                "metrics": {}
            }
        
        # Generate signals based on logic identifier
        if logic_identifier == "moving_average_crossover":
            if 'fast_period' not in strategy_params or 'slow_period' not in strategy_params:
                return {
                    "success": False,
                    "error": "Strategy parameters must include 'fast_period' and 'slow_period'",
                    "metrics": {}
                }
                
            fast_ma = df['close'].rolling(window=int(strategy_params['fast_period'])).mean()
            slow_ma = df['close'].rolling(window=int(strategy_params['slow_period'])).mean()
            entries = fast_ma > slow_ma
            exits = fast_ma < slow_ma
            
        elif logic_identifier == "rsi_reversal":
            if 'rsi_period' not in strategy_params or 'oversold_threshold' not in strategy_params or 'overbought_threshold' not in strategy_params:
                return {
                    "success": False,
                    "error": "Missing required RSI strategy parameters",
                    "metrics": {}
                }
                
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=int(strategy_params['rsi_period'])).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=int(strategy_params['rsi_period'])).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            entries = rsi < float(strategy_params['oversold_threshold'])
            exits = rsi > float(strategy_params['overbought_threshold'])
        
        else:
            return {
                "success": False,
                "error": f"Unknown strategy logic: {logic_identifier}",
                "metrics": {}
            }
        
        # Calculate position and returns
        position = pd.Series(0, index=df.index)
        position[entries] = 1
        position[exits] = 0
        position = position.fillna(method='ffill').fillna(0)
        
        returns = df['close'].pct_change()
        strategy_returns = position.shift() * returns
        strategy_returns = strategy_returns.fillna(0)
        
        # Calculate metrics
        total_return = (1 + strategy_returns).prod() - 1
        
        # Calculate annualized return
        days = (pd.to_datetime(df.index[-1]) - pd.to_datetime(df.index[0])).days
        annualized_return = ((1 + total_return) ** (365 / days)) - 1 if days > 0 else 0
        
        # Calculate Sharpe ratio
        volatility = strategy_returns.std() * np.sqrt(252)
        sharpe_ratio = annualized_return / volatility if volatility != 0 else 0
        
        # Calculate drawdown
        cum_returns = (1 + strategy_returns).cumprod()
        rolling_max = cum_returns.expanding().max()
        drawdowns = (cum_returns - rolling_max) / rolling_max
        max_drawdown = drawdowns.min()
        
        # Calculate win rate
        trades = position.diff().fillna(0)
        trade_returns = strategy_returns[trades != 0]
        win_rate = (trade_returns > 0).sum() / len(trade_returns) * 100 if len(trade_returns) > 0 else 0
        
        # Calculate profit factor
        winning_trades = trade_returns[trade_returns > 0].sum()
        losing_trades = abs(trade_returns[trade_returns < 0].sum())
        profit_factor = winning_trades / losing_trades if losing_trades != 0 else float('inf')
        
        metrics = {
            "total_return": float(total_return * 100),  # Convert to percentage
            "annualized_return": float(annualized_return * 100),  # Convert to percentage
            "sharpe_ratio": float(sharpe_ratio),
            "max_drawdown": float(max_drawdown * 100),  # Convert to percentage
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor)
        }
        
        return {
            "success": True,
            "metrics": metrics,
            "trades": int(len(trade_returns))
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "metrics": {}
        }