from flask import Flask, jsonify, render_template,request
import pandas as pd
from contextlib import redirect_stdout, contextmanager
import io
import os
import asyncio
import hashlib
import workflow
import json
import importlib.util
import sys
import subprocess
import base64
import textwrap
import ast
import traceback  # 确保已经导入traceback模块
import re
import traceback
import shutil
import importlib
import logging
import tempfile
import asyncio
import ast
import time
from pathlib import Path
from threading import Lock
import uuid
import threading
from datetime import datetime

from typing import Any, Dict, List, Optional

# =========================
# App Print Switch (ALL HERE)
# =========================
# 说明：只影响本文件(app.py)内的 print(...) 调用；不会全局篡改 builtins.print。
# 如需开启，改为 True。
APP_ENABLE_PRINT = False
try:
    import builtins as _builtins
    _APP_ORIG_PRINT = _builtins.print
except Exception:
    _APP_ORIG_PRINT = None

def print(*args, **kwargs):  # noqa: A001  (shadow built-in intentionally)
    if APP_ENABLE_PRINT and _APP_ORIG_PRINT is not None:
        _APP_ORIG_PRINT(*args, **kwargs)

# =========================
# Thread-local StdIO Router
# =========================
# 说明：APP_ENABLE_PRINT 只影响 app.py 自己的 print。
# 节点脚本/第三方库大量使用 sys.stdout/sys.stderr 或 logging 输出，
# 且 Flask/WorkflowEngine 可能多线程并发执行节点。
# 这里安装线程本地 stdout/stderr 路由器：每个请求线程可选择“静音/捕获/放行”。

CAPTURE_NODE_STDIO_WHEN_SILENCED = True  # 静音时是否捕获节点脚本 stdout/stderr 到 debug
MAX_CAPTURED_STDIO_CHARS = 4000         # 只保留末尾 N 字符，避免 debug 爆炸


def _is_thread_stdio_router(obj) -> bool:
    return bool(getattr(obj, "__thread_stdio_router__", False))


class _ThreadLocalStdIO(io.TextIOBase):
    __thread_stdio_router__ = True

    def __init__(self, target, default_console_enabled: bool = True):
        super().__init__()
        self._target = target
        self._default_console_enabled = bool(default_console_enabled)
        self._local = threading.local()
        self._write_lock = Lock()

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
    try:
        if not _is_thread_stdio_router(sys.stdout):
            sys.stdout = _ThreadLocalStdIO(sys.stdout, default_console_enabled=bool(APP_ENABLE_PRINT))
    except Exception:
        pass
    try:
        if not _is_thread_stdio_router(sys.stderr):
            sys.stderr = _ThreadLocalStdIO(sys.stderr, default_console_enabled=bool(APP_ENABLE_PRINT))
    except Exception:
        pass


@contextmanager
def _thread_stdio_scope(console_enabled: bool = True, capture: bool = False):
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


# 进程启动即安装：后续每个请求线程按需静音/捕获
_install_thread_stdio_router()

# 可选：压低 Werkzeug/Flask 默认日志输出（不属于 print，但会刷控制台）
try:
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
except Exception:
    pass
try:
    # requests/urllib3 的 DEBUG 日志（不是 print）也会刷控制台
    logging.getLogger("urllib3").setLevel(logging.WARNING)
except Exception:
    pass

# 占位符 {{InputN}} 插值工具（支持 Num/String/Boolean）
import re

def _interp_placeholders(s: str, inputs: list):
    if not isinstance(s, str):
        return s

    def _val(inp: dict):
        kind = (inp.get("Kind") or "")
        if kind == "Num":
            v = inp.get("Num", "")
        elif "String" in kind:
            v = inp.get("Context", "")
        elif kind == "Boolean":
            v = "true" if inp.get("Boolean") else "false"
        else:
            v = inp.get("Context", inp.get("Num", ""))
        return "" if v is None else str(v)

    # 第一轮：处理 {{InputN}}
    def _repl_by_index(m):
        idx = int(m.group(1)) - 1  # {{Input1}} -> inputs[0]
        return _val(inputs[idx]) if 0 <= idx < len(inputs) else m.group(0)

    out = re.sub(r"\{\{\s*Input(\d+)\s*\}\}", _repl_by_index, s)

    # 第二轮：处理 {{name}} / {{Id}} / {{Alias}} 等别名占位符（支持中英文与可选空格）
    def _repl_by_alias(m):
        key = str(m.group(1)).strip()
        for inp in inputs or []:
            aliases = [
                (str(inp.get("name")).strip()  if inp.get("name")  is not None else None),
                (str(inp.get("Id")).strip()    if inp.get("Id")    is not None else None),
                (str(inp.get("Alias")).strip() if inp.get("Alias") is not None else None),
            ]
            if key and key in [a for a in aliases if a is not None]:
                return _val(inp)
        return m.group(0)

    # 放宽占位符匹配：{{ 变量 }} / {{变量}} 均可（避免误伤普通 JSON 单花括号）
    out = re.sub(r"\{\{\s*([^{}]+?)\s*\}\}", _repl_by_alias, out)
    return out

app = Flask(__name__)
project_data = {}
project_name = ''
# 当前实例最近一次启动的工作流ID（用于 Control Room 监控）
current_workflow_id = None

# ==== 1. 目录常量（全部 Path 对象）====
BASE_DIR      = Path(__file__).parent.absolute()        # 项目根目录
TEMP_DIR      = BASE_DIR / "TempFiles"                  # 临时文件夹
NOTEBOOK_DIR  = BASE_DIR / "NoteBook"                   # NoteBook 绝对路径
MEMORY_DIR    = BASE_DIR / "Memory"                     # Memory 绝对路径
WORKFLOW_DIR  = BASE_DIR / "WorkFlow"                   # WorkFlow 绝对路径
NODES_DIR     = BASE_DIR / "Nodes"                      # Nodes 绝对路径

# ==== 2. 确保这些目录都存在 ====
for folder in (TEMP_DIR, NOTEBOOK_DIR, MEMORY_DIR, WORKFLOW_DIR, NODES_DIR):
    folder.mkdir(parents=True, exist_ok=True)

# 在app.py初始化部分添加workflow引擎初始化
workflow.init_workflow_engine(BASE_DIR)

# 旧的工作流路由已被移除，新的路由在文件底部定义

def hash_file(filepath):
    """计算文件的SHA-256哈希值"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
def extract_node_kind(file_path):
    """从文件中提取NodeKind值"""
    # 兼容单引号/双引号：NodeKind = 'xxx' 或 NodeKind = "xxx"
    node_kind_pattern = re.compile(r"NodeKind\s*=\s*['\"]([^'\"]+)['\"]")
    try:
        with open(file_path, 'r', encoding='utf-8') as file:  # 指定使用utf-8编码读取
            contents = file.read()
    except UnicodeDecodeError:
        return 'EncodingError'  # 如果读取时发生编码错误，返回'EncodingError'
    
    match = node_kind_pattern.search(contents)
    if match:
        return match.group(1)
    else:
        return 'Unknown'  # 如果没有找到NodeKind，返回'Unknown'
def _unescape_py_string(s: str, quote: str = '"') -> str:
    """用 ast.literal_eval 安全还原转义；失败则做最小替换。"""
    try:
        return ast.literal_eval(quote + s + quote)
    except Exception:
        return s.replace("\\n", "\n").replace("\\t", "\t")

def extract_node_function(file_path: str) -> str:
    """从文件中提取 FunctionIntroduction 的值（支持三引号、单段、括号多段拼接）。"""
    # 尝试多编码读取，避免 'EncodingError'
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            with open(file_path, "r", encoding=enc) as f:
                contents = f.read()
            break
        except UnicodeDecodeError:
            contents = None
    if contents is None:
        return "EncodingError"

    # 1) 三引号（优先匹配）
    triple_pat = re.compile(
        r'FunctionIntroduction\s*=\s*(?P<q>"""|\'\'\')(?P<body>.*?)(?P=q)',
        re.DOTALL
    )
    m = triple_pat.search(contents)
    if m:
        return m.group("body")

    # 2) 单/双引号单段
    single_pat = re.compile(
        r'FunctionIntroduction\s*=\s*(?P<q>"|\')(?P<body>(?:\\.|(?!\1).)*?)(?P=q)',
        re.DOTALL
    )
    m = single_pat.search(contents)
    if m:
        q = m.group("q")
        body = m.group("body")
        return _unescape_py_string(body, quote=q)

    # 3) 括号内多段拼接：提取括号里的所有字符串字面量并拼接
    paren_pat = re.compile(
        r'FunctionIntroduction\s*=\s*\((?P<body>.*?)\)',
        re.DOTALL
    )
    m = paren_pat.search(contents)
    if m:
        body = m.group("body")
        # 匹配括号里每个字符串字面量
        str_lit_pat = re.compile(r'(?P<q>"|\')(?P<s>(?:\\.|(?!\1).)*?)(?P=q)', re.DOTALL)
        parts = []
        for sm in str_lit_pat.finditer(body):
            q = sm.group("q")
            s = sm.group("s")
            parts.append(_unescape_py_string(s, quote=q))
        if parts:
            return "".join(parts)

    return "Unknown"

def _split_history_stem(stem: str):
    # 兼容两种命名：
    # 1) name_YYYYmmdd_HHMMSS
    # 2) name_YYYYmmdd_HHMMSS_xxxxxx （高并发下带随机后缀防止重名）
    match = re.search(r'_(\d{8})_(\d{6})(?:_.+)?$', stem)
    if not match:
        return stem, ''
    ymd, hms = match.groups()
    try:
        dt = datetime.strptime(f"{ymd}{hms}", "%Y%m%d%H%M%S")
        readable = dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        readable = ''
    label = stem[:match.start()] or stem
    return label, readable
# 历史记录路径安全化（项目名转文件夹名）
def _safe_project_dir(name: str) -> str:
    try:
        safe = re.sub(r"[^\w\.\-]+", "_", str(name)).strip("._")
        return safe or "default"
    except Exception:
        return "default"
@app.route('/save', methods=['POST'])
def save():
    global project_data, project_name

    payload   = request.get_json(force=True)
    save_name = payload['name'].strip()
    save_data = payload['data']
    save_path = (payload.get('path') or '').strip()     # 可能为空/None

    # ---------- 目录处理 ----------
    base_dir  = Path('WorkFlow')                        # 稳定根目录

    # 1) 去掉开头可能出现的 ./  \  /  等
    rel_path  = Path(save_path).as_posix().lstrip('/\\')

    # 2) 若前端误把 'WorkFlow' 带进来了，祛除重复
    if rel_path.startswith('WorkFlow'):
        rel_path = rel_path[len('WorkFlow'):].lstrip('/\\')

    # 3) 拼完整目录
    full_dir  = base_dir / rel_path if rel_path else base_dir
    full_dir.mkdir(parents=True, exist_ok=True)         # 递归创建

    # ---------- 写文件 ----------
    file_path = full_dir / f'{save_name}.json'
    file_path.write_text(save_data, encoding='utf-8')

    # ---------- 更新全局变量 ----------
    if not isinstance(project_data, dict):
        project_data = {}

    project_data.update({
        'json_name': f'{save_name}.json',
        'json_path': str(full_dir),
        'name'     : f'{save_name}.json',
        'path'     : str(full_dir),
        'host'     : payload.get('host', ''),
        'callsign' : payload.get('callsign', '')
    })
    project_name = save_name
    
    return jsonify({'message': 'Save successful'})

@app.route('/')
def index():
    return render_template('index.html')
@app.route('/export', methods=['POST'])
def export():
    data = request.json
    graph_data = data['graphData']
    file_name = data['fileName']
    Kind=data['type']
    if Kind=='full':
        full_function_code = generate_full_function(graph_data['nodes'], graph_data['edges'])
        full_function_code_modified = full_function_code.replace('false', 'False')

        export_path = 'Export'
        os.makedirs(export_path, exist_ok=True)
        file_path = os.path.join(export_path, f"{file_name}.py")

        # 写入初始文件
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(full_function_code_modified)

        # 读取文件，过滤空行，替换 '**n**' 为 '\\n'，并写回
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            cleaned_lines = [line for line in lines if line.strip() != '']
            modified_lines = [line.replace('**n**', '\\n') for line in cleaned_lines]

        with open(file_path, 'w', encoding='utf-8') as file:
            file.writelines(modified_lines)

        return jsonify({'message': 'Graph data exported successfully, empty lines removed and replacements made'})
    elif Kind == 'independent':
        export_path = os.path.join('Export', 'Independ', file_name)
        os.makedirs(export_path, exist_ok=True)
        response = generate_independent_function(graph_data['nodes'], graph_data['edges'], export_path)

        return response
      
def generate_independent_function(nodes, edges, export_path):
    # 找到node文件夹中对应的nodes文件夹将他们复制粘贴到指定的Export\Independ文件夹中
    for node in nodes:
        script_name = node['name'] + '.py' if not node['name'].endswith('.py') else node['name']
        script_path = os.path.join('Nodes', script_name)
        if not os.path.exists(script_path):
            return jsonify({'error': f'Script {script_name} not found'}), 404

        destination_path = os.path.join(export_path, script_name)
        shutil.copy(script_path, destination_path)

    # 生成代码，并替换特定的文本
    tempcode = generate_independent_code(nodes, edges)
    modified_code = tempcode.replace('**n**', '\\n').replace('false', 'False').replace('true', 'True')
    modified_code = "\n".join([line for line in modified_code.splitlines() if line.strip() != ''])  # 过滤空行

    # 创建一个与文件夹同名的.py文件，并写入处理后的代码
    main_script_path = os.path.join(export_path, os.path.basename(export_path) + '.py')
    with open(main_script_path, 'w', encoding='utf-8') as file:
        file.write(modified_code)

    return jsonify({'message': 'Files successfully copied and main script created'})
