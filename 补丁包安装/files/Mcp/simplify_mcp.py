#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 McpList.json → 精简版 Mcp_Server.json
  • 每个 tool 仅保留 name 和必要 arguments
  • 必要 arguments = inputSchema.required ∪ ALWAYS_KEEP_ARGS
"""

import json, os, sys

ALWAYS_KEEP_ARGS = {"days"}          # 需要额外保留的可选字段
SRC_FILE = "McpList.json"            # 原文件
DST_FILE = "Mcp_Server.json"         # 精简后文件

# ---------- 精简逻辑 ----------
def simplify_tool(tool: dict) -> dict:
    simp = {"name": tool.get("name")}
    schema   = tool.get("inputSchema", {})
    props    = schema.get("properties", {})
    required = set(schema.get("required", []))
    keep     = required | ALWAYS_KEEP_ARGS
    if keep:
        simp["arguments"] = {k: props.get(k, {}).get("type", "any")
                             for k in keep if k in props}
    return simp

def simplify_prompt(prompt: dict) -> dict:
    return {"name": prompt.get("name")}

def simplify_server(cfg: dict):
    """无论有无 tools / prompts，都重新覆盖为精简结构"""
    if "tools" in cfg:
        cfg["tools"] = [simplify_tool(t) for t in cfg["tools"]]
    if "prompts" in cfg:
        cfg["prompts"] = [simplify_prompt(p) for p in cfg["prompts"]]

# ---------- 主流程 ----------
def main():
    if not os.path.isfile(SRC_FILE):
        sys.exit(f"❌ 找不到 {SRC_FILE}")

    data = json.load(open(SRC_FILE, encoding="utf-8"))
    servers = data.get("mcpServers", {})
    if not servers:
        sys.exit("❌ mcpServers not found")

    for name, scfg in servers.items():
        print(f"⇢ 精简 {name}")
        simplify_server(scfg)

    json.dump(data, open(DST_FILE, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print(f"✅ 已写入精简结果 → {DST_FILE}")

if __name__ == "__main__":
    main()
