@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title TradingView MCP & Trade Visualizer Launcher

echo ====================================================================
echo       AI Trading Intelligence Framework - Quick Launcher
echo ====================================================================

where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] 'uv' package manager was not found.
    echo Please install uv from: https://docs.astral.sh/uv/
    echo.
    pause
    exit /b 1
)

echo [1/3] Syncing dependencies...
uv sync --quiet

echo [2/3] Checking trade database...
if not exist "data" mkdir data
uv run python test_strategies.py >nul 2>&1

echo [3/3] Starting Trade Visualizer on http://127.0.0.1:8000 ...
start http://127.0.0.1:8000

echo.
echo Server is running. Press Ctrl+C in this window to stop.
echo.

uv run python src/tradingview_mcp/ui/server.py
