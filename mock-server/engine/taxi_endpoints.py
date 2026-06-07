"""
taxi_endpoints.py — 打车模拟 Flask Blueprint

支持注入真实价格（来自官方 DiDi skill 的 taxi_estimate）
需要由 app.py 导入并注册 blueprint。
"""

import threading
import json
from flask import Blueprint, jsonify, request
from engine.taxi_sim import TaxiSimulator

taxi_bp = Blueprint('taxi', __name__)

_taxi_sim = None
_taxi_sim_lock = threading.Lock()


@taxi_bp.route('/taxi/start', methods=['POST'])
def taxi_start():
    global _taxi_sim
    body = request.get_json(silent=True) or {}

    sim = TaxiSimulator(
        origin_name=body.get('origin', '深圳北站'),
        dest_name=body.get('destination', '南坑站'),
        origin_lat=float(body.get('origin_lat', 22.608443)),
        origin_lng=float(body.get('origin_lng', 114.025796)),
        dest_lat=float(body.get('dest_lat', 22.610894)),
        dest_lng=float(body.get('dest_lng', 114.060546)),
        real_data=body.get('real_data'),
    )

    with _taxi_sim_lock:
        if _taxi_sim:
            _taxi_sim.stop()
        _taxi_sim = sim

    estimate = sim.estimate()
    sim.start(tick_interval=5)

    return jsonify({
        'ok': True,
        'message': f"打车模拟已启动: {body.get('origin', '?')} -> {body.get('destination', '?')}",
        'estimate': estimate,
    })


@taxi_bp.route('/taxi/scenario', methods=['POST'])
def taxi_scenario():
    global _taxi_sim
    body = request.get_json(silent=True) or {}

    sim = TaxiSimulator(
        origin_name=body.get('origin', '深圳北站'),
        dest_name=body.get('destination', '南坑站'),
        origin_lat=float(body.get('origin_lat', 22.608443)),
        origin_lng=float(body.get('origin_lng', 114.025796)),
        dest_lat=float(body.get('dest_lat', 22.610894)),
        dest_lng=float(body.get('dest_lng', 114.060546)),
        real_data=body.get('real_data'),
    )

    with _taxi_sim_lock:
        if _taxi_sim:
            _taxi_sim.stop()
        _taxi_sim = sim

    estimate = sim.estimate()
    product_id = int(body.get('product_category', 1))
    order = sim.create_order(product_category=product_id)
    sim.start(tick_interval=5)

    return jsonify({
        'ok': True,
        'estimate': estimate,
        'order': order,
        'message': f"司机 {order['driver']['name']} 已接单，预计 {order['eta_min']} 分钟到达",
    })


@taxi_bp.route('/taxi/order', methods=['POST'])
def create_order():
    global _taxi_sim
    body = request.get_json(silent=True) or {}
    product_id = int(body.get('product_category', 1))
    with _taxi_sim_lock:
        if not _taxi_sim:
            return jsonify({'error': '请先调 /taxi/start 启动模拟'}), 400
        result = _taxi_sim.create_order(product_category=product_id)
    return jsonify(result)


@taxi_bp.route('/taxi/order', methods=['GET'])
def query_order():
    global _taxi_sim
    with _taxi_sim_lock:
        if not _taxi_sim:
            return jsonify({'error': '无进行中的订单'}), 404
        result = _taxi_sim.query_order()
    return jsonify(result)


@taxi_bp.route('/taxi/order', methods=['DELETE'])
def cancel_order():
    global _taxi_sim
    with _taxi_sim_lock:
        if not _taxi_sim:
            return jsonify({'error': '无进行中的订单'}), 404
        result = _taxi_sim.cancel_order()
        _taxi_sim = None
    return jsonify(result)


@taxi_bp.route('/taxi/driver', methods=['GET'])
def driver_location():
    global _taxi_sim
    with _taxi_sim_lock:
        if not _taxi_sim:
            return jsonify({'error': '无进行中的行程'}), 404
        state = _taxi_sim.query_order()
    return jsonify({
        'order_id': state.get('order_id'),
        'status': state.get('status'),
        'driver': state.get('driver'),
        'eta_min': state.get('eta_min'),
    })


@taxi_bp.route('/taxi/simulate', methods=['POST'])
def advance():
    global _taxi_sim
    body = request.get_json(silent=True) or {}
    steps = int(body.get('steps', 5))
    with _taxi_sim_lock:
        if not _taxi_sim:
            return jsonify({'error': '请先调 /taxi/start 启动模拟'}), 400
        for _ in range(steps):
            _taxi_sim._tick(0)
        result = _taxi_sim.query_order()
    return jsonify(result)
