import math
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

TABLE_PREFIXES = {"small": "A", "medium": "B", "large": "C"}
TABLE_CN       = {"small": "小桌", "medium": "中桌", "large": "大桌"}


@dataclass
class QueueEntry:
    queue_number: str
    table_type: str
    party_size: int
    user_id: Optional[str]
    taken_at_tick: int
    status: str = "waiting"  # waiting / seated


@dataclass
class _TableState:
    seats: int
    total: int
    avg_dining_min: int
    dining: int = 0
    dining_remaining: list = field(default_factory=list)
    waiting: list = field(default_factory=list)
    number_counter: int = 0

    def next_number(self, prefix: str) -> str:
        self.number_counter += 1
        return f"{prefix}{self.number_counter:03d}"


@dataclass
class _ActiveEvent:
    description: str
    user_message: str
    effects: dict
    remaining_ticks: int


def _poisson(lam: float) -> int:
    if lam <= 0:
        return 0
    L = math.exp(-min(lam, 20))
    k, p = 0, 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1


class RestaurantSimulator:
    def __init__(self, restaurant_name: str, profile: dict):
        self.name = restaurant_name
        self._profile = profile
        self._tick = 0
        self._virtual_minutes = 18 * 60  # start at 18:00
        self._lock = threading.Lock()
        self._running = False
        self._current_event: Optional[_ActiveEvent] = None
        self._last_event_tick = 0

        tt = profile["table_types"]
        self._tables: dict[str, _TableState] = {}
        for k, v in tt.items():
            # 高峰期：所有桌全满，所有就餐者刚入座（dining_remaining 统一为 avg_dining_min）
            init_d = v["total"]
            self._tables[k] = _TableState(
                seats=v["seats"],
                total=v["total"],
                avg_dining_min=v["avg_dining_min"],
                dining=init_d,
                dining_remaining=[v["avg_dining_min"]] * init_d,
            )

        # 高峰期预设排队人数：每种桌型 5-10 组，确保有实际等候
        mix = profile.get("customer_mix", {"small": 0.4, "medium": 0.45, "large": 0.15})
        for ttype, st in self._tables.items():
            count = random.randint(5, 10)
            for _ in range(count):
                st.waiting.append(QueueEntry(
                    queue_number=st.next_number(TABLE_PREFIXES[ttype]),
                    table_type=ttype,
                    party_size=random.randint(1, st.seats),
                    user_id=None,
                    taken_at_tick=0,
                ))

    # ── helpers ────────────────────────────────────────────────────────────

    def _time_str(self) -> str:
        h, m = divmod(self._virtual_minutes % (24 * 60), 60)
        return f"{h:02d}:{m:02d}"

    def _arrival_mult(self) -> float:
        t = self._virtual_minutes % (24 * 60)
        mult = 1.0
        for ph in self._profile.get("peak_hours", []):
            sh, sm = map(int, ph["start"].split(":"))
            eh, em = map(int, ph["end"].split(":"))
            if (sh * 60 + sm) <= t <= (eh * 60 + em):
                mult = max(mult, ph["multiplier"])
        if self._current_event:
            mult *= self._current_event.effects.get("arrival_multiplier", 1.0)
        return mult

    def _estimate_wait(self, ttype: str) -> int:
        st = self._tables[ttype]
        w = sum(1 for e in st.waiting if e.status == "waiting")
        if w == 0:
            return 0
        free = max(1, st.total - st.dining)
        return max(5, int(w / free * st.avg_dining_min))

    # ── simulation tick ─────────────────────────────────────────────────────

    def _advance_tick(self):
        with self._lock:
            scale = getattr(self, "_time_scale", 1)
            drain = getattr(self, "_drain", False)
            self._tick += 1
            self._virtual_minutes += scale

            base_rate = self._profile.get("base_arrival_rate", 8)
            # drain 模式：不来新客人；否则按 scale 倍到客量
            rate_min = 0.0 if drain else base_rate / 60.0 * self._arrival_mult() * scale
            mix = self._profile.get("customer_mix", {"small": 0.4, "medium": 0.45, "large": 0.15})

            extra_groups = {}
            if self._current_event:
                extra_groups = self._current_event.effects.get("extra_groups", {})
                self._current_event.remaining_ticks -= 1
                if self._current_event.remaining_ticks <= 0:
                    self._current_event = None

            for ttype, st in self._tables.items():
                # Arrivals (Poisson)
                n = _poisson(rate_min * mix.get(ttype, 0.33)) + extra_groups.get(ttype, 0)
                for _ in range(n):
                    st.waiting.append(QueueEntry(
                        queue_number=st.next_number(TABLE_PREFIXES[ttype]),
                        table_type=ttype,
                        party_size=random.randint(1, st.seats),
                        user_id=None,
                        taken_at_tick=self._tick,
                    ))

                # Dining completions
                dm = 1.0
                if self._current_event:
                    dm = self._current_event.effects.get(f"{ttype}_dining_multiplier", 1.0)
                new_rem, freed = [], 0
                for mins in st.dining_remaining:
                    eff = mins * dm
                    remaining = max(1, mins - scale)
                    if eff <= scale or random.random() < scale / max(eff, 1):
                        freed += 1
                    else:
                        new_rem.append(remaining)
                st.dining = max(0, st.dining - freed)
                st.dining_remaining = new_rem

                # Seat waiting groups when tables free up
                free = st.total - st.dining
                for entry in st.waiting:
                    if free <= 0:
                        break
                    if entry.status == "waiting":
                        entry.status = "seated"
                        st.dining += 1
                        st.dining_remaining.append(
                            max(10, st.avg_dining_min + random.randint(-10, 15))
                        )
                        free -= 1

                # Trim: keep last 50 seated + all waiting (for status lookups)
                seated  = [e for e in st.waiting if e.status == "seated"][-50:]
                waiting = [e for e in st.waiting if e.status == "waiting"]
                st.waiting = seated + waiting

    # ── public API ─────────────────────────────────────────────────────────

    def take_number(self, user_id: str, table_type: str, party_size: int) -> dict:
        with self._lock:
            if table_type not in self._tables:
                raise ValueError(f"Unknown table type: {table_type}")
            st = self._tables[table_type]
            number = st.next_number(TABLE_PREFIXES[table_type])
            entry = QueueEntry(
                queue_number=number,
                table_type=table_type,
                party_size=party_size,
                user_id=user_id,
                taken_at_tick=self._tick,
            )
            st.waiting.append(entry)
            position = sum(1 for e in st.waiting if e.status == "waiting")
            return {
                "queue_number": number,
                "table_type": table_type,
                "table_type_cn": TABLE_CN.get(table_type, table_type),
                "party_size": party_size,
                "position": position,
                "estimated_min": self._estimate_wait(table_type),
                "virtual_time": self._time_str(),
                "personality": self._profile.get("personality", ""),
                "table_status": self._table_snapshot(),
            }

    def _table_snapshot(self) -> dict:
        """返回当前各桌型的就餐/空闲/等待快照"""
        snap = {}
        for ttype, st in self._tables.items():
            snap[ttype] = {
                "total": st.total,
                "dining": st.dining,
                "free": max(0, st.total - st.dining),
                "waiting": sum(1 for e in st.waiting if e.status == "waiting"),
                "avg_dining_min": st.avg_dining_min,
            }
        return snap

    def queue_status(self, queue_number: str) -> Optional[dict]:
        with self._lock:
            for ttype, st in self._tables.items():
                # Check seated
                for entry in st.waiting:
                    if entry.queue_number == queue_number and entry.status == "seated":
                        return {
                            "queue_number": queue_number,
                            "table_type": ttype,
                            "table_type_cn": TABLE_CN.get(ttype, ttype),
                            "position": 0,
                            "estimated_min": 0,
                            "status": "seated",
                            "virtual_time": self._time_str(),
                            "current_event": None,
                            "table_status": self._table_snapshot(),
                        }
                # Check waiting
                waiting_list = [e for e in st.waiting if e.status == "waiting"]
                for i, entry in enumerate(waiting_list):
                    if entry.queue_number == queue_number:
                        return {
                            "queue_number": queue_number,
                            "table_type": ttype,
                            "table_type_cn": TABLE_CN.get(ttype, ttype),
                            "position": i + 1,
                            "estimated_min": self._estimate_wait(ttype),
                            "status": "waiting",
                            "virtual_time": self._time_str(),
                            "current_event": (
                                self._current_event.user_message if self._current_event else None
                            ),
                            "table_status": self._table_snapshot(),
                        }
            return None

    def state(self) -> dict:
        with self._lock:
            result = {
                "restaurant": self.name,
                "virtual_time": self._time_str(),
                "table_types": {},
                "current_event": None,
            }
            total_waiting, max_est = 0, 0
            for ttype, st in self._tables.items():
                w   = sum(1 for e in st.waiting if e.status == "waiting")
                est = self._estimate_wait(ttype)
                total_waiting += w
                max_est = max(max_est, est)
                result["table_types"][ttype] = {
                    "seats": st.seats,
                    "total_tables": st.total,
                    "waiting": w,
                    "dining": st.dining,
                    "estimated_min": est,
                }
            # Backward-compat fields for existing restaurant_monitor.js
            result["waiting"]       = total_waiting
            result["estimated_min"] = max_est
            if self._current_event:
                result["current_event"] = {
                    "message": self._current_event.user_message,
                    "remaining_ticks": self._current_event.remaining_ticks,
                }
            return result

    def apply_event(self, event: dict):
        with self._lock:
            self._current_event = _ActiveEvent(
                description=event.get("description", ""),
                user_message=event.get("user_message", ""),
                effects=event.get("effects", {}),
                remaining_ticks=event.get("duration_ticks", 3),
            )

    def start_background(self, tick_interval: float = 3.0, time_scale: int = 1, drain: bool = False):
        """
        tick_interval: 每个 tick 的真实秒数
        time_scale:    每个 tick 推进几分钟虚拟时间（默认1，演示时可设10~30）
        drain:         True = 不产生新客人，队列只出不进，适合演示快速清队
        """
        self._time_scale = max(1, int(time_scale))
        self._drain = drain
        self._running = True
        threading.Thread(target=self._run_loop, args=(tick_interval,), daemon=True).start()

    def stop_background(self):
        self._running = False

    def _run_loop(self, interval: float):
        from . import llm_gen
        while self._running:
            time.sleep(interval)
            self._advance_tick()
            if self._tick - self._last_event_tick >= random.randint(10, 15):
                try:
                    s = self.state()
                    ev = llm_gen.generate_event(self.name, s["virtual_time"], s["table_types"])
                    self.apply_event(ev)
                    self._last_event_tick = self._tick
                except Exception as e:
                    print(f"[restaurant_sim] event gen failed: {e}")
