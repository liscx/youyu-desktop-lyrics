# -*- coding: utf-8 -*-
"""飞行物设置页：素材选择 + 四个触发场景的独立配置。

界面规范：
  - 数量/尺寸/速度/偏转/旋转速度：有限挡位选择器
  - 方向：二维坐标方向盘
  - 活动范围：可拖动矩形
  - 随机偏向/大小/旋转、场景启用：独立开关
  - 分组折叠，避免参数堆叠
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QCheckBox, QGroupBox, QScrollArea, QPushButton, QFrame,
)
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QFont

from core.floating_config import (
    MATERIALS, SCENE_LABELS, SCENE_FIELDS, TIER_LABELS,
    default_scene, normalize_direction,
)
from ui.floating_widgets import DirectionPad, AreaSelector, TierSelector, SizeSlider


def _material_preview(material_id, size=34):
    """素材预览小控件：用与引擎相同的绘制逻辑画一个样例。"""
    from ui.floating_objects import MATERIAL_DRAW
    from core.floating_config import MATERIALS as M

    class Preview(QWidget):
        def __init__(self):
            super().__init__()
            self.setFixedSize(size, size)

        def paintEvent(self, e):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, True)
            drawer = MATERIAL_DRAW.get(material_id)
            if not drawer:
                return
            c = QColor("#DCE6F1")
            meta = M.get(material_id, {"base": 10})
            s = size / 34.0 * meta["base"] * 0.9
            p.translate(size / 2, size / 2)
            drawer(p, s, c)

    return Preview()


class ScenePanel(QGroupBox):
    """单个触发场景的设置面板（可折叠）。"""

    def __init__(self, scene_id, spec, parent=None):
        super().__init__(SCENE_LABELS[scene_id], parent)
        self.setCheckable(True)
        self.setChecked(spec.get("enabled", True))
        self._scene_id = scene_id
        self._spec = dict(spec)
        self._default = default_scene(scene_id)
        self._refs = {}   # 控件引用

        lay = QVBoxLayout(self)
        form = QFormLayout()

        # 素材选择（预览 + 下拉）
        mat_row = QHBoxLayout()
        self._refs["material"] = QComboBox()
        for mid, meta in MATERIALS.items():
            self._refs["material"].addItem(meta["label"], userData=mid)
        mi = self._refs["material"].findData(spec["material"])
        if mi >= 0:
            self._refs["material"].setCurrentIndex(mi)
        self._preview_holder = QHBoxLayout()
        self._update_preview(spec["material"])
        self._refs["material"].currentIndexChanged.connect(self._on_material_changed)
        mat_row.addWidget(self._refs["material"], 1)
        mat_row.addLayout(self._preview_holder)
        form.addRow("飞行物素材", mat_row)

        # 数量挡位
        self._refs["count"] = TierSelector("count", spec["count"])
        form.addRow("数量", self._refs["count"])

        # 背景专属：活动范围
        if "area" in SCENE_FIELDS[scene_id]:
            self._refs["area"] = AreaSelector(spec.get("area", [0, 0, 1, 1]))
            form.addRow("活动范围", self._refs["area"])

        # 方向
        self._refs["direction"] = DirectionPad(
            spec["direction"], self._default["direction"]
        )
        form.addRow("飞行方向", self._refs["direction"])

        # 速度挡位 / 大小（拖条+实时示例）
        self._refs["speed"] = TierSelector("speed", spec["speed"])
        form.addRow("速度", self._refs["speed"])
        self._refs["size"] = SizeSlider(spec["material"], spec["size"])
        form.addRow("大小", self._refs["size"])

        # 随机偏向
        if "random_deviation" in SCENE_FIELDS[scene_id]:
            dev_row = QHBoxLayout()
            self._refs["random_deviation"] = QCheckBox("随机偏向")
            self._refs["random_deviation"].setChecked(spec.get("random_deviation", False))
            dev_row.addWidget(self._refs["random_deviation"])
            self._refs["deviation"] = TierSelector("deviation", spec["deviation"])
            dev_row.addWidget(self._refs["deviation"])
            form.addRow("", dev_row)

        # 随机大小
        if "random_size" in SCENE_FIELDS[scene_id]:
            self._refs["random_size"] = QCheckBox("随机大小")
            self._refs["random_size"].setChecked(spec.get("random_size", False))
            form.addRow("", self._refs["random_size"])

        # 随机旋转 + 速度
        if "random_rotation" in SCENE_FIELDS[scene_id]:
            rot_row = QHBoxLayout()
            self._refs["random_rotation"] = QCheckBox("随机旋转")
            self._refs["random_rotation"].setChecked(spec.get("random_rotation", False))
            rot_row.addWidget(self._refs["random_rotation"])
            self._refs["rotation_speed"] = TierSelector("rotation_speed", spec["rotation_speed"])
            rot_row.addWidget(self._refs["rotation_speed"])
            form.addRow("", rot_row)

        lay.addLayout(form)

        # 恢复本场景默认
        reset = QPushButton("恢复本场景默认")
        reset.clicked.connect(self._reset_defaults)
        lay.addWidget(reset, alignment=Qt.AlignRight)

    def _on_material_changed(self, idx):
        mid = self._refs["material"].itemData(idx)
        self._update_preview(mid)
        self._refs["size"].set_material(mid)

    def _update_preview(self, material_id):
        # 清空旧预览
        while self._preview_holder.count():
            item = self._preview_holder.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._preview_holder.addWidget(_material_preview(material_id))

    def _reset_defaults(self):
        """把本场景所有控件恢复为默认值。"""
        d = self._default
        self.setChecked(d["enabled"])
        self._refs["material"].setCurrentIndex(
            self._refs["material"].findData(d["material"]))
        self._refs["count"].setValue(d["count"])
        self._refs["speed"].setValue(d["speed"])
        self._refs["size"].setValue(d["size"])
        self._refs["direction"].setDirection(d["direction"])
        if "area" in self._refs:
            self._refs["area"].setArea(d["area"])
        for key in ("random_deviation", "random_size", "random_rotation"):
            if key in self._refs:
                self._refs[key].setChecked(d.get(key, False))
        for key in ("deviation", "rotation_speed"):
            if key in self._refs:
                self._refs[key].setValue(d[key])

    def spec(self):
        """读取当前面板配置，返回 scene spec。"""
        out = dict(self._spec)
        out["enabled"] = self.isChecked()
        out["material"] = self._refs["material"].currentData()
        out["count"] = self._refs["count"].value()
        out["speed"] = self._refs["speed"].value()
        out["size"] = self._refs["size"].value()
        out["direction"] = normalize_direction(self._refs["direction"].direction())
        if "area" in self._refs:
            out["area"] = self._refs["area"].area()
        for key in ("random_deviation", "random_size", "random_rotation"):
            if key in self._refs:
                out[key] = self._refs[key].isChecked()
        for key in ("deviation", "rotation_speed"):
            if key in self._refs:
                out[key] = self._refs[key].value()
        return out


class FloatingSettingsPage(QWidget):
    """飞行物设置页：素材说明 + 四个场景分组。"""

    def __init__(self, floating, parent=None):
        super().__init__(parent)
        self._panels = {}
        self._extra = {}   # 保留非场景字段（如 legacy_rain 迁移信息）
        for key in ("legacy_rain",):
            if key in floating:
                self._extra[key] = floating[key]
        self._build(floating)

    def _build(self, floating):
        outer = QVBoxLayout(self)
        root = QVBoxLayout()

        intro = QLabel(
            "飞行物素材与运动分离：每个出现场景可独立设置素材、数量、方向、速度、大小与随机效果。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#7BA7D7;font-size:11px;padding:2px 0 6px 0;")
        root.addWidget(intro)

        scenes = floating.get("scenes", {})
        for sid in SCENE_LABELS:
            panel = ScenePanel(sid, scenes.get(sid, default_scene(sid)))
            self._panels[sid] = panel
            root.addWidget(panel)

        root.addStretch()
        # 放进滚动区（四场景参数较多）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        holder = QWidget()
        holder.setLayout(root)
        scroll.setWidget(holder)
        outer.addWidget(scroll)

    def collect(self):
        """返回完整的 floating 配置。"""
        out = {
            "version": 1,
            "scenes": {sid: panel.spec() for sid, panel in self._panels.items()},
        }
        out.update(self._extra)
        return out
