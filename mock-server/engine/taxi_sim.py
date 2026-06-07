"""
taxi_sim.py — 打车模拟引擎

模拟完整的打车流程：
  1. 预估价格（返回车型、价格）
  2. 司机接单（生成司机信息）
  3. 司机前往起点（ETA 实时变化）
  4. 司机到达起点
  5. 行程中（位置更新）
  6. 到达终点

支持注入真实数据模式：
  - 传入 real_data（来自官方 DiDi skill 的 taxi_estimate 结果）
  - 使用真实距离/时长/价格，绕过模拟计算
"""

import threading
import time
import random
import math
from datetime import datetime

# 模拟司机数据
DRIVERS = [
    {"name": "张师傅", "phone": "138****5678", "car_plate": "粤B·12345", "color": "白色", "car_model": "丰田卡罗拉"},
    {"name": "李师傅", "phone": "139****9012", "car_plate": "粤B·67890", "color": "银色", "car_model": "大众朗逸"},
    {"name": "王师傅", "phone": "137****3456", "car_plate": "粤B·24680", "color": "黑色", "car_model": "比亚迪秦"},
    {"name": "陈师傅", "phone": "136****7890", "car_plate": "粤B·13579", "color": "白色", "car_model": "日产轩逸"},
    {"name": "刘师傅", "phone": "135****2345", "car_plate": "粤B·97531", "color": "红色", "car_model": "本田思域"},
]

PRODUCT_TYPES = [
    {"id": 1, "name": "快车", "base_price": 10, "per_km": 2.4, "per_min": 0.5},
    {"id": 2, "name": "专车", "base_price": 18, "per_km": 3.8, "per_min": 0.8},
    {"id": 3, "name": "优享", "base_price": 14, "per_km": 3.0, "per_min": 0.6},
]


