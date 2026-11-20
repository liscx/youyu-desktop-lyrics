# -*- coding: utf-8 -*-
"""桌面歌词工具 - 主程序。

功能：
  - 悬浮置顶歌词窗，鼠标点击穿透
  - 逐行/逐字高亮跟随
  - 系统托盘 + 设置面板（字体、颜色、透明度、格式）
  - 播放控制（媒体键）+ 歌词时间轴校准
"""
import os
import sys
import ctypes
import ctypes.wintypes

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QSystemTrayIcon, QMenu, QDialog,
    QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton, QSlider,
    QCheckBox, QFontComboBox, QSpinBox, QColorDialog, QMessageBox,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer, QPoint, QSettings, QRect, QAbstractNativeEventFilter
from PySide6.QtGui import (
    QPainter, QColor, QFont, QFontMetrics, QLinearGradient, QBrush,
    QPen, QIcon, QPixmap, QPainterPath, QCursor, QKeySequence, QShortcut,
)

from config import load_config, save_config
from media import MediaMonitor
from lyrics import get_lyrics

user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080

# 全局热键：Ctrl+Alt+L 切换锁定（穿透状态下鼠标点不到窗口，必须靠热键/托盘）
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
HOTKEY_ID = 0x4C4C21
WM_HOTKEY = 0x0312
VK_L = 0x4C


class GlobalHotkeyFilter(QAbstractNativeEventFilter):
    """接收 Windows 全局热键消息（Ctrl+Alt+L）。"""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        try:
            if event_type in ("windows_generic_MSG", b"windows_generic_MSG"):
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    self.callback()
        except Exception:
            pass
        return False, 0


def register_hotkey():
    """注册 Ctrl+Alt+L，返回是否成功。"""
    try:
        ok = user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT, VK_L)
        return bool(ok)
    except Exception:
        return False


def unregister_hotkey():
    try:
        user32.UnregisterHotKey(None, HOTKEY_ID)
    except Exception:
        pass


def set_click_through(hwnd, enabled):
    """切换窗口点击穿透。"""
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if enabled:
        style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
    else:
        style &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


