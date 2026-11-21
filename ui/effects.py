# -*- coding: utf-8 -*-
"""雾中飞羽 · 特效引擎（Mist & Feathers effect engine）。

设计与实现说明
================
本模块为桌面歌词提供一套**可配置、可独立开关**的动画系统。
在 Qt/PySide6 中，用 QPainter 的 transform / opacity 等价实现
网页 CSS transform+opacity / Canvas 的动画思路，且不重建任何控件，
只靠一个 QTimer 驱动纯绘制，长时间运行内存恒定。

公开接口（调用方式）：
    engine = EffectEngine(cfg)                 # 用配置构造
    engine.configure(cfg)                       # 配置变更时重读
    engine.on_line_changed(idx, row_y, line_h,  # 当前歌词行切换时调用
                           prev_text="", prev_char_xs=None, prev_row_y=None)
    engine.tick(dt_ms, w, h)                    # 每个动画帧推进（QTimer 里调）
    engine.draw_background(painter, w, h)       # 画雾气/远景羽毛/微粒（文字下层）
    engine.draw_foreground(painter, w, h)       # 画近景羽毛/扫光（文字上层）
    engine.char_state(i, elapsed_ms) -> (alpha, blur, rise, float_y)  # 逐字入场状态
    engine.char_dissolve_state(i, n, elapsed) -> (alpha, blur, dx, dy)  # 逐字消散状态
    engine.line_alpha(elapsed_ms, entering) -> (alpha, blur, spread)  # 整行入场/退场状态
    engine.sweep_pos() -> 0..1                  # 扫光位置
    engine.sweep_alpha(pos) -> 0..1             # 扫光亮度包络（边界渐隐，无硬切）

每个动画模块都有 cfg 开关 ``fx.<name>`` 与独立参数，见 core/config.py 的 FX_DEFAULTS。
"""
import math
import random

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QPainterPath, QBrush, QPen, QLinearGradient


# ----------------------------------------------------------------------------
# 缓动函数：输入 0..1，输出 0..1。避免线性跳变，让动画有加减速的"呼吸感"。
# ----------------------------------------------------------------------------
EASINGS = {
    # 平滑起步/收尾，最通用
    "ease_in_out": lambda t: t * t * (3 - 2 * t),
    # 快速起步、缓慢收尾——适合"浮现/显现"
    "ease_out": lambda t: 1 - (1 - t) ** 3,
    # 缓慢起步、快速收尾——适合"消散/退场"
    "ease_in": lambda t: t ** 3,
    "linear": lambda t: t,
}


def eased(t, name="ease_out"):
    t = max(0.0, min(1.0, t))
    return EASINGS.get(name, EASINGS["ease_out"])(t)


def _cfg_fx(cfg, key, default):
    """从 cfg['fx'] 里安全取子参数。"""
    fx = cfg.get("fx", {})
    return fx.get(key, default)


class _Particle:
    """通用漂浮粒子基类：位置/速度/透明度/生命周期。"""

    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "alpha",
                 "spin", "angle", "depth", "delay")

    def __init__(self, w, h, depth=0.0):
        self.depth = depth  # 0 近景 1 远景，影响速度/大小/透明度
        self.respawn(w, h, initial=True)

    def respawn(self, w, h, initial=False):
        self.x = random.uniform(0, w) if w > 0 else 0
        self.y = random.uniform(0, h) if (initial and h > 0) else -20
        self.vx = random.uniform(-0.35, 0.35)
        self.vy = random.uniform(0.25, 0.85)
        self.max_life = random.uniform(2600, 5200)
        self.life = random.uniform(0, self.max_life) if initial else 0
        self.size = random.uniform(4, 11)
        self.alpha = random.randint(60, 150)
        self.angle = random.uniform(0, 360)
        self.spin = random.uniform(-0.5, 0.5)
        self.delay = 0.0  # 延迟激活（逐字化羽时让羽毛随文字从左到右依次出现）

    def step(self, dt, w, h):
        if self.delay > 0:
            self.delay -= dt
            return
        self.life += dt
        self.x += self.vx * dt / 16.0 + math.sin(self.life / 900.0) * 0.3
        self.y += self.vy * dt / 16.0
        self.angle += self.spin * dt / 16.0
        if self.life >= self.max_life or self.y - 20 > h:
            self.respawn(w, h)

    def fade(self):
        """生命周期两端的淡入淡出，0..1。"""
        t = self.life / self.max_life
        if t < 0.15:
            return t / 0.15
        if t > 0.75:
            return (1 - t) / 0.25
        return 1.0


