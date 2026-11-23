# 文字动效说明（原「雾中飞羽」特效系统）

一套为桌面歌词设计的电影感动态效果系统。文字动效实现在 `ui/effects.py`，
主题定义在 `themes/presets.py` 的 `MIST`。

设计理念：空灵、安静、自由、孤独。低饱和月白/雾灰/淡蓝配色，少量银白高光。
歌词始终是视觉中心——所有特效都围绕文字展开，避免霓虹爆闪与过度装饰。

> **架构说明**：飘落粒子（羽毛/微粒/雨滴）已彻底迁移到通用飞行物系统
> `ui/floating_objects.py`，支持羽毛/樱花/花瓣/雪花/枫叶/光点/蝴蝶等素材，
> 四个触发场景各自独立配置。`ui/effects.py` 现只负责文字动效
> （逐字浮现、呼吸、浮动、交叠、文字消散），不再持有任何粒子池。
> 行切换时通过注入的 `self.floater.burst(scene, ...)` 触发飞行物。
> 飞行物系统详见 README「飞行物系统」一节。

## 一、整体架构

```
ui/effects.py
├─ 缓动函数 EASINGS / eased()     数学缓动，杜绝线性跳变
└─ EffectEngine                   文字动效引擎：时钟、逐字状态
       └─ self.floater            注入的飞行物引擎（粒子全部由它负责）

ui/floating_objects.py
├─ MATERIAL_DRAW                  各素材绘制函数
├─ FlyingObject                   通用飞行物（运动状态）
└─ FloatingEngine                 四场景对象池 + 生命周期 + 绘制
```

**调用方式**（歌词窗 `ui/lyric_window.py` 中的实际用法）：

```python
self.floating = FloatingEngine(ensure_floating(cfg))  # 飞行物引擎
self.fx = EffectEngine(cfg); self.fx.floater = self.floating
self.fx.configure(cfg)                         # 配置变更时重读（apply_config 里）
self.fx.on_line_changed(idx, y, h, prev_text, prev_char_xs, prev_row_y)  # 行切换→触发飞行物 enter/switch
self.fx.tick(dt_ms, w, h)                      # 每帧推进（同时推进 floater）
self.floating.draw(painter, layer="background") # 远景飞行物（文字下层）
self.floating.draw(painter, layer="foreground") # 近景飞行物（文字上层）
self.fx.char_state(i, elapsed)                 # 逐字入场 → (alpha, blur, rise, float_y)
self.fx.char_dissolve_state(i, n, elapsed)     # 逐字消散 → (alpha, blur, dx=0, dy=0)，文字原地淡出
self.fx.follow_reset(idx, char_xs, y, h)       # 切行：重置逐字跟随消散跟踪
self.fx.set_follow_chars(chars)                # 缓存当前行字符（收尾绘制用）
self.fx.follow_step(progress, dt)              # 每帧推进：读条扫过的字逐个消散→触发飞行物 exit
self.fx.follow_char_alpha(i)                   # 当前行第 i 字可见度 0..1
self.fx.follow_prev_state()                    # 收尾行 → [(char, alpha, x), ...]，散完后返回 None
self.fx.reset_follow_all()                     # 换歌：彻底重置跟随消散状态 + 清空飞行物
self.fx.line_alpha(elapsed, entering)          # 整行入场/退场 → (alpha, blur, spread)
```

所有文字状态集中在 EffectEngine；粒子用对象池复用、数量恒定，长时间运行内存稳定。

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
- **触发时机（重要）**：在歌词行【补进窗口】的那一刻播放，不是读条唱到它才播放。歌词窗为每行记录 `_reveal_start[行索引]`（首次出现在布局的时刻），`elapsed = 当前时刻 - 入场时刻`；因此切当前行、读条推进都不会重播浮现——只有补位进来的新行才会逐字出现。换歌会清空该表，让新歌从头浮现。
- **实现**：`char_state(i, elapsed)`，`delay = i * char_stagger_ms`，每字有独立的 alpha、blur、rise。
- **参数**：`fx.char_reveal`（开关）、`fx.char_stagger_ms`（60）、`fx.fade_in_ms`、`fx.refill_delay_ms`（slot 空位延迟会推迟补位，也就推迟浮现）。
- **调用**：歌词窗 `_draw_effect_line`（当前行）/ `_draw_reveal_line`（补位预览行）里逐字循环调用。

### 4. 飘落粒子（羽毛/花瓣/雨滴等）→ 已迁出

**本章节内容已移至 README「飞行物系统」一节。**

飘落粒子不再由本引擎实现。现由 `ui/floating_objects.py` 的统一飞行物系统负责：
- 素材：羽毛、樱花、花瓣、雪花、枫叶、光点、蝴蝶、雨丝（自定义图片预留）。
- 四个触发场景（背景漂浮/入场/消失/切换）各自独立配置素材、数量、方向、速度、大小、随机偏向与旋转。
- 数量/速度等用有限挡位，大小用拖条 + 实时示例，方向用二维方向盘，背景活动范围用可拖动矩形。
- 配置在 `core/floating_config.py`，UI 在「设置 → 飞行物」页。

