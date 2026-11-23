# -*- coding: utf-8 -*-
"""设置面板：外观 / 飞行物 / 文字动效三页。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QLabel, QComboBox, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QSlider, QCheckBox, QFontComboBox, QSpinBox,
    QColorDialog, QTabWidget, QWidget, QGroupBox, QGridLayout, QScrollArea,
    QLineEdit, QFileDialog,
)
from PySide6.QtGui import QColor, QFont

from themes import theme_list
from core.config import FX_DEFAULTS, save_config
from core.floating_config import load_floating, save_floating
from ui.floating_settings import FloatingSettingsPage
from ui.fx_tiers import FX_TIERS, ValueTierSelector


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
    def __init__(self, cfg, parent=None, on_switch_theme=None, on_apply=None):
        super().__init__(parent)
        self.cfg = cfg
        self.on_switch_theme = on_switch_theme
        self.on_apply = on_apply
        self._floating = load_floating(cfg)
        self.setWindowTitle("桌面歌词 - 设置")
        self.setMinimumWidth(460)
        # 独立置顶的普通对话框：避免继承歌词窗 Qt.Tool / 点击穿透 导致关闭按钮失效
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint
            | Qt.WindowMinimizeButtonHint | Qt.WindowStaysOnTopHint
        )
        self._suppress_theme_change = False
        self._build_ui()

    def closeEvent(self, event):
        """右上角 X / 系统关闭：与「关闭」按钮一致，直接接受关闭。"""
        event.accept()

    def _build_ui(self):
        root = QVBoxLayout(self)
        self.fx_cfg = dict(self.cfg.get("fx", FX_DEFAULTS))

        tabs = QTabWidget()
        tabs.addTab(self._build_appearance_tab(), "外观")
        tabs.addTab(self._build_floating_page(), "飞行物")
        tabs.addTab(self._build_effects_tab(), "文字动效")
        root.addWidget(tabs)

        tip = QLabel(
            "Ctrl+Alt+T 轮换主题 · Ctrl+Alt+L 解锁拖动 · Ctrl+Alt+H 显示/隐藏"
        )
        tip.setStyleSheet("color:#888;font-size:11px;")
        tip.setAlignment(Qt.AlignCenter)
        root.addWidget(tip)

        buttons = QHBoxLayout()
        apply = QPushButton("应用（不关闭）")
        apply.clicked.connect(self._apply)
        close = QPushButton("关闭")
        close.clicked.connect(self.close)  # 走 closeEvent，右上角 X 同样有效
        buttons.addStretch()
        buttons.addWidget(apply)
        buttons.addWidget(close)
        root.addLayout(buttons)

    # ---------------- 外观页 ----------------
    def _build_appearance_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        # 主题选择置顶
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("外观主题"))
        self.theme_combo = QComboBox()
        for key, label, icon_char in theme_list():
            self.theme_combo.addItem(f"{icon_char}  {label}", userData=key)
        idx = self.theme_combo.findData(self.cfg.get("theme", "classic"))
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.theme_combo, 1)
        layout.addLayout(theme_row)

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
        form.addRow("高亮颜色（读条扫过）", self.highlight_btn)
        self.reading_btn = color_dialog_button(
            self, self.cfg.get("color_reading", self.cfg["color_normal"]), lambda c: None
        )
        self.reading_btn.setToolTip("当前行读条尚未扫到的字所用颜色，可区别于其他歌词行")
        form.addRow("读行歌词颜色", self.reading_btn)
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

        # 网易云安装目录（CDP 补丁需要定位 libcef.dll）
        netease_group = QGroupBox("网易云安装目录（CDP 精确进度补丁用）")
        netease_row = QHBoxLayout()
        self.netease_edit = QLineEdit(self.cfg.get("netease_dir", ""))
        self.netease_edit.setPlaceholderText("填 libcef.dll 所在文件夹，留空自动探测")
        netease_row.addWidget(self.netease_edit, 1)
        browse = QPushButton("浏览...")

        def pick_dir():
            chosen = QFileDialog.getExistingDirectory(
                self, "选择网易云安装目录", self.netease_edit.text() or None
            )
            if chosen:
                self.netease_edit.setText(chosen)

        browse.clicked.connect(pick_dir)
        netease_row.addWidget(browse)
        netease_group.setLayout(netease_row)
        netease_group.setToolTip(
            "打补丁时需要定位 libcef.dll。网易云装在非标准目录时在这里指定，"
            "留空则自动探测常见安装位置。"
        )
        layout.addWidget(netease_group)
        return page

    # ---------------- 飞行物页 ----------------
    def _build_floating_page(self):
        self.floating_page = FloatingSettingsPage(self._floating)
        return self.floating_page

    # ---------------- 文字动效页 ----------------
    def _build_effects_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        fx = self.fx_cfg

        # 文字动效开关（飞行物相关开关已移到「飞行物」页）
        sw_group = QGroupBox("文字动效（飞行物请在「飞行物」页设置）")
        grid = QGridLayout()
        switches = [
            ("char_reveal", "逐字浮现"), ("breathing", "微光呼吸"),
            ("float", "整体浮动"), ("crossfade", "行切换交叠"),
            ("soft_glow", "文字柔光"), ("word_dissolve", "整行消散"),
            ("follow_dissolve", "逐字跟随消散"),
        ]
        self.fx_switches = {}
        for i, (key, label) in enumerate(switches):
            cb = QCheckBox(label)
            cb.setChecked(fx.get(key, FX_DEFAULTS[key]))
            if key == "char_reveal":
                cb.setToolTip(
                    "逐字浮现：歌词【补进窗口】时逐字从雾中浮现，"
                    "不是读条唱到它时才出现。补位延迟结束后开始播放。"
                )
            elif key == "word_dissolve":
                cb.setToolTip("切到下一行时，上一整行从左到右依次消散（飞行物形态在「飞行物」页的「歌词切换」场景设置）")
            elif key == "follow_dissolve":
                cb.setToolTip("读条唱到哪、文字就在哪逐字消散（飞行物在「飞行物」页的「逐字消散配置」场景设置）")
            self.fx_switches[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        sw_group.setLayout(grid)
        layout.addWidget(sw_group)

        # 参数调节：全部用有限挡位（与飞行物页风格一致，不暴露底层数值）
        p_group = QGroupBox("参数调节")
        pform = QFormLayout()
        self.fx_tiers = {}

        PARAM_LABELS = {
            "fade_in_ms": "入场速度", "fade_out_ms": "退场速度",
            "char_stagger_ms": "逐字间隔", "rise_px": "上浮距离",
            "float_px": "浮动幅度", "blur_max": "文字模糊",
            "breath_pct": "呼吸幅度", "breath_ms": "呼吸速度",
            "float_ms": "浮动速度", "glow_len_chars": "柔光长度",
            "batch_gap_ms": "整批空窗", "refill_delay_ms": "补位延迟",
            "dissolve_char_ms": "单字消散速度", "dissolve_stagger_ms": "整行消散跨度",
            "follow_char_ms": "跟随消散速度", "follow_lead": "消散提前量",
        }
        for key, label in PARAM_LABELS.items():
            sel = ValueTierSelector(FX_TIERS[key], fx.get(key, FX_DEFAULTS[key]))
            self.fx_tiers[key] = sel
            pform.addRow(label, sel)
        self.fx_tiers["refill_delay_ms"].setToolTip(
            "仅「原位替换」模式有效：唱完的行位先留空，等消散完再补入下一句。"
        )
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
            (self.reading_btn, "color_reading"),
            (self.translate_btn, "color_translated"),
            (self.glow_btn, "color_glow"),
        ):
            color = self.cfg.get(key, self.cfg.get("color_normal", "#B7B7B7"))
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
        self.netease_edit.setText(self.cfg.get("netease_dir", ""))

        # fx 同步（主题可能改了 fx）
        self.fx_cfg = dict(self.cfg.get("fx", FX_DEFAULTS))
        for key, cb in self.fx_switches.items():
            cb.setChecked(self.fx_cfg.get(key, FX_DEFAULTS[key]))
        for key, sel in self.fx_tiers.items():
            sel.setValue(self.fx_cfg.get(key, FX_DEFAULTS[key]))
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
        self._sync_controls_from_cfg()

    def _apply(self):
        self.cfg.update({
            "font_family": self.font_combo.currentFont().family(),
            "font_size": self.size_spin.value(),
            "font_bold": self.bold_check.isChecked(),
            "color_normal": self.normal_btn.text(),
            "color_highlight": self.highlight_btn.text(),
            "color_reading": self.reading_btn.text(),
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
            "netease_dir": self.netease_edit.text().strip(),
        })
        # 收集 fx 参数（enabled 总开关不再由 UI 暴露，保留配置原值）
        fx = self.cfg.setdefault("fx", dict(FX_DEFAULTS))
        for key, cb in self.fx_switches.items():
            fx[key] = cb.isChecked()
        for key, sel in self.fx_tiers.items():
            fx[key] = sel.value()
        fx["easing"] = self.fx_ease.currentData()
        # 收集飞行物配置
        self._floating = self.floating_page.collect()
        self.cfg["floating"] = self._floating
        # 实时生效并保存，但不关闭窗口（方便边调边看效果）
        if self.on_apply:
            self.on_apply()
        save_config(self.cfg)
