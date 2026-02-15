import json
import re
import http.client
import string
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
#**Define the number of outputs and inputs

FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个大语言模型（LLM）节点，用于处理和分析文本内容，支持字数统计、文本查找和内容提取等功能。该节点可以根据不同的描述模式对输入的提示文本进行处理，并输出相应的结果。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n核心功能包括文本预处理（去除标点符号）、模式匹配识别（支持查找模式和字数统计模式）、文本内容提取和字数统计。主要通过正则表达式匹配特定模式，对ExportPrompt文本进行分析处理，根据不同的描述要求输出对应的文本内容或统计数据。\\n\\n参数\\n```yaml\\ninputs: []\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 处理后的文本内容或统计结果\\n```\\n\\n运行逻辑\\n- 作为LLM节点，该组件可以动态创建输入和输出节点\\n- 接收ExportPrompt文本作为处理对象\\n- 对输出节点的描述进行模式匹配，识别是否包含查找模式<@find:\"...\">或字数统计模式<@WordsNum>\\n- 如果匹配到查找模式，则在ExportPrompt中搜索指定的文本内容，提取匹配行的后续内容\\n- 如果匹配到字数统计模式，则对文本进行标点符号清理，统计去除标点后的字符数量\\n- 对于默认输出，会移除ExportPrompt中最后一个\"Please\"之前的内容，并清理末尾换行符\\n- 将处理结果存储到对应的输出节点Context字段中\\n- 返回包含所有处理结果的输出数组'
#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':'answer'} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum)]
#**Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'LLm'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

PUNCT = string.punctuation + '，。！？；：…“”‘’（）《》【】—、'
def remove_punctuation(s: str) -> str:
    return s.translate(str.maketrans('', '', PUNCT))

# 更稳的“裁掉结尾 JSON 输出指令”规则：优先匹配完整短语；兜底匹配同一行同时包含 Please + JSON
JSON_INSTRUCTION_LINE_RE = re.compile(
    r'(?im)^\s*Please\s+ensure\s+the\s+output\s+is\s+in\s+JSON\s+format\b.*$'
)
PLEASE_JSON_LINE_RE = re.compile(r'(?im)^\s*Please\b.*\bJSON\b.*$')

def strip_trailing_json_instruction(text: str) -> str:
    """
    从 ExportPrompt 里裁掉末尾的“请以 JSON 输出”的指令行，避免用裸 'Please' 误裁切正文。
    - 先找最后一条：Please ensure the output is in JSON format ...
    - 找不到则兜底找最后一条：同一行同时包含 Please 和 JSON
    """
    matches = list(JSON_INSTRUCTION_LINE_RE.finditer(text))
    if not matches:
        matches = list(PLEASE_JSON_LINE_RE.finditer(text))
    if not matches:
        return text.rstrip('\n')
    last = matches[-1]
    return text[: last.start()].rstrip('\n')

# 支持两种形式：<@WordsNum"foo"> 或 <@WordsNum>
PAT = r'<@WordsNum(?:"(.*?)")?>'
#**Assign properties to Inputs

for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
#**Assign properties to Inputs
def remove_punctuation(text: str) -> str:
    return text.translate(str.maketrans('', '', PUNCT))

def count_chars_exclude_punc(text: str) -> int:
    cleaned = remove_punctuation(text)
    return len(cleaned)
#**Function definition
def run_node(node):
    Outputs.clear()
    for i in range(len(node['Outputs'])):
        Outputs.append(node['Outputs'][i])
    
    # Process Outputs[0] as before
    Outputs[0]['Context'] = strip_trailing_json_instruction(node['ExportPrompt'])


    # Process Outputs[1-n] with new logic
    for i in range(0, len(node['Outputs'])):
        description = Outputs[i]['Description']
        match = re.search(r'<@find:"(.*?)">', description)
        if match:
            context_to_find = match.group(1)
            lines = node['ExportPrompt'].split('\n')
            for line in lines:
                if line.startswith(context_to_find):
                    # Get the context after the search term
                    context_part = line[len(context_to_find):].strip()
                    # Remove the <@find:"..."> pattern and combine with remaining description
                    remaining_description = re.sub(r'<@find:".*?">', '', description).strip()
                    Outputs[i]['Context'] = context_part + remaining_description
                    break
            else:
                Outputs[i]['Context'] = ''  # Default to empty if not found
        match = re.search(PAT, description)
        if match:
            key = match.group(1) or ''
            # 先从 ExportPrompt 里找包含 key 的那行
            context_part = ''

            full = node['ExportPrompt']
            print('Test 2', full)
            # 去标点
            full = strip_trailing_json_instruction(full)
            cleaned = remove_punctuation(full)

            # 统计字数
            Outputs[i]['Num'] = len(cleaned)
            Outputs[i]['Context'] = len(cleaned)



    return Outputs