本引擎仅在行切换时通过 `floater.burst("enter"/"exit"/"switch", origins=...)` 触发对应场景，
不再持有粒子池，也不再读 `fx.feathers` / `fx.feather_count` 等旧键。

### 8. 微光呼吸
- **作用**：歌词主体亮度极轻微起伏。
- **实现**：`breathe()` 返回 `1 + sin(t/period)*pct`，乘到文字 alpha。
- **参数**：`fx.breathing`（开关）、`fx.breath_pct`（百分比整数 0-50，设置面板填百分比，引擎 /100 转小数）、`fx.breath_ms`（3600）。
- **调用**：歌词窗 `_draw_effect_line`。

### 9. 文字柔光（非霓虹描边）
- **作用**：文字边缘极细、低透明的柔化，以及高亮部分一层淡淡光晕——刻意避免廉价霓虹描边。
- **参数**：`fx.soft_glow`（开关）、主题 `outline_width`、主题 `glow_enabled`/`glow_radius`、主题 `color_glow`（辉色）、`fx.glow_len_chars`（柔光条长度，默认 2.5 字宽）。
- **调用**：歌词窗 `_draw_outline_for_text` / `_draw_effect_line`。

### 11. 整行消散（文字侧；退场动画）
- **作用**：新歌词出现时，上一句从左边开始**一个字一个字消散**、渐隐、融入雾中——不是整行一起淡出。
- **实现**：`char_dissolve_state(i, n, elapsed)` 让文字按从左到右的延迟**原地**渐隐 + 羽化（文字不移动）。关闭 `word_dissolve` 则退回整行渐隐路径 `_draw_fading_line`。**伴随的飘落粒子由飞行物系统负责**：切行时 `on_line_changed` 触发 `floater.burst("switch", ...)`，从每个字符原位发出飞行物。
- **参数（文字侧）**：`fx.crossfade`（交叠开关）、`fx.word_dissolve`（整行消散开关）、`fx.dissolve_char_ms`（单字时长 360）、`fx.dissolve_stagger_ms`（整行跨度 420）、`fx.fade_out_ms`（旧路径时长）。
- **参数（粒子侧）**：飞行物「歌词切换」场景的素材/数量/方向/速度等，见「设置 → 飞行物」。
- **调用**：`prev_line_state()` + 歌词窗 `_draw_dissolving_line()`（或 `_draw_fading_line()`）。

### 11b. 逐字跟随消散（贯穿整行生命周期，mist 默认开启）
- **作用**：消散不再只在切行瞬间发生，而是**唱到哪散到哪**——读条扫过的字立刻开始原地消散；唱到一半时前半句已散掉。切到下一行时，上一行还没散完的字继续**慢慢散完**（收尾）。
- **实现**：歌词窗每帧用 `_line_progress()`（由 `position_ms` 在当前行时间轴上线性插值）算出读条进度，传给 `follow_step(progress, dt)`。引擎为每个字维护消散进度 `0→1`：当读条越过该字（含 `follow_lead` 提前量）时开始计时，每个字**首次**开始消散时触发 `floater.burst("exit", origins=[该字位置], count_override=1)`（只触发一次）。`follow_char_alpha(i)` 返回该字可见度供绘制。切行时 `follow_reset()` 把未散完的字快照到收尾队列，`follow_prev_state()` 逐帧返回收尾字及其 alpha，全部到 1 后自动清空。换歌时 `reset_follow_all()` 彻底重置并清空飞行物。
- **参数（文字侧）**：`fx.follow_dissolve`（总开关）、`fx.follow_char_ms`（单字从被扫过到散完 340ms）、`fx.follow_lead`（读条越过该字多少比例后开始消散，6%）。
- **参数（粒子侧）**：飞行物「逐字消散配置」场景控制伴随粒子的素材、数量、方向、速度等——原 `feather_on_exit` / `dissolve_drift_x/y` / `dissolve_feathers_per_char` / `dissolve_spread_y` 等旧键已废弃，统一由该场景的方向盘与挡位接管。
- **调用**：歌词窗 `_step_fx` → `follow_step()`；`_draw_effect_line` → `follow_char_alpha(i)`；退场绘制 → `follow_prev_state()` + `_draw_follow_tail()`。
- **注意**：开启后模块 11 的退场整行消散不再触发（消散已分散到整个生命周期），关闭 `follow_dissolve` 则退回模块 11 的切行整行消散。

### 12. 整体上下浮动
- **作用**：歌词整体非常轻微地上下浮动，增加呼吸感。
- **实现**：`char_state()` 返回的 `float_y = sin(t/period)*float_px` 叠加到每个字。
- **参数**：`fx.float`（开关）、`fx.float_px`（3）、`fx.float_ms`（5200）。
- **调用**：`char_state()`。

