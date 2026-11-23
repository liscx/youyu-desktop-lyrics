# -*- coding: utf-8 -*-
"""飞行物系统：配置默认值、挡位映射、旧配置迁移。

配置结构（cfg["floating"]）：
    {
      "version": 1,
      "scenes": {
        "ambient": {...},   # 背景持续漂浮
        "enter": {...},     # 歌词入场
        "exit": {...},      # 逐字消散配置（唱到哪散到哪）
        "switch": {...},    # 歌词切换
      }
    }

每个场景的字段（scene spec）：
    enabled          bool    场景开关
    material         str     素材 id（见 MATERIALS）
    count            str     数量挡位 key
    direction        [x,y]   主方向单位向量
    random_deviation bool    随机偏向开关
    deviation        str     偏转幅度挡位 key
    size             str     尺寸挡位 key
    random_size      bool    随机大小开关
    speed            str     速度挡位 key
    random_rotation  bool    随机旋转开关
    rotation_speed   str     旋转速度挡位 key
    area             [x,y,w,h] 归一化活动范围（仅 ambient 使用）

挡位只是 UI 交互形式，底层映射到精确数值。所有映射集中在本文件，
改挡位手感只需改 TIER_* 表，不用碰引擎。
"""
import os
import sys

from core.config import BASE_DIR

# ---------------- 素材注册表 ----------------
# id -> 显示名 + SVG 文件 + 基础尺寸px。所有素材统一 SVG 驱动（矢量，缩放无损）。
# SVG 位于 assets/materials/：源码运行时在项目根目录，打包后由 PyInstaller
# 解包到 sys._MEIPASS（见 materials_dir()）。
MATERIALS = {
    "feather":   {"label": "羽毛",   "svg": "feather.svg",   "base": 8},
    "sakura":    {"label": "樱花",   "svg": "sakura.svg",    "base": 10},
    "petal":     {"label": "花瓣",   "svg": "petal.svg",     "base": 9},
    "snow":      {"label": "雪花",   "svg": "snow.svg",      "base": 8},
    "maple":     {"label": "枫叶",   "svg": "maple.svg",     "base": 11},
    "glow":      {"label": "光点",   "svg": "glow.svg",      "base": 7},
    "butterfly": {"label": "蝴蝶",   "svg": "butterfly.svg", "base": 12},
    "leaf":      {"label": "树叶",   "svg": "leaf.svg",      "base": 10},
    "sunflower": {"label": "向日葵", "svg": "sunflower.svg", "base": 11},
    "rain":      {"label": "雨丝",   "svg": "rain.svg",      "base": 9},
    "custom":    {"label": "自定义图片（待接入）", "svg": "glow.svg", "base": 12},
}
MATERIAL_IDS = tuple(MATERIALS.keys())


def materials_dir():
    """内置 SVG 素材目录：打包后在 _MEIPASS，源码运行时在项目根目录。"""
    if getattr(sys, "frozen", False):
        root = getattr(sys, "_MEIPASS", BASE_DIR)
    else:
        root = BASE_DIR
    return os.path.join(root, "assets", "materials")

# ---------------- 挡位表 ----------------
TIER_COUNT = {"few": 4, "some": 9, "many": 18, "lots": 32}
# 旧版 size 挡位 key -> 倍率；仅用于迁移老配置，现配置直接存倍率数值(0.3~2.5)
TIER_SIZE = {"small": 0.7, "medium": 1.0, "large": 1.5}
SIZE_MIN, SIZE_MAX = 0.3, 2.5
TIER_SPEED = {"slow": 0.06, "natural": 0.16, "fast": 0.34}       # px/ms 基准速度
TIER_DEVIATION = {"slight": 0.22, "moderate": 0.6, "obvious": 1.2}  # 弧度上限
TIER_ROTATION = {"slow": 0.0004, "natural": 0.0012, "fast": 0.003}  # 弧度/ms

# 挡位中文显示（UI 用），顺序即显示顺序
TIER_LABELS = {
    "count": [("few", "少量"), ("some", "适中"), ("many", "较多"), ("lots", "大量")],
    "speed": [("slow", "缓慢"), ("natural", "自然"), ("fast", "快速")],
    "deviation": [("slight", "轻微"), ("moderate", "适中"), ("obvious", "明显")],
    "rotation_speed": [("slow", "缓慢"), ("natural", "自然"), ("fast", "快速")],
}

SCENE_LABELS = {
    "ambient": "背景持续漂浮",
    "enter": "歌词入场",
    "exit": "逐字消散配置",
    "switch": "歌词切换",
}
SCENE_IDS = tuple(SCENE_LABELS.keys())