def generate_independent_code(nodes, edges):
    #类似于generate_full_function函数，但是主代码是用于寻找节点文件夹中的py文件运行，其他一样
    unconnected_inputs, unconnected_outputs = get_unconnected_points(nodes, edges)
    input_params = [f"{info['target']}_{info['anchorIndex']}" for info in unconnected_inputs]
    input_params_str = ', '.join(input_params)

    # 初始化 Outputs 和 Inputs 的数量
    OutPutNum = len(unconnected_outputs)
    InPutNum = len(unconnected_inputs)
    InputDict = []
    for info in unconnected_inputs:
        for node in nodes:
            if node['id'] == info['target']:
                # 判断是处理输入还是输出
                if info['anchorIndex'] < len(node['Inputs']):
                    # 处理输入
                    input_item = node['Inputs'][info['anchorIndex']]
                    if 'Kind' in input_item:
                        #将input_item['Kind']存入InputDict字典中
                        InputDict.append(input_item['Kind'])
                break

    OutPutDict = []
    for info in unconnected_outputs:
        for node in nodes:
            if node['id'] == info['source']:
                total_inputs = len(node['Inputs'])
                # 判断是处理输入还是输出
                if info['anchorIndex'] >= total_inputs:
                    # 处理输出，调整索引以匹配输出列表
                    output_index = info['anchorIndex'] - total_inputs
                    if output_index < len(node['Outputs']):
                        output_item = node['Outputs'][output_index]
                        if 'Kind' in output_item:
                            OutPutDict.append(output_item['Kind'])
                break         
    # 根据未连接的输入和输出生成 Outputs 和 Inputs 的定义
    Outputs = [
    f"{{'Num': None, 'Kind': '{OutPutDict[index]}', 'Id': '{info['source']}_{info['anchorIndex']}', 'Context': None,'Boolean': False,'name': '{info['name']}','Link':0,'Description':'answer'}}"
    for index, info in enumerate(unconnected_outputs)
]
    Inputs = [
    f"{{'Num': {info['Num']}, 'Context': '{info['Context'] if info['Context'] != None else ''}', 'Boolean': {info['Boolean'] if info['Boolean'] != None else False}, 'Kind': '{InputDict[index]}', 'Id': 'Input{index + 1}', 'IsLabel': {info['IsLabel']}, 'name': '{info['name']}'}}"
    for index, info in enumerate(unconnected_inputs)
]
    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)
    unconnected_inputs_json = json.dumps(unconnected_inputs)
    unconnected_outputs_json = json.dumps(unconnected_outputs)
    unconnected_inputs_json =unconnected_inputs_json.replace('null', 'None')
    unconnected_outputs_json =unconnected_outputs_json.replace('null', 'None')
    unconnected_inputs_json =unconnected_inputs_json.replace('true', 'True')
    nodes_json =nodes_json.replace('null', 'None')
    edges_json =edges_json.replace('null', 'None')
    nodes_json =nodes_json.replace('true', 'True')
    edges_json =edges_json.replace('true', 'True')
    nodes_json =nodes_json.replace('false', 'False')
    edges_json =edges_json.replace('false', 'False')
    node_logic = []
    import_statements = set()  # 用于存储所有节点中的 import 语句
    all_functions = []
    for node in nodes:
        node_code = get_node_code(node)
        functions, new_code = extract_and_remove_functions(node_code)
        node_code = new_code
        if functions:
            all_functions.extend(functions)
        all_functions = list(set(all_functions))
        node_function_name = f"{node['id'].replace('.', '_')}_run_node"  # 替换点号为下划线
        # 移除额外的 return Outputs
        node_code_lines = node_code.splitlines()
        node_code_lines = [line for line in node_code_lines if line.strip()]  # 移除空行
        filtered_lines = []
        import_statements = set()  # 确保这是一个集合
        filtered_lines = []
        import_statements.add('import re')  # 使用add()方法添加'import re'语句from flask import Flask, request, jsonifyimport osimport sysimport traceback
        import_statements.add('import json')  # 使用add()方法添加'import json'语句
        import_statements.add('import hashlib')  # 使用add()方法添加'import hashlib'语句
        import_statements.add('from flask import Flask, jsonify, request')  # 使用add()方法添加'from flask import Flask, jsonify, request'语句
        import_statements.add('import os')
        import_statements.add('import sys')
        import_statements.add('import traceback')
        for line in node_code_lines:
            if line.startswith('import '):
                import_statements.add(line)
            else:
                filtered_lines.append(line)

        import_statements.add('import re')  # 使用add()方法添加'import re'语句
        node_code = '\n'.join(filtered_lines)
        node_code =node_code.replace('OutPutNum', 'OutPutNum_node')
        node_code =node_code.replace('InPutNum', 'InPutNum_node')
        # 替换所有"Outputs"和"Inputs"
        node_code = node_code.replace('Outputs', 'Outputs_node')
        node_code = node_code.replace('Inputs', 'Inputs_node')

        # 将方括号内的替换回原样
        node_code = node_code.replace("['Inputs_node']", "['Inputs']")
        node_code = node_code.replace("['Outputs_node']", "['Outputs']")

        node_code =node_code.replace('nodes', 'nodes_node')
        node_code =node_code.replace('edges', 'edges_node')
        node_code =node_code.replace('unconnected_inputs', 'unconnected_inputs_node')
        node_code =node_code.replace('unconnected_outputs', 'unconnected_outputs_node')
        node_code =node_code.replace('def run_node(node)', 'def run_nodes(node)')
        node_code +="\nreturn run_nodes(node)"
        node_logic.append(f"def {node_function_name}(node):\n{textwrap.indent(node_code, '   ')}\n ")
        optimized_code = '\n'.join(block.rstrip('\n') for block in node_logic) + '\n\n'
    unique_functions = list(set(all_functions))
    optimized_all_functions = '\n'.join(block.rstrip('\n') for block in all_functions) + '\n\n'
    execute_node_code = """
def run_node_route(node, node_name):
    data = request.json
    # 获取当前脚本的目录，而不是工作目录
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(current_script_dir, node_name)
    if not script_path.endswith('.py'):
        script_path += '.py'
    print('Script path:', script_path)  # Debug: Print the script path
    if not os.path.exists(script_path):
        return jsonify({'error': f'Script {node_name} not found'}), 404

    # 添加脚本目录到 sys.path 以便能够导入模块
    if os.path.dirname(script_path) not in sys.path:
        sys.path.append(os.path.dirname(script_path))
    try:
        module = __import__(os.path.splitext(node_name)[0])
        output = module.run_node(node)
        return jsonify({'output': output}), 200
    except Exception as e:
        error_info = traceback.format_exc()
        return jsonify({'error': str(e), 'trace': error_info}), 400
def execute_node(nodez):
    if nodez['firstRun'] and all(
        (not input['Isnecessary'] and not input.get('isConnected', False)) or nodez['inputStatus'][i]
        for i, input in enumerate(nodez['Inputs'])
    ):
        nodez['firstRun'] = False
        #检索同文件夹下的同名py文件，nodez['name']为文件名
        node_function_name = nodez['name']
        #检索同文件夹下的同名py文件，nodez['name']为文件名
        if not node_function_name.endswith('.py'):
            node_function_name += '.py'
        if not os.path.exists(node_function_name):
            response, status_code = run_node_route(nodez, node_function_name)  # 接收响应和状态码
            print('Response received with status:', status_code)  # Debug: Print the status code
            if status_code == 200:
                data = response.get_json()['output']
                print('Data received:', data)  # Debug: Print the data
                for i, output in enumerate(nodez['Outputs']):
                    if output['Kind'] == 'Num':
                        output['Num'] = data[i]['Num']
                    elif output['Kind'] == 'String':
                        output['Context'] = data[i]['Context']
                    elif output['Kind'] == 'Boolean':
                        output['Boolean'] = data[i]['Boolean']
                for i, uo in enumerate(unconnected_outputs):
                    source_id = uo["source"]
                    anchor_index = uo["anchorIndex"]
                    for node in nodes:
                        if node["id"] == source_id:
                            if len(node["Inputs"]) <= anchor_index < len(node["Inputs"]) + len(node["Outputs"]):
                                Outputs[i]= node["Outputs"][anchor_index-len(node["Inputs"])]  
                for io,edge in enumerate(edges): 
                    if edge['source'] == nodez['id']:
                        targetNode = next((n for n in nodes if n['id'] == edge['target']), None)
                        if targetNode and edge['targetAnchor'] == len(targetNode['Inputs']) + len(targetNode['Outputs']):
                            if data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Boolean'] == True:
                                targetNode['IsTrigger'] = False
                        if (targetNode and len(targetNode['Inputs']) > edge['targetAnchor']) or (targetNode and len(targetNode['Inputs'])+len(targetNode['Outputs']) == edge['targetAnchor'] and targetNode['NodeKind'] == 'IfNode'):
                            if(targetNode and len(targetNode['Inputs']) > edge['targetAnchor']):
                                if(targetNode['Inputs'][edge['targetAnchor']]['Kind'] == 'Num'):
                                    targetNode['Inputs'][edge['targetAnchor']]['Num'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Num']
                                elif(targetNode['Inputs'][edge['targetAnchor']]['Kind'] == 'String'):
                                    targetNode['Inputs'][edge['targetAnchor']]['Context'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Context']
                                elif(targetNode['Inputs'][edge['targetAnchor']]['Kind'] == 'Boolean'):
                                    targetNode['Inputs'][edge['targetAnchor']]['Boolean'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Boolean']
                                print(f"Node {nodez['id']} output to Node {targetNode['id']}")
                                targetNode['inputStatus'][edge['targetAnchor']] = True
                            export_prompt = targetNode['prompt']
                            if targetNode['ExprotAfterPrompt'] == '':
                                temp = 'Please ensure the output is in JSON format**n**{**n**'
                                for index, output in enumerate(targetNode['ExprotAfterPrompt']):
                                    kind = ''
                                    if output['Kind'] == 'String':
                                        kind = 'String'
                                    elif output['Kind'] == 'Num':
                                        kind = 'Num'
                                    elif output['Kind'] == 'Boolean':
                                        kind = 'Boolean'
                                    temp += f'"{output["Id"]}": "{output["Description"]}" (you need output type:{kind})**n**'
                                temp += '}**n**'
                                targetNode['ExprotAfterPrompt'] = temp
                            matches = retrieve_content_within_braces(targetNode['prompt'])
                            for match in matches:
                                for input in targetNode['Inputs']:
                                    if input['name'] == match:
                                        if input['Kind'] == 'Num':
                                            export_prompt = export_prompt.replace(match, str(input['Num']))
                                        elif input['Kind'] == 'String':
                                            export_prompt = export_prompt.replace(match, input['Context'])
                                        elif input['Kind'] == 'Boolean':
                                            export_prompt = export_prompt.replace(match, str(input['Boolean']))
                                export_prompt = export_prompt.replace('{{', '').replace('}}', '')
                            print('prompt:', export_prompt)
                            targetNode['ExportPrompt'] = export_prompt +'**n**' + targetNode.get('ExprotAfterPrompt', '')
                            print('ExportPrompt:', targetNode['ExportPrompt'])
                            if not targetNode.get('IsTrigger', False):
                                execute_node(targetNode)
            else:
                print(f"Error executing node: {response.get_json()['error']}")
        else:
            print(f"Function {node_function_name} not found")
"""

    return (
    '\n'.join(sorted(import_statements)) + '\n\n'
    + f"OutPutNum = {OutPutNum}\n"
    + f"InPutNum = {InPutNum}\n"
    + f"Outputs = [{', '.join(Outputs)}]\n"
    + f"Inputs = [{', '.join(Inputs)}]\n"
    + f"NodeKind = 'Normal'\n"
    + f"nodes = {nodes_json}\n"
    + f"edges = {edges_json}\n"
    + f"unconnected_inputs = {unconnected_inputs_json}\n"
    + f"unconnected_outputs = {unconnected_outputs_json}\n"
    + """
def run_node(nodex):
    for index, value in enumerate(nodex['Inputs']):
        if index < len(Inputs):
            if(Inputs[index]['Kind'] == 'Num'):
                Inputs[index]['Num'] = nodex['Inputs'][index]['Num']
            elif(Inputs[index]['Kind'] == 'String'):
                Inputs[index]['Context'] = nodex['Inputs'][index]['Context']
            elif(Inputs[index]['Kind'] == 'Boolean'):
                Inputs[index]['Boolean'] = nodex['Inputs'][index]['Boolean']
            print(f'Index {index} is updated with value {value}Num{Inputs[index]["Num"]}')
        else:
            print(f'Warning: input_args contains more items than Inputs. Extra value {value} at index {index} is ignored.')
    for i, Input in enumerate(Inputs):
        for node in nodes:
            if node['id']==unconnected_inputs[i]['target']:
                node['Inputs'][unconnected_inputs[i]["anchorIndex"]]['Num']=Input['Num']
                node['Inputs'][unconnected_inputs[i]["anchorIndex"]]['Context']=Input['Context']
                node['Inputs'][unconnected_inputs[i]["anchorIndex"]]['Boolean']=Input['Boolean']
    for node in nodes:
        node['inputStatus'] = [False] * len(node['Inputs'])
        node['firstRun'] = True
        node['IsTrigger'] = False
        if node['TriggerLink']>0:
            node['IsTrigger'] = True
        for output in node['Outputs']:
            output['Num'] = 0
            output['Context'] = ''
        for input in node['Inputs']:
            input['isConnected'] = False
    # 检查每个节点的每个输入矛点是否都被连接
    for node in nodes:
        for index, input in enumerate(node['Inputs']):
            isConnected = any(edge['target'] == node['id'] and edge['targetAnchor'] == index for edge in edges)
            if isConnected and not input['Isnecessary']:
                node['Inputs'][index]['isConnected'] = True
    for i, uo in enumerate(unconnected_inputs):
        target_id = uo['target']
        anchor_index = uo['anchorIndex']
        for node in nodes:
            if node['id'] == target_id:
                if 0 <= anchor_index < len(node['Inputs']):
                    node['inputStatus'][anchor_index] = True
    start_nodes = [node for node in nodes if len(node['Inputs']) == 0 or all(node['inputStatus'])]
    for node in start_nodes:
        if node['ExprotAfterPrompt'] == '':
            temp = 'Please ensure the output is in JSON format**n**{**n**'
            for index, output in enumerate(node['ExprotAfterPrompt']):
                kind = ''
                if output['Kind'] == 'String':
                    kind = 'String'
                elif output['Kind'] == 'Num':
                    kind = 'Num'
                elif output['Kind'] == 'Boolean':
                    kind = 'Boolean'
                temp += f'"{output["Id"]}": "{output["Description"]}" (you need output type:{kind})**n**'
            temp += '}**n**'
            node['ExprotAfterPrompt'] = temp     
        export_prompt = node['prompt']
        matches = retrieve_content_within_braces(node['prompt'])
        for match in matches:
            for input in node['Inputs']:
                if input['name'] == match:
                    if input['Kind'] == 'Num':
                        export_prompt = export_prompt.replace(match, str(input['Num']))
                    elif input['Kind'] == 'String':
                        export_prompt = export_prompt.replace(match, input['Context'])
                    elif input['Kind'] == 'Boolean':
                        export_prompt = export_prompt.replace(match, str(input['Boolean']))
            export_prompt = export_prompt.replace('{{', '').replace('}}', '')
        print('prompt:', export_prompt)
        node['ExportPrompt'] = export_prompt + '**n**' + node.get('ExprotAfterPrompt', '')
        print('ExportPrompt:', node['ExportPrompt'])
        if not node.get('IsTrigger', False):
            execute_node(node)
    return Outputs
def retrieve_content_within_braces(text):
    return re.findall(r'{{(.*?)}}', text)
"""

    + execute_node_code+ '\n\n'
)
    
def conditional_replace(text, old, new):
    # 使用正则表达式定义替换规则，(?<!\[)' 和 '(?!\])' 确保 'old' 不在方括号内
    pattern = r'(?<!\[)' + re.escape(old) + r'(?!\])'
    replaced_text = re.sub(pattern, new, text)
    return replaced_text
