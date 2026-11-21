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

# 雾中飞羽特效：每个动画模块独立开关 + 参数（见 ui/effects.py）
FX_DEFAULTS = {
    "enabled": True,             # 特效总开关
    # 时间 / 强度 / 距离
    "fade_in_ms": 900,           # 入场时长
    "fade_out_ms": 700,          # 退场时长
    "blur_max": 7,               # 羽化模糊最大程度(0-12)
    "rise_px": 12,               # 入场文字上浮距离(px)
    "char_stagger_ms": 60,       # 逐字浮现的每字延迟(ms)
    "float_px": 3,               # 整体上下浮动幅度(px)
    "float_ms": 5200,            # 浮动周期(ms)
    "breath_pct": 0.10,          # 微光呼吸幅度(0-0.5)
    "breath_ms": 3600,           # 呼吸周期(ms)
    "sweep_ms": 4200,            # 扫光周期(ms)
    "sweep_alpha": 34,           # 光条峰值透明度(0-80)
    "sweep_fade_start": 55,      # 光条从 55% 处开始渐隐(0-95)，到右边界归零，避免硬切
    "batch_gap_ms": 220,         # 整批补位时上一批完全消失到下一批出现的间隔(ms)
    # 逐字化羽消散：歌词消失时从左到右化为羽毛，向左上方飘散
    "word_dissolve": True,       # 逐字消散（关闭则退回整行渐隐）
    "dissolve_char_ms": 360,     # 单个字化羽时长(ms)
    "dissolve_stagger_ms": 420,  # 整行从左到右化羽的延迟跨度(ms)
    "dissolve_drift_x": 22,      # 消散文字向左漂移(px)
    "dissolve_drift_y": 34,      # 消散文字向上漂移(px)
    "mist_speed": 0.15,          # 雾气流动速度
    "mist_alpha": 26,            # 雾气不透明度(0-80)
    "feather_alpha": 150,        # 羽毛不透明度(0-255)
    "feather_color": "#DCE6F1",  # 羽毛/微粒颜色
    "mist_color": "#B7C6D8",     # 雾气颜色
    "easing": "ease_out",        # 缓动曲线
    # 独立开关
    "char_reveal": True,         # 逐字从雾中浮现
    "feathers": True,            # 近景羽毛漂浮
    "far_feathers": True,        # 远景羽毛(空间层次)
    "motes": True,               # 微粒漂浮
    "mist_flow": True,           # 雾气流动
    "breathing": True,           # 微光呼吸
    "float": True,               # 整体浮动
    "light_sweep": True,         # 光线扫过
    "crossfade": True,           # 行切换交叠
    "soft_glow": True,           # 文字柔光(非霓虹描边)
    "feather_on_enter": True,    # 入场撒羽毛
    "feather_on_exit": True,     # 退场撒羽毛
    # 粒子数量
    "feather_count": 12,
    "far_feather_count": 8,
    "mote_count": 22,
}

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
    "visible_lines": 4,          # 歌词窗同时显示的行数（1-8）
    "show_line_number": False,   # 右上角显示 当前行/总行数（默认关闭）
    "read_lines": 2,             # 读条批大小：整批补位一次显示几行 / 原位替换占几个固定行(1-8)
    "refill_mode": "batch",      # 消失后补位方式: batch=唱完消失+整批补位 / slot=原位替换 / shift=逐行上移
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
    # 雾中飞羽特效
    "fx": dict(FX_DEFAULTS),
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
            # fx 字典深合并：用户只改了部分键也要保留其余默认值
            if isinstance(user.get("fx"), dict):
                cfg["fx"] = {**FX_DEFAULTS, **user["fx"]}
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