# 每个场景支持的参数（决定 UI 显示哪些控件、迁移时保留哪些字段）
SCENE_FIELDS = {
    "ambient": ("material", "count", "area", "direction", "speed", "size",
                "random_deviation", "deviation", "random_size", "random_rotation",
                "rotation_speed"),
    "enter": ("material", "count", "direction", "speed", "size",
              "random_deviation", "deviation", "random_size"),
    "exit": ("material", "count", "direction", "speed", "size",
             "random_deviation", "deviation", "random_size", "random_rotation",
             "rotation_speed"),
    "switch": ("material", "count", "direction", "speed", "size",
               "random_deviation", "deviation", "random_size", "random_rotation",
               "rotation_speed"),
}


def default_scene(scene_id):
    """返回某场景的默认配置（每次新建独立字典）。"""
    base = {
        "enabled": True,
        "material": "feather",
        "count": "some",
        "direction": [0.0, 1.0],   # 向下（屏幕坐标 y 向下）
        "random_deviation": False,
        "deviation": "slight",
        "size": 1.0,               # 大小倍率(0.3~2.5)，UI 用拖条+实时示例
        "random_size": False,
        "speed": "natural",
        "random_rotation": False,
        "rotation_speed": "natural",
        "area": [0.0, 0.0, 1.0, 1.0],
    }
    # 场景差异化默认值：保留原羽毛特效的观感
    if scene_id == "ambient":
        base.update(count="some", random_deviation=True, deviation="slight",
                    speed="slow", random_size=True, random_rotation=True,
                    rotation_speed="slow")
    elif scene_id == "enter":
        base.update(count="few", direction=[0.0, -1.0], speed="slow", size="small")
    elif scene_id == "exit":
        base.update(count="some", direction=[-0.6, -0.8], random_deviation=True,
                    size="small", random_rotation=True, rotation_speed="slow")
    elif scene_id == "switch":
        base.update(count="few", direction=[-0.6, -0.8], size="small",
                    random_rotation=True)
    return base


def default_floating():
    """完整默认配置。"""
    return {
        "version": 1,
        "scenes": {sid: default_scene(sid) for sid in SCENE_IDS},
    }


def normalize_direction(vec):
    """把方向盘给的向量归一化；零向量回退到向下。"""
    try:
        x, y = float(vec[0]), float(vec[1])
    except Exception:
        return [0.0, 1.0]
    n = (x * x + y * y) ** 0.5
    if n < 1e-6:
        return [0.0, 1.0]
    return [x / n, y / n]


def sanitize_scene(raw, scene_id):
    """把用户配置规整成合法 scene spec：填默认值、校验枚举、归一化方向/范围。"""
    out = default_scene(scene_id)
    if not isinstance(raw, dict):
        return out
    out["enabled"] = bool(raw.get("enabled", out["enabled"]))
    mat = raw.get("material", out["material"])
    out["material"] = mat if mat in MATERIALS else out["material"]
    for key, table in (("count", TIER_COUNT), ("speed", TIER_SPEED),
                       ("deviation", TIER_DEVIATION), ("rotation_speed", TIER_ROTATION)):
        val = raw.get(key, out[key])
        out[key] = val if val in table else out[key]
    # size 现为倍率数值(0.3~2.5)；兼容旧版挡位 key（small/medium/large）
    raw_size = raw.get("size", out["size"])
    if isinstance(raw_size, str) and raw_size in TIER_SIZE:
        out["size"] = TIER_SIZE[raw_size]
    else:
        try:
            out["size"] = max(SIZE_MIN, min(SIZE_MAX, float(raw_size)))
        except (TypeError, ValueError):
            pass
    for key in ("random_deviation", "random_size", "random_rotation"):
        out[key] = bool(raw.get(key, out[key]))
    out["direction"] = normalize_direction(raw.get("direction", out["direction"]))
    area = raw.get("area", out["area"])
    try:
        ax, ay, aw, ah = (float(v) for v in area)
        ax, ay = max(0.0, min(1.0, ax)), max(0.0, min(1.0, ay))
        aw = max(0.05, min(1.0 - ax, aw))
        ah = max(0.05, min(1.0 - ay, ah))
        out["area"] = [ax, ay, aw, ah]
    except Exception:
        pass
    return out


def load_floating(cfg):
    """从 cfg 读取并规整整个 floating 配置（缺省时给默认值）。"""
    raw = cfg.get("floating", {})
    scenes = raw.get("scenes", {}) if isinstance(raw, dict) else {}
    return {
        "version": 1,
        "scenes": {sid: sanitize_scene(scenes.get(sid), sid) for sid in SCENE_IDS},
    }


