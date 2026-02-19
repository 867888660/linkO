import json
import io
import importlib
import sys
import traceback
import threading
import time
from pathlib import Path
import copy
import re
from collections import deque
from itertools import islice
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import base64
import os
import hashlib
import uuid
from datetime import datetime, timedelta
from contextlib import contextmanager
import importlib.abc
import subprocess


# =========================
# Runtime Tuning (ALL HERE)
# =========================
MAX_WORKERS = int(os.getenv("WF_MAX_WORKERS", "50"))                 # 节点并发上限（原来硬编码 5）
ENQUEUE_BURST = int(os.getenv("WF_ENQUEUE_BURST", "5"))         # 每轮最多入队N个
STATE_FLUSH_INTERVAL = float(os.getenv("WF_STATE_FLUSH_MS", "300")) / 1000.0
ENABLE_DEBUG_PRINT = False       # 一键关闭调试打印
CACHE_MAX_ITEMS = 50000          # 缓存最大条目保护
CACHE_TTL_SECONDS = 6 * 3600     # 缓存TTL（6小时）
CLEANUP_EXPIRED_EVERY_N_RUNS = 200  # 每执行N次触发一次过期清理

# 节点脚本加载策略：
# - 默认(0)：每次执行创建“独立 module 实例”，避免多线程共享 module 全局变量导致串数据
# - 设为 1：复用 module（旧行为，性能更好，但脚本若有全局状态/requests.Session 等会在并发下串数据）
WF_SHARED_NODE_MODULES = os.getenv("WF_SHARED_NODE_MODULES", "0").strip() in ("1", "true", "True", "yes", "YES")

# 节点运行态持久化（默认开启）：
# - 许多 trigger 类节点（如 passivityTrigger_Timer）用 node["_state"] 保存“上次触发时间”
# - 工作流执行过程中会 deepcopy 节点以保证并发安全，导致 node["_state"] 默认无法跨轮保留
# - 开启后：按 (workflow_id, node_id) 在内存中持久化 node["_state"]，使 Timer 的 Second 间隔真正生效
# - 若担心性能/兼容性，可通过环境变量关闭：WF_PERSIST_NODE_STATE=0
WF_PERSIST_NODE_STATE = os.getenv("WF_PERSIST_NODE_STATE", "1").strip() in ("1", "true", "True", "yes", "YES")

# ArrayTrigger 队列项是否携带 graph_data 快照：
# - 旧行为：每次 enqueue 时 deepcopy 整张图，写入 queue item["graph_data"]
#   这在大量数组输出/子任务场景下会显著抬高内存占用，并可能造成 RSS 随运行时间持续增长。
# - 新默认：不携带快照（0），在消费队列时使用当前 data_temp 现场路由 outputData。
WF_QUEUE_STORE_GRAPH_SNAPSHOT = os.getenv("WF_QUEUE_STORE_GRAPH_SNAPSHOT", "0").strip() in ("1", "true", "True", "yes", "YES")

# =========================
# Workflow Print Switch
# =========================
# 说明：只影响本文件(workflow.py)内的 print(...) 调用；不会全局篡改 builtins.print。
# 默认跟随 ENABLE_DEBUG_PRINT；若要强制静音，改为 False。
WORKFLOW_ENABLE_PRINT = bool(ENABLE_DEBUG_PRINT)
try:
    import builtins as _builtins
    _WORKFLOW_ORIG_PRINT = _builtins.print
except Exception:
    _WORKFLOW_ORIG_PRINT = None

def print(*args, **kwargs):  # noqa: A001  (shadow built-in intentionally)
    if WORKFLOW_ENABLE_PRINT and _WORKFLOW_ORIG_PRINT is not None:
        _WORKFLOW_ORIG_PRINT(*args, **kwargs)

# =========================
# Thread-local StdIO Router
# =========================
# 背景：本文件里的 print 开关只影响 workflow.py 自己的 print；
# 但 Nodes 节点脚本/第三方库往往直接写 sys.stdout/sys.stderr 或 logging，
# 在多线程(ThreadPoolExecutor)场景下用 redirect_stdout 这种“全局替换”会互相干扰。
# 这里安装一个“线程本地”的 stdout/stderr 路由器：每个线程可以选择
# - 控制台输出开/关
# - 是否捕获到 buffer（用于返回 debug，而不是刷屏）

CAPTURE_NODE_STDIO_WHEN_SILENCED = True  # 静音时是否把节点脚本的 stdout/stderr 捕获进 debug
MAX_CAPTURED_STDIO_CHARS = 4000         # 防止 debug 爆炸：只保留末尾 N 字符


def _is_thread_stdio_router(obj) -> bool:
    return bool(getattr(obj, "__thread_stdio_router__", False))


class _ThreadLocalStdIO(io.TextIOBase):
    __thread_stdio_router__ = True

    def __init__(self, target, default_console_enabled: bool = True):
        super().__init__()
        self._target = target
        self._default_console_enabled = bool(default_console_enabled)
        self._local = threading.local()
        self._write_lock = threading.Lock()

    def writable(self):
        return True

    @property
    def encoding(self):
        return getattr(self._target, "encoding", "utf-8")

    def isatty(self):
        try:
            return bool(getattr(self._target, "isatty", lambda: False)())
        except Exception:
            return False

    def _get_console_enabled(self) -> bool:
        if hasattr(self._local, "console_enabled"):
            try:
                return bool(self._local.console_enabled)
            except Exception:
                return self._default_console_enabled
        return self._default_console_enabled

    def _get_buffer(self):
        return getattr(self._local, "buffer", None)

    def _set_state(self, console_enabled: bool, buffer):
        self._local.console_enabled = bool(console_enabled)
        self._local.buffer = buffer

    def write(self, s):
        try:
            buf = self._get_buffer()
            if buf is not None:
                try:
                    buf.write(s)
                except Exception:
                    pass

            if self._get_console_enabled():
                try:
                    with self._write_lock:
                        self._target.write(s)
                except Exception:
                    pass
            return len(s)
        except Exception:
            return len(s)

    def flush(self):
        try:
            buf = self._get_buffer()
            if buf is not None:
                try:
                    buf.flush()
                except Exception:
                    pass
            with self._write_lock:
                try:
                    self._target.flush()
                except Exception:
                    pass
        except Exception:
            pass


def _install_thread_stdio_router():
    """幂等安装：把 sys.stdout/sys.stderr 替换成线程路由器。"""
    try:
        if not _is_thread_stdio_router(sys.stdout):
            sys.stdout = _ThreadLocalStdIO(sys.stdout, default_console_enabled=bool(ENABLE_DEBUG_PRINT))
    except Exception:
        pass
    try:
        if not _is_thread_stdio_router(sys.stderr):
            sys.stderr = _ThreadLocalStdIO(sys.stderr, default_console_enabled=bool(ENABLE_DEBUG_PRINT))
    except Exception:
        pass


@contextmanager
def _thread_stdio_scope(console_enabled: bool = True, capture: bool = False):
    """
    仅影响当前线程的 stdout/stderr 行为：
    - console_enabled=False：不往控制台吐
    - capture=True：捕获到 buffer（返回时读取 buffer.getvalue()）
    """
    _install_thread_stdio_router()

    buf = io.StringIO() if capture else None
    out_router = sys.stdout if _is_thread_stdio_router(sys.stdout) else None
    err_router = sys.stderr if _is_thread_stdio_router(sys.stderr) else None
    prev = None
    try:
        prev = (
            (getattr(out_router, "_get_console_enabled", lambda: True)(),
             getattr(out_router, "_get_buffer", lambda: None)()) if out_router else (True, None),
            (getattr(err_router, "_get_console_enabled", lambda: True)(),
             getattr(err_router, "_get_buffer", lambda: None)()) if err_router else (True, None),
        )
        if out_router:
            out_router._set_state(console_enabled=console_enabled, buffer=buf)
        if err_router:
            err_router._set_state(console_enabled=console_enabled, buffer=buf)
        yield buf
    finally:
        try:
            if prev and out_router:
                out_router._set_state(console_enabled=prev[0][0], buffer=prev[0][1])
            if prev and err_router:
                err_router._set_state(console_enabled=prev[1][0], buffer=prev[1][1])
        except Exception:
            pass


def _merge_debug_with_stdio(debug_text: str, stdio_text: str) -> str:
    try:
        dt = debug_text or ""
        st = (stdio_text or "").strip()
        if not st:
            return dt
        if MAX_CAPTURED_STDIO_CHARS and len(st) > MAX_CAPTURED_STDIO_CHARS:
            st = st[-MAX_CAPTURED_STDIO_CHARS:]
        block = f"[STDIO]\n{st}"
        return f"{dt}\n\n{block}".strip() if dt else block
    except Exception:
        return debug_text or ""


# 进程启动即安装（线程本地，不会改变业务逻辑，只是减少刷屏/便于捕获）
_install_thread_stdio_router()

# 工作流状态常量
class WorkflowStatus:
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    STOPPED = "stopped"

def retrieve_content_within_braces(text):
    """提取文本中 {{variable}} 格式的变量（支持中英文与可选空格）"""
    if not isinstance(text, str):
        return []
    return [m.strip() for m in re.findall(r'{{\s*(.*?)\s*}}', text, flags=re.S)]

# =========================
# History JSONL (append-only)
# =========================
# 目标：
# - 写入：改为 append JSONL（不再“读整文件 + 重写整文件”）
# - 读取：支持 JSONL + 旧 JSON 双兼容
# - 对外返回结构：保持现有的 “list[list[dict]]（按会话分组）” 形态不变（前端无感）

def _history_jsonl_path(base_dir: Path, day: datetime = None) -> Path:
    d = (day or datetime.utcnow()).strftime("%Y%m%d")
    p = Path(base_dir) / "workflow_history"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"history-{d}.jsonl"


