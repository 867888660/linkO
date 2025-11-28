import os
import re
import json
import base64
import logging
from pathlib import Path

import chardet
import PyPDF2
import docx2txt
import pandas as pd
from tabulate import tabulate
import fitz  # PyMuPDF
from openai import OpenAI

# ============================ 基础配置 ============================ #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# 若使用 DashScope 兼容模式，密钥放到环境变量里：
DASHSCOPE_API_KEY = "sk-d08a424af9d44655934ad7117c77ebd2"
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# ============================ I/O 定义 ============================ #

OutPutNum = 1
InPutNum = 1

Outputs = [{
    'Num': None, 'Kind': 'String', 'Boolean': False,
    'Id': f'Output1', 'Context': None, 'name': f'OutPut1',
    'Link': 0, 'Description': '提取的文件内容'
}]

Inputs = [{
    'Num': None, 'Kind': 'String_FilePath', 'Id': f'Input1',
    'Context': None, 'Isnecessary': True, 'name': f'Input1',
    'Link': 0, 'IsLabel': True
}]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# ============================ 工具函数 ============================ #

def detect_encoding(file_path: str) -> str:
    """自动探测文本文件编码，失败时回退 utf-8"""
    with open(file_path, 'rb') as f:
        raw = f.read(2048)
    result = chardet.detect(raw)
    enc = result.get('encoding') or 'utf-8'
    return enc

def extract_text_with_ocr(pdf_path: str, page_num: int) -> str:
    """
    针对图片型 PDF 页面，调用 Qwen 视觉大模型做 OCR
    """
    try:
        doc = fitz.open(pdf_path)
        if page_num >= len(doc):
            return ""

        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        img_b64 = base64.b64encode(pix.tobytes("jpeg")).decode('utf-8')
        doc.close()

        client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=DASHSCOPE_BASE_URL)

        messages = [
            {'role': 'user',
             'content': '你是一名图片板书员，你需要为我板书图片中你所看到的文字，强调不要有除图片内容任何多余文字'},
            {'role': 'user',
             'content': [{'type': 'image_url',
                          'image_url': {'url': f'data:image/jpeg;base64,{img_b64}'}}]}
        ]

        resp = client.chat.completions.create(
            model="qwen2.5-vl-7b-instruct",
            messages=messages,
            temperature=0.3,
            max_tokens=2000,
            top_p=0.95
        )

        return resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error("OCR 失败（第 %d 页）: %s", page_num + 1, e, exc_info=True)
        return ""

# ============================ 主执行函数 ============================ #

def run_node(node: dict):
    file_path: str = node['Inputs'][0]['Context']
    if not file_path or not Path(file_path).exists():
        Outputs[0]['Context'] = f"文件不存在：{file_path}"
        return Outputs

    content = ""

    # ---------- 文本 / SRT ---------- #
    if file_path.endswith(('.txt', '.srt')):
        enc = detect_encoding(file_path)
        logging.info("检测到文件编码：%s", enc)
        with open(file_path, 'r', encoding=enc, errors='ignore') as f:
            if file_path.endswith('.srt'):
                lines = f.readlines()
                subtitles = [
                    ln.strip() for ln in lines
                    if not re.match(r'^\d+$', ln.strip())
                    and not re.match(r'^\d{2}:\d{2}:\d{2},\d{3}', ln.strip())
                    and ln.strip()
                ]
                content = '\n'.join(subtitles)
            else:
                content = f.read()

    # ---------- JSON ---------- #
    elif file_path.endswith('.json'):
        enc = detect_encoding(file_path)
        with open(file_path, 'r', encoding=enc, errors='ignore') as f:
            obj = json.load(f)
        content = json.dumps(obj, ensure_ascii=False, indent=4)

    # ---------- PDF ---------- #
    elif file_path.endswith('.pdf'):
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                logging.info("PDF 总页数：%d", len(reader.pages))
                needs_ocr = False

                for idx, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ''
                    if len(page_text.strip()) < 10:
                        logging.debug("第 %d 页文本过短，将使用 OCR", idx + 1)
                        needs_ocr = True
                    content += page_text

            # 如必要，OCR
            if needs_ocr or not content.strip():
                logging.info("检测到图片型 PDF，切换 OCR 流程…")
                content = ""
                doc = fitz.open(file_path)
                for idx in range(len(doc)):
                    logging.info("OCR 处理第 %d/%d 页…", idx + 1, len(doc))
                    content += extract_text_with_ocr(file_path, idx) + "\n\n"
                doc.close()

        except Exception as e:
            logging.error("处理 PDF 出错：%s", e, exc_info=True)
            content = f"Error processing PDF: {e}"

    # ---------- Word ---------- #
    elif file_path.endswith('.docx'):
        content = docx2txt.process(file_path)

    # ---------- Excel ---------- #
    elif file_path.endswith(('.xlsx', '.xls')):
        excel_data = pd.read_excel(file_path, sheet_name=None)
        for sheet, df in excel_data.items():
            content += f"## {sheet}\n\n"
            content += tabulate(df, headers='keys', tablefmt='pipe', showindex=False)
            content += "\n\n"

    else:
        content = "Unsupported file format"

    Outputs[0]['Context'] = content.strip()
    return Outputs