class Feather(_Particle):
    """羽毛粒子：绘制为一片带羽轴与轻微弧度的羽片，缓慢旋转飘落。"""

    def draw(self, painter, color):
        if self.delay > 0:
            return
        f = self.fade()
        if f <= 0:
            return
        c = QColor(color)
        c.setAlpha(int(self.alpha * f * (0.45 if self.depth else 0.8)))
        painter.save()
        painter.translate(self.x, self.y)
        painter.rotate(self.angle)
        s = self.size * (0.6 if self.depth else 1.0)
        # 羽片轮廓（对称柳叶形）
        path = QPainterPath()
        path.moveTo(0, -s)
        path.cubicTo(s * 0.55, -s * 0.35, s * 0.55, s * 0.45, 0, s)
        path.cubicTo(-s * 0.55, s * 0.45, -s * 0.55, -s * 0.35, 0, -s)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(c))
        painter.drawPath(path)
        # 羽轴（更亮一点）
        stem = QColor(c)
        stem.setAlpha(min(255, c.alpha() + 40))
        painter.setPen(QPen(stem, max(0.6, s * 0.08)))
        painter.drawLine(0, -s * 0.9, 0, s * 0.9)
        painter.restore()


class Mote(_Particle):
    """微粒：极小的圆点，缓慢漂浮，增加空间层次。"""

    def draw(self, painter, color):
        f = self.fade()
        if f <= 0:
            return
        c = QColor(color)
        c.setAlpha(int(self.alpha * f * 0.5))
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(c))
        r = max(0.8, self.size * 0.12)
        painter.drawEllipse(self.x, self.y, r, r)
        painter.restore()


