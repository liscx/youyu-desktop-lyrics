# -*- coding: utf-8 -*-
"""歌词悬浮窗：绘制、交互、歌词更新。

绘制完全由 cfg 驱动（cfg 的外观键由当前主题决定），
因此切换主题只需 apply_config() + update() 即可即时生效。
"""
import random

from PySide6.QtCore import Qt, QTimer, QPoint, QRect
from PySide6.QtWidgets import QWidget, QMenu, QApplication
from PySide6.QtGui import (
    QPainter, QColor, QFont, QFontMetrics, QBrush,
    QPen, QPainterPath, QLinearGradient,
)

from core.config import save_config
from core.lyrics import get_lyrics
from ui.hotkey import set_click_through
from ui.effects import EffectEngine


class RainDrop:
    """一颗雨滴（忧郁主题的氛围粒子）。"""

    __slots__ = ("x", "y", "length", "speed", "alpha")

    def __init__(self, w, h):
        self.reset(w, h, random_initial=True)

    def reset(self, w, h, random_initial=False):
        self.x = random.uniform(0, w) if w > 0 else 0
        self.length = random.uniform(8, 22)
        self.speed = random.uniform(1.6, 4.2)
        self.alpha = random.randint(30, 95)
        self.y = random.uniform(-h, h) if random_initial else -self.length

    def step(self, w, h):
        self.y += self.speed
        if self.y - self.length > h:
            self.reset(w, h)


