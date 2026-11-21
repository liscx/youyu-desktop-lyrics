# 雾中飞羽 · 特效系统说明

一套为桌面歌词设计的电影感动态效果系统，实现在 `ui/effects.py`，主题定义在 `themes/presets.py` 的 `MIST`。

设计理念：空灵、安静、自由、孤独。低饱和月白/雾灰/淡蓝配色，少量银白高光。
歌词始终是视觉中心——所有特效都围绕文字展开，避免霓虹爆闪与过度装饰。

## 一、整体架构

```
ui/effects.py
├─ 缓动函数 EASINGS / eased()     数学缓动，杜绝线性跳变
├─ _Particle                      通用漂浮粒子（位置/速度/生命周期/淡入淡出）
├─ Feather / Mote                 羽毛 / 微粒（各自 draw()）
└─ EffectEngine                   引擎：时钟、状态、粒子池、绘制
```

**调用方式**（歌词窗 `ui/lyric_window.py` 中的实际用法）：

```python
self.fx = EffectEngine(cfg)                    # 构造
self.fx.configure(cfg)                         # 配置变更时重读（apply_config 里）
self.fx.tick(dt_ms, w, h)                      # 每帧推进（_step_fx，QTimer 33ms ≈ 30fps）
self.fx.on_line_changed(idx, y, h, prev_text)  # 当前行切换时触发入场/退场/撒羽毛
self.fx.draw_background(painter, w, h)         # 画雾气 + 远景羽毛（文字下层）
self.fx.draw_foreground(painter, w, h)         # 画微粒 + 近景羽毛（文字上层）
self.fx.char_state(i, elapsed)                 # 逐字状态 → (alpha, blur, rise, float_y)
self.fx.line_alpha(elapsed, entering)          # 整行入场/退场 → (alpha, blur, spread)
```

所有状态集中在引擎，歌词窗只负责调用与把文字画上去。粒子用对象池复用、数量恒定，
不重建任何控件（对应"禁止高频 DOM 重建"的 Web 要求），长时间运行内存稳定。

## 二、动画模块（作用 / 参数 / 调用）

### 1. 缓动函数 `eased(t, name)`
- **作用**：把线性进度 0..1 转成有加减速的曲线，是所有动画"不突然跳变"的基础。
- **参数**：`name` ∈ `ease_out`（快起慢收，用于浮现）、`ease_in_out`（平滑）、`ease_in`（慢起快收，用于消散）、`linear`。
- **配置**：`fx.easing`。

### 2. 淡雾显现 + 羽化浮现（入场）
- **作用**：文字从完全隐藏，经低透明雾气，逐渐显现；同时由模糊到清晰、从下方上浮 8–15px。
- **实现**：`line_alpha(elapsed, True)` 给出整行 alpha/blur；歌词窗用 `_draw_blurred_text` 以多层微偏移半透明绘制模拟羽化（等价 Canvas 的 shadowBlur / CSS filter: blur），随 blur→0 收敛为单次清晰绘制。
- **参数**：`fx.fade_in_ms`（900）、`fx.blur_max`（7）、`fx.rise_px`（12）、`fx.easing`。
- **调用**：`char_state()` / `line_alpha(elapsed, True)`。

### 3. 逐字浮现（非打字机）
- **作用**：每个字符有独立延迟与透明度/模糊过渡，像逐个从雾里浮出，而不是机械地一个个蹦字。
- **实现**：`char_state(i, elapsed)`，`delay = i * char_stagger_ms`，每字有独立的 alpha、blur、rise。
- **参数**：`fx.char_reveal`（开关）、`fx.char_stagger_ms`（60）、`fx.fade_in_ms`。
- **调用**：歌词窗 `_draw_effect_line` 里逐字循环调用。

### 4. 羽毛漂浮 + 入场/退场撒羽毛
- **作用**：文字周围生成少量半透明羽毛，缓慢漂浮、旋转、飘远消失；出场/入场时额外撒一小簇。
- **实现**：`Feather` 粒子，柳叶形 QPainterPath + 羽轴，透明羽毛随时间淡入淡出；对象池上限 `feather_count*3` 防止长跑累积。
- **参数**：`fx.feathers`（开关）、`fx.feather_count`（12）、`fx.feather_alpha`、`fx.feather_color`、`fx.feather_on_enter`、`fx.feather_on_exit`。
- **调用**：`tick()` 推进；`_burst_feathers()` 生成；`draw_foreground()` 绘制。

### 5. 远景羽毛（空间层次）
- **作用**：更小、更淡、更慢的羽毛画在文字下方，制造纵深感。
- **参数**：`fx.far_feathers`（开关）、`fx.far_feather_count`（8）。
- **调用**：`draw_background()`。

### 6. 微粒漂浮
- **作用**：极小的圆点在文字周围随机漂浮。
- **参数**：`fx.motes`（开关）、`fx.mote_count`（22）。
- **调用**：`draw_foreground()`。

