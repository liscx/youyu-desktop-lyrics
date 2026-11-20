# -*- coding: utf-8 -*-
"""网易云 CDP 精确播放进度读取模块。

通过 Chrome DevTools Protocol 连接到网易云的渲染进程，注入 JS 访问其
webpack store，读取当前播放进度 positionMs / durationMs / 状态。

前提：网易云需开启调试端口（默认 21631）。开启方式见 setup_cdp.py。
"""
import json
import time
import threading
import urllib.request

try:
    import websocket  # websocket-client
except Exception:
    websocket = None

CDP_PORT = 21631

# 注入到页面的桥接脚本：建立到网易云 store 的连接，并订阅进度事件。
# 结果挂在 window.__dgMusic 上，供后续 evaluate 轮询读取。
BRIDGE_JS = r"""
(() => {
  if (window.__dgMusic && window.__dgMusic.ready) return 'exists';
  // 等待应用启动完成
  if (typeof window._enterAppTime === 'number' && !window.__dgReadyWait) {
    // 应用仍在初始化，稍后重试
  }
  let loader = window.__dgLoader;
  if (!loader) {
    if (window.webpackJsonp && typeof window.webpackJsonp.push === 'function') {
      const modules = {}; const key = 'dgBridge' + Date.now();
      modules[key] = function (module, exports, require) { loader = require; };
      window.webpackJsonp.push([[key], modules, [[key]]]);
    } else {
      const chunks = Object.keys(window).find(k => k.startsWith('webpackChunk') && Array.isArray(window[k]));
      if (chunks) {
        const key = 'dgBridge' + Date.now();
        window[chunks].push([[key], {}, require => { loader = require; }]);
      }
    }
    if (loader) window.__dgLoader = loader;
  }
  if (!loader || !loader.c) return 'no-loader';
  const exports = Object.values(loader.c).map(m => m && m.exports).filter(Boolean);
  const tool = exports.map(e => e.a).find(e => e && typeof e.getStore === 'function' && typeof e.getDispatch === 'function');
  const store = tool && tool.app && tool.app._store;
  const player = exports.map(e => e.AudioPlayer).find(e => e && typeof e.subscribePlayStatus === 'function');
  const storage = exports.map(e => e.b).find(e => e && e.lastPlaying && typeof e.lastPlaying.get === 'function');
  if (!store || typeof store.getState !== 'function') return 'no-store';

  const bridge = window.__dgMusic = { ready: true, positionMs: null, positionTrack: '', latest: {} };
  const songId = p => String((p.trackFileType === 'local' && p.onlineResourceId) || p.resourceTrackId || p.curPlaying?.resourceId || '');
  const clean = v => typeof v === 'string' ? v.slice(0, 1024) : '';
  const modes = ['playOrder', 'playCycle', 'playOneCycle', 'playRandom'];
  const info = () => {
    const s = store.getState(), p = s.playing, t = p.curTrack || p.curPlaying?.track || {}, id = songId(p);
    const rawDur = t.duration ?? t.dt;
    const duration = Number.isFinite(rawDur) && rawDur > 0 ? rawDur : null;
    const title = clean(p.resourceName || t.name);
    if (id !== bridge.positionTrack) { bridge.positionMs = null; bridge.positionTrack = id; }
    const artist = (p.resourceArtists || t.artists || t.ar || []).map(a => clean(a.name)).filter(Boolean).join(' / ');
    const state = p.playingState === 2 ? 'playing' : p.playingState === 1 ? 'paused' : 'unknown';
    return { title, artist, songId: /^\d+$/.test(id) ? id : '',
             durationMs: duration, positionMs: bridge.positionMs,
             state, mode: modes.includes(p.playingMode) ? p.playingMode : '' };
  };
  bridge.info = info;
  const validEvent = ev => {
    if (!ev || typeof ev.playId !== 'string') return false;
    const p = store.getState().playing, id = songId(p);
    return !!id && ev.playId.split('_')[0] === id;
  };
  // 订阅播放器进度事件（原版用配置对象 {type, callback}）
  const onProgress = ev => {
    if (validEvent(ev) && Number.isFinite(ev.current) && ev.current >= 0) {
      bridge.positionTrack = songId(store.getState().playing);
      bridge.positionMs = ev.current * 1000;
    }
  };
  const onSeek = ev => {
    if (validEvent(ev) && Number.isFinite(ev.position) && ev.position >= 0 && (ev.code === undefined || ev.code === 0)) {
      bridge.positionTrack = songId(store.getState().playing);
      bridge.positionMs = ev.position * 1000;
    }
  };
  if (player && typeof player.subscribePlayStatus === 'function') {
    try {
      player.subscribePlayStatus({ type: 'playprogress', callback: onProgress });
      player.subscribePlayStatus({ type: 'seek', callback: onSeek });
    } catch (e) {
      // 兜底：直接传回调
      try { player.subscribePlayStatus(onProgress); } catch (e2) {}
    }
  }
  // 读取暂停时保存的进度
  const restoreSaved = () => {
    const p = store.getState().playing, id = songId(p);
    if (!storage || p.playingState !== 1 || !id || (bridge.positionMs !== null && bridge.positionTrack === id)) return;
    Promise.resolve(storage.lastPlaying.get()).then(saved => {
      if (p.playingState !== 1 || String(saved?.trackId) !== id || !Number.isFinite(saved?.current)) return;
      if (bridge.positionMs !== null && bridge.positionTrack === id) return;
      bridge.positionTrack = id; bridge.positionMs = saved.current * 1000;
    }).catch(() => {});
  };
  if (typeof store.subscribe === 'function') {
    try { store.subscribe(() => { restoreSaved(); }); } catch (e) {}
  }
  restoreSaved();
  // 兜底：从 store 里直接找进度字段
  const probe = () => {
    const p = store.getState().playing;
    for (const k of ['currentTime', 'position', 'playedTime', 'progress', 'currentPosition']) {
      if (Number.isFinite(p[k]) && p[k] >= 0) {
        if (bridge.positionMs === null) { bridge.positionTrack = songId(p); bridge.positionMs = p[k] > 1000 ? p[k] : p[k] * 1000; }
      }
    }
  };
  probe();
  return 'ok';
})()
"""