def color_dialog_button(parent, color, callback):
    btn = QPushButton(color)
    btn.setObjectName("colorBtn")

    def pick():
        c = QColorDialog.getColor(QColor(color), parent, "选择颜色")
        if c.isValid():
            btn.setText(c.name())
            btn.setStyleSheet(f"background:{c.name()};color:{'#000' if c.lightness()>128 else '#fff'};")
            callback(c.name())

    btn.setStyleSheet(f"background:{color};color:{'#000' if QColor(color).lightness()>128 else '#fff'};padding:4px;border-radius:4px;")
    btn.clicked.connect(pick)
    return btn


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

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
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
        h = max(160, 60 + len(self.lines) * (self.cfg["font_size"] + self.cfg["line_spacing"]))
        if pos.get("x") is None:
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - w) // 2
            y = screen.height() - 220
        else:
            x, y = pos["x"], pos["y"]
        self.setGeometry(x, y, w, h)

    def apply_config(self):
        self.setWindowOpacity(self.cfg.get("opacity", 0.92))
        self.font = QFont(self.cfg["font_family"], self.cfg["font_size"])
        self.font.setBold(self.cfg.get("font_bold", True))
        self.color_normal = QColor(self.cfg["color_normal"])
        self.color_highlight = QColor(self.cfg["color_highlight"])
        self.color_translated = QColor(self.cfg["color_translated"])
        self.color_glow = QColor(self.cfg["color_glow"])
        self.glow_enabled = self.cfg.get("glow_enabled", True)
        self.show_translation = self.cfg.get("show_translation", True)
        self.line_spacing = self.cfg.get("line_spacing", 12)
        self.outline_width = self.cfg.get("outline_width", 3)
        self.click_through = self.cfg.get("click_through", True)
        self.locked = self.cfg.get("locked", True)
        # 只有锁定且开启穿透时才穿透
        effective = self.click_through and self.locked
        self.set_click_through(effective)

    def set_click_through(self, enabled):
        self.winId()  # 确保原生窗口已创建
        hwnd = int(self.winId())
        set_click_through(hwnd, enabled)

    # ---------- 歌词更新 ----------
    def update_lyric(self):
        self.monitor.poll()  # 主线程轮询（避免后台线程 ctypes 回调持有 GIL 阻塞 Qt 事件循环）
        state = self.monitor.snapshot()
        key = f"{state['artist']}||{state['title']}"
        if not state["title"]:
            self.lines = []
            self.update()
            return

        # 切换歌曲 -> 加载歌词
        if key != self.lyric_key:
            self.lyric_key = key
            result = get_lyrics(state["title"], state["artist"], self.cfg.get("source", "auto"))
            self.lines = result["lines"]
            self.translated = result["translated"] if self.show_translation else []
            self.current_index = -1
            self._resize_to_content()

        if not self.lines:
            self.update()
            return

        pos_ms = state.get("position_ms", 0)
        # 二分查找当前行
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

    # ---------- 绘制 ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if not self.lines:
            painter.setFont(self.font)
            painter.setPen(QColor("#888888"))
            painter.drawText(self.rect(), Qt.AlignCenter, "♪  等待播放...")
            if not self.locked:
                self._draw_unlock_indicator(painter)
            return

        idx = self.current_index
        if idx < 0:
            idx = 0
        line_h = self.cfg["font_size"] + self.line_spacing
        # 显示当前行前后几行
        start = max(0, idx - 1)
        visible = 4
        y_base = 24
        fm = QFontMetrics(self.font)

        for i in range(start, min(len(self.lines), start + visible)):
            ms, text = self.lines[i]
            row = i - start
            y = y_base + row * line_h

            # 当前行高亮：按字符渐变填充
            if i == self.current_index:
                self._draw_highlight_line(painter, text, y, line_h)
                # 翻译行
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
                painter.setPen(self._outline_pen(self.color_normal))
                # 描边
                self._draw_outlined_text(painter, 20, int(y + self.cfg["font_size"]), text, self.color_normal)

        if not self.locked:
            self._draw_unlock_indicator(painter)

    def _draw_unlock_indicator(self, painter):
        """解锁时在窗口边缘画出可拖动的视觉提示。"""
        # 半透明底色 + 边框，让用户看清窗口边界
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        painter.setPen(QPen(QColor(255, 200, 80, 220), 2, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
        # 底部提示条（避开歌词，放在窗口最下方）
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
        painter.drawText(12, bar_y, self.width() - 24, bar_h,
                         Qt.AlignLeft | Qt.AlignVCenter, "已解锁 - 拖动窗口 / 单击歌词行对齐 / 右键菜单")

    def _find_translation(self, ms):
        best = ""
        for t_ms, t_text in self.translated:
            if t_ms <= ms:
                best = t_text
            else:
                break
        return best

    def _draw_highlight_line(self, painter, text, y, line_h):
        """逐字高亮：根据当前进度从左到右填充高亮色。"""
        state = self.monitor.snapshot()
        pos_ms = state.get("position_ms", 0)
        cur_ms = self.lines[self.current_index][0] if self.current_index >= 0 else 0
        next_ms = self.lines[self.current_index + 1][0] if self.current_index + 1 < len(self.lines) else cur_ms + 3000
        progress = 0.0
        if next_ms > cur_ms:
            progress = max(0.0, min(1.0, (pos_ms - cur_ms) / (next_ms - cur_ms)))

        font = self.font
        painter.setFont(font)
        x = 20
        baseline = int(y + self.cfg["font_size"])

        # 先画整行描边底色
        self._draw_outlined_text(painter, x, baseline, text, self.color_normal)

        # 计算高亮宽度
        fm = QFontMetrics(font)
        total_w = fm.horizontalAdvance(text)
        hl_w = int(total_w * progress)

        if hl_w > 0:
            # 发光效果
            if self.glow_enabled:
                painter.save()
                painter.setPen(Qt.NoPen)
                glow = QColor(self.color_glow)
                glow.setAlpha(90)
                painter.setBrush(QBrush(glow))
                painter.drawRoundedRect(x - 4, y + 2, hl_w + 8, line_h - 4, 6, 6)
                painter.restore()

            # 高亮文字（裁剪）
            painter.save()
            path = QPainterPath()
            path.addRect(QRect(x, y, hl_w, line_h))
            painter.setClipPath(path)
            self._draw_outlined_text(painter, x, baseline, text, self.color_highlight)
            painter.restore()

    def _outline_pen(self, color):
        return QPen(color)

    def _draw_outlined_text(self, painter, x, y, text, color):
        """带描边的文字。"""
        w = self.outline_width
        if w > 0:
            painter.setPen(QPen(QColor(0, 0, 0, 200), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        else:
            painter.setPen(Qt.NoPen)
        fm = QFontMetrics(self.font)
        # 用 drawText 路径实现描边：先粗描边再填色
        path = QPainterPath()
        path.addText(x, y, self.font, text)
        painter.setPen(QPen(QColor(0, 0, 0, 220), w))
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
                # 单击（未拖动）歌词行 -> 对齐到该行
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
        line_h = self.cfg["font_size"] + self.cfg["line_spacing"]
        row = int((pos.y() - 24) // line_h)
        start = max(0, self.current_index - 1)
        target = start + row
        if 0 <= target < len(self.lines):
            self.monitor.align_to(self.lines[target][0])
            self.current_index = target
            self.update()

    def _show_context_menu(self, pos):
        menu = QMenu()
        lock_item = menu.addAction(self._lock_menu_text(), self._toggle_lock)
        menu.addAction("对齐到当前行（点击行也可）", lambda: self.monitor.align_to(self.lines[self.current_index][0]) if self.lines else None)
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
        # 同步托盘菜单文字 + 立即重绘提示
        act = getattr(self, "_lock_action", None)
        if act is not None:
            act.setText(self._lock_menu_text())
        self.update()

    def _lock_menu_text(self):
        return "锁定歌词（鼠标穿透）" if not self.locked else "解锁歌词（可拖动）"

    def _open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec() == QDialog.Accepted:
            self.apply_config()
            self._resize_to_content()
            save_config(self.cfg)

    def toggle_visible(self):
        self.setVisible(not self.isVisible())


class SettingsDialog(QDialog):
    """设置面板。"""

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("桌面歌词 - 设置")
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        # 字体
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(self.cfg["font_family"]))
        form.addRow("字体", self.font_combo)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(12, 80)
        self.size_spin.setValue(self.cfg["font_size"])
        form.addRow("字号", self.size_spin)

        self.bold_check = QCheckBox("粗体")
        self.bold_check.setChecked(self.cfg["font_bold"])
        form.addRow("", self.bold_check)

        # 颜色
        self.normal_btn = color_dialog_button(self, self.cfg["color_normal"], lambda c: None)
        form.addRow("普通歌词颜色", self.normal_btn)

        self.highlight_btn = color_dialog_button(self, self.cfg["color_highlight"], lambda c: None)
        form.addRow("高亮颜色", self.highlight_btn)

        self.translate_btn = color_dialog_button(self, self.cfg["color_translated"], lambda c: None)
        form.addRow("翻译颜色", self.translate_btn)

        self.glow_btn = color_dialog_button(self, self.cfg["color_glow"], lambda c: None)
        form.addRow("光晕颜色", self.glow_btn)

        self.glow_check = QCheckBox("启用高亮光晕")
        self.glow_check.setChecked(self.cfg["glow_enabled"])
        form.addRow("", self.glow_check)

        self.trans_check = QCheckBox("显示翻译歌词")
        self.trans_check.setChecked(self.cfg["show_translation"])
        form.addRow("", self.trans_check)

        # 透明度
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(self.cfg["opacity"] * 100))
        form.addRow("窗口透明度", self.opacity_slider)

        # 行距
        self.spacing_spin = QSpinBox()
        self.spacing_spin.setRange(0, 40)
        self.spacing_spin.setValue(self.cfg["line_spacing"])
        form.addRow("行间距", self.spacing_spin)

        layout.addLayout(form)

        # 提示
        tip = QLabel(
            "提示：锁定状态下鼠标穿透歌词窗，方便操作桌面。\n"
            "解锁方法（三选一）：按 Ctrl+Alt+L / 右键托盘图标选“解锁歌词” / 右键歌词窗。\n"
            "解锁后可拖动窗口、单击某行歌词对齐进度；再按 Ctrl+Alt+L 重新锁定。\n"
            "Ctrl+←/→ 微调歌词时间轴（±2 秒）。"
        )
        tip.setStyleSheet("color:#888;font-size:11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        buttons = QHBoxLayout()
        ok = QPushButton("确定")
        ok.clicked.connect(self._apply)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def _apply(self):
        self.cfg.update({
            "font_family": self.font_combo.currentFont().family(),
            "font_size": self.size_spin.value(),
            "font_bold": self.bold_check.isChecked(),
            "color_normal": self.normal_btn.text(),
            "color_highlight": self.highlight_btn.text(),
            "color_translated": self.translate_btn.text(),
            "color_glow": self.glow_btn.text(),
            "glow_enabled": self.glow_check.isChecked(),
            "show_translation": self.trans_check.isChecked(),
            "opacity": self.opacity_slider.value() / 100,
            "line_spacing": self.spacing_spin.value(),
        })
        self.accept()


def build_tray(app, window, monitor, cfg):
    """构建系统托盘。"""
    # 简易图标
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#EC4141"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(8, 8, 48, 48)
    p.setPen(QColor("white"))
    p.setFont(QFont("Arial", 30, QFont.Bold))
    p.drawText(pix.rect(), Qt.AlignCenter, "♪")
    p.end()
    icon = QIcon(pix)

    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("桌面歌词")
    menu = QMenu()

    menu.addAction("显示/隐藏歌词", window.toggle_visible)
    lock_action = menu.addAction(window._lock_menu_text(), window._toggle_lock)
    window._lock_action = lock_action
    menu.addSeparator()
    menu.addAction("上一首", lambda: monitor.prev_track())
    menu.addAction("播放/暂停", lambda: monitor.toggle_play())
    menu.addAction("下一首", lambda: monitor.next_track())
    menu.addSeparator()
    menu.addAction("歌词时间 +2s", lambda: monitor.adjust(2000))
    menu.addAction("歌词时间 -2s", lambda: monitor.adjust(-2000))
    menu.addAction("重置时间校准", monitor.reset_offset)
    menu.addSeparator()
    menu.addAction("设置", window._open_settings)
    menu.addAction("退出", app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: window.toggle_visible() if reason == QSystemTrayIcon.Trigger else None)
    tray.show()
    return tray


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    cfg = load_config()
    monitor = MediaMonitor()
    monitor.start()

    window = LyricWindow(cfg, monitor)
    window.show()
    if cfg.get("click_through", True) and cfg.get("locked", True):
        window.set_click_through(True)

    tray = build_tray(app, window, monitor, cfg)

    # 全局热键 Ctrl+Alt+L 切换锁定（穿透状态下唯一可靠的解锁方式之一）
    hotkey_ok = register_hotkey()
    hotkey_filter = GlobalHotkeyFilter(window._toggle_lock)
    app.installNativeEventFilter(hotkey_filter)

    # 快捷键校准
    s_right = QShortcut(QKeySequence("Ctrl+Right"), window)
    s_right.activated.connect(lambda: monitor.adjust(2000))
    s_left = QShortcut(QKeySequence("Ctrl+Left"), window)
    s_left.activated.connect(lambda: monitor.adjust(-2000))

    try:
        sys.exit(app.exec())
    finally:
        unregister_hotkey()


if __name__ == "__main__":
    main()