def generate_full_function(nodes, edges):
    #for node in nodes:
      #  for i, input in enumerate(node['Inputs']):
        #    isConnected = any(edge['target'] == node['id'] and edge['targetAnchor'] == i for edge in edges)
        #    if not isConnected and input['Isnecessary']:
       #         raise Exception(f"节点 {node['name']} 的输入矛点 {input['Name']} 没有被连接")
            
    unconnected_inputs, unconnected_outputs = get_unconnected_points(nodes, edges)
    input_params = [f"{info['target']}_{info['anchorIndex']}" for info in unconnected_inputs]
    input_params_str = ', '.join(input_params)

    # 初始化 Outputs 和 Inputs 的数量
    OutPutNum = len(unconnected_outputs)
    InPutNum = len(unconnected_inputs)
    InputDict = []
    for info in unconnected_inputs:
        for node in nodes:
            if node['id'] == info['target']:
                # 判断是处理输入还是输出
                if info['anchorIndex'] < len(node['Inputs']):
                    # 处理输入
                    input_item = node['Inputs'][info['anchorIndex']]
                    if 'Kind' in input_item:
                        #将input_item['Kind']存入InputDict字典中
                        InputDict.append(input_item['Kind'])
                break

    OutPutDict = []
    for info in unconnected_outputs:
        for node in nodes:
            if node['id'] == info['source']:
                total_inputs = len(node['Inputs'])
                # 判断是处理输入还是输出
                if info['anchorIndex'] >= total_inputs:
                    # 处理输出，调整索引以匹配输出列表
                    output_index = info['anchorIndex'] - total_inputs
                    if output_index < len(node['Outputs']):
                        output_item = node['Outputs'][output_index]
                        if 'Kind' in output_item:
                            OutPutDict.append(output_item['Kind'])
                break         
    # 根据未连接的输入和输出生成 Outputs 和 Inputs 的定义
    Outputs = [
    f"{{'Num': None, 'Kind': '{OutPutDict[index]}', 'Id': '{info['source']}_{info['anchorIndex']}', 'Context': None,'Boolean': False,'name': '{info['name']}','Link':0,'Description':'answer'}}"
    for index, info in enumerate(unconnected_outputs)
]
    Inputs = [
    f"{{'Num': {info['Num']}, 'Context': '{info['Context'] if info['Context'] != None else ''}', 'Boolean': {info['Boolean'] if info['Boolean'] != None else False}, 'Kind': '{InputDict[index]}', 'Id': 'Input{index + 1}', 'IsLabel': {info['IsLabel']}, 'name': '{info['name']}'}}"
    for index, info in enumerate(unconnected_inputs)
]
    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)
    unconnected_inputs_json = json.dumps(unconnected_inputs)
    unconnected_outputs_json = json.dumps(unconnected_outputs)
    unconnected_inputs_json =unconnected_inputs_json.replace('null', 'None')
    unconnected_outputs_json =unconnected_outputs_json.replace('null', 'None')
    unconnected_inputs_json =unconnected_inputs_json.replace('true', 'True')
    nodes_json =nodes_json.replace('null', 'None')
    edges_json =edges_json.replace('null', 'None')
    nodes_json =nodes_json.replace('true', 'True')
    edges_json =edges_json.replace('true', 'True')
    nodes_json =nodes_json.replace('false', 'False')
    edges_json =edges_json.replace('false', 'False')
    node_logic = []
    import_statements = set()  # 用于存储所有节点中的 import 语句
    all_functions = []
    for node in nodes:
        node_code = get_node_code(node)
        functions, new_code = extract_and_remove_functions(node_code)
        node_code = new_code
        if functions:
            all_functions.extend(functions)
        all_functions = list(set(all_functions))
        node_function_name = f"{node['id'].replace('.', '_')}_run_node"  # 替换点号为下划线
        # 移除额外的 return Outputs
        node_code_lines = node_code.splitlines()
        node_code_lines = [line for line in node_code_lines if line.strip()]  # 移除空行
        filtered_lines = []
        import_statements = set()  # 确保这是一个集合
        filtered_lines = []

        for line in node_code_lines:
            if line.startswith('import '):
                import_statements.add(line)
            else:
                filtered_lines.append(line)

        import_statements.add('import re')  # 使用add()方法添加'import re'语句from flask import Flask, request, jsonifyimport osimport sysimport traceback
        import_statements.add('import json')  # 使用add()方法添加'import json'语句
        import_statements.add('import hashlib')  # 使用add()方法添加'import hashlib'语句
        import_statements.add('from flask import Flask, jsonify, request')  # 使用add()方法添加'from flask import Flask, jsonify, request'语句
        import_statements.add('import os')
        import_statements.add('import sys')
        import_statements.add('import traceback')  
        node_code = '\n'.join(filtered_lines)
        node_code =node_code.replace('OutPutNum', 'OutPutNum_node')
        node_code =node_code.replace('InPutNum', 'InPutNum_node')
        # 替换所有"Outputs"和"Inputs"
        node_code = node_code.replace('Outputs', 'Outputs_node')
        node_code = node_code.replace('Inputs', 'Inputs_node')

        # 将方括号内的替换回原样
        node_code = node_code.replace("['Inputs_node']", "['Inputs']")
        node_code = node_code.replace("['Outputs_node']", "['Outputs']")

        node_code =node_code.replace('nodes', 'nodes_node')
        node_code =node_code.replace('edges', 'edges_node')
        node_code =node_code.replace('unconnected_inputs', 'unconnected_inputs_node')
        node_code =node_code.replace('unconnected_outputs', 'unconnected_outputs_node')
        node_code =node_code.replace('def run_node(node)', 'def run_nodes(node)')
        node_code +="\nreturn run_nodes(node)"
        node_logic.append(f"def {node_function_name}(node):\n{textwrap.indent(node_code, '   ')}\n ")
        optimized_code = '\n'.join(block.rstrip('\n') for block in node_logic) + '\n\n'
    unique_functions = list(set(all_functions))
    optimized_all_functions = '\n'.join(block.rstrip('\n') for block in all_functions) + '\n\n'
    execute_node_code = """
def execute_node(nodez):
    if nodez['firstRun'] and all(
        (not input['Isnecessary'] and not input.get('isConnected', False)) or nodez['inputStatus'][i]
        for i, input in enumerate(nodez['Inputs'])
    ):
        nodez['firstRun'] = False
        node_function_name = f"{nodez['id'].replace('.', '_')}_run_node"
        node_function = globals().get(node_function_name)
        if node_function:
            data = node_function(nodez)
            for i, output in enumerate(nodez['Outputs']):
                if output['Kind'] == 'Num':
                 output['Num'] = data[i]['Num']
                elif output['Kind'] == 'String':
                    output['Context'] = data[i]['Context']
                elif output['Kind'] == 'Boolean':
                    output['Boolean'] = data[i]['Boolean']
            for i, uo in enumerate(unconnected_outputs):
                source_id = uo["source"]
                anchor_index = uo["anchorIndex"]
                for node in nodes:
                    if node["id"] == source_id:
                        if len(node["Inputs"]) <= anchor_index < len(node["Inputs"]) + len(node["Outputs"]):
                            Outputs[i]= node["Outputs"][anchor_index-len(node["Inputs"])]  
            for io,edge in enumerate(edges):
                if edge['source'] == nodez['id']:
                    targetNode = next((n for n in nodes if n['id'] == edge['target']), None)
                    if targetNode and edge['targetAnchor'] == len(targetNode['Inputs']) + len(targetNode['Outputs']):
                        if data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Boolean'] == True:
                            targetNode['IsTrigger'] = False

                    if (targetNode and len(targetNode['Inputs']) > edge['targetAnchor']) or (targetNode and len(targetNode['Inputs'])+len(targetNode['Outputs']) == edge['targetAnchor'] and targetNode['NodeKind'] == 'IfNode'):
                        if(targetNode and len(targetNode['Inputs']) > edge['targetAnchor']):
                            if(targetNode['Inputs'][edge['targetAnchor']]['Kind'] == 'Num'):
                                targetNode['Inputs'][edge['targetAnchor']]['Num'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Num']
                            elif(targetNode['Inputs'][edge['targetAnchor']]['Kind'] == 'String'):
                                targetNode['Inputs'][edge['targetAnchor']]['Context'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Context']
                            elif(targetNode['Inputs'][edge['targetAnchor']]['Kind'] == 'Boolean'):
                                targetNode['Inputs'][edge['targetAnchor']]['Boolean'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Boolean']
                            print(f"Node {nodez['id']} output to Node {targetNode['id']}")
                            targetNode['inputStatus'][edge['targetAnchor']] = True
                        export_prompt = targetNode['prompt']
                        if targetNode['ExprotAfterPrompt'] == '':
                            temp = 'Please ensure the output is in JSON format**n**{**n**'
                            for index, output in enumerate(targetNode['ExprotAfterPrompt']):
                                kind = ''
                                if output['Kind'] == 'String':
                                    kind = 'String'
                                elif output['Kind'] == 'Num':
                                    kind = 'Num'
                                elif output['Kind'] == 'Boolean':
                                    kind = 'Boolean'
                                temp += f'"{output["Id"]}": "{output["Description"]}" (you need output type:{kind})**n**'
                            temp += '}**n**'
                            targetNode['ExprotAfterPrompt'] = temp
                        matches = retrieve_content_within_braces(targetNode['prompt'])
                        for match in matches:
                            for input in targetNode['Inputs']:
                                if input['name'] == match:
                                    if input['Kind'] == 'Num':
                                        export_prompt = export_prompt.replace(match, str(input['Num']))
                                    elif input['Kind'] == 'String':
                                        export_prompt = export_prompt.replace(match, input['Context'])
                                    elif input['Kind'] == 'Boolean':
                                        export_prompt = export_prompt.replace(match, str(input['Boolean']))
                            export_prompt = export_prompt.replace('{{', '').replace('}}', '')
                        print('prompt:', export_prompt)
                        targetNode['ExportPrompt'] = export_prompt +'**n**' + targetNode.get('ExprotAfterPrompt', '')
                        print('ExportPrompt:', targetNode['ExportPrompt'])
                        if not targetNode.get('IsTrigger', False):
                            execute_node(targetNode)
        else:
            print(f"Function {node_function_name} not found")
"""

    return (
    '\n'.join(sorted(import_statements)) + '\n\n'
    + f"OutPutNum = {OutPutNum}\n"
    + f"InPutNum = {InPutNum}\n"
    + f"Outputs = [{', '.join(Outputs)}]\n"
    + f"Inputs = [{', '.join(Inputs)}]\n"
    + f"NodeKind = 'Normal'\n"
    + f"nodes = {nodes_json}\n"
    + f"edges = {edges_json}\n"
    + f"unconnected_inputs = {unconnected_inputs_json}\n"
    + f"unconnected_outputs = {unconnected_outputs_json}\n"
    + """
def run_node(nodex):
    for index, value in enumerate(nodex['Inputs']):
        if index < len(Inputs):
            if(Inputs[index]['Kind'] == 'Num'):
                Inputs[index]['Num'] = nodex['Inputs'][index]['Num']
            elif(Inputs[index]['Kind'] == 'String'):
                Inputs[index]['Context'] = nodex['Inputs'][index]['Context']
            elif(Inputs[index]['Kind'] == 'Boolean'):
                Inputs[index]['Boolean'] = nodex['Inputs'][index]['Boolean']
            print(f'Index {index} is updated with value {value}Num{Inputs[index]["Num"]}')
        else:
            print(f'Warning: input_args contains more items than Inputs. Extra value {value} at index {index} is ignored.')
    for i, Input in enumerate(Inputs):
        for node in nodes:
            if node['id']==unconnected_inputs[i]['target']:
                node['Inputs'][unconnected_inputs[i]["anchorIndex"]]['Num']=Input['Num']
                node['Inputs'][unconnected_inputs[i]["anchorIndex"]]['Context']=Input['Context']
                node['Inputs'][unconnected_inputs[i]["anchorIndex"]]['Boolean']=Input['Boolean']
    for node in nodes:
        node['inputStatus'] = [False] * len(node['Inputs'])
        node['firstRun'] = True
        node['IsTrigger'] = False
        if node['TriggerLink']>0:
            node['IsTrigger'] = True
        for output in node['Outputs']:
            output['Num'] = 0
            output['Context'] = ''
        for input in node['Inputs']:
            input['isConnected'] = False
    # 检查每个节点的每个输入矛点是否都被连接
    for node in nodes:
        for index, input in enumerate(node['Inputs']):
            isConnected = any(edge['target'] == node['id'] and edge['targetAnchor'] == index for edge in edges)
            if isConnected and not input['Isnecessary']:
                node['Inputs'][index]['isConnected'] = True
    for i, uo in enumerate(unconnected_inputs):
        target_id = uo['target']
        anchor_index = uo['anchorIndex']
        for node in nodes:
            if node['id'] == target_id:
                if 0 <= anchor_index < len(node['Inputs']):
                    node['inputStatus'][anchor_index] = True
    start_nodes = [node for node in nodes if len(node['Inputs']) == 0 or all(node['inputStatus'])]
    for node in start_nodes:
        if node['ExprotAfterPrompt'] == '':
            temp = 'Please ensure the output is in JSON format**n**{**n**'
            for index, output in enumerate(node['ExprotAfterPrompt']):
                kind = ''
                if output['Kind'] == 'String':
                    kind = 'String'
                elif output['Kind'] == 'Num':
                    kind = 'Num'
                elif output['Kind'] == 'Boolean':
                    kind = 'Boolean'
                temp += f'"{output["Id"]}": "{output["Description"]}" (you need output type:{kind})**n**'
            temp += '}**n**'
            node['ExprotAfterPrompt'] = temp     
        export_prompt = node['prompt']
        matches = retrieve_content_within_braces(node['prompt'])
        for match in matches:
            for input in node['Inputs']:
                if input['name'] == match:
                    if input['Kind'] == 'Num':
                        export_prompt = export_prompt.replace(match, str(input['Num']))
                    elif input['Kind'] == 'String':
                        export_prompt = export_prompt.replace(match, input['Context'])
                    elif input['Kind'] == 'Boolean':
                        export_prompt = export_prompt.replace(match, str(input['Boolean']))
            export_prompt = export_prompt.replace('{{', '').replace('}}', '')
        print('prompt:', export_prompt)
        node['ExportPrompt'] = export_prompt + '**n**' + node.get('ExprotAfterPrompt', '')
        print('ExportPrompt:', node['ExportPrompt'])
        if not node.get('IsTrigger', False):
            execute_node(node)
    return Outputs
def retrieve_content_within_braces(text):
    return re.findall(r'{{(.*?)}}', text)
"""

    + execute_node_code+ '\n\n'
    + optimized_code
    + optimized_all_functions
)
    
def extract_and_remove_functions(code):
    # 如果存在，则从 "print(f"Function {node_function_name} not found")" 之后开始提取内容
    if "print(f\"Function {node_function_name} not found\")" in code:
        start_index = code.index("print(f\"Function {node_function_name} not found\")") + len("print(f\"Function {node_function_name} not found\")")
    elif "return Outputs_node" in code:
        # 如果不存在，则从 "return Outputs_node" 之后开始提取内容
        start_index = code.index("return Outputs_node") + len("return Outputs_node")
    else:
        # 如果都不存在，可以选择一个合适的默认行为
        start_index = len(code)  # 例如，可以设置为代码的末尾

    functions_part = code[start_index:]

    # 提取整个函数定义，包括函数名、参数和函数体
    function_defs = re.findall(r"def\s.*?return run_nodes\(input_argss\)", functions_part, re.DOTALL)

    # 将每个函数定义分开并放入数组
    function_defs = [f.strip() for f in function_defs]

    # 从原始代码中删除这些函数定义
    for func_def in function_defs:
        code = code.replace(func_def, '')

    return function_defs, code

