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
    QPen, QPainterPath,
)

from core.config import save_config
from core.lyrics import get_lyrics
from ui.hotkey import set_click_through


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
        self.current_index = idx
        self.update()

    def _resize_to_content(self):
        if not self.lines:
            return
        n = min(len(self.lines), 4)
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

        # 氛围粒子在最底层
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
        start = max(0, idx - 1)
        visible = 4
        y_base = 24

        for i in range(start, min(len(self.lines), start + visible)):
            ms, text = self.lines[i]
            row = i - start
            y = y_base + row * line_h

            if i == self.current_index:
                # 当前行左侧强调竖线（忧郁主题）
                if self.accent_line:
                    self._draw_accent_line(painter, y, line_h)
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

        if not self.locked:
            self._draw_unlock_indicator(painter)

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

    def _align_to_clicked_line(self, pos):
        """点击歌词行，把播放进度对齐到该行时间戳。"""
        if not self.lines:
            return
        line_h = self.cfg["font_size"] + self.line_spacing
        row = int((pos.y() - 24) // line_h)
        start = max(0, self.current_index - 1)
        target = start + row
        if 0 <= target < len(self.lines):
            self.monitor.align_to(self.lines[target][0])
            self.current_index = target
            self.update()

    def _show_context_menu(self, pos):
        menu = QMenu()
        menu.addAction(self._lock_menu_text(), self._toggle_lock)
        menu.addAction("下一个主题 (Ctrl+Alt+T)", self._next_theme)
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
