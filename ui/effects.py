# -*- coding: utf-8 -*-
"""文字动效引擎（原「雾中飞羽」的文字侧）。

职责边界：
  本引擎只处理**文字**动画——逐字浮现/消散、整行交叠、呼吸、浮动、柔光、
  整批补位空窗。
  飘落粒子（羽毛/花瓣/雨滴等）已全部迁移到通用飞行物系统
  `ui/floating_objects.py`，由歌词窗注入的 `self.floater` 负责，本引擎不再
  持有任何粒子池，也不绘制粒子。

公开接口（歌词窗 `ui/lyric_window.py` 中的实际用法）：
    engine = EffectEngine(cfg)
    engine.floater = FloatingEngine(...)       # 歌词窗注入飞行物引擎
    engine.configure(cfg)                       # 配置变更时重读
    engine.on_line_changed(idx, row_y, line_h, prev_text, prev_char_xs, prev_row_y)
    engine.tick(dt_ms, w, h)                    # 每帧推进（同时推进 floater）
    engine.char_state(i, elapsed_ms) -> (alpha, blur, rise, float_y)
    engine.char_dissolve_state(i, n, elapsed) -> (alpha, blur, dx, dy)
    engine.line_alpha(elapsed_ms, entering) -> (alpha, blur, spread)
    engine.follow_reset / set_follow_chars / follow_step / follow_char_alpha
    engine.follow_prev_state / follow_full / reset_follow_all
    engine.float_offset / breathe / batch_alpha
"""
import math


# ---------------------------------------------------------------------------
# 缓动函数：输入 0..1，输出 0..1。避免线性跳变，让动画有"呼吸感"。
# ---------------------------------------------------------------------------
EASINGS = {
    "ease_in_out": lambda t: t * t * (3 - 2 * t),
    "ease_out": lambda t: 1 - (1 - t) ** 3,
    "ease_in": lambda t: t ** 3,
    "linear": lambda t: t,
}


def eased(t, name="ease_out"):
    t = max(0.0, min(1.0, t))
    return EASINGS.get(name, EASINGS["ease_out"])(t)


def _cfg_fx(cfg, key, default):
    """从 cfg['fx'] 里安全取子参数。"""
    return cfg.get("fx", {}).get(key, default)


