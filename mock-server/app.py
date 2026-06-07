import json
import os
import threading
from pathlib import Path
from flask import Flask, jsonify, request, abort
try:
    from flask_cors import CORS
except ImportError:
    CORS = None
from engine.sandbox import SandboxEngine
from engine.restaurant_sim import RestaurantSimulator
from engine import llm_gen
from engine.taxi_endpoints import taxi_bp

app = Flask(__name__)
if CORS:
    CORS(app)

# 注册打车模拟 Blueprint
app.register_blueprint(taxi_bp)

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_PATH", "/workspace"))

# ── Restaurant simulators (one per restaurant, created on first take_number) ──
_restaurant_sims: dict[str, RestaurantSimulator] = {}
_sims_lock = threading.Lock()

TICK_INTERVAL = float(os.getenv("TICK_INTERVAL", "3.0"))


def _get_or_create_sim(name: str) -> RestaurantSimulator:
    with _sims_lock:
        if name not in _restaurant_sims:
            profile = llm_gen.generate_profile(name)
            sim = RestaurantSimulator(name, profile)
            sim.start_background(tick_interval=TICK_INTERVAL)
            _restaurant_sims[name] = sim
            print(f"[app] Created simulator for '{name}': {profile.get('personality', '')}")
        return _restaurant_sims[name]


