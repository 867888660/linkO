#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取 Cline MCP 设置 + 可选 .vscode/mcp.json 并保存为 McpList.json
"""

import os
import shutil
import json
import pathlib
import sys
from datetime import datetime

APPDATA = os.getenv("APPDATA")  # Windows %APPDATA% 路径
if not APPDATA:
    sys.exit("❌ 未检测到 APPDATA 环境变量，脚本仅支持 Windows。")

# 1) 目标文件路径
cline_cfg = pathlib.Path(APPDATA, r"Code\User\globalStorage",
                         r"saoudrizwan.claude-dev\settings",
                         "cline_mcp_settings.json")
workspace_cfg = pathlib.Path(".vscode", "mcp.json")  # 相对当前目录

if not cline_cfg.exists():
    sys.exit(f"❌ 未找到 {cline_cfg}")

# 2) 构建 McpList.json 内容
mcp_list = {"cline_mcp_settings.json": cline_cfg.read_text(encoding="utf-8")}
if workspace_cfg.exists():
    mcp_list[".vscode/mcp.json"] = workspace_cfg.read_text(encoding="utf-8")

# 3) 保存为 McpList.json
output_file = f"McpList_{datetime.now():%Y%m%d_%H%M%S}.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(mcp_list, f, ensure_ascii=False, indent=2)

print(f"✅ 已生成 {output_file}")
