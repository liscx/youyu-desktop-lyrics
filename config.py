# -*- coding: utf-8 -*-
"""配置管理：读写 config.json，提供默认值。"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

DEFAULTS = {
    # 歌词源: auto(本地优先+网络兜底) / local / network
    "source": "auto",
    # 网易云歌词缓存目录（留空自动探测）
    "netease_lyric_dir": "",
    # 外观
    "font_family": "Microsoft YaHei",
    "font_size": 30,
    "font_bold": True,
    "color_normal": "#B7B7B7",
    "color_highlight": "#FFFFFF",
    "color_translated": "#9A9A9A",
    "color_glow": "#4A90E2",
    "glow_enabled": True,
    "outline_width": 3,
    "line_spacing": 12,
    # 窗口
    "opacity": 0.92,
    "click_through": True,
    "locked": True,
    "position": {"x": None, "y": None},
    "width": 1000,
    # 行为
    "show_translation": True,
    "refresh_ms": 80,
}


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            cfg.update(user)
            if isinstance(user.get("position"), dict):
                cfg["position"] = {**DEFAULTS["position"], **user["position"]}
        except Exception:
            pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)
    return CACHE_DIR
