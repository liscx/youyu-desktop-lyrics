# -*- coding: utf-8 -*-
"""播放监控模块。

数据源（按优先级）：
  1. SMTC（部分播放器注册，能拿到精确进度）—— 自动检测
  2. 网易云窗口标题（歌名 - 歌手），进度本地估算 + 用户校准

控制：Windows 媒体键（VK_MEDIA_*），网易云已验证响应。
"""
import ctypes
import threading
import time

from ctypes import wintypes

user32 = ctypes.windll.user32

# 媒体键
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

# ---- SMTC 可选 ----
try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )
except Exception:
    MediaManager = None

# ---- CDP 精确进度（最高优先级）----
try:
    from .cdp import CDPClient
except Exception:
    CDPClient = None


def _all_windows():
    """枚举所有顶层窗口（含隐藏），返回 (hwnd, pid, class, title)。"""
    result = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lparam):
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        if n > 0:
            user32.GetWindowTextW(hwnd, buf, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        result.append((hwnd, pid.value, cls.value, buf.value))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return result


def _netease_pids():
    """获取所有 cloudmusic.exe 进程 PID（纯 Win32，避免 subprocess 阻塞线程）。"""
    import ctypes
    from ctypes import wintypes
    pids = set()
    TH32CS_SNAPPROCESS = 0x00000002
    kernel32 = ctypes.windll.kernel32

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
        ]

    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return pids
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
            while True:
                if pe.szExeFile.lower() == "cloudmusic.exe":
                    pids.add(pe.th32ProcessID)
                if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                    break
    finally:
        kernel32.CloseHandle(snap)
    return pids


def find_netease_window():
    """找到网易云当前播放标题 (hwnd, title)。

    兼容：主窗口隐藏(最小化到托盘)、迷你播放器模式。
    从网易云进程的窗口中取带 '歌名 - 歌手' 格式的标题。
    """
    pids = _netease_pids()
    windows = _all_windows()

    # 优先：这些类的窗口标题通常是 "歌名 - 歌手"
    preferred_classes = ("OrpheusBrowserHost", "icon", "MiniPlayer")
    title_classes = []
    for hwnd, pid, cls, title in windows:
        if pid in pids and title and cls in preferred_classes:
            title_classes.append((hwnd, title, cls))

    # 选带分隔符 " - " 的标题（歌名 - 歌手）
    for hwnd, title, cls in title_classes:
        if " - " in title:
            return hwnd, title
    if title_classes:
        return title_classes[0][0], title_classes[0][1]

    # 兜底：任意网易云窗口带 " - " 标题
    for hwnd, pid, cls, title in windows:
        if pid in pids and title and " - " in title and "GDI" not in cls:
            return hwnd, title
    return None, ""


def _parse_title(title):
    """从 '歌名 - 歌手' 解析 (歌名, 歌手)。"""
    if not title:
        return "", ""
    seps = [" - ", " – ", " — "]
    for sep in seps:
        if sep in title:
            parts = title.split(sep)
            if len(parts) >= 2:
                return parts[0].strip(), parts[-1].strip()
    return title.strip(), ""


