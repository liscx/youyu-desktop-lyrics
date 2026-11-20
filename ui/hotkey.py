# -*- coding: utf-8 -*-
"""全局热键（Windows）与点击穿透等 Win32 工具。

热键：
  Ctrl+Alt+L  解锁/锁定歌词
  Ctrl+Alt+T  循环切换外观主题
  Ctrl+Alt+H  显示/隐藏歌词
穿透状态下鼠标点不到窗口，必须靠热键/托盘操作，所以这套基础设施独立成模块。
"""
import ctypes
import ctypes.wintypes

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
WM_HOTKEY = 0x0312
VK_L = 0x4C
VK_T = 0x54
VK_H = 0x48

# (id, 修饰键, 虚拟键) —— 每个热键一个唯一 ID
HOTKEYS = {
    "lock":   (0x4C4C21, MOD_CONTROL | MOD_ALT, VK_L),
    "theme":  (0x4C4C22, MOD_CONTROL | MOD_ALT, VK_T),
    "toggle": (0x4C4C23, MOD_CONTROL | MOD_ALT, VK_H),
}
# WM_HOTKEY 的 wParam -> 语义名
_ID_TO_NAME = {cfg[0]: name for name, cfg in HOTKEYS.items()}


def make_hotkey_filter(QAbstractNativeEventFilter):
    """工厂：注入 Qt 的原生事件过滤器基类，返回热键过滤器类。"""

    class GlobalHotkeyFilter(QAbstractNativeEventFilter):
        def __init__(self, callbacks):
            super().__init__()
            # callbacks: {"lock": fn, "theme": fn, "toggle": fn}
            self.callbacks = callbacks

        def nativeEventFilter(self, event_type, message):
            try:
                if event_type in ("windows_generic_MSG", b"windows_generic_MSG"):
                    msg = ctypes.wintypes.MSG.from_address(int(message))
                    if msg.message == WM_HOTKEY:
                        name = _ID_TO_NAME.get(msg.wParam)
                        cb = self.callbacks.get(name) if name else None
                        if cb:
                            cb()
            except Exception:
                pass
            return False, 0

    return GlobalHotkeyFilter


def register_all_hotkeys():
    """注册全部热键，返回 {name: bool}。"""
    result = {}
    for name, (hid, mods, vk) in HOTKEYS.items():
        try:
            result[name] = bool(user32.RegisterHotKey(None, hid, mods, vk))
        except Exception:
            result[name] = False
    return result


def unregister_all_hotkeys():
    for hid, _mods, _vk in HOTKEYS.values():
        try:
            user32.UnregisterHotKey(None, hid)
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
