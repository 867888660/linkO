import json
import pandas as pd
import re
import re as _re
import copy
import logging
import traceback
from typing import Dict, List, Any, Optional
import os
import sqlite3

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class NodeConfigurationError(Exception):
    """Custom exception for node configuration errors"""
    pass

class NodeExecutionError(Exception):
    """Custom exception for node execution errors"""
    pass

# Define the number of outputs and inputs
OutPutNum = 0
InPutNum = 2

# Initialize Outputs and Inputs arrays with type hints
Outputs: List[Dict[str, Any]] = [
    {
        'Num': None,
        'Isnecessary': False,
        'Kind': 'String',
        'Id': f'Output1{i + 1}',
        'Context': None,
        'name': f'OutPut{i + 1}',
        'Link': 0
    } for i in range(OutPutNum)
]

Inputs: List[Dict[str, Any]] = [
    {
        'Num': None,
        'Kind': 'String',
        'Id': f'Input{i + 1}',
        'Context': None,
        'Isnecessary': True,
        'name': f'Input{i + 1}',
        'Link': 0,
        'IsLabel': False
    } for i in range(InPutNum)
]

# Node configuration
NodeKind = 'ArrayTrigger_DataBase'
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个Excel文件数据处理节点，用于读取Excel表格数据并按行处理，支持全表格输出或指定列输出两种模式。\n\n代码功能摘要（概括核心算法或主要处理步骤）\\n核心算法基于pandas库读取Excel文件，逐行遍历数据并根据配置的selectBox1参数决定输出格式：当选择\'All\'时生成markdown表格格式的完整行数据，当选择特定列名时仅输出该列的值。包含完整的节点结构验证、输入参数校验和异常处理机制。\n\n参数\\n```yaml\\ninputs:\\n  - name: FilePath\\n    type: file\\n    required: true\\n    description: Excel文件的完整路径\\n  - name: Table\\n    type: string\\n    required: true\\n    description: 要读取的Excel工作表名称\\noutputs:\\n  - name: 动态输出数组\\n    type: string\\n    description: 处理后的数据内容，格式取决于selectBox1配置\\n```\n\n运行逻辑（用 - 列表描写详细流程）\\n- 验证节点结构完整性，检查必需的Inputs和Outputs键是否存在\\n- 确保输入数组至少包含2个元素，输出数组为列表格式\\n- 对缺少selectBox1配置的输出项设置默认值\'All\'\\n- 获取FilePath和Table输入参数，验证其非空性\\n- 使用pandas的ExcelFile上下文管理器读取指定Excel文件和工作表\\n- 记录成功加载的数据框形状信息到日志\\n- 遍历数据框的每一行，调用process_row函数处理\\n- 在process_row中根据selectBox1值决定输出格式：\'All\'时生成包含列名和数据的markdown表格行，特定列名时仅输出该列值\\n- 为每个输出配置创建深拷贝并设置Context内容\\n- 将每行的处理结果添加到results列表中\\n- 单行处理异常时记录错误日志但继续处理其他行\\n- 返回包含所有行处理结果的二维列表结构\\n- 全程使用logging记录关键步骤和异常信息，确保处理过程可追踪'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Configure inputs
Inputs[0].update({
    'Kind': 'String_FilePath',
    'name': 'FilePath',
    'Isnecessary': True
})
Inputs[1].update({
    'Kind': 'String',
    'name': 'Table',
    'Isnecessary': True
})

def _detect_backend(filepath: str) -> str:
    ext = os.path.splitext(str(filepath))[1].lower()
    return 'sqlite' if ext in ('.db', '.sqlite') else 'excel'

def _safe_sqlite_table_name(name: str) -> str:
    # 允许字母数字下划线、空格、点、破折号、$；其它情况直接报配置错
    if not _re.match(r'^[\w\s\.\-\$]+$', str(name or '')):
        raise NodeConfigurationError(f"Illegal SQLite table name: {name!r}")
    return name

def validate_node_structure(node: Dict[str, Any]) -> None:
    """
    验证节点结构的完整性
    """
    required_keys = ['Inputs', 'Outputs']
    for key in required_keys:
        if key not in node:
            raise NodeConfigurationError(f"Missing required key: {key}")
    
    if not isinstance(node['Inputs'], list) or len(node['Inputs']) < 2:
        raise NodeConfigurationError("Node must have at least 2 inputs")
    
    if not isinstance(node['Outputs'], list):
        raise NodeConfigurationError("Outputs must be a list")
    
    # 若无输出，兜底增补一个默认输出（不改变既有使用者的 selectBox1 语义）
    if len(node['Outputs']) == 0:
        node['Outputs'].append({'selectBox1': 'All'})
    
    for output in node['Outputs']:
        if 'selectBox1' not in output:
            logger.warning("Output missing selectBox1, setting default value 'All'")
            output['selectBox1'] = 'All'