def get_unconnected_points(nodes, edges):
    # 创建一个用于存储所有节点的锚点信息的列表
    anchors = []
    for node in nodes:
        index=-1
        for i, input in enumerate(node['Inputs']):
            Temp=False
            if(input['IsLabel']==True):
                Temp=True
            print('测试',input)
            # 假设 info 是之前定义好的字典
            info = {'Boolean': None, 'Context': None}  # 你可能需要根据实际情况来初始化这个字典
            # 检查并设置默认值
            if info['Boolean'] is None:
                info['Boolean'] = False
            if info['Context'] is None:
                info['Context'] = ''
            anchors.append({
                'NodeId': node['id'], 
                'IsOutputOrInput': 'Input', 
                'anchorIndex': i, 
                'IsConnected': False,
                'name': input['name'],
                'IsLabel': Temp,
                'Kind': input['Kind'],
                'Num': input['Num'],
                'Context': info['Context'],  # 使用更新后的info字典中的值
                'Boolean': info['Boolean']  # 同上
            })
            index=i
        for i, output in enumerate(node['Outputs']):
            anchors.append({'NodeId': node['id'], 'IsOutputOrInput': 'Output', 'anchorIndex': i+index+1, 'IsConnected': False,'name':output['name']})
    
    # 遍历边，更新连接的锚点信息
    for edge in edges:
        # 更新输入锚点的连接状态
        for anchor in anchors:
            if anchor['NodeId'] == edge['target'] and anchor['anchorIndex'] == edge['targetAnchor'] and anchor['IsOutputOrInput'] == 'Input':
                anchor['IsConnected'] = True
                anchor['source'] = edge['source']
                anchor['sourceAnchor'] = edge['sourceAnchor']
        # 更新输出锚点的连接状态
        for anchor in anchors:
            if anchor['NodeId'] == edge['source'] and anchor['anchorIndex'] == edge['sourceAnchor'] and anchor['IsOutputOrInput'] == 'Output':
                anchor['IsConnected'] = True
                anchor['target'] = edge['target']
                anchor['targetAnchor'] = edge['targetAnchor']
    
    # 根据连接状态将锚点分配到未连接的输入和输出列表中
    unconnected_inputs = [
        {'source': anchor.get('source'), 'sourceAnchor': anchor.get('sourceAnchor'), 'target': anchor['NodeId'], 'anchorIndex': anchor['anchorIndex'],'name':anchor['name'],'IsLabel':anchor['IsLabel'],'Kind':anchor['Kind'],'Num':anchor['Num'],'Context':anchor['Context'],'Boolean':anchor['Boolean']}
        for anchor in anchors if anchor['IsOutputOrInput'] == 'Input' and not anchor['IsConnected']
    ]
    unconnected_outputs = [
        {'source': anchor['NodeId'], 'anchorIndex': anchor['anchorIndex'], 'target': anchor.get('target'), 'targetAnchor': anchor.get('targetAnchor'),'name':anchor['name']}
        for anchor in anchors if anchor['IsOutputOrInput'] == 'Output' and not anchor['IsConnected']
    ]

    return unconnected_inputs, unconnected_outputs

def extract_and_remove_run_node_code(script_content):
    # 正则表达式匹配 return Outputs 后面的所有内容
    pattern = re.compile(r'(return Outputs[\s\S]*?(?=return run_nodes\())', re.MULTILINE)
    matches = pattern.findall(script_content)

    # 如果找到了匹配的内容，则提取代码并存储到数组中，并从原始脚本中移除该部分的代码
    if matches:
        run_node_code = matches[0].strip().split('\n')
        modified_script_content = pattern.sub('', script_content).strip()
        return modified_script_content, run_node_code
    else:
        return script_content, []

def get_node_code(node):
    script_name = node['name'] if node['name'].endswith('.py') else f"{node['name']}.py"
    script_path = os.path.join('Nodes', script_name)
    try:
        with open(script_path, 'rb') as file:
            content = file.read()
            decoded_content = content.decode('utf-8', errors='ignore')
            cleaned_content = decoded_content.replace('Ƹ', '').replace('�', '')
            return cleaned_content
    except FileNotFoundError:
        print(f"File not found: {script_path}")
        return ""
    except Exception as e:
        print(f"Error reading file {script_path}: {e}")
        return ""

