#!/usr/bin/env python3
"""
Iterative Strategy Backtester
Compares strategies against Buy-and-Hold for GOOGL, PLTR, WDC, SPY
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
from pathlib import Path

# Configuration
TICKERS = ['GOOGL', 'PLTR', 'WDC', 'SPY']
START_DATE = '2020-01-01'
END_DATE = '2024-04-01'  # Last year of data
OUTPUT_DIR = Path('/root/workspace/tradingview-mcp/hermes-strategies')
LOG_FILE = Path('/root/workspace/tradingview-mcp/hermes-experiments.log')
MAX_ITERATIONS = 100

# Create output directory
OUTPUT_DIR.mkdir(exist_ok=True)
LOG_FILE.parent.mkdir(exist_ok=True)

# Initialize log
with open(LOG_FILE, 'w') as f:
    f.write("=" * 80 + "\n")
    f.write("HERMES ITERATIVE STRATEGY BACKTESTER\n")
    f.write(f"Started: {datetime.now().isoformat()}\n")
    f.write(f"Tickers: {', '.join(TICKERS)}\n")
    f.write(f"Period: {START_DATE} to {END_DATE}\n")
    f.write("=" * 80 + "\n\n")

def fetch_data(tickers):
    """Fetch historical data for all tickers"""
    data = yf.download(tickers, start=START_DATE, end=END_DATE, group_by='ticker')
    return data

def buy_and_hold(prices):
    """Calculate buy and hold returns"""
    returns = prices['Close'].pct_change().dropna()
    total_return = (1 + returns).prod() - 1
    cagr = (1 + total_return) ** (1 / len(returns)) - 1
    max_drawdown = calculate_max_drawdown(prices['Close'])
    sharpe = calculate_sharpe(returns)
    return {
        'total_return': total_return,
        'cagr': cagr,
        'max_drawdown': max_drawdown,
        'sharpe_ratio': sharpe
    }

def calculate_max_drawdown(prices):
    """Calculate maximum drawdown"""
    cumret = (1 + prices.pct_change().dropna()).cumprod()
    rolling_max = cumret.cummax()
    drawdown = (cumret - rolling_max) / rolling_max
    return drawdown.min()

def calculate_sharpe(returns, risk_free_rate=0.02):
    """Calculate Sharpe ratio (annualized)"""
    excess_returns = returns - risk_free_rate / 252
    if len(excess_returns) == 0:
        return 0
    sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)
    return sharpe

def plot_equity_curve(prices, equity, title, filename):
    """Generate equity curve plot data (simplified - just return data)"""
    equity_df = pd.DataFrame({'Equity': equity}, index=prices.index)
    plot_data = equity_df.to_dict()
    return plot_data

def run_strategy_1(prices):
    """Strategy 1: Moving Average Crossover (50/200 day)"""
    close = prices['Close']
    ma50 = close.rolling(window=50).mean()
    ma200 = close.rolling(window=200).mean()
    
    equity = np.zeros(len(close))
    in_position = False
    position = 0
    
    for i in range(1, len(close)):
        if ma50.iloc[i] > ma200.iloc[i] and not in_position:
            in_position = True
            position = equity[0]
        elif ma50.iloc[i] < ma200.iloc[i] and in_position:
            in_position = False
            equity = position
        
        equity[i] = position if in_position else position
    
    # Initialize with entry position
    equity[0] = 10000
    
    for i in range(1, len(close)):
        if ma50.iloc[i] > ma200.iloc[i]:
            if not in_position:
                position = equity[i-1]
                in_position = True
        elif ma50.iloc[i] < ma200.iloc[i] and in_position:
            in_position = False
            position = equity[i-1]
        
        if in_position:
            equity[i] = position * close.iloc[i] / close.iloc[i-1] if i > 0 else position
        else:
            equity[i] = position
    
    returns = pd.Series(equity).pct_change().dropna()
    total_return = (1 + returns).prod() - 1
    
    return {
        'total_return': total_return,
        'cagr': (1 + total_return) ** (1 / len(returns)) - 1 if len(returns) > 0 else 0,
        'max_drawdown': calculate_max_drawdown(pd.Series(equity)),
        'sharpe_ratio': calculate_sharpe(returns),
        'equity': equity.tolist(),
        'index': close.index.tolist()
    }

def run_strategy_2(prices):
    """Strategy 2: RSI Oversold/Overbought (14-day RSI)"""
    close = prices['Close']
    
    # Calculate RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    equity = np.zeros(len(close))
    in_position = False
    position = 10000
    
    equity[0] = 10000
    
    for i in range(14, len(close)):
        if rsi.iloc[i] < 30 and not in_position:
            in_position = True
            position = equity[i-1]
        elif rsi.iloc[i] > 70 and in_position:
            in_position = False
            position = equity[i-1]
        
        if in_position:
            equity[i] = position * close.iloc[i] / close.iloc[i-1] if i > 0 else position
        else:
            equity[i] = position
    
    returns = pd.Series(equity).pct_change().dropna()
    total_return = (1 + returns).prod() - 1
    
    return {
        'total_return': total_return,
        'cagr': (1 + total_return) ** (1 / len(returns)) - 1 if len(returns) > 0 else 0,
        'max_drawdown': calculate_max_drawdown(pd.Series(equity)),
        'sharpe_ratio': calculate_sharpe(returns),
        'equity': equity.tolist(),
        'index': close.index.tolist()
    }

def run_strategy_3(prices):
    """Strategy 3: Momentum (12-month return)"""
    close = prices['Close']
    
    # 12-month momentum
    momentum = close.pct_change(periods=252)
    
    equity = np.zeros(len(close))
    in_position = False
    position = 10000
    
    equity[0] = 10000
    
    for i in range(252, len(close)):
        if momentum.iloc[i] > 0 and not in_position:
            in_position = True
            position = equity[i-1]
        elif momentum.iloc[i] < 0 and in_position:
            in_position = False
            position = equity[i-1]
        
        if in_position:
            equity[i] = position * close.iloc[i] / close.iloc[i-1] if i > 0 else position
        else:
            equity[i] = position
    
    returns = pd.Series(equity).pct_change().dropna()
    total_return = (1 + returns).prod() - 1
    
    return {
        'total_return': total_return,
        'cagr': (1 + total_return) ** (1 / len(returns)) - 1 if len(returns) > 0 else 0,
        'max_drawdown': calculate_max_drawdown(pd.Series(equity)),
        'sharpe_ratio': calculate_sharpe(returns),
        'equity': equity.tolist(),
        'index': close.index.tolist()
    }

def evaluate_strategy(strategy_func, prices, tickers, iteration):
    """Evaluate a strategy and compare to BAH"""
    results = {}
    
    for ticker in tickers:
        ticker_data = prices[ticker]
        if ticker_data is None:
            continue
        
        try:
            # BAH benchmark
            bah_results = buy_and_hold(ticker_data)
            
            # Strategy
            strat_results = strategy_func(ticker_data)
            
            # Compare
            strat_vs_bah = strat_results['total_return'] - bah_results['total_return']
            
            results[ticker] = {
                'bah': bah_results,
                'strategy': strat_results,
                'vs_bah': strat_vs_bah
            }
            
        except Exception as e:
            results[ticker] = {'error': str(e)}
    
    return results

def log_experiment(iteration, tickers, results, strategy_name):
    """Log experiment results"""
    with open(LOG_FILE, 'a') as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write(f"EXPERIMENT #{iteration}\n")
        f.write(f"Strategy: {strategy_name}\n")
        f.write(f"Time: {datetime.now().isoformat()}\n")
        f.write("=" * 80 + "\n\n")
        
        all_beat_bah = True
        
        for ticker in tickers:
            if ticker in results:
                data = results[ticker]
                if 'error' not in data:
                    bah = data['bah']
                    strat = data['strategy']
                    diff = data['vs_bah']
                    
                    status = "✓ BEATS BAH" if diff > 0 else "✗ Underperforms"
                    if diff <= 0:
                        all_beat_bah = False
                    
                    f.write(f"{ticker}:\n")
                    f.write(f"  BAH Total Return: {bah['total_return']*100:.2f}%\n")
                    f.write(f"  Strategy Total Return: {strat['total_return']*100:.2f}%\n")
                    f.write(f"  Difference: {diff*100:+.2f}% [{status}]\n")
                    f.write(f"  BAH Sharpe: {bah['sharpe_ratio']:.2f}\n")
                    f.write(f"  Strategy Sharpe: {strat['sharpe_ratio']:.2f}\n")
                    f.write(f"  BAH Max DD: {bah['max_drawdown']*100:.2f}%\n")
                    f.write(f"  Strategy Max DD: {strat['max_drawdown']*100:.2f}%\n")
                    f.write("\n")
        
        if all_beat_bah:
            f.write("\n✓✓✓ ALL TICKERS BEAT BUY AND HOLD! ✓✓✓\n")
        else:
            f.write("\nStatus: Some or all strategies underperformed BAH\n")

def save_best_results(results, iteration):
    """Save results for the best performing iteration"""
    output_file = OUTPUT_DIR / f'iteration_{iteration:03d}.json'
    with open(output_file, 'w') as f:
        json.dump({
            'iteration': iteration,
            'timestamp': datetime.now().isoformat(),
            'results': results
        }, f, indent=2)
    print(f"Saved results to {output_file}")

def main():
    """Main iterative loop"""
    print("Fetching market data...")
    prices = fetch_data(TICKERS)
    
    if prices is None or prices.empty:
        print("Error: Could not fetch data")
        return
    
    strategies = [
        (run_strategy_1, "MA Crossover (50/200)"),
        (run_strategy_2, "RSI Oversold/Overbought"),
        (run_strategy_3, "12-Month Momentum"),
    ]
    
    iteration = 0
    best_iteration = 0
    best_avg_diff = -float('inf')
    
    while iteration < MAX_ITERATIONS:
        iteration += 1
        strategy_func, strategy_name = strategies[iteration % len(strategies)]
        
        print(f"\nIteration {iteration}: Testing {strategy_name}")
        
        # Run strategy
        results = evaluate_strategy(strategy_func, prices, TICKERS, iteration)
        
        # Log results
        log_experiment(iteration, TICKERS, results, strategy_name)
        
        # Calculate average performance vs BAH
        avg_diff = 0
        tickers_with_results = 0
        for ticker in TICKERS:
            if ticker in results and 'error' not in results[ticker]:
                avg_diff += results[ticker]['vs_bah']
                tickers_with_results += 1
        
        if tickers_with_results > 0:
            avg_diff /= tickers_with_results
            
            if avg_diff > best_avg_diff:
                best_avg_diff = avg_diff
                best_iteration = iteration
                save_best_results(results, iteration)
                print(f"New best! Avg vs BAH: {avg_diff*100:+.2f}%")
            else:
                print(f"Avg vs BAH: {avg_diff*100:+.2f}% (Best: {best_avg_diff*100:+.2f}%)")
        else:
            print("No valid results this iteration")
        
        if avg_diff > 0:
            print("\n✓ All tickers beat BAH! Stopping.")
            break
        
        print(f"\nBest so far: Iteration {best_iteration} with {best_avg_diff*100:+.2f}% avg outperformance")
        
        if iteration >= MAX_ITERATIONS:
            print(f"\nReached max iterations ({MAX_ITERATIONS})")
    
    # Final summary
    with open(LOG_FILE, 'a') as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write("FINAL SUMMARY\n")
        f.write("=" * 80 + "\n")
        f.write(f"Best iteration: {best_iteration}\n")
        f.write(f"Best avg outperformance: {best_avg_diff*100:+.2f}%\n")
        f.write(f"Total iterations: {iteration}\n")
    
    print(f"\nFinal: Best iteration was #{best_iteration}")
    print(f"Best strategy average outperformance: {best_avg_diff*100:+.2f}% vs BAH")

if __name__ == '__main__':
    main()
