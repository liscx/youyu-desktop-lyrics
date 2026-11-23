# -*- coding: utf-8 -*-
"""飞行物系统的可视化控件：二维方向盘、活动范围选择、挡位选择器、大小拖条。

遵循交互规范：不暴露角度/坐标数值输入，全部用可视化拖拽 + 有限挡位；
大小用拖条 + 实时示例（示例按引擎同款公式渲染，1:1 对应实际大小）。
"""
import math

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QButtonGroup, QPushButton, QSlider, QLabel
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont

from core.floating_config import (
    TIER_LABELS, MATERIALS, normalize_direction, SIZE_MIN, SIZE_MAX,
)
from ui.floating_objects import MATERIAL_DRAW


class DirectionPad(QWidget):
    """二维方向盘：中心为原点，拖拽控制点决定主飞行方向。

    - 八个基本方向吸附（按住 Shift 禁用吸附，自由调整）
    - 双击恢复默认方向
    - 实时绘制方向箭头
    """
    directionChanged = Signal(list)

    def __init__(self, direction=None, default=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(128, 128)
        self.setCursor(Qt.CrossCursor)
        self._dir = normalize_direction(direction or [0.0, 1.0])
        self._default = list(default or [0.0, 1.0])
        self._dragging = False
        self.setToolTip("拖动圆点设定方向 · 八方向自动吸附 · 按住 Shift 自由调整 · 双击复位")

    def direction(self):
        return list(self._dir)

    def setDirection(self, vec):
        self._dir = normalize_direction(vec)
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._update_from_pos(e.position())

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._update_from_pos(e.position())

    def mouseReleaseEvent(self, e):
        self._dragging = False

    def mouseDoubleClickEvent(self, e):
        self._dir = normalize_direction(self._default)
        self.directionChanged.emit(list(self._dir))
        self.update()

    def _update_from_pos(self, pos):
        cx = cy = self.width() / 2.0
        dx, dy = pos.x() - cx, pos.y() - cy
        # 八方向吸附（45° 倍数），Shift 取消吸附
        if not (QApplication_shift_held()):
            ang = math.atan2(dy, dx)
            step = math.pi / 4
            ang = round(ang / step) * step
            r = math.hypot(dx, dy)
            dx, dy = math.cos(ang) * r, math.sin(ang) * r
        self._dir = normalize_direction([dx, dy])
        self.directionChanged.emit(list(self._dir))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        r = min(w, h) / 2.0 - 10

        # 底盘
        p.setPen(QPen(QColor("#5a5f6b"), 1))
        p.setBrush(QBrush(QColor("#2a2e36")))
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        # 十字 + 八方向刻度
        p.setPen(QPen(QColor("#454b57"), 1))
        for i in range(8):
            ang = i * math.pi / 4
            x1, y1 = cx + math.cos(ang) * r * 0.82, cy + math.sin(ang) * r * 0.82
            x2, y2 = cx + math.cos(ang) * r, cy + math.sin(ang) * r
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.setPen(QPen(QColor("#6b7280"), 1))
        p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
        p.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))
        # 方向箭头
        dx, dy = self._dir
        ex, ey = cx + dx * r * 0.88, cy + dy * r * 0.88
        pen = QPen(QColor("#8ab4f8"), 3, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(cx, cy), QPointF(ex, ey))
        # 箭头头部
        ang = math.atan2(dy, dx)
        head = 9
        for a in (ang + 2.6, ang - 2.6):
            p.drawLine(QPointF(ex, ey),
                       QPointF(ex + math.cos(a) * head, ey + math.sin(a) * head))
        # 中心 + 控制点
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#8ab4f8")))
        p.drawEllipse(QRectF(ex - 6, ey - 6, 12, 12))
        p.setBrush(QBrush(QColor("#c4d4e8")))
        p.drawEllipse(QRectF(cx - 3, cy - 3, 6, 6))
        # 方位文字
        p.setFont(QFont("Microsoft YaHei", 9))
        p.setPen(QColor("#7a8290"))
        p.drawText(QRectF(cx - 8, 2, 16, 14), Qt.AlignCenter, "上")
        p.drawText(QRectF(cx - 8, h - 16, 16, 14), Qt.AlignCenter, "下")
        p.drawText(QRectF(2, cy - 8, 14, 16), Qt.AlignCenter, "左")
        p.drawText(QRectF(w - 16, cy - 8, 14, 16), Qt.AlignCenter, "右")


