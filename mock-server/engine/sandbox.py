import threading
from typing import Any, Callable, List, Optional
from .models import Tick, Watcher


class SandboxEngine:
    def __init__(self, script: List[dict], real_weather_fn: Callable = None):
        self._ticks: List[Tick] = [Tick(**t) for t in script]
        self._current: int = 0
        self._watchers: List[Watcher] = []
        self._real_weather_fn = real_weather_fn
        self._lock = threading.Lock()
        self._running = False

    def state(self) -> dict:
        with self._lock:
            return self._state_unlocked()

    def _state_unlocked(self) -> dict:
        t = self._ticks[self._current]
        overlay = t.weather_overlay
        if overlay:
            weather = overlay
        elif self._real_weather_fn:
            weather = self._real_weather_fn()
        else:
            weather = {}
        return {
            "index": t.index,
            "virtual_time": t.virtual_time,
            "restaurants": t.restaurants,
            "taxi": t.taxi,
            "weather": weather,
        }

    def _get_by_path(self, path: str) -> Any:
        parts = path.split(".")
        val = self._state_unlocked()
        for p in parts:
            val = val[p]
        return val

    def advance(self) -> bool:
        with self._lock:
            if self._current >= len(self._ticks) - 1:
                return False
            self._current += 1
            self._check_watchers_unlocked()
            return True

    def start_background(self, tick_interval: float = 3.0):
        self._running = True
        t = threading.Thread(
            target=self._run_loop, args=(tick_interval,), daemon=True
        )
        t.start()

    def stop_background(self):
        self._running = False

    def _run_loop(self, interval: float):
        import time
        while self._running:
            time.sleep(interval)
            if not self.advance():
                self._running = False

    def register_watcher(self, entity_path: str, operator: str,
                          threshold: Any, callback: Callable, user_id: str):
        with self._lock:
            self._watchers.append(
                Watcher(entity_path, operator, threshold, callback, user_id)
            )

    def remove_watchers(self, user_id: str):
        with self._lock:
            self._watchers = [w for w in self._watchers if w.user_id != user_id]

    def _check_watchers_unlocked(self):
        for w in self._watchers:
            if w.fired:
                continue
            try:
                val = self._get_by_path(w.entity_path)
            except (KeyError, TypeError):
                continue
            hit = (
                (w.operator == "<=" and val <= w.threshold) or
                (w.operator == ">=" and val >= w.threshold) or
                (w.operator == "==" and val == w.threshold)
            )
            if hit:
                w.fired = True
                state_snapshot = self._state_unlocked()
                threading.Thread(
                    target=w.callback,
                    args=(w.user_id, w.entity_path, val, state_snapshot),
                    daemon=True,
                ).start()

    def admin_set(self, path: str, value: Any):
        with self._lock:
            parts = path.split(".")
            # Get the top-level field from the Tick dataclass
            t = self._ticks[self._current]
            # Navigate: first part is a Tick field, rest are dict keys
            obj = getattr(t, parts[0])
            for p in parts[1:-1]:
                obj = obj[p]
            obj[parts[-1]] = value
            self._check_watchers_unlocked()

    def reset(self, script: List[dict]):
        with self._lock:
            self._ticks = [Tick(**t) for t in script]
            self._current = 0
            self._watchers = []
            self._running = False
