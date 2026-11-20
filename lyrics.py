# -*- coding: utf-8 -*-
"""歌词模块：本地缓存扫描、网易云接口、LRCLIB 兜底、LRC/逐字解析。"""
import os
import re
import json
import time
import hashlib
import requests
from config import CACHE_DIR, ensure_cache_dir

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ---------- LRC 解析 ----------
_TS_RE = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")


def _parse_ts(ts_text):
    m = _TS_RE.match(ts_text)
    if not m:
        return None
    minute = int(m.group(1))
    sec = int(m.group(2))
    frac = m.group(3) or "0"
    ms = int(frac.ljust(3, "0")[:3])
    return minute * 60000 + sec * 1000 + ms


def parse_lrc(lrc_text):
    """解析标准 LRC，返回 [(ms, text), ...] 已排序。"""
    lines = []
    if not lrc_text:
        return lines
    for raw in lrc_text.splitlines():
        stamps = _TS_RE.findall(raw)
        if not stamps:
            continue
        text = _TS_RE.sub("", raw).strip()
        if not text:
            continue
        for minute, sec, frac in stamps:
            ms = int(minute) * 60000 + int(sec) * 1000 + int((frac or "0").ljust(3, "0")[:3])
            lines.append((ms, text))
    lines.sort(key=lambda x: x[0])
    return lines


def parse_klyric(klyric_text):
    """解析网易云逐字歌词 YRC/增强 LRC，返回 [(ms, text), ...]。
    网易云 klyric 形如: [00:00.00]字(100,200)字(300,400) 或 <00:00.00> 格式。"""
    lines = []
    if not klyric_text:
        return lines
    # 逐字格式: \uE??? 或 (ms,ms) ; 这里做增强 LRC: [00:00.00]文(100,200)字
    word_re = re.compile(r"(.)(?:\((\d+),(\d+)\))?")
    for raw in klyric_text.splitlines():
        if not raw.strip():
            continue
        # 行首时间戳
        head = _TS_RE.match(raw)
        if not head:
            continue
        line_ms = _parse_ts(head.group(0))
        body = raw[head.end():]
        words = []
        for m in word_re.finditer(body):
            ch, s, e = m.group(1), m.group(2), m.group(3)
            if ch.isspace():
                continue
            if s and e:
                words.append((line_ms + int(s), ch))
            else:
                words.append((line_ms, ch))
        if words:
            lines.extend(words)
    lines.sort(key=lambda x: x[0])
    return lines


# ---------- 网易云接口 ----------
def netease_search(keyword, limit=6):
    """通过网易云搜索接口按关键词找歌曲 id（返回公开接口）。"""
    url = "https://music.163.com/api/search/get/web"
    data = {"s": keyword, "type": 1, "offset": 0, "limit": limit}
    try:
        r = requests.post(url, data=data, headers={**UA, "Referer": "https://music.163.com"}, timeout=10)
        obj = r.json()
        songs = obj.get("result", {}).get("songs", [])
        return [(s.get("id"), s.get("name", ""), (s.get("artists") or [{}])[0].get("name", "")) for s in songs]
    except Exception:
        return []


def netease_lyric(song_id):
    """按 song id 获取歌词，返回 (lrc, klyric, translated_lrc)。"""
    url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=-1&kv=-1&tv=-1"
    try:
        r = requests.get(url, headers={**UA, "Referer": "https://music.163.com"}, timeout=10)
        obj = r.json()
        return (
            obj.get("lrc", {}).get("lyric", ""),
            obj.get("klyric", {}).get("lyric", ""),
            obj.get("tlyric", {}).get("lyric", ""),
        )
    except Exception:
        return "", "", ""


# ---------- LRCLIB 兜底 ----------
def lrclib_search(title, artist=""):
    """返回 (synced_lrc, plain_lrc)。"""
    params = {"track_name": title}
    if artist:
        params["artist_name"] = artist
    try:
        r = requests.get("https://lrclib.net/api/search", params=params, headers=UA, timeout=10)
        arr = r.json()
        if not arr:
            return "", ""
        return arr[0].get("syncedLyrics", "") or "", arr[0].get("plainLyrics", "") or ""
    except Exception:
        return "", ""


# ---------- 本地缓存 ----------
def scan_local_cache(custom_dir=""):
    """扫描网易云本地歌词缓存目录，返回 {songid: lrc_text}。"""
    candidates = []
    if custom_dir:
        candidates.append(custom_dir)
    profile = os.environ.get("USERPROFILE", "")
    candidates += [
        os.path.join(profile, "AppData", "Local", "Netease", "CloudMusic", "webdata", "lyric"),
        os.path.join(profile, "AppData", "Roaming", "Netease", "CloudMusic", "Cache", "lyric"),
    ]
    result = {}
    for d in candidates:
        if not d or not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            path = os.path.join(d, name)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "rb") as f:
                    head = f.read(512)
                if b"[" not in head and b"lyric" not in head:
                    continue
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                key = os.path.splitext(name)[0]
                result[key] = text
            except Exception:
                continue
    return result


def cache_key(title, artist):
    raw = f"{artist}||{title}".lower().strip()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def save_lyric_cache(title, artist, lrc_lines, translated=None):
    ensure_cache_dir()
    data = {
        "title": title,
        "artist": artist,
        "ts": time.time(),
        "lines": lrc_lines,
        "translated": translated or [],
    }
    path = os.path.join(CACHE_DIR, cache_key(title, artist) + ".json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass
    return path


def load_lyric_cache(title, artist, max_age=86400 * 7):
    path = os.path.join(CACHE_DIR, cache_key(title, artist) + ".json")
    if not os.path.exists(path):
        return None
    try:
        if time.time() - os.path.getmtime(path) > max_age:
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------- 统一获取入口 ----------
def get_lyrics(title, artist, source="auto", local_index=None):
    """返回 dict: {lines:[(ms,text)], translated:[(ms,text)], source:str}"""
    if not title:
        return {"lines": [], "translated": [], "source": "none"}

    # 1) 本地缓存（工具自身）
    cached = load_lyric_cache(title, artist)
    if cached and source in ("auto", "local"):
        return {
            "lines": [tuple(x) for x in cached.get("lines", [])],
            "translated": [tuple(x) for x in cached.get("translated", [])],
            "source": "tool-cache",
        }

    # 2) 网易云本地歌词缓存（按歌名模糊匹配文件名需 id，先用网络拿 id）
    # 3) 网络：网易云接口 -> LRCLIB
    if source in ("auto", "network"):
        results = netease_search(f"{artist} {title}".strip())
        chosen_id = None
        for sid, name, ar in results:
            if title and (title in name or name in title):
                chosen_id = sid
                break
        if chosen_id is None and results:
            chosen_id = results[0][0]

        if chosen_id:
            lrc, klyric, tlyric = netease_lyric(chosen_id)
            lines = parse_lrc(lrc)
            translated = parse_lrc(tlyric)
            if not lines and klyric:
                lines = parse_klyric(klyric)
            if lines:
                save_lyric_cache(title, artist, lines, translated)
                return {"lines": lines, "translated": translated, "source": "netease"}

        synced, plain = lrclib_search(title, artist)
        lines = parse_lrc(synced)
        if lines:
            save_lyric_cache(title, artist, lines, [])
            return {"lines": lines, "translated": [], "source": "lrclib"}

    return {"lines": [], "translated": [], "source": "none"}
