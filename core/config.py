# -*- coding: utf-8 -*-
"""配置管理：读写 config.json，提供默认值。

config.json 与 cache/ 始终位于项目根目录（core/ 的上一级），
与模块文件位置解耦，方便工程分层重构。
"""
import json
import os

# 项目根目录 = 本文件所在 core/ 的上一级
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

DEFAULTS = {
    # 当前外观主题（见 themes/presets.py）
    "theme": "classic",
    # 歌词源: auto(本地优先+网络兜底) / local / network
    "source": "auto",
    # 网易云歌词缓存目录（留空自动探测）
    "netease_lyric_dir": "",
    # 外观（会被所选主题覆盖，这里的取值 = classic 经典主题）
    "font_family": "Microsoft YaHei",
    "font_size": 30,
    "font_bold": True,
    "color_normal": "#B7B7B7",
    "color_highlight": "#FFFFFF",
    "color_translated": "#9A9A9A",
    "color_glow": "#4A90E2",
    "glow_enabled": True,
    "glow_radius": 6,
    "outline_width": 3,
    "line_spacing": 12,
    "opacity": 0.92,
    # 主题专属开关
    "ambient": False,          # 氛围粒子（忧郁主题 = 雨滴）
    "ambient_density": 46,     # 粒子数量
    "ambient_color": "#9FC6FF",  # 粒子颜色
    "accent_line": False,      # 当前行左侧强调竖线
    # 窗口
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