def QApplication_shift_held():
    """读取 Shift 是否按下（避免重复 import）。"""
    from PySide6.QtWidgets import QApplication
    return bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)


class AreaSelector(QWidget):
    """活动范围可视化：在矩形示意图里拖动整块改变位置，拖边改变大小。

    数值为归一化 [x, y, w, h]，双击恢复默认（全窗口）。
    """
    areaChanged = Signal(list)

    HANDLE = 9

    def __init__(self, area=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 120)
        self.setCursor(Qt.CrossCursor)
        self._area = list(area or [0, 0, 1, 1])
        self._drag = None  # ('move'|'n'|'s'|'e'|'w', start_mouse, start_area)
        self.setToolTip("拖动矩形移动位置 · 拖四边调整范围 · 双击恢复默认")

    def area(self):
        return list(self._area)

    def setArea(self, area):
        self._area = list(area)
        self.update()

    def _rect_px(self):
        x, y, w, h = self._area
        m = 6
        aw, ah = self.width() - 2 * m, self.height() - 2 * m
        return QRectF(m + x * aw, m + y * ah, w * aw, h * ah)

    def _handle_at(self, pos):
        r = self._rect_px()
        d = self.HANDLE
        if abs(pos.x() - r.left()) <= d and r.top() <= pos.y() <= r.bottom():
            return "w"
        if abs(pos.x() - r.right()) <= d and r.top() <= pos.y() <= r.bottom():
            return "e"
        if abs(pos.y() - r.top()) <= d and r.left() <= pos.x() <= r.right():
            return "n"
        if abs(pos.y() - r.bottom()) <= d and r.left() <= pos.x() <= r.right():
            return "s"
        if r.contains(pos):
            return "move"
        return None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = (self._handle_at(e.position()), e.position(), list(self._area))
            self.setCursor(Qt.ClosedHandCursor if self._drag[0] else Qt.CrossCursor)

    def mouseMoveEvent(self, e):
        if not self._drag or not self._drag[0]:
            return
        kind, start, orig = self._drag
        m = 6
        aw, ah = self.width() - 2 * m, self.height() - 2 * m
        ddx = (e.position().x() - start.x()) / aw
        ddy = (e.position().y() - start.y()) / ah
        x, y, w, h = orig
        if kind == "move":
            x = max(0.0, min(1.0 - w, x + ddx))
            y = max(0.0, min(1.0 - h, y + ddy))
        else:
            if "w" in kind:
                nx = max(0.0, min(x + w - 0.05, x + ddx))
                w += x - nx
                x = nx
            if "e" in kind:
                w = max(0.05, min(1.0 - x, w + ddx))
            if "n" in kind:
                ny = max(0.0, min(y + h - 0.05, y + ddy))
                h += y - ny
                y = ny
            if "s" in kind:
                h = max(0.05, min(1.0 - y, h + ddy))
        self._area = [x, y, w, h]
        self.areaChanged.emit(list(self._area))
        self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None
        self.setCursor(Qt.CrossCursor)

    def mouseDoubleClickEvent(self, e):
        self._area = [0, 0, 1, 1]
        self.areaChanged.emit(list(self._area))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # 窗口示意底
        p.setPen(QPen(QColor("#5a5f6b"), 1))
        p.setBrush(QBrush(QColor("#22262d")))
        p.drawRect(QRectF(6, 6, self.width() - 12, self.height() - 12))
        # 活动区
        r = self._rect_px()
        p.setBrush(QBrush(QColor(90, 130, 200, 45)))
        p.setPen(QPen(QColor("#8ab4f8"), 1.5))
        p.drawRect(r)
        # 四角把手
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#8ab4f8")))
        d = 5
        for hx, hy in ((r.left(), r.top()), (r.right(), r.top()),
                       (r.left(), r.bottom()), (r.right(), r.bottom())):
            p.drawRect(QRectF(hx - d, hy - d, d * 2, d * 2))


