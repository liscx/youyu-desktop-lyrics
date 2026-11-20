# youyu-desktop-lyrics

一款很忧郁的桌面歌词插件 —— 悬浮置顶、点击穿透、逐字高亮、实时翻译，
带**多款可切换外观主题**。Developed by Python + PySide6。

## 启动

双击 `启动歌词.bat` 即可（会自动寻找 Python，优先 `D:\python\<版本>\python.exe`）。

命令行启动：

```bat
python main.py
```

## 外观主题（多模式）

内置三款主题，随时切换、即时生效：

| 主题 | 说明 |
|------|------|
| ☂ **忧郁** | 雾蓝冷色、雨滴飘落、纤细疏朗的排版（默认） |
| ♪ **经典** | 清爽通透，最初的桌面歌词设计 |
| ✦ **霓虹** | 青与品红交织的强烈光晕 |

切换方式（任选）：
- **Ctrl+Alt+T** 循环切换主题
- 右键歌词窗 → “下一个主题”
- 托盘图标 → “外观主题” 子菜单
- 托盘 → “设置” → 顶部“外观主题”下拉框（可即时预览并微调各项）

> 主题的参数定义在 `themes/presets.py`，新增主题只需往 `THEMES` 里加一个字典；
> 专属绘制效果（如雨滴）在 `ui/lyric_window.py` 里按主题字段分支。

## 操作

| 操作 | 方式 |
|------|------|
| 解锁 / 锁定歌词 | **Ctrl+Alt+L**，或右键歌词窗 / 托盘菜单 |
| 显示 / 隐藏 | **Ctrl+Alt+H**，或单击托盘图标 |
| 拖动窗口 | 先解锁，再按住歌词窗拖动 |
| 播放控制 | 上一首 / 播放暂停 / 下一首（托盘菜单或媒体键） |

设置面板可调「显示行数」（1–8 行，窗口高度自动适配）与「显示行号」（右上角显示 `当前行 / 总行数`）。

> **关于时间校准**：CDP 开启时进度直接来自网易云内核，天然精确，
> 无需也无法校准——因此「对齐到当前行」「±2s」这类入口会自动隐藏。
> 只有 CDP 失效、降级到「标题模式」（进度靠本地估算）时，这些校准入口才会出现：
> 解锁后单击某行歌词对齐，或 Ctrl+← / →（±2 秒）微调。

## 精确进度（CDP）

歌词进度通过网易云内嵌 DevTools 端口（`127.0.0.1:21631`）读取，启动即从当前播放位置开始，不会从头。

补丁工具（需先关闭网易云）：

```bat
python cdp_patch.py status   :: 查看补丁状态
python cdp_patch.py patch    :: 打补丁（自动备份 libcef.dll.bak）
python cdp_patch.py revert   :: 回滚
```

> 网易云更新会替换 `libcef.dll`，届时补丁失效、自动降级到标题模式。关闭网易云后重新 `patch` 即可。

## 工程结构

```
desktop-gc/
├── main.py              程序入口（仅做组装）
├── config.json          运行时配置（外观/主题/位置/行为）
├── 启动歌词.bat
├── core/                数据与逻辑层（无 UI 依赖）
│   ├── config.py        配置读写
│   ├── media.py         播放监控（CDP / SMTC / 标题）
│   ├── lyrics.py        歌词获取、解析、缓存
│   └── cdp.py           DevTools 协议客户端
├── themes/              外观主题
│   └── presets.py       主题预设与切换逻辑
├── ui/                  界面层
│   ├── lyric_window.py  歌词窗绘制与交互
│   ├── settings.py      设置面板
│   ├── tray.py          系统托盘
│   └── hotkey.py        全局热键 / Win32 工具
└── tools/
    └── cdp_patch.py     libcef 补丁工具（根目录 cdp_patch.py 为兼容入口）
```

依赖分层原则：`ui → themes / core`，`core` 不反向依赖 UI。

## 依赖

见 `requirements.txt`。主要：PySide6、requests、pycryptodome、winrt（SMTC）、websocket-client。
