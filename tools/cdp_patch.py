# -*- coding: utf-8 -*-
"""网易云 libcef.dll 调试端口补丁工具（针对 3.1.41 / CEF 91）。

原理：修改 libcef.dll 的 2 处字节，使网易云每次启动自动在 127.0.0.1:21631
开放 DevTools 端口。字节特征来自 BrimDeck 项目（NeteasePatch.cs）。

用法：
    python cdp_patch.py status   # 查看补丁状态
    python cdp_patch.py patch    # 打补丁（需先关闭网易云）
    python cdp_patch.py revert   # 还原（需先关闭网易云）

补丁前会自动备份原文件到 libcef.dll.bak。
"""
import os
import sys

LIBCEF = r"E:\CloudMusic\CloudMusic\libcef.dll"
BACKUP = LIBCEF + ".bak"
PORT = 21631

# (原始字节, 补丁字节, 后续上下文) —— 补丁字节把端口常量设为 21631 (0x547F)
SITES = [
    (bytes.fromhex("8B907C010000"), bytes.fromhex("BA7F54000090"), bytes.fromhex("8D8A00FCFFFF81F9FFFB0000")),
    (bytes.fromhex("8B957C010000"), bytes.fromhex("BA7F54000090"), bytes.fromhex("8D8200FCFFFF3DFFFB000077")),
]


def scan(path):
    """返回每个站点的 (偏移, 状态)：original / patched / missing。"""
    with open(path, "rb") as f:
        data = f.read()
    result = []
    for orig, patched, suffix in SITES:
        w_orig = orig + suffix
        w_patch = patched + suffix
        o = data.find(w_orig)
        p = data.find(w_patch)
        co = data.count(w_orig)
        cp = data.count(w_patch)
        if co == 1 and cp == 0:
            result.append((o, "original"))
        elif cp == 1 and co == 0:
            result.append((p, "patched"))
        else:
            result.append((-1, f"missing(orig={co},patch={cp})"))
    return result


def status():
    if not os.path.exists(LIBCEF):
        print("libcef.dll 不存在:", LIBCEF)
        return
    states = scan(LIBCEF)
    print("补丁状态:")
    for i, (off, st) in enumerate(states, 1):
        print(f"  站点{i}: {st}" + (f" @ {hex(off)}" if off >= 0 else ""))
    if all(st == "patched" for _, st in states):
        print("=> 已打补丁")
    elif all(st == "original" for _, st in states):
        print("=> 原始状态（未打补丁）")
    else:
        print("=> 状态异常/不支持")


def check_cloudmusic_running():
    import subprocess
    out = subprocess.run(["tasklist"], capture_output=True).stdout.decode("gbk", "ignore")
    return any("cloudmusic.exe" in l.lower() for l in out.splitlines())


def patch():
    if check_cloudmusic_running():
        print("错误：请先完全关闭网易云再打补丁！")
        return False
    states = scan(LIBCEF)
    if not all(st in ("original", "patched") for _, st in states):
        print("错误：libcef.dll 字节特征不匹配，版本可能不受支持。未做修改。")
        return False
    if all(st == "patched" for _, st in states):
        print("已经是补丁状态，无需操作。")
        return True
    # 备份
    if not os.path.exists(BACKUP):
        import shutil
        shutil.copy2(LIBCEF, BACKUP)
        print("已备份原文件 ->", BACKUP)
    else:
        print("备份已存在，跳过备份")
    # 打补丁
    with open(LIBCEF, "r+b") as f:
        data = f.read()
        for orig, patched, suffix in SITES:
            w_orig = orig + suffix
            off = data.find(w_orig)
            if off >= 0:
                f.seek(off)
                f.write(patched)
                print(f"已写入站点 @ {hex(off)}")
    # 验证
    states2 = scan(LIBCEF)
    ok = all(st == "patched" for _, st in states2)
    print("验证:", "成功" if ok else "失败")
    for i, (off, st) in enumerate(states2, 1):
        print(f"  站点{i}: {st}")
    return ok


def revert():
    if check_cloudmusic_running():
        print("错误：请先完全关闭网易云再还原！")
        return False
    if not os.path.exists(BACKUP):
        print("错误：找不到备份文件", BACKUP)
        return False
    import shutil
    shutil.copy2(BACKUP, LIBCEF)
    print("已从备份还原")
    status()
    return True


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"status": status, "patch": patch, "revert": revert}.get(cmd, status)()
