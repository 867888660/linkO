#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 McpList.json 恢复 Cline MCP 设置，并自动启动/安装 MCP Servers
"""

import os
import json
import subprocess
import pathlib
import sys
import signal
import shutil
import re

# 1) 查找 McpList.json 文件
mcp_file = next(pathlib.Path(".").glob("McpList_*.json"), None)
if not mcp_file:
    sys.exit("❌ 当前目录未找到 McpList_*.json")

# 2) 读取 McpList.json 内容
with open(mcp_file, encoding="utf-8") as f:
    mcp_list = json.load(f)

# 3) 恢复 cline_mcp_settings.json
cline_cfg = mcp_list.get("cline_mcp_settings.json")
if cline_cfg:
    appdata = os.getenv("APPDATA")
    if not appdata:
        sys.exit("❌ 未检测到 APPDATA 环境变量，脚本仅支持 Windows。")
    dst_dir = pathlib.Path(appdata, r"Code\User\globalStorage",
                           r"saoudrizwan.claude-dev\settings")
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cline_cfg, dst_dir / "cline_mcp_settings.json")
    print(f"✅ 已恢复 {cline_cfg} 到 {dst_dir}")
else:
    print("⚠️ 未找到 cline_mcp_settings.json 配置")

# 4) 恢复 .vscode/mcp.json（如果存在）
workspace_cfg = mcp_list.get(".vscode/mcp.json")
if workspace_cfg:
    workspace_dir = pathlib.Path(".vscode")
    workspace_dir.mkdir(exist_ok=True)
    shutil.copy2(workspace_cfg, workspace_dir / "mcp.json")
    print(f"✅ 已恢复 {workspace_cfg} 到 {workspace_dir}")
else:
    print("⚠️ 未找到 .vscode/mcp.json 配置")

# 5) 启动 MCP Servers
def expand_env(value: str) -> str:
    """替换 ${env:VAR} 占位符为当前环境变量值"""
    return re.sub(r"\$\{env:([^}]+)}", lambda m: os.getenv(m.group(1), ""), value)

def install_and_run_server(command: str, args: list, env_vars: dict):
    """安装并启动 MCP Server"""
    cmd = [expand_env(command)] + [expand_env(arg) for arg in args]
    env = os.environ.copy()
    for k, v in env_vars.items():
        env[k] = expand_env(v)
    try:
        subprocess.run(cmd, env=env, check=True)
        print(f"✅ 启动成功：{' '.join(cmd)}")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ 启动失败：{e}")

# 读取 MCP Servers 配置并启动
servers = mcp_list.get("mcpServers", {})
if not servers:
    sys.exit("❌ McpList.json 中未找到 mcpServers 配置")

for name, cfg in servers.items():
    print(f"\n▶ 启动 MCP Server: {name}")
    install_and_run_server(cfg["command"], cfg.get("args", []), cfg.get("env", {}))
