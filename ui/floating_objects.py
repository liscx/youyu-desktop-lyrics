# -*- coding: utf-8 -*-
"""通用飞行物系统：素材外观 + 统一运动引擎。

设计原则：
  1. 素材只画自己（draw_material），运动逻辑完全共用（FlyingObject.step）。
  2. 四个触发场景各自一个粒子池，配置独立，互不覆盖。
  3. 对象池 + 一次性粒子回收，避免高频创建/销毁，长时间运行内存恒定。
  4. 引擎只管粒子；文字的逐字消散 alpha 仍由 EffectEngine 负责。
"""
import math
import os
import random

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from core.floating_config import (
    TIER_COUNT, TIER_SPEED, TIER_DEVIATION, TIER_ROTATION,
    MATERIALS, SCENE_IDS, materials_dir,
)


# ---------------------------------------------------------------------------
# 素材绘制：统一 SVG 渲染（矢量缩放无损，与大小拖条/实时示例共用同一公式）
#
# SVG 自带配色，绘制时不再用主题色染色，只把 color 的 alpha 当不透明度用。
# 渲染结果按 (素材, 尺寸) 缓存成 QPixmap，逐帧只做缩放贴图，避免重复解析矢量。
# ---------------------------------------------------------------------------
_SVG_CACHE = {}   # material_id -> QSvgRenderer（解析一次）
_PIX_CACHE = {}   # (material_id, size_px) -> QPixmap（同尺寸复用）
_PIX_CACHE_MAX = 512


def _svg_renderer(material_id):
    r = _SVG_CACHE.get(material_id)
    if r is None:
        meta = MATERIALS.get(material_id, {})
        path = os.path.join(materials_dir(), meta.get("svg", "glow.svg"))
        r = QSvgRenderer(path)
        _SVG_CACHE[material_id] = r
    return r


