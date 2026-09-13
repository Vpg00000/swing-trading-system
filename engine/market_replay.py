"""
TASK-149: Market Replay Tool — Historical Tick Data Streamer
Accelerated tick replay simulator for testing live UI and trading engine outside market hours.
"""

import time
import json
import asyncio
from typing import List, Dict, Any, Callable, Optional


class MarketReplayEngine:
    """
    Replays historical tick/candle data at configurable speed multipliers (1x to 100x).
    """
    def __init__(
        self,
        historical_ticks: List[Dict[str, Any]],
        speed_multiplier: float = 10.0
    ):
        self.ticks = historical_ticks
        self.speed_multiplier = max(0.1, float(speed_multiplier))
        self.is_running = False
        self.current_index = 0
        self.replayed_count = 0

    def start_replay(self, callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """Synchronously replay all ticks using speed scaling simulation."""
        self.is_running = True
        self.current_index = 0
        self.replayed_count = 0

        for tick in self.ticks:
            if not self.is_running:
                break
            self.replayed_count += 1
            if callback:
                callback(tick)

        self.is_running = False
        return {
            "status": "COMPLETED",
            "ticks_replayed": self.replayed_count,
            "speed_multiplier": self.speed_multiplier
        }

    async def start_async_replay(self, callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """Asynchronously replay ticks streaming deltas over SSE/WebSocket."""
        self.is_running = True
        for tick in self.ticks:
            if not self.is_running:
                break
            self.replayed_count += 1
            if callback:
                callback(tick)
            # Scaled delay
            await asyncio.sleep(0.01 / self.speed_multiplier)
        self.is_running = False


if __name__ == "__main__":
    sample_ticks = [
        {"symbol": "RELIANCE.NS", "ltp": 2850.0 + i * 0.5, "volume": 1000 + i * 50}
        for i in range(10)
    ]
    engine = MarketReplayEngine(sample_ticks, speed_multiplier=20.0)
    res = engine.start_replay(lambda t: print(f"Replayed: {t['symbol']} @ ₹{t['ltp']}"))
    print("Replay result:", res)