class EffectEngine:
    """雾中飞羽特效引擎。所有状态在此集中管理，歌词窗只负责调用接口。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.w = 0
        self.h = 0
        self.time_ms = 0.0            # 引擎自身时钟（始终推进，驱动呼吸/浮动/雾气）
        self.line_start_ms = 0.0      # 当前行入场起始时刻
        self.prev_line_start_ms = -1  # 上一行退场起始时刻（交叠用）
        self.prev_line_text = ""
        self.prev_line_y = 0
        self.prev_line_h = 0
        self._batch_change_ms = -1  # 整批补位切换时刻（空窗淡入用）
        self._feathers = []           # 常驻近景羽毛（对象池）
        self._burst = []              # 临时爆发羽毛（入场/化羽消散），独立于池，避免被 sync 回收
        self._far_feathers = []
        self._motes = []
        self.configure(cfg)

    # ---------------- 配置 ----------------
    def configure(self, cfg):
        """重读配置；粒子数量变化时增量补齐，不整体重建（省内存）。"""
        self.cfg = cfg
        self.enabled = _cfg_fx(cfg, "enabled", True)
        self.fade_in_ms = _cfg_fx(cfg, "fade_in_ms", 900)
        self.fade_out_ms = _cfg_fx(cfg, "fade_out_ms", 700)
        self.blur_max = _cfg_fx(cfg, "blur_max", 7)
        self.rise_px = _cfg_fx(cfg, "rise_px", 12)
        self.char_stagger_ms = _cfg_fx(cfg, "char_stagger_ms", 60)
        self.float_px = _cfg_fx(cfg, "float_px", 3)
        self.float_ms = _cfg_fx(cfg, "float_ms", 5200)
        self.breath_pct = _cfg_fx(cfg, "breath_pct", 0.10)
        self.breath_ms = _cfg_fx(cfg, "breath_ms", 3600)
        self.sweep_ms = _cfg_fx(cfg, "sweep_ms", 4200)
        self.sweep_alpha_max = _cfg_fx(cfg, "sweep_alpha", 34)       # 光条峰值透明度
        self.sweep_fade_start = (_cfg_fx(cfg, "sweep_fade_start", 55) / 100.0)  # 配置存 0-95 整数，引擎用 0..0.95
        self.batch_gap_ms = _cfg_fx(cfg, "batch_gap_ms", 220)   # 整批补位空窗时长
        self.mist_speed = _cfg_fx(cfg, "mist_speed", 0.15)
        self.mist_alpha = _cfg_fx(cfg, "mist_alpha", 26)
        self.feather_alpha = _cfg_fx(cfg, "feather_alpha", 150)
        self.feather_color = _cfg_fx(cfg, "feather_color", "#DCE6F1")
        self.mist_color = _cfg_fx(cfg, "mist_color", "#B7C6D8")
        self.easing = _cfg_fx(cfg, "easing", "ease_out")

        # 逐字化羽消散（从左到右化为羽毛，向左上方飘散）
        self.word_dissolve = _cfg_fx(cfg, "word_dissolve", True)
        self.dissolve_char_ms = _cfg_fx(cfg, "dissolve_char_ms", 360)      # 单字消散时长
        self.dissolve_stagger_ms = _cfg_fx(cfg, "dissolve_stagger_ms", 420)  # 整行从左到右的延迟跨度
        self.dissolve_drift_x = _cfg_fx(cfg, "dissolve_drift_x", 22)       # 文字向左漂移(px)
        self.dissolve_drift_y = _cfg_fx(cfg, "dissolve_drift_y", 34)       # 文字向上漂移(px)

        # 各模块独立开关
        self.on_char = _cfg_fx(cfg, "char_reveal", True)
        self.on_feather = _cfg_fx(cfg, "feathers", True)
        self.on_far_feather = _cfg_fx(cfg, "far_feathers", True)
        self.on_mote = _cfg_fx(cfg, "motes", True)
        self.on_mist = _cfg_fx(cfg, "mist_flow", True)
        self.on_breath = _cfg_fx(cfg, "breathing", True)
        self.on_float = _cfg_fx(cfg, "float", True)
        self.on_sweep = _cfg_fx(cfg, "light_sweep", True)
        self.on_crossfade = _cfg_fx(cfg, "crossfade", True)
        self.on_soft = _cfg_fx(cfg, "soft_glow", True)
        self.on_enter_feather = _cfg_fx(cfg, "feather_on_enter", True)
        self.on_exit_feather = _cfg_fx(cfg, "feather_on_exit", True)

        self.n_feather = max(0, _cfg_fx(cfg, "feather_count", 12))
        self.n_far = max(0, _cfg_fx(cfg, "far_feather_count", 8))
        self.n_mote = max(0, _cfg_fx(cfg, "mote_count", 22))

    # ---------------- 尺寸 ----------------
    def resize(self, w, h):
        if (w, h) == (self.w, self.h):
            return
        self.w, self.h = w, h
        # 尺寸变化时重排常驻粒子（数量不变，避免重建）
        for group, cls, depth in (
            (self._feathers, Feather, 0.0),
            (self._far_feathers, Feather, 1.0),
            (self._motes, Mote, 0.0),
        ):
            for p in group:
                p.respawn(w, h, initial=True)

    # ---------------- 事件：当前行切换 ----------------
    def on_batch_change(self):
        """整批补位模式：一批唱完、整批换新时调用，制造短暂空窗再淡入。"""
        if self.enabled:
            self._batch_change_ms = self.time_ms

    def batch_alpha(self):
        """整批补位的可见度 0..1：前 batch_gap_ms 完全隐藏（空窗），随后淡入。"""
        if not self.enabled or self._batch_change_ms < 0:
            return 1.0
        elapsed = self.time_ms - self._batch_change_ms
        if elapsed < self.batch_gap_ms:
            return 0.0
        t = (elapsed - self.batch_gap_ms) / max(1, self.fade_in_ms)
        return eased(min(1.0, t), "ease_out")

    def on_line_changed(self, idx, row_y, line_h, prev_text="",
                        prev_char_xs=None, prev_row_y=None):
        """当前歌词行变化时调用：重置入场时钟，记录上一行用于交叠退场，撒羽毛。

        prev_char_xs: 上一行每个字符的中心 x 坐标（由歌词窗用 QFontMetrics 计算），
                      用于让羽毛从对应字符的原位化出。
        prev_row_y:   上一行的实际 y 坐标（退场行应画在上一行位置，而非当前行）。
        """
        now = self.time_ms
        if self.on_crossfade and prev_text:
            self.prev_line_start_ms = now
            self.prev_line_text = prev_text
            self.prev_line_y = prev_row_y if prev_row_y is not None else row_y
            self.prev_line_h = line_h
            # 消散羽毛：旧文字从左到右依次化为羽毛，向左上方飘散
            if self.enabled and self.on_exit_feather and self.on_feather and prev_char_xs:
                n = len(prev_char_xs)
                delays = [(i / max(1, n - 1)) * self.dissolve_stagger_ms
                          for i in range(n)]
                self._spawn_burst(self.prev_line_y, line_h, n, mode="dissolve",
                                  xs=prev_char_xs, delays=delays)
        self.line_start_ms = now
        if self.enabled and self.on_enter_feather and self.on_feather:
            self._spawn_burst(row_y, line_h, count=max(2, self.n_feather // 3),
                              mode="enter")

    def _spawn_burst(self, y, line_h, count, mode="enter", xs=None, delays=None):
        """生成一簇临时羽毛。

        mode='enter'    入场：在行附近随机分布，缓慢上浮。
        mode='dissolve' 消散：从每个字符原位化出，带递增延迟，向左上方飘散。
        """
        for k in range(count):
            f = Feather(self.w or 1000, self.h or 200)
            f.y = y + random.uniform(-line_h * 0.35, line_h * 0.35)
            f.x = xs[k] if xs else random.uniform(0, max(1, self.w))
            f.life = 0
            if mode == "dissolve":
                f.vx = random.uniform(-1.35, -0.45)   # 向左
                f.vy = random.uniform(-1.15, -0.35)   # 向上
                f.size = random.uniform(3.5, 8.0)
                f.alpha = random.randint(90, 175)
                f.max_life = random.uniform(1500, 2600)
                f.delay = delays[k] if delays else 0.0
                f.spin = random.uniform(-1.2, 1.2)
            else:
                f.vx = random.uniform(-0.35, 0.35)
                f.vy = random.uniform(-0.6, -0.1)
                f.max_life = random.uniform(1400, 2600)
                f.delay = 0.0
            self._burst.append(f)
        # 防止长跑累积：超过上限则丢弃最老的
        cap = max(8, self.n_feather * 2)
        if len(self._burst) > cap:
            del self._burst[:len(self._burst) - cap]

    # ---------------- 每帧推进 ----------------
    def tick(self, dt_ms, w, h):
        self.resize(w, h)
        if not self.enabled:
            return
        dt = min(dt_ms, 100)  # 单帧钳制，切后台回来不会瞬移
        self.time_ms += dt

        def sync(group, cls, depth, target):
            while len(group) < target:
                group.append(cls(w, h, depth))
            if len(group) > target:
                del group[target:]

        if self.on_feather:
            sync(self._feathers, Feather, 0.0, self.n_feather)
            for p in self._feathers:
                p.step(dt, w, h)
            # 临时羽毛：延迟中的只递减 delay，其余推进；死亡即回收
            alive = []
            for p in self._burst:
                if p.delay > 0:
                    p.delay -= dt
                else:
                    p.step(dt, w, h)
                if p.life < p.max_life:
                    alive.append(p)
            self._burst = alive
        else:
            self._feathers.clear()
            self._burst.clear()

        if self.on_far_feather:
            sync(self._far_feathers, Feather, 1.0, self.n_far)
            for p in self._far_feathers:
                p.step(dt, w, h)
        else:
            self._far_feathers.clear()

        if self.on_mote:
            sync(self._motes, Mote, 0.0, self.n_mote)
            for p in self._motes:
                p.step(dt, w, h)
        else:
            self._motes.clear()

    # ---------------- 状态查询：逐字/整行 ----------------
    def char_state(self, i, elapsed_ms):
        """返回第 i 个字符的 (alpha 0..1, blur 0..1, rise_px, float_y)。"""
        float_y = 0.0
        if self.enabled and self.on_float and self.float_ms > 0:
            float_y = math.sin(self.time_ms / self.float_ms * 2 * math.pi) * self.float_px

        if not self.enabled or not self.on_char or self.fade_in_ms <= 0:
            return 1.0, 0.0, 0.0, float_y
        # 每个字有独立延迟：像逐个从雾里浮出，而非打字机
        delay = i * self.char_stagger_ms
        t = (elapsed_ms - delay) / self.fade_in_ms
        if t <= 0:
            return 0.0, 1.0, self.rise_px, float_y
        if t >= 1:
            return 1.0, 0.0, 0.0, float_y
        a = eased(t, self.easing)
        blur = 1 - eased(t, "ease_in_out")
        rise = self.rise_px * (1 - a)
        return a, blur, rise, float_y

    def char_dissolve_state(self, i, n_chars, elapsed_ms):
        """逐字消散状态 (alpha, blur, dx, dy)——从左到右依次化羽。

        i 越靠左 delay 越小，越早开始消散；消散中的字向左上漂移并羽化，
        与 _spawn_burst(mode='dissolve') 生成的羽毛同步，形成"字化羽"的观感。
        """
        if not self.enabled or n_chars <= 0 or self.dissolve_char_ms <= 0:
            return 1.0, 0.0, 0.0, 0.0
        delay = (i / max(1, n_chars - 1)) * self.dissolve_stagger_ms
        t = (elapsed_ms - delay) / self.dissolve_char_ms
        if t <= 0:
            return 1.0, 0.0, 0.0, 0.0
        if t >= 1:
            return 0.0, 1.0, -self.dissolve_drift_x, -self.dissolve_drift_y
        e = eased(t, "ease_in")
        return (1.0 - e,
                eased(t, "ease_in_out"),
                -self.dissolve_drift_x * e,
                -self.dissolve_drift_y * e)

    def line_alpha(self, elapsed_ms, entering=True):
        """整行入场/退场的 (alpha, blur, spread)。

        entering=True 入场：淡雾显现 + 羽化；False 退场：渐隐 + 羽化消散。
        """
        if entering:
            if not self.enabled or self.fade_in_ms <= 0:
                return 1.0, 0.0, 0.0
            t = elapsed_ms / self.fade_in_ms
            a = eased(t, self.easing)
            blur = 1 - eased(t, "ease_in_out")
            spread = 0.0
        else:
            if not self.enabled or self.fade_out_ms <= 0:
                return 0.0, 0.0, 0.0
            t = elapsed_ms / self.fade_out_ms
            a = 1 - eased(t, self.ease_in_name())
            blur = eased(t, "ease_in_out")
            spread = 4 * eased(t, "ease_in_out")
        return max(0.0, min(1.0, a)), max(0.0, min(1.0, blur)), spread

    def ease_in_name(self):
        return "ease_in"

    def breathe(self):
        """整行微光呼吸系数（乘到 alpha 上的微小波动）。"""
        if not self.enabled or not self.on_breath or self.breath_ms <= 0:
            return 1.0
        return 1.0 + math.sin(self.time_ms / self.breath_ms * 2 * math.pi) * self.breath_pct

    def prev_line_state(self):
        """返回上一行交叠退场状态 (text, y, h, alpha, blur, spread) 或 None。"""
        if not self.enabled or not self.on_crossfade:
            return None
        if not self.prev_line_text or self.prev_line_start_ms < 0:
            return None
        elapsed = self.time_ms - self.prev_line_start_ms
        # 逐字消散的总时长 = 跨度 + 单字时长；旧路径用 fade_out_ms
        life = (self.dissolve_stagger_ms + self.dissolve_char_ms
                if self.word_dissolve else self.fade_out_ms)
        if elapsed > life:
            return None
        a, blur, spread = self.line_alpha(elapsed, entering=False)
        return self.prev_line_text, self.prev_line_y, self.prev_line_h, a, blur, spread

    def sweep_pos(self):
        """光线扫过位置 0..1（<0 表示未启用/不在扫过周期）。"""
        if not self.enabled or not self.on_sweep or self.sweep_ms <= 0:
            return -1
        return (self.time_ms % self.sweep_ms) / self.sweep_ms

    def sweep_alpha(self, pos):
        """光条亮度包络 0..1：淡入 → 巡航 → 向右渐隐，到边界归零。

        这样 pos 经 % 循环从右边界跳回左侧时，两端 alpha 都是 0，
        不会出现"光条撞墙后突然消失/突然出现"的硬切。
        """
        if pos < 0 or not self.enabled or not self.on_sweep:
            return 0.0
        fade_in = min(1.0, pos / 0.10)  # 左侧 10% 淡入
        fs = max(0.0, min(0.95, self.sweep_fade_start))
        if pos <= fs:
            fade_out = 1.0
        else:
            fade_out = 1.0 - (pos - fs) / max(0.01, 1.0 - fs)
            fade_out = max(0.0, min(1.0, fade_out))
            fade_out = fade_out * fade_out  # 二次缓动，尾部更柔和
        return fade_in * fade_out

    # ---------------- 绘制：背景层 ----------------
    def draw_background(self, painter, w, h):
        if not self.enabled:
            return
        # 1) 低速横向流动的雾气（低透明渐变，绝不遮挡文字）
        if self.on_mist and self.mist_alpha > 0:
            offset = (self.time_ms * self.mist_speed * 0.02) % (w or 1)
            grad = QLinearGradient(-offset, 0, (w or 1) - offset, 0)
            base = QColor(self.mist_color)
            grad.setColorAt(0.0, self._with_alpha(base, 0))
            grad.setColorAt(0.3, self._with_alpha(base, self.mist_alpha))
            grad.setColorAt(0.7, self._with_alpha(base, self.mist_alpha // 2))
            grad.setColorAt(1.0, self._with_alpha(base, 0))
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRect(0, int(h * 0.15), w, int(h * 0.7))
            painter.restore()

        # 2) 远景羽毛（空间层次，画在文字下）
        if self.on_far_feather:
            for p in self._far_feathers:
                p.draw(painter, self.feather_color)

    # ---------------- 绘制：前景层 ----------------
    def draw_foreground(self, painter, w, h):
        if not self.enabled:
            return
        # 微粒（少量，文字周围）
        if self.on_mote:
            for p in self._motes:
                p.draw(painter, self.feather_color)
        # 近景羽毛（常驻 + 入场/化羽消散的临时羽毛）
        if self.on_feather:
            for p in self._feathers:
                p.draw(painter, self.feather_color)
            for p in self._burst:
                p.draw(painter, self.feather_color)

    @staticmethod
    def _with_alpha(color, alpha):
        c = QColor(color)
        c.setAlpha(max(0, min(255, alpha)))
        return c
