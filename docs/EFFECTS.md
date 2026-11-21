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
self.fx.on_line_changed(idx, y, h, prev_text, prev_char_xs, prev_row_y)  # 行切换：入场/退场/化羽
self.fx.draw_background(painter, w, h)         # 画雾气 + 远景羽毛（文字下层）
self.fx.draw_foreground(painter, w, h)         # 画微粒 + 近景羽毛（文字上层）
self.fx.char_state(i, elapsed)                 # 逐字入场 → (alpha, blur, rise, float_y)
self.fx.char_dissolve_state(i, n, elapsed)     # 逐字消散 → (alpha, blur, dx, dy)，向左上
self.fx.line_alpha(elapsed, entering)          # 整行入场/退场 → (alpha, blur, spread)
self.fx.sweep_pos()                            # 扫光位置 0..1
self.fx.sweep_alpha(pos)                       # 扫光亮度包络 0..1（边界渐隐）
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
- **实现**：`Feather` 粒子，柳叶形 QPainterPath + 羽轴，透明羽毛随时间淡入淡出；对象池上限 `feather_count*2` 防止长跑累积。`_spawn_burst(mode='enter')` 在行附近撒入场羽毛；`_spawn_burst(mode='dissolve')` 让旧文字逐字化羽——每片羽毛从对应字符的原 x 位置生成，带递增延迟，初速度向左上（`vx<0, vy<0`）。
- **参数**：`fx.feathers`（开关）、`fx.feather_count`（12）、`fx.feather_alpha`、`fx.feather_color`、`fx.feather_on_enter`、`fx.feather_on_exit`。
- **调用**：`tick()` 推进；`_spawn_burst()` 生成；`draw_foreground()` 绘制。

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

### 10. 光线扫过（到边界平滑渐隐）
- **作用**：一条低透明斜向高光周期性掠过文字，向右滚动时逐渐变淡，抵达边界时完全消失，不会突然"撞墙"硬切。
- **实现**：`sweep_pos()` 给出 0..1 位置；`sweep_alpha(pos)` 给出亮度包络——左侧 10% 淡入，巡航到 `sweep_fade_start` 后按二次缓动衰减到 0。因为位置用 `%` 循环，两端 alpha 都是 0，回卷时无跳变。歌词窗把包络乘到渐变峰值 alpha 上。
- **参数**：`fx.light_sweep`（开关）、`fx.sweep_ms`（4200）、`fx.sweep_alpha`（峰值 34）、`fx.sweep_fade_start`（渐隐起点 55%）。
- **调用**：歌词窗 `_draw_sweep` → `sweep_pos()` + `sweep_alpha()`。

### 11. 逐字化羽消散（退场动画）
- **作用**：新歌词出现时，上一句从左边开始**一个字一个字化为羽毛**，向左上方飘散、渐隐、融入雾中——不是整行一起淡出。
- **实现**：行切换时歌词窗用 QFontMetrics 算出旧行每个字符的中心 x，连同旧行 y 传给 `on_line_changed`。引擎记录这些位置并生成带递增延迟、向左上运动的消散羽毛（`mode='dissolve'`）；`char_dissolve_state(i, n, elapsed)` 让文字按同样延迟逐字渐隐 + 向左上漂移 + 羽化，两者同步即为"字化羽"。关闭 `word_dissolve` 则退回旧的整行渐隐路径 `_draw_fading_line`。
- **参数**：`fx.crossfade`（交叠开关）、`fx.word_dissolve`（逐字化羽开关）、`fx.feather_on_exit`（化羽羽毛开关）、`fx.dissolve_char_ms`（单字时长 360）、`fx.dissolve_stagger_ms`（整行跨度 420）、`fx.dissolve_drift_x/y`（左移 22 / 上移 34px）、`fx.fade_out_ms`（旧路径时长）。
- **调用**：`prev_line_state()` + 歌词窗 `_draw_dissolving_line()`（或 `_draw_fading_line()`）。

### 12. 整体上下浮动
- **作用**：歌词整体非常轻微地上下浮动，增加呼吸感。
- **实现**：`char_state()` 返回的 `float_y = sin(t/period)*float_px` 叠加到每个字。
- **参数**：`fx.float`（开关）、`fx.float_px`（3）、`fx.float_ms`（5200）。
- **调用**：`char_state()`。

### 13. 消失后补位（三种模式，歌词窗布局层）
- **作用**：控制歌词唱完消失后，剩余歌词如何补位——这是布局策略，不属于粒子特效。
- **模式**（配置 `refill_mode`）：
  - `batch` **整批补位**（默认）：窗口显示 `read_lines` 行一批；唱过的行化羽消失后留空、不再驻留；整批唱完后由 `on_batch_change()` 制造 `batch_gap_ms` 空窗，再随 `fade_in_ms` 整批淡入。实现见歌词窗 `_compute_layout()` / `fx.batch_alpha()`。
  - `slot` **原位替换**：固定 `read_lines` 个行位，唱完的行位立即由 `_update_slots()` 补入下一句，其余行不动。
  - `shift` **逐行上移**：原有行为，当前行固定在第 2 行、整窗上移。
- **参数**：`refill_mode`、`read_lines`（1-8）、`fx.batch_gap_ms`（220）。
- **调用**：歌词窗 `update_lyric()` 触发模式状态更新，`paintEvent()` 经 `_compute_layout()` 取布局绘制。

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
| 扫光 | sweep_ms / sweep_alpha | 4200 / 34 | 周期 / 光条峰值亮度 |
| 扫光 | sweep_fade_start | 55 | 从 55% 处开始渐隐，到右边界归零（无硬切） |
| 化羽消散 | word_dissolve / feather_on_exit | true / true | 逐字化羽 / 化羽羽毛开关 |
| 化羽消散 | dissolve_char_ms / dissolve_stagger_ms | 360 / 420 | 单字时长 / 整行从左到右跨度 |
| 化羽消散 | dissolve_drift_x / dissolve_drift_y | 22 / 34 | 文字向左 / 向上漂移(px) |
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
