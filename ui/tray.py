# -*- coding: utf-8 -*-
"""系统托盘构建。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QIcon

from themes import theme_list


def _make_icon():
    """生成一个简易托盘图标：红色圆底 + 白色音符。"""
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
    return QIcon(pix)


def build_tray(app, window, monitor, on_switch_theme, needs_calibration=lambda: False):
    """构建系统托盘。

    on_switch_theme(name): 切换主题的回调（由 main 注入）。
    needs_calibration(): 返回是否处于标题模式（仅此时显示时间校准项）。
    """
    tray = QSystemTrayIcon(_make_icon(), app)
    tray.setToolTip("桌面歌词")
    menu = QMenu()

    menu.addAction("显示/隐藏歌词", window.toggle_visible)
    lock_action = menu.addAction(window._lock_menu_text(), window._toggle_lock)
    window._lock_action = lock_action

    # 外观主题子菜单（遍历主题列表，新增主题自动出现）
    theme_menu = menu.addMenu("外观主题")
    theme_actions = {}
    for key, label, icon_char in theme_list():
        act = theme_menu.addAction(f"{icon_char}  {label}")
        act.setCheckable(True)
        act.triggered.connect(lambda checked=False, k=key: on_switch_theme(k))
        theme_actions[key] = act
    window._theme_actions = theme_actions
    window._refresh_theme_menu()

    menu.addSeparator()
    menu.addAction("上一首", lambda: monitor.prev_track())
    menu.addAction("播放/暂停", lambda: monitor.toggle_play())
    menu.addAction("下一首", lambda: monitor.next_track())
    # 校准入口仅在标题模式显示（CDP 精确进度下无效）
    if needs_calibration():
        menu.addSeparator()
        menu.addAction("歌词时间 +2s", lambda: monitor.adjust(2000))
        menu.addAction("歌词时间 -2s", lambda: monitor.adjust(-2000))
        menu.addAction("重置时间校准", monitor.reset_offset)
    menu.addSeparator()
    menu.addAction("设置", window._open_settings)
    menu.addAction("退出", app.quit)
    tray.setContextMenu(menu)

    tray.activated.connect(
        lambda reason: window.toggle_visible()
        if reason == QSystemTrayIcon.Trigger else None
    )
    tray.show()
    return tray