class LyricWindow(QWidget):
    """透明悬浮歌词窗。"""

    def __init__(self, cfg, monitor):
        super().__init__()
        self.cfg = cfg
        self.monitor = monitor
        self.lines = []
        self.translated = []
        self.current_index = -1
        self.lyric_key = ""
        self._drag_pos = None

        # 雨滴粒子（忧郁主题）
        self._rain = []
        self._ambient_timer = QTimer(self)
        self._ambient_timer.timeout.connect(self._step_ambient)

        # 雾中飞羽特效引擎 + 独立动画时钟
        self.fx = EffectEngine(cfg)
        self._fx_timer = QTimer(self)
        self._fx_timer.timeout.connect(self._step_fx)
        self._fx_last_tick = 0
        self._line_row_y = 24
        self._line_h = 40

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self.apply_config()
        self._init_position()
        self._init_timer()

    # ---------- 初始化 ----------
    def _init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_lyric)
        self.timer.start(self.cfg.get("refresh_ms", 80))
        # 特效动画帧：~30fps，独立于歌词刷新（_step_fx 在 __init__ 已连接）
        import time as _time
        self._fx_last_tick = _time.monotonic()
        self._fx_timer.start(33)

    def _step_fx(self):
        """特效帧：推进粒子/时钟，触发重绘。"""
        import time as _time
        now = _time.monotonic()
        dt = (now - self._fx_last_tick) * 1000
        self._fx_last_tick = now
        if self.fx.enabled:
            self.fx.tick(dt, self.width(), self.height())
            self.update()

    def _init_position(self):
        pos = self.cfg.get("position", {})
        w = self.cfg.get("width", 1000)
        h = 160
        if pos.get("x") is None:
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - w) // 2
            y = screen.height() - 220
        else:
            x, y = pos["x"], pos["y"]
        self.setGeometry(x, y, w, h)

    def apply_config(self):
        """从 cfg 重读全部外观参数（主题切换后调用）。"""
        self.setWindowOpacity(self.cfg.get("opacity", 0.92))
        self.font = QFont(self.cfg["font_family"], self.cfg["font_size"])
        self.font.setBold(self.cfg.get("font_bold", True))
        self.color_normal = QColor(self.cfg["color_normal"])
        self.color_highlight = QColor(self.cfg["color_highlight"])
        self.color_translated = QColor(self.cfg["color_translated"])
        self.color_glow = QColor(self.cfg["color_glow"])
        self.glow_enabled = self.cfg.get("glow_enabled", True)
        self.glow_radius = self.cfg.get("glow_radius", 6)
        self.show_translation = self.cfg.get("show_translation", True)
        self.line_spacing = self.cfg.get("line_spacing", 12)
        self.outline_width = self.cfg.get("outline_width", 3)
        # 显示行数与行号
        self.visible_lines = max(1, min(8, int(self.cfg.get("visible_lines", 4))))
        self.show_line_number = self.cfg.get("show_line_number", True)
        # 特效引擎重读配置
        self.fx.configure(self.cfg)
        self.click_through = self.cfg.get("click_through", True)
        self.locked = self.cfg.get("locked", True)
        # 主题专属
        self.ambient = self.cfg.get("ambient", False)
        self.ambient_color = QColor(self.cfg.get("ambient_color", "#9FC6FF"))
        self.ambient_density = self.cfg.get("ambient_density", 46)
        self.accent_line = self.cfg.get("accent_line", False)

        self._sync_ambient()

        # 只有锁定且开启穿透时才穿透
        effective = self.click_through and self.locked
        self.set_click_through(effective)

    def _sync_ambient(self):
        """根据主题开关启停雨滴动画。"""
        if self.ambient:
            if not self._rain:
                self._rebuild_rain()
            if not self._ambient_timer.isActive():
                self._ambient_timer.start(33)  # ~30fps
        else:
            self._ambient_timer.stop()
            self._rain = []

    def _rebuild_rain(self):
        w, h = self.width(), max(self.height(), 160)
        self._rain = [RainDrop(w, h) for _ in range(self.ambient_density)]

    def _step_ambient(self):
        if not self._rain:
            return
        w, h = self.width(), self.height()
        for drop in self._rain:
            drop.step(w, h)
        self.update()

    def set_click_through(self, enabled):
        self.winId()  # 确保原生窗口已创建
        hwnd = int(self.winId())
        set_click_through(hwnd, enabled)

    # ---------- 歌词更新 ----------
    def update_lyric(self):
        self.monitor.poll()  # 主线程轮询（后台线程 ctypes 回调会持有 GIL 阻塞 Qt 事件循环）
        state = self.monitor.snapshot()
        key = f"{state['artist']}||{state['title']}"
        if not state["title"]:
            self.lines = []
            self.update()
            return

        if key != self.lyric_key:
            self.lyric_key = key
            result = get_lyrics(
                state["title"], state["artist"], self.cfg.get("source", "auto")
            )
            self.lines = result["lines"]
            self.translated = result["translated"] if self.show_translation else []
            self.current_index = -1
            self._resize_to_content()

        if not self.lines:
            self.update()
            return

        pos_ms = state.get("position_ms", 0)
        idx = -1
        lo, hi = 0, len(self.lines) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.lines[mid][0] <= pos_ms:
                idx = mid
                lo = mid + 1
            else:
                hi = mid - 1
        # 行切换 -> 触发入场/退场动画与羽毛
        if idx != self.current_index and idx >= 0:
            prev_text = self.lines[self.current_index][1] if 0 <= self.current_index < len(self.lines) else ""
            self.fx.on_line_changed(idx, self._line_row_y, self._line_h, prev_text=prev_text)
        self.current_index = idx
        self.update()

    def _resize_to_content(self):
        if not self.lines:
            return
        n = min(len(self.lines), self.visible_lines)
        line_h = self.cfg["font_size"] + self.line_spacing
        h = 40 + n * line_h + (20 if self.translated else 0)
        w = self.cfg.get("width", 1000)
        geom = self.geometry()
        self.setGeometry(geom.x(), geom.y(), w, max(160, h))
        if self.ambient and len(self._rain) != self.ambient_density:
            self._rebuild_rain()

    # ---------- 绘制 ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        fx_on = self.fx.enabled
        w, h = self.width(), self.height()

        # ---- 特效背景层：雾气流动 + 远景羽毛 ----
        if fx_on:
            self.fx.draw_background(painter, w, h)
        # 氛围雨滴（忧郁主题，与特效互斥但两者都开也共存无妨）
        if self.ambient and self._rain:
            self._draw_rain(painter)

        if not self.lines:
            painter.setFont(self.font)
            painter.setPen(QColor("#888888"))
            painter.drawText(self.rect(), Qt.AlignCenter, "♪  等待播放...")
            if not self.locked:
                self._draw_unlock_indicator(painter)
            return

        idx = max(0, self.current_index)
        line_h = self.cfg["font_size"] + self.line_spacing
        visible = self.visible_lines
        anchor = min(1, max(0, visible - 1))
        start = max(0, idx - anchor)
        start = min(start, max(0, len(self.lines) - visible))
        y_base = 24
        self._line_row_y = y_base + anchor * line_h
        self._line_h = line_h

        # ---- 特效：上一行交叠退场 ----
        if fx_on:
            prev = self.fx.prev_line_state()
            if prev:
                p_text, p_y, p_h, p_alpha, p_blur, p_spread = prev
                if p_alpha > 0:
                    self._draw_fading_line(painter, p_text, p_y, p_h, p_alpha, p_blur, p_spread)

        for i in range(start, min(len(self.lines), start + visible)):
            ms, text = self.lines[i]
            row = i - start
            y = y_base + row * line_h

            if i == self.current_index:
                if self.accent_line:
                    self._draw_accent_line(painter, y, line_h)
                if fx_on:
                    elapsed = self.fx.time_ms - self.fx.line_start_ms
                    self._draw_effect_line(painter, text, y, line_h, elapsed)
                    # 微光呼吸：整体亮度轻微波动
                    if self.fx.on_breath:
                        pass  # 呼吸已并入逐字 alpha，避免重复叠加
                else:
                    self._draw_highlight_line(painter, text, y, line_h)
                if self.show_translation and self.translated:
                    trans_text = self._find_translation(ms)
                    if trans_text:
                        p = QFont(self.font)
                        p.setPointSize(max(10, self.cfg["font_size"] - 8))
                        painter.setFont(p)
                        painter.setPen(self.color_translated)
                        painter.drawText(20, int(y + line_h - 2), trans_text)
                        painter.setFont(self.font)
            else:
                painter.setFont(self.font)
                self._draw_outlined_text(
                    painter, 20, int(y + self.cfg["font_size"]), text, self.color_normal
                )

        # ---- 特效前景层：微粒 + 近景羽毛 + 扫光 ----
        if fx_on:
            self.fx.draw_foreground(painter, w, h)
            sweep = self.fx.sweep_pos()
            if sweep >= 0:
                cy = y_base + anchor * line_h
                self._draw_sweep(painter, cy, line_h, sweep)

        if self.show_line_number:
            self._draw_line_number(painter, idx)

        if not self.locked:
            self._draw_unlock_indicator(painter)

    # ---------- 雾中飞羽 · 特效绘制 ----------
    def _draw_blurred_text(self, painter, x, y, text, color, alpha=1.0, blur=0.0):
        """用多层微偏移半透明绘制模拟"从雾中浮现"的羽化（Canvas shadowBlur 的等价）。

        blur=0 时只画一次（清晰），blur 越大层数与偏移越多、单层越淡。
        """
        if alpha <= 0:
            return
        c = QColor(color)
        c.setAlpha(int(max(0, min(1, alpha)) * 255))
        if blur <= 0.02:
            self._fill_text_path(painter, x, y, text, c)
            return
        # 羽化：3-5 层，偏移随 blur 增大，权重递减；中心层最清晰
        layers = 4
        max_off = self.fx.blur_max * blur
        painter.save()
        for k in range(layers):
            t = k / max(1, layers - 1)
            off = max_off * (t - 0.5) * 2
            layer_c = QColor(c)
            layer_c.setAlpha(int(c.alpha() * (0.12 + 0.22 * (1 - t))))
            self._fill_text_path(painter, x + off, y + off * 0.25, text, layer_c)
        # 中心清晰层
        center = QColor(c)
        center.setAlpha(int(c.alpha() * (0.55 + 0.45 * (1 - blur))))
        self._fill_text_path(painter, x, y, text, center)
        painter.restore()

    def _fill_text_path(self, painter, x, y, text, color):
        path = QPainterPath()
        path.addText(x, y, self.font, text)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPath(path)

    def _draw_outline_for_text(self, painter, x, y, text, alpha=1.0):
        """柔光描边：极细、低透明，绝不做霓虹描边。"""
        if not self.fx.on_soft or self.outline_width <= 0:
            return
        path = QPainterPath()
        path.addText(x, y, self.font, text)
        pen = QColor(0, 0, 0)
        pen.setAlpha(int(150 * alpha))
        painter.setPen(QPen(pen, max(1, self.outline_width - 1), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    def _draw_effect_line(self, painter, text, y, line_h, elapsed):
        """当前行：逐字从雾中浮现 + 上浮 + 柔光 + 高亮进度填充。"""
        baseline = int(y + self.cfg["font_size"])
        x = 20
        fm = QFontMetrics(self.font)
        # 先按进度算出整行高亮宽度（沿用逐字填充语义）
        state = self.monitor.snapshot()
        pos_ms = state.get("position_ms", 0)
        cur_ms = self.lines[self.current_index][0] if self.current_index >= 0 else 0
        next_ms = (self.lines[self.current_index + 1][0]
                   if self.current_index + 1 < len(self.lines) else cur_ms + 3000)
        progress = max(0.0, min(1.0, (pos_ms - cur_ms) / (next_ms - cur_ms))) if next_ms > cur_ms else 0.0
        total_w = fm.horizontalAdvance(text)
        hl_px = total_w * progress

        breathe = self.fx.breathe()
        cx = x
        for i, ch in enumerate(text):
            a, blur, rise, float_y = self.fx.char_state(i, elapsed)
            if a <= 0:
                cx += fm.horizontalAdvance(ch)
                continue
            char_w = fm.horizontalAdvance(ch)
            cy = baseline - rise + float_y
            col = self.color_highlight if (cx < x + hl_px) else self.color_normal
            self._draw_outline_for_text(painter, cx, cy, ch, a)
            self._draw_blurred_text(painter, cx, cy, ch, col, a * breathe, blur)
            cx += char_w

        # 柔光晕（沿已高亮部分），非霓虹：低透明柔和矩形
        if self.fx.on_soft and self.glow_enabled and hl_px > 0:
            painter.save()
            painter.setPen(Qt.NoPen)
            g = QColor(self.color_glow)
            g.setAlpha(46)
            painter.setBrush(QBrush(g))
            r = self.glow_radius
            painter.drawRoundedRect(x - r, int(y + 2), int(hl_px) + r * 2, int(line_h - 6), r, r)
            painter.restore()

    def _draw_fading_line(self, painter, text, y, line_h, alpha, blur, spread):
        """上一行交叠退场：渐隐 + 羽化扩散。"""
        if alpha <= 0:
            return
        painter.save()
        offset = -spread
        self._draw_blurred_text(
            painter, 20 + offset, int(y + self.cfg["font_size"] + offset),
            text, self.color_normal, alpha, max(blur, 0.3)
        )
        painter.restore()

    def _draw_sweep(self, painter, y, line_h, pos):
        """轻微光线扫过文字：一条低透明斜向高光，随时间循环。"""
        w = self.width()
        sweep_x = -w * 0.3 + pos * w * 1.6
        grad = QLinearGradient(sweep_x, 0, sweep_x + w * 0.25, 0)
        grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        grad.setColorAt(0.5, QColor(242, 246, 250, 28))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRect(0, int(y), w, int(line_h))
        painter.restore()

    def _draw_line_number(self, painter, idx):
        """在窗口右上角绘制「当前行 / 总行数」。"""
        total = len(self.lines)
        cur = idx + 1  # 行号从 1 开始
        rf_font = QFont(self.font)
        rf_font.setPointSize(max(9, self.cfg["font_size"] - 12))
        rf_font.setBold(False)
        painter.save()
        painter.setFont(rf_font)
        # 用高亮色的低透明版本，弱化存在感又不至于看不清
        c = QColor(self.color_highlight)
        c.setAlpha(170)
        pen = QPen(c, 1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawText(
            0, 6, self.width() - 14, 20,
            Qt.AlignRight | Qt.AlignTop, f"{cur} / {total}"
        )
        painter.restore()

    def _draw_rain(self, painter):
        """绘制雨滴（忧郁主题氛围）。"""
        painter.save()
        color = QColor(self.ambient_color)
        for drop in self._rain:
            c = QColor(color)
            c.setAlpha(drop.alpha)
            pen = QPen(c, 1.0)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            x, y = int(drop.x), int(drop.y)
            painter.drawLine(x, y, x - 2, y + int(drop.length))
        painter.restore()

    def _draw_accent_line(self, painter, y, line_h):
        """当前行左侧的竖向强调线。"""
        r = self.glow_radius
        c = QColor(self.color_highlight)
        c.setAlpha(210)
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(c))
        painter.drawRoundedRect(QRect(8, int(y + 2), 3, int(line_h - 8)), 2, 2)
        # 顶端小圆点
        painter.drawEllipse(int(9 - r / 4), int(y + 2 - r / 4), max(3, r // 2), max(3, r // 2))
        painter.restore()

    def _draw_unlock_indicator(self, painter):
        """解锁时的可拖动视觉提示。"""
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        painter.setPen(QPen(QColor(255, 200, 80, 220), 2, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
        tip_font = QFont(self.font)
        tip_font.setPointSize(max(9, self.cfg["font_size"] - 6))
        tip_font.setBold(True)
        painter.setFont(tip_font)
        bar_h = tip_font.pointSize() + 10
        bar_y = self.height() - bar_h - 4
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(30, 30, 30, 210)))
        painter.drawRoundedRect(6, bar_y, self.width() - 12, bar_h, 4, 4)
        painter.setPen(QColor("#FFC857"))
        painter.drawText(
            12, bar_y, self.width() - 24, bar_h,
            Qt.AlignLeft | Qt.AlignVCenter,
            "已解锁 - 拖动窗口 / 单击歌词行对齐 / 右键菜单",
        )

    def _find_translation(self, ms):
        best = ""
        for t_ms, t_text in self.translated:
            if t_ms <= ms:
                best = t_text
            else:
                break
        return best

    def _draw_highlight_line(self, painter, text, y, line_h):
        """逐字高亮：按进度从左到右填充高亮色。"""
        state = self.monitor.snapshot()
        pos_ms = state.get("position_ms", 0)
        cur_ms = self.lines[self.current_index][0] if self.current_index >= 0 else 0
        next_ms = (
            self.lines[self.current_index + 1][0]
            if self.current_index + 1 < len(self.lines)
            else cur_ms + 3000
        )
        progress = 0.0
        if next_ms > cur_ms:
            progress = max(0.0, min(1.0, (pos_ms - cur_ms) / (next_ms - cur_ms)))

        painter.setFont(self.font)
        x = 20
        baseline = int(y + self.cfg["font_size"])

        # 整行描边底色
        self._draw_outlined_text(painter, x, baseline, text, self.color_normal)

        fm = QFontMetrics(self.font)
        total_w = fm.horizontalAdvance(text)
        hl_w = int(total_w * progress)

        if hl_w > 0:
            if self.glow_enabled:
                painter.save()
                painter.setPen(Qt.NoPen)
                glow = QColor(self.color_glow)
                glow.setAlpha(90)
                painter.setBrush(QBrush(glow))
                r = self.glow_radius
                painter.drawRoundedRect(x - r, y + 2, hl_w + r * 2, line_h - 4, r, r)
                painter.restore()

            painter.save()
            path = QPainterPath()
            path.addRect(QRect(x, y, hl_w, line_h))
            painter.setClipPath(path)
            self._draw_outlined_text(painter, x, baseline, text, self.color_highlight)
            painter.restore()

    def _draw_outlined_text(self, painter, x, y, text, color):
        """带描边的文字：先粗描边再填色。"""
        w = self.outline_width
        path = QPainterPath()
        path.addText(x, y, self.font, text)
        if w > 0:
            painter.setPen(QPen(QColor(0, 0, 0, 220), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPath(path)

    # ---------- 交互 ----------
    def mousePressEvent(self, event):
        if not self.locked:
            if event.button() == Qt.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.pos()
            elif event.button() == Qt.RightButton:
                self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if not self.locked and self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        if not self.locked and self._drag_pos is not None:
            if event.button() == Qt.LeftButton:
                press_global = self._drag_pos + self.pos()
                if (event.globalPosition().toPoint() - press_global).manhattanLength() < 5:
                    self._align_to_clicked_line(event.position().toPoint())
            self._drag_pos = None
            self.cfg["position"]["x"] = self.x()
            self.cfg["position"]["y"] = self.y()
            save_config(self.cfg)

    def _needs_calibration(self):
        """是否需要/支持时间轴校准。

        CDP/SMTC 模式进度精确，校准无效；只有标题模式（本地估算）才需要。
        """
        return self.monitor.snapshot().get("source") == "title"

    def _align_to_clicked_line(self, pos):
        """点击歌词行，把播放进度对齐到该行时间戳（仅标题模式有效）。"""
        if not self.lines or not self._needs_calibration():
            return
        line_h = self.cfg["font_size"] + self.line_spacing
        row = int((pos.y() - 24) // line_h)
        anchor = min(1, max(0, self.visible_lines - 1))
        start = max(0, self.current_index - anchor)
        start = min(start, max(0, len(self.lines) - self.visible_lines))
        target = start + row
        if 0 <= target < len(self.lines):
            self.monitor.align_to(self.lines[target][0])
            self.current_index = target
            self.update()

    def _show_context_menu(self, pos):
        menu = QMenu()
        menu.addAction(self._lock_menu_text(), self._toggle_lock)
        menu.addAction("下一个主题 (Ctrl+Alt+T)", self._next_theme)
        # 校准入口仅在标题模式（进度为本地估算）下显示
        if self._needs_calibration():
            menu.addAction("对齐到当前行", lambda: self.monitor.align_to(self.lines[self.current_index][0]) if self.lines else None)
            menu.addAction("重置时间校准", lambda: self.monitor.reset_offset())
        menu.addAction("打开设置", self._open_settings)
        menu.addSeparator()
        menu.addAction("上一首", lambda: self.monitor.prev_track())
        menu.addAction("播放/暂停", lambda: self.monitor.toggle_play())
        menu.addAction("下一首", lambda: self.monitor.next_track())
        menu.addSeparator()
        menu.addAction("隐藏", self.hide)
        menu.exec(pos)

    def _toggle_lock(self):
        self.locked = not self.locked
        self.cfg["locked"] = self.locked
        self.set_click_through(self.cfg["click_through"] and self.locked)
        save_config(self.cfg)
        act = getattr(self, "_lock_action", None)
        if act is not None:
            act.setText(self._lock_menu_text())
        self.update()

    def _lock_menu_text(self):
        return "锁定歌词（鼠标穿透）" if not self.locked else "解锁歌词（可拖动）"

    def _refresh_theme_menu(self):
        """同步托盘主题菜单的勾选状态。"""
        acts = getattr(self, "_theme_actions", None)
        if not acts:
            return
        cur = self.cfg.get("theme", "classic")
        for key, act in acts.items():
            act.setChecked(key == cur)

    def _next_theme(self):
        """切换到下一个主题（由 main 注入 cycle_theme 回调）。"""
        cyc = getattr(self, "_cycle_theme", None)
        if cyc:
            cyc()

    def _open_settings(self):
        dlg = SettingsDialog(
            self.cfg, self, on_switch_theme=getattr(self, "_switch_theme", None)
        )
        if dlg.exec() == QDialog.Accepted:
            self.apply_config()
            self._resize_to_content()
            self._refresh_theme_menu()
            save_config(self.cfg)

    def toggle_visible(self):
        self.setVisible(not self.isVisible())
