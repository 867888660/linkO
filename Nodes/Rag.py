import json
import logging
import math
import os
import re
import requests
from typing import List

# ============ 基本定义（与原代码一致，只改 InPutNum） ============
OutPutNum = 1
InPutNum  = 5            # ←★ 修正为 5
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False,
            'Id': f'Output{i+1}', 'Context': None,
            'name': f'OutPut{i+1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i+1}',
           'Context': None, 'Isnecessary': True,
           'name': f'Input{i+1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction = '组件功能（简述代码整体功能）\n这是一个基于语义向量的文本搜索组件，通过阿里云DashScope的text-embedding-v3模型对JSONL格式的文本数据进行语义相似度搜索和排序。支持多个查询词，使用**分隔。\n\n代码功能摘要（概括核心算法或主要处理步骤）\n核心算法采用向量余弦相似度计算，先读取JSONL文件并根据项目名称进行预筛选，然后使用DashScope API将查询文本和候选文本转换为向量，计算相似度并按分数降序排列，最终返回符合阈值要求的前N个结果。支持多个查询词，分别计算并输出结果。\n\n参数\n```yaml\ninputs:\n  - name: Json_Path\n    type: file\n    required: true\n    description: 包含待搜索文本数据的JSONL格式文件路径\n  - name: Select_item\n    type: string\n    required: true\n    description: 用于预筛选的项目名称，支持逗号分隔多个关键词，当为\"All\"时跳过筛选\n  - name: query\n    type: string\n    required: true\n    description: 用户输入的搜索查询文本，支持**分隔多个查询词\n  - name: Rank\n    type: integer\n    required: true\n    description: 返回搜索结果的最大数量\n  - name: Min_Score\n    type: number\n    required: true\n    description: 相似度分数的最小阈值，低于此值的结果将被过滤\noutputs:\n  - name: Result\n    type: string\n    description: 包含调试信息和格式化搜索结果的完整文本输出\n```\n\n运行逻辑\n- 读取并验证输入参数，检查JSONL文件是否存在\n- 逐行解析JSONL文件内容，将每行转换为JSON对象\n- 根据Select_item参数对数据进行预筛选，保留ID中包含指定关键词的条目，若Select_item为\"All\"不做筛选\n- 提取所有候选文本内容，准备进行向量化处理\n- 调用DashScope的text-embedding-v3模型，将查询文本和候选文本批量转换为向量\n- 计算查询向量与每个候选向量的余弦相似度分数\n- 按相似度分数降序排列所有结果，取前Rank个候选项\n- 应用Min_Score阈值过滤，只保留相似度大于等于阈值的结果\n- 格式化输出结果，包含序号、ID、相似度分数和文本片段预览\n- 如果没有符合条件的结果，返回相应的提示信息\n- 将调试信息和搜索结果合并，生成最终的输出文本'

# ---- I/O 字段属性 ----
for out in Outputs:
    out['Kind'] = 'String'
Outputs[0]['name'] = 'Result'

for inp in Inputs:
    inp['Kind'] = 'String'
Inputs[0]['Kind'], Inputs[0]['name'] = 'String_FilePath', 'Json_Path'
Inputs[1]['name'] = 'Select_item'
Inputs[2]['name'] = 'query'
Inputs[3]['Kind'], Inputs[3]['name'] = 'Num', 'Rank'
Inputs[4]['Kind'], Inputs[4]['name'] = 'Num', 'Min_Score'

# ============ DashScope Embedding =============
DASHSCOPE_API_KEY = 'sk-194e194cc95a4951a33d8666a6fffa80'  # ← 请替换为你自己的密钥
EMBED_URL = 'https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding'
EMBED_MODEL = 'text-embedding-v3'
MAX_BATCH = 10  # 官方限制

def dashscope_embed(texts: List[str]) -> List[List[float]]:
    """调用 text-embedding-v3，返回每句向量"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {DASHSCOPE_API_KEY}'
    }
    vectors = []
    for i in range(0, len(texts), MAX_BATCH):
        chunk = texts[i:i + MAX_BATCH]
        payload = {
            "model": EMBED_MODEL,
            "input": {"texts": chunk}
        }
        resp = requests.post(EMBED_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()["output"]["embeddings"]
        vectors.extend([item["embedding"] for item in data])
    return vectors

def cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

def normalize_select(raw: str) -> List[str]:
    """'AddIntroduce,AddNode.py' → ['addintroduce','addnode']"""
    return [p.lower().replace('.py', '') for p in re.split(r'[\,\s]+', raw) if p.strip()]

# ============ 主函数 ============

def run_node(node):
    Debugging = []
    try:
        # -------- 1. 读取输入 --------
        Json_Path   = node['Inputs'][0]['Context']
        Select_item = node['Inputs'][1]['Context']
        query       = node['Inputs'][2]['Context']
        Rank        = int(float(node['Inputs'][3]['Num']))
        Min_Score   = float(node['Inputs'][4]['Num'])

        Debugging.append(f"[Input] Path={Json_Path}")
        Debugging.append(f"[Input] Select_item='{Select_item}', Rank={Rank}, Min_Score={Min_Score}")

        # -------- 2. 读取 jsonl --------
        if not os.path.isfile(Json_Path):
            raise FileNotFoundError(f"找不到文件: {Json_Path}")
        with open(Json_Path, 'r', encoding='utf-8') as f:
            rows = [json.loads(line) for line in f if line.strip()]

        # -------- 3. Select_item 过滤 --------
        select_raw = (Select_item or '').strip()
        if select_raw.lower() != 'all':
            targets = normalize_select(select_raw)
            rows = [r for r in rows if any(t in r.get('id', '').lower() for t in targets)]
            Debugging.append(f"[Filter] Select_item='{Select_item}' → 候选条目数 = {len(rows)}")
            if not rows:
                raise ValueError("Select_item 过滤后无匹配条目")
        else:
            Debugging.append("[Filter] Select_item='All' → 不做筛选，使用全部条目")

        # -------- 4. 向量化和相似度计算 --------
        query_list = query.split('**')
        all_results = []
        corpus_texts = [r['text'] for r in rows]
        corpus_vecs  = dashscope_embed(corpus_texts)  # ← 只计算一次候选向量，提高效率

        for q in query_list:
            query_vec = dashscope_embed([q])[0]

            # -------- 5. 相似度排序 --------
            scored = sorted(
                zip(rows, corpus_vecs),
                key=lambda x: cosine(query_vec, x[1]),
                reverse=True
            )[:Rank]

            final = [(r, cosine(query_vec, v)) for r, v in scored if cosine(query_vec, v) >= Min_Score]
            Debugging.append(f"[Rank] Query='{q}' Top {Rank} → 保留 {len(final)} 条")

            # -------- 6. 结果整理 --------
            if final:
                lines = []
                for idx, (r, s) in enumerate(final, 1):
                    snippet = r['text'][:120].replace('\n', ' ')
                    lines.append(f"{idx}. id={r['id']}  score={s:.4f}\n   {snippet}…")
                content = "\n".join(lines)
            else:
                content = "⚠️ 无符合阈值的结果"

            all_results.append(f"=== Query: {q} ===\n" + content)

        content = "\n\n".join(all_results)

    except Exception as e:
        content = f"❌ 运行失败: {e}"
        import traceback; Debugging.append(traceback.format_exc())

    # -------- 7. 输出 --------
    Outputs[0]['Context'] = "\n".join(Debugging) + "\n\n=== 结果 ===\n" + content
    return Outputs