class TaxiSimulator:
    """打车全流程模拟器"""

    def __init__(self, origin_name="深圳北站", dest_name="南坑站",
                 origin_lat=22.608443, origin_lng=114.025796,
                 dest_lat=22.610894, dest_lng=114.060546,
                 real_data=None):
        """
        real_data: 来自官方 DiDi skill（taxi_estimate）的真实数据（可选）
            格式：
            {
                "distance_km": 8.5,
                "duration_min": 20,
                "items": [
                    {"productName": "快车", "productCategory": 1, "priceText": "25.5"},
                    ...
                ],
                "traceId": "xxx"
            }
        """
        self.origin_name = origin_name
        self.dest_name = dest_name
        self.origin_lat = origin_lat
        self.origin_lng = origin_lng
        self.dest_lat = dest_lat
        self.dest_lng = dest_lng

        self._real_data = real_data
        if real_data:
            self.distance_km = float(real_data.get("distance_km", 0))
            self.duration_min = int(real_data.get("duration_min", 0))
            self._real_items = real_data.get("items", [])
            self._real_trace_id = real_data.get("traceId", "")
        else:
            self.distance_km = self._calc_distance() * 1.3
            self.duration_min = max(5, int(self.distance_km / 25 * 60))
            self._real_items = []
            self._real_trace_id = ""

        self.status = "idle"
        self.driver = None
        self.order_id = None
        self.trace_id = None
        self.product = None
        self.price = 0
        self.surge = 1.0
        self.driver_lat = origin_lat + random.uniform(-0.02, 0.02)
        self.driver_lng = origin_lng + random.uniform(-0.02, 0.02)
        self.eta_min = random.randint(3, 8)
        self.elapsed_min = 0
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def _calc_distance(self):
        R = 6371
        dlat = math.radians(self.dest_lat - self.origin_lat)
        dlng = math.radians(self.dest_lng - self.origin_lng)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(self.origin_lat)) * math.cos(math.radians(self.dest_lat)) * math.sin(dlng/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    def _extract_price(self, price_text):
        return float("".join(c for c in str(price_text) if c.isdigit() or c == "."))

    def _real_price_by_category(self, category):
        for item in self._real_items:
            cat = item.get("productCategory")
            if cat is not None and int(cat) == category:
                return self._extract_price(item.get("priceText", "0"))
        return None

    def _calc_price(self, product):
        rp = self._real_price_by_category(product["id"])
        if rp is not None:
            return round(rp, 1)
        price = product["base_price"] + product["per_km"] * self.distance_km + product["per_min"] * self.duration_min
        price *= self.surge
        return round(price, 1)

    def estimate(self, product_id=None):
        self.status = "estimated"
        self.trace_id = self._real_trace_id or f"trace_{int(time.time())}_{random.randint(1000, 9999)}"
        self.surge = round(random.uniform(1.0, 2.0), 1)

        if self._real_items:
            # 有真实数据：直接用 DiDi API 返回的车型列表
            products = []
            for item in self._real_items:
                cat = item.get("productCategory")
                if product_id and cat != product_id:
                    continue
                products.append({
                    "product_category": cat,
                    "product_name": item.get("productName", "未知"),
                    "total_price": self._extract_price(item.get("priceText", "0")),
                    "base_price": 0,
                    "distance_km": round(self.distance_km, 1),
                    "duration_min": self.duration_min,
                    "price_source": "real",
                })
        else:
            # 没有真实数据：用硬编码的 PRODUCT_TYPES
            products = []
            for p in PRODUCT_TYPES:
                if product_id and p["id"] != product_id:
                    continue
                products.append({
                    "product_category": p["id"],
                    "product_name": p["name"],
                    "total_price": self._calc_price(p),
                    "base_price": p["base_price"],
                    "distance_km": round(self.distance_km, 1),
                    "duration_min": self.duration_min,
                    "price_source": "simulated",
                })

        return {
            "traceId": self.trace_id,
            "origin": self.origin_name,
            "destination": self.dest_name,
            "distance_km": round(self.distance_km, 1),
            "surge": self.surge,
            "product_list": products,
        }

    def create_order(self, product_category=1):
        rp = self._real_price_by_category(product_category)
        if rp is not None:
            # 从真实数据中找车型名
            name = f"品类{product_category}"
            for item in self._real_items:
                cat = item.get("productCategory")
                if cat is not None and int(cat) == product_category:
                    name = item.get("productName", name)
                    break
            self.product = {"id": product_category, "name": name}
            self.price = rp
        else:
            self.product = next((p for p in PRODUCT_TYPES if p["id"] == product_category),
                                {"id": product_category, "name": f"品类{product_category}"})
            self.price = self._calc_price(self.product)

        self.order_id = f"MOCK{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(100, 999)}"
        self.driver = random.choice(DRIVERS)
        self.status = "driver_assigned"

        return {
            "order_id": self.order_id,
            "status": "pending",
            "driver": {
                "name": self.driver["name"],
                "phone": self.driver["phone"],
                "car_plate": self.driver["car_plate"],
                "color": self.driver["color"],
                "car_model": self.driver["car_model"],
                "lat": round(self.driver_lat, 6),
                "lng": round(self.driver_lng, 6),
            },
            "eta_min": self.eta_min,
            "estimated_price": self.price,
            "product_name": self.product["name"],
            "price_source": "real" if rp else "simulated",
        }

    def query_order(self):
        with self._lock:
            if not self.order_id:
                return {"error": "无进行中的订单"}
            driver_info = None
            if self.driver:
                driver_info = {
                    "name": self.driver["name"],
                    "phone": self.driver["phone"],
                    "car_plate": self.driver["car_plate"],
                    "color": self.driver["color"],
                    "car_model": self.driver["car_model"],
                    "lat": round(self.driver_lat, 6),
                    "lng": round(self.driver_lng, 6),
                }
            return {
                "order_id": self.order_id,
                "status": self.status,
                "driver": driver_info,
                "eta_min": self.eta_min,
                "elapsed_min": self.elapsed_min if self.status == "driving" else 0,
                "origin": self.origin_name,
                "destination": self.dest_name,
                "estimated_price": self.price,
            }

    def cancel_order(self):
        with self._lock:
            self.status = "cancelled"
            self.driver = None
        return {
            "order_id": self.order_id,
            "status": "cancelled",
            "message": f"订单 {self.order_id} 已取消",
        }

    def start(self, tick_interval=5):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, args=(tick_interval,), daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run_loop(self, interval):
        tick_count = 0
        while self._running:
            time.sleep(interval)
            tick_count += 1
            with self._lock:
                self._tick(tick_count, interval)

    def _tick(self, tick_count, interval=None):
        if interval is None:
            interval = 5
        if self.status == "driver_assigned":
            self.eta_min = max(1, self.eta_min - 1)
            self.driver_lat += (self.origin_lat - self.driver_lat) * 0.2
            self.driver_lng += (self.origin_lng - self.driver_lng) * 0.2
            if self.eta_min <= 1:
                self.status = "arrived"
                self.eta_min = 0
        elif self.status == "arrived":
            if tick_count % 2 == 0:
                self.status = "driving"
                self.eta_min = self.duration_min
        elif self.status == "driving":
            self.elapsed_min += int(interval) / 60 * 2
            self.eta_min = max(1, self.duration_min - int(self.elapsed_min))
            progress = min(1, self.elapsed_min / self.duration_min) if self.duration_min > 0 else 0
            self.driver_lat = self.origin_lat + (self.dest_lat - self.origin_lat) * progress
            self.driver_lng = self.origin_lng + (self.dest_lng - self.origin_lng) * progress
            if self.eta_min <= 1:
                self.status = "completed"
                self.eta_min = 0
        elif self.status in ("completed", "cancelled", "idle"):
            pass