class TierSelector(QWidget):
    """有限挡位选择器：一组互斥按钮，返回挡位 key。"""
    changed = Signal(str)

    def __init__(self, tier_name, current, parent=None):
        super().__init__(parent)
        self._tier = tier_name
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        for key, label in TIER_LABELS[tier_name]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setObjectName("tierBtn")
            btn.setFixedHeight(26)
            self._group.addButton(btn)
            self._buttons[key] = btn
            layout.addWidget(btn)
        self._group.buttonClicked.connect(self._on_click)
        self.setValue(current)

    def _on_click(self, btn):
        for key, b in self._buttons.items():
            if b is btn:
                self.changed.emit(key)
                return

    def value(self):
        for key, b in self._buttons.items():
            if b.isChecked():
                return key
        return next(iter(self._buttons))

    def setValue(self, key):
        if key in self._buttons:
            self._buttons[key].setChecked(True)


class SizePreview(QWidget):
    """飞行物大小实时示例：按与引擎完全相同的尺寸公式绘制当前素材。

    引擎实际尺寸 s = 倍率 × MATERIALS[material]["base"]，示例用同一公式，
    因此示例大小就是歌词窗里飞行物的实际大小。
    """

    def __init__(self, material="feather", mult=1.0, parent=None):
        super().__init__(parent)
        self._material = material
        self._mult = mult
        self.setFixedSize(80, 80)
        self.setToolTip("示例大小 = 实际飞行物大小")

    def set_material(self, material):
        self._material = material
        self.update()

    def set_mult(self, mult):
        self._mult = mult
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # 参考框：表示窗口边界，帮助判断相对大小
        p.setPen(QPen(QColor("#4a4f59"), 1, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(2, 2, self.width() - 4, self.height() - 4)
        drawer = MATERIAL_DRAW.get(self._material)
        if not drawer:
            return
        meta = MATERIALS.get(self._material, {"base": 10})
        s = self._mult * meta["base"]   # 与 FlyingObject.draw 一致的尺寸
        p.translate(self.width() / 2, self.height() / 2)
        drawer(p, s, QColor("#DCE6F1"))


class SizeSlider(QWidget):
    """飞行物大小：拖条 + 实时示例。拖动即实时变化，示例即实际大小。"""
    changed = Signal()

    def __init__(self, material, mult, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(30, 250)          # 0.30x ~ 2.50x
        self._slider.setValue(int(round(float(mult) * 100)))
        self._slider.setFixedWidth(140)
        self._preview = SizePreview(material, float(mult))
        self._label = QLabel(f"{float(mult):.1f}x")
        self._label.setMinimumWidth(36)
        row.addWidget(self._slider, 1)
        row.addWidget(self._preview)
        row.addWidget(self._label)
        self._slider.valueChanged.connect(self._on_change)

    def _on_change(self, v):
        mult = v / 100.0
        self._preview.set_mult(mult)
        self._label.setText(f"{mult:.1f}x")
        self.changed.emit()

    def value(self):
        """返回大小倍率（float）。"""
        return self._slider.value() / 100.0

    def setValue(self, mult):
        try:
            self._slider.setValue(int(round(float(mult) * 100)))
        except (TypeError, ValueError):
            self._slider.setValue(100)

    def set_material(self, material):
        """素材切换时同步示例（不同素材 base 不同，示例尺寸跟着变）。"""
        self._preview.set_material(material)
