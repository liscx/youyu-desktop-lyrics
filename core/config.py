# -*- coding: utf-8 -*-
"""配置管理：读写 config.json，提供默认值。

config.json 与 cache/ 与代码位置解耦：源码运行时位于项目根目录
（core/ 的上一级），打包后（PyInstaller frozen）位于 exe 所在目录，
始终外置可编辑。
"""
import json
import os
import sys

if getattr(sys, "frozen", False):
    # 打包后：exe 所在目录，配置外置，升级不丢设置
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    # 源码运行：项目根目录 = 本文件所在 core/ 的上一级
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

# 文字与氛围动效参数（见 ui/effects.py）。
# 飘落粒子（原 feathers/motes/feather_on_* / feather_count 等）已迁移到
# 通用飞行物系统，配置见 core/floating_config.py；旧键仅由迁移函数读取一次。
FX_DEFAULTS = {
    "enabled": True,             # 特效总开关
    # 时间 / 强度 / 距离
    "fade_in_ms": 900,           # 入场时长
    "fade_out_ms": 700,          # 退场时长
    "blur_max": 7,               # 文字模糊最大程度(0-12)
    "rise_px": 12,               # 入场文字上浮距离(px)
    "char_stagger_ms": 60,       # 逐字浮现的每字延迟(ms)
    "float_px": 3,               # 整体上下浮动幅度(px)
    "float_ms": 5200,            # 浮动周期(ms)
    "breath_pct": 10,            # 微光呼吸幅度：百分比整数 0-50，引擎读取时 /100 转小数
    "breath_ms": 3600,           # 呼吸周期(ms)
    "glow_len_chars": 2.5,       # 文字柔光光条长度(以字宽为单位)，默认 2.5 字
    "batch_gap_ms": 220,         # 整批补位时上一批完全消失到下一批出现的间隔(ms)
    "refill_delay_ms": 1000,     # 原位替换：空行位等消散粒子飘走后再补入下一句的延迟(ms)
    # 逐字消散（文字侧；飞行物形态由 floating 的 exit 场景控制）
    "word_dissolve": True,       # 逐字消散（关闭则退回整行渐隐）
    "dissolve_char_ms": 360,     # 单个字消散时长(ms)
    "dissolve_stagger_ms": 420,  # 整行从左到右消散的延迟跨度(ms)
    "follow_dissolve": True,     # 逐字跟随消散总开关
    "follow_char_ms": 340,       # 单字从被读条扫过到完全消散的时长(ms)
    "follow_lead": 6,            # 读条越过该字多少比例(%)后开始消散
    "easing": "ease_out",        # 缓动曲线
    # 独立开关（文字动效，飞行物开关在 floating.scenes.*.enabled）
    "char_reveal": True,         # 逐字浮现
    "breathing": True,           # 微光呼吸
    "float": True,               # 整体浮动
    "crossfade": True,           # 行切换交叠
    "soft_glow": True,           # 文字柔光(非霓虹描边)
    # 飞行物主题色（注入飞行物引擎，不是粒子数量参数）
    "feather_color": "#DCE6F1",
}

DEFAULTS = {
    # 当前外观主题（见 themes/presets.py）
    "theme": "classic",
    # 歌词源: auto(本地优先+网络兜底) / local / network
    "source": "auto",
    # 网易云歌词缓存目录（留空自动探测）
    "netease_lyric_dir": "",
    # 网易云安装目录（CDP 补丁用，填 libcef.dll 所在文件夹；留空自动探测）
    "netease_dir": "",
    # 外观（会被所选主题覆盖，这里的取值 = classic 经典主题）
    "font_family": "Microsoft YaHei",
    "font_size": 30,
    "font_bold": True,
    "color_normal": "#B7B7B7",
    "color_highlight": "#FFFFFF",
    "color_reading": "#B7B7B7",  # 「读行歌词」颜色：当前行读条未经过的字（默认同普通色，不改变现有外观）
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
            # 读行颜色未显式配置时，跟随实际生效的普通歌词颜色（保证外观不因升级改变）
            if "color_reading" not in user:
                cfg["color_reading"] = cfg["color_normal"]
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