def validate_inputs(filepath: str, sheet: str) -> None:
    """
    验证输入参数的有效性
    - Excel: sheet 为工作表名
    - SQLite: sheet 为表名
    """
    if not filepath:
        raise NodeConfigurationError("FilePath cannot be empty")
    if not sheet:
        raise NodeConfigurationError("Sheet name (or table name) cannot be empty")

def process_row(row: pd.Series, df: pd.DataFrame, outputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    处理单行数据并生成输出
    """
    processed_outputs = []
    # 统一把当前行转成纯字符串视图（NaN -> ""）
    row_str = row.fillna("").astype(str)
    # 列名映射（规范 -> 原名），提升容错
    cols_map = {str(c).strip(): c for c in df.columns}
    
    for output in outputs:
        select_box_value = output.get('selectBox1', 'All')
        if select_box_value and select_box_value != 'All':
            select_box_value = select_box_value.split('/')[-1].strip()
        
        if select_box_value == 'All':
            header = "| " + " | ".join(map(str, df.columns)) + " |"
            values = "| " + " | ".join([row_str.get(col, "") for col in df.columns]) + " |"
            temp_context = header + "\n" + values
        elif select_box_value in cols_map:
            real_col = cols_map[select_box_value]
            temp_context = row_str.get(real_col, "")
        else:
            logger.warning(f"Invalid column selection: {select_box_value}")
            temp_context = "Invalid column selection"
        
        output_copy = copy.deepcopy(output)
        output_copy['Context'] = temp_context
        processed_outputs.append(output_copy)
    
    return processed_outputs
def run_node(node: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
    """
    执行节点的主函数
    """
    try:
        # 验证节点结构
        validate_node_structure(node)
        
        # 获取输入参数
        filepath = (node['Inputs'][0].get('Context') or '').strip()
        sheet = (node['Inputs'][1].get('Context') or '').strip()
        
        # 验证输入参数
        validate_inputs(filepath, sheet)
        
        logger.info(f"Processing file: {filepath}, sheet: {sheet}")
        
        results = []
        
        # 读取数据：Excel or SQLite
        try:
            backend = _detect_backend(filepath)
            if backend == 'sqlite':
                logger.info(f"Detected SQLite backend for file: {filepath}")
                # 只读直连，出错时抛出一致的 NodeExecutionError
                try:
                    _safe_sqlite_table_name(sheet)  # 先校验表名
                    with sqlite3.connect(filepath, timeout=5.0) as conn:
                        # 最小侵入：把 sheet 当成"表名"使用（与原入参保持一致）
                        # 用双引号包裹，兼容大小写/特殊字符
                        query = f'SELECT * FROM "{sheet}"'
                        df = pd.read_sql_query(query, conn)
                except Exception as ie:
                    raise NodeExecutionError(f"Error reading SQLite table '{sheet}': {ie}")
            else:
                logger.info(f"Detected Excel backend for file: {filepath}")
                try:
                    with pd.ExcelFile(filepath) as xls:
                        df = pd.read_excel(xls, sheet_name=sheet)
                except ValueError as ve:
                    raise NodeExecutionError(
                        f"Excel sheet '{sheet}' not found in file '{filepath}'"
                    ) from ve
            logger.info(f"Successfully loaded data. Shape: {df.shape}")
            # 处理每一行（保持你原有逻辑）
            for index, row in df.iterrows():
                try:
                    processed_outputs = process_row(row, df, node['Outputs'])
                    results.append(processed_outputs)
                    logger.debug(f"Processed row {index} successfully")
                except Exception as e:
                    logger.error(f"Error processing row {index}: {str(e)}")
                    traceback.print_exc()
                    continue
        except NodeExecutionError:
            # 上面已经构造过明确信息，透传
            raise
        except Exception as e:
            # 兜底（与原逻辑一致）
            raise NodeExecutionError(f"Error reading data: {str(e)}")
        
        logger.info(f"Successfully processed {len(results)} rows")
        return results
        
    except Exception as e:
        logger.error(f"Error in run_node: {str(e)}")
        traceback.print_exc()
        raise


