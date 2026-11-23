# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：文件夹版。

主程序 youyu.exe（GUI，无控制台）与补丁工具 cdp_patch.exe（命令行）
打进同一个文件夹，Python 解释器与全部依赖只打一份，位于 _internal/。

用法：python -m PyInstaller --noconfirm --clean build.spec
"""
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# winrt 是命名空间包，SMTC 走 winrt.windows.media.control，显式收集避免漏打
try:
    hidden_winrt = collect_submodules("winrt")
except Exception:
    hidden_winrt = [
        "winrt",
        "winrt.windows",
        "winrt.windows.foundation",
        "winrt.windows.media",
        "winrt.windows.media.control",
        "winrt.windows.storage",
        "winrt.windows.storage.streams",
    ]
if not hidden_winrt:
    hidden_winrt = ["winrt.windows.media.control"]

# ---------------- 主程序：桌面歌词 ----------------
a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets/materials", "assets/materials")],
    hiddenimports=hidden_winrt,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_main = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe_main = EXE(
    pyz_main,
    a.scripts,
    [],
    exclude_binaries=True,
    name="youyu",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# ---------------- 补丁工具：命令行 ----------------
b = Analysis(
    ["cdp_patch.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_patch = PYZ(b.pure, b.zipped_data, cipher=block_cipher)
exe_patch = EXE(
    pyz_patch,
    b.scripts,
    [],
    exclude_binaries=True,
    name="cdp_patch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# ---------------- 汇总：依赖只打一份 ----------------
coll = COLLECT(
    exe_main,
    exe_patch,
    a.binaries,
    a.zipfiles,
    a.datas,
    b.binaries,
    b.zipfiles,
    b.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="youyu-desktop-lyrics",
)
