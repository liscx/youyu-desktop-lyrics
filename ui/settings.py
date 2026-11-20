# -*- coding: utf-8 -*-
"""设置面板。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QLabel, QComboBox, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QSlider, QCheckBox, QFontComboBox, QSpinBox,
    QColorDialog,
)
from PySide6.QtGui import QColor

from themes import theme_list, get_theme


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
        self.setMinimumWidth(440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._suppress_theme_change = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ---- 主题选择（置顶，最显眼）----
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("外观主题"))
        self.theme_combo = QComboBox()
        for key, label, icon_char, desc in theme_list():
            self.theme_combo.addItem(f"{icon_char}  {label}", userData=key)
            self.theme_combo.setItemData(self.theme_combo.count() - 1, desc, Qt.ToolTipRole)
        cur = self.cfg.get("theme", "classic")
        idx = self.theme_combo.findData(cur)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.theme_combo, 1)
        layout.addLayout(theme_row)

        self.theme_desc = QLabel(get_theme(cur)["desc"])
        self.theme_desc.setStyleSheet("color:#7BA7D7;font-size:11px;padding:2px 0 8px 0;")
        self.theme_desc.setWordWrap(True)
        layout.addWidget(self.theme_desc)

        # ---- 详细外观 ----
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

        layout.addLayout(form)

        tip = QLabel(
            "提示：选择主题会套用整套配色与氛围，可再手动微调。\n"
            "Ctrl+Alt+T 快速轮换主题 · Ctrl+Alt+L 解锁拖动 · Ctrl+Alt+H 显示/隐藏。"
        )
        tip.setStyleSheet("color:#888;font-size:11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        buttons = QHBoxLayout()
        ok = QPushButton("确定")
        ok.clicked.connect(self._apply)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def _sync_controls_from_cfg(self):
        """主题切换后，用新 cfg 刷新各微调控件。"""
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
        self._suppress_theme_change = False

    def _on_theme_changed(self):
        if self._suppress_theme_change:
            return
        key = self.theme_combo.currentData()
        if not key:
            return
        # 立即应用主题（回调会改 cfg、重绘窗口），再同步控件显示
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
        })
        self.accept()