class MediaMonitor:
    """后台线程监控网易云播放状态。"""

    def __init__(self, interval=0.3, use_smtc=False):
        self.interval = interval
        self.use_smtc = use_smtc  # 网易云不注册 SMTC，默认关闭以免空转
        self.state = {
            "title": "", "artist": "", "status": "stopped",
            "position": 0.0, "duration": 0.0, "source": "title",
        }
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._last_title = ""
        self._track_start = 0.0
        self._smtc_updated = 0.0
        self._paused_at = 0.0
        self._paused_total = 0.0
        self._key_changed = False
        self._offset_ms = 0  # 当前歌曲校准偏移
        self._offsets = {}   # 每首歌独立的校准偏移: "歌手||歌名" -> ms
        self._current_song_key = ""
        # CDP 精确进度：自动探测端口，可用时作为最高优先级数据源
        self.cdp = None
        self._cdp_failed_at = 0.0  # 探测失败节流，避免频繁重试
        if CDPClient is not None:
            try:
                if CDPClient.probe_port():
                    self.cdp = CDPClient()
            except Exception:
                self.cdp = None

    def adjust(self, delta_ms):
        """用户手动校准歌词时间轴（毫秒）。按当前歌曲保存。"""
        with self._lock:
            self._offset_ms += delta_ms
            self._offsets[self._current_song_key] = self._offset_ms
            self._key_changed = True

    def reset_offset(self):
        with self._lock:
            self._offset_ms = 0
            self._offsets[self._current_song_key] = 0
            self._key_changed = True

    def align_to(self, target_ms):
        """把当前歌词时间轴对齐到 target_ms（点击歌词行校准）。

        CDP/SMTC 模式下进度是精确的，无需偏移（校准无意义）；仅标题模式需要偏移。
        """
        with self._lock:
            if self.state["source"] in ("cdp", "smtc"):
                # 精确进度模式：校准偏移不生效，直接忽略
                self._offset_ms = 0
            else:
                current = (time.time() - self._track_start - self._paused_total) * 1000
                self._offset_ms = int(target_ms - current)
                self._offsets[self._current_song_key] = self._offset_ms
            self._key_changed = True

    # ---------- SMTC 检测 ----------
    def _try_smtc(self):
        """返回 (title, artist, status, position, duration) 或 None。"""
        if MediaManager is None:
            return None
        try:
            import asyncio

            async def get():
                m = await MediaManager.request_async()
                s = m.get_current_session()
                if s is None:
                    return None
                p = await s.try_get_media_properties_async()
                pb = s.get_playback_info()
                tl = s.get_timeline_properties()
                name = pb.playback_status.name if pb else ""
                status = "playing" if name == "PLAYING" else ("paused" if name == "PAUSED" else "stopped")
                return (
                    p.title or "" if p else "",
                    p.artist or "" if p else "",
                    status,
                    tl.position.total_seconds() if tl else 0.0,
                    tl.end_time.total_seconds() if tl else 0.0,
                )

            return asyncio.run(get())
        except Exception:
            return None

    # ---------- 主循环 ----------
    def _loop(self):
        while self._running:
            try:
                self._poll()
            except Exception:
                pass
            time.sleep(self.interval)

    def _try_cdp(self):
        """尝试用 CDP 读取精确播放状态，返回 dict 或 None。"""
        if self.cdp is None:
            return None
        # 失败后节流：3 秒内不再重试
        if not self.cdp._ready and (time.time() - self._cdp_failed_at) < 3.0:
            return None
        try:
            snap = self.cdp.snapshot()
            if snap and snap.get("title") and snap.get("positionMs") is not None:
                return snap
        except Exception:
            pass
        if not self.cdp._ready:
            self._cdp_failed_at = time.time()
        return None

    def _poll(self):
        # 优先级 1：CDP 精确进度
        cdp = self._try_cdp()
        if cdp:
            title = cdp.get("title", "")
            artist = cdp.get("artist", "")
            status = cdp.get("state", "unknown")
            if status not in ("playing", "paused"):
                status = "playing"
            pos_s = (cdp.get("positionMs") or 0) / 1000.0
            dur_s = (cdp.get("durationMs") or 0) / 1000.0
            with self._lock:
                song_key = f"{artist}||{title}"
                changed = song_key != self._current_song_key
                self.state.update({
                    "title": title, "artist": artist, "status": status,
                    "position": pos_s, "duration": dur_s, "source": "cdp",
                })
                # CDP 模式下进度精确，用 position 直接驱动，无需本地计时
                self._current_song_key = song_key
                if changed:
                    self._offset_ms = 0
                    self._key_changed = True
                self._last_title = f"{title} - {artist}"
            return

        smtc = self._try_smtc() if self.use_smtc else None
        with self._lock:
            if smtc and smtc[0]:
                title, artist, status, pos, dur = smtc
                self.state.update({
                    "title": title, "artist": artist, "status": status,
                    "position": pos, "duration": dur, "source": "smtc",
                })
                self._smtc_updated = time.time()
                if (title, artist) != (self._last_title.split(" - ")[0], self._last_title.split(" - ")[-1]):
                    self._key_changed = True
                self._last_title = f"{title} - {artist}"
                return

            # 窗口标题模式
            hwnd, title = find_netease_window()
            if not title:
                self.state["status"] = "stopped"
                return
            song, artist = _parse_title(title)
            changed = song != self.state["title"]
            if changed:
                self._current_song_key = f"{artist}||{song}"
                self.state["title"] = song
                self.state["artist"] = artist
                self.state["source"] = "title"
                self._track_start = time.time()
                self._paused_total = 0.0
                # 恢复这首歌上次校准的偏移（没有则 0）
                self._offset_ms = self._offsets.get(self._current_song_key, 0)
                self._key_changed = True
            # 标题模式下假设正在播放（网易云最小化到托盘时窗口可能隐藏）
            self.state["status"] = "playing"

    def snapshot(self):
        with self._lock:
            s = dict(self.state)
            if s["source"] == "cdp":
                # CDP 进度精确且实时，直接用，不加偏移
                s["position_ms"] = int(s["position"] * 1000)
                s["duration_ms"] = int(s["duration"] * 1000)
                return s
            elif s["source"] == "smtc":
                # SMTC position 不连续更新，按时间差外推
                if s["status"] == "playing" and self._smtc_updated:
                    s["position"] += time.time() - self._smtc_updated
            else:
                if s["status"] == "playing":
                    s["position"] = time.time() - self._track_start - self._paused_total
            s["position_ms"] = int(s["position"] * 1000) + self._offset_ms
            s["duration_ms"] = int(s["duration"] * 1000)
            return s

    def consume_key_change(self):
        with self._lock:
            v = self._key_changed
            self._key_changed = False
            return v

    # ---------- 控制 ----------
    @staticmethod
    def _media_key(vk):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)

    def toggle_play(self):
        self._media_key(VK_MEDIA_PLAY_PAUSE)

    def next_track(self):
        self._media_key(VK_MEDIA_NEXT_TRACK)

    def prev_track(self):
        self._media_key(VK_MEDIA_PREV_TRACK)

    # ---------- 生命周期 ----------
    def start(self):
        """兼容旧接口；实际改为主线程 QTimer 驱动 poll()，不启动后台线程。

        后台线程里的 ctypes/EnumWindows 回调会持有 GIL，阻塞 Qt 事件循环，
        导致定时器与绘制全部停摆，因此改为单线程轮询。
        """
        pass

    def stop(self):
        self._running = False

    def poll(self):
        """由主线程定时器调用，刷新当前播放状态。"""
        self._poll()