def _svg_pixmap(material_id, size_px):
    key = (material_id, size_px)
    pm = _PIX_CACHE.get(key)
    if pm is not None:
        return pm
    r = _svg_renderer(material_id)
    if not r.isValid():
        return None
    pm = QPixmap(size_px, size_px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r.render(p, QRectF(0, 0, size_px, size_px))
    p.end()
    if len(_PIX_CACHE) >= _PIX_CACHE_MAX:
        _PIX_CACHE.clear()
    _PIX_CACHE[key] = pm
    return pm


def draw_material(painter, s, c, material_id):
    """按素材 id 绘制 SVG：缩放到 2s×2s 方框，居中于原点。

    s 为半高（沿用旧手绘约定，与 SizeSlider/SizePreview 的公式一致）。
    c 只取 alpha 作为不透明度；SVG 自身配色保留。
    """
    size_px = max(2, int(round(s * 2)))
    pm = _svg_pixmap(material_id, size_px)
    if pm is None:
        return
    painter.save()
    painter.setOpacity(max(0.0, min(1.0, c.alpha() / 255.0)))
    painter.drawPixmap(QRectF(-s, -s, s * 2, s * 2), pm, QRectF(0, 0, size_px, size_px))
    painter.restore()


def _make_drawer(material_id):
    def drawer(painter, s, c):
        draw_material(painter, s, c, material_id)
    drawer.__name__ = f"draw_{material_id}"
    return drawer


MATERIAL_DRAW = {mid: _make_drawer(mid) for mid in MATERIALS}


# ---------------------------------------------------------------------------
# 单个飞行物：运动状态 + 绘制，素材无关
# ---------------------------------------------------------------------------
class FlyingObject:
    __slots__ = ("x", "y", "vx", "vy", "size", "angle", "spin", "alpha",
                 "life", "max_life", "delay", "material", "depth", "color",
                 "phase", "no_respawn", "base_speed")

    def __init__(self, material, color):
        self.material = material
        self.color = color
        self.phase = random.uniform(0, 2 * math.pi)  # 飘摆相位，让同类不同步
        self.reset(100, 100, None)

    def reset(self, w, h, scene):
        self.x = random.uniform(0, max(1, w))
        self.y = random.uniform(0, max(1, h))
        self.vx = self.vy = 0.0
        self.size = 8
        self.angle = random.uniform(0, 360)
        self.spin = 0.0
        self.alpha = 150
        self.life = 0.0
        self.max_life = 4000
        self.delay = 0.0
        self.depth = 1.0
        self.base_speed = 0.1
        self.no_respawn = bool(scene and scene.get("_one_shot", False))

    def step(self, dt, w, h, area):
        if self.delay > 0:
            self.delay -= dt
            return
        self.life += dt
        self.x += (self.vx + math.sin(self.life / 900.0 + self.phase) * 0.12) * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt
        ax, ay, aw, ah = area
        left, top, right, bottom = ax * w, ay * h, (ax + aw) * w, (ay + ah) * h
        if self.no_respawn:
            # 一次性粒子：飞出活动区或寿命到就标记死亡
            if self.life >= self.max_life or not (left - 40 <= self.x <= right + 40
                                                   and top - 40 <= self.y <= bottom + 40):
                self.life = self.max_life
        else:
            # 常驻粒子：出界后从对侧回绕，保持在活动范围内
            if self.x < left:
                self.x = right
            elif self.x > right:
                self.x = left
            if self.y < top:
                self.y = bottom
            elif self.y > bottom:
                self.y = top
            # 生命周期走完则重置，让 fade() 淡入淡出循环（否则常驻粒子会一直透明）
            if self.life >= self.max_life:
                self.life = 0

    def fade(self):
        t = self.life / max(1, self.max_life)
        if t < 0.12:
            return t / 0.12
        if t > 0.75:
            return (1 - t) / 0.25
        return 1.0

    def draw(self, painter, color):
        f = self.fade()
        if f <= 0:
            return
        c = QColor(color if color else self.color)
        c.setAlpha(int(self.alpha * f * (0.5 if self.depth > 0.5 else 1.0)))
        drawer = MATERIAL_DRAW.get(self.material) or MATERIAL_DRAW["glow"]
        meta = MATERIALS.get(self.material, {"base": 10})
        # 远景(depth>0.5)按 0.6 倍缩，恢复 git 版的近/远景层次感
        depth_scale = 0.6 if self.depth > 0.5 else 1.0
        s = self.size * meta["base"] / 10.0 * depth_scale
        painter.save()
        painter.translate(self.x, self.y)
        painter.rotate(self.angle)
        drawer(painter, s, c)
        painter.restore()


# ---------------------------------------------------------------------------
# 统一引擎：场景对象池 + 生成规则 + 生命周期
# ---------------------------------------------------------------------------
class FloatingEngine:
    FPS_AREA = 1.0

    def __init__(self, floating):
        self.floating = floating
        self.color = "#DCE6F1"       # 由主题注入
        self.w = 100
        self.h = 100
        self._pools = {sid: [] for sid in SCENE_IDS}
        self._rain_pool = []
        self.legacy_rain = floating.get("legacy_rain", {"enabled": False})
        self.configure(floating)

    # ---------------- 配置 ----------------
    def configure(self, floating):
        self.floating = floating
        self.legacy_rain = floating.get("legacy_rain", {"enabled": False, "count": "few"})

    def set_color(self, color):
        self.color = color

    def resize(self, w, h):
        self.w, self.h = w, h

    def scene(self, sid):
        return self.floating["scenes"].get(sid)

    def _enabled(self, sid):
        s = self.scene(sid)
        return bool(s and s.get("enabled"))

    def _sync_pool(self, pool, count, material, scene=None):
        """增量补齐/收缩池，不整体重建。"""
        while len(pool) < count:
            obj = FlyingObject(material, self.color)
            obj.reset(self.w, self.h, scene)
            pool.append(obj)
        if len(pool) > count:
            del pool[count:]
        # 素材被改：就地切换
        for o in pool:
            if o.material != material:
                o.material = material
                o.reset(self.w, self.h, scene)

    # ---------------- 生成参数 ----------------
    def _apply_motion(self, obj, scene, refresh_angle=True):
        """只翻译运动参数，不碰生命周期——ambient 每帧调用也不会重置动画。"""
        dx, dy = scene["direction"]
        base = TIER_SPEED[scene["speed"]]
        # 同场景内轻微速度差异，让整体更自然（用相位做稳定扰动，避免每帧抖动）
        speed = base * (0.85 + 0.3 * (0.5 + 0.5 * math.sin(obj.phase * 3.1)))
        if scene.get("random_deviation"):
            max_dev = TIER_DEVIATION[scene["deviation"]]
            # 每个粒子的偏转量由自身相位决定，稳定不抖动
            ang = max_dev * math.sin(obj.phase * 2.3)
            ca, sa = math.cos(ang), math.sin(ang)
            ndx, ndy = dx * ca - dy * sa, dx * sa + dy * ca
        else:
            ndx, ndy = dx, dy
        obj.vx, obj.vy = ndx * speed, ndy * speed
        obj.base_speed = speed

        sz = max(0.3, min(2.5, float(scene.get("size", 1.0))))
        if scene.get("random_size"):
            sz *= 0.7 + 0.65 * (0.5 + 0.5 * math.sin(obj.phase * 5.7))
        obj.size = sz * 10

        if scene.get("random_rotation"):
            obj.spin = TIER_ROTATION[scene["rotation_speed"]] * 1000 * math.sin(obj.phase * 1.7)
            if refresh_angle:
                obj.angle = random.uniform(0, 360)
        else:
            obj.spin = 0.0
            if refresh_angle:
                obj.angle = 0.0
        obj.material = scene["material"]

    def _apply_scene_to_object(self, obj, scene, origin=None):
        """一次性粒子：运动参数 + 重置生命周期。"""
        self._apply_motion(obj, scene)
        obj.alpha = random.randint(110, 190)
        obj.phase = random.uniform(0, 2 * math.pi)
        obj.depth = 1.0
        obj.life = 0.0
        obj.delay = 0.0
        if origin is not None:
            ox, oy = origin
            obj.x = ox + random.uniform(-6, 6)
            obj.y = oy + random.uniform(-6, 6)
            obj.max_life = random.uniform(1200, 2600)
            obj.no_respawn = True

    # ---------------- 场景触发 ----------------
    def burst(self, sid, origins=None, count_override=None):
        """一次性触发：入场/消失/切换。origins 为 [(x,y), ...] 发射点。"""
        if not self._enabled(sid):
            return
        scene = self.scene(sid)
        n = count_override if count_override is not None else TIER_COUNT[scene["count"]]
        # 逐字消散：每个字附近生成少量；整行场景则按总数均摊
        if origins:
            per = max(1, n // max(1, len(origins)))
            points = [(o, per) for o in origins]
        else:
            points = [((self.w * 0.5, self.h * 0.5), n)]
        pool = self._pools.setdefault(sid, [])
        for (ox, oy), k in points:
            for _ in range(k):
                obj = FlyingObject(scene["material"], self.color)
                self._apply_scene_to_object(obj, scene, origin=(ox, oy))
                pool.append(obj)
        self._trim(pool, sid)

    def _trim(self, pool, sid):
        scene = self.scene(sid)
        cap = max(40, TIER_COUNT[scene["count"]] * 4)
        if len(pool) > cap:
            del pool[:len(pool) - cap]

    # ---------------- 每帧推进 ----------------
    def tick(self, dt):
        dt = min(dt, 100)
        w, h = self.w, self.h

        # ambient：常驻池，数量由挡位决定，活动范围约束
        ambient = self.scene("ambient")
        pool = self._pools["ambient"]
        if self._enabled("ambient"):
            count = TIER_COUNT[ambient["count"]]
            self._sync_pool(pool, count, ambient["material"], None)
            area = ambient.get("area", [0, 0, 1, 1])
            for o in pool:
                self._apply_motion(o, ambient, refresh_angle=False)
                o.no_respawn = False
                o.depth = 0.6 if o.material in ("sakura", "petal", "snow", "maple") else 1.0
                o.max_life = random.uniform(2600, 5200)  # 有限寿命，fade 淡入淡出循环
                o.step(dt, w, h, area)
        else:
            pool.clear()

        # 其它场景：一次性粒子推进 + 回收
        for sid in ("enter", "exit", "switch"):
            scene = self.scene(sid)
            p = self._pools[sid]
            if not self._enabled(sid):
                p.clear()
                continue
            alive = []
            for o in p:
                o.step(dt, w, h, [0, 0, 1, 1])
                if o.life < o.max_life:
                    alive.append(o)
            self._pools[sid] = alive

        # 旧雨滴（忧郁主题迁移）：作为 rain 素材的一个常驻池
        if self.legacy_rain.get("enabled"):
            rc = TIER_COUNT.get(self.legacy_rain.get("count", "few"), 4)
            self._sync_pool(self._rain_pool, rc, "rain", None)
            for o in self._rain_pool:
                if o.material != "rain":
                    o.material = "rain"
                o.vx, o.vy = -0.04, TIER_SPEED["fast"]
                o.size = 9
                o.angle = -12
                o.spin = 0
                o.alpha = 90
                o.depth = 1.0
                o.no_respawn = False
                o.max_life = random.uniform(2600, 5200)
                o.step(dt, w, h, [0, 0, 1, 1])
        else:
            self._rain_pool.clear()

    # ---------------- 绘制 ----------------
    def draw(self, painter, layer="foreground"):
        """layer: background=远景/雨丝(文字下层), foreground=其余(文字上层)。"""
        # 雨丝画在背景层
        if layer == "background":
            color = self.legacy_rain.get("color", self.color)
            for o in self._rain_pool:
                o.draw(painter, color)
            for o in self._pools["ambient"]:
                if o.depth > 0.5:  # 远景素材
                    o.draw(painter, self.color)
            return

        for sid in ("ambient", "enter", "exit", "switch"):
            if not self._enabled(sid):
                continue
            for o in self._pools[sid]:
                if sid == "ambient" and o.depth > 0.5:
                    continue  # 远景已在背景层画过
                o.draw(painter, self.color)

    def clear(self):
        for p in self._pools.values():
            p.clear()
        self._rain_pool.clear()
