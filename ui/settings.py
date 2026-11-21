# -*- coding: utf-8 -*-
"""设置面板：外观 + 雾中飞羽特效两页。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QLabel, QComboBox, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QSlider, QCheckBox, QFontComboBox, QSpinBox,
    QColorDialog, QTabWidget, QWidget, QGroupBox, QGridLayout, QScrollArea,
)
from PySide6.QtGui import QColor, QFont

from themes import theme_list, get_theme
from core.config import FX_DEFAULTS


def color_dialog_button(parent, color, callback):
    """带颜色预览的按钮，点击弹出取色器。"""
    btn = QPushButton(color)
    btn.setObjectName("colorBtn")

    def pick():
        c = QColorDialog.getColor(QColor(color), parent, "选择颜色")
        if c.isValid():
            btn.setText(c.name())
            btn.setStyleSheet(
                f"background:{c.name()};"
                f"color:{'#000' if c.lightness() > 128 else '#fff'};"
            )
            callback(c.name())

    btn.setStyleSheet(
        f"background:{color};"
        f"color:{'#000' if QColor(color).lightness() > 128 else '#fff'};"
        f"padding:4px;border-radius:4px;"
    )
    btn.clicked.connect(pick)
    return btn


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None, on_switch_theme=None):
        super().__init__(parent)
        self.cfg = cfg
        self.on_switch_theme = on_switch_theme
        self.setWindowTitle("桌面歌词 - 设置")
        self.setMinimumWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._suppress_theme_change = False
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        self.fx_cfg = dict(self.cfg.get("fx", FX_DEFAULTS))

        tabs = QTabWidget()
        tabs.addTab(self._build_appearance_tab(), "外观")
        tabs.addTab(self._build_effects_tab(), "雾中飞羽 · 特效")
        root.addWidget(tabs)

        tip = QLabel(
            "Ctrl+Alt+T 轮换主题 · Ctrl+Alt+L 解锁拖动 · Ctrl+Alt+H 显示/隐藏"
        )
        tip.setStyleSheet("color:#888;font-size:11px;")
        tip.setAlignment(Qt.AlignCenter)
        root.addWidget(tip)

        buttons = QHBoxLayout()
        ok = QPushButton("确定")
        ok.clicked.connect(self._apply)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        root.addLayout(buttons)

    # ---------------- 外观页 ----------------
    def _build_appearance_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        # 主题选择置顶
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("外观主题"))
        self.theme_combo = QComboBox()
        for key, label, icon_char, desc in theme_list():
            self.theme_combo.addItem(f"{icon_char}  {label}", userData=key)
            self.theme_combo.setItemData(self.theme_combo.count() - 1, desc, Qt.ToolTipRole)
        idx = self.theme_combo.findData(self.cfg.get("theme", "classic"))
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.theme_combo, 1)
        layout.addLayout(theme_row)

        self.theme_desc = QLabel(get_theme(self.cfg.get("theme", "classic"))["desc"])
        self.theme_desc.setStyleSheet("color:#7BA7D7;font-size:11px;padding:2px 0 8px 0;")
        self.theme_desc.setWordWrap(True)
        layout.addWidget(self.theme_desc)

        form = QFormLayout()
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(self.cfg["font_family"]))
        form.addRow("字体", self.font_combo)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(12, 80)
        self.size_spin.setValue(self.cfg["font_size"])
        form.addRow("字号", self.size_spin)

        self.bold_check = QCheckBox("粗体")
        self.bold_check.setChecked(self.cfg["font_bold"])
        form.addRow("", self.bold_check)

        self.normal_btn = color_dialog_button(self, self.cfg["color_normal"], lambda c: None)
        form.addRow("普通歌词颜色", self.normal_btn)
        self.highlight_btn = color_dialog_button(self, self.cfg["color_highlight"], lambda c: None)
        form.addRow("高亮颜色", self.highlight_btn)
        self.translate_btn = color_dialog_button(self, self.cfg["color_translated"], lambda c: None)
        form.addRow("翻译颜色", self.translate_btn)
        self.glow_btn = color_dialog_button(self, self.cfg["color_glow"], lambda c: None)
        form.addRow("光晕颜色", self.glow_btn)

        self.glow_check = QCheckBox("启用高亮光晕")
        self.glow_check.setChecked(self.cfg["glow_enabled"])
        form.addRow("", self.glow_check)
        self.trans_check = QCheckBox("显示翻译歌词")
        self.trans_check.setChecked(self.cfg["show_translation"])
        form.addRow("", self.trans_check)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(self.cfg["opacity"] * 100))
        form.addRow("窗口透明度", self.opacity_slider)

        self.spacing_spin = QSpinBox()
        self.spacing_spin.setRange(0, 40)
        self.spacing_spin.setValue(self.cfg["line_spacing"])
        form.addRow("行间距", self.spacing_spin)

        self.visible_spin = QSpinBox()
        self.visible_spin.setRange(1, 8)
        self.visible_spin.setValue(self.cfg.get("visible_lines", 4))
        self.visible_spin.setSuffix(" 行")
        form.addRow("显示行数", self.visible_spin)

        self.lineno_check = QCheckBox("显示行号（当前 / 总数）")
        self.lineno_check.setChecked(self.cfg.get("show_line_number", True))
        form.addRow("", self.lineno_check)

        # 补位方式
        self.refill_combo = QComboBox()
        for key, label in (
            ("batch", "整批补位（唱完消失，整批换新）"),
            ("slot", "原位替换（哪行空补哪行）"),
            ("shift", "逐行上移（传统方式）"),
        ):
            self.refill_combo.addItem(label, userData=key)
        ri = self.refill_combo.findData(self.cfg.get("refill_mode", "batch"))
        if ri >= 0:
            self.refill_combo.setCurrentIndex(ri)
        form.addRow("消失后补位", self.refill_combo)

        self.read_spin = QSpinBox()
        self.read_spin.setRange(1, 8)
        self.read_spin.setValue(self.cfg.get("read_lines", 2))
        self.read_spin.setSuffix(" 行")
        self.read_spin.setToolTip("整批补位/原位替换模式下，同时显示的歌词行数")
        form.addRow("读条行数", self.read_spin)

        layout.addLayout(form)
        return page

    # ---------------- 特效页 ----------------
    def _mk_slider(self, key, label, lo, hi, scale=1):
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        val = self.fx_cfg.get(key, FX_DEFAULTS[key])
        s.setValue(int(val * scale) if scale != 1 else int(val))
        s.setObjectName(key)
        return s, label

    def _build_effects_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        fx = self.fx_cfg

        self.fx_enabled = QCheckBox("启用「雾中飞羽」特效（总开关）")
        self.fx_enabled.setChecked(fx.get("enabled", True))
        layout.addWidget(self.fx_enabled)

        # 各动画独立开关（两列网格）
        sw_group = QGroupBox("动画模块（独立开关）")
        grid = QGridLayout()
        switches = [
            ("char_reveal", "逐字浮现"), ("feathers", "羽毛漂浮"),
            ("far_feathers", "远景羽毛"), ("motes", "微粒漂浮"),
            ("mist_flow", "雾气流动"), ("breathing", "微光呼吸"),
            ("float", "整体浮动"), ("light_sweep", "光线扫过"),
            ("crossfade", "行切换交叠"), ("soft_glow", "文字柔光"),
            ("feather_on_enter", "入场羽毛"), ("feather_on_exit", "退场羽毛"),
            ("word_dissolve", "逐字化羽消散"),
        ]
        self.fx_switches = {}
        for i, (key, label) in enumerate(switches):
            cb = QCheckBox(label)
            cb.setChecked(fx.get(key, FX_DEFAULTS[key]))
            self.fx_switches[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        sw_group.setLayout(grid)
        layout.addWidget(sw_group)

        # 关键参数（时间/强度/距离/数量）
        p_group = QGroupBox("参数调节")
        pform = QFormLayout()
        self.fx_sliders = {}

        def add_int(key, label, lo, hi):
            s = QSlider(Qt.Horizontal)
            s.setRange(lo, hi)
            s.setValue(int(fx.get(key, FX_DEFAULTS[key])))
            lab = QLabel(f"{label} ({s.value()})")
            s.valueChanged.connect(
                lambda v, lab=lab, label=label: lab.setText(f"{label} ({v})")
            )
            pform.addRow(lab, s)
            self.fx_sliders[key] = s
            return s

        add_int("fade_in_ms", "入场时长(ms)", 200, 2500)
        add_int("fade_out_ms", "退场时长(ms)", 200, 2000)
        add_int("char_stagger_ms", "逐字延迟(ms)", 0, 200)
        add_int("rise_px", "上浮距离(px)", 0, 30)
        add_int("float_px", "浮动幅度(px)", 0, 12)
        add_int("blur_max", "羽化程度", 0, 12)
        add_int("breath_pct", "呼吸幅度(%)", 0, 40)
        add_int("mist_alpha", "雾气浓度", 0, 80)
        add_int("feather_count", "羽毛数量", 0, 30)
        add_int("mote_count", "微粒数量", 0, 50)
        add_int("sweep_alpha", "光条亮度", 0, 80)
        add_int("sweep_fade_start", "光条渐隐起点(%)", 0, 95)
        add_int("batch_gap_ms", "整批补位空窗(ms)", 0, 900)
        add_int("dissolve_char_ms", "单字化羽时长(ms)", 100, 1200)
        add_int("dissolve_stagger_ms", "整行化羽跨度(ms)", 0, 1500)
        add_int("dissolve_drift_x", "化羽左移(px)", 0, 80)
        add_int("dissolve_drift_y", "化羽上移(px)", 0, 80)
        p_group.setLayout(pform)
        layout.addWidget(p_group)

        # 缓动曲线
        ease_row = QHBoxLayout()
        ease_row.addWidget(QLabel("缓动曲线"))
        self.fx_ease = QComboBox()
        for k, label in (("ease_out", "浮现（快起慢收）"), ("ease_in_out", "平滑"),
                         ("ease_in", "消散（慢起快收）"), ("linear", "线性")):
            self.fx_ease.addItem(label, userData=k)
        ei = self.fx_ease.findData(fx.get("easing", "ease_out"))
        if ei >= 0:
            self.fx_ease.setCurrentIndex(ei)
        ease_row.addWidget(self.fx_ease, 1)
        layout.addLayout(ease_row)

        layout.addStretch()
        # 参数较多，放进滚动区避免窗口超出屏幕
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    # ---------------- 同步 / 应用 ----------------
    def _sync_controls_from_cfg(self):
        """主题切换后，用新 cfg 刷新各控件（含 fx）。"""
        self._suppress_theme_change = True
        self.font_combo.setCurrentFont(QFont(self.cfg["font_family"]))
        self.size_spin.setValue(self.cfg["font_size"])
        self.bold_check.setChecked(self.cfg["font_bold"])
        for btn, key in (
            (self.normal_btn, "color_normal"),
            (self.highlight_btn, "color_highlight"),
            (self.translate_btn, "color_translated"),
            (self.glow_btn, "color_glow"),
        ):
            color = self.cfg[key]
            btn.setText(color)
            btn.setStyleSheet(
                f"background:{color};"
                f"color:{'#000' if QColor(color).lightness() > 128 else '#fff'};"
                f"padding:4px;border-radius:4px;"
            )
        self.glow_check.setChecked(self.cfg["glow_enabled"])
        self.trans_check.setChecked(self.cfg["show_translation"])
        self.opacity_slider.setValue(int(self.cfg["opacity"] * 100))
        self.spacing_spin.setValue(self.cfg["line_spacing"])
        self.visible_spin.setValue(self.cfg.get("visible_lines", 4))
        self.lineno_check.setChecked(self.cfg.get("show_line_number", True))
        ri = self.refill_combo.findData(self.cfg.get("refill_mode", "batch"))
        if ri >= 0:
            self.refill_combo.setCurrentIndex(ri)
        self.read_spin.setValue(self.cfg.get("read_lines", 2))

        # fx 同步（主题可能改了 fx）
        self.fx_cfg = dict(self.cfg.get("fx", FX_DEFAULTS))
        self.fx_enabled.setChecked(self.fx_cfg.get("enabled", True))
        for key, cb in self.fx_switches.items():
            cb.setChecked(self.fx_cfg.get(key, FX_DEFAULTS[key]))
        for key, s in self.fx_sliders.items():
            s.setValue(int(self.fx_cfg.get(key, FX_DEFAULTS[key])))
        ei = self.fx_ease.findData(self.fx_cfg.get("easing", "ease_out"))
        if ei >= 0:
            self.fx_ease.setCurrentIndex(ei)
        self._suppress_theme_change = False

    def _on_theme_changed(self):
        if self._suppress_theme_change:
            return
        key = self.theme_combo.currentData()
        if not key:
            return
        if self.on_switch_theme:
            self.on_switch_theme(key, save=False)
        self.theme_desc.setText(get_theme(key)["desc"])
        self._sync_controls_from_cfg()

    def _apply(self):
        self.cfg.update({
            "font_family": self.font_combo.currentFont().family(),
            "font_size": self.size_spin.value(),
            "font_bold": self.bold_check.isChecked(),
            "color_normal": self.normal_btn.text(),
            "color_highlight": self.highlight_btn.text(),
            "color_translated": self.translate_btn.text(),
            "color_glow": self.glow_btn.text(),
            "glow_enabled": self.glow_check.isChecked(),
            "show_translation": self.trans_check.isChecked(),
            "opacity": self.opacity_slider.value() / 100,
            "line_spacing": self.spacing_spin.value(),
            "visible_lines": self.visible_spin.value(),
            "show_line_number": self.lineno_check.isChecked(),
            "refill_mode": self.refill_combo.currentData(),
            "read_lines": self.read_spin.value(),
        })
        # 收集 fx 参数
        fx = self.cfg.setdefault("fx", dict(FX_DEFAULTS))
        fx["enabled"] = self.fx_enabled.isChecked()
        for key, cb in self.fx_switches.items():
            fx[key] = cb.isChecked()
        for key, s in self.fx_sliders.items():
            fx[key] = s.value()
        fx["easing"] = self.fx_ease.currentData()
        self.accept()
