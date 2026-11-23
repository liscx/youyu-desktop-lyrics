# -*- coding: utf-8 -*-
"""通用飞行物系统：素材外观 + 统一运动引擎。

设计原则：
  1. 素材只画自己（draw_material），运动逻辑完全共用（FlyingObject.step）。
  2. 四个触发场景各自一个粒子池，配置独立，互不覆盖。
  3. 对象池 + 一次性粒子回收，避免高频创建/销毁，长时间运行内存恒定。
  4. 引擎只管粒子；文字的逐字消散 alpha 仍由 EffectEngine 负责。
"""
import math
import random

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainterPath, QBrush, QPen

from core.floating_config import (
    TIER_COUNT, TIER_SPEED, TIER_DEVIATION, TIER_ROTATION,
    MATERIALS, SCENE_IDS,
)


# ---------------------------------------------------------------------------
# 素材绘制：每个函数接收 painter / size / color / t，以原点为中心绘制
# ---------------------------------------------------------------------------
def _draw_feather(p, s, c):
    """羽毛：带羽轴的柳叶形羽片。

    贝塞尔宽度从 0.55 提到 0.72——羽片实际宽高比约 0.55（对应 MATERIALS.aspect），
    避免大尺寸下看起来像"大长条"。
    """
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(c))
    path = QPainterPath()
    path.moveTo(0, -s)
    path.cubicTo(s * 0.72, -s * 0.35, s * 0.72, s * 0.45, 0, s)
    path.cubicTo(-s * 0.72, s * 0.45, -s * 0.72, -s * 0.35, 0, -s)
    p.drawPath(path)
    stem = QColor(c)
    stem.setAlpha(min(255, stem.alpha() + 40))
    p.setPen(QPen(stem, max(0.6, s * 0.08)))
    p.drawLine(0, int(-s * 0.9), 0, int(s * 0.9))


def _draw_sakura(p, s, c):
    """樱花：五片带缺口的圆润花瓣 + 花蕊。"""
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(c))
    for i in range(5):
        p.save()
        p.rotate(i * 72)
        path = QPainterPath()
        path.moveTo(0, 0)
        path.cubicTo(-s * 0.5, -s * 0.5, -s * 0.35, -s * 1.15, 0, -s * 0.9)
        path.cubicTo(s * 0.35, -s * 1.15, s * 0.5, -s * 0.5, 0, 0)
        p.drawPath(path)
        p.restore()
    core = QColor(c)
    core.setAlpha(min(255, core.alpha() + 60))
    p.setBrush(QBrush(core))
    p.drawEllipse(-s * 0.14, -s * 0.14, s * 0.28, s * 0.28)


def _draw_petal(p, s, c):
    """单片花瓣：柳叶形 + 中脉。"""
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(c))
    path = QPainterPath()
    path.moveTo(0, -s)
    path.cubicTo(s * 0.62, -s * 0.4, s * 0.5, s * 0.6, 0, s * 0.9)
    path.cubicTo(-s * 0.5, s * 0.6, -s * 0.62, -s * 0.4, 0, -s)
    p.drawPath(path)
    vein = QColor(c)
    vein.setAlpha(max(0, vein.alpha() - 40))
    p.setPen(QPen(vein, max(0.5, s * 0.06)))
    p.drawLine(0, int(-s * 0.7), 0, int(s * 0.6))


def _draw_snow(p, s, c):
    """雪花：六角对称枝晶。"""
    p.setPen(QPen(c, max(0.7, s * 0.11), Qt.SolidLine, Qt.RoundCap))
    for i in range(6):
        p.save()
        p.rotate(i * 60)
        p.drawLine(0, 0, 0, int(-s))
        for d in (0.45, 0.72):
            y = int(-s * d)
            p.drawLine(0, y, int(s * 0.28), y + int(s * 0.22))
            p.drawLine(0, y, int(-s * 0.28), y + int(s * 0.22))
        p.restore()
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(c))
    p.drawEllipse(-s * 0.12, -s * 0.12, s * 0.24, s * 0.24)


def _draw_maple(p, s, c):
    """枫叶：五裂掌状叶形 + 短柄。"""
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(c))
    path = QPainterPath()
    pts = [(0, -s), (0.28, -0.42), (0.72, -0.55), (0.5, -0.12),
           (0.95, 0.22), (0.42, 0.32), (0.3, 0.78), (0, 0.5)]
    path.moveTo(pts[0][0] * s, pts[0][1] * s)
    for x, y in pts[1:]:
        path.lineTo(x * s, y * s)
    for x, y in reversed(pts[:-1]):
        path.lineTo(-x * s, y * s)
    path.closeSubpath()
    p.drawPath(path)


def _draw_glow(p, s, c):
    """光点：柔光圆斑（三层同心，最外层淡）。"""
    p.setPen(Qt.NoPen)
    for scale, alpha_mul in ((1.6, 0.18), (1.0, 0.45), (0.45, 1.0)):
        cc = QColor(c)
        cc.setAlpha(int(min(255, cc.alpha() * alpha_mul)))
        p.setBrush(QBrush(cc))
        r = s * scale
        p.drawEllipse(-r, -r, r * 2, r * 2)


def _draw_butterfly(p, s, c):
    """蝴蝶：左右翅 + 身体，翅膀带轻微色差。"""
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(c))
    for sign in (-1, 1):
        path = QPainterPath()
        path.moveTo(0, -s * 0.25)
        path.cubicTo(sign * s * 1.1, -s * 1.2, sign * s * 1.15, s * 0.35, 0, s * 0.2)
        p.drawPath(path)
        path2 = QPainterPath()
        path2.moveTo(0, s * 0.1)
        path2.cubicTo(sign * s * 0.8, s * 0.15, sign * s * 0.75, s * 0.95, 0, s * 0.5)
        p.drawPath(path2)
    body = QColor(c)
    body.setAlpha(min(255, body.alpha() + 70))
    p.setBrush(QBrush(body))
    p.drawEllipse(-s * 0.09, -s * 0.6, s * 0.18, s * 1.3)


def _draw_rain(p, s, c):
    """雨丝（迁移自忧郁主题）：短斜线。"""
    p.setPen(QPen(c, max(0.8, s * 0.12), Qt.SolidLine, Qt.RoundCap))
    p.drawLine(0, -s, -s * 0.18, s)


MATERIAL_DRAW = {
    "feather": _draw_feather,
    "sakura": _draw_sakura,
    "petal": _draw_petal,
    "snow": _draw_snow,
    "maple": _draw_maple,
    "glow": _draw_glow,
    "butterfly": _draw_butterfly,
    "rain": _draw_rain,
    "custom": _draw_glow,  # 待接入：暂用光点占位
}

# 雨丝加入运行时素材表（配置层 MATERIALS 不含，专供迁移的旧雨滴使用）
_RUNTIME_MATERIALS = dict(MATERIALS)
_RUNTIME_MATERIALS["rain"] = {"label": "雨丝", "aspect": 0.2, "base": 9}


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
        drawer = MATERIAL_DRAW.get(self.material, _draw_glow)
        meta = _RUNTIME_MATERIALS.get(self.material, {"base": 10})
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
