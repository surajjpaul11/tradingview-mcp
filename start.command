#!/usr/bin/env bash
# ==============================================================================
#  TradingView MCP & Trade Visualizer — One-Click Launcher (macOS)
# ==============================================================================

# Ensure script runs from the project root directory regardless of how it was launched
cd "$(cd "$(dirname "$0")" && pwd)"

# Ensure common paths (Homebrew, Cargo, uv, Python) are in PATH
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# Color definitions
BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

clear 2>/dev/null || true

echo -e "${CYAN}${BOLD}"
cat << "EOF"
====================================================================
      📈 AI Trading Intelligence Framework — Quick Launcher
====================================================================
EOF
echo -e "${NC}"

# 1. Check for uv
echo -e "${BOLD}[1/4] Checking Python & Package Manager (uv)...${NC}"
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}uv was not found in standard paths. Attempting to install uv...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv &> /dev/null; then
        echo -e "${RED}Error: Failed to find or install 'uv'. Please install uv manually: https://docs.astral.sh/uv/${NC}"
        echo "Press any key to exit..."
        read -n 1
        exit 1
    fi
fi
echo -e "      ${GREEN}✓ uv found: $(uv --version)${NC}"

# 2. Sync dependencies
echo -e "\n${BOLD}[2/4] Syncing project dependencies...${NC}"
uv sync --quiet
echo -e "      ${GREEN}✓ Virtual environment and dependencies ready.${NC}"

# 3. Ensure database and seed initial trades if empty
echo -e "\n${BOLD}[3/4] Checking trade database...${NC}"
mkdir -p data
TRADE_COUNT=$(uv run python -c "
import sqlite3
try:
    conn = sqlite3.connect('data/trades.db')
    cnt = conn.execute('SELECT COUNT(*) FROM trades').fetchone()[0]
    conn.close()
    print(cnt)
except Exception:
    print(0)
" 2>/dev/null || echo "0")

if [ "$TRADE_COUNT" -lt 50 ]; then
    echo -e "      ${YELLOW}Seeding database with full backtest history (690+ trades)...${NC}"
    uv run python -m tradingview_mcp.core.services.seed_backtests > /dev/null 2>&1
    TRADE_COUNT=$(uv run python -c "
import sqlite3
conn = sqlite3.connect('data/trades.db')
print(conn.execute('SELECT COUNT(*) FROM trades').fetchone()[0])
conn.close()
" 2>/dev/null || echo "0")
    echo -e "      ${GREEN}✓ Trade database initialized (${TRADE_COUNT} trades logged).${NC}"
else
    echo -e "      ${GREEN}✓ Trade database ready (${TRADE_COUNT} trades logged).${NC}"
fi

# 4. Launch the dashboard (launcher reserves the first free port: 8000, 8001, ...)
echo -e "\n${BOLD}[4/4] Launching Trade Visualizer Dashboard...${NC}"
echo -e "      ${CYAN}ℹ Selecting a free port and opening the browser...${NC}"
echo -e "      ${YELLOW}ℹ Press [Ctrl + C] in this window to stop the server at any time.${NC}\n"
echo -e "${CYAN}--------------------------------------------------------------------${NC}"

# Run the FastAPI server in the foreground
uv run python -m tradingview_mcp.ui.launcher --open-browser
