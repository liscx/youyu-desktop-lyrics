# -*- coding: utf-8 -*-
"""主题系统：可插拔的外观模式。

每个主题是一组外观参数的字典。切换主题时，把这些参数覆盖进 cfg，
再让窗口 apply_config() 重新读取即可即时生效，无需重启。

新增主题只需三步：
  1. 在 THEMES 里加一个字典（字段参考 THEME_FIELDS）
  2. 在设置面板/托盘的主题列表里会自动出现（遍历 THEMES）
  3. 若需要专属绘制效果，在 ui/lyric_window.py 里按 theme 名分支
"""
from copy import deepcopy

# 主题可覆盖的字段（与 core/config.py 的 DEFAULTS 外观键一致）
THEME_FIELDS = (
    "font_family", "font_size", "font_bold",
    "color_normal", "color_highlight", "color_reading", "color_translated", "color_glow",
    "glow_enabled", "glow_radius", "outline_width", "line_spacing",
    "opacity", "show_translation",
    "ambient", "ambient_density", "ambient_color", "accent_line",
)

# ---------------- 经典：当前设计，保持不变 ----------------
CLASSIC = {
    "label": "经典",
    "icon": "♪",
    "params": {
        "font_family": "Microsoft YaHei",
        "font_size": 30,
        "font_bold": True,
        "color_normal": "#B7B7B7",
        "color_highlight": "#FFFFFF",
        "color_reading": "#B7B7B7",         # 当前行读条未经过的字，默认同普通色
        "color_translated": "#9A9A9A",
        "color_glow": "#4A90E2",
        "glow_enabled": True,
        "glow_radius": 6,
        "outline_width": 3,
        "line_spacing": 12,
        "opacity": 0.92,
        "show_translation": True,
        "ambient": False,
        "ambient_density": 46,
        "ambient_color": "#9FC6FF",
        "accent_line": False,
    },
}

# ---------------- 忧郁：冷蓝灰 + 雨滴 + 细衬线 + 强调竖线 ----------------
MELANCHOLY = {
    "label": "忧郁",
    "icon": "☂",
    "params": {
        "font_family": "Microsoft YaHei",
        "font_size": 32,
        "font_bold": False,                 # 纤细，不张扬
        "color_normal": "#6E7C93",          # 雾蓝灰
        "color_highlight": "#DCE6F1",       # 雨夜冷白
        "color_reading": "#6E7C93",         # 默认同普通色
        "color_translated": "#5A6880",      # 更沉的蓝灰
        "color_glow": "#3E5A8C",            # 深海蓝微光
        "glow_enabled": True,
        "glow_radius": 10,                  # 光晕更柔更大
        "outline_width": 4,                 # 描边更厚，雨夜更清晰
        "line_spacing": 20,                 # 行距疏朗，留白更多
        "opacity": 0.88,
        "show_translation": True,
        "ambient": True,                    # 开启雨滴粒子
        "ambient_density": 55,
        "ambient_color": "#7FA8D8",         # 雨丝冷蓝
        "accent_line": True,                # 当前行左侧竖线
    },
}

# ---------------- 霓虹：高对比青品红光晕 ----------------
NEON = {
    "label": "霓虹",
    "icon": "✦",
    "params": {
        "font_family": "Microsoft YaHei",
        "font_size": 30,
        "font_bold": True,
        "color_normal": "#4C6A72",
        "color_highlight": "#00FFF0",       # 青
        "color_reading": "#4C6A72",         # 默认同普通色
        "color_translated": "#3E6E78",
        "color_glow": "#FF2E88",            # 品红
        "glow_enabled": True,
        "glow_radius": 14,
        "outline_width": 4,
        "line_spacing": 14,
        "opacity": 0.95,
        "show_translation": True,
        "ambient": False,
        "ambient_density": 46,
        "ambient_color": "#00FFF0",
        "accent_line": False,
    },
}

# ---------------- 雾中飞羽：电影感空灵特效（月白/雾灰/淡蓝）----------------
MIST = {
    "label": "雾中飞羽",
    "icon": "❧",
    "params": {
        "font_family": "Microsoft YaHei",
        "font_size": 31,
        "font_bold": False,
        "color_normal": "#9FAEBD",          # 雾灰
        "color_highlight": "#F2F6FA",       # 月白
        "color_reading": "#9FAEBD",         # 当前行未读字，默认同普通色
        "color_translated": "#8B9AA9",      # 淡蓝灰
        "color_glow": "#C7D8E8",            # 银白微光（非霓虹）
        "glow_enabled": True,
        "glow_radius": 9,
        "outline_width": 2,                 # 细描边，避免廉价感
        "line_spacing": 18,
        "opacity": 0.93,
        "show_translation": True,
        "ambient": False,                   # 关掉旧雨滴，改用羽毛特效
        "ambient_density": 0,
        "ambient_color": "#DCE6F1",
        "accent_line": False,
    },
    # 该主题专属的文字动效参数（合并进 cfg['fx']）。
    # 飘落粒子改由飞行物系统管理，主题只通过 feather_color 注入飞行物配色。
    "fx": {
        "enabled": True,
        "feather_color": "#DCE6F1",  # 注入飞行物引擎的主题色
        "char_reveal": True,
        "breathing": True,
        "float": True,
        "crossfade": True,
        "soft_glow": True,
        "word_dissolve": True,
        "follow_dissolve": True,
    },
}

THEMES = {
    "classic": CLASSIC,
    "melancholy": MELANCHOLY,
    "neon": NEON,
    "mist": MIST,
}

DEFAULT_THEME = "classic"


def get_theme(name):
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def theme_list():
    """返回 [(key, label, icon), ...]，供 UI 遍历。"""
    return [(k, v["label"], v["icon"]) for k, v in THEMES.items()]


def apply_theme(cfg, name):
    """把主题参数覆盖进 cfg，并设置 cfg['theme']。返回 cfg。

    若主题定义了 ``fx`` 子字典，则合并进 cfg['fx']（未列出的键保持原值），
    让不同主题自带契合的特效配置。
    """
    theme = get_theme(name)
    for key, value in theme["params"].items():
        cfg[key] = deepcopy(value)
    if "fx" in theme:
        fx = cfg.setdefault("fx", {})
        fx.update(deepcopy(theme["fx"]))
    cfg["theme"] = name if name in THEMES else DEFAULT_THEME
    return cfg
