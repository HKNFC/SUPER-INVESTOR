import json
import os
import uuid
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("stock_screener.history")

HISTORY_FILE = "scan_history.json"


def _load_raw() -> Dict[str, Any]:
    if not os.path.exists(HISTORY_FILE):
        return {"entries": []}
    try:
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
        if "entries" not in data:
            data = {"entries": []}
        return data
    except (json.JSONDecodeError, IOError) as e:
        logger.error("Failed to read history file: %s", e)
        return {"entries": []}


def _save_raw(data: Dict[str, Any]) -> bool:
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except IOError as e:
        logger.error("Failed to write history file: %s", e)
        return False


def _gen_id() -> str:
    return uuid.uuid4().hex[:12]


def add_scan_entry(
    market: str,
    segment: str,
    scan_mode: str,
    profile: str,
    quality: str,
    sort_by: str,
    top_n: int,
    result_count: int,
    top_stocks: List[str],
    scan_date: Optional[str] = None,
) -> bool:
    data = _load_raw()
    entry = {
        "id": _gen_id(),
        "type": "scan",
        "timestamp": time.time(),
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "market": market,
        "segment": segment,
        "scan_mode": scan_mode,
        "profile": profile,
        "quality": quality,
        "sort_by": sort_by,
        "top_n": top_n,
        "result_count": result_count,
        "top_stocks": top_stocks[:10],
        "scan_date": scan_date,
    }
    data["entries"].insert(0, entry)
    return _save_raw(data)


def add_backtest_entry(
    params: Dict[str, Any],
    total_return: float,
    benchmark_return: float,
    num_periods: int,
    sharpe: Optional[float] = None,
    max_drawdown: Optional[float] = None,
) -> bool:
    data = _load_raw()
    entry = {
        "id": _gen_id(),
        "type": "backtest",
        "timestamp": time.time(),
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "params": params,
        "total_return": total_return,
        "benchmark_return": benchmark_return,
        "num_periods": num_periods,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
    }
    data["entries"].insert(0, entry)
    return _save_raw(data)


def get_history() -> List[Dict[str, Any]]:
    data = _load_raw()
    return data.get("entries", [])


def delete_entry(entry_id) -> bool:
    data = _load_raw()
    original_len = len(data["entries"])
    data["entries"] = [e for e in data["entries"] if str(e.get("id")) != str(entry_id)]
    if len(data["entries"]) < original_len:
        return _save_raw(data)
    return False


def clear_history() -> bool:
    return _save_raw({"entries": []})
