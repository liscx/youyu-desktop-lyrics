# -*- coding: utf-8 -*-
"""文字动效参数的有限挡位定义。

每个参数给出 3-5 个挡位：(显示名, 实际写入配置的值)。
配置里存的仍是数值（不是挡位 key），所以旧配置完全兼容——
加载时按数值最接近的挡位高亮，用户点选后写入该挡位的预设值。

设计原则：挡位数少、名字直观、数值经过调校有明显感知差异。
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QButtonGroup, QPushButton

# 参数 -> 挡位列表 [(显示名, 写入值), ...]，按顺序显示
FX_TIERS = {
    "fade_in_ms":     [("极快", 300), ("快", 600), ("中", 900), ("慢", 1500), ("极慢", 2400)],
    "fade_out_ms":    [("极快", 250), ("快", 450), ("中", 700), ("慢", 1200), ("极慢", 1900)],
    "char_stagger_ms": [("无", 0), ("紧凑", 30), ("适中", 60), ("舒缓", 120)],
    "rise_px":        [("无", 0), ("轻微", 6), ("适中", 12), ("明显", 22)],
    "float_px":       [("无", 0), ("轻微", 2), ("适中", 4), ("明显", 8)],
    "blur_max":       [("无", 0), ("轻", 3), ("中", 7), ("强", 12)],
    "breath_pct":     [("无", 0), ("轻", 5), ("中", 10), ("强", 25)],
    "breath_ms":      [("快", 1600), ("中", 3600), ("慢", 6000)],
    "float_ms":       [("快", 2500), ("中", 5200), ("慢", 10000)],
    "batch_gap_ms":   [("无", 0), ("短", 150), ("中", 300), ("长", 600)],
    "refill_delay_ms": [("无", 0), ("短", 400), ("中", 1000), ("长", 2000)],
    "dissolve_char_ms": [("快", 180), ("中", 360), ("慢", 700), ("极慢", 1100)],
    "dissolve_stagger_ms": [("紧凑", 100), ("中", 420), ("舒缓", 900), ("极缓", 1400)],
    "follow_char_ms":  [("快", 180), ("中", 340), ("慢", 650), ("极慢", 950)],
    "follow_lead":     [("无", 0), ("小", 3), ("中", 6), ("大", 15)],
    "glow_len_chars":  [("短", 1.0), ("中", 2.5), ("长", 4.5), ("极长", 7.0)],
}


class ValueTierSelector(QWidget):
    """数值挡位选择器：按钮组，每个挡位对应一个写入配置的数值。

    与 floating_widgets.TierSelector 的区别：那个返回挡位 key，
    这个直接返回数值（文字动效配置里存的就是数值）。
    """
    from PySide6.QtCore import Signal
    changed = Signal()

    def __init__(self, tiers, current, parent=None):
        super().__init__(parent)
        self._tiers = tiers
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        group = QButtonGroup(self)
        group.setExclusive(True)
        self._buttons = []
        for label, value in tiers:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setObjectName("tierBtn")
            btn.setFixedHeight(26)
            group.addButton(btn)
            self._buttons.append((btn, value))
            layout.addWidget(btn)
        group.buttonClicked.connect(self._on_click)
        self.setValue(current)

    def _on_click(self, btn):
        for b, value in self._buttons:
            if b is btn:
                self.changed.emit()
                return

    def value(self):
        for btn, value in self._buttons:
            if btn.isChecked():
                return value
        return self._buttons[0][1]

    def setValue(self, current):
        """选中数值最接近的挡位。"""
        try:
            cur = float(current)
        except (TypeError, ValueError):
            self._buttons[0][0].setChecked(True)
            return
        best, best_diff = self._buttons[0], float("inf")
        for btn, value in self._buttons:
            diff = abs(float(value) - cur)
            if diff < best_diff:
                best, best_diff = (btn, value), diff
        best[0].setChecked(True)