class EffectEngine:
    """文字/氛围动效引擎。粒子全部委托给注入的 floater。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.floater = None       # 由歌词窗注入 FloatingEngine，负责全部粒子
        self.w = 0
        self.h = 0
        self.time_ms = 0.0            # 引擎自身时钟（始终推进，驱动呼吸/浮动）
        self.line_start_ms = 0.0      # 当前行入场起始时刻
        self.prev_line_start_ms = -1  # 上一行退场起始时刻（交叠用）
        self.prev_line_text = ""
        self.prev_line_y = 0
        self.prev_line_h = 0
        self._batch_change_ms = -1    # 整批补位切换时刻（空窗淡入用）
        # 逐字跟随消散：贯穿整行生命周期，读条扫过的字逐个化羽飘走
        self._follow_idx = -1
        self._follow_n = 0
        self._follow_char = []         # 每字消散进度 0..1（1=完全消散）
        self._follow_char_x = []       # 每字中心 x（触发飞行物用）
        self._follow_row_y = 0
        self._follow_line_h = 0
        self._follow_prev = []         # 退场收尾：上一行未散完的字进度（切行时快照）
        self._follow_prev_chars = []
        self._follow_prev_x = []
        self._follow_prev_y = 0
        self._follow_prev_start = 0
        self._follow_chars_text = []   # 当前行字符内容（收尾绘制用）
        self.configure(cfg)

    # ---------------- 配置 ----------------
    def configure(self, cfg):
        """重读文字/氛围动效参数。"""
        self.cfg = cfg
        self.enabled = _cfg_fx(cfg, "enabled", True)
        self.fade_in_ms = _cfg_fx(cfg, "fade_in_ms", 900)
        self.fade_out_ms = _cfg_fx(cfg, "fade_out_ms", 700)
        self.blur_max = _cfg_fx(cfg, "blur_max", 7)
        self.rise_px = _cfg_fx(cfg, "rise_px", 12)
        self.char_stagger_ms = _cfg_fx(cfg, "char_stagger_ms", 60)
        self.float_px = _cfg_fx(cfg, "float_px", 3)
        self.float_ms = _cfg_fx(cfg, "float_ms", 5200)
        # 设置面板存百分比整数(0-40)，引擎按 0..0.40 小数用
        self.breath_pct = max(0.0, min(0.5, _cfg_fx(cfg, "breath_pct", 10) / 100.0))
        self.breath_ms = _cfg_fx(cfg, "breath_ms", 3600)
        self.glow_len_chars = max(0.1, float(_cfg_fx(cfg, "glow_len_chars", 2.5)))
        self.batch_gap_ms = _cfg_fx(cfg, "batch_gap_ms", 220)
        self.easing = _cfg_fx(cfg, "easing", "ease_out")

        # 文字消散（飞行物形态由飞行物引擎的 exit 场景负责）
        self.word_dissolve = _cfg_fx(cfg, "word_dissolve", True)
        self.dissolve_char_ms = _cfg_fx(cfg, "dissolve_char_ms", 360)
        self.dissolve_stagger_ms = _cfg_fx(cfg, "dissolve_stagger_ms", 420)

        # 文字动效模块开关
        self.on_char = _cfg_fx(cfg, "char_reveal", True)
        self.on_breath = _cfg_fx(cfg, "breathing", True)
        self.on_float = _cfg_fx(cfg, "float", True)
        self.on_crossfade = _cfg_fx(cfg, "crossfade", True)
        self.on_soft = _cfg_fx(cfg, "soft_glow", True)
        self.on_follow_dissolve = _cfg_fx(cfg, "follow_dissolve", True)
        self.follow_char_ms = _cfg_fx(cfg, "follow_char_ms", 340)
        self.follow_lead = _cfg_fx(cfg, "follow_lead", 6) / 100.0

    # ---------------- 尺寸 ----------------
    def resize(self, w, h):
        self.w, self.h = w, h

    # ---------------- 事件：当前行切换 ----------------
    def on_batch_change(self):
        """整批补位：一批唱完换新时调用，制造短暂空窗再淡入。"""
        if self.enabled:
            self._batch_change_ms = self.time_ms

    def batch_alpha(self):
        """整批补位可见度 0..1：前 batch_gap_ms 全隐藏，随后淡入。"""
        if not self.enabled or self._batch_change_ms < 0:
            return 1.0
        elapsed = self.time_ms - self._batch_change_ms
        if elapsed < self.batch_gap_ms:
            return 0.0
        t = (elapsed - self.batch_gap_ms) / max(1, self.fade_in_ms)
        return eased(min(1.0, t), "ease_out")

    def on_line_changed(self, idx, row_y, line_h, prev_text="",
                        prev_char_xs=None, prev_row_y=None):
        """当前歌词行变化：重置入场时钟、记录上一行用于交叠退场，触发飞行物。"""
        now = self.time_ms
        if self.on_crossfade and prev_text:
            self.prev_line_start_ms = now
            self.prev_line_text = prev_text
            self.prev_line_y = prev_row_y if prev_row_y is not None else row_y
            self.prev_line_h = line_h
            # 切行整行化羽 -> 飞行物「歌词切换」场景
            if self.enabled and prev_char_xs and self.floater is not None:
                self.floater.burst("switch",
                                   origins=[(x, self.prev_line_y) for x in prev_char_xs])
        self.line_start_ms = now
        # 入场 -> 飞行物「歌词入场」场景
        if self.enabled and self.floater is not None:
            self.floater.burst("enter", origins=[(self.w * 0.5, row_y)])

    # ---------------- 逐字跟随消散：贯穿整行生命周期 ----------------
    def follow_reset(self, idx, char_xs, row_y, line_h):
        """切换歌词行时重置逐字消散跟踪状态。"""
        if idx == self._follow_idx and len(char_xs) == self._follow_n:
            self._follow_row_y = row_y
            self._follow_line_h = line_h
            self._follow_char_x = list(char_xs)
            return
        self._follow_prev = list(self._follow_char)
        self._follow_prev_chars = list(self._follow_chars_text)
        self._follow_prev_x = list(self._follow_char_x)
        self._follow_prev_y = self._follow_row_y
        self._follow_prev_start = self.time_ms

        self._follow_idx = idx
        self._follow_n = len(char_xs)
        self._follow_char = [0.0] * self._follow_n
        self._follow_char_x = list(char_xs)
        self._follow_row_y = row_y
        self._follow_line_h = line_h

    def set_follow_chars(self, chars):
        self._follow_chars_text = list(chars)

    def follow_step(self, progress, dt):
        """每帧推进逐字消散：读条扫过的字逐个化羽，并触发飞行物。"""
        if not self.enabled or not self.on_follow_dissolve:
            return
        dt = min(dt, 100)
        n = self._follow_n
        if n <= 0:
            return
        for i in range(n):
            frac = (i + 0.5) / n
            hit = frac <= max(0.0, min(1.0, progress + self.follow_lead))
            if hit and self._follow_char[i] < 1.0:
                was = self._follow_char[i]
                self._follow_char[i] = min(1.0, was + dt / max(1, self.follow_char_ms))
                # 刚开始消散 -> 飞行物「逐字消散配置」场景（每字一个发射点）
                if was <= 0.0 and self.floater is not None:
                    self.floater.burst("exit",
                                       origins=[(self._follow_char_x[i], self._follow_row_y)],
                                       count_override=1)
        if self._follow_prev:
            for i in range(len(self._follow_prev)):
                if self._follow_prev[i] < 1.0:
                    self._follow_prev[i] = min(
                        1.0, self._follow_prev[i] + dt / max(1, self.follow_char_ms))

    def follow_char_alpha(self, i):
        if not self.enabled or not self.on_follow_dissolve:
            return 1.0
        if 0 <= i < len(self._follow_char):
            return 1.0 - self._follow_char[i]
        return 1.0

    def follow_prev_state(self):
        """返回收尾行 [(char, alpha, x), ...]；全部散完则清空返回 None。"""
        if not self.enabled or not self.on_follow_dissolve:
            return None
        if not self._follow_prev:
            return None
        if all(d >= 1.0 for d in self._follow_prev):
            self._follow_prev = []
            self._follow_prev_chars = []
            self._follow_prev_x = []
            return None
        chars = self._follow_prev_chars
        out = []
        for i, d in enumerate(self._follow_prev):
            text = chars[i] if i < len(chars) else ""
            out.append((text, 1.0 - d,
                        self._follow_prev_x[i] if i < len(self._follow_prev_x) else 20))
        return out

    def follow_full(self):
        return bool(self._follow_char) and all(d >= 1.0 for d in self._follow_char)

    def reset_follow_all(self):
        """换歌时彻底清空逐字消散状态与飞行物。"""
        if self.floater is not None:
            self.floater.clear()
        self._follow_idx = -1
        self._follow_n = 0
        self._follow_char = []
        self._follow_char_x = []
        self._follow_prev = []
        self._follow_prev_chars = []
        self._follow_prev_x = []
        self._follow_chars_text = []

    # ---------------- 每帧推进 ----------------
    def tick(self, dt_ms, w, h):
        self.resize(w, h)
        if not self.enabled:
            return
        dt = min(dt_ms, 100)  # 单帧钳制，切后台回来不会瞬移
        self.time_ms += dt
        if self.floater is not None:
            self.floater.resize(w, h)
            self.floater.tick(dt)

    # ---------------- 状态查询：逐字/整行 ----------------
    def char_state(self, i, elapsed_ms):
        """返回第 i 个字符的 (alpha, blur, rise_px, float_y)。"""
        float_y = self.float_offset()
        if not self.enabled or not self.on_char or self.fade_in_ms <= 0:
            return 1.0, 0.0, 0.0, float_y
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
        """逐字消散状态 (alpha, blur, dx, dy)。文字原地渐隐+羽化，不移动。"""
        if not self.enabled or n_chars <= 0 or self.dissolve_char_ms <= 0:
            return 1.0, 0.0, 0.0, 0.0
        delay = (i / max(1, n_chars - 1)) * self.dissolve_stagger_ms
        t = (elapsed_ms - delay) / self.dissolve_char_ms
        if t <= 0:
            return 1.0, 0.0, 0.0, 0.0
        if t >= 1:
            return 0.0, 1.0, 0.0, 0.0
        e = eased(t, "ease_in")
        return 1.0 - e, eased(t, "ease_in_out"), 0.0, 0.0

    def line_alpha(self, elapsed_ms, entering=True):
        """整行入场/退场的 (alpha, blur, spread)。"""
        if entering:
            if not self.enabled or self.fade_in_ms <= 0:
                return 1.0, 0.0, 0.0
            t = elapsed_ms / self.fade_in_ms
            return eased(t, self.easing), 1 - eased(t, "ease_in_out"), 0.0
        if not self.enabled or self.fade_out_ms <= 0:
            return 0.0, 0.0, 0.0
        t = elapsed_ms / self.fade_out_ms
        a = 1 - eased(t, "ease_in")
        blur = eased(t, "ease_in_out")
        spread = 4 * eased(t, "ease_in_out")
        return max(0.0, min(1.0, a)), max(0.0, min(1.0, blur)), spread

    def float_offset(self):
        """整体上下浮动偏移(px)：所有歌词行共用，保持整窗同步呼吸感。"""
        if not self.enabled or not self.on_float or self.float_ms <= 0:
            return 0.0
        return math.sin(self.time_ms / self.float_ms * 2 * math.pi) * self.float_px

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
        life = (self.dissolve_stagger_ms + self.dissolve_char_ms
                if self.word_dissolve else self.fade_out_ms)
        if elapsed > life:
            return None
        a, blur, spread = self.line_alpha(elapsed, entering=False)
        return self.prev_line_text, self.prev_line_y, self.prev_line_h, a, blur, spread
