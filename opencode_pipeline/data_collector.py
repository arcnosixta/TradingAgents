import os
import json
import logging

from tradingagents.dataflows.y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as yf_get_fundamentals,
    get_balance_sheet, 
    get_cashflow, 
    get_income_statement,
)
from tradingagents.dataflows.yfinance_news import get_news_yfinance, get_global_news_yfinance
from tradingagents.dataflows.fred import get_macro_data
from tradingagents.dataflows.polymarket import get_prediction_markets as pm_get
from tradingagents.dataflows.reddit import fetch_reddit_posts
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages
from tradingagents.dataflows.market_data_validator import build_verified_market_snapshot
from tradingagents.agents.utils.agent_utils import resolve_instrument_identity, build_instrument_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def write_to_file(path: str, data: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)

def format_indicators(indicators_dict: dict) -> str:
    return json.dumps(indicators_dict, indent=2)

def collect_data(ticker: str, start_date: str, end_date: str, trade_date: str, run_dir: str):
    data_dir = os.path.join(run_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    
    logger.info(f"Collecting data for {ticker} at {trade_date}...")
    
    try:
        identity = resolve_instrument_identity(ticker)
        instrument_context = build_instrument_context(ticker, "stock", identity)
        write_to_file(os.path.join(data_dir, "instrument_context.md"), instrument_context)
    except Exception as e:
        logger.error(f"Error resolving identity: {e}")

    try:
        ohlcv = get_YFin_data_online(ticker, start_date, end_date)
        if isinstance(ohlcv, list):
            ohlcv = json.dumps(ohlcv, indent=2)
        elif not isinstance(ohlcv, str):
            ohlcv = str(ohlcv)
        write_to_file(os.path.join(data_dir, "ohlcv.md"), ohlcv)
    except Exception as e:
        logger.error(f"Error getting OHLCV: {e}")

    indicators = {}
    ind_list = ["close_50_sma", "close_200_sma", "close_10_ema", "macd", "macds", "macdh", "rsi", "boll", "boll_ub", "boll_lb", "atr"]
    for ind in ind_list:
        try:
            val = get_stock_stats_indicators_window(ticker, ind, trade_date, 30)
            indicators[ind] = val
        except Exception as e:
            logger.error(f"Error getting indicator {ind}: {e}")
            indicators[ind] = f"Error: {e}"
    write_to_file(os.path.join(data_dir, "indicators.md"), format_indicators(indicators))

    try:
        fundamentals = yf_get_fundamentals(ticker)
        write_to_file(os.path.join(data_dir, "fundamentals.md"), str(fundamentals))
    except Exception as e:
        logger.error(f"Error getting fundamentals: {e}")

    try:
        balance = get_balance_sheet(ticker, "quarterly")
        write_to_file(os.path.join(data_dir, "balance_sheet.md"), str(balance))
    except Exception as e:
        logger.error(f"Error getting balance sheet: {e}")

    try:
        cashflow = get_cashflow(ticker, "quarterly")
        write_to_file(os.path.join(data_dir, "cashflow.md"), str(cashflow))
    except Exception as e:
        logger.error(f"Error getting cashflow: {e}")

    try:
        income = get_income_statement(ticker, "quarterly")
        write_to_file(os.path.join(data_dir, "income.md"), str(income))
    except Exception as e:
        logger.error(f"Error getting income statement: {e}")

    try:
        news = get_news_yfinance(ticker, start_date, end_date)
        write_to_file(os.path.join(data_dir, "news.md"), str(news))
    except Exception as e:
        logger.error(f"Error getting news: {e}")

    try:
        global_news = get_global_news_yfinance(trade_date)
        write_to_file(os.path.join(data_dir, "global_news.md"), str(global_news))
    except Exception as e:
        logger.error(f"Error getting global news: {e}")

    macro = {}
    for ind in ["fed_funds_rate", "cpi", "unemployment", "10y_treasury", "vix"]:
        try:
            macro[ind] = get_macro_data(ind, trade_date)
        except Exception as e:
            logger.error(f"Error getting macro {ind}: {e}")
            macro[ind] = f"Error: {e}"
    write_to_file(os.path.join(data_dir, "macro.md"), json.dumps(macro, indent=2))

    try:
        prediction_mkts = pm_get(ticker) # Or "topic_related_to_ticker"
        write_to_file(os.path.join(data_dir, "predictions.md"), str(prediction_mkts))
    except Exception as e:
        logger.error(f"Error getting prediction markets: {e}")

    try:
        reddit = fetch_reddit_posts(ticker)
        write_to_file(os.path.join(data_dir, "reddit.md"), str(reddit))
    except Exception as e:
        logger.error(f"Error getting reddit: {e}")

    try:
        stocktwits = fetch_stocktwits_messages(ticker)
        write_to_file(os.path.join(data_dir, "stocktwits.md"), str(stocktwits))
    except Exception as e:
        logger.error(f"Error getting stocktwits: {e}")

    try:
        snapshot = build_verified_market_snapshot(ticker, trade_date)
        write_to_file(os.path.join(data_dir, "snapshot.md"), str(snapshot))
    except Exception as e:
        logger.error(f"Error getting snapshot: {e}")
        
    logger.info("Data collection complete.")
