# -*- coding: utf-8 -*-
"""生成内置 SVG 素材（对应原 QPainterPath 手绘素材，坐标一致）。

一次性脚本，产出 assets/materials/*.svg。viewBox 统一 -12..12，
形状按 s=12 绘制（与原 draw 函数坐标一致，仅放大到填满 viewBox）。
"""
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "assets", "materials")
os.makedirs(OUT, exist_ok=True)

S = 12  # 形状绘制尺度，viewBox 半宽


def write(name, body):
    svg = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-12 -12 24 24">\n'
           f'{body}\n</svg>\n')
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote", path)


# 羽毛：柳叶形 + 羽轴（_draw_feather）
s = S
write("feather.svg", f'''  <path d="M0,{-s} C{s*0.72},{-s*0.35} {s*0.72},{s*0.45} 0,{s} C{-s*0.72},{s*0.45} {-s*0.72},{-s*0.35} 0,{-s} Z" fill="#DCE6F1"/>
  <line x1="0" y1="{-s*0.9}" x2="0" y2="{s*0.9}" stroke="#F2F6FB" stroke-width="0.96"/>''')

# 花瓣：柳叶形 + 中脉（_draw_petal）
write("petal.svg", f'''  <path d="M0,{-s} C{s*0.62},{-s*0.4} {s*0.5},{s*0.6} 0,{s*0.9} C{-s*0.5},{s*0.6} {-s*0.62},{-s*0.4} 0,{-s} Z" fill="#DCE6F1"/>
  <line x1="0" y1="{-s*0.7}" x2="0" y2="{s*0.6}" stroke="#C8D0DA" stroke-width="0.72"/>''')

# 枫叶：五裂掌状（_draw_maple 多边形）
pts = [(0, -12), (3.36, -5.04), (8.64, -6.6), (6, -1.44), (11.4, 2.64),
       (5.04, 3.84), (3.6, 9.36), (0, 6)]
d = f"M{pts[0][0]},{pts[0][1]} " + " ".join(f"L{x},{y}" for x, y in pts[1:])
d += " " + " ".join(f"L{-x},{y}" for x, y in reversed(pts[:-1])) + " Z"
write("maple.svg", f'  <path d="{d}" fill="#DCE6F1"/>')

# 光点：三层同心圆（_draw_glow）
write("glow.svg", '''  <circle cx="0" cy="0" r="19.2" fill="#DCE6F1" fill-opacity="0.18"/>
  <circle cx="0" cy="0" r="12" fill="#DCE6F1" fill-opacity="0.45"/>
  <circle cx="0" cy="0" r="5.4" fill="#DCE6F1" fill-opacity="1"/>''')

# 蝴蝶：四翅 + 身体（_draw_butterfly）
wings = []
for sign in (-1, 1):
    wings.append(f'  <path d="M0,{-s*0.25} C{sign*s*1.1},{-s*1.2} {sign*s*1.15},{s*0.35} 0,{s*0.2} Z" fill="#DCE6F1"/>')
    wings.append(f'  <path d="M0,{s*0.1} C{sign*s*0.8},{s*0.15} {sign*s*0.75},{s*0.95} 0,{s*0.5} Z" fill="#DCE6F1"/>')
write("butterfly.svg", "\n".join(wings) + f'\n  <ellipse cx="0" cy="0.6" rx="1.08" ry="7.8" fill="#F2F6FB"/>')

# 雨丝：短斜线（_draw_rain）
write("rain.svg", f'  <line x1="0" y1="{-s}" x2="{-s*0.18}" y2="{s}" stroke="#9FC6FF" stroke-width="1.44" stroke-linecap="round"/>')

print("done")
