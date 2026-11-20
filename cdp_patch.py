# -*- coding: utf-8 -*-
"""兼容入口：转发到 tools/cdp_patch.py。

保留旧的 `python cdp_patch.py status|patch|revert` 用法。
"""
from tools.cdp_patch import *  # noqa: F401,F403
from tools.cdp_patch import status, patch, revert
import sys

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"status": status, "patch": patch, "revert": revert}.get(cmd, status)()
