import time, threading
from engine.models import Tick, Watcher
from engine.sandbox import SandboxEngine

SCRIPT = [
    {"index": 0, "virtual_time": "18:00",
     "restaurants": {"海底捞福田": {"waiting": 8, "estimated_min": 45}},
     "taxi": {"eta_minutes": 8, "surge": 1.0}, "weather_overlay": None},
    {"index": 1, "virtual_time": "18:05",
     "restaurants": {"海底捞福田": {"waiting": 5, "estimated_min": 25}},
     "taxi": {"eta_minutes": 10, "surge": 1.2}, "weather_overlay": None},
    {"index": 2, "virtual_time": "18:10",
     "restaurants": {"海底捞福田": {"waiting": 2, "estimated_min": 10}},
     "taxi": {"eta_minutes": 12, "surge": 1.5},
     "weather_overlay": {"condition": "light_rain", "warning": "暴雨预警"}},
]

def test_get_state():
    sb = SandboxEngine(SCRIPT)
    state = sb.state()
    assert state["restaurants"]["海底捞福田"]["waiting"] == 8
    assert state["virtual_time"] == "18:00"

def test_advance():
    sb = SandboxEngine(SCRIPT)
    sb.advance()
    assert sb.state()["restaurants"]["海底捞福田"]["waiting"] == 5

def test_watcher_fires():
    sb = SandboxEngine(SCRIPT)
    fired = []
    sb.register_watcher("restaurants.海底捞福田.waiting", "<=", 5,
                         lambda uid, path, val, s: fired.append(val), "u1")
    sb.advance()  # waiting goes to 5 → fires
    time.sleep(0.1)  # wait for thread callback
    assert len(fired) == 1
    assert fired[0] == 5

def test_watcher_fires_once():
    sb = SandboxEngine(SCRIPT)
    fired = []
    sb.register_watcher("restaurants.海底捞福田.waiting", "<=", 5,
                         lambda uid, path, val, s: fired.append(val), "u1")
    sb.advance()  # fires
    time.sleep(0.1)
    sb.advance()  # should NOT fire again
    time.sleep(0.1)
    assert len(fired) == 1

def test_weather_overlay():
    sb = SandboxEngine(SCRIPT)
    sb.advance(); sb.advance()  # go to index 2
    state = sb.state()
    assert state["weather"]["condition"] == "light_rain"

def test_weather_real_fn():
    sb = SandboxEngine(SCRIPT, real_weather_fn=lambda: {"condition": "sunny"})
    state = sb.state()  # index 0 has overlay=None → use real fn
    assert state["weather"]["condition"] == "sunny"

def test_admin_set():
    sb = SandboxEngine(SCRIPT)
    sb.admin_set("restaurants.海底捞福田.waiting", 3)
    assert sb.state()["restaurants"]["海底捞福田"]["waiting"] == 3

def test_reset():
    sb = SandboxEngine(SCRIPT)
    sb.advance()
    sb.reset(SCRIPT)
    assert sb.state()["virtual_time"] == "18:00"

if __name__ == "__main__":
    for fn in [test_get_state, test_advance, test_watcher_fires,
               test_watcher_fires_once, test_weather_overlay,
               test_weather_real_fn, test_admin_set, test_reset]:
        fn()
        print(f"[PASS] {fn.__name__}")
    print("All tests passed!")