def _iter_jsonl_records(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                yield json.loads(s)
            except Exception:
                # 容错：坏行跳过（常见于异常中断导致最后半行）
                continue


def _event_dedupe_key(x: dict) -> str:
    # 有 event_id 就用 event_id；没有就用组合键
    try:
        eid = x.get("event_id") if isinstance(x, dict) else None
    except Exception:
        eid = None
    if eid:
        return f"eid:{eid}"
    try:
        return "k:{wf}|{node}|{etype}|{ts}".format(
            wf=(x.get("workflow_id", "") if isinstance(x, dict) else ""),
            node=(x.get("node_id", "") if isinstance(x, dict) else ""),
            etype=(x.get("event_type", "") if isinstance(x, dict) else ""),
            ts=(x.get("ts", "") if isinstance(x, dict) else ""),
        )
    except Exception:
        return "k:invalid"


class WorkflowEngine:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or Path(".")
        # 全局状态锁（工作流字典等）
        self.lock = threading.Lock()
        # Runtime tuning (from unified config above)
        self.max_workers = MAX_WORKERS
        self.enable_debug_print = ENABLE_DEBUG_PRINT
        self.cache_max_items = CACHE_MAX_ITEMS
        self.cache_ttl_seconds = CACHE_TTL_SECONDS
        self.cleanup_expired_every_n_runs = CLEANUP_EXPIRED_EVERY_N_RUNS
        self._run_counter = 0
        self._cache_time = {}  # 记录缓存键最近更新时间戳: {(cache_name, key): ts}
        # 历史文件写入锁（避免并发读改写导致记录丢失/文件损坏）
        self._history_lock = threading.Lock()
        # 性能开关：默认关闭大量 print（需要排查时再打开）
        self.DEBUG_PRINT = False
        # History：缓冲 + 批量落盘（最小改动：仍然写同一个 json 文件，只减少 IO 次数）
        self.HISTORY_BUFFER_SIZE = 20
        self.HISTORY_FLUSH_INTERVAL = 0.5  # seconds
        self._history_buffer = {}          # { workflow_id: { "file_path": str, "pending": [...], "last_flush": ts } }
        # History 限额：防止单个文件/会话无限增大
        self.HISTORY_MAX_SESSIONS_PER_FILE = 30
        self.HISTORY_MAX_ITEMS_PER_SESSION = 500
        # 事件日志节流（避免高频 with self.lock 抢锁）
        self._event_throttle_last_ts = {}  # { workflow_id: last_ts }
        self.workflows = {}  # 存储所有工作流的状态
        self.stop_events = {}  # 用于停止工作流的事件
        self._cleanup_timers = {}  # 延迟清理定时器
        self.child_workflows = {}  # 父 -> 子工作流集合
        self.parent_map = {}       # 子 -> 父映射
        
        # 初始化目录常量（与app.py保持一致）
        self.BASE_DIR = self.base_dir
        self.TEMP_DIR = self.BASE_DIR / "TempFiles"
        self.NOTEBOOK_DIR = self.BASE_DIR / "NoteBook"
        self.MEMORY_DIR = self.BASE_DIR / "Memory"
        self.WORKFLOW_DIR = self.BASE_DIR / "WorkFlow"
        self.NODES_DIR = self.BASE_DIR / "Nodes"
        
        # 确保目录存在
        for folder in (self.TEMP_DIR, self.NOTEBOOK_DIR, self.MEMORY_DIR, self.WORKFLOW_DIR, self.NODES_DIR):
            folder.mkdir(parents=True, exist_ok=True)

        # 运行级别的跟踪状态（仅在 passivity 触发后启用）
        self._trace_enabled = False
        self._trace_nodes = []
        self._trace_session_id = 0
        self._stdout_backup = None
        
        # 最近指纹去重表：记录每个节点最近一次入环的指纹
        self._last_ring_fp = {}  # { (workflow_id, node_id): last_fp }
        # 性能优化：ArrayTrigger 队列索引，快速定位最后一个相同 nodeId 的项
        # { workflow_id: { node_id: last_index } }
        self._array_queue_last_index = {}

        # ---- Module cache (min patch) ----
        self._module_cache = {}         # { abs_path: (mtime, module) }
        self._module_cache_lock = threading.Lock()

        self._event_throttle_lock = threading.Lock()

        # ---- System monitor cache (for UI metrics) ----
        # Frontend polls /workflow/status frequently (300ms in running mode).
        # System-wide queries like net_connections/netstat are expensive, so we cache results.
        self._sysmon_lock = threading.Lock()
        self._sysmon_cache_ts = 0.0
        self._sysmon_cache_interval_s = float(os.getenv("WF_SYSMON_INTERVAL_S", "2.0") or 2.0)
        self._sysmon_cache = {"ConnNow": None, "TWNow": None, "PortUse": None}
        self._dyn_port_range_cache = None  # (start_port:int, num_ports:int)

        # ---- Persisted per-node state (for triggers like Timer) ----
        # Many node scripts store runtime state in node["_state"] (e.g. last_fire_ts).
        # Because workflow runtime frequently deepcopy nodes for thread-safety, that state
        # would otherwise be lost between polls. We persist it here by (workflow_id, node_id).
        self._node_state_store = {}   # { (workflow_id, node_id): dict_state }
        self._node_state_lock = threading.Lock()

        # 兼容旧的 DEBUG_PRINT：统一用 enable_debug_print 控制（不删旧逻辑）
        try:
            self.DEBUG_PRINT = bool(self.enable_debug_print)
        except Exception:
            pass

    # —— 输出过滤器：仅放行以 [TRACE: 开头的行 ——
    class _TracePrefixFilter(io.TextIOBase):
        def __init__(self, target, prefixes):
            self._target = target
            self._prefixes = tuple(prefixes or [])
            self._buf = ''
        def writable(self):
            return True
        def write(self, s):
            try:
                self._buf += s
                out = []
                while '\n' in self._buf:
                    line, self._buf = self._buf.split('\n', 1)
                    if any(line.startswith(p) for p in self._prefixes):
                        out.append(line + '\n')
                if out:
                    self._target.write(''.join(out))
                return len(s)
            except Exception:
                return len(s)
        def flush(self):
            try:
                if self._buf:
                    if any(self._buf.startswith(p) for p in self._prefixes):
                        self._target.write(self._buf)
                    self._buf = ''
                self._target.flush()
            except Exception:
                pass

    def _install_trace_filter(self):
        try:
            if self._stdout_backup is None:
                self._stdout_backup = sys.stdout
                sys.stdout = self._TracePrefixFilter(self._stdout_backup, ['[TRACE:'])
        except Exception:
            pass

    def _restore_stdout(self):
        try:
            if self._stdout_backup is not None:
                sys.stdout = self._stdout_backup
                self._stdout_backup = None
        except Exception:
            pass

    # -------------------------
    # Debug / cache bookkeeping
    # -------------------------
    def dbg(self, *args, **kwargs):
        if getattr(self, "enable_debug_print", False):
            print(*args, **kwargs)

    # -------------------------
    # Persisted node state
    # -------------------------
    def _get_node_state(self, workflow_id: str, node_id: str):
        try:
            wid = str(workflow_id or "")
            nid = str(node_id or "")
            if not wid or not nid:
                return None
            with self._node_state_lock:
                st = self._node_state_store.get((wid, nid))
            return copy.deepcopy(st) if isinstance(st, dict) else None
        except Exception:
            return None

    def _set_node_state(self, workflow_id: str, node_id: str, state):
        try:
            wid = str(workflow_id or "")
            nid = str(node_id or "")
            if not wid or not nid:
                return
            if not isinstance(state, dict):
                with self._node_state_lock:
                    self._node_state_store.pop((wid, nid), None)
                return
            with self._node_state_lock:
                # store a deepcopy to avoid accidental shared mutation across threads
                self._node_state_store[(wid, nid)] = copy.deepcopy(state)
        except Exception:
            pass

    def _clear_workflow_node_states(self, workflow_id: str):
        """Clear persisted node states for a workflow (called on restart/cleanup)."""
        try:
            wid = str(workflow_id or "")
            if not wid:
                return
            with self._node_state_lock:
                stale = [k for k in list(self._node_state_store.keys()) if k and k[0] == wid]
                for k in stale:
                    self._node_state_store.pop(k, None)
        except Exception:
            pass

    def _mark_cache_touch(self, cache_name, key, now_ts=None):
        if now_ts is None:
            now_ts = time.time()
        self._cache_time[(cache_name, key)] = now_ts

    def _prune_cache_if_needed(self):
        now = time.time()

        # 周期触发（避免每次都扫）
        self._run_counter += 1
        if self._run_counter % self.cleanup_expired_every_n_runs != 0:
            return

        # A) TTL清理
        expired = []
        for (cache_name, key), ts in list(self._cache_time.items()):
            try:
                if now - ts > self.cache_ttl_seconds:
                    expired.append((cache_name, key))
            except Exception:
                continue
        for cache_name, key in expired:
            self._cache_time.pop((cache_name, key), None)
            cache_obj = getattr(self, cache_name, None)
            if isinstance(cache_obj, dict):
                cache_obj.pop(key, None)

        # B) 最大条目保护（按时间从旧到新裁剪）
        try:
            if len(self._cache_time) > self.cache_max_items:
                over = len(self._cache_time) - self.cache_max_items
                oldest = sorted(self._cache_time.items(), key=lambda x: x[1])[:over]
                for (cache_name, key), _ in oldest:
                    self._cache_time.pop((cache_name, key), None)
                    cache_obj = getattr(self, cache_name, None)
                    if isinstance(cache_obj, dict):
                        cache_obj.pop(key, None)
        except Exception:
            pass

    def _runtime_cleanup(self, workflow_id):
        # 1) 核心运行态
        self.workflows.pop(workflow_id, None)
        self.stop_events.pop(workflow_id, None)
        self.child_workflows.pop(workflow_id, None)
        self.parent_map.pop(workflow_id, None)

        # 2) 缓存/节流
        self._history_buffer.pop(workflow_id, None)
        self._event_throttle_last_ts.pop(workflow_id, None)
        self._array_queue_last_index.pop(workflow_id, None)
        # 2.1) per-node persisted state
        try:
            self._clear_workflow_node_states(workflow_id)
        except Exception:
            pass

        # 3) 前缀类缓存（如 wid:xxx）
        try:
            wid0 = str(workflow_id or "")
            stale = []
            for k in list(self._last_ring_fp.keys()):
                try:
                    # canonical: (workflow_id, node_id)
                    if isinstance(k, tuple) and len(k) >= 1 and str(k[0]) == wid0:
                        stale.append(k)
                        continue
                    # legacy: "wid:xxx" / other string-like keys
                    if isinstance(k, str) and k.startswith(f"{wid0}:"):
                        stale.append(k)
                        continue
                except Exception:
                    continue
            for k in stale:
                self._last_ring_fp.pop(k, None)
        except Exception:
            pass

        # 4) 定时器
        t = self._cleanup_timers.pop(workflow_id, None)
        if t:
            try:
                t.cancel()
            except Exception:
                pass

        # 5) cache_time 侧表清理
        try:
            wid0 = str(workflow_id or "")
            stale_time_keys = []
            for ck in list(self._cache_time.keys()):
                try:
                    # ck is (cache_name, key)
                    if not isinstance(ck, tuple) or len(ck) != 2:
                        continue
                    _key = ck[1]
                    # common: key == workflow_id (e.g. _event_throttle_last_ts)
                    if str(_key) == wid0:
                        stale_time_keys.append(ck)
                        continue
                    # tuple keys like (workflow_id, node_id) for _last_ring_fp
                    if isinstance(_key, tuple) and len(_key) >= 1 and str(_key[0]) == wid0:
                        stale_time_keys.append(ck)
                        continue
                    # legacy prefix style
                    if isinstance(_key, str) and _key.startswith(f"{wid0}:"):
                        stale_time_keys.append(ck)
                        continue
                except Exception:
                    continue
            for ck in stale_time_keys:
                self._cache_time.pop(ck, None)
        except Exception:
            pass

    def _trace_start(self, workflow_id, pass_node, outputs_len):
        try:
            self._trace_enabled = True
            self._trace_nodes = []
            self._trace_session_id += 1
            print(f"[TRACE:START] wf={workflow_id} sid={self._trace_session_id} passivity={pass_node.get('label', pass_node.get('id'))} outputs={outputs_len}")
        except Exception:
            pass

    def _trace_node(self, node):
        if not self._trace_enabled:
            return
        try:
            # 摘要化输出（仅取每个端口关键值）
            outs = []
            for idx, o in enumerate(node.get('Outputs', []) or []):
                val = None
                if o is None:
                    val = None
                elif 'Context' in o and o.get('Context') not in (None, ''):
                    v = str(o.get('Context'))
                    val = (v[:60] + '...') if len(v) > 60 else v
                elif 'Num' in o and o.get('Num') is not None:
                    val = o.get('Num')
                elif 'Boolean' in o and o.get('Boolean') is not None:
                    val = o.get('Boolean')
                outs.append(val)
            line = f"[TRACE:NODE] {node.get('label', node.get('id'))} kind={node.get('NodeKind')} status={'ERR' if node.get('IsError') else ('FIN' if node.get('isFinish') else ('RUN' if node.get('IsRunning') else 'IDLE'))} outs={outs}"
            print(line)
            self._trace_nodes.append(node.get('id'))
        except Exception:
            pass

    def _trace_end(self, workflow_id, status):
        try:
            if self._trace_enabled:
                print(f"[TRACE:END] wf={workflow_id} sid={self._trace_session_id} status={status} nodes={len(self._trace_nodes)}")
            self._trace_enabled = False
            self._trace_nodes = []
        except Exception:
            pass

    def _flush_history_items_to_file(self, file_path: Path, items: list):
        """
        ✅ 改为 JSONL append（关键提速点）：
        - 不再读整文件/重写整文件
        - 保留函数名与签名，避免大范围改动调用点
        """
        if not items:
            return
        # file_path 参数保留兼容旧调用点（旧模式写 History/<project>/<workflow_id>.json）
        try:
            p = _history_jsonl_path(Path(self.BASE_DIR))
        except Exception:
            p = _history_jsonl_path(Path(self.base_dir))
        # 串行化 append（避免多线程写入行交错）
        with self._history_lock:
            try:
                with p.open("a", encoding="utf-8") as f:
                    for it in items:
                        if not isinstance(it, dict):
                            continue
                        f.write(json.dumps(it, ensure_ascii=False) + "\n")
                    f.flush()
            except Exception:
                pass

    def _find_legacy_history_file_by_workflow(self, workflow_id: str):
        """兼容旧版：查找 History/**/<workflow_id>.json（可能按项目分目录）。"""
        try:
            wid = str(workflow_id or "")
            if not wid:
                return None
            history_root = Path(self.BASE_DIR) / "History"
            pat = f"{wid}.json"
            try:
                matches = list(history_root.rglob(pat))
                if matches:
                    return matches[0]
            except Exception:
                pass
            legacy = history_root / pat
            return legacy if legacy.exists() else None
        except Exception:
            return None

    def _read_history_compatible(self, workflow_id: str, days: int = 7):
        """
        读取：JSONL + 旧 JSON 双兼容；对外仍返回 list[list[dict]]（会话分组），前端无感。
        """
        wid = str(workflow_id or "")
        if not wid:
            return []

        all_items = []
        seen = set()

        # A) 先读 JSONL（近 N 天）
        try:
            n_days = max(1, int(days or 7))
        except Exception:
            n_days = 7
        now = datetime.utcnow()
        for i in range(n_days):
            dd = now - timedelta(days=i)
            try:
                p = _history_jsonl_path(Path(self.BASE_DIR), dd)
            except Exception:
                p = _history_jsonl_path(Path(self.base_dir), dd)
            for it in _iter_jsonl_records(p):
                if not isinstance(it, dict):
                    continue
                if str(it.get("workflow_id", "")) != wid:
                    continue
                k = _event_dedupe_key(it)
                if k in seen:
                    continue
                seen.add(k)
                all_items.append(it)

        # B) 回退读旧 JSON（兼容老数据：History/**/<workflow_id>.json）
        old_p = self._find_legacy_history_file_by_workflow(wid)
        if old_p and old_p.exists():
            try:
                with old_p.open("r", encoding="utf-8") as f:
                    old = json.load(f)
                old_items = []
                if isinstance(old, list):
                    # 旧结构通常是 list[list[dict]]
                    if old and all(isinstance(x, list) for x in old):
                        for sess in old:
                            for it in (sess or []):
                                if isinstance(it, dict):
                                    old_items.append(it)
                    else:
                        for it in old:
                            if isinstance(it, dict):
                                old_items.append(it)
                elif isinstance(old, dict):
                    cand = old.get("items", []) or old.get("history", []) or []
                    if isinstance(cand, list):
                        for it in cand:
                            if isinstance(it, dict):
                                old_items.append(it)
                # 给旧条目补齐必要字段（用于排序/去重/过滤）
                try:
                    base_ts = float(old_p.stat().st_mtime)
                except Exception:
                    base_ts = time.time()
                for idx, it in enumerate(old_items):
                    if not isinstance(it, dict):
                        continue
                    it.setdefault("workflow_id", wid)
                    it.setdefault("event_type", "legacy")
                    it.setdefault("node_id", it.get("id") or it.get("nodeId") or "")
                    if it.get("ts") is None:
                        it["ts"] = base_ts + (idx * 1e-6)
                    k = _event_dedupe_key(it)
                    if k in seen:
                        continue
                    seen.add(k)
                    all_items.append(it)
            except Exception:
                pass

        # B2) 回退读旧 JSON（兼容另一种旧路径：workflow_history/history.json）
        try:
            old2_p = Path(self.BASE_DIR) / "workflow_history" / "history.json"
        except Exception:
            old2_p = Path(self.base_dir) / "workflow_history" / "history.json"
        if old2_p.exists():
            try:
                with old2_p.open("r", encoding="utf-8") as f:
                    old2 = json.load(f)
                if isinstance(old2, list):
                    old2_items = old2
                elif isinstance(old2, dict):
                    old2_items = old2.get("items", []) or old2.get("history", []) or []
                else:
                    old2_items = []
                if not isinstance(old2_items, list):
                    old2_items = []
                try:
                    base_ts2 = float(old2_p.stat().st_mtime)
                except Exception:
                    base_ts2 = time.time()
                for idx, it in enumerate(old2_items):
                    if not isinstance(it, dict):
                        continue
                    # 若该旧 JSON 是全局混合文件，则优先按 workflow_id 过滤
                    if it.get("workflow_id") is not None and str(it.get("workflow_id")) != wid:
                        continue
                    it.setdefault("workflow_id", wid)
                    it.setdefault("event_type", "legacy")
                    it.setdefault("node_id", it.get("node_id") or it.get("id") or it.get("nodeId") or "")
                    if it.get("ts") is None:
                        it["ts"] = base_ts2 + (idx * 1e-6)
                    k = _event_dedupe_key(it)
                    if k in seen:
                        continue
                    seen.add(k)
                    all_items.append(it)
            except Exception:
                pass

        # C) 排序（ts 缺失时放后面）
        def _ts_key(x: dict):
            try:
                v = x.get("ts") or x.get("time") or ""
                if v in (None, ""):
                    return (1, 0.0)
                if isinstance(v, (int, float)):
                    return (0, float(v))
                # 字符串：尽量解析为 float，否则退化为字符串排序
                try:
                    return (0, float(str(v)))
                except Exception:
                    return (0, str(v))
            except Exception:
                return (1, 0.0)

        all_items.sort(key=_ts_key)

        # D) 组装为“会话列表”（保持旧返回结构）
        def _is_start_record(it: dict) -> bool:
            try:
                et = str(it.get("event_type", "")).lower()
                if et in ("start", "session_start"):
                    return True
            except Exception:
                pass
            # 兼容前端/旧 Start 形态
            try:
                name_s = str(it.get("name", "")).strip().lower()
                msg_s = str(it.get("message", "")).strip().lower()
                if name_s in ("new started", "start", "new conversation started"):
                    return True
                if msg_s.startswith("new conversation"):
                    return True
            except Exception:
                pass
            return False

        sessions = []
        cur = []
        for it in all_items:
            if not isinstance(it, dict):
                continue
            if _is_start_record(it):
                if cur:
                    sessions.append(cur)
                cur = [it]
            else:
                if not cur:
                    cur = []
                cur.append(it)
        if cur:
            sessions.append(cur)
        return sessions

    def _is_history_enabled(self, workflow_id: str) -> bool:
        """判断当前工作流是否允许写入 History（默认允许）。"""
        try:
            wf = self.workflows.get(workflow_id) or {}
            gd = wf.get("graph_data") if isinstance(wf, dict) else None
            if isinstance(gd, dict) and ("RecordHistory" in gd):
                return bool(gd.get("RecordHistory"))
        except Exception:
            pass
        return True

    def _flush_history_buffer_for_workflow(self, workflow_id: str):
        """把某个 workflow 的 History 缓冲落盘（用于结束/清理前兜底 flush）。"""
        try:
            items = None
            fp_str = None
            now_ts = time.time()
            # 先在锁内“拿走待写 items”，缩短共享区停留时间
            with self._history_lock:
                entry = self._history_buffer.get(workflow_id)
                if not entry:
                    return
                pending = entry.get("pending") or []
                fp_str = entry.get("file_path")
                if not pending or not fp_str:
                    return
                items = pending[:]
                entry["pending"] = []
                entry["last_flush"] = now_ts
            # I/O 在锁外执行
            if items and fp_str:
                self._flush_history_items_to_file(Path(fp_str), items)
        except Exception:
            pass

    def _log_event(self, workflow_id, message: str):
        """记录可供前端查看的事件日志（最多100条）"""
        try:
            # 最小节流：100ms 内的“非关键日志”直接跳过，避免 self.lock 变成热点
            try:
                now_ts = time.time()
                with self._event_throttle_lock:
                    last_ts = self._event_throttle_last_ts.get(workflow_id, 0.0)
                    is_critical = any(k in message for k in ("❌", "⚠️", "✅", "🆕", "[TRACE", "[RING", "[CHILD", "[HISTORY"))
                    if (not is_critical) and (now_ts - last_ts) < 0.1:
                        return
                    self._event_throttle_last_ts[workflow_id] = now_ts
                # cache bookkeeping (TTL + max-items)
                try:
                    self._mark_cache_touch("_event_throttle_last_ts", workflow_id, now_ts)
                    self._prune_cache_if_needed()
                except Exception:
                    pass
            except Exception:
                pass
            with self.lock:
                wf = self.workflows.get(workflow_id)
                if not wf:
                    return
                events = wf.setdefault("events", [])
                ts = time.strftime("%H:%M:%S")
                events.append(f"{ts} {message}")
                if len(events) > 100:
                    del events[:-100]
                wf["last_update"] = time.time()
        except Exception:
            pass

    # -------------------------
    # Memory guards / lightweight clones
    # -------------------------
    def _clone_graph_for_child(self, graph_data: dict):
        """
        Lightweight graph clone for ArrayTrigger child workflows.
        Goal: avoid deep-copying large runtime fields from the parent graph (Outputs Context, node debug, messages, etc.).
        We keep node/edge structure and node INPUTS (config) intact, but clear node OUTPUTS/runtime flags.
        """
        try:
            if not isinstance(graph_data, dict):
                return copy.deepcopy(graph_data)

            out = {}
            # Copy top-level keys except nodes/edges (handled below)
            for k, v in graph_data.items():
                if k in ("nodes", "edges"):
                    continue
                try:
                    out[k] = copy.deepcopy(v)
                except Exception:
                    out[k] = v

            nodes = graph_data.get("nodes", []) or []
            edges = graph_data.get("edges", []) or []

            new_nodes = []
            drop_node_keys = {
                "messages", "debug", "ErrorContext", "inputStatus",
                "IsBlock", "IsRunning", "IsError", "isFinish", "firstRun",
                "TriggerLink", "_state",
            }
            for n in nodes:
                if not isinstance(n, dict):
                    continue
                nn = {}
                for k, v in n.items():
                    if k in drop_node_keys:
                        continue
                    if k == "Outputs":
                        continue
                    # Inputs carry config; keep as-is but deep-copy for isolation
                    if k == "Inputs":
                        try:
                            nn["Inputs"] = copy.deepcopy(v)
                        except Exception:
                            nn["Inputs"] = v
                        continue
                    try:
                        nn[k] = copy.deepcopy(v)
                    except Exception:
                        nn[k] = v

                # Outputs: keep port definitions, clear runtime values to avoid copying huge Context/debug.
                outs = n.get("Outputs", []) or []
                new_outs = []
                for o in outs:
                    if not isinstance(o, dict):
                        continue
                    oo = {}
                    for ok, ov in o.items():
                        if ok in ("Context", "Num", "Boolean", "prompt_tokens", "completion_tokens", "total_tokens"):
                            continue
                        try:
                            oo[ok] = copy.deepcopy(ov)
                        except Exception:
                            oo[ok] = ov
                    kind = str(o.get("Kind", "") or "")
                    if "String" in kind:
                        oo["Context"] = ""
                    elif kind == "Num":
                        oo["Num"] = None
                    elif kind == "Boolean":
                        oo["Boolean"] = False
                    new_outs.append(oo)
                nn["Outputs"] = new_outs
                new_nodes.append(nn)

            new_edges = []
            for e in edges:
                if isinstance(e, dict):
                    try:
                        new_edges.append(copy.deepcopy(e))
                    except Exception:
                        new_edges.append(dict(e))
            out["nodes"] = new_nodes
            out["edges"] = new_edges
            return out
        except Exception:
            # fallback: correctness over performance
            try:
                return copy.deepcopy(graph_data)
            except Exception:
                return graph_data

    def _cap_node_debug(self, v):
        """Limit node-level debug payload stored in graph_data to avoid unbounded RSS growth.
        This does NOT affect dataflow outputs; it's only for UI/debug display.
        """
        try:
            max_chars = int(os.getenv("WF_NODE_DEBUG_MAX_CHARS", "20000") or 20000)
        except Exception:
            max_chars = 20000
        try:
            max_items = int(os.getenv("WF_NODE_DEBUG_MAX_ITEMS", "200") or 200)
        except Exception:
            max_items = 200

        try:
            if v is None:
                return ""
            if isinstance(v, str):
                if max_chars and len(v) > max_chars:
                    return v[:max_chars] + f"\n...[debug truncated {len(v) - max_chars} chars]"
                return v
            if isinstance(v, (list, tuple)):
                items = list(v)
                if max_items and len(items) > max_items:
                    items = items[:max_items] + [f"...[debug truncated {len(v) - max_items} items]"]
                out = []
                for it in items:
                    s = str(it)
                    if max_chars and len(s) > max_chars:
                        s = s[:max_chars] + f"...[truncated {len(str(it)) - max_chars} chars]"
                    out.append(s)
                # Keep as list to preserve frontend expectations (some nodes already return list)
                return out
            # fallback: stringify
            s = str(v)
            if max_chars and len(s) > max_chars:
                return s[:max_chars] + f"\n...[debug truncated {len(s) - max_chars} chars]"
            return s
        except Exception:
            return v

    def _cap_output_context_in_place(self, outputs):
        """
        Cap stored output Context in node["Outputs"] to prevent graph_data from retaining huge strings.
        IMPORTANT: This only caps what we store for UI/state; dataflow propagation uses `result["output"]`.
        """
        try:
            max_chars = int(os.getenv("WF_OUTPUT_CONTEXT_MAX_CHARS", "20000") or 20000)
        except Exception:
            max_chars = 20000
        if not max_chars:
            return
        try:
            if not isinstance(outputs, list):
                return
            for o in outputs:
                if not isinstance(o, dict):
                    continue
                ctx = o.get("Context")
                if isinstance(ctx, str) and len(ctx) > max_chars:
                    o["Context"] = ctx[:max_chars] + f"\n...[output truncated {len(ctx) - max_chars} chars]"
        except Exception:
            pass

    def _maybe_clear_graph_after_done(self, workflow: dict):
        """
        If workflow is DONE (completed/error/stopped) and past TTL, clear graph_data to free memory.
        Keep an empty graph dict to avoid frontend crashes expecting graph_data.nodes.
        """
        try:
            if not isinstance(workflow, dict):
                return
            st = workflow.get("status")
            if st not in (WorkflowStatus.COMPLETED, WorkflowStatus.ERROR, WorkflowStatus.STOPPED):
                return
            ttl_s = float(os.getenv("WF_DONE_GRAPH_TTL_S", "30") or 30)
            if ttl_s < 0:
                return
            done_ts = workflow.get("done_ts")
            if done_ts is None:
                # fallback: use last_update as approximation
                done_ts = workflow.get("last_update")
            if done_ts is None:
                return
            if (time.time() - float(done_ts)) < ttl_s:
                return
            gd = workflow.get("graph_data")
            # already cleared?
            if isinstance(gd, dict) and gd.get("_cleared") is True:
                return
            # clear to minimal stub
            workflow["graph_data"] = {"nodes": [], "edges": [], "_cleared": True}
        except Exception:
            return

    def _safe_project_dir(self, name: str) -> str:
        """将项目名转为安全的目录名"""
        try:
            safe = re.sub(r"[^\w\.\-]+", "_", str(name)).strip("._")
            return safe or "workflow"
        except Exception:
            return "workflow"
    
    def _add_history(self, workflow_id, node_data):
        """添加历史记录（与前端addHistory逻辑对齐）"""
        try:
            # 用户可选择关闭历史记录：关闭后不再写入（减少磁盘/IO压力）
            if not self._is_history_enabled(str(workflow_id)):
                return
            debug = getattr(self, "DEBUG_PRINT", False)
            # 防止单条 Context/prompt 超大撑爆文件：字符串截断
            def _trunc(s, max_chars: int = 20000):
                try:
                    if isinstance(s, str) and max_chars and len(s) > max_chars:
                        return s[:max_chars] + f"\n...[truncated {len(s) - max_chars} chars]"
                except Exception:
                    pass
                return s
            # 打印调试信息（可开关）
            if debug:
                print(f"📝 [HISTORY] 添加历史记录 - 工作流: {workflow_id}")
                name = node_data if isinstance(node_data, str) else node_data.get('label', node_data.get('id', 'Unknown'))
                print(f"📝 [HISTORY] 节点数据: {name}")
            
            if node_data == 'Start':
                # 开始新对话
                filtered_data = {'message': 'New conversation started'}
                if debug:
                    print(f"📝 [HISTORY] 开始新对话")
            elif not isinstance(node_data, dict):
                # 兼容字符串或其它非常规类型
                filtered_data = {'message': str(node_data)}
            else:
                # 过滤节点数据，只保留必要字段（与前端逻辑一致）
                filtered_data = {
                    'NodeKind': node_data.get('NodeKind'),
                    'label': node_data.get('label'),
                    'Outputs': [],
                    'Inputs': []
                }
                
                # 处理Outputs
                for item in node_data.get('Outputs', []):
                    selected_field = {}
                    if 'String' in item.get('Kind', ''):
                        selected_field = {'Context': _trunc(item.get('Context'))}
                    elif 'Boolean' in item.get('Kind', ''):
                        selected_field = {'Boolean': item.get('Boolean')}
                    elif 'Num' in item.get('Kind', ''):
                        selected_field = {'Num': item.get('Num')}
                    
                    filtered_data['Outputs'].append({
                        'name': item.get('name'),
                        'Kind': item.get('Kind'),
                        **selected_field
                    })
                
                # 处理Inputs
                for item in node_data.get('Inputs', []):
                    selected_field = {}
                    if 'String' in item.get('Kind', ''):
                        selected_field = {'Context': _trunc(item.get('Context'))}
                    elif 'Boolean' in item.get('Kind', ''):
                        selected_field = {'Boolean': item.get('Boolean')}
                    elif 'Num' in item.get('Kind', ''):
                        selected_field = {'Num': item.get('Num')}
                    
                    filtered_data['Inputs'].append({
                        'name': item.get('name'),
                        'Kind': item.get('Kind'),
                        **selected_field
                    })
                
                if debug:
                    print(f"📝 [HISTORY] 过滤后的数据: {json.dumps(filtered_data, ensure_ascii=False, indent=2)}")
            
            # ---- JSONL 兼容字段（不影响前端；仅增加去重/排序/过滤所需元数据）----
            try:
                filtered_data.setdefault("ts", time.time())
                filtered_data.setdefault("workflow_id", str(workflow_id))
                if node_data == "Start":
                    _etype = "start"
                    _nid = ""
                elif isinstance(node_data, dict):
                    _etype = "node"
                    _nid = node_data.get("id") or node_data.get("nodeId") or ""
                else:
                    _etype = "misc"
                    _nid = ""
                filtered_data.setdefault("event_type", _etype)
                filtered_data.setdefault("node_id", str(_nid) if _nid is not None else "")
                # 每条记录一个 event_id；用于 JSONL 合并去重（更稳）
                filtered_data.setdefault("event_id", uuid.uuid4().hex)
            except Exception:
                pass

            # 过滤不需要的 array 子工作流历史
            if "__array_" in str(workflow_id):
                try:
                    skip_root = self.BASE_DIR / "History"
                    for p in skip_root.rglob(f"{workflow_id}.json"):
                        try:
                            p.unlink()
                        except Exception:
                            pass
                    if debug:
                        print(f"⏭️ [HISTORY] 跳过并清理子数组工作流历史: {workflow_id}")
                except Exception:
                    pass
                return

            # 获取项目名（用于分目录存放）
            try:
                wf_meta = self.workflows.get(workflow_id) or {}
                graph_data = wf_meta.get("graph_data") if isinstance(wf_meta, dict) else {}
                project_name = None
                if isinstance(graph_data, dict):
                    project_name = graph_data.get("ProjectName") or graph_data.get("name")
                project_dir = self._safe_project_dir(project_name or "workflow")
            except Exception:
                project_dir = "workflow"

            # 保存到历史文件（串行化读改写，避免高并发下记录丢失）
            history_root = self.BASE_DIR / "History"
            history_dir = history_root / project_dir
            history_dir.mkdir(parents=True, exist_ok=True)
            file_path = history_dir / f'{workflow_id}.json'
            # ✅ 最小修改：改为缓冲 + 批量落盘，减少“读-改-写整文件”的频率与锁竞争
            now_ts = time.time()
            fp_str = str(file_path)
            old_items = None
            old_fp = None
            items_to_flush = None

            # 1) 锁内：更新 buffer / 决定是否需要 flush / 若路径变化则把旧 pending 取出
            with self._history_lock:
                entry = self._history_buffer.get(workflow_id)
                if (not entry) or entry.get("file_path") != fp_str:
                    # 若 path 变化，先把旧缓冲取走（锁外 I/O）
                    try:
                        if entry and entry.get("pending") and entry.get("file_path"):
                            old_items = (entry.get("pending") or [])[:]
                            old_fp = entry.get("file_path")
                    except Exception:
                        old_items, old_fp = None, None
                    entry = {"file_path": fp_str, "pending": [], "last_flush": now_ts}
                    self._history_buffer[workflow_id] = entry

                entry["pending"].append(filtered_data)

                should_flush = False
                try:
                    buf_n = int(getattr(self, "HISTORY_BUFFER_SIZE", 20) or 20)
                    if len(entry["pending"]) >= buf_n:
                        should_flush = True
                except Exception:
                    pass
                if not should_flush:
                    try:
                        last_flush = float(entry.get("last_flush", 0.0) or 0.0)
                        interval = float(getattr(self, "HISTORY_FLUSH_INTERVAL", 0.5) or 0.5)
                        if (now_ts - last_flush) >= interval:
                            should_flush = True
                    except Exception:
                        pass

                if should_flush:
                    items_to_flush = (entry.get("pending") or [])[:]
                    entry["pending"] = []
                    entry["last_flush"] = now_ts

            # 2) 锁外：实际落盘（JSONL append）
            try:
                if old_items and old_fp:
                    self._flush_history_items_to_file(Path(old_fp), old_items)
            except Exception:
                pass
            if items_to_flush:
                self._flush_history_items_to_file(file_path, items_to_flush)
                if debug:
                    print(f"✅ [HISTORY] 批量落盘 {len(items_to_flush)} 条 -> {file_path}")
            
        except Exception as e:
            debug = locals().get("debug", getattr(self, "DEBUG_PRINT", False))
            if debug:
                print(f"❌ [HISTORY] 添加历史记录失败: {e}")
                import traceback
                print(f"❌ [HISTORY] 错误详情: {traceback.format_exc()}")
    
    def _save_simple_history(self, graph_data):
        """
        简单历史快照：只保存 nodes 到 History/{name}_{YYYYmmdd_HHMMSS}.json
        - name 优先取 graph_data 中的可能字段，否则使用 'workflow'
        - 允许中文；若传入名包含“.json”后缀则移除，避免出现“.json_时间”
        """
        try:
            if not isinstance(graph_data, dict):
                return
            # 用户关闭历史记录时：不保存 run 快照（否则仍会产生大文件）
            try:
                if ("RecordHistory" in graph_data) and (not bool(graph_data.get("RecordHistory"))):
                    return
            except Exception:
                pass
            nodes = graph_data.get("nodes", [])
            edges = graph_data.get("edges", [])
            # 组件名（尽量简单安全）
            name_candidates = [
                (graph_data.get("ProjectName") if isinstance(graph_data.get("ProjectName"), str) else None),
                (graph_data.get("name") if isinstance(graph_data.get("name"), str) else None),
                "workflow"
            ]
            comp = next((x for x in name_candidates if x), "workflow")
            # 如果是子任务（例如 “测试项目 · 子任务3”），按“条数”语义只取主项目名部分
            try:
                if isinstance(comp, str) and "子任务" in comp:
                    # 约定格式："{base} · 子任务N" → 只保留 base
                    split_tok = "· 子任务"
                    idx = comp.find(split_tok)
                    if idx != -1:
                        comp = comp[:idx]
            except Exception:
                pass
            try:
                import re
                # 允许 Unicode 单词字符（含中文）+ . 与 -，其余替换为 _
                comp_safe = re.sub(r"[^\w\.\-]+", "_", str(comp)).strip("._")
                # 若包含 .json 后缀，移除以避免生成“.json_时间”
                if comp_safe.lower().endswith(".json"):
                    comp_safe = comp_safe[:-5].strip("._")
                if not comp_safe:
                    comp_safe = "workflow"
            except Exception:
                comp_safe = "workflow"
            ts = time.strftime("%Y%m%d_%H%M%S")
            history_dir = self.BASE_DIR / "History" / comp_safe
            history_dir.mkdir(parents=True, exist_ok=True)
            # 为避免高并发同一秒内文件名冲突，这里追加一个短随机后缀
            try:
                suffix = uuid.uuid4().hex[:6]
                fp = history_dir / f"{ts}_{suffix}.json"
            except Exception:
                # 兜底：仍然退化为旧命名方式
                fp = history_dir / f"{ts}.json"
            # 体积优化：只保存必要字段，并截断超长字符串
            def _trunc(s, max_chars: int = 4000):
                try:
                    if isinstance(s, str) and max_chars and len(s) > max_chars:
                        return s[:max_chars] + f"\n...[truncated {len(s) - max_chars} chars]"
                except Exception:
                    pass
                return s

            def _slim_ports(arr):
                out = []
                if not isinstance(arr, list):
                    return out
                for it in arr:
                    if not isinstance(it, dict):
                        continue
                    kind = str(it.get("Kind", "") or "")
                    d = {
                        "name": it.get("name"),
                        "Kind": it.get("Kind"),
                    }
                    if "String" in kind:
                        d["Context"] = _trunc(it.get("Context"))
                    elif "Boolean" in kind:
                        d["Boolean"] = it.get("Boolean")
                    elif "Num" in kind:
                        d["Num"] = it.get("Num")
                    out.append(d)
                return out

            def _slim_edges(arr):
                out = []
                if not isinstance(arr, list):
                    return out
                for e in arr:
                    if not isinstance(e, dict):
                        continue
                    out.append({
                        "id": e.get("id"),
                        "source": e.get("source"),
                        "target": e.get("target"),
                        "sourceAnchor": e.get("sourceAnchor"),
                        "targetAnchor": e.get("targetAnchor"),
                        "sourceAnchorID": e.get("sourceAnchorID"),
                        "targetAnchorID": e.get("targetAnchorID"),
                        # 可选字段：用于渲染/并行边恢复（存在则保留）
                        "type": e.get("type"),
                        "label": e.get("label"),
                        "curveOffset": e.get("curveOffset"),
                        "curvePosition": e.get("curvePosition"),
                        "minCurveOffset": e.get("minCurveOffset"),
                    })
                return out

            slim_nodes = []
            if isinstance(nodes, list):
                for n in nodes:
                    if not isinstance(n, dict):
                        continue
                    slim_nodes.append({
                        "id": n.get("id"),
                        "name": n.get("name"),
                        "label": n.get("label"),
                        "NodeKind": n.get("NodeKind"),
                        "isFinish": n.get("isFinish"),
                        "IsError": n.get("IsError"),
                        "ErrorContext": _trunc(n.get("ErrorContext")),
                        "Inputs": _slim_ports(n.get("Inputs", [])),
                        "Outputs": _slim_ports(n.get("Outputs", [])),
                    })

            payload = {
                "project": comp_safe,
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "nodes": slim_nodes,
                # 之前这里为了节省体积只存 nodes；但 edges 对回放/还原拓扑很关键，这里补回（仍为精简版）
                "edges": _slim_edges(edges)
            }
            with open(fp, "w", encoding="utf-8") as f:
                # 体积优化：不缩进 + 紧凑分隔符
                json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
            try:
                print(f"[HISTORY:SAVE] {fp}")
            except Exception:
                pass

            # ---------- 可选：按上限清理最老的“运行快照记录”文件 ----------
            # 仅清理当前项目目录下形如 YYYYMMDD_HHMMSS_xxxxxx.json 的快照文件，
            # 不影响 workflow_*.json（运行细节）或 YYYYMMDD.json（/addHistory 的按日记录）
            try:
                max_files = graph_data.get("HistoryMaxFiles") if isinstance(graph_data, dict) else None
                if max_files is None:
                    max_files = graph_data.get("history_max_files") if isinstance(graph_data, dict) else None
                max_files = int(max_files) if max_files is not None else 0
                if max_files and max_files > 0:
                    try:
                        import re as _re
                        pat = _re.compile(r"^\\d{8}_\\d{6}_.+\\.json$", _re.I)
                        cands = [p for p in history_dir.glob("*.json") if pat.match(p.name)]
                        cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                        for old in cands[max_files:]:
                            try:
                                old.unlink()
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception as _e_hist:
            try:
                print(f"[HISTORY:SAVE:ERR] {str(_e_hist)}")
            except Exception:
                pass
    
    def _load_module(self, script_path: Path):
        """
        节点脚本加载：
        - 默认：每次创建独立 module（避免多线程共享 module 全局变量导致“数据误传”）
        - 可选：开启 WF_SHARED_NODE_MODULES=1 时，复用 module（旧缓存行为）
        返回 module
        """
        p = Path(script_path).resolve()
        try:
            mtime = p.stat().st_mtime
        except Exception:
            mtime = None

        key = str(p)

        # 安全默认：隔离 module 全局变量（每次 new module）
        if not WF_SHARED_NODE_MODULES:
            mod_name = f"node_{p.stem}_{uuid.uuid4().hex}"
            spec = importlib.util.spec_from_file_location(mod_name, p)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Unable to load module spec for {p}")
            module = importlib.util.module_from_spec(spec)
            # IMPORTANT:
            # - We must register in sys.modules during exec_module for correct import semantics
            #   (e.g. circular imports inside node scripts).
            # - But with WF_SHARED_NODE_MODULES=0 we intentionally create a fresh module per run.
            #   Keeping those unique module names in sys.modules causes an unbounded memory/resource leak:
            #   many node scripts allocate global resources at import time (e.g. requests.Session / thread pools).
            #   If the module stays in sys.modules forever, those globals never get GC'd, and on Windows this can
            #   eventually exhaust sockets/ephemeral ports, making "all webpages fail" until the process exits.
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)
            finally:
                # Remove ephemeral module entry to avoid leaking thousands of modules over long-running workflows.
                # The returned `module` object is still referenced by the caller for this execution.
                try:
                    sys.modules.pop(spec.name, None)
                except Exception:
                    pass
            return module

        # 兼容旧行为：同一路径 + mtime 不变 => 复用 module（注意：并发下 module 全局状态会共享）
        with self._module_cache_lock:
            hit = self._module_cache.get(key)
            if hit and hit[0] == mtime and hit[1] is not None:
                return hit[1]

        mod_name = f"node_{p.stem}_{abs(hash(key))}"
        spec = importlib.util.spec_from_file_location(mod_name, p)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load module spec for {p}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        with self._module_cache_lock:
            self._module_cache[key] = (mtime, module)
        return module

    # -------------------------
    # System monitor helpers (for UI metrics)
    # -------------------------
    def _get_windows_dynamic_tcp_port_range(self):
        """
        Return (start_port, num_ports) for Windows TCP dynamic port range.
        Cached because calling netsh repeatedly is expensive.
        Fallback to the common default: start=49152, num=16384.
        """
        if self._dyn_port_range_cache:
            return self._dyn_port_range_cache

        start_port = 49152
        num_ports = 16384
        try:
            # netsh output example:
            #   Start Port      : 49152
            #   Number of Ports : 16384
            out = subprocess.check_output(
                ["netsh", "int", "ipv4", "show", "dynamicport", "tcp"],
                stderr=subprocess.STDOUT,
                text=True,
                timeout=2.0,
                encoding="utf-8",
                errors="ignore",
            )
            m1 = re.search(r"Start\s+Port\s*:\s*(\d+)", out, re.I)
            m2 = re.search(r"Number\s+of\s+Ports\s*:\s*(\d+)", out, re.I)
            if m1 and m2:
                sp = int(m1.group(1))
                np = int(m2.group(1))
                if 0 < sp < 65536 and 0 < np <= 65536:
                    start_port, num_ports = sp, np
        except Exception:
            pass

        self._dyn_port_range_cache = (start_port, num_ports)
        return self._dyn_port_range_cache

    def _compute_sysmon_metrics(self):
        """
        Compute 3 short metrics for frontend:
        - ConnNow: current TCP connection count for this process
        - TWNow: system-wide TCP TIME_WAIT count
        - PortUse: system-wide TCP dynamic(ephemeral) port utilization %, based on unique local ports in range
        Returns dict with keys: ConnNow, TWNow, PortUse
        """
        if str(os.getenv("WF_SYSMON_ENABLED", "1")).strip() in ("0", "false", "False", "no", "NO"):
            return {"ConnNow": None, "TWNow": None, "PortUse": None}

        # Prefer psutil (fast/portable). Fallback to netstat (Windows) if missing.
        try:
            import psutil  # type: ignore

            pid = os.getpid()
            proc = psutil.Process(pid)
            try:
                proc_conns = proc.net_connections(kind="tcp")
            except Exception:
                # Some psutil versions use connections()
                proc_conns = proc.connections(kind="tcp")  # type: ignore
            conn_now = len(proc_conns) if proc_conns is not None else None

            try:
                sys_conns = psutil.net_connections(kind="tcp")
            except Exception:
                sys_conns = []

            # TIME_WAIT count (system)
            tw = 0
            try:
                for c in (sys_conns or []):
                    st = getattr(c, "status", None)
                    if st == "TIME_WAIT" or st == getattr(psutil, "CONN_TIME_WAIT", "TIME_WAIT"):
                        tw += 1
            except Exception:
                tw = None

            # Dynamic port utilization (system)
            port_use = None
            try:
                sp, np = self._get_windows_dynamic_tcp_port_range()
                ep_start = int(sp)
                ep_end = int(sp + np - 1)
                used_ports = set()
                for c in (sys_conns or []):
                    la = getattr(c, "laddr", None)
                    lp = None
                    # psutil uses addr objects with (ip, port)
                    try:
                        lp = int(getattr(la, "port", None))
                    except Exception:
                        try:
                            lp = int(la[1]) if la and len(la) >= 2 else None
                        except Exception:
                            lp = None
                    if lp is None:
                        continue
                    if ep_start <= lp <= ep_end:
                        used_ports.add(lp)
                if np > 0:
                    port_use = round((len(used_ports) / float(np)) * 100.0, 1)
            except Exception:
                port_use = None

            return {"ConnNow": conn_now, "TWNow": tw, "PortUse": port_use}
        except Exception:
            pass

        # Fallback (Windows): netstat parsing (best-effort, may be slower)
        try:
            pid = str(os.getpid())
            out = subprocess.check_output(
                ["netstat", "-ano", "-p", "tcp"],
                stderr=subprocess.STDOUT,
                text=True,
                timeout=2.0,
                encoding="utf-8",
                errors="ignore",
            )
            conn_now = 0
            tw = 0
            sp, np = self._get_windows_dynamic_tcp_port_range()
            ep_start = int(sp)
            ep_end = int(sp + np - 1)
            used_ports = set()
            for line in (out or "").splitlines():
                s = line.strip()
                if not s.startswith("TCP"):
                    continue
                parts = re.split(r"\s+", s)
                # TCP local foreign state pid
                if len(parts) < 5:
                    continue
                local = parts[1]
                state = parts[3].upper()
                lpid = parts[4]
                if lpid == pid:
                    conn_now += 1
                if state == "TIME_WAIT":
                    tw += 1
                # local port
                try:
                    lp = int(local.rsplit(":", 1)[-1])
                except Exception:
                    lp = None
                if lp is not None and ep_start <= lp <= ep_end:
                    used_ports.add(lp)
            port_use = round((len(used_ports) / float(np)) * 100.0, 1) if np else None
            return {"ConnNow": conn_now, "TWNow": tw, "PortUse": port_use}
        except Exception:
            return {"ConnNow": None, "TWNow": None, "PortUse": None}

    def _get_sysmon_metrics_cached(self):
        now = time.time()
        try:
            with self._sysmon_lock:
                if (now - float(self._sysmon_cache_ts or 0.0)) < float(self._sysmon_cache_interval_s or 2.0):
                    return dict(self._sysmon_cache or {})
        except Exception:
            pass

        metrics = self._compute_sysmon_metrics()
        try:
            with self._sysmon_lock:
                self._sysmon_cache = dict(metrics or {})
                self._sysmon_cache_ts = now
        except Exception:
            pass
        return dict(metrics or {})

    def _find_script(self, node_name):
        """查找节点对应的脚本文件（与app.py保持一致）"""
        base = node_name[:-3] if node_name.lower().endswith(".py") else node_name
        candidates = [
            f"{base}.py",            # foo.py
            f"{base}/__init__.py",   # foo/__init__.py
            f"{base}/main.py",       # foo/main.py
        ]

        for cand in candidates:
            p = (self.NODES_DIR / cand).resolve()
            if p.is_file():
                return p

        # 兼容 macOS/Linux 的大小写差异：遍历一次
        lower_target_names = {Path(c).name.lower() for c in candidates}
        for p in self.NODES_DIR.rglob("*"):
            if p.is_file() and p.name.lower() in lower_target_names:
                return p

        return None
    
    def _resolve_tempfiles(self, ctx: str) -> str:
        """
        在多行字符串中把形如
            @TempFiles/path/to/file.txt
            @NoteBook\sub\dir
            ...
        的标记替换为 **绝对路径的 POSIX 形式**（使用正斜杠），并保证父目录存在。

        支持的标记：
            @TempFiles  @NoteBook  @Memory  @WorkFlow  @Nodes
        """
        if not isinstance(ctx, str):
            return ctx

        # 根目录映射
        DIRS = {
            "TempFiles": Path(self.TEMP_DIR),
            "NoteBook":  Path(self.NOTEBOOK_DIR),
            "Memory":    Path(self.MEMORY_DIR),
            "WorkFlow":  Path(self.WORKFLOW_DIR),
            "Nodes":     Path(self.NODES_DIR),
        }

        # 动态构造正则：@Tag[/\]optional_sub_path
        tag_pattern = "|".join(map(re.escape, DIRS.keys()))
        pattern = re.compile(
            rf'@(?P<tag>{tag_pattern})(?P<sep>[\\/])?(?P<sub>[^\s;,\n\r]*)',
            flags=re.MULTILINE,
        )

        def _repl(m: re.Match) -> str:
            tag   = m.group("tag")               # TempFiles / NoteBook / ...
            sub   = m.group("sub") or ""         # 跟在标签后的子路径
            base  = DIRS[tag]

            # 把子路径按 / 或 \ 拆开再拼接
            parts = re.split(r"[\\/]", sub) if sub else []
            full  = (base.joinpath(*parts)).resolve()

            # 若有具体文件/文件夹，确保父目录存在
            if parts:
                full.parent.mkdir(parents=True, exist_ok=True)

            # 统一输出为 POSIX 样式，避免 JSON 转义麻烦
            return full.as_posix()

        return pattern.sub(_repl, ctx)
    
    def _resolve_aliases_in_node(self, node: dict) -> dict:
        """解析 node 中 Inputs/ExportPrompt 的 @TempFiles 等别名到绝对路径（与 app.py 对齐）"""
        try:
            TAGS = ["TempFiles", "NoteBook", "Memory", "WorkFlow", "Nodes"]
            for tag in TAGS:
                marker = f"@{tag}"
                for inp in node.get("Inputs", []):
                    ctx = inp.get("Context")
                    if isinstance(ctx, str) and marker in ctx:
                        inp["Context"] = self._resolve_tempfiles(ctx)
                ex_prompt = node.get("ExportPrompt")
                if isinstance(ex_prompt, str) and marker in ex_prompt:
                    node["ExportPrompt"] = self._resolve_tempfiles(ex_prompt)
        except Exception:
            pass
        return node
    
    def _collect_related_workflow_ids(self, workflow_id: str):
        """收集与 workflow_id 相关的所有工作流（包含 batch）"""
        base_id = workflow_id.split('_batch_')[0]
        related = set()
        for wid in list(self.workflows.keys()):
            if wid == workflow_id:
                related.add(wid)
            elif wid.startswith(f"{base_id}_batch_"):
                related.add(wid)
        return related or {workflow_id}

    def _ensure_child_summary(self, workflow_id: str):
        wf = self.workflows.get(workflow_id)
        if not wf:
            return None
        summary = wf.setdefault("child_summary", {"active": 0, "completed": 0, "failed": 0, "total": 0})
        return summary

    def _has_active_children(self, workflow_id: str) -> bool:
        wf = self.workflows.get(workflow_id)
        if not wf:
            return False
        summary = wf.get("child_summary") or {}
        return summary.get("active", 0) > 0

    def _register_child_workflow(self, parent_id: str, child_id: str):
        self.child_workflows.setdefault(parent_id, set()).add(child_id)
        self.parent_map[child_id] = parent_id
        self._ensure_child_summary(parent_id)

    def _unregister_child_workflow(self, child_id: str):
        parent_id = self.parent_map.pop(child_id, None)
        if parent_id:
            children = self.child_workflows.get(parent_id)
            if children and child_id in children:
                children.discard(child_id)
            if not children:
                self.child_workflows.pop(parent_id, None)
        return parent_id

    def _refresh_parent_array_queue(self, workflow_id: str, pending_array_len: int):
        wf = self.workflows.get(workflow_id)
        if not wf:
            return
        summary = self._ensure_child_summary(workflow_id) or {}
        active_children = summary.get("active", 0)
        total_array = max(0, pending_array_len) + active_children
        wf.setdefault("queue_lengths", {})
        wf["queue_lengths"]["array"] = total_array
        passivity_len = wf["queue_lengths"].get("passivity", wf["queue_lengths"].get("pending", 0))
        wf["queue_lengths"]["passivity"] = passivity_len
        wf["queues"] = {"pending": passivity_len, "array": total_array}

    def _stop_child_workflows(self, workflow_id: str):
        children = list(self.child_workflows.get(workflow_id, set()))
        for child_id in children:
            if child_id in self.workflows:
                self.stop_workflow(child_id)

    def _schedule_workflow_cleanup(self, workflow_id: str, delay: float = 5.0):
        """延迟清理工作流，给前端留出同步时间"""
        if delay <= 0:
            try:
                self._flush_history_buffer_for_workflow(workflow_id)
            except Exception:
                pass
            self.cleanup_workflow(workflow_id)
            return

        # 取消已有定时器
        timer = self._cleanup_timers.pop(workflow_id, None)
        if timer:
            try:
                timer.cancel()
            except Exception:
                pass

        def _cleanup():
            try:
                try:
                    self._flush_history_buffer_for_workflow(workflow_id)
                except Exception:
                    pass
                self.cleanup_workflow(workflow_id)
            except Exception as e:
                print(f"[CLEANUP] 延迟清理 {workflow_id} 失败: {e}")

        timer = threading.Timer(delay, _cleanup)
        timer.daemon = True
        timer.start()
        self._cleanup_timers[workflow_id] = timer

    def _normalize_result(self, result):
        """统一处理节点执行结果格式"""
        if isinstance(result, dict) and "outputs" in result:
            output, debug_text = result["outputs"], result.get("debug", "")
        else:
            output, debug_text = result, ""

        if isinstance(output, str):
            import re
            m = re.search(r"```(?:json)?\s*(.*?)\s*```", output, re.S | re.I)
            raw = m.group(1) if m else output
            try:
                output = json.loads(raw)
            except Exception:
                pass

        if isinstance(output, list) and len(output) == 1 and isinstance(output[0], list):
            output = output[0]

        if not isinstance(output, list):
            output = [output]

        return output, debug_text
    
    def _process_node(self, node):
        """处理节点的输入输出，准备执行环境 - 完全按照老代码逻辑"""
        # ✅ 并发止血：保持“纯函数风格”，不回写传入 node（入参可能被并发共享）
        # 统一在局部副本上进行 tempfiles 解析 / 模板替换 / messages 组装
        try:
            node = copy.deepcopy(node)
        except Exception:
            # 兜底：至少浅拷贝，避免直接污染外部引用
            node = dict(node or {})
        # ---------- 1. 先解析 @TempFiles、@Memory 等标签 ----------
        TAGS = ["TempFiles", "NoteBook", "Memory", "WorkFlow", "Nodes"]
        for tag in TAGS:
            marker = f"@{tag}"
            for inp in node.get("Inputs", []):
                ctx = inp.get("Context")
                if isinstance(ctx, str) and marker in ctx:
                    inp["Context"] = self._resolve_tempfiles(ctx)

            ex_prompt = node.get("ExportPrompt")
            if isinstance(ex_prompt, str) and marker in ex_prompt:
                node["ExportPrompt"] = self._resolve_tempfiles(ex_prompt)

        # ---------- 2. 构造完整对话 messages（含图片） ----------
        # 2.1 收集需要转 Base64 的图片
        temp_images_b64 = []
        node_kind = node.get("NodeKind")
        
        # 只有当节点类型为LLm时才处理图片
        if node_kind == "LLm":
            # 检查文件路径是否为图片后缀
            image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
            temp_images_b64 = [
                self._image_to_base64(inp.get("Context", ""))
                for inp in node.get("Inputs", [])
                if isinstance(inp.get("Kind"), str) and "FilePath" in inp["Kind"] 
                and any(inp.get("Context", "").lower().endswith(ext) for ext in image_extensions)
            ]

        # 2.2 构建 ExprotAfterPrompt（每次重建，避免沿用旧模板/描述）
        if node_kind == "LLm":
            export_after_prompt = 'Please ensure the output is in JSON format\n{\n'
            for output in node.get("Outputs", []):
                output_kind = ''
                if output.get("Kind", "").find('String') >= 0:
                    output_kind = 'String'
                elif output.get("Kind") == 'Num':
                    output_kind = 'Num'
                elif output.get("Kind") == 'Boolean':
                    output_kind = 'Boolean'
                export_after_prompt += f'"{output.get("Id", "")}": "{output.get("Description", "")}" (you need output type:{output_kind})\n'
            export_after_prompt += '}\n'
            node['ExprotAfterPrompt'] = export_after_prompt

        # 2.3 system_prompt 生成
        system_prompt = f"{node.get('SystemPrompt', '')}\n{node.get('ExprotAfterPrompt', '')}"
        if node.get("OriginalTextSelector") == "OriginalText":
            system_prompt = node.get("SystemPrompt", "")

        # 直接使用节点的 prompt 作为 ExportPrompt（不做模板替换）
           # ---------- 2.2.1 处理 prompt 模板替换（关键步骤！） ----------

        # 替换 ExportPrompt/Prompt 中的占位符（同时兼容两种来源）
        template_text = node.get("prompt") or node.get("ExportPrompt", "") or ""
        export_prompt = template_text
        matches = retrieve_content_within_braces(template_text)

        def _replace_token(text, token, value):
            try:
                # 使用正则替换，允许 {{ 变量 }} 与 {{变量}}，支持中英文 token
                return re.sub(r'{{\s*' + re.escape(token) + r'\s*}}', value if value is not None else "", text)
            except Exception:
                return text

        for match in matches:
            for input_item in node.get("Inputs", []) or []:
                # 统一为字符串并去除空格，避免中英文与空白差异导致不匹配
                token = (str(match).strip() if match is not None else "")
                aliases = [
                    (str(input_item.get("name")).strip()  if input_item.get("name")  is not None else None),
                    (str(input_item.get("Id")).strip()    if input_item.get("Id")    is not None else None),
                    (str(input_item.get("Alias")).strip() if input_item.get("Alias") is not None else None),
                ]
                if token and token in [a for a in aliases if a is not None]:
                    if input_item.get("Kind") == 'Num':
                        val = str(input_item.get("Num", ""))
                    elif isinstance(input_item.get("Kind"), str) and ('String' in input_item.get("Kind")):
                        val = str(input_item.get("Context", ""))
                    elif input_item.get("Kind") == 'Boolean':
                        val = "true" if input_item.get("Boolean", False) else "false"
                    else:
                        val = ""
                    export_prompt = _replace_token(export_prompt, token, val)
                    break

        # 二次兜底：仍有未替换的 {{...}} 占位符时，清空为空串
        if '{{' in export_prompt and '}}' in export_prompt:
            leftovers = retrieve_content_within_braces(export_prompt)
            for token in leftovers:
                export_prompt = _replace_token(export_prompt, token, "")

        # ExportPrompt 仅写回局部副本（不污染外部共享 node）
        node["ExportPrompt"] = export_prompt
        try:
            print(f"[DEBUG:PROCESS_NODE] ExportPrompt after replace → {node.get('ExportPrompt')}")
        except Exception:
            pass

        # 处理 SystemPrompt 中的模板变量
        system_matches = retrieve_content_within_braces(node.get("SystemPrompt", ""))
        system_prompt_processed = node.get("SystemPrompt", "")
        for match in system_matches:
            for input_item in node.get("Inputs", []):
                token = (str(match).strip() if match is not None else "")
                aliases = [
                    (str(input_item.get("name")).strip()  if input_item.get("name")  is not None else None),
                    (str(input_item.get("Id")).strip()    if input_item.get("Id")    is not None else None),
                    (str(input_item.get("Alias")).strip() if input_item.get("Alias") is not None else None),
                ]
                if token and token in [a for a in aliases if a is not None]:
                    replacement = ""
                    if input_item.get("Kind") == 'Num':
                        replacement = str(input_item.get("Num", ""))
                    elif input_item.get("Kind", "").find('String') >= 0:
                        replacement = str(input_item.get("Context", ""))
                    elif input_item.get("Kind") == 'Boolean':
                        replacement = str(input_item.get("Boolean", ""))
                    # 使用正则替换，允许占位符内部空格
                    system_prompt_processed = re.sub(r'{{\s*' + re.escape(token) + r'\s*}}', replacement, system_prompt_processed)
                    break

        # 重新生成 system_prompt（仅用于本次消息拼装，不回写覆盖 SystemPrompt 原值）
        system_prompt = f"{system_prompt_processed}\n{node.get('ExprotAfterPrompt', '')}"
        if node.get("OriginalTextSelector") == "OriginalText":
            system_prompt = system_prompt_processed

        # 2.3 拼接消息列表
        msg_list = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": node.get("ExportPrompt", "")},
            *[m for m in node.get("messages", []) if m.get("role") != "System"],
        ]
        for b64 in temp_images_b64:
            msg_list.append({
                "role": "user",
                "content": [{
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                }]
            })

        # messages 仅写回局部副本（不污染外部共享 node）
        node["messages"] = msg_list
        
        return node
    
    def _image_to_base64(self, fp: str) -> str:
        """将图片转换为base64编码"""
        fp = Path(fp).expanduser().resolve()
        with open(fp, "rb") as f:
            return base64.b64encode(f.read()).decode()
    
    def _execute_node(self, node, workflow_id: str = None):
        """执行单个节点（完全从app.py迁移的逻辑）"""
        # ✅ 去掉重复 deepcopy：调用方（线程提交前 / _process_node）通常已做过 deepcopy
        # 这里直接使用入参（并尽量避免回写）。
        node_local = node if isinstance(node, dict) else dict(node or {})

        node_name = node_local.get("name")
        self.dbg(f"🔧 [EXECUTE] 开始执行节点: {node_local.get('label', node_local.get('id'))} ({node_name})")
        self.dbg(f"🔧 [EXECUTE] 节点类型: {node_local.get('NodeKind')}")
        self.dbg(f"🔧 [EXECUTE] 输入数量: {len(node_local.get('Inputs', []))}")
        self.dbg(f"🔧 [EXECUTE] 输出数量: {len(node_local.get('Outputs', []))}")
        
        # ---------- 1. 先解析 @TempFiles、@Memory 等标签 ----------
        TAGS = ["TempFiles", "NoteBook", "Memory", "WorkFlow", "Nodes"]
        for tag in TAGS:
            marker = f"@{tag}"
            for inp in node_local.get("Inputs", []):
                ctx = inp.get("Context")
                if isinstance(ctx, str) and marker in ctx:
                    inp["Context"] = self._resolve_tempfiles(ctx)

            ex_prompt = node_local.get("ExportPrompt")
            if isinstance(ex_prompt, str) and marker in ex_prompt:
                node_local["ExportPrompt"] = self._resolve_tempfiles(ex_prompt)

        # ---------- 2. 构造完整对话 messages（含图片） ----------
        # 2.1 收集需要转 Base64 的图片
        temp_images_b64 = []
        node_kind = node_local.get("NodeKind")
        
        # 只有当节点类型为LLm时才处理图片
        if node_kind == "LLm":
            # 检查文件路径是否为图片后缀
            image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
            temp_images_b64 = [
                self._image_to_base64(inp.get("Context", ""))
                for inp in node_local.get("Inputs", [])
                if isinstance(inp.get("Kind"), str) and "FilePath" in inp["Kind"] 
                and any(inp.get("Context", "").lower().endswith(ext) for ext in image_extensions)
            ]

        # ✅ C. 去掉“二次替换”：仅保留 _process_node 阶段的模板替换
        export_prompt_to_send = node_local.get("ExportPrompt", "")

        # 2.3 system_prompt 生成
        system_prompt = f"{node_local.get('SystemPrompt', '')}\n{node_local.get('ExprotAfterPrompt', '')}"
        if node_local.get("OriginalTextSelector") == "OriginalText":
            system_prompt = node_local.get("SystemPrompt", "")

        # 2.4 拼接消息列表
        msg_list = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": export_prompt_to_send},
            *[m for m in node_local.get("messages", []) if m.get("role") != "System"],
        ]
        for b64 in temp_images_b64:
            msg_list.append({
                "role": "user",
                "content": [{
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                }]
            })

        # ✅ 不回写 node_local；仅构造本次执行的 payload
        node_to_run = dict(node_local)
        node_to_run["messages"] = msg_list
        node_to_run["ExportPrompt"] = export_prompt_to_send
        try:
            print(f"[DEBUG:EXEC_NODE] ExportPrompt before send → {export_prompt_to_send}")
            if msg_list and isinstance(msg_list, list) and len(msg_list) > 1:
                print(f"[DEBUG:EXEC_NODE] USER content → {msg_list[1].get('content')}")
        except Exception:
            pass

        # ---------- 3. 统一结果格式处理 ----------
        def normalize_result(result):
            if isinstance(result, dict) and "outputs" in result:
                output, debug_text = result["outputs"], result.get("debug_text", "")
            else:
                output, debug_text = result, ""

            if isinstance(output, str):
                m = re.search(r"```(?:json)?\s*(.*?)\s*```", output, re.S | re.I)
                raw = m.group(1) if m else output
                try:
                    output = json.loads(raw)
                except Exception:
                    pass

            if isinstance(output, list) and len(output) == 1 and isinstance(output[0], list):
                output = output[0]

            if not isinstance(output, list):
                output = [output]

            return output, debug_text

        # ---------- 4. 分支：ReAct / LangGraph ----------
        node_kind = node_to_run.get("NodeKind")
        tools = node_to_run.get("Tools")
        is_react = node_to_run.get("IsReact")

        if node_kind == "LLm" and tools is not None and is_react is True:
            try:
                langgraph_agent_path = (self.BASE_DIR / "Langgraph" / "Agent.py").resolve()
                if not langgraph_agent_path.is_file():
                    return {"error": f"Langgraph/Agent.py not found at {langgraph_agent_path}"}, 404

                capture = (not bool(self.enable_debug_print)) and bool(CAPTURE_NODE_STDIO_WHEN_SILENCED)
                with _thread_stdio_scope(console_enabled=bool(self.enable_debug_print), capture=capture) as _buf:
                    # I/O (module load) must be outside self.lock
                    module = self._load_module(langgraph_agent_path)

                    result = module.run_node(node_to_run)
                    output, debug_text = normalize_result(result)
                if _buf is not None:
                    debug_text = _merge_debug_with_stdio(debug_text, _buf.getvalue())

                result_data = {
                    "output":       output,
                    "debug":        debug_text,
                    "inputs":       node_to_run.get("Inputs", []),
                    "ExportPrompt": export_prompt_to_send,
                }
                
                # 打印执行结果
                print(f"✅ [EXECUTE] LangGraph节点执行完成: {node_to_run.get('label', node_to_run.get('id'))}")
                print(f"✅ [EXECUTE] 输出数量: {len(output)}")
                print(f"✅ [EXECUTE] Debug长度: {len(debug_text)}")
                if output:
                    print(f"✅ [EXECUTE] 第一个输出预览: {str(output[0])[:100]}..." if len(str(output[0])) > 100 else f"✅ [EXECUTE] 第一个输出: {output[0]}")
                
                # 添加指纹日志
                try:
                    outs = result_data.get("output") if isinstance(result_data, dict) else None
                    fp = self._calc_fp(node_to_run.get("id"), outs)
                    print(f"[RING:FP] recv {fp}")
                except Exception:
                    pass
                
                return result_data

            except Exception as e:
                return {"error": str(e), "trace": traceback.format_exc()}, 400

        # ---------- 5. 分支：普通脚本 ----------
        script_path = self._find_script(node_name)
        if script_path is None or not script_path.is_file():
            return {"error": f"Script {node_name} not found"}, 404

        try:
            capture = (not bool(self.enable_debug_print)) and bool(CAPTURE_NODE_STDIO_WHEN_SILENCED)
            with _thread_stdio_scope(console_enabled=bool(self.enable_debug_print), capture=capture) as _buf:
                # I/O (module load) must be outside self.lock
                module = self._load_module(script_path)

                # ★ 新增：执行前解析别名，确保工具收到绝对路径
                node_to_run2 = self._resolve_aliases_in_node(copy.deepcopy(node_to_run))

                # ★ 关键修复：注入并持久化 node["_state"]（用于 Timer 等触发器跨轮记忆）
                if WF_PERSIST_NODE_STATE:
                    try:
                        nid = node_to_run2.get("id") or node_to_run2.get("nodeId")
                        if workflow_id and nid:
                            st = self._get_node_state(str(workflow_id), str(nid))
                            if st is not None:
                                node_to_run2["_state"] = st
                    except Exception:
                        pass

                result = module.run_node(node_to_run2)
                output, debug_text = normalize_result(result)

                # 回写持久化状态（脚本可能更新了 node_to_run2["_state"]）
                if WF_PERSIST_NODE_STATE:
                    try:
                        nid = node_to_run2.get("id") or node_to_run2.get("nodeId")
                        if workflow_id and nid:
                            self._set_node_state(str(workflow_id), str(nid), node_to_run2.get("_state"))
                    except Exception:
                        pass
            if _buf is not None:
                debug_text = _merge_debug_with_stdio(debug_text, _buf.getvalue())

            result = {
                "output":       output,
                "debug":        debug_text,
                "inputs":       node_to_run2.get("Inputs", []),
                "ExportPrompt": export_prompt_to_send,
            }
            
            # 打印执行结果
            print(f"✅ [EXECUTE] 节点执行完成: {node_to_run2.get('label', node_to_run2.get('id'))}")
            print(f"✅ [EXECUTE] 输出数量: {len(output)}")
            print(f"✅ [EXECUTE] Debug长度: {len(debug_text)}")
            if output:
                print(f"✅ [EXECUTE] 第一个输出预览: {str(output[0])[:100]}..." if len(str(output[0])) > 100 else f"✅ [EXECUTE] 第一个输出: {output[0]}")
            
                # 添加指纹日志
                try:
                    outs = result.get("output") if isinstance(result, dict) else None
                    fp = self._calc_fp(node_to_run2.get("id"), outs)
                    print(f"[RING:FP] recv {fp}")
                except Exception:
                    pass
            
            return result

        except Exception as e:
            return {"error": str(e), "trace": traceback.format_exc()}, 400
    
    def _get_linked_edges(self, edges, node_id):
        """获取节点相关的边"""
        outgoing = [e for e in edges if e.get("source") == node_id]
        incoming = [e for e in edges if e.get("target") == node_id]
        return {"outgoing": outgoing, "incoming": incoming}
    
    def _update_node_status(self, graph_data, node_id, status):
        """更新节点状态"""
        for node in graph_data.get("nodes", []):
            if node.get("id") == node_id:
                node.update(status)
                break
        return graph_data
    
    def _update_workflow_state(self, workflow_id, data_temp=None, local_passivity_array=None, local_array_trigger_array=None):
        """统一更新工作流状态的方法"""
        dbg_lines = []
        with self.lock:
            # 检查工作流是否存在且不为None
            if workflow_id not in self.workflows:
                return
                
            if self.workflows[workflow_id] is None:
                return
            
            try:
                # 允许 data_temp 为 None：仅刷新队列长度与时间戳
                if data_temp is None:
                    dbg_lines.append(f"[STATE] (partial) 仅刷新队列长度: workflow_id={workflow_id}")
                else:
                    # 打印状态更新信息
                    nodes_count = len(data_temp.get("nodes", []))
                    edges_count = len(data_temp.get("edges", []))
                    dbg_lines.append(f"🔄 [STATE] 更新工作流状态: {workflow_id}")
                    dbg_lines.append(f"🔄 [STATE] 节点数量: {nodes_count}, 边数量: {edges_count}")
                    self.workflows[workflow_id]["graph_data"] = data_temp
                self.workflows[workflow_id]["last_update"] = time.time()
                
                # 更新队列长度（允许部分更新）
                qlens = self.workflows[workflow_id].get("queue_lengths", {"passivity": 0, "array": 0}).copy()
                if local_passivity_array is not None:
                    qlens["passivity"] = len(local_passivity_array)
                    dbg_lines.append(f"🔄 [STATE] 被动队列长度: {len(local_passivity_array)}")
                if local_array_trigger_array is not None:
                    qlens["array"] = len(local_array_trigger_array)
                    dbg_lines.append(f"🔄 [STATE] 数组队列长度: {len(local_array_trigger_array)}")
                self.workflows[workflow_id]["queue_lengths"] = qlens
                # 同步写入固定字段 queues，方便前端直接读取
                self.workflows[workflow_id]["queues"] = {"pending": qlens.get("passivity", 0), "array": qlens.get("array", 0)}
                if local_passivity_array is not None:
                    self.workflows[workflow_id]["pending_passivity_count"] = len(local_passivity_array)
                if local_array_trigger_array is not None:
                    self.workflows[workflow_id]["pending_array_count"] = len(local_array_trigger_array)
                    self._refresh_parent_array_queue(workflow_id, len(local_array_trigger_array))
                try:
                    dbg_lines.append(f"[STATE:QUEUES] write queue_lengths={{P:{qlens.get('passivity',0)}, A:{qlens.get('array',0)}}} queues={{pending:{self.workflows[workflow_id]['queues'].get('pending',0)}, array:{self.workflows[workflow_id]['queues'].get('array',0)}}}")
                except Exception:
                    pass
                
                dbg_lines.append("✅ [STATE] 工作流状态更新完成")
                    
            except Exception as e:
                import traceback
                dbg_lines.append(f"❌ [ERROR] _update_workflow_state failed: {e}")
                dbg_lines.append(f"❌ [ERROR] Traceback: {traceback.format_exc()}")
        # I/O outside lock
        for line in dbg_lines:
            self.dbg(line)
    
    def _extract_passivity_triggers(self, graph_data):
        """从图数据中提取passivity trigger数据"""
        # 初始化时不创建默认数据，让 passivityTrigger 节点自己运行生成数据
        # 这与前端逻辑保持一致：初始时 passivityTriggerArray 为空，通过 runPassivityTriggerNodes 填充
        passivity_triggers = []
        

        return passivity_triggers
    
    def _extract_array_triggers(self, graph_data):
        """从图数据中提取array trigger数据"""  
        # 检查前端是否传递了ArrayTrigger数据
        # 在新架构中，应该让ArrayTrigger节点自己运行生成数据，而不是预填充
        
        # 暂时返回空数组，让ArrayTrigger节点通过 _run_array_trigger_nodes 自己生成数据
        array_triggers = []
        
        # 只有在特殊情况下才预填充数据（比如从前端传递过来的数据）
        # 这里可以根据实际需求调整
        

        return array_triggers
    
    def _process_node_inputs(self, node):
        """处理节点输入，与前端getNodeInputs保持一致"""
        inputs = {}
        for idx, input_item in enumerate(node.get("Inputs", [])):
            if input_item.get("Kind") == "Num":
                if input_item.get("Num") is None and input_item.get("Isnecessary", False):
                    raise Exception(f"节点 {node.get('label')} 的输入点 {input_item.get('Id')} 缺失，请检查")
                inputs[idx] = input_item.get("Num")
            elif "String" in input_item.get("Kind", ""):
                if input_item.get("Context") is None and input_item.get("Isnecessary", False):
                    raise Exception(f"节点 {node.get('label')} 的输入点 {input_item.get('Id')} 缺失，请检查")
                inputs[idx] = input_item.get("Context")
            elif input_item.get("Kind") == "Boolean":
                if input_item.get("Boolean") is None and input_item.get("Isnecessary", False):
                    raise Exception(f"节点 {node.get('label')} 的输入点 {input_item.get('Id')} 缺失，请检查")
                inputs[idx] = input_item.get("Boolean")
        return inputs
    
    def _process_llm_prompt(self, node):
        """处理LLM节点的提示词"""
        # 简化实现，实际应与前端逻辑保持一致
        system_prompt = node.get("SystemPrompt", "")
        export_prompt = node.get("ExportPrompt", "")
        return [system_prompt, export_prompt]
    
    def _process_context(self, context):
        """处理输出上下文"""
        # 简化实现，实际应与前端逻辑保持一致
        return context

    def _normalize_output_for_port(self, item, port_kind):
        """将节点执行返回的任意类型输出规范化为前端期望的结构。
        - String* → { Context }
        - Num     → { Num }
        - Boolean → { Boolean }
        其他未知类型一律落入 Context 字段（转字符串/JSON）。
        """
        try:
            kind = (port_kind or '').lower()
            # 直接是 dict，假定已经是规范结构
            if isinstance(item, dict):
                return item
            # 列表：对常见情况做降维或 JSON 化
            if isinstance(item, list):
                if 'string' in kind:
                    # 仅保留字符串，其他元素 JSON 化后拼接
                    def to_str(x):
                        if isinstance(x, str):
                            return x
                        try:
                            return json.dumps(x, ensure_ascii=False)
                        except Exception:
                            return str(x)
                    return { 'Context': '\n'.join(to_str(x) for x in item) }
                # 数值端口：取第一个可解析为数字的元素
                if 'num' in kind:
                    for x in item:
                        if isinstance(x, (int, float)):
                            return { 'Num': x }
                    return { 'Num': None }
                if 'boolean' in kind:
                    for x in item:
                        if isinstance(x, bool):
                            return { 'Boolean': x }
                    return { 'Boolean': False }
                # 其它：落入 Context（JSON）
                try:
                    return { 'Context': json.dumps(item, ensure_ascii=False) }
                except Exception:
                    return { 'Context': str(item) }

            # 标量
            if 'string' in kind:
                return { 'Context': item if isinstance(item, str) else str(item) }
            if 'num' in kind:
                if isinstance(item, (int, float)):
                    return { 'Num': item }
                try:
                    return { 'Num': float(item) }
                except Exception:
                    return { 'Num': None }
            if 'boolean' in kind:
                return { 'Boolean': bool(item) }
            # 其它：落入 Context
            return { 'Context': str(item) }
        except Exception:
            return { 'Context': str(item) }
    
    def _convert_between_kinds(self, item_dict, target_kind):
        """将任意 {Context|Num|Boolean} 字典转换为目标端口类型的字典（只返回该目标键）。
        规则：
        - Num <=> Boolean: 1/0 ↔ True/False
        - Context <=> Boolean: 忽略大小写，'true'/'false' 可互转；数字字符串视为非零即 True
        - Context <=> Num: 可解析的数字字符串转为数值；数值转字符串
        """
        try:
            kind = (target_kind or "").lower()
            ctx = item_dict.get("Context") if isinstance(item_dict, dict) else None
            num = item_dict.get("Num") if isinstance(item_dict, dict) else None
            boo = item_dict.get("Boolean") if isinstance(item_dict, dict) else None
            
            # 更稳健的数字解析：支持 'Num' 为字符串、千分位、正负号与小数
            def _parse_number(value):
                try:
                    # 已是数值
                    if isinstance(value, (int, float)):
                        return int(value) if isinstance(value, float) and value.is_integer() else value
                    # 尝试从字符串解析
                    if isinstance(value, str):
                        s = value.strip()
                        if not s:
                            return None
                        # 常见千分位形式：1,234,567.89 或 -1,234
                        # 仅当字符串只包含数字/逗号/点/正负号时才去除逗号
                        import re
                        if re.fullmatch(r"[+\-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?", s):
                            s = s.replace(",", "")
                        # 常规纯数字/小数
                        if re.fullmatch(r"[+\-]?\d+(?:\.\d+)?", s):
                            v = float(s)
                            return int(v) if v.is_integer() else v
                        # 其它不支持的格式
                        return None
                    return None
                except Exception:
                    return None
            
            def to_num():
                # 1) 直接取 Num
                parsed_from_num = _parse_number(num)
                try:
                    print(f"[CONVERT:to_num] raw num={num} parsed={parsed_from_num}")
                except Exception:
                    pass
                if parsed_from_num is not None:
                    return parsed_from_num
                # 2) Context → 若为数字字符串，优先解析为数值
                if isinstance(ctx, str):
                    s = ctx.strip()
                    parsed = _parse_number(s)
                    try:
                        print(f"[CONVERT:to_num] from Context='{s}' parsed={parsed}")
                    except Exception:
                        pass
                    if parsed is not None:
                        return parsed
                # 3) Boolean → 1/0（最后兜底，避免覆盖 Context 的数值字符串）
                if isinstance(boo, bool):
                    try:
                        print(f"[CONVERT:to_num] from Boolean={boo} -> {1 if boo else 0}")
                    except Exception:
                        pass
                    return 1 if boo else 0
                return None
            
            def to_bool():
                # 优先从 Context 判断（很多上游节点是 String 端口，Boolean 字段可能只是占位默认值 False）
                if isinstance(ctx, str):
                    s = ctx.strip().lower()
                    if s in ("true", "false"):
                        return s == "true"
                    try:
                        parsed = _parse_number(s)
                        if parsed is not None:
                            return bool(parsed)
                        v = float(s)
                        return bool(v)
                    except Exception:
                        pass
                # 其次使用明确的 Boolean 字段
                if isinstance(boo, bool):
                    return boo
                if isinstance(boo, str):
                    s = boo.strip().lower()
                    if s in ("true", "false"):
                        return s == "true"
                    try:
                        parsed = _parse_number(s)
                        if parsed is not None:
                            return bool(parsed)
                    except Exception:
                        pass
                # 再退化为 Num → 非零即真
                parsed_from_num = _parse_number(num)
                if parsed_from_num is not None:
                    return bool(parsed_from_num)
                return None
            
            def to_context():
                if isinstance(ctx, str):
                    return ctx
                parsed_from_num = _parse_number(num)
                if parsed_from_num is not None:
                    # 尽量不带小数点的整数外观
                    if isinstance(parsed_from_num, float) and parsed_from_num.is_integer():
                        return str(int(parsed_from_num))
                    return str(parsed_from_num)
                if isinstance(boo, bool):
                    return "true" if boo else "false"
                return None
            
            if "num" in kind:
                v = to_num()
                return {"Num": v}
            if "boolean" in kind:
                v = to_bool()
                return {"Boolean": v}
            # 其它一律视为 String(Context)
            v = to_context()
            return {"Context": v}
        except Exception:
            # 失败则不写入任何有效值
            if isinstance(target_kind, str) and target_kind == "Num":
                return {"Num": None}
            if isinstance(target_kind, str) and target_kind == "Boolean":
                return {"Boolean": None}
            return {"Context": None}
    
    def _coerce_to_dict(self, value):
        """将任意标量/列表尽可能转为 {Context|Num|Boolean} 字典，用于后续跨类型转换。"""
        try:
            if isinstance(value, dict):
                return value
            # 若是列表，优先找能转成字典的元素；否则取第一个可识别的标量
            if isinstance(value, list):
                for el in value:
                    d = self._coerce_to_dict(el)
                    if isinstance(d, dict):
                        return d
                return None
            if isinstance(value, bool):
                return {"Boolean": value}
            if isinstance(value, (int, float)):
                return {"Num": value}
            if isinstance(value, str):
                return {"Context": value}
            return None
        except Exception:
            return None
    
    def _calc_fp(self, node_id: str, outputs) -> str:
        """
        基于 node_id + 输出关键字段生成稳定指纹；
        outputs 可以是 list[dict] / list / dict / 标量。
        """
        import hashlib, json
        def _normalize(o):
            if isinstance(o, dict):
                # 只取对 UI 有意义的键，避免无关噪声导致指纹抖动
                keep = {k: o.get(k) for k in ("Id","Kind","Context","Num","Boolean")}
                return keep
            if isinstance(o, (list, tuple)):
                return [_normalize(x) for x in o]
            return o
        payload = {"node": node_id, "outs": _normalize(outputs)}
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
    
    def _reset_block_flags(self, graph_data):
        """
        运行结束/停止后，将所有节点的 IsBlock 复位为 False，恢复为可编辑状态。
        仅用于返回给前端的 graph_data，不影响执行过程中的内部语义。
        """
        try:
            if not isinstance(graph_data, dict):
                return
            nodes = graph_data.get("nodes") or []
            for n in nodes:
                if isinstance(n, dict):
                    n["IsBlock"] = False
        except Exception:
            # 复位失败不应影响主流程
            pass

    def _execute_workflow_thread(self, workflow_id, graph_data, passivity_trigger_array, array_trigger_array):
        """在单独线程中执行工作流 - 完全按照前端逻辑重写"""
        print(f"🚀 [WORKFLOW] 开始执行工作流: {workflow_id}")
        
        try:
            workflow_state = self.workflows[workflow_id]
            stop_event = self.stop_events[workflow_id]
            # 状态刷新节流：避免每个 item 都刷导致锁竞争
            last_state_flush_ts = 0.0
            # 运行期历史保存防抖标记：避免一次运行保存多份（异常、完成、兜底多处调用）
            saved_once = False
            saved_by_array = False
            
            # 复制数据，避免修改原始数据
            data_temp = copy.deepcopy(graph_data)
            nodes = data_temp.get("nodes", [])
            edges = data_temp.get("edges", [])
            
            # 检查是否有 passivityTrigger 和 ArrayTrigger 节点
            has_passivity_trigger = any(node.get("NodeKind", "").find("passivityTrigger") >= 0 for node in nodes)
            has_array_trigger = any(node.get("NodeKind", "").find("ArrayTrigger") >= 0 for node in nodes)

            # 早退：无任一触发器时，直接执行普通节点并完成
            if not has_passivity_trigger and not has_array_trigger:
                self._process_normal_nodes(data_temp, workflow_state)
                with self.lock:
                    # 运行结束，复位 IsBlock，便于前端进入编辑模式
                    self._reset_block_flags(data_temp)
                    workflow_state["graph_data"] = data_temp
                    workflow_state["last_update"] = time.time()
                    workflow_state["status"] = WorkflowStatus.COMPLETED
                # 完成后保存一次简单历史（仅 nodes）
                try:
                    self._save_simple_history(workflow_state["graph_data"])
                    saved_once = True
                except Exception:
                    pass
                return
            
            # 创建本地队列副本，避免线程冲突
            # 性能关键：用 deque 避免 list.pop(0) 的 O(n) 开销（几万条会变成 O(n^2)）
            local_passivity_array = deque(passivity_trigger_array or [])
            local_array_trigger_array = deque(array_trigger_array or [])
            workflow_state["pending_passivity_count"] = len(local_passivity_array)
            workflow_state["pending_array_count"] = len(local_array_trigger_array)
            self._refresh_parent_array_queue(workflow_id, len(local_array_trigger_array))
            # 仅预热一次的标记位
            did_preheat_passivity = False
            did_preheat_array = False
            # 记录自上次预热后是否出现过非空队列，用于"再次预热"
            had_non_empty_since_last_preheat = False
            # 被动触发器轮询节流时间戳
            last_passivity_pull_ts = 0.0

            # 🔥 关键修复：当图中存在 ArrayTrigger 节点时，清洗“来自前端的旧 array 队列”
            # 你遇到的现象（ArrayTrigger 一直 IDLE，但队列却被消费）往往是：
            # - array_trigger_array 里有占位项/历史残留（nodeId=None 或 nodeId 不属于当前图的 ArrayTrigger）
            # - 导致启动时 `not local_array_trigger_array` 为 False，从而跳过 ArrayTrigger 预热
            try:
                array_node_ids = set()
                if has_array_trigger:
                    for _n in (nodes or []):
                        if isinstance(_n, dict) and "ArrayTrigger" in str(_n.get("NodeKind", "")):
                            if _n.get("id"):
                                array_node_ids.add(_n.get("id"))

                if has_array_trigger and not has_passivity_trigger and isinstance(local_array_trigger_array, (list, deque)) and local_array_trigger_array:
                    before = len(local_array_trigger_array)
                    # 仅保留“由当前图的 ArrayTrigger 生成”的有效项：nodeId 命中且 outputData 非空
                    filtered = []
                    for it in local_array_trigger_array:
                        if not isinstance(it, dict):
                            continue
                        nid = it.get("nodeId")
                        if nid in array_node_ids and it.get("outputData") is not None:
                            filtered.append(it)
                    # 如果过滤后为空，但原队列非空 → 说明是旧队列/占位项，必须清空并强制预热
                    if len(filtered) == 0 and before > 0:
                        self._log_event(workflow_id, f"🧹 [ARRAY:SANITIZE] drop stale array_queue (before={before}) → force preheat ArrayTrigger")
                        if hasattr(local_array_trigger_array, "clear"):
                            local_array_trigger_array.clear()
                        else:
                            local_array_trigger_array = []
                        workflow_state["pending_array_count"] = 0
                        self._refresh_parent_array_queue(workflow_id, 0)
                    elif len(filtered) != before:
                        self._log_event(workflow_id, f"🧹 [ARRAY:SANITIZE] shrink array_queue {before} -> {len(filtered)}")
                        if hasattr(local_array_trigger_array, "clear"):
                            local_array_trigger_array.clear()
                            local_array_trigger_array.extend(filtered)
                        else:
                            local_array_trigger_array = filtered
                        workflow_state["pending_array_count"] = len(local_array_trigger_array)
                        self._refresh_parent_array_queue(workflow_id, len(local_array_trigger_array))
            except Exception:
                pass
            
            # 如果没有初始数据，优先预热 passivityTrigger（与JS一致）
            if not local_passivity_array and has_passivity_trigger:
                self._run_passivity_trigger_nodes(workflow_id, data_temp, local_passivity_array)
                did_preheat_passivity = True
            elif not local_array_trigger_array and has_array_trigger and not has_passivity_trigger:
                # 仅在不存在 passivityTrigger 时，预热 ArrayTrigger
                self._run_array_trigger_nodes(workflow_id, data_temp, local_array_trigger_array)
                did_preheat_array = True
            
            # 主执行循环 - 模拟前端的 setInterval 逻辑
            current_time = time.strftime('%H:%M:%S')
            loop_msg = f"📋 [LOOP] Pq={len(local_passivity_array)} Aq={len(local_array_trigger_array)} status={workflow_state['status']} time={current_time}"
            if getattr(self, "DEBUG_PRINT", False):
                print(loop_msg)
            self._log_event(workflow_id, loop_msg)
            while workflow_state["status"] == WorkflowStatus.RUNNING:
                did_work = False
                
                # 检查是否应该停止
                if stop_event.is_set():
                    workflow_state["status"] = WorkflowStatus.STOPPED
                    break
                
                # 检查是否暂停
                while workflow_state["status"] == WorkflowStatus.PAUSED:
                    time.sleep(0.5)
                    if stop_event.is_set():
                        workflow_state["status"] = WorkflowStatus.STOPPED
                        break
                
                # 1. 先处理 ArrayTrigger 队列（防止被 Passivity 持续填充时"饿死"）
                if local_array_trigger_array:
                    before_len = len(local_array_trigger_array)
                    msg = f"🔴 [ARRAY] size={before_len}"
                    if getattr(self, "DEBUG_PRINT", False):
                        print(msg)
                    self._log_event(workflow_id, msg)
                    if getattr(self, "DEBUG_PRINT", False):
                        print(f"[ARRAY-DEBUG] 处理前 ArrayTrigger 队列长度: {before_len}")
                    try:
                        preview = list(islice(local_array_trigger_array, 0, 3))
                        if getattr(self, "DEBUG_PRINT", False):
                            print(f"[ARRAY-DEBUG] 队列内容预览: {[item.get('nodeId', 'unknown') for item in preview]}")
                    except Exception:
                        pass

                    # ✅ 每轮最多处理 ENQUEUE_BURST 个 array 项（默认 5）
                    processed = 0
                    while local_array_trigger_array and processed < ENQUEUE_BURST:
                        len_before_one = len(local_array_trigger_array)
                        self._process_next_array_trigger(workflow_id, data_temp, local_array_trigger_array, workflow_state)
                        processed += 1
                        len_after_one = len(local_array_trigger_array)

                        # 状态刷新节流（默认 300ms）
                        now = time.time()
                        if (now - last_state_flush_ts) >= STATE_FLUSH_INTERVAL:
                            self._update_workflow_state(workflow_id, data_temp, local_array_trigger_array=local_array_trigger_array)
                            last_state_flush_ts = now

                        # 如果本次调用没有消耗队列（例如并行满负荷导致直接 return），避免同一轮内空转多次
                        if len_after_one == len_before_one:
                            break

                    after_len = len(local_array_trigger_array)
                    if getattr(self, "DEBUG_PRINT", False):
                        print(f"[ARRAY-DEBUG] 处理后 ArrayTrigger 队列长度: {after_len} (处理了 {before_len - after_len} 个)")

                    # 本轮结束强制刷一次，避免节流导致前端长时间看不到变化
                    self._update_workflow_state(workflow_id, data_temp, local_array_trigger_array=local_array_trigger_array)
                    last_state_flush_ts = time.time()

                    did_work = True
                    had_non_empty_since_last_preheat = True

                # 2. 再处理 Passivity（它可能继续向 Array 队列投喂数据）
                elif local_passivity_array:
                    msg = f"🔵 [PASSIVITY] size={len(local_passivity_array)}"
                    if getattr(self, "DEBUG_PRINT", False):
                        print(msg)
                    self._log_event(workflow_id, msg)
                    # 取出数据但先不从队列中移除，保持队列长度不变
                    passivity_data = local_passivity_array[0]
                    self._log_event(workflow_id, f"   └─ pass keys={list(passivity_data.keys()) if isinstance(passivity_data, dict) else type(passivity_data)}")
                    
                    # 找到对应的 passivityTrigger 节点
                    passivity_node = None
                    if passivity_data.get("nodeId"):
                        passivity_node = next((n for n in nodes if n["id"] == passivity_data["nodeId"]), None)
                    else:
                        passivity_node = next((n for n in nodes if "passivityTrigger" in n.get("NodeKind", "")), None)
                    
                    # ✅ 支持 tick-only passivityTrigger（无 Outputs）
                    # - tick=True：只触发 ArrayTrigger 链路（不走“无 ArrayTrigger → run normal nodes”兜底）
                    # - 旧行为保持：仍然仅当 outputData truthy 时才进行路由
                    is_tick = isinstance(passivity_data, dict) and passivity_data.get("tick") is True
                    if passivity_node and (is_tick or passivity_data.get("outputData")):
                        # 使用克隆图在本地处理，避免污染全局
                        local_data_for_pass = copy.deepcopy(data_temp)
                        self._log_event(workflow_id, "🎯 [PASS] 使用克隆图处理当前队列项")
                        if is_tick:
                            # tick-only：不做节点路由（无 outputData），但仍按“标准逻辑”触发：
                            # - 有 ArrayTrigger：入队遍历项
                            # - 无 ArrayTrigger：入队 graph_data 占位项，后续会触发普通节点执行
                            self._log_event(workflow_id, "⏰ [PASS:TICK] trigger workflow (ArrayTrigger if exists, else normal nodes)")
                            self._load_array_trigger_array(workflow_id, local_data_for_pass, local_array_trigger_array)
                            self._log_event(workflow_id, f"   └─ after loadArrayTriggerArray(tick) → Aq={len(local_array_trigger_array)}")
                            # 即时更新数组队列长度（不覆盖 graph_data，仅更新队列长度时间戳）
                            self._update_workflow_state(workflow_id, None, local_array_trigger_array=local_array_trigger_array)
                        else:
                            # 处理节点连接（等同于前端的 processNodeConnections）
                            processed_data = self._process_node_connections(local_data_for_pass, passivity_node, passivity_data.get("outputData"), workflow_id)
                            # 加载 ArrayTriggerArray（等同于前端的 loadArrayTriggerArray）
                            self._load_array_trigger_array(workflow_id, processed_data, local_array_trigger_array)
                            self._log_event(workflow_id, f"   └─ loadArrayTriggerArray → Aq={len(local_array_trigger_array)}")
                            # 即时更新数组队列长度（不覆盖 graph_data，仅更新队列长度时间戳）
                            self._update_workflow_state(workflow_id, None, local_array_trigger_array=local_array_trigger_array)
                        # 最小改动：移除“立刻处理一次”加速，保证一轮只消耗一个项，便于前端采样
                        # if local_array_trigger_array:
                        #     self._process_next_array_trigger(workflow_id, data_temp, local_array_trigger_array, workflow_state)
                        #     self._log_event(workflow_id, f"   └─ immediate processNextArrayTrigger → Aq={len(local_array_trigger_array)}")
                    
                    # 数据处理完成后才从队列中移除
                    try:
                        local_passivity_array.popleft()
                    except Exception:
                        # 兜底：兼容旧 list
                        local_passivity_array.pop(0)
                    
                    # 设置本轮固定指纹（避免同一轮内指纹随状态变化）
                    import hashlib
                    # 为passivity trigger生成标识
                    item_tag = f"P:{workflow_id}:{int(time.time())}"
                    workflow = self.workflows[workflow_id]
                    workflow["round_id"] = item_tag
                    
                    # 为本轮生成稳定指纹（与状态变化解耦）
                    fixed = f"{workflow_id}:{item_tag}"
                    workflow["ring_fingerprint"] = hashlib.sha1(fixed.encode("utf-8")).hexdigest()
                    # 也可写回给前端备用
                    workflow["graph_data"]["fingerprint"] = workflow["ring_fingerprint"]
                    
                    # 更新工作流状态（更新队列长度）
                    # 更新队列长度（不覆盖 graph_data）
                    self._update_workflow_state(workflow_id, None, local_passivity_array, local_array_trigger_array)
                    self._log_event(workflow_id, f"   └─ POP → Pq={len(local_passivity_array)} Aq={len(local_array_trigger_array)}")
                    did_work = True
                    had_non_empty_since_last_preheat = True
                    
                # 3. 如果没有passivity数据但有passivityTrigger节点，且尚未预热过，则预热一次
                elif (not local_passivity_array) and has_passivity_trigger and (not did_preheat_passivity):
                    msg = f"🟡 [TRIGGER] 运行被动触发节点 (预热)"
                    if getattr(self, "DEBUG_PRINT", False):
                        print(msg)
                    self._log_event(workflow_id, msg)
                    self._run_passivity_trigger_nodes(workflow_id, data_temp, local_passivity_array)
                    did_preheat_passivity = True
                    did_work = True
                
                # 4. 若两个队列都为空
                elif not local_passivity_array and not local_array_trigger_array:
                    if self._has_active_children(workflow_id):
                        self._log_event(workflow_id, "🟢 [CHILD] 等待子工作流完成...")
                        time.sleep(0.05)
                        continue
                    if has_passivity_trigger:
                        # 队列皆空且存在被动触发器 → 周期性再次拉取（轮询），节流 1s
                        now_ts = time.time()
                        if (now_ts - last_passivity_pull_ts) >= 1.0:
                            self._log_event(workflow_id, "🟡 [POLL] 触发 passivityTrigger 拉取")
                            self._run_passivity_trigger_nodes(workflow_id, data_temp, local_passivity_array)
                            last_passivity_pull_ts = now_ts
                            # 更新队列长度（不覆盖 graph_data）
                            self._update_workflow_state(workflow_id, None, local_passivity_array, local_array_trigger_array)
                            did_work = True
                        else:
                            self._log_event(workflow_id, "🟡 [WAITING] 已预热，等待新数据...")
                    else:
                        self._log_event(workflow_id, "✅ [COMPLETE] 所有队列为空，工作流完成")
                        # 运行结束，复位 IsBlock，便于前端进入编辑模式
                        try:
                            self._reset_block_flags(workflow_state["graph_data"])
                        except Exception:
                            pass
                        workflow_state["status"] = WorkflowStatus.COMPLETED
                        # 完成后保存一次简单历史（仅 nodes）
                        if not saved_by_array:
                            try:
                                self._save_simple_history(workflow_state["graph_data"])
                                saved_once = True
                            except Exception:
                                pass
                        break
                
                # 检查停止信号（在每次循环中检查）
                if stop_event.is_set():
                    workflow_state["status"] = WorkflowStatus.STOPPED
                    break
                
                # ✅ 仅空转等待才慢睡；有活就轻微让出时间片
                if did_work:
                    time.sleep(0.001)  # 或 0
                    workflow_state["last_update"] = time.time()
                else:
                    time.sleep(0.3)
        
        except Exception as e:
            # 保留关键错误日志
            print(f"[DEBUG] 工作流执行错误: {workflow_id} - {str(e)}")
            print(f"[DEBUG] 完整错误堆栈:")
            print(traceback.format_exc())
            
            # 尝试更新工作流状态
            try:
                if workflow_id in self.workflows and self.workflows[workflow_id] is not None:
                    workflow_state["status"] = WorkflowStatus.ERROR
                    workflow_state["error"] = str(e)
                    workflow_state["traceback"] = traceback.format_exc()
                    # 错误时也保存一次历史（仅 nodes）
                    try:
                        self._save_simple_history(workflow_state.get("graph_data"))
                        saved_once = True
                    except Exception:
                        pass
                else:
                    print(f"[DEBUG] 无法更新工作流状态，workflow_state 不存在或为None")
            except Exception as update_error:
                print(f"[DEBUG] 更新工作流状态时出错: {update_error}")
        
        finally:
            # 清理资源
            if workflow_id in self.stop_events:
                del self.stop_events[workflow_id]
            
            # 确保工作流状态被正确标记为完成或错误
            status_for_cleanup = None
            with self.lock:
                if workflow_id in self.workflows and self.workflows[workflow_id] is not None:
                    if self.workflows[workflow_id]["status"] == WorkflowStatus.RUNNING:
                        # 兜底：线程自然结束但状态仍为 RUNNING，视为完成并复位 IsBlock
                        try:
                            self._reset_block_flags(self.workflows[workflow_id].get("graph_data"))
                        except Exception:
                            pass
                        self.workflows[workflow_id]["status"] = WorkflowStatus.COMPLETED
                        try:
                            self.workflows[workflow_id]["done_ts"] = time.time()
                        except Exception:
                            pass
                    # 最后兜底保存一次：
                    # - 仅针对“普通工作流”（没有 passivity / ArrayTrigger）
                    # - 避免在数组模式下多出一条“父级总览”，保证“按条数保存”的直觉一致
                    if not saved_once and not saved_by_array and not has_passivity_trigger and not has_array_trigger:
                        try:
                            self._save_simple_history(self.workflows[workflow_id].get("graph_data"))
                        except Exception:
                            pass
                    status_for_cleanup = self.workflows[workflow_id].get("status")
            if status_for_cleanup in (WorkflowStatus.COMPLETED, WorkflowStatus.ERROR, WorkflowStatus.STOPPED):
                self._schedule_workflow_cleanup(workflow_id, delay=5.0)
            # runtime cleanup (must)
            try:
                self._flush_history_buffer_for_workflow(workflow_id)
            except Exception:
                pass
            try:
                self._runtime_cleanup(workflow_id)
            except Exception:
                pass
    
    def _run_passivity_trigger_nodes(self, workflow_id, data_temp, passivity_trigger_array):
        """运行 passivityTrigger 节点（模拟前端 runPassivityTriggerNodes）"""
        nodes = data_temp.get("nodes", [])
        passivity_nodes = [node for node in nodes if "passivityTrigger" in node.get("NodeKind", "")]
        print(f"🟡 [TRIGGER] 发现 {len(passivity_nodes)} 个 passivityTrigger 节点 → 开始执行")
        
        count = 0
        for node in passivity_nodes:
            try:
                msg = f"🟡 [TRIGGER] 执行节点: {node.get('label', node.get('id'))}"
                print(msg)
                self._log_event(workflow_id, msg)
                
                # 处理节点输入（与前端 getNodeInputs 保持一致）
                inputs = self._process_node_inputs(node)
                self._log_event(workflow_id, f"   └─ inputs={inputs}")
                
                # 标记运行中并推送状态
                self._update_node_status(data_temp, node["id"], {"IsRunning": True, "IsError": False})
                self._update_workflow_state(workflow_id, data_temp)
                
                # 直接使用现有的节点执行逻辑，但确保正确处理 passivityTrigger
                processed_node = self._process_node(node)
                self._log_event(workflow_id, f"   └─ node={processed_node.get('name')} kind={processed_node.get('NodeKind')}")
                # 启用仅 TRACE 打印
                self._install_trace_filter()
                result = self._execute_node(processed_node, workflow_id=str(workflow_id))
                
                self._log_event(workflow_id, f"   └─ result.count={(len(result.get('output')) if isinstance(result, dict) and isinstance(result.get('output'), list) else ('1' if isinstance(result, dict) and result.get('output') is not None else 0))}")
                
                # 写回 debug
                if isinstance(result, dict):
                    node["debug"] = self._cap_node_debug(result.get("debug", ""))
                
                # 更新节点输出（包括 token 信息）
                if isinstance(result, dict) and result.get("output") is not None:
                    for idx, output in enumerate(result["output"] if isinstance(result["output"], list) else [result["output"]]):
                        if idx < len(node.get("Outputs", [])):
                            port_kind = node["Outputs"][idx].get("Kind", "")
                            normalized = self._normalize_output_for_port(output, port_kind)
                            node["Outputs"][idx].update(normalized)
                    
                    # 更新第一条输出的 token 信息
                    out_list = result["output"] if isinstance(result["output"], list) else [result["output"]]
                    if len(out_list) > 0 and len(node.get("Outputs", [])) > 0:
                        first_output = out_list[0]
                        if isinstance(first_output, dict):
                            token_fields = ["prompt_tokens", "completion_tokens", "total_tokens"]
                            for field in token_fields:
                                if field in first_output:
                                    node["Outputs"][0][field] = first_output[field]

                    # Cap stored output contexts (UI/state only)
                    self._cap_output_context_in_place(node.get("Outputs", []))
                
                # 运行完成，更新状态
                self._update_node_status(data_temp, node["id"], {"IsRunning": False, "isFinish": True, "IsError": False, "ErrorContext": ""})
                self._update_workflow_state(workflow_id, data_temp)
                
                # 添加历史记录
                print(f"📝 [PASSIVITY-COMPLETE] 被动触发节点完成: {node.get('label', node.get('id'))}")
                print(f"📝 [PASSIVITY-COMPLETE] 输出数量: {len(result.get('output', [])) if isinstance(result, dict) else 0}")
                self._add_history(workflow_id, node)

                # ✅ 支持“无 Output 的定时触发型 passivityTrigger”
                # 语义：该节点本身只负责“tick”，不携带 outputData；
                # 后续在主循环中识别 tick 并仅触发 ArrayTrigger 链路。
                try:
                    if isinstance(node.get("Outputs", []), list) and len(node.get("Outputs", [])) == 0:
                        # 仅当节点脚本明确返回 tick=True 时才入队，避免轮询时每秒强制触发
                        fired = False
                        try:
                            outs = result.get("output") if isinstance(result, dict) else None
                            if isinstance(outs, dict):
                                fired = outs.get("tick") is True
                            elif isinstance(outs, list):
                                for it in outs:
                                    if isinstance(it, dict) and it.get("tick") is True:
                                        fired = True
                                        break
                        except Exception:
                            fired = False

                        if not fired:
                            self._log_event(workflow_id, f"⏳ [TICK] passivityTrigger(no-outputs) not due → skip enqueue node={node.get('label', node.get('id'))}")
                            continue

                        item = {
                            "outputData": None,
                            "nodeId": node.get("id"),
                            "tick": True,
                            "ts": time.time(),
                        }
                        passivity_trigger_array.append(item)
                        self._log_event(workflow_id, f"⏰ [TICK] passivityTrigger(no-outputs) enqueue → Pq={len(passivity_trigger_array)} node={node.get('label', node.get('id'))}")
                        # 刷新队列长度，前端可见
                        self._update_workflow_state(workflow_id, data_temp, local_passivity_array=passivity_trigger_array)
                        continue
                except Exception:
                    pass

                # 修复：正确处理 None 输出和空输出
                outputs = result.get("output") if isinstance(result, dict) else None
                
                # 🎯🎯🎯 检查是否为有效输出 🎯🎯🎯
                has_valid_output = False
                if outputs is not None:
                    if isinstance(outputs, list):
                        # 检查列表中是否有非 None 项
                        has_valid_output = any(item is not None for item in outputs)
                        self._log_event(workflow_id, f"🎯🎯🎯 [OUTPUT-CHECK] 输出列表: {outputs}, 有效输出: {has_valid_output}")
                    else:
                        # 单个输出且不为 None
                        has_valid_output = True
                        self._log_event(workflow_id, f"🎯🎯🎯 [OUTPUT-CHECK] 单个输出: {outputs}, 有效输出: {has_valid_output}")
                else:
                    self._log_event(workflow_id, f"🎯🎯🎯 [OUTPUT-CHECK] 输出为 None，无有效输出")
                
                if has_valid_output:
                    self._log_event(workflow_id, f"✅ passivityTrigger 输出 count={len(outputs) if isinstance(outputs, list) else 1}")
                    
                    # 🎯🎯🎯 添加特殊标识符显示 passivityTrigger 的具体输出内容 🎯🎯🎯
                    self._log_event(workflow_id, f"🎯🎯🎯 [PASSIVITY-OUTPUT] passivityTrigger 详细输出:")
                    if isinstance(outputs, list):
                        for i, item in enumerate(outputs):
                            self._log_event(workflow_id, f"🎯🎯🎯 [PASSIVITY-OUTPUT] 第{i+1}项: {item}")
                            if isinstance(item, list) and len(item) > 0:
                                for j, sub_item in enumerate(item):
                                    if isinstance(sub_item, dict) and 'Context' in sub_item:
                                        self._log_event(workflow_id, f"🎯🎯🎯 [PASSIVITY-OUTPUT]   └─ 输出{j+1}.Context: {sub_item['Context']}")
                                        self._log_event(workflow_id, f"🎯🎯🎯 [PASSIVITY-OUTPUT]   └─ 输出{j+1}.name: {sub_item.get('name', 'N/A')}")
                                    else:
                                        self._log_event(workflow_id, f"🎯🎯🎯 [PASSIVITY-OUTPUT]   └─ 输出{j+1}: {sub_item}")
                    else:
                        self._log_event(workflow_id, f"🎯🎯🎯 [PASSIVITY-OUTPUT] 非列表输出: {outputs}")
                    self._log_event(workflow_id, f"🎯🎯🎯 [PASSIVITY-OUTPUT] passivityTrigger 输出结束 🎯🎯🎯")
                    
                    # 启动 TRACE 会话
                    try:
                        self._trace_start(workflow_id, node, (len(outputs) if isinstance(outputs, list) else 1))
                    except Exception:
                        pass

                    # 加载到 passivityTriggerArray（模拟前端 LoadInPassivityTriggerArray）
                    self._load_in_passivity_trigger_array(workflow_id, data_temp, result, node, passivity_trigger_array)
                    self._log_event(workflow_id, f"   └─ after load → Pq={len(passivity_trigger_array)}")
                else:
                    self._log_event(workflow_id, f"⚠️ [WARNING] passivityTrigger 节点没有生成有效输出，跳过处理")
                    
            except Exception as e:
                print(f"❌ [ERROR] PassivityTrigger 节点执行失败: {e}")
                import traceback
                print(f"🔍 [TRACEBACK] {traceback.format_exc()}")
                self._update_node_status(data_temp, node["id"], {"IsRunning": False, "IsError": True, "ErrorContext": str(e)})
                self._update_workflow_state(workflow_id, data_temp)
            finally:
                # 恢复 stdout
                self._restore_stdout()
    
    def _load_in_passivity_trigger_array(self, workflow_id, data_temp, result, trigger_node, passivity_trigger_array):
        """加载数据到 passivityTriggerArray（模拟前端 LoadInPassivityTriggerArray）"""
        output_list = result.get("output", []) or []

        # 兼容两种形态：
        # 1) list[list[dict]] → 已按“组”拆好
        # 2) list[dict]       → 单组端口列表（需要包一层，避免把端口数当作组数）
        if isinstance(output_list, list) and output_list and all(isinstance(x, dict) for x in output_list):
            grouped_outputs = [output_list]
        else:
            grouped_outputs = output_list

        filtered_outputs = [x for x in grouped_outputs if x is not None]
        try:
            if getattr(self, "DEBUG_PRINT", False):
                print(f"🎯🎯🎯 [PASSIVITY-LOAD] 原始输出结构: {type(output_list)} → 归一化后组数={len(filtered_outputs)}")
        except Exception:
            pass
        if not filtered_outputs:
            if getattr(self, "DEBUG_PRINT", False):
                print(f"🎯🎯🎯 [PASSIVITY-LOAD] 没有有效输出，跳过入队")
            return

        node_id = trigger_node["id"]
        key = (workflow_id, node_id)
        enqueued = 0

        # 期望：list[list[dict]]，每个子数组是一条“消息组”
        for idx, group in enumerate(filtered_outputs):
            if group is None:
                continue
            normalized_group = group if isinstance(group, list) else [group]

            fp = self._calc_fp(node_id, normalized_group)
            last_fp = self._last_ring_fp.get(key)

            item = {"outputData": copy.deepcopy(normalized_group), "nodeId": node_id}

            if last_fp == fp:
                replaced = False
                for i in range(len(passivity_trigger_array) - 1, -1, -1):
                    if passivity_trigger_array[i].get("nodeId") == node_id:
                        passivity_trigger_array[i] = item
                        if getattr(self, "DEBUG_PRINT", False):
                            print("🌀 [RING:OVERWRITE] Passivity 覆盖上一条记录 (相同指纹)")
                        replaced = True
                        break
                if not replaced:
                    passivity_trigger_array.append(item)
                    if getattr(self, "DEBUG_PRINT", False):
                        print("✅ [RING:PUSH] Passivity 覆盖失败，退化为新增记录到环")
            else:
                passivity_trigger_array.append(item)
                self._last_ring_fp[key] = fp
                # cache bookkeeping
                try:
                    self._mark_cache_touch("_last_ring_fp", key)
                    self._prune_cache_if_needed()
                except Exception:
                    pass
                if getattr(self, "DEBUG_PRINT", False):
                    print(f"✅ [RING:PUSH] Passivity 入队消息组 {idx+1}/{len(filtered_outputs)}")
            enqueued += 1

        if getattr(self, "DEBUG_PRINT", False):
            print(f"🎯🎯🎯 [PASSIVITY-LOAD] 共入队 {enqueued} 组")
        self._update_workflow_state(workflow_id, data_temp, local_passivity_array=passivity_trigger_array)
    
    def _load_array_trigger_array(self, workflow_id, passivity_data, array_trigger_array):
        """使用 passivityData 加载 ArrayTriggerArray（调用前端 loadArrayTriggerArray）"""
        self._log_event(workflow_id, "▶️ loadArrayTriggerArray")
        
        data_temp = copy.deepcopy(passivity_data)
        has_array_trigger = any("ArrayTrigger" in node.get("NodeKind", "") for node in data_temp.get("nodes", []))
        self._log_event(workflow_id, f"   └─ hasArrayTrigger={has_array_trigger}")
        
        if has_array_trigger:
            # 后端处理 ArrayTrigger（前端会在 LoadInPassivityTriggerArray 中调用 loadArrayTriggerArray）
            if getattr(self, "DEBUG_PRINT", False):
                print(f"[ARRAY-DEBUG] 后端处理 ArrayTrigger，数据节点数: {len(data_temp.get('nodes', []))}")
            self._run_array_trigger_nodes_in_passivity_trigger_array(workflow_id, data_temp, array_trigger_array)
        else:
            # 修复：不应该直接添加 data_temp，而是添加包含 nodeId 和 outputData 的对象
            # 但是这种情况下我们没有具体的 nodeId，所以设置为 None，让 _process_next_array_trigger 直接处理
            array_trigger_array.append({
                "outputData": None,  # 没有具体的输出数据
                "nodeId": None,      # 没有具体的节点ID
                "graph_data": data_temp  # 保存完整的图数据用于直接处理
            })
            self._log_event(workflow_id, "   └─ no ArrayTrigger → push graph_data")
    
    def _run_array_trigger_nodes_in_passivity_trigger_array(self, workflow_id, data_temp, array_trigger_array):
        """运行 ArrayTrigger 节点（在 passivityTrigger 处理中）"""
        self._log_event(workflow_id, "🔴 [DEBUG] _run_array_trigger_nodes_in_passivity_trigger_array 被调用")
        nodes = data_temp.get("nodes", [])
        edges = data_temp.get("edges", [])
        count = 0
        
        # 第一阶段：找到 ArrayTrigger 节点
        array_trigger_nodes = [node for node in nodes if "ArrayTrigger" in node.get("NodeKind", "")]
        self._log_event(workflow_id, f"🔴 [DEBUG] 找到 {len(array_trigger_nodes)} 个 ArrayTrigger 节点")
        for node in array_trigger_nodes:
            self._log_event(workflow_id, f"🔴 [DEBUG] ArrayTrigger 节点: {node.get('label', node.get('id'))} kind={node.get('NodeKind')}")
        
        # 🔥 关键修复：使用统一的辅助函数执行上游普通节点
        # 这样可以支持 Normal → ArrayTrigger 和 passivityTrigger + Normal → ArrayTrigger 两种架构
        if array_trigger_nodes:
            self._log_event(workflow_id, "🔴 [DEBUG] 执行 ArrayTrigger 的上游普通节点（支持 Normal → ArrayTrigger）")
            self._execute_upstream_normal_nodes_for_array_trigger(workflow_id, data_temp, array_trigger_nodes)
        
        # 第二阶段：找到连接到 ArrayTrigger 节点的上游节点（保留原有逻辑用于兼容性，但主要依赖上面的辅助函数）
        connect_edges = [
            edge for edge in edges
            if any(node["id"] == edge["target"] for node in array_trigger_nodes)
        ]
        connect_nodes = [
            next((node for node in nodes if node["id"] == edge["source"]), None)
            for edge in connect_edges
        ]
        # 关键改动：过滤掉 None 和 passivityTrigger 节点，避免重复执行 passivityTrigger
        connect_nodes = [
            node for node in connect_nodes
            if node is not None and "passivityTrigger" not in node.get("NodeKind", "")
        ]
        self._log_event(workflow_id, f"🔴 [DEBUG] 找到 {len(connect_nodes)} 个直接连接的上游节点（已通过辅助函数处理）")
        
        # 第三阶段：处理所有上游节点（保留原有逻辑作为兜底，但主要逻辑已在辅助函数中完成）
        # 注意：如果辅助函数已经执行了所有上游节点，这里可能不会执行（因为节点状态已更新）
        self._log_event(workflow_id, f"🔴 [DEBUG] 开始处理剩余的上游节点（如有）")
        
        # 🎯🎯🎯 显示 passivity 数据传递给 ArrayTrigger 的过程 🎯🎯🎯
        current_passivity_item = None
        if hasattr(self, 'current_passivity_data'):
            current_passivity_item = getattr(self, 'current_passivity_data', None)
            self._log_event(workflow_id, f"🎯🎯🎯 [P→A-TRANSFER] 当前传递给ArrayTrigger的passivity数据: {current_passivity_item}")
        
        for node in connect_nodes:
            self._log_event(workflow_id, f"🔴 [DEBUG] 进入上游节点循环: {node.get('label', node.get('id'))}")
            try:
                # 标记运行中（仅本地数据）
                self._update_node_status(data_temp, node["id"], {"IsRunning": True, "IsError": False})
                
                # 构建 ExprotAfterPrompt（如果为空）
                if not node.get("ExprotAfterPrompt"):
                    temp = 'Please ensure the output is in JSON format\n{\n'
                    for output in node.get("Outputs", []):
                        kind = output.get("Kind", "")
                        temp += f'"{output.get("Id", "")}": "{output.get("Description", "")}" (you need output type: {kind})\n'
                    temp += '}\n'
                    node["ExprotAfterPrompt"] = temp
                
                self._log_event(workflow_id, f"🔴 [DEBUG] 处理上游节点: {node.get('label', node.get('id'))}")
                
                # 处理 LLM 提示词
                if node.get("NodeKind", "").lower() == "llm":
                    # 仅在本次执行中生成提示词，避免写回覆盖
                    _ = self._process_llm_prompt(node)
                
                # 执行节点
                processed_node = self._process_node(node)
                result = self._execute_node(processed_node, workflow_id=str(workflow_id))
                self._log_event(workflow_id, f"🔴 [DEBUG] 上游节点结果: {result}")
                # 检查是否有有效输出用于传递给下游
                if isinstance(result, dict) and result.get("output") and result["output"] != [None]:
                    self._log_event(workflow_id, f"🔴 [DEBUG] 上游节点有有效输出，将传播给下游")
                else:
                    self._log_event(workflow_id, f"🔴 [DEBUG] 上游节点无有效输出，ArrayTrigger将收不到数据")
                
                # 写回 debug
                if isinstance(result, dict):
                    node["debug"] = self._cap_node_debug(result.get("debug", ""))
                
                # 更新节点输出（包括 token 信息）
                if isinstance(result, dict) and result.get("output") is not None:
                    for idx, output in enumerate(result["output"] if isinstance(result["output"], list) else [result["output"]]):
                        if idx < len(node.get("Outputs", [])):
                            port_kind = node["Outputs"][idx].get("Kind", "")
                            normalized = self._normalize_output_for_port(output, port_kind)
                            node["Outputs"][idx].update(normalized)
                    
                    # 更新第一条输出的 token 信息
                    out_list = result["output"] if isinstance(result["output"], list) else [result["output"]]
                    if len(out_list) > 0 and len(node.get("Outputs", [])) > 0:
                        first_output = out_list[0]
                        if isinstance(first_output, dict):
                            token_fields = ["prompt_tokens", "completion_tokens", "total_tokens"]
                            for field in token_fields:
                                if field in first_output:
                                    node["Outputs"][0][field] = first_output[field]

                    # Cap stored output contexts (UI/state only)
                    self._cap_output_context_in_place(node.get("Outputs", []))
                
                # 运行完成（仅本地数据）
                self._update_node_status(data_temp, node["id"], {"IsRunning": False, "isFinish": True, "IsError": False, "ErrorContext": ""})
                
                outputs = result.get("output", []) if isinstance(result, dict) else []
                if outputs:
                    # 传播输出到下游节点（后端风格：仅按本次 outputs，按 offset 路由）
                    for edge in edges:
                        if edge["source"] == node["id"]:
                            target_nodes = [n for n in nodes if n["id"] == edge["target"]]
                            for target_node in target_nodes:
                                offset = edge["sourceAnchor"] - len(node.get("Inputs", []))
                                if offset < 0 or offset >= len(outputs):
                                    continue
                                output_item = outputs[offset] or {}
                                if not isinstance(output_item, dict):
                                    output_item = self._coerce_to_dict(output_item) or {}
                                target_idx = edge["targetAnchor"]
                                if target_idx < len(target_node.get("Inputs", [])):
                                    input_item = target_node["Inputs"][target_idx]
                                    # 跨类型转换
                                    ik = input_item.get("Kind", "")
                                    conv_in = self._convert_between_kinds(output_item, ik)
                                    if ik == "Num":
                                        input_item["Num"] = conv_in.get("Num")
                                    elif ik == "Boolean":
                                        input_item["Boolean"] = conv_in.get("Boolean")
                                    elif "String" in ik:
                                        input_item["Context"] = conv_in.get("Context")
                                    # 标记就绪
                                    if "inputStatus" not in target_node:
                                        target_node["inputStatus"] = [False] * len(target_node.get("Inputs", []))
                                    target_node["inputStatus"][target_idx] = True
            except Exception as e:
                # 保留错误日志用于调试
                print(f"处理上游节点时出错: {e}")
                self._update_node_status(data_temp, node["id"], {"IsRunning": False, "IsError": True, "ErrorContext": str(e)})
            finally:
                try:
                    self._trace_node(node)
                except Exception:
                    pass
        
        # 第四阶段：处理 ArrayTrigger 节点
        for node in array_trigger_nodes:
            try:
                self._log_event(workflow_id, f"🔴 [DEBUG] 开始执行 ArrayTrigger 节点: {node.get('label', node.get('id'))}")
                
                # 标记运行中（仅本地数据）
                self._update_node_status(data_temp, node["id"], {"IsRunning": True, "IsError": False})
                
                # 🔥 关键修复：执行前检查输入是否就绪（与预热场景保持一致）
                inputs_ready_min = True
                for inp in node.get("Inputs", []):
                    if inp.get("Isnecessary", False):
                        kind = inp.get("Kind", "")
                        if kind == "Num" and inp.get("Num") is None:
                            inputs_ready_min = False
                            self._log_event(workflow_id, f"⚠️ [PASSIVITY-ARRAY] ArrayTrigger 输入未就绪: {inp.get('name', '?')} (Num=None)")
                            break
                        if kind == "Boolean" and inp.get("Boolean") is None:
                            inputs_ready_min = False
                            self._log_event(workflow_id, f"⚠️ [PASSIVITY-ARRAY] ArrayTrigger 输入未就绪: {inp.get('name', '?')} (Boolean=None)")
                            break
                        if "String" in kind and (inp.get("Context") is None or inp.get("Context") == ""):
                            inputs_ready_min = False
                            self._log_event(workflow_id, f"⚠️ [PASSIVITY-ARRAY] ArrayTrigger 输入未就绪: {inp.get('name', '?')} (Context=None或空)")
                            break
                if not inputs_ready_min:
                    self._log_event(workflow_id, f"⏸️ [PASSIVITY-ARRAY] ArrayTrigger 输入未就绪，跳过执行: {node.get('label', node.get('id'))}")
                    self._update_node_status(data_temp, node["id"], {"IsRunning": False})
                    continue
                # 执行节点
                processed_node = self._process_node(node)
                self._log_event(workflow_id, f"🔴 [DEBUG] processed_node name: {processed_node.get('name')}")
                result = self._execute_node(processed_node, workflow_id=str(workflow_id))
                self._log_event(workflow_id, f"🔴 [DEBUG] execute_node result: {result}")
                
                # 写回 debug
                if isinstance(result, dict):
                    node["debug"] = self._cap_node_debug(result.get("debug", ""))
                
                # 更新节点输出（包括 token 信息）
                if isinstance(result, dict) and result.get("output") is not None:
                    for idx, output in enumerate(result["output"] if isinstance(result["output"], list) else [result["output"]]):
                        if idx < len(node.get("Outputs", [])):
                            port_kind = node["Outputs"][idx].get("Kind", "")
                            normalized = self._normalize_output_for_port(output, port_kind)
                            node["Outputs"][idx].update(normalized)
                    
                    # 更新第一条输出的 token 信息
                    out_list = result["output"] if isinstance(result["output"], list) else [result["output"]]
                    if len(out_list) > 0 and len(node.get("Outputs", [])) > 0:
                        first_output = out_list[0]
                        if isinstance(first_output, dict):
                            token_fields = ["prompt_tokens", "completion_tokens", "total_tokens"]
                            for field in token_fields:
                                if field in first_output:
                                    node["Outputs"][0][field] = first_output[field]

                    # Cap stored output contexts (UI/state only)
                    self._cap_output_context_in_place(node.get("Outputs", []))
                
                # 运行完成（仅本地数据）
                self._update_node_status(data_temp, node["id"], {"IsRunning": False, "isFinish": True, "IsError": False, "ErrorContext": ""})
                
                # 修复：与前端逻辑保持一致 - 检查 result.output 是否不为 None（而不是检查真值）
                if isinstance(result, dict) and result.get("output") is not None:
                    original_outputs = result.get("output") or []
                    # ===== 深度调试：记录原始 output 形状和每组内容摘要 =====
                    try:
                        raw = result.get("output")
                        raw_len = len(raw) if isinstance(raw, list) else 1
                        self._log_event(workflow_id, f"🔴 [ARRAY-TRACE] node={node.get('label', node.get('id'))} raw_type={type(raw)} raw_len={raw_len}")
                        if isinstance(raw, list):
                            for i, g in enumerate(raw):
                                if isinstance(g, list):
                                    self._log_event(workflow_id, f"   └─ raw[{i}] is list, size={len(g)}")
                                elif isinstance(g, dict):
                                    keys = list(g.keys())
                                    self._log_event(workflow_id, f"   └─ raw[{i}] is dict, keys={keys}")
                                else:
                                    self._log_event(workflow_id, f"   └─ raw[{i}] type={type(g)} value_preview={str(g)[:80]}")
                    except Exception:
                        pass
                    # === 形状归一化（最小修） ===
                    def _looks_like_output_slot(x):
                        return (
                            isinstance(x, dict)
                            and isinstance(x.get('Id'), str)
                            and x['Id'].startswith('Output')
                            and isinstance(x.get('name'), str)
                        )
                    # 不是列表 → 置空
                    if not isinstance(original_outputs, list):
                        original_outputs = []
                    # 如果 original_outputs 是“槽位字典的列表”，说明这其实是“一行”
                    # 自动包一层，使其成为单元素数组：[Outputs_row]
                    if original_outputs and all(_looks_like_output_slot(x) for x in original_outputs):
                        original_outputs = [original_outputs]
                        if getattr(self, "DEBUG_PRINT", False):
                            print("[ARRAY-DEBUG] 归一化：检测到单行的 Outputs，被包裹为 1 个数组元素")
                    # 归一化后再输出一遍统计信息（仅在 DEBUG_PRINT 时输出，避免入队阶段被事件日志拖慢）
                    if getattr(self, "DEBUG_PRINT", False):
                        try:
                            self._log_event(workflow_id, f"🔴 [ARRAY-TRACE] 标准化后组数(original_outputs.len) = {len(original_outputs)}")
                            for gi, g in enumerate(original_outputs):
                                if isinstance(g, list):
                                    ids = []
                                    for it in g:
                                        if isinstance(it, dict):
                                            ids.append(it.get('Id') or it.get('name'))
                                    self._log_event(workflow_id, f"   └─ group[{gi}] size={len(g)} ids={ids}")
                                else:
                                    self._log_event(workflow_id, f"   └─ group[{gi}] type={type(g)} value_preview={str(g)[:80]}")
                        except Exception:
                            pass
                        try:
                            self._log_event(workflow_id, f"🔴 [DEBUG] ArrayTrigger 原始输出数量: {len(original_outputs)}")
                        except Exception:
                            pass
                    
                    # 性能关键：每批输出只冻结一次 graph 快照，避免每条队列项都 deepcopy 整张图
                    shared_graph_snapshot = None
                    if WF_QUEUE_STORE_GRAPH_SNAPSHOT:
                        try:
                            shared_graph_snapshot = copy.deepcopy(data_temp)
                        except Exception:
                            shared_graph_snapshot = data_temp
                    
                    # 🔥 关键修复：ArrayTrigger 的 output 是嵌套数组结构
                    # 每个子数组代表一个完整的输出组，应该作为一个队列项
                    # 入队统计（减少每条入队都写 events 抢锁）
                    enq_push = 0
                    enq_overwrite = 0
                    enq_empty_push = 0
                    enq_t0 = time.time()
                    for idx, array_group in enumerate(original_outputs):
                        if array_group is None:
                            continue
                        
                        node_id = node["id"]
                        # 性能关键：避免对每个 group 做 deepcopy（几万条会非常慢且占内存）
                        # group 在后续仅用于“本次路由”，允许被轻微规范化（Id/name），不影响其它项
                        group = array_group
                        fp = self._calc_fp(node_id, group)            # ← 新增
                        key = (workflow_id, node_id)
                        last_fp = self._last_ring_fp.get(key)
                        item = {"outputData": group, "nodeId": node_id}
                        if WF_QUEUE_STORE_GRAPH_SNAPSHOT and shared_graph_snapshot is not None:
                            item["graph_data"] = shared_graph_snapshot

                        # 性能优化：使用索引字典快速定位最后一个相同 nodeId 的项
                        # 注意：deque 支持 index 访问与赋值（O(n)），但仍远比 list(tmp)+clear+extend 省内存/更快
                        queue_index = self._array_queue_last_index.setdefault(workflow_id, {})
                        last_index = queue_index.get(node_id)
                        
                        if last_fp == fp and last_index is not None:
                            # 性能优化：从 last_index 开始向前查找（限制查找范围）
                            found = False
                            if last_index < len(array_trigger_array):
                                # 从 last_index 向前查找（更可能命中，减少遍历次数）
                                start_idx = min(last_index, len(array_trigger_array) - 1)
                                for j in range(start_idx, -1, -1):
                                    if array_trigger_array[j].get("nodeId") == node_id:
                                        # ✅ 真正覆盖：命中时原位替换（队列长度不变）
                                        try:
                                            array_trigger_array[j] = item
                                        except Exception:
                                            # 兜底：无法索引赋值时退化为重建（极少发生）
                                            tmp = list(array_trigger_array)
                                            tmp[j] = item
                                            array_trigger_array.clear()
                                            array_trigger_array.extend(tmp)
                                        queue_index[node_id] = j
                                        found = True
                                        enq_overwrite += 1
                                        break
                            if not found:
                                # 索引失效或未找到，从末尾重新查找
                                for j in range(len(array_trigger_array)-1, -1, -1):
                                    if array_trigger_array[j].get("nodeId") == node_id:
                                        # ✅ 真正覆盖：命中时原位替换（队列长度不变）
                                        try:
                                            array_trigger_array[j] = item
                                        except Exception:
                                            tmp = list(array_trigger_array)
                                            tmp[j] = item
                                            array_trigger_array.clear()
                                            array_trigger_array.extend(tmp)
                                        queue_index[node_id] = j
                                        found = True
                                        enq_overwrite += 1
                                        break
                            if not found:
                                # 完全未找到：指纹相同视为“覆盖不涨”
                                # 兼容 deque：用 list 临时覆盖后再写回（保持队列长度不变）
                                try:
                                    j = int(last_index) if last_index is not None else (len(array_trigger_array) - 1)
                                except Exception:
                                    j = len(array_trigger_array) - 1
                                if len(array_trigger_array) > 0:
                                    j = max(0, min(j, len(array_trigger_array) - 1))
                                    try:
                                        array_trigger_array[j] = item  # ✅原地覆盖，不涨长度
                                    except Exception:
                                        tmp = list(array_trigger_array)
                                        tmp[j] = item                 # ✅原地覆盖，不涨长度
                                        array_trigger_array.clear()
                                        array_trigger_array.extend(tmp)
                                    queue_index[node_id] = j      # ✅索引指向被覆盖的位置
                                    enq_overwrite += 1
                                else:
                                    # 空队列时仍需入队一个元素（否则无处可覆盖）
                                    array_trigger_array.append(item)
                                    queue_index[node_id] = 0
                                    enq_empty_push += 1
                        else:
                            array_trigger_array.append(item)
                            self._last_ring_fp[key] = fp
                            queue_index[node_id] = len(array_trigger_array) - 1  # 更新索引
                            # cache bookkeeping
                            try:
                                self._mark_cache_touch("_last_ring_fp", key)
                                self._mark_cache_touch("_array_queue_last_index", workflow_id)
                                self._prune_cache_if_needed()
                            except Exception:
                                pass
                            enq_push += 1
                    
                    # 汇总一次（避免每条入队都写 events 抢锁，显著提速）
                    try:
                        enq_ms = (time.time() - enq_t0) * 1000.0
                        self._log_event(
                            workflow_id,
                            f"🔴 [DEBUG] ArrayTrigger enqueue groups={len([x for x in original_outputs if x is not None])} push={enq_push} overwrite={enq_overwrite} emptyPush={enq_empty_push} costMs={enq_ms:.1f}"
                        )
                    except Exception:
                        pass
                else:
                    self._log_event(workflow_id, f"🔴 [DEBUG] ArrayTrigger 无输出: result={result}")
            except Exception as e:
                print(f"❌ [ERROR] 处理 ArrayTrigger 节点时出错: {e}")
                import traceback
                print(f"🔍 [TRACEBACK] {traceback.format_exc()}")
                self._update_node_status(data_temp, node["id"], {"IsRunning": False, "IsError": True, "ErrorContext": str(e)})
            finally:
                # 最小改动：入队后立即刷新队列长度到全局状态，确保前端第一时间可见
                try:
                    self._update_workflow_state(workflow_id, None, local_array_trigger_array=array_trigger_array)
                except Exception:
                    pass
                try:
                    self._trace_node(node)
                except Exception:
                    pass
    
    def _execute_upstream_normal_nodes_for_array_trigger(self, workflow_id, data_temp, array_trigger_nodes):
        """
        执行 ArrayTrigger 节点的上游普通节点（排除 trigger 类节点）
        支持 Normal → ArrayTrigger 和 passivityTrigger + Normal → ArrayTrigger 架构
        """
        nodes = data_temp.get("nodes", [])
        edges = data_temp.get("edges", [])
        
        # 找到所有连接到 ArrayTrigger 节点的上游节点
        connect_edges = [
            edge for edge in edges
            if any(node["id"] == edge["target"] for node in array_trigger_nodes)
        ]
        connect_nodes = [
            next((node for node in nodes if node["id"] == edge["source"]), None)
            for edge in connect_edges
        ]
        
        # 过滤掉 None 和 trigger 类节点（passivityTrigger、ArrayTrigger 等）
        normal_upstream_nodes = [
            node for node in connect_nodes
            if node is not None and "trigger" not in node.get("NodeKind", "").lower()
        ]
        
        if not normal_upstream_nodes:
            self._log_event(workflow_id, "🔵 [UPSTREAM] ArrayTrigger 无上游普通节点，跳过")
            return
        
        self._log_event(workflow_id, f"🔵 [UPSTREAM] 找到 {len(normal_upstream_nodes)} 个上游普通节点，开始执行")
        
        # 执行所有上游普通节点（使用拓扑排序，确保依赖关系正确）
        # 简化版：直接执行所有上游节点（如果它们之间没有依赖，可以并行；有依赖则按顺序）
        executed_node_ids = set()
        
        def _can_execute(node):
            """检查节点是否可以执行（所有输入都已就绪）"""
            for inp in node.get("Inputs", []):
                if inp.get("Isnecessary", False):
                    kind = inp.get("Kind", "")
                    if kind == "Num" and inp.get("Num") is None:
                        return False
                    if kind == "Boolean" and inp.get("Boolean") is None:
                        return False
                    if "String" in kind and inp.get("Context") is None:
                        return False
            return True
        
        # 执行上游节点（按依赖顺序，或直接执行所有可执行的）
        remaining_nodes = normal_upstream_nodes.copy()
        max_iterations = len(remaining_nodes) * 2  # 防止无限循环
        iteration = 0
        
        while remaining_nodes and iteration < max_iterations:
            iteration += 1
            executed_this_round = []
            
            for node in remaining_nodes:
                if node["id"] in executed_node_ids:
                    continue
                
                # 检查是否可以执行（输入已就绪）
                if not _can_execute(node):
                    continue
                
                try:
                    self._log_event(workflow_id, f"🔵 [UPSTREAM] 执行上游节点: {node.get('label', node.get('id'))}")
                    
                    # 标记运行中
                    self._update_node_status(data_temp, node["id"], {"IsRunning": True, "IsError": False})
                    self._update_workflow_state(workflow_id, data_temp)
                    
                    # 处理节点
                    processed_node = self._process_node(node)
                    result = self._execute_node(processed_node, workflow_id=str(workflow_id))
                    
                    # 写回 debug
                    if isinstance(result, dict):
                        node["debug"] = self._cap_node_debug(result.get("debug", ""))
                    
                    # 更新节点输出
                    if isinstance(result, dict) and result.get("output") is not None:
                        for idx, output in enumerate(result["output"] if isinstance(result["output"], list) else [result["output"]]):
                            if idx < len(node.get("Outputs", [])):
                                port_kind = node["Outputs"][idx].get("Kind", "")
                                normalized = self._normalize_output_for_port(output, port_kind)
                                node["Outputs"][idx].update(normalized)
                        
                        # 更新第一条输出的 token 信息
                        out_list = result["output"] if isinstance(result["output"], list) else [result["output"]]
                        if len(out_list) > 0 and len(node.get("Outputs", [])) > 0:
                            first_output = out_list[0]
                            if isinstance(first_output, dict):
                                token_fields = ["prompt_tokens", "completion_tokens", "total_tokens"]
                                for field in token_fields:
                                    if field in first_output:
                                        node["Outputs"][0][field] = first_output[field]

                        # Cap stored output contexts (UI/state only)
                        self._cap_output_context_in_place(node.get("Outputs", []))
                    
                    # 运行完成
                    self._update_node_status(data_temp, node["id"], {"IsRunning": False, "isFinish": True, "IsError": False, "ErrorContext": ""})
                    
                    # 传播输出到下游节点（包括 ArrayTrigger）
                    outputs = result.get("output", []) if isinstance(result, dict) else []
                    # 🔥 关键修复：处理 normalize_result 可能产生的嵌套列表
                    # 如果 outputs 是 [[...]] 格式（嵌套列表），取第一个元素
                    if isinstance(outputs, list) and len(outputs) == 1 and isinstance(outputs[0], list):
                        outputs = outputs[0]
                    if outputs:
                        for edge in edges:
                            if edge["source"] == node["id"]:
                                target_nodes = [n for n in nodes if n["id"] == edge["target"]]
                                for target_node in target_nodes:
                                    offset = edge["sourceAnchor"] - len(node.get("Inputs", []))
                                    if offset < 0 or offset >= len(outputs):
                                        self._log_event(workflow_id, f"⚠️ [UPSTREAM] 跳过边传播：offset={offset} 超出范围 (outputs长度={len(outputs)})")
                                        continue
                                    output_item = outputs[offset] or {}
                                    if not isinstance(output_item, dict):
                                        output_item = self._coerce_to_dict(output_item) or {}
                                    target_idx = edge["targetAnchor"]
                                    if target_idx < len(target_node.get("Inputs", [])):
                                        input_item = target_node["Inputs"][target_idx]
                                        # 跨类型转换
                                        ik = input_item.get("Kind", "")
                                        conv_in = self._convert_between_kinds(output_item, ik)
                                        if ik == "Num":
                                            input_item["Num"] = conv_in.get("Num")
                                        elif ik == "Boolean":
                                            input_item["Boolean"] = conv_in.get("Boolean")
                                        elif "String" in ik:
                                            input_item["Context"] = conv_in.get("Context")
                                        # 标记就绪
                                        if "inputStatus" not in target_node:
                                            target_node["inputStatus"] = [False] * len(target_node.get("Inputs", []))
                                        target_node["inputStatus"][target_idx] = True
                                        self._log_event(workflow_id, f"✅ [UPSTREAM] 数据传播成功: {node.get('label', '?')}.Outputs[{offset}] → {target_node.get('label', '?')}.Inputs[{target_idx}]({input_item.get('name', '?')}) = {conv_in.get('Context') or conv_in.get('Num') or conv_in.get('Boolean')}")
                                    else:
                                        self._log_event(workflow_id, f"⚠️ [UPSTREAM] 跳过边传播：target_idx={target_idx} 超出范围 (Inputs长度={len(target_node.get('Inputs', []))})")
                    
                    executed_node_ids.add(node["id"])
                    executed_this_round.append(node)
                    self._log_event(workflow_id, f"✅ [UPSTREAM] 上游节点完成: {node.get('label', node.get('id'))}")
                    
                except Exception as e:
                    print(f"❌ [ERROR] 执行上游节点失败: {e}")
                    self._log_event(workflow_id, f"❌ [UPSTREAM] 上游节点执行失败: {node.get('label', node.get('id'))} - {e}")
                    self._update_node_status(data_temp, node["id"], {"IsRunning": False, "IsError": True, "ErrorContext": str(e)})
                    executed_node_ids.add(node["id"])  # 标记为已处理，避免卡住
                    executed_this_round.append(node)
            
            # 移除已执行的节点
            for node in executed_this_round:
                if node in remaining_nodes:
                    remaining_nodes.remove(node)
            
            # 更新工作流状态
            self._update_workflow_state(workflow_id, data_temp)
        
        if remaining_nodes:
            self._log_event(workflow_id, f"⚠️ [UPSTREAM] 仍有 {len(remaining_nodes)} 个上游节点未执行（可能因依赖未满足）")
        else:
            self._log_event(workflow_id, f"✅ [UPSTREAM] 所有上游普通节点执行完成")
    
    def _run_array_trigger_nodes(self, workflow_id, data_temp, array_trigger_array):
        """运行 ArrayTrigger 节点（模拟前端 runArrayTriggerNodes）"""
        nodes = data_temp.get("nodes", [])
        count = 0
        
        nodes_to_process = [node for node in nodes if "ArrayTrigger" in node.get("NodeKind", "")]
        
        # 🔥 关键修复：在执行 ArrayTrigger 前，先执行其上游普通节点
        if nodes_to_process:
            self._log_event(workflow_id, f"🔵 [ARRAY-PREHEAT] 预热 ArrayTrigger，先执行上游普通节点")
            self._execute_upstream_normal_nodes_for_array_trigger(workflow_id, data_temp, nodes_to_process)
        
        for node in nodes_to_process:
            try:
                # 🔥 关键修复：执行前检查输入是否就绪
                inputs_ready = True
                for inp in node.get("Inputs", []):
                    if inp.get("Isnecessary", False):
                        kind = inp.get("Kind", "")
                        if kind == "Num" and inp.get("Num") is None:
                            inputs_ready = False
                            self._log_event(workflow_id, f"⚠️ [ARRAY-PREHEAT] ArrayTrigger 输入未就绪: {inp.get('name', '?')} (Num=None)")
                            break
                        if kind == "Boolean" and inp.get("Boolean") is None:
                            inputs_ready = False
                            self._log_event(workflow_id, f"⚠️ [ARRAY-PREHEAT] ArrayTrigger 输入未就绪: {inp.get('name', '?')} (Boolean=None)")
                            break
                        if "String" in kind and (inp.get("Context") is None or inp.get("Context") == ""):
                            inputs_ready = False
                            self._log_event(workflow_id, f"⚠️ [ARRAY-PREHEAT] ArrayTrigger 输入未就绪: {inp.get('name', '?')} (Context=None或空)")
                            break
                
                if not inputs_ready:
                    self._log_event(workflow_id, f"⏸️ [ARRAY-PREHEAT] ArrayTrigger 输入未就绪，跳过执行: {node.get('label', node.get('id'))}")
                    continue
                
                # 标记运行中
                with self.lock:
                    self._update_node_status(data_temp, node["id"], {"IsRunning": True, "IsError": False})
                    self.workflows[workflow_id]["graph_data"] = data_temp
                    self.workflows[workflow_id]["last_update"] = time.time()
                
                # 执行节点
                processed_node = self._process_node(node)
                result = self._execute_node(processed_node, workflow_id=str(workflow_id))
                
                # 写回 debug
                if isinstance(result, dict):
                    node["debug"] = self._cap_node_debug(result.get("debug", ""))
                
                # 更新节点输出（包括 token 信息）
                if isinstance(result, dict) and result.get("output"):
                    for idx, output in enumerate(result["output"]):
                        if isinstance(output, dict) and idx < len(node.get("Outputs", [])):
                            node["Outputs"][idx].update(output)
                    
                    # 更新第一条输出的 token 信息
                    if len(result["output"]) > 0 and len(node.get("Outputs", [])) > 0:
                        first_output = result["output"][0]
                        if isinstance(first_output, dict):
                            token_fields = ["prompt_tokens", "completion_tokens", "total_tokens"]
                            for field in token_fields:
                                if field in first_output:
                                    node["Outputs"][0][field] = first_output[field]

                    # Cap stored output contexts (UI/state only)
                    self._cap_output_context_in_place(node.get("Outputs", []))
                
                # 运行完成
                with self.lock:
                    self._update_node_status(data_temp, node["id"], {"IsRunning": False, "isFinish": True, "IsError": False, "ErrorContext": ""})
                    self.workflows[workflow_id]["graph_data"] = data_temp
                    self.workflows[workflow_id]["last_update"] = time.time()
                
                # 添加历史记录
                print(f"📝 [ARRAY-COMPLETE] 数组触发节点完成: {node.get('label', node.get('id'))}")
                print(f"📝 [ARRAY-COMPLETE] 输出数量: {len(result.get('output', [])) if isinstance(result, dict) else 0}")
                self._add_history(workflow_id, node)
                
                # 修复：与前端逻辑保持一致 - 检查 result.output 是否不为 None（而不是检查真值）
                if isinstance(result, dict) and result.get("output") is not None:
                    original_outputs = result.get("output") or []
                    # ===== 深度调试：记录原始 output 形状和每组内容摘要 =====
                    try:
                        raw = result.get("output")
                        raw_len = len(raw) if isinstance(raw, list) else 1
                        if getattr(self, "DEBUG_PRINT", False):
                            print(f"[ARRAY-TRACE] node={node.get('label', node.get('id'))} raw_type={type(raw)} raw_len={raw_len}")
                        if isinstance(raw, list):
                            for i, g in enumerate(raw):
                                if isinstance(g, list):
                                    if getattr(self, "DEBUG_PRINT", False):
                                        print(f"   └─ raw[{i}] is list, size={len(g)}")
                                elif isinstance(g, dict):
                                    keys = list(g.keys())
                                    if getattr(self, "DEBUG_PRINT", False):
                                        print(f"   └─ raw[{i}] is dict, keys={keys}")
                                else:
                                    if getattr(self, "DEBUG_PRINT", False):
                                        print(f"   └─ raw[{i}] type={type(g)} value_preview={str(g)[:80]}")
                    except Exception:
                        pass
                    # === 形状归一化（最小修） ===
                    def _looks_like_output_slot(x):
                        return (
                            isinstance(x, dict)
                            and isinstance(x.get('Id'), str)
                            and x['Id'].startswith('Output')
                            and isinstance(x.get('name'), str)
                        )
                    # 不是列表 → 置空
                    if not isinstance(original_outputs, list):
                        original_outputs = []
                    # 如果 original_outputs 是“槽位字典的列表”，说明这其实是“一行”
                    # 自动包一层，使其成为单元素数组：[Outputs_row]
                    if original_outputs and all(_looks_like_output_slot(x) for x in original_outputs):
                        original_outputs = [original_outputs]
                        if getattr(self, "DEBUG_PRINT", False):
                            print("[ARRAY-DEBUG] 归一化：检测到单行的 Outputs，被包裹为 1 个数组元素")
                    # 归一化后再输出一遍统计信息
                    try:
                        if getattr(self, "DEBUG_PRINT", False):
                            print(f"[ARRAY-TRACE] 标准化后组数(original_outputs.len) = {len(original_outputs)}")
                        for gi, g in enumerate(original_outputs):
                            if isinstance(g, list):
                                ids = []
                                for it in g:
                                    if isinstance(it, dict):
                                        ids.append(it.get('Id') or it.get('name'))
                                if getattr(self, "DEBUG_PRINT", False):
                                    print(f"   └─ group[{gi}] size={len(g)} ids={ids}")
                            else:
                                if getattr(self, "DEBUG_PRINT", False):
                                    print(f"   └─ group[{gi}] type={type(g)} value_preview={str(g)[:80]}")
                    except Exception:
                        pass
                    if getattr(self, "DEBUG_PRINT", False):
                        print(f"[ARRAY-DEBUG] ArrayTrigger 原始输出数量: {len(original_outputs)}")
                    
                    # 性能关键：每批输出只冻结一次 graph 快照，避免每条队列项都 deepcopy 整张图
                    shared_graph_snapshot = None
                    if WF_QUEUE_STORE_GRAPH_SNAPSHOT:
                        try:
                            shared_graph_snapshot = copy.deepcopy(data_temp)
                        except Exception:
                            shared_graph_snapshot = data_temp
                    
                    # 🔥 关键修复：ArrayTrigger 的 output 是嵌套数组结构
                    # 每个子数组代表一个完整的输出组，应该作为一个队列项
                    enqueued_count = 0
                    for idx, array_group in enumerate(original_outputs):
                        if array_group is None:
                            continue
                        
                        node_id = node["id"]
                        # 性能关键：避免对每个 group 做 deepcopy（几万条会非常慢且占内存）
                        group = array_group
                        fp = self._calc_fp(node_id, group)            # ← 新增
                        key = (workflow_id, node_id)
                        last_fp = self._last_ring_fp.get(key)
                        item = {"outputData": group, "nodeId": node_id}
                        if WF_QUEUE_STORE_GRAPH_SNAPSHOT and shared_graph_snapshot is not None:
                            item["graph_data"] = shared_graph_snapshot

                        # 性能优化：使用索引字典快速定位最后一个相同 nodeId 的项
                        queue_index = self._array_queue_last_index.setdefault(workflow_id, {})
                        last_index = queue_index.get(node_id)
                        
                        if last_fp == fp and last_index is not None:
                            # 性能优化：从 last_index 开始向前查找（限制查找范围）
                            found = False
                            if last_index < len(array_trigger_array):
                                start_idx = min(last_index, len(array_trigger_array) - 1)
                                for j in range(start_idx, -1, -1):
                                    if array_trigger_array[j].get("nodeId") == node_id:
                                        # ✅ 真正覆盖：命中时原位替换（队列长度不变）
                                        try:
                                            array_trigger_array[j] = item
                                        except Exception:
                                            tmp = list(array_trigger_array)
                                            tmp[j] = item
                                            array_trigger_array.clear()
                                            array_trigger_array.extend(tmp)
                                        queue_index[node_id] = j
                                        found = True
                                        if getattr(self, "DEBUG_PRINT", False):
                                            print(f"🌀 [RING:OVERWRITE] ArrayTrigger 覆盖队列中该节点记录（相同指纹） fp={fp} group_idx={idx}")
                                        break
                            if not found:
                                # 索引失效，从末尾重新查找
                                for j in range(len(array_trigger_array)-1, -1, -1):
                                    if array_trigger_array[j].get("nodeId") == node_id:
                                        # ✅ 真正覆盖：命中时原位替换（队列长度不变）
                                        try:
                                            array_trigger_array[j] = item
                                        except Exception:
                                            tmp = list(array_trigger_array)
                                            tmp[j] = item
                                            array_trigger_array.clear()
                                            array_trigger_array.extend(tmp)
                                        queue_index[node_id] = j
                                        found = True
                                        if getattr(self, "DEBUG_PRINT", False):
                                            print(f"🌀 [RING:OVERWRITE] ArrayTrigger 覆盖队列中该节点记录（重新查找命中） fp={fp} group_idx={idx}")
                                        break
                            if not found:
                                # 指纹相同视为“覆盖不涨”；未命中旧项时按 last_index 兜底覆盖
                                try:
                                    j = int(last_index) if last_index is not None else (len(array_trigger_array) - 1)
                                except Exception:
                                    j = len(array_trigger_array) - 1
                                if len(array_trigger_array) > 0:
                                    j = max(0, min(j, len(array_trigger_array) - 1))
                                    try:
                                        array_trigger_array[j] = item  # ✅原地覆盖，不涨长度
                                    except Exception:
                                        tmp = list(array_trigger_array)
                                        tmp[j] = item                 # ✅原地覆盖，不涨长度（兼容 deque）
                                        array_trigger_array.clear()
                                        array_trigger_array.extend(tmp)
                                    queue_index[node_id] = j      # ✅索引指向被覆盖的位置
                                else:
                                    array_trigger_array.append(item)
                                    queue_index[node_id] = 0
                                if getattr(self, "DEBUG_PRINT", False):
                                    print(f"🌀 [RING:OVERWRITE] ArrayTrigger 未命中旧项，兜底覆盖 fp={fp} group_idx={idx}")
                        else:
                            array_trigger_array.append(item)
                            self._last_ring_fp[key] = fp
                            queue_index[node_id] = len(array_trigger_array) - 1
                            # cache bookkeeping
                            try:
                                self._mark_cache_touch("_last_ring_fp", key)
                                self._mark_cache_touch("_array_queue_last_index", workflow_id)
                                self._prune_cache_if_needed()
                            except Exception:
                                pass
                            if getattr(self, "DEBUG_PRINT", False):
                                print(f"✅ [RING:PUSH] ArrayTrigger 入队数组组 {idx+1}/{len(original_outputs)} fp={fp} group_idx={idx}")
                        
                        enqueued_count += 1
                    
                    if getattr(self, "DEBUG_PRINT", False):
                        print(f"[ARRAY-DEBUG] ArrayTrigger 总共入队 {enqueued_count} 个数组组")
                    if enqueued_count == 0:
                        if getattr(self, "DEBUG_PRINT", False):
                            print("[ARRAY-DEBUG] ArrayTrigger 所有输出元素均为空，跳过入队")
                    # 最小改动：入队完成后立即刷新队列长度到全局状态
                    try:
                        self._update_workflow_state(workflow_id, None, local_array_trigger_array=array_trigger_array)
                    except Exception:
                        pass
                
            except Exception as e:
                print(f"处理 ArrayTrigger 节点时出错: {e}")
                with self.lock:
                    self._update_node_status(data_temp, node["id"], {"IsRunning": False, "IsError": True, "ErrorContext": str(e)})
                    self.workflows[workflow_id]["graph_data"] = data_temp
                    self.workflows[workflow_id]["last_update"] = time.time()
            finally:
                try:
                    self._trace_node(node)
                except Exception:
                    pass
    
    def _process_next_array_trigger(self, workflow_id, data_temp, array_trigger_array, workflow_state):
        """处理下一个 ArrayTrigger 数据（模拟前端 processNextArrayTrigger）"""
        self._log_event(workflow_id, f"▶️ processNextArrayTrigger size={len(array_trigger_array) if array_trigger_array else 0}")
        
        if array_trigger_array:
            # 取出第一个数据，用于获取 ParallelLimit
            array_data = array_trigger_array[0]
            if getattr(self, "DEBUG_PRINT", False):
                print(f"[ARRAY-DEBUG] 开始处理 ArrayTrigger 数据: nodeId={array_data.get('nodeId')}")
                print(f"[ARRAY-DEBUG] 当前队列总长度: {len(array_trigger_array)}")
                print(f"[ARRAY-DEBUG] 处理的数据类型: {type(array_data.get('outputData'))}")
            if isinstance(array_data.get('outputData'), list):
                if getattr(self, "DEBUG_PRINT", False):
                    print(f"[ARRAY-DEBUG] 输出数据长度: {len(array_data.get('outputData', []))}")
            self._log_event(workflow_id, f"   └─ headKeys={(list(array_data.keys()) if isinstance(array_data, dict) else type(array_data))}")
            
            # 检查 array_data 是否为 None；当 outputData 为空但带有 graph_data（占位项，用于无 ArrayTrigger 的场景）时，不丢弃
            if array_data is None or (array_data.get("outputData") is None and "graph_data" not in array_data):
                self._log_event(workflow_id, "❌ array_data 无效（无 outputData 且无 graph_data）→ DROP & POP")
                try:
                    array_trigger_array.popleft()
                except Exception:
                    array_trigger_array.pop(0)
                workflow_state["queue_lengths"] = workflow_state.get("queue_lengths", {})
                workflow_state["queue_lengths"]["array"] = len(array_trigger_array)
                workflow_state["last_update"] = time.time()
                self._log_event(workflow_id, f"   └─ POP → Aq={len(array_trigger_array)}")
                workflow_state["pending_array_count"] = len(array_trigger_array)
                self._refresh_parent_array_queue(workflow_id, len(array_trigger_array))
                return
            
            # 获取 ArrayTrigger 节点的 ParallelLimit
            parallel_limit = 1
            if array_data.get("nodeId"):
                effective_graph = array_data.get("graph_data") or data_temp
                nodes = effective_graph.get("nodes", [])
                array_node = next((node for node in nodes if node["id"] == array_data["nodeId"]), None)
                if array_node:
                    parallel_limit = array_node.get("ParallelLimit", 1)
                    if not isinstance(parallel_limit, int) or parallel_limit < 1:
                        parallel_limit = 1
            
            # 如果 ParallelLimit > 1，进行并行处理
            if parallel_limit > 1 and len(array_trigger_array) > 0:
                # 根据当前活跃子工作流数量动态限流
                with self.lock:
                    summary = self._ensure_child_summary(workflow_id) or {}
                    active_children = summary.get("active", 0)
                available_slots = max(0, parallel_limit - active_children)

                if available_slots <= 0:
                    # 当前已满负荷，保持队列不动，等待下一轮
                    self._log_event(workflow_id, f"⏸ [CHILD] 并行上限={parallel_limit}，活跃={active_children}，暂不新增")
                    workflow_state["pending_array_count"] = len(array_trigger_array)
                    self._refresh_parent_array_queue(workflow_id, len(array_trigger_array))
                    return

                batch_size = min(available_slots, len(array_trigger_array))
                # 关键：先“占位出队”(pending--) ，再启动子任务(active++)，
                # 最后只刷新一次队列长度，避免出现 pending 旧值 + active 新值 的假增长。
                reserved_items = []
                for _ in range(batch_size):
                    if not array_trigger_array:
                        break
                    try:
                        reserved_items.append(array_trigger_array.popleft())
                    except Exception:
                        reserved_items.append(array_trigger_array.pop(0))

                launched = 0
                for batch_item in reserved_items:
                    try:
                        child_graph = self._prepare_child_graph(workflow_id, data_temp, batch_item)
                        if child_graph is None:
                            continue
                        self._start_child_workflow(workflow_id, child_graph, batch_item)
                        launched += 1
                    except Exception as e:
                        if getattr(self, "DEBUG_PRINT", False):
                            print(f"[ARRAY-DEBUG] 子工作流启动失败: {e}")
                        self._log_event(workflow_id, f"❌ [CHILD] 子工作流启动失败: {e}")

                # 最小修：批量 pop 之后，旧的 last_index 全部失效，直接丢弃索引缓存，避免误判
                try:
                    self._array_queue_last_index.pop(workflow_id, None)
                except Exception:
                    pass

                workflow_state["pending_array_count"] = len(array_trigger_array)
                self._refresh_parent_array_queue(workflow_id, len(array_trigger_array))
                if launched:
                    self._log_event(workflow_id, f"🔄 [CHILD] 已启动 {launched} 个子工作流，剩余队列 {len(array_trigger_array)}")
                else:
                    self._log_event(workflow_id, f"⚠️ [CHILD] 未能启动子工作流，剩余队列 {len(array_trigger_array)}")
                return
            else:
                # 原有串行处理逻辑
                if array_data.get("nodeId") is None:
                    # 没有 nodeId，检查是否有 graph_data
                    if "graph_data" in array_data:
                        self._log_event(workflow_id, "   └─ process graph_data → run normal nodes")
                        self._process_normal_nodes(array_data["graph_data"], workflow_state)
                    else:
                        self._log_event(workflow_id, "   └─ treat as graph_data → run normal nodes")
                        self._process_normal_nodes(array_data, workflow_state)
                else:
                    # 找到对应的 ArrayTrigger 节点
                    # 优先使用队列项中附带的 graph_data（包含 passivity 路由后的最新输入状态）
                    effective_graph = array_data.get("graph_data") or data_temp
                    nodes = effective_graph.get("nodes", [])
                    array_node = next((node for node in nodes if node["id"] == array_data["nodeId"]), None)
                    
                    if array_node:
                        if getattr(self, "DEBUG_PRINT", False):
                            print(f"[ARRAY-DEBUG] 找到 ArrayTrigger 节点: {array_node.get('label', array_node.get('id'))}")
                        self._log_event(workflow_id, f"   └─ hit ArrayTrigger node: {array_node.get('label', array_node.get('id'))}")
                        try:
                            if getattr(self, "DEBUG_PRINT", False):
                                print(f"[ARRAY-DEBUG] outputData 类型: {type(array_data.get('outputData'))}")
                                print(f"[ARRAY-DEBUG] outputData 内容: {array_data.get('outputData')}")
                            self._log_event(workflow_id, f"🔴 [DEBUG] array_data keys: {list(array_data.keys())}")
                            self._log_event(workflow_id, f"🔴 [DEBUG] ArrayTrigger outputData type: {type(array_data.get('outputData'))}")
                            self._log_event(workflow_id, f"🔴 [DEBUG] ArrayTrigger outputData: {array_data.get('outputData')}")
                            # 处理节点连接
                            processed_data_temp = self._process_node_connections(self._clone_graph_for_child(effective_graph), array_node, array_data["outputData"], workflow_id)
                            if getattr(self, "DEBUG_PRINT", False):
                                print(f"[ARRAY-DEBUG] 处理节点连接完成，图中有 {len(processed_data_temp.get('nodes', []))} 个节点")
                            self._log_event(workflow_id, f"🔴 [DEBUG] 开始处理普通节点，图中有 {len(processed_data_temp.get('nodes', []))} 个节点")
                            # 处理节点
                            self._process_normal_nodes(processed_data_temp, workflow_state)
                            if getattr(self, "DEBUG_PRINT", False):
                                print(f"[ARRAY-DEBUG] 普通节点处理完成")
                            self._log_event(workflow_id, f"🔴 [DEBUG] 普通节点处理完成")
                        except Exception as e:
                            if getattr(self, "DEBUG_PRINT", False):
                                print(f"[ARRAY-DEBUG] 处理错误: {e}")
                            self._log_event(workflow_id, f"❌ [ERROR] _process_next_array_trigger 内部错误: {e}")
                            import traceback
                            self._log_event(workflow_id, f"🔍 [TRACEBACK] {traceback.format_exc()}")
                    else:
                        if getattr(self, "DEBUG_PRINT", False):
                            print(f"[ARRAY-DEBUG] 找不到 ArrayTrigger 节点: {array_data.get('nodeId')}")
                        self._log_event(workflow_id, f"❌ [ERROR] 找不到 ArrayTrigger 节点: {array_data.get('nodeId')}")
                
                # 处理完成后，才从队列中移除并更新队列长度
                try:
                    popped_item = array_trigger_array.popleft()
                    # 性能优化：清理索引（如果被移除的项是某个 nodeId 的最后一项）
                    if isinstance(popped_item, dict):
                        popped_node_id = popped_item.get("nodeId")
                        if popped_node_id:
                            queue_index = self._array_queue_last_index.get(workflow_id, {})
                            # 检查被移除的项是否是该 nodeId 的最后一项
                            if queue_index.get(popped_node_id, -1) == 0:
                                # 如果索引指向的是第一个项（刚被移除），清除索引
                                queue_index.pop(popped_node_id, None)
                            elif queue_index.get(popped_node_id, -1) > 0:
                                # 索引需要减1（因为队列头部被移除）
                                queue_index[popped_node_id] = queue_index[popped_node_id] - 1
                except Exception:
                    array_trigger_array.pop(0)
                if getattr(self, "DEBUG_PRINT", False):
                    print(f"[ARRAY-DEBUG] 移除一个 ArrayTrigger 数据，剩余长度: {len(array_trigger_array)}")
            
            # 设置本轮固定指纹（避免同一轮内指纹随状态变化）
            import hashlib
            node_id_or_payload = array_data.get('nodeId', 'unknown')
            item_tag = f"A:{str(node_id_or_payload)[:64]}"
            workflow = self.workflows[workflow_id]
            workflow["round_id"] = item_tag
            
            # 为本轮生成稳定指纹（与状态变化解耦）
            fixed = f"{workflow_id}:{item_tag}"
            workflow["ring_fingerprint"] = hashlib.sha1(fixed.encode("utf-8")).hexdigest()
            # 也可写回给前端备用
            workflow["graph_data"]["fingerprint"] = workflow["ring_fingerprint"]
            
            workflow_state["queue_lengths"] = workflow_state.get("queue_lengths", {})
            workflow_state["queue_lengths"]["array"] = len(array_trigger_array)
            workflow_state["last_update"] = time.time()
            self._log_event(workflow_id, f"   └─ POP → Aq={len(array_trigger_array)}")
            

        else:
            # 没有更多数据要处理
            pass

    def _prepare_child_graph(self, workflow_id, parent_graph_data, array_data):
        """根据 arrayTrigger 数据构建子工作流的图"""
        try:
            if array_data is None:
                return None
            if array_data.get("nodeId") is None:
                graph_payload = array_data.get("graph_data") or array_data
                if isinstance(graph_payload, dict):
                    # Even when a snapshot is provided, avoid copying runtime junk if possible
                    return self._clone_graph_for_child(graph_payload)
                return None
            effective_graph = array_data.get("graph_data") or parent_graph_data
            graph_copy = self._clone_graph_for_child(effective_graph)
            nodes = graph_copy.get("nodes", [])
            array_node = next((node for node in nodes if node.get("id") == array_data.get("nodeId")), None)
            if array_node is None:
                self._log_event(workflow_id, f"❌ [CHILD] 找不到 ArrayTrigger 节点: {array_data.get('nodeId')}")
                return None
            if array_data.get("outputData") is None:
                self._log_event(workflow_id, f"❌ [CHILD] ArrayTrigger 输出为空，跳过子工作流")
                return None
            processed_graph = self._process_node_connections(graph_copy, array_node, array_data["outputData"], workflow_id)
            return processed_graph
        except Exception as e:
            self._log_event(workflow_id, f"❌ [CHILD] 构建子工作流图失败: {e}")
            return None

    def _start_child_workflow(self, parent_id, child_graph, source_item=None):
        """为 arrayTrigger 结果启动子工作流"""
        if child_graph is None:
            return None
        child_suffix = uuid.uuid4().hex[:6]
        child_id = f"{parent_id}__array_{int(time.time()*1000)}_{child_suffix}"
        parent_state = self.workflows.get(parent_id, {})
        parent_graph = (parent_state or {}).get("graph_data", {}) or {}
        base_project_name = parent_graph.get("ProjectName") or parent_graph.get("name") or parent_id
        parent_summary = self._ensure_child_summary(parent_id)
        next_index = (parent_summary.get("total", 0) if parent_summary else 0) + 1
        display_name = f"{base_project_name} · 子任务{next_index}"
        child_graph = copy.deepcopy(child_graph)
        child_graph.setdefault("ProjectName", display_name)
        with self.lock:
            self.workflows[child_id] = {
                "id": child_id,
                "status": WorkflowStatus.RUNNING,
                "graph_data": child_graph,
                "start_time": time.time(),
                "last_update": time.time(),
                "error": None,
                "traceback": None,
                "queue_lengths": {"passivity": 0, "array": 0},
                "events": [],
                "is_child": True,
                "parent_id": parent_id,
                "display_name": display_name
            }
            self.stop_events[child_id] = threading.Event()
            self._register_child_workflow(parent_id, child_id)
            summary = self._ensure_child_summary(parent_id)
            if summary:
                summary["active"] += 1
                summary["total"] += 1
            # 注意：这里不要刷新父队列长度。
            # 父队列的 pending_array_count 通常会在调用方“出队/占位”之后才更新；
            # 若在这里用旧 pending 叠加 active，会造成前端看到队列数瞬间 +1 的假增长。
            # 由调用方在“pending 已减少 + active 已增加”后统一刷新，保证总数稳定。
        self._log_event(parent_id, f"🆕 [CHILD] 启动子工作流: {child_id}")
        self._add_history(child_id, 'Start')
        thread = threading.Thread(target=self._execute_child_workflow_thread, args=(child_id,))
        thread.daemon = True
        thread.start()
        return child_id

    def _execute_child_workflow_thread(self, child_id):
        """执行子工作流（仅普通节点）"""
        workflow_state = self.workflows.get(child_id)
        if workflow_state is None:
            return
        parent_id = workflow_state.get("parent_id")
        stop_event = self.stop_events.get(child_id)
        try:
            if stop_event and stop_event.is_set():
                workflow_state["status"] = WorkflowStatus.STOPPED
                return
            graph_data = workflow_state.get("graph_data")
            self._process_normal_nodes(graph_data, workflow_state)
            if workflow_state.get("status") == WorkflowStatus.RUNNING:
                workflow_state["status"] = WorkflowStatus.COMPLETED
            workflow_state["graph_data"] = graph_data
        except Exception as e:
            workflow_state["status"] = WorkflowStatus.ERROR
            workflow_state["error"] = str(e)
            workflow_state["traceback"] = traceback.format_exc()
            self._log_event(child_id, f"❌ [CHILD] 子工作流执行失败: {e}")
        finally:
            # 守护：避免长时间保持 RUNNING，未被正常收敛时强制标记完成
            if workflow_state.get("status") == WorkflowStatus.RUNNING:
                workflow_state["status"] = WorkflowStatus.COMPLETED
            try:
                if workflow_state.get("status") in (WorkflowStatus.COMPLETED, WorkflowStatus.ERROR, WorkflowStatus.STOPPED):
                    workflow_state["done_ts"] = time.time()
            except Exception:
                pass
            workflow_state["last_update"] = time.time()
            try:
                self._save_simple_history(workflow_state.get("graph_data"))
            except Exception:
                pass
            self._handle_child_completion(child_id, parent_id)
            self._schedule_workflow_cleanup(child_id, delay=5.0)

    def _handle_child_completion(self, child_id, parent_id):
        status = None
        with self.lock:
            wf = self.workflows.get(child_id)
            if wf:
                status = wf.get("status")
        registered_parent = self._unregister_child_workflow(child_id)
        target_parent = parent_id or registered_parent
        if not target_parent:
            return
        parent_state = self.workflows.get(target_parent)
        if not parent_state:
            return
        parent_state["last_update"] = time.time()
        summary = self._ensure_child_summary(target_parent)
        if summary:
            summary["active"] = max(0, summary.get("active", 0) - 1)
            if status == WorkflowStatus.COMPLETED:
                summary["completed"] += 1
            elif status in (WorkflowStatus.ERROR, WorkflowStatus.STOPPED):
                summary["failed"] += 1
        pending = parent_state.get("pending_array_count", 0)
        self._refresh_parent_array_queue(target_parent, pending)
        remaining_children = summary.get("active", 0) if summary else 0
        self._log_event(target_parent, f"✅ [CHILD] {child_id} 结束（{status}），剩余子任务 {remaining_children}")
    
    def _process_batch_array_trigger(self, batch_workflow_id, parent_workflow_id, data_temp, array_data, workflow_state):
        """处理单个批次的 ArrayTrigger 数据（并行处理用）"""
        try:
            self._log_event(parent_workflow_id, f"🔄 [BATCH] 开始处理批次: {batch_workflow_id}")
            
            if array_data.get("nodeId") is None:
                # 没有 nodeId，检查是否有 graph_data
                if "graph_data" in array_data:
                    self._log_event(parent_workflow_id, f"   └─ [BATCH] process graph_data → run normal nodes")
                    self._process_normal_nodes(array_data["graph_data"], workflow_state)
                else:
                    self._log_event(parent_workflow_id, f"   └─ [BATCH] treat as graph_data → run normal nodes")
                    self._process_normal_nodes(array_data, workflow_state)
            else:
                # 找到对应的 ArrayTrigger 节点
                effective_graph = array_data.get("graph_data") or data_temp
                nodes = effective_graph.get("nodes", [])
                array_node = next((node for node in nodes if node["id"] == array_data["nodeId"]), None)
                
                if array_node:
                    self._log_event(parent_workflow_id, f"   └─ [BATCH] hit ArrayTrigger node: {array_node.get('label', array_node.get('id'))}")
                    # 处理节点连接
                    processed_data_temp = self._process_node_connections(self._clone_graph_for_child(effective_graph), array_node, array_data["outputData"], parent_workflow_id)
                    # 处理节点
                    self._process_normal_nodes(processed_data_temp, workflow_state)
                    self._log_event(parent_workflow_id, f"   └─ [BATCH] 批次处理完成")
                else:
                    self._log_event(parent_workflow_id, f"❌ [BATCH] 找不到 ArrayTrigger 节点: {array_data.get('nodeId')}")
        except Exception as e:
            if getattr(self, "DEBUG_PRINT", False):
                print(f"[ARRAY-DEBUG] 批次处理错误: {e}")
            self._log_event(parent_workflow_id, f"❌ [BATCH] 批次处理错误: {e}")
            import traceback
            self._log_event(parent_workflow_id, f"🔍 [BATCH-TRACEBACK] {traceback.format_exc()}")
    
    def _process_normal_nodes(self, data_temp, workflow_state):
        """处理普通节点流程（模拟前端 processNodes + runAllNodes）"""
        if isinstance(data_temp, dict):
            nodes = data_temp.get("nodes", [])
            edges = data_temp.get("edges", [])
            
            # 初始化节点状态
            for node in nodes:
                node["IsBlock"] = True
                node["IsRunning"] = False
                node["IsError"] = False
                node["isFinish"] = False
                node["firstRun"] = True
            
            # 执行所有节点
            self._run_all_nodes(data_temp, workflow_state)

    def _run_all_nodes(self, data_temp, workflow_state):
        """执行所有节点（简化版的前端 runAllNodes 逻辑）"""
        nodes = data_temp.get("nodes", [])
        edges = data_temp.get("edges", [])
        
        # 🔥 初始化节点状态 (参考前端runAllNodes函数)
        workflow_id = workflow_state.get("id") if isinstance(workflow_state, dict) else None
        for node in nodes:
            # 初始化输入输出Link和TriggerLink
            for inp in node.get("Inputs", []):
                inp["Link"] = 0
            for out in node.get("Outputs", []):
                out["Link"] = 0
            node["TriggerLink"] = 0
            
            # 🔥 关键修复：每次运行都重置firstRun=True (参考前端第11013行)
            if not node.get("NodeKind", "").lower().endswith("trigger"):
                node["firstRun"] = True
            
            # 确保RecursionBehavior有默认值
            if "RecursionBehavior" not in node:
                node["RecursionBehavior"] = "STOP"
            
            # 重置节点状态 (参考前端)
            node["IsBlock"] = True
            node["IsRunning"] = False
            node["IsError"] = False
            node["isFinish"] = False
            
            # 确保inputStatus存在
            if "inputStatus" not in node:
                node["inputStatus"] = [False] * len(node.get("Inputs", []))
                
            # 初始化输出状态 (参考前端第11015-11019行)
            for output in node.get("Outputs", []):
                output["Boolean"] = False
                output["Num"] = 0
                output["Context"] = ""
        
        # 处理边连接，设置Link和TriggerLink (参考前端第11003-11012行)
        for edge in edges:
            source_node = next((n for n in nodes if n["id"] == edge["source"]), None)
            target_node = next((n for n in nodes if n["id"] == edge["target"]), None)
            
            if source_node and target_node:
                # 设置输出Link
                source_idx = edge.get("sourceAnchor", 0) - len(source_node.get("Inputs", []))
                if source_idx >= 0 and source_idx < len(source_node.get("Outputs", [])):
                    source_node["Outputs"][source_idx]["Link"] = 1
                
                # 设置输入Link（但IfNode是特殊情况）
                if source_node.get("NodeKind") != "IfNode":
                    target_idx = edge.get("targetAnchor", 0)
                    if target_idx < len(target_node.get("Inputs", [])):
                        target_node["Inputs"][target_idx]["Link"] = 1
                        
                        # 🔥 inputStatus：不要覆盖已有的就绪标记
                        # 触发器边：直接标记就绪；非触发器边：保留已有 True，不强制置 False
                        if "trigger" in source_node.get("NodeKind", "").lower():
                            target_node["inputStatus"][target_idx] = True
                        # 非触发器：不修改 inputStatus，保持之前 _process_node_connections 写入的状态
                
                # 特殊处理：IfNode会设置TriggerLink (参考前端第11382-11388行)
                if source_node.get("NodeKind") == "IfNode":
                    target_node["TriggerLink"] = 1
                    # 🔥 关键：IfNode连接到触发器锚点，不是常规输入
                    edge["targetAnchor"] = len(target_node.get("Inputs", [])) + len(target_node.get("Outputs", []))
        
        # 🔥 关键修复：找到起始节点（类似JS的startNodes）
        # 排除被IfNode控制的节点（TriggerLink > 0的节点不应该是起始节点）
        start_nodes = [
            n for n in nodes 
            if (n.get("IsStartNode") or 
                len(n.get("Inputs", [])) == 0 or 
                all(inp.get("IsLabel") for inp in n.get("Inputs", []))) and
            not n.get("NodeKind", "").lower().endswith("trigger") and
            n.get("firstRun", True) and
            n.get("TriggerLink", 0) == 0  # 🔥 关键：排除被IfNode控制的节点
        ]
        
        if start_nodes:
            try:
                print("[TRACE:FLOW] begin normal-nodes execution")
            except Exception:
                pass
            self._execute_nodes_recursively(start_nodes, nodes, edges, data_temp, workflow_state)
            try:
                self._trace_end(workflow_state.get('id'), workflow_state.get('status'))
            except Exception:
                pass

        # 运行一轮普通节点后，计算并写入本轮识别指纹，便于前端进行去重/覆盖
        try:
            def _node_brief(n: dict) -> dict:
                try:
                    outs = []
                    for o in (n.get('Outputs') or []):
                        if not isinstance(o, dict):
                            outs.append(None)
                            continue
                        outs.append({
                            'C': o.get('Context'),
                            'N': o.get('Num'),
                            'B': o.get('Boolean')
                        })
                    st = 'E' if n.get('IsError') else ('F' if n.get('isFinish') else ('R' if n.get('IsRunning') else 'I'))
                    return {
                        'id': n.get('id'),
                        'st': st,
                        'outs': outs
                    }
                except Exception:
                    return {'id': n.get('id')}

            brief = {'nodes': [_node_brief(n) for n in (data_temp.get('nodes') or [])]}
            raw = json.dumps(brief, ensure_ascii=False, separators=(',', ':'))
            fp = hashlib.sha1(raw.encode('utf-8')).hexdigest()
            data_temp['ringFingerprint'] = fp
            try:
                self._log_event(workflow_state.get('id'), f"🧾 [RING:FP] fingerprint={fp} nodes={len(brief['nodes'])}")
            except Exception:
                pass
        except Exception:
            pass

    def _execute_nodes_recursively(self, nodes_to_execute, all_nodes, all_edges, data_temp, workflow_state):
        """递归执行节点列表，实现真正的并发（从原来的代码移动过来）"""
        if not nodes_to_execute:
            return
        workflow_id = workflow_state.get("id") if isinstance(workflow_state, dict) else None


        
        result_lock = threading.Lock()
        
        def execute_single_node(node):
            """执行单个节点的同步函数"""
            node_id = node["id"]
            
            # 检查执行条件 (参考前端prepareAndExecuteNode)
            if (not node.get("firstRun", True) or 
                "trigger" in node.get("NodeKind", "").lower()):
                return None
            
            # 额外检查：如果TriggerLink=0或RecursionBehavior!='STOP'才执行(参考前端prepareAndExecuteNode)
            if node.get("TriggerLink", 0) > 0 and node.get("RecursionBehavior", "STOP") == "STOP":
                return None
            
            # 检查输入是否就绪 (参考前端逻辑) 并打印未就绪详情
            inputs_ready = True
            input_status = node.get("inputStatus", [False] * len(node.get("Inputs", [])))
            
            for idx, input_item in enumerate(node.get("Inputs", [])):
                ready = (
                    (not input_item.get("Isnecessary", False) and input_item.get("Link", 0) == 0) or  # 非必需未连线
                    (input_status[idx] and input_item.get("Link", 0) > 0) or  # 已连线且就绪
                    input_item.get("IsLabel", False)  # Label 输入
                )
                if not ready:
                    inputs_ready = False
                    if workflow_id is not None:
                        self._log_event(workflow_id, f"⏭️ [SKIP] {node.get('label','?')} 未就绪输入: idx={idx}, name={input_item.get('name')}, Link={input_item.get('Link')}, Isnecessary={input_item.get('Isnecessary')}, IsLabel={input_item.get('IsLabel')}, status={input_status[idx]}")
                    break
            
            if not inputs_ready:
                return None
            
            # 检查递归行为 (参考前端逻辑)
            trigger_link = node.get("TriggerLink", 0)
            recursion_behavior = node.get("RecursionBehavior", "STOP")
            is_recursion = recursion_behavior == "STOP" and trigger_link > 0
            
            if is_recursion:
                return None
            
            try:
                # 更新节点状态为运行中（线程安全）
                with result_lock:
                    # 与前端 TempMessageNode 预运行写入保持一致：进入运行中、复位错误/完成标记
                    self._update_node_status(data_temp, node_id, {
                        "IsRunning": True,
                        "isFinish": False,
                        "IsError": False,
                        "ErrorContext": ""
                    })
                    
                    # 清空上一轮输出与 token（不改变端口结构）
                    try:
                        for o in (node.get("Outputs", []) or []):
                            if not isinstance(o, dict):
                                continue
                            if "Context" in o: o["Context"] = ""
                            if "Num" in o: o["Num"] = None
                            if "Boolean" in o: o["Boolean"] = False
                            if "prompt_tokens" in o: o["prompt_tokens"] = None
                            if "completion_tokens" in o: o["completion_tokens"] = None
                            if "total_tokens" in o: o["total_tokens"] = None
                    except Exception:
                        pass

                    workflow_state["graph_data"] = data_temp
                    workflow_state["last_update"] = time.time()
                
                # 处理LLM提示词
                if node.get("NodeKind", "").lower() == "llm":
                    # 仅生成本次执行所需提示词，不写回节点字段
                    _ = self._process_llm_prompt(node)
                
                # 将预处理后的 Prompt 也立即同步到 graph_data（便于前端在运行中查看）
                with result_lock:
                    workflow_state["graph_data"] = data_temp
                    workflow_state["last_update"] = time.time()
                
                # 执行节点（带重试）
                retry_num = node.get("ReTryNum", 0)
                success = False
                result = None
                
                while retry_num >= 0 and not success:
                    try:
                        # 检查是否应该跳过执行 (参考前端SKIP模式)
                        if trigger_link > 0 and recursion_behavior == "SKIP":
                            # 构造空输出 (和前端保持一致)
                            result = {
                                "output": [
                                    {
                                        "Num": -1, 
                                        "Context": "", 
                                        "Boolean": False,
                                        "prompt_tokens": 0,
                                        "completion_tokens": 0,
                                        "total_tokens": 0
                                    } 
                                    for _ in node.get("Outputs", [])
                                ]
                            }
                        else:
                            # 执行节点
                            processed_node = self._process_node(node)
                            result = self._execute_node(processed_node, workflow_id=str(workflow_id) if workflow_id is not None else None)
                        
                        # 处理输出
                        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], dict) and "error" in result[0]:
                            raise Exception(result[0]["error"])
                        
                        # 处理输出上下文
                        for out in result.get("output", []) or []:
                            if isinstance(out, dict):
                                out["Context"] = self._process_context(out.get("Context", ""))
                        
                        success = True
                        
                    except Exception as e:
                        retry_num -= 1
                        if retry_num < 0:
                            error_msg = f"节点运行失败: {str(e)}"
                            
                            # 更新节点错误状态
                            with result_lock:
                                self._update_node_status(data_temp, node_id, {
                                    "IsRunning": False,
                                    "IsError": True,
                                    "ErrorContext": error_msg
                                })
                            return None
                
                # 成功执行，返回结果用于数据传播
                return {"node": node, "result": result}
                
            except Exception as e:
                with result_lock:
                    self._update_node_status(data_temp, node_id, {
                        "IsRunning": False,
                        "IsError": True,
                        "ErrorContext": f"执行异常: {str(e)}"
                    })
                return None
        
        # 使用线程池并发执行所有节点（类似JS的Promise.all）
        workers = min(len(nodes_to_execute), self.max_workers)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # 提交所有任务
            # ✅ A. 进入线程前做深拷贝隔离（最关键）：禁止并发共享 node 引用
            futures = []
            for node in nodes_to_execute:
                try:
                    safe_node = copy.deepcopy(node)
                except Exception:
                    safe_node = dict(node or {})
                futures.append(executor.submit(execute_single_node, safe_node))
            
            # 等待所有任务完成
            executed_results = [future.result() for future in futures]
        
        # 处理执行结果并获取子节点
        child_nodes = self._process_execution_results(executed_results, all_nodes, all_edges, data_temp, workflow_state, result_lock)
        
        # 递归执行子节点（类似JS的childPromises逻辑）
        if child_nodes:
            self._execute_nodes_recursively(child_nodes, all_nodes, all_edges, data_temp, workflow_state)

    def _process_execution_results(self, executed_results, all_nodes, all_edges, data_temp, workflow_state, result_lock):
        """处理执行结果并传播数据到子节点"""
        child_nodes_to_execute = []
        
        for exec_result in executed_results:
            if exec_result is None:
                continue
                
            node = exec_result["node"]
            result = exec_result["result"]
            node_id = node["id"]
            
            with result_lock:
                # 更新节点状态为完成 (保持RecursionBehavior)
                self._update_node_status(data_temp, node_id, {
                    "IsRunning": False,
                    "isFinish": True,
                    "ErrorContext": "",
                    "IsError": False,
                    "RecursionBehavior": node.get("RecursionBehavior", "STOP")
                })
                
                # 更新节点输出
                output_list = result.get("output", []) or []
                self.dbg(f"🔍 [OUTPUT-UPDATE] 节点 {node.get('label', node.get('id'))} 的输出数量: {len(output_list)}")
                for idx, output in enumerate(output_list):
                    if not isinstance(output, dict):
                        self.dbg(f"⚠️ [OUTPUT-UPDATE] 节点 {node.get('label', node.get('id'))} 的输出 {idx} 不是字典，跳过: {type(output)}")
                        continue
                    if idx < len(node.get("Outputs", [])):
                        # 打印更新前的状态
                        old_output = node["Outputs"][idx].copy() if node["Outputs"][idx] else {}
                        node["Outputs"][idx].update(output)
                        # 打印更新后的状态
                        new_output = node["Outputs"][idx]
                        self.dbg(f"✅ [OUTPUT-UPDATE] 节点 {node.get('label', node.get('id'))} 的输出 {idx} 已更新:")
                        self.dbg(f"   更新前: Context={bool(old_output.get('Context'))}, Num={old_output.get('Num')}, Boolean={old_output.get('Boolean')}")
                        self.dbg(f"   更新后: Context={bool(new_output.get('Context'))}, Num={new_output.get('Num')}, Boolean={new_output.get('Boolean')}")
                        self.dbg(f"   更新数据: {output}")
                    else:
                        self.dbg(f"⚠️ [OUTPUT-UPDATE] 节点 {node.get('label', node.get('id'))} 的输出索引 {idx} 超出范围 (共有 {len(node.get('Outputs', []))} 个输出)")
                
                # 更新第一条输出的 token 信息（与前端保持一致）
                if result.get("output") and len(result["output"]) > 0 and len(node.get("Outputs", [])) > 0:
                    first_output = result["output"][0]
                    if isinstance(first_output, dict):
                        token_fields = ["prompt_tokens", "completion_tokens", "total_tokens"]
                        for field in token_fields:
                            if field in first_output:
                                node["Outputs"][0][field] = first_output[field]

                # Cap stored output contexts to avoid retaining huge strings in graph_data
                self._cap_output_context_in_place(node.get("Outputs", []))
                
                # 更新节点debug信息
                node["debug"] = self._cap_node_debug(result.get("debug", ""))
                
                # 标记节点已执行
                node["firstRun"] = False
                
                # 添加历史记录（与前端executeNode中的addHistory调用对齐）
                workflow_id = workflow_state.get("id") if isinstance(workflow_state, dict) else None
                if workflow_id:
                    self.dbg(f"📝 [NODE-COMPLETE] 节点执行完成: {node.get('label', node.get('id'))}")
                    self.dbg(f"📝 [NODE-COMPLETE] 输出数量: {len(result.get('output', []))}")
                    self.dbg(f"📝 [NODE-COMPLETE] Debug长度: {len(str(result.get('debug', '')))}")
                    self._add_history(workflow_id, node)
                
                # 🔥 关键：传播输出到连接的子节点
                linked_edges = [e for e in all_edges if e["source"] == node_id]
                
                for edge in linked_edges:
                    target_node = next((n for n in all_nodes if n["id"] == edge["target"]), None)
                    if target_node and not target_node.get("NodeKind", "").lower().endswith("trigger"):
                        # 传播输出数据到目标节点
                        source_idx = edge["sourceAnchor"] - len(node.get("Inputs", []))
                        target_idx = edge["targetAnchor"]
                        
                        if target_idx < len(target_node.get("Inputs", [])):
                            outputs_list = result.get("output", []) or []
                            # 期望的端口Id/name（来自源节点端口定义）
                            expected_id = None
                            if source_idx >= 0 and source_idx < len(node.get("Outputs", [])):
                                expected_id = node.get("Outputs", [])[source_idx].get("Id") or node.get("Outputs", [])[source_idx].get("name")
                            
                            # 优先用 offset 命中；否则按 Id/name 匹配；再兜底取第一项
                            output_val = {}
                            if source_idx >= 0 and source_idx < len(outputs_list):
                                output_val = outputs_list[source_idx] or {}
                            else:
                                candidate = None
                                if expected_id:
                                    for it in outputs_list:
                                        if isinstance(it, dict) and (it.get("Id") == expected_id or it.get("name") == expected_id):
                                            candidate = it
                                            break
                                if candidate is None and outputs_list:
                                    candidate = outputs_list[0]
                                output_val = candidate or {}
                            if not isinstance(output_val, dict):
                                output_val = self._coerce_to_dict(output_val) or {}
                            # 跨类型转换并写入目标输入
                            ik = target_node["Inputs"][target_idx].get("Kind", "")
                            conv_in = self._convert_between_kinds(output_val, ik)
                            if ik == "Num":
                                target_node["Inputs"][target_idx]["Num"] = conv_in.get("Num")
                            elif ik == "Boolean":
                                target_node["Inputs"][target_idx]["Boolean"] = conv_in.get("Boolean")
                            elif "String" in ik:
                                target_node["Inputs"][target_idx]["Context"] = conv_in.get("Context")
                            # 确保inputStatus存在
                            if "inputStatus" not in target_node:
                                target_node["inputStatus"] = [False] * len(target_node.get("Inputs", []))
                            target_node["inputStatus"][target_idx] = True
                        
                        # 处理触发器逻辑
                        if edge["targetAnchor"] == len(target_node.get("Inputs", [])) + len(target_node.get("Outputs", [])):
                            outputs = result.get("output", [])
                            trigger_result = outputs[source_idx] if source_idx < len(outputs) else {"Boolean": False}
                            if not isinstance(trigger_result, dict):
                                trigger_result = {"Boolean": False}
                            target_node["RecursionBehavior"] = "Run" if trigger_result.get("Boolean") else trigger_result.get("TriggerKind", "STOP")
                        
                        # 处理LLM提示词（为子节点）
                        if target_node.get("NodeKind", "").lower() == "llm":
                            # 仅生成本次执行所需提示词，不写回节点字段
                            _ = self._process_llm_prompt(target_node)
                        
                        # 将子节点加入待执行列表
                        if target_node not in child_nodes_to_execute:
                            child_nodes_to_execute.append(target_node)
                
                # 更新工作流状态
                workflow_state["graph_data"] = data_temp
                workflow_state["last_update"] = time.time()
                
                # 🔥 关键修复：确保更新立即同步到全局 workflows 字典
                # 因为 workflow_state 是 self.workflows[workflow_id] 的引用，所以这个更新应该已经生效
                # 但为了确保线程安全，我们再次显式同步
                workflow_id = workflow_state.get("id") if isinstance(workflow_state, dict) else None
                if workflow_id and workflow_id in self.workflows:
                    with self.lock:
                        # 确保全局状态与局部状态一致
                        self.workflows[workflow_id]["graph_data"] = data_temp
                        self.workflows[workflow_id]["last_update"] = time.time()
                        # 打印调试信息，确认 Outputs 已更新
                        if node and node.get("Outputs"):
                            outputs_info = []
                            for out in node.get("Outputs", []):
                                has_context = bool(out.get("Context"))
                                has_num = out.get("Num") is not None
                                has_bool = out.get("Boolean") is not None
                                outputs_info.append(f"Context={has_context}, Num={has_num}, Boolean={has_bool}")
                            self.dbg(f"✅ [SYNC] 节点 {node.get('label', node.get('id'))} 的 Outputs 已同步到全局状态: {outputs_info}")
        
        return child_nodes_to_execute
    
    def _process_node_connections(self, data_temp, trigger_node, output_data, workflow_id=None):
        """处理节点连接，传递输出数据（模拟前端 processNodeConnections）"""
        if trigger_node is None:
            self.dbg("[DEBUG] _process_node_connections: trigger_node is None, skip updating outputs")
            return data_temp
        
        # 🎯🎯🎯 数据传递调试 🎯🎯🎯
        self.dbg(f"🎯🎯🎯 [DATA-TRANSFER] _process_node_connections 被调用")
        self.dbg(f"🎯🎯🎯 [DATA-TRANSFER] trigger_node: {trigger_node.get('label', trigger_node.get('id'))}")
        self.dbg(f"🎯🎯🎯 [DATA-TRANSFER] output_data type: {type(output_data)}")
        self.dbg(f"🎯🎯🎯 [DATA-TRANSFER] output_data: {output_data}")
        if workflow_id is not None:
            self._log_event(workflow_id, f"🎯 [ROUTE] from={trigger_node.get('label', trigger_node.get('id'))} outputs={len(output_data) if isinstance(output_data, list) else 1}")
        
        # 后端风格：仅写回 offset 指向的输出端口；路由直接使用本次 output_data
        # 不再进行"广播写回所有输出端口"的操作
        
        # 创建节点和边的映射，减少循环查询
        edges = data_temp.get("edges", [])
        nodes = data_temp.get("nodes", [])
        
        node_edges_map = {}
        for edge in edges:
            if edge["source"] == trigger_node["id"]:
                if edge["target"] not in node_edges_map:
                    node_edges_map[edge["target"]] = []
                node_edges_map[edge["target"]].append(edge)
        
        # 优化节点处理
        for node in nodes:
            # 计算标签输入数量
            label_input_count = sum(1 for input_item in node.get("Inputs", []) if input_item.get("IsLabel"))
            
            # 获取当前节点的相关边
            relevant_edges = node_edges_map.get(node["id"], [])
            
            if relevant_edges:
                # 处理相关边
                for edge in relevant_edges:
                    # 与老版JS一致：offset=sourceAnchor-Inputs.length
                    offset = edge["sourceAnchor"] - len(trigger_node.get("Inputs", []))
                    self.dbg(f"🎯🎯🎯 [ROUTE] sourceAnchor: {edge['sourceAnchor']} → offset: {offset}")
                    if workflow_id is not None:
                        self._log_event(workflow_id, f"🎯 [ROUTE] edge {trigger_node.get('label','?')}[{offset}] → {node.get('label','?')}.{edge['targetAnchor']}")
                    if offset < 0 or offset >= len(trigger_node.get("Outputs", [])):
                        self.dbg(f"🎯🎯🎯 [ROUTE] offset 越界，跳过该边")
                        if workflow_id is not None:
                            self._log_event(workflow_id, f"⚠️ [ROUTE] 跳过(越界) offset={offset}")
                        continue
                    
                    # 取得 offset 对应输出端口
                    out_ports = trigger_node.get("Outputs", [])
                    out_port = out_ports[offset]
                    expected_id = out_port.get("Id") or out_port.get("name")
                    expected_name = out_port.get("name") or out_port.get("Id")
                    
                    # 从本次 output_data 取对应端口的数据
                    if isinstance(output_data, list):
                        if 0 <= offset < len(output_data):
                            item = output_data[offset]
                        else:
                            self.dbg(f"🎯🎯🎯 [ROUTE] output_data 为 list 但无该 offset，跳过")
                            if workflow_id is not None:
                                self._log_event(workflow_id, f"⚠️ [ROUTE] 跳过(无该offset) offset={offset}")
                            continue
                    elif isinstance(output_data, dict):
                        item = output_data
                        # 端口对齐校验（宽松校验 + 一致化）
                        got_id = (item.get("Id") or "").strip()
                        got_name = (item.get("name") or "").strip()
                        source_anchor = edge.get("sourceAnchor")
                        equiv_ids = {expected_id, f"Output{source_anchor}"}
                        id_ok = (not got_id) or (got_id in equiv_ids)
                        name_ok = (not got_name) or (got_name == expected_name)
                        if not (id_ok or name_ok):
                            self.dbg(f"🎯🎯🎯 [ROUTE] 端口Id不匹配，跳过。expected={expected_id} got={got_id}")
                            if workflow_id is not None:
                                self._log_event(workflow_id, f"⚠️ [ROUTE] 跳过(Id不匹配) expected={expected_id} got={got_id}")
                            continue
                        # ☆ 规范化：强制写回“正统”Id/Name，后续链路一致
                        item["Id"] = expected_id
                        item["name"] = expected_name
                    else:
                        self.dbg(f"🎯🎯🎯 [ROUTE] output_data 非法类型，跳过")
                        if workflow_id is not None:
                            self._log_event(workflow_id, f"⚠️ [ROUTE] 跳过(非法类型) type={type(output_data)}")
                        continue
                    
                    # 兼容解包：list[list[dict]] / list[dict] / dict 均可
                    def _coerce_dict(x):
                        # 使用统一的标量→字典转换，支持字符串/数字/布尔
                        d = self._coerce_to_dict(x)
                        return d

                    item_dict = _coerce_dict(item)
                    if not isinstance(item_dict, dict):
                        self.dbg(f"🎯🎯🎯 [ROUTE] 本次端口数据不是字典，跳过")
                        if workflow_id is not None:
                            self._log_event(workflow_id, f"⚠️ [ROUTE] 跳过(非字典) offset={offset}")
                        continue
                    
                    # 仅写回 offset 指向的输出端口（按 Kind）
                    kind = out_port.get("Kind", "")
                    conv = self._convert_between_kinds(item_dict, kind)
                    if kind == "Num":
                        out_port["Num"] = conv.get("Num")
                    elif kind == "Boolean":
                        out_port["Boolean"] = conv.get("Boolean")
                    elif "String" in kind:
                        out_port["Context"] = conv.get("Context")
                    self.dbg(f"🎯🎯🎯 [WRITE] 输出端口{offset}({out_port.get('name','')}) ← {item_dict}")
                    if workflow_id is not None:
                        self._log_event(workflow_id, f"✅ [WRITE:OUT] {trigger_node.get('label','?')}.{out_port.get('name','?')} ← offset={offset}")
                    
                    # 路由到目标输入（按 Kind）
                    target_idx = edge["targetAnchor"]
                    if target_idx < len(node.get("Inputs", [])):
                        input_item = node["Inputs"][target_idx]
                        ik = input_item.get("Kind", "")
                        # 仅在有效值时写入并标记就绪（避免 None 污染）
                        wrote = False
                        conv_in = self._convert_between_kinds(item_dict, ik)
                        if ik == "Num":
                            if conv_in.get("Num") is not None:
                                input_item["Num"] = conv_in.get("Num")
                                wrote = True
                        elif ik == "Boolean":
                            if conv_in.get("Boolean") is not None:
                                input_item["Boolean"] = conv_in.get("Boolean")
                                wrote = True
                        elif "String" in ik:
                            if conv_in.get("Context") is not None:
                                input_item["Context"] = conv_in.get("Context")
                                wrote = True
                        if wrote:
                            self.dbg(f"🎯🎯🎯 [WRITE] 输入端口{target_idx}({input_item.get('name','')}) ← {item_dict}")
                            if "inputStatus" not in node:
                                node["inputStatus"] = [False] * len(node.get("Inputs", []))
                            node["inputStatus"][target_idx] = True
                            if workflow_id is not None:
                                self._log_event(workflow_id, f"✅ [WRITE:IN] {node.get('label','?')}.Inputs[{target_idx}]({input_item.get('name','')}) 就绪")
                
                # 判断是否为起始节点：使用全图连接信息 + inputStatus
                inputs_len = len(node.get("Inputs", []))
                ready_flags = node.get("inputStatus", [False] * inputs_len)
                # 非必需且未连线的输入，视为天然就绪
                for i, inp in enumerate(node.get("Inputs", [])):
                    if inp.get("IsLabel", False):
                        ready_flags[i] = True
                    elif inp.get("Link", 0) == 0 and not inp.get("Isnecessary", False):
                        ready_flags[i] = True
                if inputs_len == 0 or all(ready_flags):
                    node["IsStartNode"] = True
                    if workflow_id is not None:
                        self._log_event(workflow_id, f"🌟 [START-NODE] {node.get('label','?')} 起始条件满足 (inputs={inputs_len}, ready={sum(1 for x in ready_flags if x)})")
        
        return data_temp
    
    def _update_node_outputs(self, node, output_data):
        """更新节点的 Outputs（模拟前端 UpdateNodeOutputs）"""
        # 🎯🎯🎯 输出更新调试 🎯🎯🎯
        self.dbg(f"🎯🎯🎯 [OUTPUT-UPDATE] _update_node_outputs 被调用")
        self.dbg(f"🎯🎯🎯 [OUTPUT-UPDATE] node: {node.get('label', node.get('id'))}")
        self.dbg(f"🎯🎯🎯 [OUTPUT-UPDATE] output_data type: {type(output_data)}")
        self.dbg(f"🎯🎯🎯 [OUTPUT-UPDATE] output_data: {output_data}")
        
        # 兼容空输出：直接跳过
        if output_data is None:
            self.dbg(f"🎯🎯🎯 [OUTPUT-UPDATE] output_data 为 None，跳过")
            return
        
        # 老JS语义：若是数组取第一个，否则用自身，写回所有Outputs
        d = output_data[0] if isinstance(output_data, list) and output_data else output_data
        if not isinstance(d, dict):
            self.dbg(f"🎯🎯🎯 [OUTPUT-UPDATE] 非字典输出，跳过写回")
            return
        
        for idx, output in enumerate(node.get("Outputs", [])):
            kind = output.get("Kind", "")
            if kind == "Num":
                output["Num"] = d.get("Num")
            elif kind == "Boolean":
                output["Boolean"] = d.get("Boolean")
            elif "String" in kind:
                output["Context"] = d.get("Context")
            self.dbg(f"🎯🎯🎯 [OUTPUT-UPDATE] 输出{idx}({output.get('name','')}) <- {d}")
    
    def start_workflow(self, workflow_id, graph_data, passivity_trigger_array=None, array_trigger_array=None):
        """启动工作流执行"""
        print(f"🚀 [START] 启动工作流: {workflow_id}")
        print(f"📊 [INIT] P队列={len(passivity_trigger_array or [])}, A队列={len(array_trigger_array or [])}")
        
        # ★ 修复：如果工作流已存在且未在运行，先清理它
        if workflow_id in self.workflows:
            current_status = self.workflows[workflow_id]["status"]
            if current_status in [WorkflowStatus.RUNNING, WorkflowStatus.PAUSED]:
                print(f"⚠️ [WARNING] 工作流已在运行: {workflow_id}")
                return {"error": "Workflow is already running or paused"}
            else:
                # 工作流已完成/错误/停止，清理它以便重新启动
                print(f"🧹 [CLEANUP] 清理现有工作流: {workflow_id}")
                self.cleanup_workflow(workflow_id)
        
        # 初始化工作流状态
        # 在启动前清理节点的临时对话历史和状态，确保每轮运行从干净状态开始
        # 同时清理持久化的 node["_state"]（否则 Timer 等触发器会沿用上一轮时间戳）
        try:
            self._clear_workflow_node_states(str(workflow_id))
        except Exception:
            pass
        cleaned_graph = copy.deepcopy(graph_data)
        try:
            for n in cleaned_graph.get("nodes", []):
                if isinstance(n, dict):
                    # 清理对话历史
                    if 'messages' in n:
                        n['messages'] = []
                    # 🔥 关键修复：清理节点内部状态，让 passivityTrigger 等节点从头开始
                    if '_state' in n:
                        del n['_state']
                        print(f"🧹 [CLEANUP] 清理节点状态: {n.get('label', n.get('id'))}")
        except Exception as _e_clean:
            print(f"[WF-START] 清理节点状态异常: {_e_clean}")
        passivity_len = len(passivity_trigger_array) if passivity_trigger_array else 0
        array_len = len(array_trigger_array) if array_trigger_array else 0
        
        self.workflows[workflow_id] = {
            "id": workflow_id,
            "status": WorkflowStatus.RUNNING,
            "graph_data": cleaned_graph,
            "start_time": time.time(),
            "last_update": time.time(),
            "error": None,
            "traceback": None,
            "queue_lengths": {"passivity": passivity_len, "array": array_len},
            "events": [],
            "pending_passivity_count": passivity_len,
            "pending_array_count": array_len,
            "child_summary": {"active": 0, "completed": 0, "failed": 0, "total": 0}
        }
        self.child_workflows.setdefault(workflow_id, set())
        self._refresh_parent_array_queue(workflow_id, array_len)
        
        nodes_cnt = len(graph_data.get("nodes", []))
        edges_cnt = len(graph_data.get("edges", []))
        has_p = any("passivityTrigger" in n.get("NodeKind", "") for n in graph_data.get("nodes", []))
        has_a = any("ArrayTrigger" in n.get("NodeKind", "") for n in graph_data.get("nodes", []))
        msg = f"🧭 [WF-START] nodes={nodes_cnt} edges={edges_cnt} hasP={has_p} hasA={has_a} Pq={passivity_len} Aq={array_len}"
        print(msg)
        self._log_event(workflow_id, msg)
        
        #print(f"Created workflow state for: {workflow_id}")
        #print(f"Available workflows now: {list(self.workflows.keys())}")
        
        # 创建停止事件
        self.stop_events[workflow_id] = threading.Event()
        
        # 添加开始历史记录
        self._add_history(workflow_id, 'Start')
        
        # 启动工作流线程
        thread = threading.Thread(
            target=self._execute_workflow_thread,
            args=(workflow_id, cleaned_graph, passivity_trigger_array or [], array_trigger_array or [])
        )
        thread.daemon = True
        thread.start()
        
        print(f"🚀 [WORKFLOW] 工作流线程已启动: {workflow_id}")
        return {"status": "started", "workflow_id": workflow_id}
    
    def pause_workflow(self, workflow_id):
        """
        暂停工作流执行（当前版本按“结束运行”处理，不保留可恢复的中间态）
        - 设计约束：现阶段不存在真正的“暂停后恢复”需求，点击暂停等效于停止。
        """
        print(f"🟡 [PAUSE->STOP] 收到暂停请求，按停止处理: {workflow_id}")
        # 直接委托给 stop_workflow，实现“暂停=结束运行”的语义
        return self.stop_workflow(workflow_id)
    
    def resume_workflow(self, workflow_id):
        """
        恢复工作流执行（当前版本不支持真正的恢复）
        - 由于“暂停”已经等同于“停止”，恢复不再有明确语义，这里直接返回错误提示。
        """
        print(f"⚠️ [RESUME] 收到恢复请求，但当前版本不支持恢复: {workflow_id}")
        return {"error": "Resume is not supported in current workflow mode"}
    
    def stop_workflow(self, workflow_id):
        """停止工作流执行"""
        print(f"🛑 [STOP] 停止工作流: {workflow_id}")
        
        if workflow_id not in self.workflows:
            return {"error": "Workflow not found"}
        
        if workflow_id in self.stop_events:
            self.stop_events[workflow_id].set()
            
        # 立即设置状态为停止，并复位 IsBlock（恢复为可编辑的图）
        if workflow_id in self.workflows:
            wf = self.workflows[workflow_id]
            try:
                self._reset_block_flags(wf.get("graph_data"))
            except Exception:
                pass
            wf["status"] = WorkflowStatus.STOPPED
            try:
                wf["done_ts"] = time.time()
            except Exception:
                pass
            print(f"✅ [STOPPED] 工作流已停止: {workflow_id}")
            self._stop_child_workflows(workflow_id)
            
        # 等待线程结束（减少等待时间，增加响应性）
        start_time = time.time()
        while (workflow_id in self.workflows and 
               self.workflows[workflow_id]["status"] == WorkflowStatus.STOPPED and
               time.time() - start_time < 2):  # 最多等待2秒
            time.sleep(0.05)  # 更频繁检查
        
        self._schedule_workflow_cleanup(workflow_id, delay=0)
        return {"status": "stopped", "workflow_id": workflow_id}
    
    def get_workflow_status(self, workflow_id):
        """获取工作流状态"""
        if workflow_id not in self.workflows:
            return {"error": f"Workflow not found: {workflow_id}"}
        
        workflow = self.workflows[workflow_id]
        
        # 检查工作流对象是否为None
        if workflow is None:
            return {"error": f"Workflow {workflow_id} is None (may have been cleaned up)"}
        
        try:
            # If done for long enough, clear graph_data to free memory (keeps empty stub for UI)
            try:
                self._maybe_clear_graph_after_done(workflow)
            except Exception:
                pass
            # 优先从统一写回的队列字段读取，避免线程内本地副本与全局字典不同步造成的滞后
            try:
                q = workflow.get("queues") or workflow.get("queue_lengths") or {}
                raw_pass = q.get("passivity", q.get("pending", 0))
                raw_arr  = q.get("array", 0)
                passivity_q = int(raw_pass) if str(raw_pass).isdigit() else (raw_pass if isinstance(raw_pass, (int, float)) else 0)
                array_q     = int(raw_arr)  if str(raw_arr).isdigit()  else (raw_arr  if isinstance(raw_arr,  (int, float)) else 0)
            except Exception:
                # 回退：根据全局 workflow 字典里的数组字段长度估算（可能是旧快照，仅作兜底）
                try:
                    passivity_q = len(workflow.get("passivity_trigger_array", []))
                except Exception:
                    passivity_q = 0
                try:
                    array_q = len(workflow.get("array_trigger_array", []))
                except Exception:
                    array_q = 0

            # 调试：打印返回给前端的 graph_data 中各节点状态
            try:
                nodes = workflow["graph_data"].get("nodes", [])
                node_states = []
                for n in nodes:
                    if n and n.get("label"):
                        state = "ERR" if n.get("IsError") else ("FIN" if n.get("isFinish") else ("RUN" if n.get("IsRunning") else "IDLE"))
                        node_states.append(f"{n.get('label')}({n.get('NodeKind', '?')[:3]})={state}")
                if node_states:
                    print(f"[RESP-TO-FE] wf={workflow_id} nodes={' '.join(node_states)}")
            except Exception:
                pass

            # 若数组队列或子工作流仍在运行，强制点亮 ArrayTrigger 节点，避免前端动画“全空闲”
            try:
                has_array_pending = array_q > 0
                child_summary = workflow.get("child_summary") or {}
                has_active_child = isinstance(child_summary, dict) and child_summary.get("active", 0) > 0
                if has_array_pending or has_active_child:
                    nodes = workflow["graph_data"].get("nodes", []) or []
                    touched = False
                    for n in nodes:
                        if not isinstance(n, dict):
                            continue
                        nk = str(n.get("NodeKind", "")).lower()
                        if "arraytrigger" in nk:
                            if n.get("IsRunning") is not True:
                                n["IsRunning"] = True
                                n["isFinish"] = False
                                n["IsError"] = False
                                touched = True
                    if touched:
                        workflow["last_update"] = time.time()
            except Exception:
                pass

            # 1) 计算轻量摘要（仅节点状态与输出核心值）
            import json, hashlib

            def _brief_graph_for_fp(graph_data: dict):
                nodes = (graph_data or {}).get("nodes", []) or []
                brief = []
                for n in nodes:
                    if not n:
                        continue
                    st = "E" if n.get("IsError") else ("F" if n.get("isFinish") else ("R" if n.get("IsRunning") else "I"))
                    outs = []
                    for o in (n.get("Outputs") or []):
                        outs.append({
                            "C": o.get("Context"),
                            "N": o.get("Num"),
                            "B": o.get("Boolean"),
                        })
                    brief.append({"id": n.get("id"), "st": st, "outsLen": len(outs), "outs": outs})
                return brief

            def _make_fp(graph_data: dict) -> str:
                brief = _brief_graph_for_fp(graph_data)
                s = json.dumps(brief, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                return hashlib.sha1(s.encode("utf-8")).hexdigest()

            # 2) 为当前图计算/更新指纹 —— 改为：只在未设置时计算一次
            try:
                fp = workflow.get("ring_fingerprint")
                if not fp:
                    fp = _make_fp(workflow["graph_data"])
                    workflow["graph_data"]["fingerprint"] = fp
                    workflow["ring_fingerprint"] = fp
            except Exception:
                fp = None

            result = {
                "status": workflow["status"],
                "start_time": workflow["start_time"],
                "last_update": workflow["last_update"],
                "error": workflow.get("error"),
                "traceback": workflow.get("traceback"),
                "graph_data": workflow["graph_data"],
                "queue_lengths": {"passivity": passivity_q, "array": array_q},
                # 固定字段：queues 供前端直接读取，减少字段名差异导致的问题
                "queues": {"pending": passivity_q, "array": array_q},
                "events": workflow.get("events", []),
                # 新增：统一字段名给前端
                "ringFingerprint": workflow.get("ring_fingerprint"),
                "isChild": workflow.get("is_child", False),
                "parentId": workflow.get("parent_id"),
            }
            # --- UI system monitor metrics (short names) ---
            try:
                sysmon = self._get_sysmon_metrics_cached()
                if isinstance(sysmon, dict):
                    result["ConnNow"] = sysmon.get("ConnNow")
                    result["TWNow"] = sysmon.get("TWNow")
                    result["PortUse"] = sysmon.get("PortUse")
            except Exception:
                # keep status endpoint resilient
                result["ConnNow"] = None
                result["TWNow"] = None
                result["PortUse"] = None
            if workflow.get("child_summary"):
                result["childSummary"] = workflow.get("child_summary")
            return result
        except Exception as e:
            import traceback
            return {"error": f"Error getting workflow status: {e}", "traceback": traceback.format_exc()}
    
    def cleanup_workflow(self, workflow_id):
        """清理工作流资源（包含其批次工作流）"""
        # 重要：
        # - 旧逻辑只删除 self.workflows/stop_events/timer 等“核心运行态”
        # - 但 workflow.py 里还有大量“伴生缓存/侧表”（history buffer、throttle、array index、node state 等）
        #   这些如果不清理，特别是在 ArrayTrigger 启动大量 child workflow 时，会导致内存持续增长。
        # 这里统一走 _runtime_cleanup，确保每个 workflow_id 都能彻底释放关联缓存。
        try:
            wid0 = str(workflow_id or "")
        except Exception:
            wid0 = workflow_id

        ids_to_clean = set()
        # A) 在锁内计算需要清理的 workflow_id 集合，并清理父子引用关系
        with self.lock:
            related_ids = self._collect_related_workflow_ids(wid0)
            ids_to_clean.update(related_ids or set())

            # 若 workflow_id 是父：把它的 child 一并纳入清理集合
            child_ids = self.child_workflows.pop(wid0, set())
            for cid in (child_ids or set()):
                ids_to_clean.add(cid)
                self.parent_map.pop(cid, None)

            # 若 workflow_id 是子：从父的 children 集合中移除（兜底）
            parent_id = self.parent_map.pop(wid0, None)
            if parent_id:
                siblings = self.child_workflows.get(parent_id)
                if siblings and wid0 in siblings:
                    siblings.discard(wid0)
                if siblings is not None and len(siblings) == 0:
                    self.child_workflows.pop(parent_id, None)

            # 尽量先发出 stop 信号（避免清理过程中仍有线程写入状态）
            for wid in list(ids_to_clean):
                try:
                    ev = self.stop_events.get(wid)
                    if ev:
                        ev.set()
                except Exception:
                    pass

        # B) I/O（history flush）放在锁外，避免阻塞其它请求
        for wid in list(ids_to_clean):
            try:
                self._flush_history_buffer_for_workflow(wid)
            except Exception:
                pass

        # C) 真正清理：取消 timer + 删除运行态 + 清理侧表/缓存
        with self.lock:
            for wid in list(ids_to_clean):
                try:
                    t = self._cleanup_timers.pop(wid, None)
                    if t:
                        try:
                            t.cancel()
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    self._runtime_cleanup(wid)
                except Exception:
                    # 兜底：至少保证核心字典被移除
                    try:
                        self.workflows.pop(wid, None)
                    except Exception:
                        pass
                    try:
                        self.stop_events.pop(wid, None)
                    except Exception:
                        pass

        return {"status": "cleaned", "workflow_id": wid0}

# 创建全局工作流引擎实例
workflow_engine = None

def init_workflow_engine(base_dir=None):
    """初始化工作流引擎"""
    global workflow_engine
    if workflow_engine is None:
        workflow_engine = WorkflowEngine(base_dir)
    return workflow_engine

def get_workflow_engine():
    """获取工作流引擎实例"""
    global workflow_engine
    if workflow_engine is None:
        workflow_engine = WorkflowEngine()
    return workflow_engine

# 对外接口函数
def start_workflow(workflow_id, graph_data, passivity_trigger_array=None, array_trigger_array=None):
    """启动工作流"""
    engine = get_workflow_engine()
    return engine.start_workflow(workflow_id, graph_data, passivity_trigger_array, array_trigger_array)

def pause_workflow(workflow_id):
    """暂停工作流"""
    engine = get_workflow_engine()
    return engine.pause_workflow(workflow_id)

def resume_workflow(workflow_id):
    """恢复工作流"""
    engine = get_workflow_engine()
    return engine.resume_workflow(workflow_id)

def stop_workflow(workflow_id):
    """停止工作流"""
    engine = get_workflow_engine()
    return engine.stop_workflow(workflow_id)

def get_workflow_status(workflow_id):
    """获取工作流状态"""
    engine = get_workflow_engine()
    return engine.get_workflow_status(workflow_id)

def cleanup_workflow(workflow_id):
    """清理工作流资源"""
    engine = get_workflow_engine()
    return engine.cleanup_workflow(workflow_id)

def run_node(node):
    """直接运行单个节点（用于测试）"""
    engine = get_workflow_engine()
    processed_node = engine._process_node(node)
    return engine._execute_node(processed_node)

def get_node_debug(workflow_id, node_id):
    """获取指定工作流中某个节点的 debug 输出"""
    engine = get_workflow_engine()
    return engine.get_node_debug(workflow_id, node_id)