### 7. 雾气流动
- **作用**：低透明度渐变横向缓慢流动，绝不遮挡文字。
- **实现**：QLinearGradient 随时间平移。
- **参数**：`fx.mist_flow`（开关）、`fx.mist_speed`（0.15）、`fx.mist_alpha`（26）、`fx.mist_color`。
- **调用**：`draw_background()`。

### 8. 微光呼吸
- **作用**：歌词主体亮度极轻微起伏。
- **实现**：`breathe()` 返回 `1 + sin(t/period)*pct`，乘到文字 alpha。
- **参数**：`fx.breathing`（开关）、`fx.breath_pct`（0.10）、`fx.breath_ms`（3600）。
- **调用**：歌词窗 `_draw_effect_line`。

### 9. 文字柔光（非霓虹描边）
- **作用**：文字边缘极细、低透明的柔化，以及高亮部分一层淡淡光晕——刻意避免廉价霓虹描边。
- **参数**：`fx.soft_glow`（开关）、主题 `outline_width`、主题 `glow_enabled`/`glow_radius`。
- **调用**：歌词窗 `_draw_outline_for_text` / `_draw_effect_line`。

### 10. 光线扫过
- **作用**：一条低透明斜向高光周期性掠过文字。
- **实现**：`sweep_pos()` 返回 0..1 位置，歌词窗用渐变矩形绘制。
- **参数**：`fx.light_sweep`（开关）、`fx.sweep_ms`（4200）。
- **调用**：歌词窗 `_draw_sweep`。

### 11. 行切换交叠（退场动画）
- **作用**：新歌词出现时，上一句以渐隐 + 羽化扩散短暂交叠，再融入雾中消失。
- **实现**：`on_line_changed` 记录上一行；`prev_line_state()` 返回退场状态；歌词窗先画退场行再画当前行。
- **参数**：`fx.crossfade`（开关）、`fx.fade_out_ms`（700）、`fx.feather_on_exit`。
- **调用**：`prev_line_state()` + 歌词窗 `_draw_fading_line`。

### 12. 整体上下浮动
- **作用**：歌词整体非常轻微地上下浮动，增加呼吸感。
- **实现**：`char_state()` 返回的 `float_y = sin(t/period)*float_px` 叠加到每个字。
- **参数**：`fx.float`（开关）、`fx.float_px`（3）、`fx.float_ms`（5200）。
- **调用**：`char_state()`。

## 三、配置总表

全部参数在 `core/config.py` 的 `FX_DEFAULTS`，运行时在 `config.json` 的 `fx` 段。
每个开关与参数都能在设置面板「雾中飞羽 · 特效」页调整。

| 类别 | 键 | 默认 | 说明 |
|------|----|------|------|
| 总开关 | enabled | true | 关闭则整个特效系统不工作，回退到经典绘制 |
| 时间 | fade_in_ms / fade_out_ms | 900 / 700 | 入场/退场时长 |
| 逐字 | char_stagger_ms | 60 | 每字延迟 |
| 羽化 | blur_max | 7 | 模糊最大程度 |
| 距离 | rise_px / float_px | 12 / 3 | 上浮 / 浮动幅度 |
| 呼吸 | breath_pct / breath_ms | 0.10 / 3600 | 幅度 / 周期 |
| 扫光 | sweep_ms | 4200 | 周期 |
| 雾气 | mist_speed / mist_alpha | 0.15 / 26 | 速度 / 浓度 |
| 粒子 | feather_count / far_feather_count / mote_count | 12 / 8 / 22 | 数量 |
| 颜色 | feather_color / mist_color | #DCE6F1 / #B7C6D8 | 羽毛 / 雾气 |
| 缓动 | easing | ease_out | 曲线 |

## 四、关于技术实现的说明

你给的提示词以 CSS/Canvas 描述。本项目是 PySide6 桌面应用，因此做了等价映射：

- CSS `transform`/`opacity` → QPainter 的 `translate/rotate` 与 QColor alpha（底层走 Qt 的 transform 与合成，GPU 加速由 Qt 图形后端负责）。
- CSS `filter: blur()` / Canvas `shadowBlur` → `_draw_blurred_text` 多层微偏移半透明绘制，blur→0 时退化为单次绘制，性能可控。
- CSS Animation 的逐帧 → 单个 QTimer（33ms）驱动纯绘制，无控件重建、无高频对象创建。
- 长跑内存 → 粒子用对象池、数量恒定、羽毛有上限；所有动画基于时间戳而非累加状态，切后台回来不会跳变。

## 五、切换到这套特效

主题下拉框选「❧ 雾中飞羽」，或按 `Ctrl+Alt+T` 轮换到它。该主题会自动开启契合的特效参数。
也可在「特效」页单独开关任意动画模块、调节时长/浓度/数量。
