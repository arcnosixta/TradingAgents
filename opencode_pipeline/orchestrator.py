import os
import argparse
import datetime
import logging
import json
import time

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.agents.utils.agent_utils import resolve_instrument_identity, build_instrument_context
from tradingagents.agents.utils.entry_validator import (
    parse_current_price_from_snapshot,
    apply_validation_to_report,
)
from data_collector import collect_data
from agent_runner import run_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PIPELINE_STAGES = [
    ("market", "market_analyst.md", "reports/market.md"),
    ("sentiment", "sentiment_analyst.md", "reports/sentiment.md"),
    ("news", "news_analyst.md", "reports/news.md"),
    ("fundamentals", "fundamentals_analyst.md", "reports/fundamentals.md"),
    ("bull_researcher", "bull_researcher.md", "reports/bull_case.md"),
    ("bear_researcher", "bear_researcher.md", "reports/bear_case.md"),
    ("research_manager", "research_manager.md", "reports/research_plan.md"),
    ("trader", "trader.md", "reports/trader_proposal.md"),
    ("risk_aggressive", "risk_aggressive.md", "reports/risk_aggressive.md"),
    ("risk_conservative", "risk_conservative.md", "reports/risk_conservative.md"),
    ("risk_neutral", "risk_neutral.md", "reports/risk_neutral.md"),
    ("portfolio_manager", "portfolio_manager.md", "reports/final_decision.md"),
]

def main():
    parser = argparse.ArgumentParser(description="Run TradingAgents OpenCode Pipeline")
    parser.add_argument("ticker", nargs="?", default="XAU-USD", help="Ticker symbol (default: XAU-USD)")
    parser.add_argument("--trade_date", default=datetime.datetime.now().strftime("%Y-%m-%d"), help="Trade date YYYY-MM-DD")
    args = parser.parse_args()

    ticker = args.ticker
    trade_date = args.trade_date

    end_date_dt = datetime.datetime.strptime(trade_date, "%Y-%m-%d")
    start_date_dt = end_date_dt - datetime.timedelta(days=365) # 1 year of data
    start_date = start_date_dt.strftime("%Y-%m-%d")
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs", f"{ticker}_{trade_date}_{timestamp}")
    
    os.makedirs(run_dir, exist_ok=True)
    reports_dir = os.path.join(run_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    
    logger.info(f"Starting pipeline for {ticker} at {trade_date}")
    logger.info(f"Run directory: {run_dir}")
    
    # Phase 0: Collect Data
    collect_data(ticker, start_date, trade_date, trade_date, run_dir)
    
    # Extract current price from snapshot for trader prompt
    snapshot_path = os.path.join(run_dir, "data", "snapshot.md")
    current_price_data = parse_current_price_from_snapshot(snapshot_path)
    if current_price_data:
        logger.info(f"Current price from snapshot: close={current_price_data['close']}, "
                     f"high={current_price_data['high']}, low={current_price_data['low']}")
    else:
        logger.warning("Could not parse current price from snapshot, using defaults")
        current_price_data = {"close": 0.0, "high": 0.0, "low": 0.0}
    
    # Memory past context
    memory = TradingMemoryLog(DEFAULT_CONFIG)
    past_context = memory.get_past_context(ticker, n_same=5, n_cross=3)
    if past_context:
        with open(os.path.join(run_dir, "data", "past_context.md"), "w") as f:
            f.write(past_context)
            
    # Resolve instrument context for prompts
    identity = resolve_instrument_identity(ticker)
    instrument_context = build_instrument_context(ticker, "stock", identity)

    format_kwargs = {
        "ticker": ticker,
        "trade_date": trade_date,
        "start_date": start_date,
        "end_date": trade_date,
        "instrument_context": instrument_context,
        "current_price": current_price_data["close"],
        "day_high": current_price_data["high"],
        "day_low": current_price_data["low"],
    }

    prompts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")

    run_log = {}
    
    # Phase 1-6: Agents
    for role, prompt_file, output_file in PIPELINE_STAGES:
        start_t = time.time()
        logger.info(f"--- Running {role} ---")
        prompt_path = os.path.join(prompts_dir, prompt_file)
        
        try:
            stdout = run_agent(role, prompt_path, format_kwargs, run_dir, output_file)
            status = "success"
        except Exception as e:
            logger.error(f"Failed {role}: {e}")
            status = f"failed: {e}"
            stdout = ""

        # Validate trader entry/stop levels after trader stage
        if role == "trader" and status == "success":
            trader_report = os.path.join(run_dir, output_file)
            if current_price_data["close"] > 0:
                result = apply_validation_to_report(trader_report, current_price_data["close"])
                if result and not result.is_valid:
                    logger.warning(f"Trader entry/stop corrected: {result.summary}")
                elif result:
                    logger.info("Trader entry/stop validated: PASS")
            
        elapsed = time.time() - start_t
        run_log[role] = {
            "status": status,
            "elapsed_seconds": round(elapsed, 2)
        }
        
    with open(os.path.join(run_dir, "run_log.json"), "w") as f:
        json.dump(run_log, f, indent=2)
        
    # Phase 7: Save to memory
    final_decision_path = os.path.join(reports_dir, "final_decision.md")
    if os.path.exists(final_decision_path):
        with open(final_decision_path, "r") as f:
            final_text = f.read()
            
        memory.store_decision(ticker, trade_date, final_text)
        logger.info("Saved final decision to memory log.")
    else:
        logger.warning("No final decision found to save.")
        
    logger.info("Pipeline complete.")

if __name__ == "__main__":
    main()
