from typing import Dict, Any
import pandas as pd
from skopt import gp_minimize
from skopt.space import Real, Integer
import numpy as np
import logging

logger = logging.getLogger(__name__)

def optimize_strategy_params(
    strategy_logic_description: str,
    data_dict: Dict,
    param_space: dict,
    method: str = 'bayesian'
) -> Dict[str, Any]:
    try:
        # Validate inputs
        if not isinstance(data_dict, dict) or 'data' not in data_dict:
            return {
                "success": False,
                "error": "Invalid data_dict format. Must contain 'data' key."
            }
            
        if not isinstance(param_space, dict) or not param_space:
            return {
                "success": False,
                "error": "Invalid param_space. Must be a non-empty dictionary."
            }
            
        # Convert data to DataFrame with proper error handling
        try:
            data = data_dict['data']
            if not isinstance(data, dict) or 'date' not in data or 'close' not in data:
                return {
                    "success": False,
                    "error": "Data must contain 'date' and 'close' columns"
                }
                
            df = pd.DataFrame(data)
            df.set_index('date', inplace=True)
            
            if df.empty:
                return {
                    "success": False,
                    "error": "Empty dataframe provided"
                }
                
            # Ensure close prices are numeric
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            if df['close'].isna().all():
                return {
                    "success": False,
                    "error": "No valid close prices found"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Error converting data to DataFrame: {str(e)}"
            }
        
        # Validate parameter space
        dimensions = []
        param_names = []
        try:
            for name, space in param_space.items():
                if not isinstance(space, dict) or 'type' not in space or 'low' not in space or 'high' not in space:
                    return {
                        "success": False,
                        "error": f"Invalid parameter space for {name}. Must contain 'type', 'low', and 'high'"
                    }
                
                if space['low'] >= space['high']:
                    return {
                        "success": False,
                        "error": f"Invalid range for {name}. 'low' must be less than 'high'"
                    }
                    
                param_names.append(name)
                if space['type'] == 'real':
                    dimensions.append(Real(space['low'], space['high']))
                elif space['type'] == 'integer':
                    dimensions.append(Integer(space['low'], space['high']))
                else:
                    return {
                        "success": False,
                        "error": f"Invalid parameter type for {name}: {space['type']}"
                    }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error validating parameter space: {str(e)}"
            }
        
        # Define objective function with better error handling
        def objective(params):
            param_dict = dict(zip(param_names, params))
            try:
                result = execute_strategy(df, strategy_logic_description, param_dict)
                
                # Handle invalid results
                if not isinstance(result, dict) or 'sharpe_ratio' not in result:
                    return 999999
                    
                sharpe_ratio = result['sharpe_ratio']
                if np.isnan(sharpe_ratio) or np.isinf(sharpe_ratio):
                    return 999999
                    
                return -sharpe_ratio  # We minimize the negative Sharpe ratio
            except Exception as e:
                logger.error(f"Error in objective function: {str(e)}")
                return 999999
        
        # Run optimization with proper error handling
        try:
            result = gp_minimize(
                objective,
                dimensions,
                n_calls=50,
                random_state=42
            )
            
            if result.fun == 999999:
                return {
                    "success": False,
                    "error": "Optimization failed to find valid parameters"
                }
                
            best_params = dict(zip(param_names, result.x))
            return {
                "success": True,
                "best_params": best_params,
                "optimization_score": -result.fun
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Optimization failed: {str(e)}"
            }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def execute_strategy(
    df: pd.DataFrame,
    logic_description: str,
    params: Dict[str, Any]
) -> Dict[str, float]:
    """Execute strategy based on description and parameters."""
    try:
        if df.empty:
            return {
                "sharpe_ratio": float('nan'),
                "total_return": float('nan'),
                "max_drawdown": float('nan')
            }
            
        returns = pd.Series(0.0, index=df.index)
        
        if "moving_average" in logic_description.lower():
            # Validate parameters
            if 'fast_period' not in params or 'slow_period' not in params:
                return {
                    "sharpe_ratio": float('nan'),
                    "total_return": float('nan'),
                    "max_drawdown": float('nan')
                }
                
            if params['fast_period'] >= params['slow_period']:
                return {
                    "sharpe_ratio": float('nan'),
                    "total_return": float('nan'),
                    "max_drawdown": float('nan')
                }
            
            # Handle NaN values in moving averages
            fast_ma = df['close'].rolling(params['fast_period']).mean()
            slow_ma = df['close'].rolling(params['slow_period']).mean()
            position = (fast_ma > slow_ma).astype(float)
            position = position.fillna(0)  # No position when MA is undefined
            
            # Calculate returns with proper error handling
            price_changes = df['close'].pct_change().fillna(0)
            returns = position.shift(1).fillna(0) * price_changes
        
        # Calculate metrics with proper error handling
        valid_returns = returns[~returns.isna()]
        if len(valid_returns) < 2:
            return {
                "sharpe_ratio": float('nan'),
                "total_return": float('nan'),
                "max_drawdown": float('nan')
            }
        
        # Calculate Sharpe ratio
        annual_factor = np.sqrt(252)  # Annualization factor for daily data
        sharpe_ratio = annual_factor * valid_returns.mean() / valid_returns.std() if valid_returns.std() != 0 else 0
        
        # Calculate total return
        total_return = (1 + valid_returns).prod() - 1
        
        # Calculate drawdown
        cum_returns = (1 + valid_returns).cumprod()
        rolling_max = cum_returns.expanding().max()
        drawdowns = (cum_returns - rolling_max) / rolling_max
        max_drawdown = drawdowns.min()
        
        return {
            "sharpe_ratio": float(sharpe_ratio),
            "total_return": float(total_return),
            "max_drawdown": float(max_drawdown)
        }
        
    except Exception as e:
        logger.error(f"Error executing strategy: {str(e)}")
        return {
            "sharpe_ratio": float('nan'),
            "total_return": float('nan'),
            "max_drawdown": float('nan')
        }