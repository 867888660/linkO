import json
import os
from tabulate import tabulate
import logging
import numpy as np
from openai import OpenAI


# **Function definition**
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个使用阿里云OCR API进行手写体识别的程序，能够读取图片文件并识别其中的手写文字内容。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n程序首先验证输入文件的存在性和格式有效性，然后使用阿里云OCR API客户端读取图片二进制数据，配置手写体识别参数（包括自动旋转、段落识别等），发送识别请求并处理返回结果，最终输出识别到的文字内容或相应的错误信息。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: File_Path\\n    type: file\\n    required: true\\n    description: 需要进行OCR识别的图片文件路径\\noutputs:\\n  - name: Result\\n    type: string\\n    description: 识别结果文本或错误信息\\n```\\n\\n运行逻辑（用 - 列表描写详细流程）\\n- 接收输入的图片文件路径参数\\n- 验证文件是否存在，如不存在则返回文件未找到错误\\n- 检查文件扩展名是否为支持的图片格式（.png、.jpg、.jpeg、.bmp、.gif、.tiff、.webp），如不支持则返回格式错误信息\\n- 导入阿里云OCR相关模块和客户端类\\n- 使用硬编码的访问密钥创建OCR客户端配置，设置服务端点为杭州区域\\n- 以二进制模式读取图片文件内容\\n- 创建手写体识别请求对象，配置参数：关闭字符信息输出、开启图片自动旋转、关闭表格输出、关闭页面排序、开启段落识别\\n- 设置运行时选项并发送OCR识别请求\\n- 处理API响应结果：如果成功则提取识别的文字数据，如果失败则构造包含错误代码和消息的错误信息\\n- 使用logging记录完整的OCR响应信息用于调试\\n- 捕获并处理可能出现的异常，记录错误日志\\n- 将最终结果（识别文字或错误信息）赋值给输出参数并返回'

# **Define the number of outputs and inputs**
OutPutNum = 1
InPutNum = 1
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly**
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# **Assign properties to Inputs**
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'File_Path'
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'
# **Assign properties to Inputs**
# **Function definition**
def run_node(node):
    file_path = node['Inputs'][0]['Context']
    content = ""
   
    # 检查文件是否存在
    if not os.path.exists(file_path):
        error_message = f"File not found: {file_path}"
        logging.error(error_message)
        Outputs[0]['Context'] = error_message
        return Outputs
    
    # 检查文件扩展名是否为支持的图片格式
    supported_formats = ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp']
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext not in supported_formats:
        error_message = f"Unsupported file format: {file_ext}. Supported formats are: {', '.join(supported_formats)}"
        logging.error(error_message)
        Outputs[0]['Context'] = error_message
        return Outputs
    
    try:
        # 导入阿里云OCR相关模块
        from alibabacloud_ocr_api20210707.client import Client as ocr_api20210707Client
        from alibabacloud_tea_openapi import models as open_api_models
        from alibabacloud_ocr_api20210707 import models as ocr_api_20210707_models
        from alibabacloud_tea_util import models as util_models
        from alibabacloud_tea_util.client import Client as UtilClient
        
        # 创建OCR客户端
        config = open_api_models.Config(
            # 从环境变量获取阿里云访问凭证
            access_key_id='LTAI5tAu92PxdWZ4Wd4QRReA',
            access_key_secret='IaZFlWtuDg3kdP2HnvGfEflQLW8d1s'
        )
        config.endpoint = 'ocr-api.cn-hangzhou.aliyuncs.com'
        client = ocr_api20210707Client(config)
        
        # 读取图片文件为二进制数据
        with open(file_path, 'rb') as f:
            image_bytes = f.read()
        print(f"Access Key ID: {'已设置' if os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID') else '未设置'}")
        print(f"Access Key Secret: {'已设置' if os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET') else '未设置'}")

        # 创建手写体识别请求
        recognize_request = ocr_api_20210707_models.RecognizeHandwritingRequest(
            body=image_bytes,
            output_char_info=False,
            need_rotate=True,
            output_table=False,
            need_sort_page=False,
            paragraph=True
        )
        
        # 设置运行时选项
        runtime = util_models.RuntimeOptions()
        
        # 发送请求并获取响应
        response = client.recognize_handwriting_with_options(recognize_request, runtime)
        
        # 处理响应结果
        if hasattr(response.body, 'data') and response.body.data:
            # 直接返回 OCR 结果
            content = response.body.data
        else:
            # 提供更详细的错误信息
            error_code = response.body.code if hasattr(response.body, 'code') else '未知'
            error_message = response.body.message if hasattr(response.body, 'message') and response.body.message else '未提供错误信息'
            content = f"OCR 失败: 代码={error_code}, 消息={error_message}"
            
        # 记录完整的响应以便调试
        logging.info(f"完整的 OCR 响应: {response.body.to_map()}")
            
    except Exception as e:
        error_message = f"Error processing OCR: {str(e)}"
        logging.error(error_message)
        
    
    Outputs[0]['Context'] = content
    return Outputs