# -*- coding: utf-8 -*-
"""桌面歌词工具 - 程序入口。

只负责组装各层：core（数据）/ themes（外观）/ ui（界面）。
业务逻辑见各子包，勿在此堆砌。
"""
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtGui import QKeySequence, QShortcut

from core.config import load_config, save_config
from core.media import MediaMonitor
from themes import THEMES, apply_theme, DEFAULT_THEME
from ui.lyric_window import LyricWindow
from ui.tray import build_tray
from ui.hotkey import (
    make_hotkey_filter, register_all_hotkeys, unregister_all_hotkeys,
)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    cfg = load_config()
    # 若配置里没有合法主题，回退到经典
    if cfg.get("theme") not in THEMES:
        apply_theme(cfg, DEFAULT_THEME)

    monitor = MediaMonitor()
    monitor.start()

    window = LyricWindow(cfg, monitor)
    window.show()
    if cfg.get("click_through", True) and cfg.get("locked", True):
        window.set_click_through(True)

    # ---- 主题切换逻辑 ----
    def switch_theme(name, save=True):
        """切换主题：应用参数 -> 重绘 -> 同步菜单 -> 可选保存。"""
        apply_theme(cfg, name)
        window.apply_config()
        window._resize_to_content()
        window._refresh_theme_menu()
        if save:
            save_config(cfg)

    def cycle_theme():
        keys = list(THEMES.keys())
        cur = cfg.get("theme", DEFAULT_THEME)
        nxt = keys[(keys.index(cur) + 1) % len(keys)] if cur in keys else keys[0]
        switch_theme(nxt)

    # 注入给窗口（右键菜单 / 设置面板 / 托盘共用同一套逻辑）
    window._switch_theme = switch_theme
    window._cycle_theme = cycle_theme

    # ---- 托盘 ----
    build_tray(app, window, monitor, on_switch_theme=switch_theme)

    # ---- 全局热键 ----
    HotkeyFilter = make_hotkey_filter(QAbstractNativeEventFilter)
    hotkey_filter = HotkeyFilter({
        "lock": window._toggle_lock,
        "theme": cycle_theme,
        "toggle": window.toggle_visible,
    })
    app.installNativeEventFilter(hotkey_filter)
    register_all_hotkeys()

    # ---- 快捷键校准 ----
    s_right = QShortcut(QKeySequence("Ctrl+Right"), window)
    s_right.activated.connect(lambda: monitor.adjust(2000))
    s_left = QShortcut(QKeySequence("Ctrl+Left"), window)
    s_left.activated.connect(lambda: monitor.adjust(-2000))

    try:
        sys.exit(app.exec())
    finally:
        unregister_all_hotkeys()


if __name__ == "__main__":
    main()