# 轮询读取脚本
POLL_JS = r"""
(() => {
  const b = window.__dgMusic;
  if (!b || !b.ready) return JSON.stringify({ready:false});
  const snap = b.info ? b.info() : {};
  return JSON.stringify({ready:true, ...snap});
})()
"""


class CDPClient:
    """网易云 CDP 客户端。"""

    def __init__(self, port=CDP_PORT):
        self.port = port
        self.ws = None
        self._id = 0
        self._lock = threading.Lock()
        self._ready = False
        self._bridge_done = False
        self._last_error = ""

    @staticmethod
    def probe_port(port=CDP_PORT, timeout=2):
        """检查 CDP 端口是否开放且返回 /json。"""
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/json",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            data = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
            pages = json.loads(data)
            return pages if isinstance(pages, list) else None
        except Exception:
            return None

    def connect(self):
        """连接到网易云播放页面。"""
        if websocket is None:
            self._last_error = "缺少 websocket-client 库"
            return False
        pages = self.probe_port(self.port)
        if not pages:
            self._last_error = f"端口 {self.port} 未开放或未返回 /json"
            return False
        # 找 page 类型的 target（播放主页面）
        ws_url = None
        for pg in pages:
            if pg.get("type") == "page" and pg.get("webSocketDebuggerUrl"):
                url = pg["webSocketDebuggerUrl"]
                # 检查 url 是否属于音乐播放页
                ws_url = url
                if "music" in pg.get("url", "") or "/index" in pg.get("url", ""):
                    break
        if not ws_url:
            self._last_error = "未找到可用的页面 target"
            return False
        try:
            self.ws = websocket.create_connection(
                ws_url, timeout=5, suppress_origin=True,
                header=["Host: 127.0.0.1:%d" % self.port],
            )
            self._ready = True
            self._last_error = ""
            return True
        except Exception as e:
            self._last_error = f"WebSocket 连接失败: {e}"
            return False

    def _call(self, method, params=None, timeout=5):
        """发送 CDP 命令并等待对应 id 的响应。"""
        if not self.ws:
            return None
        with self._lock:
            self._id += 1
            mid = self._id
        msg = {"id": mid, "method": method, "params": params or {}}
        try:
            self.ws.send(json.dumps(msg))
        except Exception as e:
            self._last_error = f"发送失败: {e}"
            self._ready = False
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.ws.settimeout(max(0.1, deadline - time.time()))
                raw = self.ws.recv()
            except Exception:
                return None
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if obj.get("id") == mid:
                return obj
        return None

    def evaluate(self, expression, timeout=5):
        """执行 JS 表达式，返回值。"""
        resp = self._call("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": False,
        }, timeout=timeout)
        if not resp:
            return None
        result = resp.get("result", {}).get("result", {})
        if "value" in result:
            return result["value"]
        # 异常
        exc = resp.get("result", {}).get("exceptionDetails")
        if exc:
            self._last_error = str(exc.get("text", "JS异常"))
        return None

    def install_bridge(self, force=False):
        """注入桥接脚本。force=True 时清除旧桥接重新注入。"""
        if force:
            self.evaluate("delete window.__dgMusic; delete window.__dgLoader; 'cleared'", timeout=5)
        r = self.evaluate(BRIDGE_JS, timeout=8)
        self._bridge_done = r in ("ok", "exists")
        return self._bridge_done

    def snapshot(self):
        """读取当前播放快照。返回 dict 或 None。"""
        if not self._ready:
            if not self.connect():
                return None
        if not self._bridge_done:
            if not self.install_bridge():
                # 应用可能还没启动完，重试
                self._bridge_done = False
                return None
        raw = self.evaluate(POLL_JS, timeout=5)
        if not raw:
            return None
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return None
        if not obj.get("ready"):
            self._bridge_done = False
            return None
        return obj

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        self._ready = False
        self._bridge_done = False


if __name__ == "__main__":
    pages = CDPClient.probe_port()
    print("CDP 端口探测:", "开放" if pages else "未开放")
    if pages:
        for pg in pages:
            print("  ", pg.get("type"), pg.get("url", "")[:80])
        c = CDPClient()
        if c.connect():
            print("连接成功, 安装桥接:", c.install_bridge())
            for i in range(3):
                print("快照:", c.snapshot())
                time.sleep(2)
            c.close()
        else:
            print("连接失败:", c._last_error)
