@echo off
rem ===========================================================================
rem  Launcher for TradingAgents (batch, so PowerShell execution policy does not
rem  apply). Comments are ASCII on purpose: cmd.exe mis-parses UTF-8 text.
rem
rem  Usage:
rem    run.cmd                                     interactive menu
rem    run.cmd --ticker NVDA --date 2026-10-30 --analysts market,news --save --no-show
rem    run.cmd backtest NVDA,AAPL --start 2026-06-01 --end 2026-08-01 --every 7
rem    run.cmd --help
rem
rem  PYTHONUTF8 must be set before Python starts: Chinese text and the check
rem  marks raise UnicodeEncodeError under the default GBK code page.
rem ===========================================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set TRADINGAGENTS_NO_UPDATE_CHECK=1

if not exist ".venv\Scripts\tradingagents.exe" (
    echo [x] .venv\Scripts\tradingagents.exe not found.
    echo     Create the environment first:
    echo         python -m venv .venv
    echo         .venv\Scripts\python.exe -m pip install -e .
    exit /b 1
)

".venv\Scripts\tradingagents.exe" %*
exit /b %ERRORLEVEL%