def _load_scenario(name: str) -> list:
    path = SCENARIOS_DIR / f"{name}.json"
    if not path.exists():
        abort(404, f"Scenario '{name}' not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _get_real_weather():
    try:
        from integrations.qweather import get_now_sync
        return get_now_sync()
    except Exception:
        return {"condition": "unknown"}


# Taxi/weather still backed by SandboxEngine
_taxi_weather_script = [
    {
        "index": 0,
        "virtual_time": "18:00",
        "restaurants": {},
        "taxi": {"eta_minutes": 8, "surge": 1.0, "accept_rate": 0.85},
        "weather_overlay": None,
    }
]
sandbox = SandboxEngine(_taxi_weather_script, real_weather_fn=_get_real_weather)


# ── Restaurant endpoints ────────────────────────────────────────────────────

@app.get("/restaurant/<name>/queue")
def restaurant_queue(name: str):
    with _sims_lock:
        sim = _restaurant_sims.get(name)
    if not sim:
        return jsonify({
            "error": f"尚未为「{name}」取号。请先调用 POST /restaurant/{name}/queue/take。"
        }), 404
    return jsonify(sim.state())


@app.post("/restaurant/<name>/queue/take")
def take_queue_number(name: str):
    """
    Take a queue number. Creates the restaurant simulator on first call (triggers LLM).
    Body: { "user_id": str, "party_size": int, "table_type": "small"|"medium"|"large" (optional) }
    """
    body = request.get_json(silent=True) or {}
    user_id    = body.get("user_id", "anonymous")
    party_size = int(body.get("party_size", 2))

    # Auto-detect table type from party_size if not specified
    table_type = body.get("table_type")
    if not table_type:
        if party_size <= 2:
            table_type = "small"
        elif party_size <= 5:
            table_type = "medium"
        else:
            table_type = "large"

    sim = _get_or_create_sim(name)
    try:
        result = sim.take_number(user_id, table_type, party_size)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(result)


@app.get("/restaurant/<name>/queue/<queue_number>")
def queue_number_status(name: str, queue_number: str):
    """Check position of a specific queue number."""
    with _sims_lock:
        sim = _restaurant_sims.get(name)
    if not sim:
        return jsonify({"error": f"No active simulator for '{name}'"}), 404
    status = sim.queue_status(queue_number)
    if status is None:
        return jsonify({"error": f"Queue number '{queue_number}' not found"}), 404
    return jsonify(status)


# ── Notification endpoint ───────────────────────────────────────────────────

@app.post("/notification/queue")
def generate_queue_notification():
    """
    Generate an LLM notification message for a queue update.
    Body: { restaurant, queue_number, table_type_cn, position, estimated_min,
            event_message (opt), user_prefs (opt) }
    """
    body = request.get_json(silent=True) or {}
    required = ["restaurant", "queue_number", "position", "estimated_min"]
    missing = [f for f in required if f not in body]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    try:
        message = llm_gen.generate_notification(
            restaurant=body["restaurant"],
            queue_number=body["queue_number"],
            table_type_cn=body.get("table_type_cn", "桌"),
            position=int(body["position"]),
            estimated_min=int(body["estimated_min"]),
            event_message=body.get("event_message", ""),
            user_prefs=body.get("user_prefs", ""),
        )
        return jsonify({"message": message})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Taxi / Weather endpoints (unchanged, backed by SandboxEngine) ───────────

@app.get("/taxi/estimate")
def taxi_estimate():
    return jsonify(sandbox.state()["taxi"])


@app.get("/weather")
def weather():
    return jsonify(sandbox.state()["weather"])


@app.get("/state")
def full_state():
    state = sandbox.state()
    state.pop("restaurants", None)
    with _sims_lock:
        state["restaurant_sims"] = list(_restaurant_sims.keys())
    return jsonify(state)


# ── Admin endpoints ─────────────────────────────────────────────────────────

@app.post("/admin/start")
def admin_start():
    body = request.get_json(silent=True) or {}
    scenario = body.get("scenario", "haidilao_demo")
    interval  = float(body.get("interval", TICK_INTERVAL))
    try:
        script = _load_scenario(scenario)
    except Exception:
        script = _taxi_weather_script
    sandbox.stop_background()
    sandbox.reset(script)
    sandbox.start_background(tick_interval=interval)
    return jsonify({"ok": True, "scenario": scenario, "interval": interval})


@app.post("/admin/stop")
def admin_stop():
    sandbox.stop_background()
    return jsonify({"ok": True})


@app.post("/admin/set")
def admin_set():
    body = request.get_json()
    if not body or "path" not in body or "value" not in body:
        return jsonify({"error": "需要 path 和 value"}), 400
    sandbox.admin_set(body["path"], body["value"])
    return jsonify({"ok": True, "state": sandbox.state()})


@app.post("/admin/reset")
def admin_reset():
    body = request.get_json(silent=True) or {}
    scenario = body.get("scenario", "haidilao_demo")
    try:
        script = _load_scenario(scenario)
    except Exception:
        script = _taxi_weather_script
    sandbox.reset(script)
    return jsonify({"ok": True, "scenario": scenario})


@app.get("/admin/state")
def admin_state():
    state = sandbox.state()
    with _sims_lock:
        state["restaurant_sims"] = {
            name: sim.state() for name, sim in _restaurant_sims.items()
        }
    return jsonify(state)


@app.get("/admin/scenarios")
def list_scenarios():
    names = [p.stem for p in SCENARIOS_DIR.glob("*.json")] if SCENARIOS_DIR.exists() else []
    return jsonify({"scenarios": names})


@app.post("/admin/restaurant/<name>/start")
def admin_restaurant_start(name: str):
    """Bootstrap/restart a restaurant simulator.
    Body: { interval: float, time_scale: int, drain: bool }
    time_scale: virtual minutes per tick (default 1; use 10-30 for demo speedup)
    drain: true = no new arrivals, queue only drains (demo fast-drain mode)
    """
    body = request.get_json(silent=True) or {}
    interval   = float(body.get("interval",   TICK_INTERVAL))
    time_scale = int(body.get("time_scale",   1))
    drain      = bool(body.get("drain",       False))
    with _sims_lock:
        if name in _restaurant_sims:
            _restaurant_sims[name].stop_background()
            del _restaurant_sims[name]
    sim = _get_or_create_sim(name)
    sim.stop_background()
    sim.start_background(tick_interval=interval, time_scale=time_scale, drain=drain)
    return jsonify({"ok": True, "restaurant": name, "time_scale": time_scale,
                    "drain": drain, "state": sim.state()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)

