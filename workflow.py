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
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import base64
import os
import hashlib
import uuid

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

class WorkflowEngine:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or Path(".")
        # 全局状态锁（工作流字典等）
        self.lock = threading.Lock()
        # 历史文件写入锁（避免并发读改写导致记录丢失/文件损坏）
        self._history_lock = threading.Lock()
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

    def _log_event(self, workflow_id, message: str):
        """记录可供前端查看的事件日志（最多100条）"""
        try:
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
            # 打印调试信息
            print(f"📝 [HISTORY] 添加历史记录 - 工作流: {workflow_id}")
            name = node_data if isinstance(node_data, str) else node_data.get('label', node_data.get('id', 'Unknown'))
            print(f"📝 [HISTORY] 节点数据: {name}")
            
            if node_data == 'Start':
                # 开始新对话
                filtered_data = {'message': 'New conversation started'}
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
                        selected_field = {'Context': item.get('Context')}
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
                        selected_field = {'Context': item.get('Context')}
                    elif 'Boolean' in item.get('Kind', ''):
                        selected_field = {'Boolean': item.get('Boolean')}
                    elif 'Num' in item.get('Kind', ''):
                        selected_field = {'Num': item.get('Num')}
                    
                    filtered_data['Inputs'].append({
                        'name': item.get('name'),
                        'Kind': item.get('Kind'),
                        **selected_field
                    })
                
                print(f"📝 [HISTORY] 过滤后的数据: {json.dumps(filtered_data, ensure_ascii=False, indent=2)}")
            
            # 过滤不需要的 array 子工作流历史
            if "__array_" in str(workflow_id):
                try:
                    skip_root = self.BASE_DIR / "History"
                    for p in skip_root.rglob(f"{workflow_id}.json"):
                        try:
                            p.unlink()
                        except Exception:
                            pass
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

            with self._history_lock:
                # 读取现有数据
                if file_path.exists():
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            json_data = json.load(f)
                    except (json.JSONDecodeError, Exception) as e:
                        print(f"⚠️ [HISTORY] 读取历史文件失败: {e}")
                        json_data = []
                else:
                    json_data = []
                
                # 添加到历史记录
                if not json_data or not isinstance(json_data[-1], list):
                    json_data.append([])
                
                json_data[-1].append(filtered_data)
                
                # 保存文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ [HISTORY] 历史记录已保存到: {file_path}")
            
        except Exception as e:
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
            nodes = graph_data.get("nodes", [])
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
            payload = {"nodes": nodes}
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            try:
                print(f"[HISTORY:SAVE] {fp}")
            except Exception:
                pass
        except Exception as _e_hist:
            try:
                print(f"[HISTORY:SAVE:ERR] {str(_e_hist)}")
            except Exception:
                pass
    
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

        # 2.2 system_prompt 生成
        system_prompt = f"{node.get('SystemPrompt', '')}\n{node.get('ExprotAfterPrompt', '')}"
        if node.get("OriginalTextSelector") == "OriginalText":
            system_prompt = node.get("SystemPrompt", "")

        # 直接使用节点的 prompt 作为 ExportPrompt（不做模板替换）
           # ---------- 2.2.1 处理 prompt 模板替换（关键步骤！） ----------
        # 构建 ExprotAfterPrompt（如果需要）
        if node_kind == "LLm" and not node.get('ExprotAfterPrompt'):
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

        # 更新节点的 ExportPrompt（保留原始 prompt，不回写覆盖）
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

        # 2.4 写回到 node，避免覆盖旧键，改用 CombinedMessages
        node["messages"] = msg_list
        
        return node
    
    def _image_to_base64(self, fp: str) -> str:
        """将图片转换为base64编码"""
        fp = Path(fp).expanduser().resolve()
        with open(fp, "rb") as f:
            return base64.b64encode(f.read()).decode()
    
    def _execute_node(self, node):
        """执行单个节点（完全从app.py迁移的逻辑）"""
        node_name = node.get("name")
        print(f"🔧 [EXECUTE] 开始执行节点: {node.get('label', node.get('id'))} ({node_name})")
        print(f"🔧 [EXECUTE] 节点类型: {node.get('NodeKind')}")
        print(f"🔧 [EXECUTE] 输入数量: {len(node.get('Inputs', []))}")
        print(f"🔧 [EXECUTE] 输出数量: {len(node.get('Outputs', []))}")
        
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

        # 2.2 在执行阶段再次进行占位符替换（兜底）
        try:
            template_text_exec = node.get("prompt") or node.get("ExportPrompt", "") or ""
            export_prompt_exec = template_text_exec
            exec_matches = retrieve_content_within_braces(template_text_exec)

            def _replace_token_exec(text, token, value):
                try:
                    return re.sub(r'{{\s*' + re.escape(token) + r'\s*}}', value if value is not None else "", text)
                except Exception:
                    return text

            for match in exec_matches:
                for input_item in node.get("Inputs", []) or []:
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
                        export_prompt_exec = _replace_token_exec(export_prompt_exec, token, val)
                        break

            if '{{' in export_prompt_exec and '}}' in export_prompt_exec:
                leftovers = retrieve_content_within_braces(export_prompt_exec)
                for token in leftovers:
                    export_prompt_exec = _replace_token_exec(export_prompt_exec, token, "")
            node["ExportPrompt"] = export_prompt_exec
        except Exception:
            pass

        # 2.3 system_prompt 生成
        system_prompt = f"{node.get('SystemPrompt', '')}\n{node.get('ExprotAfterPrompt', '')}"
        if node.get("OriginalTextSelector") == "OriginalText":
            system_prompt = node.get("SystemPrompt", "")

        # 2.4 拼接消息列表
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

        # 2.5 写回到 node，避免覆盖旧键，改用 CombinedMessages
        node["messages"] = msg_list
        try:
            print(f"[DEBUG:EXEC_NODE] ExportPrompt before send → {node.get('ExportPrompt')}")
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
        node_kind = node.get("NodeKind")
        tools = node.get("Tools")
        is_react = node.get("IsReact")

        if node_kind == "LLm" and tools is not None and is_react is True:
            try:
                langgraph_agent_path = (self.BASE_DIR / "Langgraph" / "Agent.py").resolve()
                if not langgraph_agent_path.is_file():
                    return {"error": f"Langgraph/Agent.py not found at {langgraph_agent_path}"}, 404

                with self.lock:
                    spec   = importlib.util.spec_from_file_location("langgraph_agent", langgraph_agent_path)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)

                result = module.run_node(node)
                output, debug_text = normalize_result(result)

                result_data = {
                    "output":       output,
                    "debug":        debug_text,
                    "inputs":       node.get("Inputs", []),
                    "ExportPrompt": node.get("ExportPrompt"),
                }
                
                # 打印执行结果
                print(f"✅ [EXECUTE] LangGraph节点执行完成: {node.get('label', node.get('id'))}")
                print(f"✅ [EXECUTE] 输出数量: {len(output)}")
                print(f"✅ [EXECUTE] Debug长度: {len(debug_text)}")
                if output:
                    print(f"✅ [EXECUTE] 第一个输出预览: {str(output[0])[:100]}..." if len(str(output[0])) > 100 else f"✅ [EXECUTE] 第一个输出: {output[0]}")
                
                # 添加指纹日志
                try:
                    outs = result_data.get("output") if isinstance(result_data, dict) else None
                    fp = self._calc_fp(node.get("id"), outs)
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
            with self.lock:
                spec   = importlib.util.spec_from_file_location(script_path.stem, script_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

            # ★ 新增：执行前解析别名，确保工具收到绝对路径
            node = self._resolve_aliases_in_node(node)

            result = module.run_node(node)
            output, debug_text = normalize_result(result)

            result = {
                "output":       output,
                "debug":        debug_text,
                "inputs":       node.get("Inputs", []),
                "ExportPrompt": node.get("ExportPrompt"),
            }
            
            # 打印执行结果
            print(f"✅ [EXECUTE] 节点执行完成: {node.get('label', node.get('id'))}")
            print(f"✅ [EXECUTE] 输出数量: {len(output)}")
            print(f"✅ [EXECUTE] Debug长度: {len(debug_text)}")
            if output:
                print(f"✅ [EXECUTE] 第一个输出预览: {str(output[0])[:100]}..." if len(str(output[0])) > 100 else f"✅ [EXECUTE] 第一个输出: {output[0]}")
            
                # 添加指纹日志
                try:
                    outs = result.get("output") if isinstance(result, dict) else None
                    fp = self._calc_fp(node.get("id"), outs)
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
        with self.lock:
            # 检查工作流是否存在且不为None
            if workflow_id not in self.workflows:
                return
                
            if self.workflows[workflow_id] is None:
                return
            
            try:
                # 允许 data_temp 为 None：仅刷新队列长度与时间戳
                if data_temp is None:
                    print(f"[STATE] (partial) 仅刷新队列长度: workflow_id={workflow_id}")
                else:
                    # 打印状态更新信息
                    nodes_count = len(data_temp.get("nodes", []))
                    edges_count = len(data_temp.get("edges", []))
                    print(f"🔄 [STATE] 更新工作流状态: {workflow_id}")
                    print(f"🔄 [STATE] 节点数量: {nodes_count}, 边数量: {edges_count}")
                    self.workflows[workflow_id]["graph_data"] = data_temp
                self.workflows[workflow_id]["last_update"] = time.time()
                
                # 更新队列长度（允许部分更新）
                qlens = self.workflows[workflow_id].get("queue_lengths", {"passivity": 0, "array": 0}).copy()
                if local_passivity_array is not None:
                    qlens["passivity"] = len(local_passivity_array)
                    print(f"🔄 [STATE] 被动队列长度: {len(local_passivity_array)}")
                if local_array_trigger_array is not None:
                    qlens["array"] = len(local_array_trigger_array)
                    print(f"🔄 [STATE] 数组队列长度: {len(local_array_trigger_array)}")
                self.workflows[workflow_id]["queue_lengths"] = qlens
                # 同步写入固定字段 queues，方便前端直接读取
                self.workflows[workflow_id]["queues"] = {"pending": qlens.get("passivity", 0), "array": qlens.get("array", 0)}
                if local_passivity_array is not None:
                    self.workflows[workflow_id]["pending_passivity_count"] = len(local_passivity_array)
                if local_array_trigger_array is not None:
                    self.workflows[workflow_id]["pending_array_count"] = len(local_array_trigger_array)
                    self._refresh_parent_array_queue(workflow_id, len(local_array_trigger_array))
                try:
                    print(f"[STATE:QUEUES] write queue_lengths={{P:{qlens.get('passivity',0)}, A:{qlens.get('array',0)}}} queues={{pending:{self.workflows[workflow_id]['queues'].get('pending',0)}, array:{self.workflows[workflow_id]['queues'].get('array',0)}}}")
                except Exception:
                    pass
                
                print(f"✅ [STATE] 工作流状态更新完成")
                    
            except Exception as e:
                import traceback
                print(f"❌ [ERROR] _update_workflow_state failed: {e}")
                print(f"❌ [ERROR] Traceback: {traceback.format_exc()}")
    
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
            local_passivity_array = copy.deepcopy(passivity_trigger_array)
            local_array_trigger_array = copy.deepcopy(array_trigger_array)
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
                    print(msg)
                    self._log_event(workflow_id, msg)
                    print(f"[ARRAY-DEBUG] 处理前 ArrayTrigger 队列长度: {before_len}")
                    print(f"[ARRAY-DEBUG] 队列内容预览: {[item.get('nodeId', 'unknown') for item in local_array_trigger_array[:3]]}")
                    self._process_next_array_trigger(workflow_id, data_temp, local_array_trigger_array, workflow_state)
                    after_len = len(local_array_trigger_array)
                    print(f"[ARRAY-DEBUG] 处理后 ArrayTrigger 队列长度: {after_len} (处理了 {before_len - after_len} 个)")
                    
                    # 立即更新状态，确保前端能及时看到队列变化
                    self._update_workflow_state(workflow_id, None, local_array_trigger_array=local_array_trigger_array)
                    print(f"🔴 [ARRAY-DEBUG] 状态已更新，当前数组队列长度: {len(local_array_trigger_array)}")
                    print(f"🔴 [ARRAY-DEBUG] 更新时间: {time.strftime('%H:%M:%S')}")
                    
                    did_work = True
                    had_non_empty_since_last_preheat = True

                # 2. 再处理 Passivity（它可能继续向 Array 队列投喂数据）
                elif local_passivity_array:
                    msg = f"🔵 [PASSIVITY] size={len(local_passivity_array)}"
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
                    
                    # 修复：按照前端逻辑，只有当 passivityData.outputData 存在时才处理
                    if passivity_node and passivity_data.get("outputData"):
                        # 使用克隆图在本地处理，避免污染全局
                        local_data_for_pass = copy.deepcopy(data_temp)
                        self._log_event(workflow_id, "🎯 [PASS] 使用克隆图处理当前队列项")
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
                    print(msg)
                    self._log_event(workflow_id, msg)
                    self._run_passivity_trigger_nodes(workflow_id, data_temp, local_passivity_array)
                    did_preheat_passivity = True
                    did_work = True
                
                # 4. 若两个队列都为空
                elif not local_passivity_array and not local_array_trigger_array:
                    if self._has_active_children(workflow_id):
                        self._log_event(workflow_id, "🟢 [CHILD] 等待子工作流完成...")
                        time.sleep(0.3)
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
                
                # 添加延迟，确保前端能看到每一步队列变化
                time.sleep(0.3)
                
                # 仅在有实际工作发生时更新last_update，避免空转刷新
                if did_work:
                    workflow_state["last_update"] = time.time()
        
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
                result = self._execute_node(processed_node)
                
                self._log_event(workflow_id, f"   └─ result.count={(len(result.get('output')) if isinstance(result, dict) and isinstance(result.get('output'), list) else ('1' if isinstance(result, dict) and result.get('output') is not None else 0))}")
                
                # 写回 debug
                if isinstance(result, dict):
                    node["debug"] = result.get("debug", "")
                
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
                
                # 运行完成，更新状态
                self._update_node_status(data_temp, node["id"], {"IsRunning": False, "isFinish": True, "IsError": False, "ErrorContext": ""})
                self._update_workflow_state(workflow_id, data_temp)
                
                # 添加历史记录
                print(f"📝 [PASSIVITY-COMPLETE] 被动触发节点完成: {node.get('label', node.get('id'))}")
                print(f"📝 [PASSIVITY-COMPLETE] 输出数量: {len(result.get('output', [])) if isinstance(result, dict) else 0}")
                self._add_history(workflow_id, node)

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
            print(f"🎯🎯🎯 [PASSIVITY-LOAD] 原始输出结构: {type(output_list)} → 归一化后组数={len(filtered_outputs)}")
        except Exception:
            pass
        if not filtered_outputs:
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
                        print("🌀 [RING:OVERWRITE] Passivity 覆盖上一条记录 (相同指纹)")
                        replaced = True
                        break
                if not replaced:
                    passivity_trigger_array.append(item)
                    print("✅ [RING:PUSH] Passivity 覆盖失败，退化为新增记录到环")
            else:
                passivity_trigger_array.append(item)
                self._last_ring_fp[key] = fp
                print(f"✅ [RING:PUSH] Passivity 入队消息组 {idx+1}/{len(filtered_outputs)}")
            enqueued += 1

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
        
        # 第二阶段：找到连接到 ArrayTrigger 节点的上游节点
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
        self._log_event(workflow_id, f"🔴 [DEBUG] 找到 {len(connect_nodes)} 个上游节点")
        for i, node in enumerate(connect_nodes):
            self._log_event(workflow_id, f"🔴 [DEBUG] 上游节点{i}: {node.get('label', node.get('id'))}")
        
        # 第三阶段：处理所有上游节点
        self._log_event(workflow_id, f"🔴 [DEBUG] 开始处理 {len(connect_nodes)} 个上游节点")
        
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
                result = self._execute_node(processed_node)
                self._log_event(workflow_id, f"🔴 [DEBUG] 上游节点结果: {result}")
                # 检查是否有有效输出用于传递给下游
                if isinstance(result, dict) and result.get("output") and result["output"] != [None]:
                    self._log_event(workflow_id, f"🔴 [DEBUG] 上游节点有有效输出，将传播给下游")
                else:
                    self._log_event(workflow_id, f"🔴 [DEBUG] 上游节点无有效输出，ArrayTrigger将收不到数据")
                
                # 写回 debug
                if isinstance(result, dict):
                    node["debug"] = result.get("debug", "")
                
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
                
                # 执行节点（先做最小输入就绪校验：若存在必需输入且 Context/Num/Boolean 全为空则跳过）
                inputs_ready_min = True
                for inp in node.get("Inputs", []):
                    if inp.get("Isnecessary"):
                        kind = inp.get("Kind", "")
                        if kind == "Num" and inp.get("Num") is None:
                            inputs_ready_min = False
                            break
                        if kind == "Boolean" and inp.get("Boolean") is None:
                            inputs_ready_min = False
                            break
                        if "String" in kind and inp.get("Context") is None:
                            inputs_ready_min = False
                            break
                if not inputs_ready_min:
                    self._log_event(workflow_id, "🔴 [DEBUG] ArrayTrigger 输入未就绪，跳过本次执行")
                    self._update_node_status(data_temp, node["id"], {"IsRunning": False})
                    continue
                # 执行节点
                processed_node = self._process_node(node)
                self._log_event(workflow_id, f"🔴 [DEBUG] processed_node name: {processed_node.get('name')}")
                result = self._execute_node(processed_node)
                self._log_event(workflow_id, f"🔴 [DEBUG] execute_node result: {result}")
                
                # 写回 debug
                if isinstance(result, dict):
                    node["debug"] = result.get("debug", "")
                
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
                        print("[ARRAY-DEBUG] 归一化：检测到单行的 Outputs，被包裹为 1 个数组元素")
                    # 归一化后再输出一遍统计信息
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
                    self._log_event(workflow_id, f"🔴 [DEBUG] ArrayTrigger 原始输出数量: {len(original_outputs)}")
                    
                    # 🔥 关键修复：ArrayTrigger 的 output 是嵌套数组结构
                    # 每个子数组代表一个完整的输出组，应该作为一个队列项
                    for idx, array_group in enumerate(original_outputs):
                        if array_group is None:
                            continue
                        
                        node_id = node["id"]
                        group = copy.deepcopy(array_group)
                        fp = self._calc_fp(node_id, group)            # ← 新增
                        key = (workflow_id, node_id)
                        last_fp = self._last_ring_fp.get(key)
                        item = {"outputData": group, "nodeId": node_id, "graph_data": copy.deepcopy(data_temp)}

                        if last_fp == fp:
                            # 深度调试：指纹重复情况
                            try:
                                self._log_event(workflow_id, f"🌀 [ARRAY-FP] group[{idx}] fp={fp} 与上次相同 → 覆盖队列中该节点最后一条")
                            except Exception:
                                pass
                            # 覆盖队列中该节点的最后一条
                            for j in range(len(array_trigger_array)-1, -1, -1):
                                if array_trigger_array[j].get("nodeId") == node_id:
                                    array_trigger_array[j] = item
                                    self._log_event(workflow_id, "🌀 [RING:OVERWRITE] ArrayTrigger 覆盖上一条记录 (相同指纹)")
                                    break
                            else:
                                array_trigger_array.append(item)
                                self._log_event(workflow_id, "✅ [RING:PUSH] ArrayTrigger 覆盖失败，退化为新增记录到环")
                        else:
                            array_trigger_array.append(item)
                            self._last_ring_fp[key] = fp               # ← 新增
                            try:
                                self._log_event(workflow_id, f"✅ [RING:PUSH] ArrayTrigger 入队数组组 {idx+1}/{len(original_outputs)} fp={fp}")
                            except Exception:
                                pass
                    
                    self._log_event(workflow_id, f"🔴 [DEBUG] ArrayTrigger 总共入队 {len([x for x in original_outputs if x is not None])} 个数组组")
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
    
    def _run_array_trigger_nodes(self, workflow_id, data_temp, array_trigger_array):
        """运行 ArrayTrigger 节点（模拟前端 runArrayTriggerNodes）"""
        nodes = data_temp.get("nodes", [])
        count = 0
        
        nodes_to_process = [node for node in nodes if "ArrayTrigger" in node.get("NodeKind", "")]
        
        for node in nodes_to_process:
            try:
                # 标记运行中
                with self.lock:
                    self._update_node_status(data_temp, node["id"], {"IsRunning": True, "IsError": False})
                    self.workflows[workflow_id]["graph_data"] = data_temp
                    self.workflows[workflow_id]["last_update"] = time.time()
                
                # 执行节点
                processed_node = self._process_node(node)
                result = self._execute_node(processed_node)
                
                # 写回 debug
                if isinstance(result, dict):
                    node["debug"] = result.get("debug", "")
                
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
                        print(f"[ARRAY-TRACE] node={node.get('label', node.get('id'))} raw_type={type(raw)} raw_len={raw_len}")
                        if isinstance(raw, list):
                            for i, g in enumerate(raw):
                                if isinstance(g, list):
                                    print(f"   └─ raw[{i}] is list, size={len(g)}")
                                elif isinstance(g, dict):
                                    keys = list(g.keys())
                                    print(f"   └─ raw[{i}] is dict, keys={keys}")
                                else:
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
                        print("[ARRAY-DEBUG] 归一化：检测到单行的 Outputs，被包裹为 1 个数组元素")
                    # 归一化后再输出一遍统计信息
                    try:
                        print(f"[ARRAY-TRACE] 标准化后组数(original_outputs.len) = {len(original_outputs)}")
                        for gi, g in enumerate(original_outputs):
                            if isinstance(g, list):
                                ids = []
                                for it in g:
                                    if isinstance(it, dict):
                                        ids.append(it.get('Id') or it.get('name'))
                                print(f"   └─ group[{gi}] size={len(g)} ids={ids}")
                            else:
                                print(f"   └─ group[{gi}] type={type(g)} value_preview={str(g)[:80]}")
                    except Exception:
                        pass
                    print(f"[ARRAY-DEBUG] ArrayTrigger 原始输出数量: {len(original_outputs)}")
                    
                    # 🔥 关键修复：ArrayTrigger 的 output 是嵌套数组结构
                    # 每个子数组代表一个完整的输出组，应该作为一个队列项
                    enqueued_count = 0
                    for idx, array_group in enumerate(original_outputs):
                        if array_group is None:
                            continue
                        
                        node_id = node["id"]
                        group = copy.deepcopy(array_group)
                        fp = self._calc_fp(node_id, group)            # ← 新增
                        key = (workflow_id, node_id)
                        last_fp = self._last_ring_fp.get(key)
                        item = {"outputData": group, "nodeId": node_id, "graph_data": copy.deepcopy(data_temp)}

                        if last_fp == fp:
                            # 覆盖队列中该节点的最后一条
                            for j in range(len(array_trigger_array)-1, -1, -1):
                                if array_trigger_array[j].get("nodeId") == node_id:
                                    array_trigger_array[j] = item
                                    print(f"🌀 [RING:OVERWRITE] ArrayTrigger 覆盖上一条记录 (相同指纹) fp={fp} group_idx={idx}")
                                    break
                            else:
                                array_trigger_array.append(item)
                                print(f"✅ [RING:PUSH] ArrayTrigger 覆盖失败，退化为新增记录到环 fp={fp} group_idx={idx}")
                        else:
                            array_trigger_array.append(item)
                            self._last_ring_fp[key] = fp               # ← 新增
                            print(f"✅ [RING:PUSH] ArrayTrigger 入队数组组 {idx+1}/{len(original_outputs)} fp={fp} group_idx={idx}")
                        
                        enqueued_count += 1
                    
                    print(f"[ARRAY-DEBUG] ArrayTrigger 总共入队 {enqueued_count} 个数组组")
                    if enqueued_count == 0:
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
            print(f"[ARRAY-DEBUG] 开始处理 ArrayTrigger 数据: nodeId={array_data.get('nodeId')}")
            print(f"[ARRAY-DEBUG] 当前队列总长度: {len(array_trigger_array)}")
            print(f"[ARRAY-DEBUG] 处理的数据类型: {type(array_data.get('outputData'))}")
            if isinstance(array_data.get('outputData'), list):
                print(f"[ARRAY-DEBUG] 输出数据长度: {len(array_data.get('outputData', []))}")
            self._log_event(workflow_id, f"   └─ headKeys={(list(array_data.keys()) if isinstance(array_data, dict) else type(array_data))}")
            
            # 检查 array_data 是否为 None；当 outputData 为空但带有 graph_data（占位项，用于无 ArrayTrigger 的场景）时，不丢弃
            if array_data is None or (array_data.get("outputData") is None and "graph_data" not in array_data):
                self._log_event(workflow_id, "❌ array_data 无效（无 outputData 且无 graph_data）→ DROP & POP")
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
                batch_size = min(parallel_limit, len(array_trigger_array))
                batch_data = array_trigger_array[:batch_size]
                launched = 0
                for idx, batch_item in enumerate(batch_data):
                    try:
                        child_graph = self._prepare_child_graph(workflow_id, data_temp, batch_item)
                        if child_graph is None:
                            continue
                        self._start_child_workflow(workflow_id, child_graph, batch_item)
                        launched += 1
                    except Exception as e:
                        print(f"[ARRAY-DEBUG] 子工作流启动失败: {e}")
                        self._log_event(workflow_id, f"❌ [CHILD] 子工作流启动失败: {e}")
                for _ in range(batch_size):
                    if array_trigger_array:
                        array_trigger_array.pop(0)
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
                        print(f"[ARRAY-DEBUG] 找到 ArrayTrigger 节点: {array_node.get('label', array_node.get('id'))}")
                        self._log_event(workflow_id, f"   └─ hit ArrayTrigger node: {array_node.get('label', array_node.get('id'))}")
                        try:
                            print(f"[ARRAY-DEBUG] outputData 类型: {type(array_data.get('outputData'))}")
                            print(f"[ARRAY-DEBUG] outputData 内容: {array_data.get('outputData')}")
                            self._log_event(workflow_id, f"🔴 [DEBUG] array_data keys: {list(array_data.keys())}")
                            self._log_event(workflow_id, f"🔴 [DEBUG] ArrayTrigger outputData type: {type(array_data.get('outputData'))}")
                            self._log_event(workflow_id, f"🔴 [DEBUG] ArrayTrigger outputData: {array_data.get('outputData')}")
                            # 处理节点连接
                            processed_data_temp = self._process_node_connections(copy.deepcopy(effective_graph), array_node, array_data["outputData"], workflow_id)
                            print(f"[ARRAY-DEBUG] 处理节点连接完成，图中有 {len(processed_data_temp.get('nodes', []))} 个节点")
                            self._log_event(workflow_id, f"🔴 [DEBUG] 开始处理普通节点，图中有 {len(processed_data_temp.get('nodes', []))} 个节点")
                            # 处理节点
                            self._process_normal_nodes(processed_data_temp, workflow_state)
                            print(f"[ARRAY-DEBUG] 普通节点处理完成")
                            self._log_event(workflow_id, f"🔴 [DEBUG] 普通节点处理完成")
                        except Exception as e:
                            print(f"[ARRAY-DEBUG] 处理错误: {e}")
                            self._log_event(workflow_id, f"❌ [ERROR] _process_next_array_trigger 内部错误: {e}")
                            import traceback
                            self._log_event(workflow_id, f"🔍 [TRACEBACK] {traceback.format_exc()}")
                    else:
                        print(f"[ARRAY-DEBUG] 找不到 ArrayTrigger 节点: {array_data.get('nodeId')}")
                        self._log_event(workflow_id, f"❌ [ERROR] 找不到 ArrayTrigger 节点: {array_data.get('nodeId')}")
                
                # 处理完成后，才从队列中移除并更新队列长度
                array_trigger_array.pop(0)
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
                    return copy.deepcopy(graph_payload)
                return None
            effective_graph = array_data.get("graph_data") or parent_graph_data
            graph_copy = copy.deepcopy(effective_graph)
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
            parent_pending = 0
            parent_state = self.workflows.get(parent_id)
            if parent_state:
                parent_pending = parent_state.get("pending_array_count", 0)
            self._refresh_parent_array_queue(parent_id, parent_pending)
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
                    processed_data_temp = self._process_node_connections(copy.deepcopy(effective_graph), array_node, array_data["outputData"], parent_workflow_id)
                    # 处理节点
                    self._process_normal_nodes(processed_data_temp, workflow_state)
                    self._log_event(parent_workflow_id, f"   └─ [BATCH] 批次处理完成")
                else:
                    self._log_event(parent_workflow_id, f"❌ [BATCH] 找不到 ArrayTrigger 节点: {array_data.get('nodeId')}")
        except Exception as e:
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
                            result = self._execute_node(processed_node)
                        
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
        with ThreadPoolExecutor(max_workers=min(len(nodes_to_execute), 5)) as executor:
            # 提交所有任务
            futures = [executor.submit(execute_single_node, node) for node in nodes_to_execute]
            
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
                print(f"🔍 [OUTPUT-UPDATE] 节点 {node.get('label', node.get('id'))} 的输出数量: {len(output_list)}")
                for idx, output in enumerate(output_list):
                    if not isinstance(output, dict):
                        print(f"⚠️ [OUTPUT-UPDATE] 节点 {node.get('label', node.get('id'))} 的输出 {idx} 不是字典，跳过: {type(output)}")
                        continue
                    if idx < len(node.get("Outputs", [])):
                        # 打印更新前的状态
                        old_output = node["Outputs"][idx].copy() if node["Outputs"][idx] else {}
                        node["Outputs"][idx].update(output)
                        # 打印更新后的状态
                        new_output = node["Outputs"][idx]
                        print(f"✅ [OUTPUT-UPDATE] 节点 {node.get('label', node.get('id'))} 的输出 {idx} 已更新:")
                        print(f"   更新前: Context={bool(old_output.get('Context'))}, Num={old_output.get('Num')}, Boolean={old_output.get('Boolean')}")
                        print(f"   更新后: Context={bool(new_output.get('Context'))}, Num={new_output.get('Num')}, Boolean={new_output.get('Boolean')}")
                        print(f"   更新数据: {output}")
                    else:
                        print(f"⚠️ [OUTPUT-UPDATE] 节点 {node.get('label', node.get('id'))} 的输出索引 {idx} 超出范围 (共有 {len(node.get('Outputs', []))} 个输出)")
                
                # 更新第一条输出的 token 信息（与前端保持一致）
                if result.get("output") and len(result["output"]) > 0 and len(node.get("Outputs", [])) > 0:
                    first_output = result["output"][0]
                    if isinstance(first_output, dict):
                        token_fields = ["prompt_tokens", "completion_tokens", "total_tokens"]
                        for field in token_fields:
                            if field in first_output:
                                node["Outputs"][0][field] = first_output[field]
                
                # 更新节点debug信息
                node["debug"] = result.get("debug", "")
                
                # 标记节点已执行
                node["firstRun"] = False
                
                # 添加历史记录（与前端executeNode中的addHistory调用对齐）
                workflow_id = workflow_state.get("id") if isinstance(workflow_state, dict) else None
                if workflow_id:
                    print(f"📝 [NODE-COMPLETE] 节点执行完成: {node.get('label', node.get('id'))}")
                    print(f"📝 [NODE-COMPLETE] 输出数量: {len(result.get('output', []))}")
                    print(f"📝 [NODE-COMPLETE] Debug长度: {len(str(result.get('debug', '')))}")
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
                            print(f"✅ [SYNC] 节点 {node.get('label', node.get('id'))} 的 Outputs 已同步到全局状态: {outputs_info}")
        
        return child_nodes_to_execute
    
    def _process_node_connections(self, data_temp, trigger_node, output_data, workflow_id=None):
        """处理节点连接，传递输出数据（模拟前端 processNodeConnections）"""
        if trigger_node is None:
            print("[DEBUG] _process_node_connections: trigger_node is None, skip updating outputs")
            return data_temp
        
        # 🎯🎯🎯 数据传递调试 🎯🎯🎯
        print(f"🎯🎯🎯 [DATA-TRANSFER] _process_node_connections 被调用")
        print(f"🎯🎯🎯 [DATA-TRANSFER] trigger_node: {trigger_node.get('label', trigger_node.get('id'))}")
        print(f"🎯🎯🎯 [DATA-TRANSFER] output_data type: {type(output_data)}")
        print(f"🎯🎯🎯 [DATA-TRANSFER] output_data: {output_data}")
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
                    print(f"🎯🎯🎯 [ROUTE] sourceAnchor: {edge['sourceAnchor']} → offset: {offset}")
                    if workflow_id is not None:
                        self._log_event(workflow_id, f"🎯 [ROUTE] edge {trigger_node.get('label','?')}[{offset}] → {node.get('label','?')}.{edge['targetAnchor']}")
                    if offset < 0 or offset >= len(trigger_node.get("Outputs", [])):
                        print(f"🎯🎯🎯 [ROUTE] offset 越界，跳过该边")
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
                            print(f"🎯🎯🎯 [ROUTE] output_data 为 list 但无该 offset，跳过")
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
                            print(f"🎯🎯🎯 [ROUTE] 端口Id不匹配，跳过。expected={expected_id} got={got_id}")
                            if workflow_id is not None:
                                self._log_event(workflow_id, f"⚠️ [ROUTE] 跳过(Id不匹配) expected={expected_id} got={got_id}")
                            continue
                        # ☆ 规范化：强制写回“正统”Id/Name，后续链路一致
                        item["Id"] = expected_id
                        item["name"] = expected_name
                    else:
                        print(f"🎯🎯🎯 [ROUTE] output_data 非法类型，跳过")
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
                        print(f"🎯🎯🎯 [ROUTE] 本次端口数据不是字典，跳过")
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
                    print(f"🎯🎯🎯 [WRITE] 输出端口{offset}({out_port.get('name','')}) ← {item_dict}")
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
                            print(f"🎯🎯🎯 [WRITE] 输入端口{target_idx}({input_item.get('name','')}) ← {item_dict}")
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
        print(f"🎯🎯🎯 [OUTPUT-UPDATE] _update_node_outputs 被调用")
        print(f"🎯🎯🎯 [OUTPUT-UPDATE] node: {node.get('label', node.get('id'))}")
        print(f"🎯🎯🎯 [OUTPUT-UPDATE] output_data type: {type(output_data)}")
        print(f"🎯🎯🎯 [OUTPUT-UPDATE] output_data: {output_data}")
        
        # 兼容空输出：直接跳过
        if output_data is None:
            print(f"🎯🎯🎯 [OUTPUT-UPDATE] output_data 为 None，跳过")
            return
        
        # 老JS语义：若是数组取第一个，否则用自身，写回所有Outputs
        d = output_data[0] if isinstance(output_data, list) and output_data else output_data
        if not isinstance(d, dict):
            print(f"🎯🎯🎯 [OUTPUT-UPDATE] 非字典输出，跳过写回")
            return
        
        for idx, output in enumerate(node.get("Outputs", [])):
            kind = output.get("Kind", "")
            if kind == "Num":
                output["Num"] = d.get("Num")
            elif kind == "Boolean":
                output["Boolean"] = d.get("Boolean")
            elif "String" in kind:
                output["Context"] = d.get("Context")
            print(f"🎯🎯🎯 [OUTPUT-UPDATE] 输出{idx}({output.get('name','')}) <- {d}")
    
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
            if workflow.get("child_summary"):
                result["childSummary"] = workflow.get("child_summary")
            return result
        except Exception as e:
            import traceback
            return {"error": f"Error getting workflow status: {e}", "traceback": traceback.format_exc()}
    
    def cleanup_workflow(self, workflow_id):
        """清理工作流资源（包含其批次工作流）"""
        with self.lock:
            related_ids = self._collect_related_workflow_ids(workflow_id)
            child_ids = self.child_workflows.pop(workflow_id, set())
            for cid in child_ids:
                related_ids.add(cid)
                self.parent_map.pop(cid, None)
            parent_id = self.parent_map.pop(workflow_id, None)
            if parent_id:
                siblings = self.child_workflows.get(parent_id)
                if siblings and workflow_id in siblings:
                    siblings.discard(workflow_id)
                if siblings and len(siblings) == 0:
                    self.child_workflows.pop(parent_id, None)
            for wid in related_ids:
                timer = self._cleanup_timers.pop(wid, None)
                if timer:
                    try:
                        timer.cancel()
                    except Exception:
                        pass
                if wid in self.stop_events:
                    try:
                        self.stop_events[wid].set()
                    except Exception:
                        pass
                    del self.stop_events[wid]
                if wid in self.workflows:
                    del self.workflows[wid]
        return {"status": "cleaned", "workflow_id": workflow_id}

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