### 13. 消失后补位（三种模式，歌词窗布局层）
- **作用**：控制歌词唱完消失后，剩余歌词如何补位——这是布局策略，不属于粒子特效。
- **模式**（配置 `refill_mode`）：
  - `batch` **整批补位**（默认）：窗口显示 `read_lines` 行一批；唱过的行化羽消失后留空、不再驻留；整批唱完后由 `on_batch_change()` 制造 `batch_gap_ms` 空窗，再随 `fade_in_ms` 整批淡入。实现见歌词窗 `_compute_layout()` / `fx.batch_alpha()`。
  - `slot` **原位替换**：固定 `read_lines` 个行位，唱完的行位先**留空**，等消散羽毛飘走（延迟 `fx.refill_delay_ms`）后再由 `_process_pending_refill()` 补入下一句——避免"羽毛还在飞、新歌词就叠上来"。延迟期间该行不绘制任何歌词；若下一句追上当前行（切行/seek）则立即补入，保证当前行不缺失。
  - `shift` **逐行上移**：原有行为，当前行固定在第 2 行、整窗上移。
- **参数**：`refill_mode`、`read_lines`（1-8）、`fx.batch_gap_ms`（220）、`fx.refill_delay_ms`（1000，仅 slot 模式；0=立即补位）。
- **调用**：歌词窗 `update_lyric()` 触发模式状态更新（`_update_slots()` 登记补位 / `_process_pending_refill()` 每帧兑现），`paintEvent()` 经 `_compute_layout()` 取布局绘制。

## 三、配置总表

文字/氛围参数在 `core/config.py` 的 `FX_DEFAULTS`，运行时在 `config.json` 的 `fx` 段；
可在设置面板「文字动效」页调整。飘落粒子的配置独立在 `config.json` 的 `floating` 段
（`core/floating_config.py`），在「飞行物」页调整。

| 类别 | 键 | 默认 | 说明 |
|------|----|------|------|
| 总开关 | enabled | true | 关闭则整个特效系统不工作，回退到经典绘制 |
| 时间 | fade_in_ms / fade_out_ms | 900 / 700 | 入场/退场时长 |
| 逐字 | char_stagger_ms | 60 | 每字延迟 |
| 模糊 | blur_max | 7 | 文字模糊最大程度 |
| 距离 | rise_px / float_px | 12 / 3 | 上浮 / 浮动幅度 |
| 呼吸 | breath_pct / breath_ms | 10% / 3600 | 幅度(百分比整数,引擎/100) / 周期 |
| 浮动 | float_ms | 5200 | 浮动周期 |
| 柔光 | glow_len_chars | 2.5 | 当前行柔光条长度(字宽倍数) |
| 歌词色 | color_reading | 同普通色 | 当前行读条未扫到的字颜色（可区别于其他行） |
| 消散 | word_dissolve | true | 整行消散开关（切行时整行依次消散） |
| 消散 | dissolve_char_ms / dissolve_stagger_ms | 360 / 420 | 单字时长 / 整行从左到右跨度 |
| 补位 | refill_mode / read_lines | slot / 2 | 补位模式 / 读条行数 |
| 补位 | batch_gap_ms / refill_delay_ms | 220 / 1000 | 整批空窗(ms) / 原位替换空位补位延迟(ms) |
| 逐字跟随 | follow_dissolve | true | 唱到哪散到哪 + 切行收尾总开关 |
| 逐字跟随 | follow_char_ms / follow_lead | 340 / 6 | 单字消散时长(ms) / 读条越过多少(%)后开始散 |
| 飞行物色 | feather_color | #DCE6F1 | 注入飞行物引擎的主题色 |
| 缓动 | easing | ease_out | 曲线 |

> 原 `feathers` / `motes` / `feather_count` / `feather_on_*` / `dissolve_drift_*` 等粒子键
> 已废弃，统一由「飞行物」页的四场景配置接管（见 README）。迁移函数会在首次启动时
> 读取一次旧键（老配置文件仍可平滑升级），之后不再使用。

## 四、关于技术实现的说明

你给的提示词以 CSS/Canvas 描述。本项目是 PySide6 桌面应用，因此做了等价映射：

- CSS `transform`/`opacity` → QPainter 的 `translate/rotate` 与 QColor alpha（底层走 Qt 的 transform 与合成，GPU 加速由 Qt 图形后端负责）。
- CSS `filter: blur()` / Canvas `shadowBlur` → `_draw_blurred_text` 多层微偏移半透明绘制，blur→0 时退化为单次绘制，性能可控。
- CSS Animation 的逐帧 → 单个 QTimer（33ms）驱动纯绘制，无控件重建、无高频对象创建。
- 长跑内存 → 飞行物用对象池、数量恒定且有上限；所有动画基于时间戳而非累加状态，切后台回来不会跳变。

## 五、切换到这套特效

主题下拉框选「❧ 雾中飞羽」，或按 `Ctrl+Alt+T` 轮换到它。该主题会自动开启契合的文字动效参数。
可在「文字动效」页开关文字/氛围模块、调节时长/浓度；在「飞行物」页设置飘落粒子的素材、数量、方向和活动范围。
