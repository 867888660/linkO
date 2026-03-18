import time

# 定时滚动触发（passivityTrigger，无 Outputs）
OutPutNum = 0
InPutNum = 1

Outputs = []
Inputs = [
    {
        "Num": 1,
        "Kind": "Num",
        "Id": "Input1",
        "Context": None,
        "Isnecessary": True,
        "name": "Second",
        "Link": 0,
        "IsLabel": True,
    }
]

NodeKind = "passivityTrigger"
Lable = [{"Id": "Label1", "Kind": "None"}]
FunctionIntroduction = "组件功能：定时滚动触发（仅 tick，不输出数据）。输入 Second（秒），到点后触发一次 tick=True。"


def _read_seconds(node) -> float:
    """兼容 Num / Context 字段的读取，兜底到 1s。"""
    try:
        inp = (node.get("Inputs") or [None])[0] or {}
        v = inp.get("Num")
        if v is None:
            ctx = inp.get("Context")
            if isinstance(ctx, str) and ctx.strip():
                v = float(ctx.strip())
        if v is None:
            return 1.0
        sec = float(v)
        return 1.0 if sec <= 0 else sec
    except Exception:
        return 1.0


def run_node(node):
    """
    返回形如 {"outputs":[{"tick": True/False, ...}], "debug": "..."} 的结构，
    其中 tick=True 会被 workflow.py 识别并入队（仅触发 ArrayTrigger 链路）。
    """
    sec = _read_seconds(node)
    now = time.time()

    state = node.setdefault("_state", {})
    last = state.get("last_fire_ts")
    if last is None:
        # 第一次：默认立即触发一次，然后进入滚动
        state["last_fire_ts"] = now
        return {
            "outputs": [{"tick": True, "ts": now, "Second": sec}],
            "debug": f"[TIMER] first fire, Second={sec}",
        }

    try:
        last_f = float(last)
    except Exception:
        last_f = 0.0

    due = (now - last_f) >= sec
    if due:
        state["last_fire_ts"] = now
        return {
            "outputs": [{"tick": True, "ts": now, "Second": sec}],
            "debug": f"[TIMER] fire, Second={sec}, dt={now-last_f:.3f}s",
        }

    # 未到点：明确返回 tick=False，workflow.py 将跳过入队
    return {
        "outputs": [{"tick": False, "ts": now, "Second": sec, "remain": max(0.0, sec - (now - last_f))}],
        "debug": f"[TIMER] wait, Second={sec}, remain={max(0.0, sec-(now-last_f)):.3f}s",
    }