def save_floating(cfg, floating):
    """写回 cfg 并落盘（返回 save_config 结果）。"""
    from core.config import save_config
    cfg["floating"] = floating
    return save_config(cfg)


# ---------------- 旧配置迁移 ----------------
# 旧 fx 键 -> 新场景：把老羽毛/雨滴配置映射到对应场景，尽量保留用户观感。
def migrate_from_fx(cfg):
    """从旧的 cfg['fx'] + 主题字段迁移出 floating 配置。

    迁移规则（一次性，只在没有 cfg['floating'] 时执行）：
      - 常驻近景羽毛 feathers/feather_count -> ambient
      - 远景羽毛 far_feathers/far_feather_count -> ambient 的 count 叠加
      - 微粒 motes/mote_count -> ambient 的 count 叠加（视作光点）
      - 入场羽毛 feather_on_enter -> enter.enabled
      - 逐字消散羽毛 feather_on_exit + follow_dissolve -> exit.enabled
      - 切行整行化羽 feather_on_line_end -> switch.enabled
      - 消散方向 dissolve_drift_x/y -> exit.direction
      - 消散时长 dissolve_char_ms -> exit.speed（反推挡位）
      - 忧郁主题雨滴 ambient/ambient_density/ambient_color -> 作为独立素材 rain 的 ambient
    """
    fx = cfg.get("fx", {}) if isinstance(cfg.get("fx"), dict) else {}
    result = default_floating()
    scenes = result["scenes"]

    def tier_from_value(value, table, prefer):
        """按数值最接近的挡位反推；value 无效时用 prefer。"""
        if not isinstance(value, (int, float)):
            return prefer
        return min(table, key=lambda k: abs(table[k] - value))

    # ambient：常驻羽毛数量 + 远景 + 微粒
    ambient = scenes["ambient"]
    ambient["enabled"] = bool(fx.get("feathers", fx.get("far_feathers", True)))
    total = int(fx.get("feather_count", 12) or 0) + int(fx.get("far_feather_count", 8) or 0) // 2
    ambient["count"] = tier_from_value(total, TIER_COUNT, "some")
    ambient["speed"] = tier_from_value(0.10, TIER_SPEED, "slow")
    ambient["size"] = 1.0
    ambient["random_rotation"] = True
    ambient["random_size"] = True
    ambient["random_deviation"] = True

    # enter
    scenes["enter"]["enabled"] = bool(fx.get("feather_on_enter", True))

    # exit（逐字消散：唱到哪散到哪；整行化羽归 switch 场景）
    exit_scene = scenes["exit"]
    exit_scene["enabled"] = bool(fx.get("feather_on_exit", True) or fx.get("follow_dissolve", True))
    dx = fx.get("dissolve_drift_x", 22)
    dy = fx.get("dissolve_drift_y", 34)
    if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
        exit_scene["direction"] = normalize_direction([-dx, -dy])
    dur = fx.get("dissolve_char_ms", 360)
    exit_scene["speed"] = tier_from_value(0.16 * 360 / max(1, dur or 360), TIER_SPEED, "natural")
    per_char = int(fx.get("dissolve_feathers_per_char", 1) or 1)
    exit_scene["count"] = "few" if per_char <= 1 else ("some" if per_char <= 3 else "many")

    # switch
    scenes["switch"]["enabled"] = bool(fx.get("feather_on_line_end", True))

    # 忧郁主题雨滴：映射成 ambient 使用 rain 素材的独立场景信息，
    # 存到 floating["legacy_rain"] 供引擎读取（不占四场景名额）
    if cfg.get("ambient") and cfg.get("ambient_density"):
        result["legacy_rain"] = {
            "enabled": True,
            "count": tier_from_value(int(cfg["ambient_density"]), TIER_COUNT, "some"),
            "color": cfg.get("ambient_color", "#9FC6FF"),
        }
    else:
        result["legacy_rain"] = {"enabled": False, "count": "few",
                                 "color": cfg.get("ambient_color", "#9FC6FF")}
    return result


def ensure_floating(cfg):
    """确保 cfg 里有 floating；没有则从旧 fx 迁移并写回。返回规整后的配置。"""
    if not isinstance(cfg.get("floating"), dict) or not cfg["floating"].get("scenes"):
        floating = migrate_from_fx(cfg)
        cfg["floating"] = floating
        try:
            from core.config import save_config
            save_config(cfg)
        except Exception:
            pass
    return load_floating(cfg)