# 全局锁：用于脚本加载等需要串行化的操作
lock = Lock()
# 历史文件写入锁：避免 /addHistory 在高并发下出现“读旧数据再覆盖新数据”的情况
history_lock = Lock()
# ==== 2. 占位符解析函数 ====
def _resolve_tempfiles(ctx: str) -> str:
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
    DIRS: dict[str, Path] = {
        "TempFiles": Path(TEMP_DIR),
        "NoteBook":  Path(NOTEBOOK_DIR),
        "Memory":    Path(MEMORY_DIR),
        "WorkFlow":  Path(WORKFLOW_DIR),
        "Nodes":     Path(NODES_DIR),
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
# ==== 3. 主路由 ====
# ------------------------------------------------------------
# 工具：本地图片转 Base64
# ------------------------------------------------------------
def image_to_base64(fp: str) -> str:
    fp = Path(fp).expanduser().resolve()
    with open(fp, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ------------------------------------------------------------
# 主入口
# ------------------------------------------------------------
@app.route("/run-node-single", methods=["POST"])
def run_node_single():
    data      = request.get_json(force=True)
    node_name = data.get("name")
    node      = data.get("node", {})

    # ---------- 1. 先解析 @TempFiles、@Memory 等标签 ----------
    TAGS = ["TempFiles", "NoteBook", "Memory", "WorkFlow", "Nodes"]
    for tag in TAGS:
        marker = f"@{tag}"
        for inp in node.get("Inputs", []):
            ctx = inp.get("Context")
            if isinstance(ctx, str) and marker in ctx:
                inp["Context"] = _resolve_tempfiles(ctx)

        ex_prompt = node.get("ExportPrompt")
        if isinstance(ex_prompt, str) and marker in ex_prompt:
            node["ExportPrompt"] = _resolve_tempfiles(ex_prompt)

    # ===== DEBUG: 占位符插值前的原始数据 =====
    try:
        print("[DBG:RUN_SINGLE:PRE] NodeKind:", node.get("NodeKind"))
        print("[DBG:RUN_SINGLE:PRE] Inputs(raw):", json.dumps(node.get("Inputs", []), ensure_ascii=False))
        print("[DBG:RUN_SINGLE:PRE] SystemPrompt(raw):", repr(node.get("SystemPrompt", "")))
        print("[DBG:RUN_SINGLE:PRE] ExprotAfterPrompt(raw):", repr(node.get("ExprotAfterPrompt", "")))
        print("[DBG:RUN_SINGLE:PRE] ExportPrompt(raw):", repr(node.get("ExportPrompt", "")))
    except Exception as _e:
        print("[DBG:RUN_SINGLE:PRE] print error:", _e)

    # —— 标签解析完毕后，立刻插值（确保发送到模型的是实际参数） ——
    node_inputs = node.get("Inputs", [])
    node["ExportPrompt"]       = _interp_placeholders(node.get("ExportPrompt", ""),       node_inputs)
    node["SystemPrompt"]       = _interp_placeholders(node.get("SystemPrompt", ""),       node_inputs)
    node["ExprotAfterPrompt"]  = _interp_placeholders(node.get("ExprotAfterPrompt", ""),  node_inputs)

    # ===== DEBUG: 占位符插值后的数据 =====
    try:
        print("[DBG:RUN_SINGLE:POST] Inputs:")
        for i, inp in enumerate(node_inputs):
            print(f"  - Input{i+1}: Kind={inp.get('Kind')} Num={inp.get('Num')} Context={repr(inp.get('Context'))} Boolean={inp.get('Boolean')}")
        print("[DBG:RUN_SINGLE:POST] SystemPrompt(filled):", repr(node.get("SystemPrompt", "")))
        print("[DBG:RUN_SINGLE:POST] ExprotAfterPrompt(filled):", repr(node.get("ExprotAfterPrompt", "")))
        print("[DBG:RUN_SINGLE:POST] ExportPrompt(filled):", repr(node.get("ExportPrompt", "")))
        # 如仍然存在 {{InputN}} 占位符，打印出未替换位置
        leftover = re.findall(r"\{\{\s*Input(\d+)\s*\}\}", node.get("ExportPrompt", ""))
        if leftover:
            print("[DBG:RUN_SINGLE:POST] ExportPrompt still has placeholders:", leftover)
    except Exception as _e2:
        print("[DBG:RUN_SINGLE:POST] print error:", _e2)

    # ---------- 2. 构造完整对话 messages（含图片） ----------
    # 2.1 收集需要转 Base64 的图片
    temp_images_b64 = []
    node_kind = node.get("NodeKind")
    
    # 只有当节点类型为LLm时才处理图片
    if node_kind == "LLm":
        # 检查文件路径是否为图片后缀
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        temp_images_b64 = [
            image_to_base64(inp.get("Context", ""))
            for inp in node.get("Inputs", [])
            if isinstance(inp.get("Kind"), str) and "FilePath" in inp["Kind"] 
            and any(inp.get("Context", "").lower().endswith(ext) for ext in image_extensions)
        ]

    # === 用插值后的文本直接构造 messages ===
    node_inputs   = node.get("Inputs", [])
    filled_system = _interp_placeholders(node.get("SystemPrompt", ""),      node_inputs)
    filled_after  = _interp_placeholders(node.get("ExprotAfterPrompt", ""), node_inputs)
    filled_user   = _interp_placeholders(node.get("ExportPrompt", ""),      node_inputs)

    system_prompt = filled_system if node.get("OriginalTextSelector") == "OriginalText" \
                   else (f"{filled_system}\n{filled_after}".strip())

    # ===== DEBUG: 最终 messages 关键内容 =====
    try:
        print("[DBG:RUN_SINGLE:MSG] system_prompt:", repr(system_prompt))
        print("[DBG:RUN_SINGLE:MSG] user(content):", repr(filled_user))
    except Exception as _e3:
        print("[DBG:RUN_SINGLE:MSG] print error:", _e3)

    msg_list = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": filled_user},
    ]
    for b64 in temp_images_b64:
        msg_list.append({
            "role": "user",
            "content": [{
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            }]
        })

    # 2.4 将本轮 messages 放入 node 以供节点脚本使用（仅本请求内，不合并历史，不做跨请求持久化）
    node["messages"] = msg_list
    # ---------- 3. 统一结果格式处理 ----------
    def normalize_result(result):
        if isinstance(result, dict) and "outputs" in result:
            output = result["outputs"]
            # 兼容两种字段名：debug_text（旧） / debug（新）
            debug_text = result.get("debug_text", "")
            if not debug_text:
                debug_text = result.get("debug", "")
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
    # your code here
        try:
            langgraph_agent_path = (BASE_DIR / "Langgraph" / "agent.py").resolve()
            if not langgraph_agent_path.is_file():
                return jsonify({"error": f"Langgraph/agent.py not found at {langgraph_agent_path}"}), 404

            capture = (not bool(APP_ENABLE_PRINT)) and bool(CAPTURE_NODE_STDIO_WHEN_SILENCED)
            with _thread_stdio_scope(console_enabled=bool(APP_ENABLE_PRINT), capture=capture) as _buf:
                with lock:
                    spec   = importlib.util.spec_from_file_location("langgraph_agent", langgraph_agent_path)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)

                # 打印传入脚本的 node["messages"]
                try:
                    print('[DBG:CALL:LangGraph] node.messages =', json.dumps(node.get('messages', []), ensure_ascii=False))
                except Exception as _e_msg1:
                    print('[DBG:CALL:LangGraph] print error:', _e_msg1)
                result = module.run_node(node)
                output, debug_text = normalize_result(result)
            if _buf is not None:
                debug_text = _merge_debug_with_stdio(debug_text, _buf.getvalue())

            return jsonify({
                "output":       output,
                "debug_text":   debug_text,
                # 额外提供 debug 字段，便于前端/其他分支统一读取（不破坏旧逻辑）
                "debug":        debug_text,
                "inputs":       node.get("Inputs", []),
                "ExportPrompt": node.get("ExportPrompt"),
            })

        except Exception as e:
            return jsonify({"error": str(e), "trace": traceback.format_exc()}), 400

    # ---------- 5. 分支：普通脚本 ----------
    script_path = _find_script(node_name)
    if script_path is None or not script_path.is_file():
        return jsonify({"error": f"Script {node_name} not found"}), 404

    try:
        capture = (not bool(APP_ENABLE_PRINT)) and bool(CAPTURE_NODE_STDIO_WHEN_SILENCED)
        with _thread_stdio_scope(console_enabled=bool(APP_ENABLE_PRINT), capture=capture) as _buf:
            with lock:
                spec   = importlib.util.spec_from_file_location(script_path.stem, script_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

            # 打印传入脚本的 node["messages"]
            try:
                print('[DBG:CALL:Script] node.messages =', json.dumps(node.get('messages', []), ensure_ascii=False))
            except Exception as _e_msg2:
                print('[DBG:CALL:Script] print error:', _e_msg2)
            result = module.run_node(node)
            output, debug_text = normalize_result(result)
        if _buf is not None:
            debug_text = _merge_debug_with_stdio(debug_text, _buf.getvalue())

        return jsonify({
            "output":       output,
            "debug_text":   debug_text,
            "debug":        debug_text,
            "inputs":       node.get("Inputs", []),
            "ExportPrompt": node.get("ExportPrompt"),
        })

    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 400
# ==== 4. 脚本查找 ====
def _find_script(node_name: str) -> Optional[Path]:
    """
    在 Nodes 目录下查找与 node_name 匹配的脚本（大小写不敏感）：
    1) foo.py
    2) foo/__init__.py
    3) foo/main.py
    """
    base = node_name[:-3] if node_name.lower().endswith(".py") else node_name
    candidates = [
        f"{base}.py",            # foo.py
        f"{base}/__init__.py",   # foo/__init__.py
        f"{base}/main.py",       # foo/main.py
    ]

    for cand in candidates:
        p = (NODES_DIR / cand).resolve()
        if p.is_file():
            return p

    # 兼容 macOS/Linux 的大小写差异：遍历一次
    lower_target_names = {Path(c).name.lower() for c in candidates}
    for p in NODES_DIR.rglob("*"):
        if p.is_file() and p.name.lower() in lower_target_names:
            return p

    return None
    
@app.route("/run-node", methods=["POST"])
def run_node_route():
    data = request.get_json(force=True)
    node_name = data.get("name")
    node = data.get("node", {})
    workflow_id = data.get("workflow_id")
    
    # 如果提供了workflow_id，则通过工作流引擎执行节点
    if workflow_id:
        workflow_status = workflow.get_workflow_status(workflow_id)
        if isinstance(workflow_status, dict) and "error" not in workflow_status:
            # 节点将由工作流引擎执行，这里只返回状态
            return jsonify({
                "status": "queued",
                "workflow_id": workflow_id,
                "message": "Node execution queued in workflow engine"
            })
    
    # 否则，使用原有逻辑执行节点
    # ---------- 1. 先解析 @TempFiles、@Memory 等标签 ----------
    TAGS = ["TempFiles", "NoteBook", "Memory", "WorkFlow", "Nodes"]
    for tag in TAGS:
        marker = f"@{tag}"
        for inp in node.get("Inputs", []):
            ctx = inp.get("Context")
            if isinstance(ctx, str) and marker in ctx:
                inp["Context"] = _resolve_tempfiles(ctx)

        ex_prompt = node.get("ExportPrompt")
        if isinstance(ex_prompt, str) and marker in ex_prompt:
            node["ExportPrompt"] = _resolve_tempfiles(ex_prompt)

    # ---------- 2. 构造完整对话 messages（含图片） ----------
    # 2.1 收集需要转 Base64 的图片
    temp_images_b64 = []
    node_kind = node.get("NodeKind")
    
    # 只有当节点类型为LLm时才处理图片
    if node_kind == "LLm":
        # 检查文件路径是否为图片后缀
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        temp_images_b64 = [
            image_to_base64(inp.get("Context", ""))
            for inp in node.get("Inputs", [])
            if isinstance(inp.get("Kind"), str) and "FilePath" in inp["Kind"] 
            and any(inp.get("Context", "").lower().endswith(ext) for ext in image_extensions)
        ]

    # 2.2 system_prompt 生成
    system_prompt = f"{node.get('SystemPrompt', '')}\n{node.get('ExprotAfterPrompt', '')}"
    if node.get("OriginalTextSelector") == "OriginalText":
        system_prompt = node.get("SystemPrompt", "")

    # 2.3 拼接消息列表（不再追加历史 node.messages）
    msg_list = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": node.get("ExportPrompt", "")},
    ]
    for b64 in temp_images_b64:
        msg_list.append({
            "role": "user",
            "content": [{
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            }]
        })

    # 2.4 将本轮 messages 放入 node 以供节点脚本使用（仅本请求内，不合并历史，不做跨请求持久化）
    node["messages"] = msg_list

    # ---------- 3. 分支：ReAct / LangGraph ----------
    node_kind = node.get("NodeKind")
    tools = node.get("Tools")
    is_react = node.get("IsReact")

    if node_kind == "LLm" and tools is not None and is_react is True:
        try:
            langgraph_agent_path = (BASE_DIR / "Langgraph" / "agent.py").resolve()
            if not langgraph_agent_path.is_file():
                return jsonify({"error": f"Langgraph/agent.py not found at {langgraph_agent_path}"}), 404

            capture = (not bool(APP_ENABLE_PRINT)) and bool(CAPTURE_NODE_STDIO_WHEN_SILENCED)
            with _thread_stdio_scope(console_enabled=bool(APP_ENABLE_PRINT), capture=capture) as _buf:
                with lock:
                    spec   = importlib.util.spec_from_file_location("langgraph_agent", langgraph_agent_path)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)

                result = module.run_node(node)
                output, debug_text = workflow._normalize_result(result)
            if _buf is not None:
                debug_text = _merge_debug_with_stdio(debug_text, _buf.getvalue())

            return jsonify({
                "output":       output,
                "debug":   debug_text,
                "inputs":       node.get("Inputs", []),
                "ExportPrompt": node.get("ExportPrompt"),
            })

        except Exception as e:
            return jsonify({"error": str(e), "trace": traceback.format_exc()}), 400

    # ---------- 4. 分支：普通脚本 ----------
    script_path = _find_script(node_name)
    if script_path is None or not script_path.is_file():
        return jsonify({"error": f"Script {node_name} not found"}), 404

    try:
        capture = (not bool(APP_ENABLE_PRINT)) and bool(CAPTURE_NODE_STDIO_WHEN_SILENCED)
        with _thread_stdio_scope(console_enabled=bool(APP_ENABLE_PRINT), capture=capture) as _buf:
            with lock:
                spec   = importlib.util.spec_from_file_location(script_path.stem, script_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

            result = module.run_node(node)
            output, debug_text = workflow._normalize_result(result)
        if _buf is not None:
            debug_text = _merge_debug_with_stdio(debug_text, _buf.getvalue())

        return jsonify({
            "output":       output,
            "debug":   debug_text,
            "inputs":       node.get("Inputs", []),
            "ExportPrompt": node.get("ExportPrompt"),
        })

    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 400
# ==== 4. 脚本查找 ====
def _find_script(node_name: str) -> Optional[Path]:
    """
    在 Nodes 目录下查找与 node_name 匹配的脚本（大小写不敏感）：
    1) foo.py
    2) foo/__init__.py
    3) foo/main.py
    """
    base = node_name[:-3] if node_name.lower().endswith(".py") else node_name
    candidates = [
        f"{base}.py",            # foo.py
        f"{base}/__init__.py",   # foo/__init__.py
        f"{base}/main.py",       # foo/main.py
    ]

    for cand in candidates:
        p = (NODES_DIR / cand).resolve()
        if p.is_file():
            return p

    # 兼容 macOS/Linux 的大小写差异：遍历一次
    lower_target_names = {Path(c).name.lower() for c in candidates}
    for p in NODES_DIR.rglob("*"):
        if p.is_file() and p.name.lower() in lower_target_names:
            return p

    return None

@app.route('/read_DataBase', methods=['POST'])
def read_data():
    try:
        # 获取文件路径
        data = request.get_json() or {}
        if 'file_path' not in data:
            return jsonify({'status': 'fail', 'message': 'No file path provided in the request'})

        file_path = _resolve_tempfiles(data['file_path'])
        include_rows = int(data.get('include_rows', 0) or 0)  # 0 = 仅返回表名/列名；>0 = 每个表/Sheet 额外返回前 N 行预览
        max_json_records = int(data.get('max_json_records', 5000) or 5000)  # schema-only 时 JSON/JSONL 最多扫描多少条记录来推断列名
        schema_only = include_rows <= 0
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return jsonify({'status': 'fail', 'message': 'File not found'})

        response_data = {}
        columns_data = {}  # 用于存储每个 sheet 的列名
        file_ext = os.path.splitext(file_path)[1].lower()

        # 根据文件类型进行处理
        if file_ext in ['.xlsx', '.xls']:
            # 处理 Excel 文件
            try:
                excel_data = pd.ExcelFile(file_path)
                for sheet_name in excel_data.sheet_names:
                    # 只读列名：nrows=0 避免把整页数据读进来（速度/内存提升巨大）
                    df_head = excel_data.parse(sheet_name, nrows=0)

                    # 替换未命名的列，添加序号和列标签（保持前端既有格式）
                    formatted_cols = [
                        f"{i+1}/{get_excel_column_label(i)}/{col if 'Unnamed' not in str(col) else 'Unnamed'}"
                        for i, col in enumerate(df_head.columns)
                    ]
                    columns_data[sheet_name] = formatted_cols

                    # 可选：仅返回每个 sheet 的前 N 行预览
                    if not schema_only:
                        df = excel_data.parse(sheet_name, nrows=include_rows)
                        df.columns = formatted_cols
                        df = df.fillna("Empty")
                        response_data[sheet_name] = df.to_dict(orient='records')

            except Exception as e:
                return jsonify({'status': 'fail', 'message': f'Error processing Excel file: {str(e)}'})

        elif file_ext in ['.json', '.jsonl']:
            # 处理 JSON/JSONL 文件
            try:
                sheet_name = 'default'
                all_columns = set()

                # schema-only 时，尽量不要把整个大文件读入内存：
                # - JSONL：流式扫描前 max_json_records 行
                # - JSON：优先尝试 ijson 流式；若不可用则回退 json.load（小文件没问题）
                json_data = []

                if file_ext == '.jsonl':
                    limit = include_rows if not schema_only else max_json_records
                    with open(file_path, 'r', encoding='utf-8') as jsonl_file:
                        for line in jsonl_file:
                            if limit <= 0:
                                break
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                            except json.JSONDecodeError as line_error:
                                logging.warning(f'Skipping invalid JSON line: {line}, Error: {str(line_error)}')
                                continue
                            if isinstance(obj, dict):
                                all_columns.update(obj.keys())
                            if not schema_only:
                                json_data.append(obj)
                            limit -= 1

                else:  # .json
                    streamed = False
                    if schema_only:
                        try:
                            import ijson  # type: ignore
                            with open(file_path, 'rb') as f:
                                # 兼容两种结构：数组或单对象；这里只抽取前 max_json_records 个对象的 keys
                                seen_any = False
                                count = 0
                                for obj in ijson.items(f, 'item'):
                                    seen_any = True
                                    if isinstance(obj, dict):
                                        all_columns.update(obj.keys())
                                    count += 1
                                    if count >= max_json_records:
                                        break
                            # 如果顶层不是数组（例如是单对象），ijson.items('item') 会拿不到任何元素
                            streamed = seen_any
                        except Exception:
                            streamed = False

                    if not streamed:
                        with open(file_path, 'r', encoding='utf-8') as json_file:
                            data_content = json.load(json_file)
                        if isinstance(data_content, list):
                            iterable = data_content[:include_rows] if not schema_only else data_content[:max_json_records]
                        else:
                            iterable = [data_content]
                        for item in iterable:
                            if isinstance(item, dict):
                                all_columns.update(item.keys())
                            if not schema_only:
                                json_data.append(item)

                columns_data[sheet_name] = sorted(list(all_columns))
                if not schema_only:
                    response_data[sheet_name] = json_data
                
            except json.JSONDecodeError as json_error:
                return jsonify({'status': 'fail', 'message': f'Invalid JSON format: {str(json_error)}'})
            except Exception as e:
                return jsonify({'status': 'fail', 'message': f'Error reading JSON/JSONL file: {str(e)}'})

        elif file_ext in ['.db', '.sqlite']:
            # 处理 SQLite 数据库
            try:
                import sqlite3
                # 优先用只读方式打开，避免对数据库做任何写入/模式切换（有些库是只读/被占用/或不希望创建 -wal/-shm）
                conn = None
                try:
                    p = Path(file_path).resolve()
                    db_uri = f"file:{p.as_posix()}?mode=ro"
                    conn = sqlite3.connect(db_uri, uri=True, timeout=5.0)
                except Exception:
                    # 回退：普通打开（尽量兼容老 sqlite / 特殊路径）
                    conn = sqlite3.connect(file_path, timeout=5.0)

                cur = conn.cursor()
                cur.execute("PRAGMA query_only=ON;")
                cur.execute("PRAGMA busy_timeout=5000;")

                # 快速一致性检查（如果数据库损坏/被截断，能给出更明确的提示）
                try:
                    check_row = cur.execute("PRAGMA quick_check;").fetchone()
                    check_res = check_row[0] if check_row else None
                    if check_res and str(check_res).lower() != "ok":
                        hint = (
                            "SQLite quick_check 未通过，说明该 .db 文件内部结构不一致/疑似损坏。"
                            "常见原因：复制/下载未完成、写入过程中程序异常退出/断电、磁盘/网盘问题，"
                            "或有其它进程正在写这个库导致你读到不一致快照。"
                            "建议：先关闭所有可能占用该库的程序；确认 .db 是完整文件（必要时重新复制/重新下载）；"
                            "用 sqlite3 执行 `PRAGMA integrity_check;` 进一步验证；"
                            "若需救数据可尝试 sqlite3 的 `.recover` 生成新库（或导出/重建）。"
                        )
                        return jsonify({
                            'status': 'fail',
                            'message': f'SQLite integrity check failed: {check_res}',
                            'resolved_path': file_path,
                            'hint': hint,
                        })
                except Exception:
                    # quick_check 在严重损坏时也可能抛异常，交给后续统一异常处理
                    pass

                def _quote_ident(name: str) -> str:
                    # SQLite 标识符双引号转义： " 变成 ""
                    return '"' + str(name).replace('"', '""') + '"'

                # 获取所有表名（不再用 pandas 读，减少开销）
                table_rows = cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                table_names = [r[0] for r in table_rows]

                for table_name in table_names:
                    try:
                        # 只取列名：PRAGMA table_info 是 O(列数)，远快于 SELECT * 读全表
                        pragma_sql = f"PRAGMA table_info({_quote_ident(table_name)})"
                        info_rows = cur.execute(pragma_sql).fetchall()
                        columns_data[table_name] = [r[1] for r in info_rows]  # r[1] = name

                        # 可选：仅返回每个表前 N 行预览
                        if not schema_only:
                            q = f"SELECT * FROM {_quote_ident(table_name)} LIMIT ?"
                            cur2 = conn.cursor()
                            cur2.execute(q, (include_rows,))
                            col_names = [d[0] for d in cur2.description] if cur2.description else []
                            rows = cur2.fetchall()
                            # 统一成 dict 列表，且把 None 变成 'Empty' 以兼容前端
                            response_data[table_name] = [
                                {col_names[i]: ("Empty" if v is None else v) for i, v in enumerate(row)}
                                for row in rows
                            ]
                    except Exception as table_e:
                        # 单表坏了也别拖垮整个库；给前端返回可见提示
                        if not schema_only:
                            response_data[table_name] = []
                        columns_data[table_name] = []
                        logging.warning(f"SQLite table schema/read failed: {table_name}: {table_e}")

                conn.close()
            except Exception as e:
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass
                msg = str(e)
                hint = None
                if "database disk image is malformed" in msg.lower():
                    hint = (
                        "SQLite reports the file is corrupted or incomplete. "
                        "Common causes: interrupted copy/download, power loss during write, "
                        "or selecting a different physical file than expected. "
                        "Try validating with `PRAGMA integrity_check;` in sqlite3, "
                        "or re-copy/regenerate the .db."
                    )
                return jsonify({
                    'status': 'fail',
                    'message': f'Error processing SQLite file: {msg}',
                    'resolved_path': file_path,
                    'hint': hint,
                })

        else:
            return jsonify({'status': 'fail', 'message': 'Invalid file type. Only .xlsx, .json, .jsonl, .db and .sqlite are allowed.'})

        return jsonify({
            'status': 'success',
            'resolved_path': file_path,
            'tables': list(columns_data.keys()),
            'columns': columns_data,
            # 为兼容旧逻辑：只有 include_rows>0 时才会带预览数据；否则保持空 dict
            'data': response_data,
        })

    except Exception as e:
        return jsonify({'status': 'fail', 'message': str(e)})

# ==== Excel 工具函数 =================================================
def get_excel_column_label(index: int) -> str:
    """
    0‑based 列号  ➜  Excel 标签：
        0 → A, 1 → B, … 25 → Z, 26 → AA …
    """
    label = ""
    index += 1                       # 变成 1‑based
    while index:
        index, rem = divmod(index - 1, 26)
        label = chr(65 + rem) + label
    return label

@app.route('/open-code-editor', methods=['POST'])
def open_code_editor():
    data = request.json
    node_name = data.get('name')
    script_path = os.path.join('Nodes', node_name)
    if not script_path.endswith('.py'):
        script_path += '.py'

    if not os.path.exists(script_path):
        return jsonify({'error': f'Script {node_name} not found'}), 404

    try:
        os.system(f'code {script_path}')
        return jsonify({'status': 'success'})
    except Exception as e:
        error_info = traceback.format_exc()
        return jsonify({'error': str(e), 'trace': error_info}), 400
@app.route('/get-python-files')
def get_python_files():
    folder_path = 'Nodes'
    os.makedirs(folder_path, exist_ok=True)

    file_hashes = []
    for fn in os.listdir(folder_path):
        if fn.endswith('.py'):
            fp = os.path.join(folder_path, fn)
            file_hashes.append({
                "Filename":  fn,
                "Hash":      hash_file(fp),
                "NodeKind":  extract_node_kind(fp),
                "NodeFunction": extract_node_function(fp)   # 建议返回真实换行
            })

    # ---------- ① 保存 json ----------
    json_path = os.path.join(folder_path, 'jsonlist.json')
    with open(json_path, 'w', encoding='utf-8') as jf:
        json.dump(file_hashes, jf, indent=4, ensure_ascii=False)

    # ---------- ② 保存 jsonl ----------
    jsonl_path = os.path.join(folder_path, 'jsonlist.jsonl')
    with open(jsonl_path, 'w', encoding='utf-8') as jl:
        for item in file_hashes:
            jl.write(json.dumps({
                "id":   item["Filename"],
                "text": item["NodeFunction"],
                "node_kind": item["NodeKind"]
            }, ensure_ascii=False) + '\n')

    # 如果只是返回给前端，内存里的 file_hashes 就够用
    return jsonify([{
        'filename':      i['Filename'],
        'hash':          i['Hash'],
        'NodeKind':      i['NodeKind'],
        'NodeFunction':  i['NodeFunction']
    } for i in file_hashes])


def find_imports(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    # 更新正则表达式以捕获import和from ... import ...语句
    imports = re.findall(r'^\s*(?:import\s+([^\s,]+)|from\s+([^\s,]+)\s+import)', content, re.MULTILINE)
    # 提取所有导入的模块名称
    imports = [imp[0] or imp[1] for imp in imports]
    return imports

def is_installed(package):
    try:
        __import__(package)
        return True
    except ImportError:
        return False
@app.route('/get-project-files', methods=['POST'])
def get_project_files():
    data = request.get_json(force=True)
    # 1. 参数校验
    if not data or 'json_path' not in data or 'json_name' not in data:
        return jsonify({'error': 'json_path 或 json_name 未提供'}), 400

    # 2. 规范化路径分隔符
    print(f"Original json_path测试: {data['json_path']}")
    path = data['json_path'].replace('\\', '/').strip('/')
    # 3. 确保以 WorkFlow/ 开头
    if not path.startswith('WorkFlow/') and not path.startswith('WorkFlow'):
        path = f'WorkFlow/{path}'
    print(f"Normalized json_path测试: {path}")
    folder_path = path  # 这时一定已被赋值

    # 4. 构造文件全路径
    json_name = data['json_name']
    file_path = os.path.join(folder_path, json_name)

    # 5. 检查文件是否存在
    if not os.path.isfile(file_path):
        return jsonify({'error': 'File not found', 'path': file_path}), 404

    # 6. 返回 JSON 内容
    with open(file_path, 'r', encoding='utf-8') as f:
        file_data = json.load(f)
    return jsonify(file_data)
@app.route('/browse', methods=['POST'])
def browse_directory():
    dir_path = request.json.get('path', '.')  # 获取请求中的路径，如果没有提供则默认为当前目录
    original_path = request.json.get('path', '.')

    # 将 @TempFiles/@NoteBook/@Memory/@Nodes/@WorkFlow 映射到项目内固定目录
    # 注意：这里必须与 `_resolve_tempfiles()` 使用同一套目录，否则“浏览到的文件”和“后端实际读取的文件”可能不是同一个。
    placeholder_map = {
        '@TempFiles': str(TEMP_DIR),
        '@NoteBook':  str(NOTEBOOK_DIR),
        '@Memory':    str(MEMORY_DIR),
        '@Nodes':     str(NODES_DIR),
        '@WorkFlow':  str(WORKFLOW_DIR),
    }
    used_marker = None
    used_actual_path = None
    for marker, actual_path in placeholder_map.items():
        if marker in dir_path:
            used_marker = marker
            used_actual_path = actual_path
            dir_path = dir_path.replace(marker, actual_path)
            break

    if used_marker is None:
        # 检查路径是否包含文件后缀
        if os.path.splitext(dir_path)[1]:  # 如果路径包含文件后缀
            dir_path = os.path.dirname(dir_path)  # 退回到文件所在的文件夹

        # 检查路径安全性
        if not os.path.isabs(dir_path):
            dir_path = os.path.abspath(os.path.join('.', dir_path))

    try:
        items = []
        for item in os.listdir(dir_path):  # 遍历目录中的所有项目
            item_path = os.path.join(dir_path, item)
            # 这里保持返回的路径显示为'@TempFiles'、'@WorkFlow'、'@Nodes'、'@Memory'、'@NoteBook'，如果原始路径中包含这些特殊前缀
            display_path = item_path
            # 若本次是从占位符目录浏览，则把真实路径根替换回占位符，方便前端继续拼接导航
            if used_marker is not None and used_actual_path is not None and used_marker in original_path:
                display_path = item_path.replace(used_actual_path, used_marker)
            items.append({
                'name': item,
                'is_dir': os.path.isdir(item_path),  # 判断是否是文件夹
                'path': display_path
            })
        
        logging.info(f"Successfully browsed directory: {dir_path}")
        return jsonify(items)
    
    except FileNotFoundError:
        error_message = f"Directory not found: {dir_path}"
        logging.error(error_message)
        return jsonify({'error': error_message}), 404
    
    except PermissionError:
        error_message = f"Permission denied for directory: {dir_path}"
        logging.error(error_message)
        return jsonify({'error': error_message}), 403
    
    except Exception as e:
        error_message = f"An error occurred while browsing directory: {dir_path} - {str(e)}"
        logging.error(error_message)
        return jsonify({'error': error_message}), 500
@app.route('/workflow-files')
def get_workflow_files():
    # 确保从正确的根目录开始搜索
    workflow_path = "WorkFlow"  # 使用相对路径，与保存逻辑一致
    
    # 确保WorkFlow文件夹存在
    if not os.path.exists(workflow_path):
        return jsonify([])
    
    workflow_files = []
    
    # 遍历WorkFlow文件夹及其子文件夹
    for root, dirs, files in os.walk(workflow_path):
        for file in files:
            if file.endswith('.json'):  # 只获取Python文件
                # 计算相对于WorkFlow文件夹的路径
                relative_path = os.path.relpath(root, workflow_path)
                folder_name = relative_path if relative_path != '.' else ''
                
                # 构建文件信息
                file_info = {
                    'filename': file,
                    'filepath': os.path.join(relative_path, file).replace('\\', '/'),
                    'folder': folder_name.replace('\\', '/')
                }
                workflow_files.append(file_info)
                
                print(f"Found file: {file_info}")  # 添加调试输出
    
    print(f"Total files found: {len(workflow_files)}")  # 添加调试输出
    return jsonify(workflow_files)


def safe_write_json(file_path, data, max_retries=3, compact: bool = True):
    for attempt in range(max_retries):
        try:
            # 在 Windows 上使用 'w' 模式会自动获取独占写入权限
            with open(file_path, 'w', encoding='utf-8') as f:
                if compact:
                    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
                else:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ Write attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(0.5)  # 重试前等待
            continue
    return False

# 历史记录限额（防止文件无限增大）
HISTORY_MAX_SESSIONS_PER_FILE = 30          # 每个历史文件最多保留多少个“会话/轮次”
HISTORY_MAX_ITEMS_PER_SESSION = 500        # 每个会话最多保留多少条记录（超出会裁剪保留最新）
HISTORY_MAX_STRING_CHARS = 20000           # 单字段字符串最大长度（超出会截断，防止 prompt/debug 爆炸）

def _parse_bool_param(v, default: bool = True) -> bool:
    """把查询参数/字符串解析成 bool。"""
    if v is None:
        return default
    try:
        s = str(v).strip().lower()
    except Exception:
        return default
    if s in ("0", "false", "no", "off", "disable", "disabled"):
        return False
    if s in ("1", "true", "yes", "on", "enable", "enabled"):
        return True
    return default

def _truncate_history_strings(obj, max_chars: int = HISTORY_MAX_STRING_CHARS, _depth: int = 0):
    """递归截断历史 payload 内过长的字符串，避免单条记录就把文件撑爆。"""
    if _depth > 6:
        return obj
    try:
        if isinstance(obj, str):
            if max_chars and len(obj) > max_chars:
                return obj[:max_chars] + f"\n...[truncated {len(obj) - max_chars} chars]"
            return obj
        if isinstance(obj, list):
            return [_truncate_history_strings(x, max_chars=max_chars, _depth=_depth + 1) for x in obj]
        if isinstance(obj, dict):
            return {k: _truncate_history_strings(v, max_chars=max_chars, _depth=_depth + 1) for k, v in obj.items()}
    except Exception:
        return obj
    return obj

@app.route('/addHistory', methods=['POST'])
def add_history():
    data = request.json
    project_name = request.args.get('ProjectName')

    # 是否记录历史（前端设置为“否”时，直接跳过写入）
    if not _parse_bool_param(request.args.get('RecordHistory'), default=True):
        return jsonify({'message': 'History recording disabled'}), 200
    
    # 验证项目名称是否存在
    if not project_name:
        return jsonify({'error': 'ProjectName is required'}), 400

    # 规范化项目目录，按项目名分文件夹
    project_dir = Path('History') / _safe_project_dir(project_name)
    project_dir.mkdir(parents=True, exist_ok=True)

    # 验证收到的数据是否为字典（JSON对象）
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid data format. Expected a JSON object.'}), 400
    # 防止 prompt/debug 超大：先做字符串截断再落盘
    data = _truncate_history_strings(data)

    # 按日期切分，避免单文件过大导致读取卡顿
    today_label = datetime.now().strftime('%Y%m%d')
    file_path = project_dir / f'{today_label}.json'
    print(f"📄 File path: {file_path}")

    # 使用独立锁串行化“读 -> 改 -> 写”流程，避免高并发下互相覆盖
    with history_lock:
        # 尝试读取现有的JSON文件
        if file_path.exists():
            for attempt in range(3):  # 添加重试机制
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    print(f"✅ Existing data loaded from {file_path}")
                    break
                except json.JSONDecodeError as e:
                    print(f"❌ JSON decode error: {e}")
                    # 如果文件损坏，创建备份
                    if file_path.stat().st_size > 0:
                        backup_path = f"{file_path}.backup.{int(time.time())}"
                        try:
                            os.rename(file_path, backup_path)
                            print(f"📦 Created backup of corrupted file: {backup_path}")
                        except Exception as e:
                            print(f"⚠️ Failed to create backup: {e}")
                    json_data = []
                    break
                except Exception as e:
                    print(f"❌ Read attempt {attempt + 1} failed: {e}")
                    if attempt == 2:  # 最后一次尝试失败
                        json_data = []
                    else:
                        time.sleep(0.5)  # 等待后重试
        else:
            print(f"ℹ️ No existing data. Initializing new data array.")
            json_data = []

        # 确保 json_data 是一个列表
        if not isinstance(json_data, list):
            print("⚠️ json_data is not a list. Initializing as empty list.")
            json_data = []

        # 将数据添加到现有的最后一个数组中
        # “Start” 语义：新开一轮会话（否则一天内会堆进同一个数组导致无限变大）
        is_start = False
        try:
            if isinstance(data, dict) and ("NodeKind" not in data):
                name_s = str(data.get("name", "")).strip().lower()
                msg_s = str(data.get("message", "")).strip().lower()
                if name_s in ("new started", "start", "new conversation started") or msg_s.startswith("new conversation"):
                    is_start = True
        except Exception:
            is_start = False
        if is_start:
            json_data.append([])
        if not json_data or not isinstance(json_data[-1], list):
            print("📝 Appending new sublist to json_data.")
            json_data.append([])

        print(f"➕ Adding data to json_data[-1]: {data}")
        json_data[-1].append(data)

        # 强制裁剪：限制会话条数 & 单会话条数，防止历史文件无限增大
        try:
            if isinstance(json_data[-1], list) and len(json_data[-1]) > HISTORY_MAX_ITEMS_PER_SESSION:
                json_data[-1] = json_data[-1][-HISTORY_MAX_ITEMS_PER_SESSION:]
        except Exception:
            pass
        try:
            if isinstance(json_data, list) and len(json_data) > HISTORY_MAX_SESSIONS_PER_FILE:
                json_data = json_data[-HISTORY_MAX_SESSIONS_PER_FILE:]
        except Exception:
            pass

        # 使用安全写入函数保存数据
        if safe_write_json(file_path, json_data, compact=True):
            print("✅ Data added successfully.")
            return jsonify({'message': 'Data added successfully'}), 200
        else:
            print("❌ Failed to write data after multiple attempts")
            return jsonify({'error': 'Failed to save data after multiple attempts'}), 500

def is_process_running(script_name):
    """检查指定的脚本是否正在运行"""
    try:
        result = subprocess.run(['pgrep', '-fl', script_name], capture_output=True, text=True)
        return script_name in result.stdout
    except Exception as e:
        print(f"Error checking process: {e}")
        return False

@app.route('/start_Message', methods=['POST'])
def start_message():
    data = request.get_json()
    project_name = data.get('ProjectName')
    # 检查Message.py是否正在运行
    if not is_process_running('Message.py'):
        # 假设Message.py在同一文件夹下，并且接受一个project_name参数来启动项目
        subprocess.Popen(['python', 'Message.py', project_name])
        return jsonify({'status': 'Message started'}), 200
    else:
        return jsonify({'status': 'Message already running'}), 200

@app.route('/getHistory', methods=['GET'])
def get_history():
    project_name = request.args.get('ProjectName')
    if not project_name:
        return jsonify({'error': 'ProjectName is required'}), 400

    # 允许指定文件名或使用最新文件
    target_filename = request.args.get('filename') or request.args.get('run')
    limit_param = request.args.get('limit', '200')  # 默认限制返回条数，防止过大
    try:
        limit = int(limit_param) if limit_param is not None else None
    except Exception:
        limit = 200

    project_dir = Path('History') / _safe_project_dir(project_name)
    if not project_dir.exists():
        # 兼容旧路径（History/项目名.json）
        legacy_path = Path('History') / project_name
        if legacy_path.exists():
            try:
                with open(legacy_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                return jsonify(json_data), 200
            except Exception as e:
                return jsonify({'error': f'读取旧版历史失败: {e}'}), 500
        return jsonify([]), 200

    # 选择目标文件
    if target_filename:
        file_path = project_dir / os.path.basename(target_filename)
    else:
        files = sorted(
            [p for p in project_dir.glob('*.json') if "__array_" not in p.stem],
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        file_path = files[0] if files else None

    if not file_path or not file_path.exists():
        return jsonify([]), 200

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except UnicodeDecodeError:
        return jsonify({'error': 'File encoding is not UTF-8. Please ensure the file is saved as UTF-8.'}), 500
    except json.JSONDecodeError:
        return jsonify({'error': 'File content is not valid JSON.'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # 仅返回最新若干条，避免前端加载过大
    if limit and isinstance(json_data, list) and json_data:
        try:
            last_session = json_data[-1] if isinstance(json_data[-1], list) else json_data
            if isinstance(last_session, list):
                json_data = [last_session[-limit:]]
        except Exception:
            pass

    return jsonify(json_data), 200

def _find_history_file_by_workflow(workflow_id: str):
    history_dir = Path('History')
    pattern = f"{workflow_id}.json"
    # 优先在新结构（按项目分目录）中查找
    matches = list(history_dir.rglob(pattern))
    if matches:
        return matches[0]
    legacy = history_dir / pattern
    return legacy if legacy.exists() else None

@app.route("/workflow/history/<workflow_id>", methods=["GET"])
def get_workflow_history_route(workflow_id):
    if not workflow_id:
        return jsonify([]), 200
    # 默认限制返回条数，防止单次响应过大
    limit_param = request.args.get('limit', '500')
    try:
        limit = int(limit_param) if limit_param is not None else None
    except Exception:
        limit = 500

    # ✅ 新版：优先从 workflow.py 的 JSONL 历史读取（并兼容旧 JSON），但对外仍返回旧结构(list[list[...]])
    try:
        days_param = request.args.get('days', '7')
        try:
            days = int(days_param) if days_param is not None else 7
        except Exception:
            days = 7
        from workflow import get_workflow_engine  # 避免循环导入（运行时引入）
        engine = get_workflow_engine()
        sessions = engine._read_history_compatible(workflow_id, days=days)
        # 与旧接口保持一致：仅截断“最后一个会话”的条数
        if limit and isinstance(sessions, list) and sessions:
            try:
                last_session = sessions[-1] if isinstance(sessions[-1], list) else sessions
                if isinstance(last_session, list):
                    sessions = [last_session[-limit:]]
            except Exception:
                pass
        return jsonify(sessions)
    except Exception:
        # 读 JSONL 失败则继续走旧文件读取逻辑
        pass

    history_path = _find_history_file_by_workflow(workflow_id)
    if not history_path:
        return jsonify([])
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        if limit and isinstance(json_data, list) and json_data:
            try:
                last_session = json_data[-1] if isinstance(json_data[-1], list) else json_data
                if isinstance(last_session, list):
                    json_data = [last_session[-limit:]]
            except Exception:
                pass
        return jsonify(json_data)
    except json.JSONDecodeError:
        return jsonify({'error': '记录文件损坏'}), 500
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

@app.route('/history/runs', methods=['GET'])
def list_history_runs():
    project_name = (request.args.get('project_name') or '').strip()
    # 可选：只列出“记录模式快照文件”（YYYYMMDD_HHMMSS_xxxxxx.json）
    only_snapshots = (request.args.get('only_snapshots') or request.args.get('onlySnapshots') or '').strip().lower()
    only_snapshots = only_snapshots in ('1', 'true', 'yes', 'on')
    # 可选：在列出前自动裁剪快照文件数量（超过则删除最老的）
    max_files = request.args.get('max_files') or request.args.get('maxFiles') or request.args.get('HistoryMaxFiles')
    try:
        max_files = int(max_files) if max_files is not None else 0
    except Exception:
        max_files = 0
    if max_files < 0:
        max_files = 0
    history_dir = Path('History')
    history_dir.mkdir(parents=True, exist_ok=True)
    records = []
    target_projects = []
    if project_name:
        proj_dir = history_dir / _safe_project_dir(project_name)
        target_projects.append(proj_dir)
        # ✅ 自动裁剪：只删除快照文件，不影响 workflow_*.json / YYYYMMDD.json
        if max_files and max_files > 0 and proj_dir.exists():
            try:
                pat = re.compile(r'^\d{8}_\d{6}_.+\.json$', re.I)
                candidates = [p for p in proj_dir.glob('*.json') if pat.match(p.name)]
                candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                if len(candidates) > max_files:
                    for p in candidates[max_files:]:
                        try:
                            p.unlink()
                        except Exception:
                            pass
            except Exception:
                pass
    else:
        target_projects.extend([p for p in history_dir.iterdir() if p.is_dir()])
        # 兼容旧版：根目录下的 JSON 也列出来
        target_projects.append(history_dir)

    for proj_dir in target_projects:
        if not proj_dir.exists():
            continue
        for json_file in proj_dir.glob('*.json'):
            if "__array_" in json_file.stem:
                # 跳过不需要的子数组工作流记录
                continue
            if only_snapshots:
                try:
                    if not re.match(r'^\d{8}_\d{6}_.+\.json$', json_file.name, re.I):
                        continue
                except Exception:
                    continue
            stat = json_file.stat()
            label, ts_label = _split_history_stem(json_file.stem)
            records.append({
                'filename': json_file.name,
                'project': proj_dir.name if proj_dir != history_dir else '',
                'path': str(json_file.relative_to(history_dir)),
                'label': label,
                'time_label': ts_label,
                'filesize': stat.st_size,
                'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
    records.sort(key=lambda item: item['modified_at'], reverse=True)
    # 若只列快照且设置了 max_files，则兜底截断返回条数（即便删除失败也不至于 UI 加载 1000+）
    if only_snapshots and max_files and max_files > 0 and isinstance(records, list) and len(records) > max_files:
        records = records[:max_files]
    return jsonify({'project': project_name, 'items': records})

@app.route('/history/run', methods=['GET'])
def get_history_run():
    filename = (request.args.get('filename') or '').strip()
    project_name = (request.args.get('project_name') or '').strip()
    if not filename:
        return jsonify({'error': 'filename is required'}), 400
    safe_name = os.path.basename(filename)
    if safe_name != filename or '..' in safe_name:
        return jsonify({'error': 'Invalid filename'}), 400
    history_root = Path('History')
    candidates = []
    if project_name:
        candidates.append(history_root / _safe_project_dir(project_name) / safe_name)
    # 优先新结构，再兼容旧文件
    candidates.append(history_root / safe_name)
    if not project_name:
        for proj_dir in history_root.iterdir():
            if proj_dir.is_dir():
                candidates.append(proj_dir / safe_name)
    history_path = next((p for p in candidates if p.exists()), None)
    if not history_path:
        return jsonify({'error': '记录不存在'}), 404
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return jsonify({'error': '记录文件损坏'}), 500
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500
    if isinstance(data, dict):
        return jsonify(data)
    return jsonify({'nodes': data})

@app.route('/history/prune', methods=['POST'])
def prune_history_runs_route():
    """
    按项目目录裁剪“记录模式/记录列表”的快照文件数量：
    - 仅清理 History/<project>/ 下形如 YYYYMMDD_HHMMSS_xxxxxx.json 的文件
    - 不影响 workflow_*.json 或 YYYYMMDD.json 等其它用途文件
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        project_name = (payload.get('project_name') or payload.get('ProjectName') or '').strip()
        max_files = payload.get('max_files', payload.get('maxFiles', payload.get('HistoryMaxFiles')))
        try:
            max_files = int(max_files)
        except Exception:
            max_files = 0
        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400
        if max_files < 0:
            max_files = 0

        history_root = Path('History')
        proj_dir = history_root / _safe_project_dir(project_name)
        if not proj_dir.exists():
            return jsonify({'status': 'ok', 'deleted': 0, 'kept': 0})

        pat = re.compile(r'^\d{8}_\d{6}_.+\.json$', re.I)
        candidates = [p for p in proj_dir.glob('*.json') if pat.match(p.name)]
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        deleted = 0
        if max_files and max_files > 0 and len(candidates) > max_files:
            for p in candidates[max_files:]:
                try:
                    p.unlink()
                    deleted += 1
                except Exception:
                    pass
        kept = min(len(candidates), max_files) if (max_files and max_files > 0) else len(candidates)
        return jsonify({'status': 'ok', 'deleted': deleted, 'kept': kept, 'max_files': max_files})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/get-missing-packages')
def get_missing_packages():
    try:
        directory = 'Nodes'  # 直接指定 Nodes 文件夹
        app.logger.debug(f"Checking directory: {directory}")
        
        python_files = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))
                    
        app.logger.debug(f"Python files found: {python_files}")
        
        all_imports = set()
        print('files:', python_files)
        for file in python_files:
            imports = find_imports(file)
            app.logger.debug(f"Imports found in {file}: {imports}")
            all_imports.update(imports)
        
        missing_packages = [package for package in all_imports if not is_installed(package)]
        app.logger.debug(f"Missing packages: {missing_packages}")
        print('missing_packages:', missing_packages)
        return jsonify(missing_packages)
    except Exception as e:
        app.logger.error(f"Error occurred: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/install-packages', methods=['POST'])
def install_packages():
    try:
        packages = request.json.get('packages', [])
        for package in packages:
            subprocess.check_call(['pip', 'install', package])
        return jsonify({'status': 'success', 'installed': packages})
    except Exception as e:
        app.logger.error(f"Error occurred during installation: {e}")
        return jsonify({'error': str(e)}), 500
@app.route('/history-project', methods=['POST'])
def set_project():
    global project_data
    #print('project_data测试:', project_data)
    return jsonify(project_data)

@app.route('/load-project', methods=['POST'])
def load_project():
    global project_data
    global project_name
    project_data = request.json
    # 同步更新全局项目名称，便于注册到 Control Hub
    try:
        name = project_data.get('name') or project_data.get('ProjectName') or ''
        if isinstance(name, str) and name.lower().endswith('.json'):
            project_name = name[:-5]
        else:
            project_name = name
        print(f"[DEBUG] /load-project 设置 project_name = {project_name}")

        # 尝试通知启动中心更新该实例的项目名称
        try:
            import requests
            port = int(sys.argv[1]) if len(sys.argv) > 1 else None
            if port and project_name:
                requests.post(
                    'http://127.0.0.1:3001/hub/update-project-name',
                    json={'port': port, 'project_name': project_name},
                    timeout=2
                )
                print(f"✅ 已通知 Control Hub 更新项目名称: {project_name}")
        except Exception as e:
            print(f"⚠️ 更新 Control Hub 项目名称失败: {e}")
    except Exception as e:
        print(f"⚠️ /load-project 解析项目名称失败: {e}")

    return jsonify({'status': 'Project loaded successfully'})  
@app.route('/get-node-details/<node_name>')
def get_node_details(node_name):
    try:
        file_path = os.path.join('Nodes', f'{node_name}.py')  # 确保路径正确
        load_error = ""
        load_trace = ""
        
        # 初始化 IsLoadSuccess 标志，假设为 True
        is_load_success = True

        # 检查文件是否存在，如果不存在直接设置 is_load_success 为 False
        if not os.path.exists(file_path):
            is_load_success = False
            return jsonify({
                "Outputs": [],
                "Inputs": [],
                "Lable": [],
                "InputIsAdd": '',
                "OutputsIsAdd": '',
                "NodeKind": '',
                "IsLoadSuccess": is_load_success  # 文件找不到时返回 false
            })
        
        # 加载节点模块
        spec = importlib.util.spec_from_file_location("node_module", file_path)
        node_module = importlib.util.module_from_spec(spec)
        sys.modules["node_module"] = node_module
        
        try:
            # 静音节点脚本 import-time 的 print/logging（避免前端频繁获取详情时刷屏）
            capture = (not bool(APP_ENABLE_PRINT)) and bool(CAPTURE_NODE_STDIO_WHEN_SILENCED)
            with _thread_stdio_scope(console_enabled=bool(APP_ENABLE_PRINT), capture=capture) as _buf:
                spec.loader.exec_module(node_module)  # 尝试加载模块
            # 不把 stdio 返回给前端，避免污染结构；需要排查时可手动打开 APP_ENABLE_PRINT
        except Exception as e:
            # 任意加载失败都不应让前端崩溃：标记失败，但仍返回空 Inputs/Outputs 结构
            is_load_success = False
            try:
                load_error = str(e)
                load_trace = traceback.format_exc()
            except Exception:
                load_error = "unknown"
                load_trace = ""

        # 获取 Outputs, Inputs, 和 Lable
        # 使用单独的 try-except 来确保即使加载模块失败，其他信息也可以正常获取
        Outputs = []
        Inputs = []
        Lable = []
        InputIsAdd = ''
        OutputsIsAdd = ''
        NodeKind = ''
        
        try:
            Outputs = getattr(node_module, 'Outputs', [])
        except AttributeError:
            pass  # 如果不存在 Outputs 属性，忽略错误
        
        try:
            Inputs = getattr(node_module, 'Inputs', [])
        except AttributeError:
            pass  # 如果不存在 Inputs 属性，忽略错误
        
        try:
            Lable = getattr(node_module, 'Lable', [])
        except AttributeError:
            pass  # 如果不存在 Lable 属性，忽略错误

        try:
            InputIsAdd = getattr(node_module, 'InputIsAdd', '')
        except AttributeError:
            pass  # 如果不存在 InputIsAdd 属性，忽略错误
        
        try:
            OutputsIsAdd = getattr(node_module, 'OutputsIsAdd', '')
        except AttributeError:
            pass  # 如果不存在 OutputsIsAdd 属性，忽略错误
        
        try:
            NodeKind = getattr(node_module, 'NodeKind', '')
        except AttributeError:
            pass  # 如果不存在 NodeKind 属性，忽略错误

        # 返回信息以 JSON 格式
        return jsonify({
            "Outputs": Outputs,
            "Inputs": Inputs,
            "Lable": Lable,
            "InputIsAdd": InputIsAdd,
            "OutputsIsAdd": OutputsIsAdd,
            "NodeKind": NodeKind,
            "IsLoadSuccess": is_load_success,  # 返回加载库是否成功
            "error": load_error,
            "trace": load_trace,
        })
    except Exception as e:
        # 兜底：永远保证 Inputs/Outputs 存在，避免前端读取 .length 直接报错
        return jsonify({
            "Outputs": [],
            "Inputs": [],
            "Lable": [],
            "InputIsAdd": '',
            "OutputsIsAdd": '',
            "NodeKind": '',
            "IsLoadSuccess": False,
            "error": str(e),
            "trace": traceback.format_exc(),
        })

# 添加新的路由用于工作流管理
@app.route("/workflow/start", methods=["POST"])
def start_workflow_route():
    global current_workflow_id
    try:
        data = request.get_json(force=True)
        graph_data = data.get("graph_data")
        passivity_trigger_array = data.get("passivity_trigger_array", [])
        array_trigger_array = data.get("array_trigger_array", [])
        
        # 生成唯一的工作流ID
        workflow_id = data.get("workflow_id", f"workflow_{uuid.uuid4().hex}")
        current_workflow_id = workflow_id  # 记录最近启动的工作流，提供给 /workflow/status/current 使用
        print(f"🚀 [API] 接收启动请求: {workflow_id}")
        
        # 为工作流注入 ProjectName，便于历史命名（优先顺序：查询参数 > 全局project_data/name > 全局project_name > graph_data.name > 'workflow'）
        try:
            pn = request.args.get("ProjectName")
        except Exception:
            pn = None
        try:
            if not pn and isinstance(project_data, dict):
                pn = project_data.get("name") or project_data.get("json_name")
        except Exception:
            pass
        if not pn:
            try:
                pn = project_name or (graph_data.get("name") if isinstance(graph_data, dict) else None) or "workflow"
            except Exception:
                pn = "workflow"
        try:
            if isinstance(graph_data, dict):
                graph_data["ProjectName"] = pn
        except Exception:
            pass
        
        # 启动工作流
        result = workflow.start_workflow(
            workflow_id, 
            graph_data, 
            passivity_trigger_array, 
            array_trigger_array
        )
        
        if result.get('error'):
            print(f"❌ [API] 启动失败: {result.get('error')}")
        else:
            print(f"✅ [API] 启动成功: {workflow_id}")
        
        return jsonify(result)
    except Exception as e:
        print(f"❌ [API] 启动异常: {str(e)}")
        #print(traceback.format_exc())
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@app.route("/workflow/status/<workflow_id>", methods=["GET"])
def get_workflow_status_route(workflow_id):
    try:
        result = workflow.get_workflow_status(workflow_id)
        
        if result.get('error'):
            print(f"❌ [API] 状态查询错误: {result.get('error')}")
        
        # 将后端计算的本轮识别指纹透传给前端（若存在）
        try:
            if isinstance(result, dict) and isinstance(result.get('graph_data'), dict):
                fp = result['graph_data'].get('ringFingerprint')
                if fp:
                    result['ringFingerprint'] = fp
        except Exception:
            pass

        return jsonify(result)
    except Exception as e:
        print(f"❌ [API] 获取工作流状态异常: {str(e)}")
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@app.route("/workflow/status/current", methods=["GET"])
def get_current_workflow_status():
    """获取当前实例中“最近启动”的工作流状态（用于 Control Room 监控）"""
    from workflow import get_workflow_engine  # 避免循环导入
    global current_workflow_id
    global project_name

    try:
        print(f"[DEBUG:STATUS] ========== /workflow/status/current ==========")
        engine = get_workflow_engine()
        workflows = getattr(engine, "workflows", {}) or {}
        print(f"[DEBUG:STATUS] 当前已有工作流数量: {len(workflows)}")
        print(f"[DEBUG:STATUS] current_workflow_id: {current_workflow_id}")

        selected_id = None

        # 1) 优先使用最近启动的工作流ID
        if current_workflow_id and current_workflow_id in workflows:
            selected_id = current_workflow_id
            print(f"[DEBUG:STATUS] 使用当前工作流ID: {selected_id}")
        elif workflows:
            # 2) 其次选择任意 RUNNING 的工作流
            try:
                from workflow import WorkflowStatus
                running_ids = [
                    wid for wid, wf in workflows.items()
                    if isinstance(wf, dict) and wf.get("status") == WorkflowStatus.RUNNING
                ]
            except Exception:
                running_ids = []

            if running_ids:
                selected_id = running_ids[0]
                print(f"[DEBUG:STATUS] 选择一个运行中的工作流: {selected_id}")
            else:
                # 3) 最后按 last_update 选择最新的一个
                try:
                    selected_id = max(
                        workflows.items(),
                        key=lambda item: (item[1] or {}).get("last_update", 0)
                    )[0]
                    print(f"[DEBUG:STATUS] 按 last_update 选择工作流: {selected_id}")
                except Exception:
                    selected_id = None

        if not selected_id:
            print(f"[DEBUG:STATUS] 没有可用的工作流，返回空闲")
            return jsonify({
                "status": "idle",
                "queue_data": {
                    "passivity_queue": 0,
                    "array_queue": 0
                },
                "workflow_id": None,
                "project_name": project_name or "",
                "graph_project_name": None
            })

        # 4) 获取该工作流的详细状态
        status_data = workflow.get_workflow_status(selected_id)
        status = status_data.get("status", "idle")
        print(f"[DEBUG:STATUS] 选中工作流 {selected_id} 状态: {status}")

        # ★ 最小改动：如果已经结束，就视为当前无工作流，返回 idle
        try:
            from workflow import WorkflowStatus
            if status in (WorkflowStatus.STOPPED, WorkflowStatus.COMPLETED, WorkflowStatus.ERROR):
                print(f"[DEBUG:STATUS] 工作流 {selected_id} 已结束({status})，返回 idle")
                return jsonify({
                    "status": "idle",
                    "queue_data": {
                        "passivity_queue": 0,
                        "array_queue": 0
                    },
                    "workflow_id": None,
                    "project_name": project_name or "",
                    "graph_project_name": None
                })
        except Exception:
            # 保险起见，导入失败就按原逻辑继续走，不额外处理
            pass

        # 提取本次工作流对应的项目名（优先使用图中的 ProjectName）
        graph = status_data.get("graph_data") or {}
        graph_project_name = None
        try:
            if isinstance(graph, dict):
                graph_project_name = graph.get("ProjectName") or graph.get("name")
        except Exception:
            graph_project_name = None

        # 解析队列长度（统一从 queues / queue_lengths 读取）
        queues = status_data.get("queues") or status_data.get("queue_lengths") or {}
        raw_pass = queues.get("pending", queues.get("passivity", 0))
        raw_array = queues.get("array", 0)

        try:
            passivity_queue = int(raw_pass)
        except Exception:
            passivity_queue = raw_pass if isinstance(raw_pass, (int, float)) else 0

        try:
            array_queue = int(raw_array)
        except Exception:
            array_queue = raw_array if isinstance(raw_array, (int, float)) else 0

        print(f"[DEBUG:STATUS] 队列长度: passivity={passivity_queue}, array={array_queue}")

        return jsonify({
            "status": status,  # 用上面解析好的 status
            "queue_data": {
                "passivity_queue": passivity_queue,
                "array_queue": array_queue
            },
            "workflow_id": selected_id,
            # 当前实例在 /load-project 中解析出的项目名（可能为空）
            "project_name": project_name or "",
            # 来自本次工作流图数据的 ProjectName/name，用于前端展示“当前监控的 workflow”
            "graph_project_name": graph_project_name,
            # --- short system monitor metrics (pass-through) ---
            "ConnNow": status_data.get("ConnNow"),
            "TWNow": status_data.get("TWNow"),
            "PortUse": status_data.get("PortUse"),
        })
    except Exception as e:
        print(f"[DEBUG:STATUS] 异常: {e}")
        traceback.print_exc()
        return jsonify({
            "status": "idle",
            "queue_data": {
                "passivity_queue": 0,
                "array_queue": 0
            },
            "workflow_id": None,
            "error": str(e)
        })

@app.route("/workflow/load-array-trigger", methods=["POST"])
def load_array_trigger():
    """调用前端 loadArrayTriggerArray 函数"""
    try:
        data = request.get_json()
        passivity_data = data.get('passivity_data')
        
        if not passivity_data:
            return jsonify({"error": "Missing passivity_data"}), 400
        
        # 这里应该调用前端的 loadArrayTriggerArray 函数
        # 但由于架构限制，我们返回一个指示，让前端自己处理
        return jsonify({
            "success": True,
            "message": "Frontend should call loadArrayTriggerArray with this data",
            "passivity_data": passivity_data
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/workflow/pause/<workflow_id>", methods=["POST"])
def pause_workflow_route(workflow_id):
    result = workflow.pause_workflow(workflow_id)
    return jsonify(result)

@app.route("/workflow/resume/<workflow_id>", methods=["POST"])
def resume_workflow_route(workflow_id):
    result = workflow.resume_workflow(workflow_id)
    return jsonify(result)

@app.route("/workflow/stop/<workflow_id>", methods=["POST"])
def stop_workflow_route(workflow_id):
    result = workflow.stop_workflow(workflow_id)
    return jsonify(result)

@app.route("/workflow/cleanup/<workflow_id>", methods=["POST"])
def cleanup_workflow_route(workflow_id):
    result = workflow.cleanup_workflow(workflow_id)
    return jsonify(result)

@app.route("/workflow/record-history/<workflow_id>", methods=["POST"])
def set_workflow_record_history(workflow_id):
    """运行中动态开关：是否记录该 workflow 的历史（同时影响 workflow.py 内部 History 与 run 快照）。"""
    if not workflow_id:
        return jsonify({"error": "workflow_id is required"}), 400
    try:
        payload = request.get_json(force=True, silent=True) or {}
        enabled = payload.get("enabled", True)
        enabled = bool(enabled)
        from workflow import get_workflow_engine  # 避免循环导入
        engine = get_workflow_engine()
        with getattr(engine, "lock", threading.Lock()):
            wf = getattr(engine, "workflows", {}).get(workflow_id)
            if not wf:
                return jsonify({"error": "Workflow not found"}), 404
            gd = wf.get("graph_data") if isinstance(wf, dict) else None
            if not isinstance(gd, dict):
                gd = {}
                wf["graph_data"] = gd
            gd["RecordHistory"] = enabled
        return jsonify({"status": "ok", "workflow_id": workflow_id, "RecordHistory": enabled})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@app.route("/workflow/list", methods=["GET"])
def list_workflows_route():
    """获取所有运行中的工作流列表（包括批次工作流）"""
    try:
        from workflow import get_workflow_engine, WorkflowStatus
        engine = get_workflow_engine()
        workflows = getattr(engine, "workflows", {}) or {}
        
        running_workflows = []
        for wf_id, wf_data in workflows.items():
            if not (wf_data and isinstance(wf_data, dict)):
                continue
            status = wf_data.get("status", "")
            is_child = wf_data.get("is_child", False)

            # 允许子工作流在“已完成/错误/已停止”状态下短暂展示，便于前端显示“运行完成”
            allowed_statuses = {WorkflowStatus.RUNNING, WorkflowStatus.PAUSED}
            if is_child:
                allowed_statuses |= {WorkflowStatus.COMPLETED, WorkflowStatus.ERROR, WorkflowStatus.STOPPED}
            if status not in allowed_statuses:
                continue
            graph_data = wf_data.get("graph_data", {})
            project_name = graph_data.get("ProjectName") or graph_data.get("name") or wf_id
            if '_batch_' in wf_id:
                parent_id = wf_id.split('_batch_')[0]
                parent_wf = workflows.get(parent_id)
                if parent_wf and isinstance(parent_wf, dict):
                    parent_graph = parent_wf.get("graph_data", {})
                    parent_name = parent_graph.get("ProjectName") or parent_graph.get("name") or parent_id
                    project_name = f"{parent_name} [批次{wf_id.split('_batch_')[1]}]"
            queue_lengths = wf_data.get("queue_lengths") or {}
            display_name = wf_data.get("display_name") or project_name
            running_workflows.append({
                "id": wf_id,
                "status": status,
                "project_name": project_name,
                "display_name": display_name,
                "is_child": is_child,
                "parent_id": wf_data.get("parent_id"),
                "child_summary": wf_data.get("child_summary") or {},
                "queue_lengths": {
                    "passivity": queue_lengths.get("passivity", queue_lengths.get("pending", 0)),
                    "array": queue_lengths.get("array", 0)
                }
            })
        
        return jsonify({"workflows": running_workflows})
    except Exception as e:
        return jsonify({"error": str(e), "workflows": []}), 500

@app.route("/debug/info", methods=["GET"])
def debug_info():
    """调试信息端点"""
    import os
    return jsonify({
        'port': request.environ.get('SERVER_PORT', 'unknown'),
        'project_name': project_name,
        'pid': os.getpid(),
        'has_register_function': 'register_to_hub' in dir(),
        'python_version': sys.version
    })

# ==================== 密钥管理接口 ====================
@app.route('/api/secrets/get-llm-nodes', methods=['GET'])
def get_llm_nodes():
    """获取所有 NodeKind='LLm' 的节点名称"""
    try:
        nodes_dir = NODES_DIR
        if not nodes_dir.exists():
            return jsonify({'nodes': []})
        
        llm_nodes = []
        for filename in os.listdir(nodes_dir):
            if filename.endswith('.py'):
                file_path = nodes_dir / filename
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if "NodeKind = 'LLm'" in content or 'NodeKind = "LLm"' in content:
                            node_name = filename[:-3]  # 去除 .py
                            llm_nodes.append(node_name)
                except Exception:
                    continue
        
        return jsonify({'nodes': llm_nodes})
    except Exception as e:
        app.logger.error(f"获取LLm节点失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/secrets/get-config', methods=['GET'])
def get_secrets_config():
    """获取密钥配置"""
    try:
        edit_dir = BASE_DIR / 'Edit'
        edit_dir.mkdir(parents=True, exist_ok=True)
        config_path = edit_dir / 'Edit.json'
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if 'secrets' not in config:
                    config['secrets'] = []
                if 'llmMappings' not in config:
                    config['llmMappings'] = {}
                return jsonify(config)
        else:
            return jsonify({'secrets': [], 'llmMappings': {}})
    except Exception as e:
        app.logger.error(f"获取密钥配置失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/secrets/save-config', methods=['POST'])
def save_secrets_config():
    """保存密钥配置，并将密钥值写入环境变量"""
    try:
        data = request.json
        edit_dir = BASE_DIR / 'Edit'
        edit_dir.mkdir(parents=True, exist_ok=True)
        config_path = edit_dir / 'Edit.json'
        
        # 保存到文件
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 将密钥值写入环境变量
        secrets = data.get('secrets', [])
        for secret in secrets:
            key_name = secret.get('name', '')
            key_value = secret.get('value', '')
            if key_name and key_value:
                os.environ[key_name] = key_value
                app.logger.info(f"✅ 已将密钥 '{key_name}' 写入环境变量")
        
        return jsonify({'status': 'success'})
    except Exception as e:
        app.logger.error(f"保存密钥配置失败: {e}")
        return jsonify({'error': str(e)}), 500

def load_secrets_to_env():
    """启动时从 Edit/Edit.json 加载密钥到环境变量"""
    try:
        edit_dir = BASE_DIR / 'Edit'
        config_path = edit_dir / 'Edit.json'
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                secrets = config.get('secrets', [])
                for secret in secrets:
                    key_name = secret.get('name', '')
                    key_value = secret.get('value', '')
                    if key_name and key_value:
                        os.environ[key_name] = key_value
                        app.logger.info(f"✅ 启动时加载密钥 '{key_name}' 到环境变量")
    except Exception as e:
        app.logger.warning(f"启动时加载密钥失败: {e}")

def register_to_hub(port):
    """向启动程序注册实例"""
    import threading
    import os
    import requests  # 必须在函数内导入
    import time
    
    def register():
        print(f"[DEBUG] App {port} 准备注册到 Control Hub...")
        time.sleep(2)  # 等待服务启动
        
        try:
            register_data = {
                'port': port,
                'type': 'app',
                'project_name': project_name or f'app_{port}',
                'pid': os.getpid()
            }
            print(f"[DEBUG] App {port} 注册数据: {register_data}")
            
            response = requests.post(
                'http://127.0.0.1:3001/hub/register-instance',
                json=register_data,
                timeout=5
            )
            print(f"[DEBUG] App {port} 注册响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ App {port} 已注册到 Control Hub: {result}")
                # 启动心跳
                start_heartbeat(port)
            else:
                print(f"⚠️ App {port} 注册失败: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"⚠️ App {port} 无法连接到 Control Hub: {e}")
            import traceback
            traceback.print_exc()
    
    thread = threading.Thread(target=register, daemon=True)
    thread.start()

def start_heartbeat(port):
    """定期发送心跳"""
    import threading
    import requests
    import time
    
    def heartbeat():
        while True:
            try:
                requests.post(
                    'http://127.0.0.1:3001/hub/heartbeat',
                    json={'port': port, 'status': 'running'},
                    timeout=2
                )
            except:
                pass
            time.sleep(10)  # 每10秒发送一次心跳
    
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()

if __name__ == '__main__':
    port = int(sys.argv[1])
    print(f"[DEBUG] ==================== APP 启动 ====================")
    print(f"[DEBUG] Starting server on port {port}")
    print(f"[DEBUG] Project name: {project_name}")
    print(f"[DEBUG] Will register to Control Hub at http://127.0.0.1:3001")
    
    # 启动时加载密钥到环境变量
    load_secrets_to_env()
    
    # 注册到 Control Hub
    register_to_hub(port)
    
    print(f"[DEBUG] Server starting...")
    app.run(debug=True, port=port, use_reloader=False)
