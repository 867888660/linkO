#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动为 McpList.json 补全 tools / prompts 列表
兼容 Windows / macOS / Linux
"""

import json
import subprocess
import os
import sys
import time
import threading
import queue

TIMEOUT = 10          # 秒
JSON_ID = 1

def read_stdout(proc, q):
    """后台线程：持续 readline()，把行放进队列"""
    for line in proc.stdout:
        q.put(line.rstrip("\n"))
    proc.stdout.close()

def call_rpc(server_cfg, method):
    """启动 MCP 服务器，发送 JSON-RPC，返回 (ok, result/err)"""
    cmd = [server_cfg["command"], *server_cfg.get("args", [])]
    env = os.environ.copy()
    env.update(server_cfg.get("env", {}))          # 继承 + 叠加环境变量

    print(f"  ➜ exec: {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',    # 强制使用 UTF-8 解码子进程输出
            errors='ignore',     # 遇到无法解码字节时忽略
            env=env,
        )
    except FileNotFoundError as e:
        return False, {"code": -1, "message": str(e)}

    # 启动后台读取线程
    q = queue.Queue()
    t = threading.Thread(target=read_stdout, args=(proc, q), daemon=True)
    t.start()

    # 发送请求
    req = {"jsonrpc": "2.0", "id": JSON_ID, "method": method}
    msg = json.dumps(req, ensure_ascii=False) + "\n"
    print(f"  ➜ send: {msg.strip()}")
    proc.stdin.write(msg)
    proc.stdin.flush()

    buff = ""
    start = time.time()
    while True:
        try:
            line = q.get(timeout=0.1)
            print(f"    ↩ {line}")
            buff += line
            try:
                resp = json.loads(buff)
                # 拿到就杀子进程，避免挂住
                proc.kill()
                if "result" in resp:
                    return True, resp["result"]
                return False, resp.get("error", {"code": -3, "message": "no result"})
            except json.JSONDecodeError:
                continue                   # 还没拼成完整 JSON
        except queue.Empty:
            if time.time() - start > TIMEOUT:
                print("  ✖ timeout, kill process")
                proc.kill()
                return False, {"code": -2, "message": "timeout"}

def enrich(name, cfg):
    if "tools" in cfg or "prompts" in cfg:
        print("  ✔ already enriched")
        return

    ok, res = call_rpc(cfg, "tools/list")
    if ok:
        cfg["tools"] = res.get("tools", [])
        print(f"  ✔ collected {len(cfg['tools'])} tools")
        return
    if isinstance(res, dict) and res.get("code") == -32601:
        print("  ↪ tools/list unsupported ➜ try prompts/list")
        ok, res2 = call_rpc(cfg, "prompts/list")
        if ok:
            cfg["prompts"] = res2.get("prompts", [])
            print(f"  ✔ collected {len(cfg['prompts'])} prompts")
        else:
            print(f"  ✖ prompts/list failed: {res2}")
    else:
        print(f"  ✖ tools/list failed: {res}")

def main():
    path = os.path.join(os.getcwd(), "McpList.json")
    if not os.path.isfile(path):
        sys.exit(f"File not found: {path}")

    cfg = json.load(open(path, encoding="utf-8"))
    servers = cfg.get("mcpServers", {})
    if not servers:
        sys.exit("mcpServers not found in JSON")

    for name, scfg in servers.items():
        print(f"\n=== {name} ===")
        enrich(name, scfg)

    json.dump(cfg, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\n✔ Updated {path}")

if __name__ == "__main__":
    main()
