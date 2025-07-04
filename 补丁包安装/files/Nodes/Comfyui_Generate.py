import json
import requests
import os
import time
import urllib3
import logging

# 定义输出和输入的数量
OutPutNum = 1
InPutNum = 4

# 初始化 Outputs 和 Inputs 数组，并直接赋值名称
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个调用ComfyUI API生成AI图片的组件。通过读取工作流配置文件，设置提示词和图片名称，向ComfyUI服务发送请求来生成AI图片。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n核心功能包括URL解析、工作流文件加载、节点参数配置和API请求发送。主要处理步骤为：解析ComfyUI服务URL、读取JSON格式的工作流配置、修改工作流中的提示词节点和图片保存节点参数、通过HTTP POST请求触发图片生成流程。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: comfyui_url\\n    type: string\\n    required: true\\n    description: ComfyUI服务的URL地址\\n  - name: workflow_file_path\\n    type: file\\n    required: true\\n    description: 工作流配置文件路径，JSON格式\\n  - name: prompt\\n    type: string\\n    required: true\\n    description: 生成图片的文本描述提示词\\n  - name: Picture_name\\n    type: string\\n    required: true\\n    description: 生成图片的保存文件名前缀\\noutputs:\\n  - name: result\\n    type: string\\n    description: 返回图片生成的执行结果状态信息\\n```\\n\\n运行逻辑\\n- 接收ComfyUI服务URL并通过split_url函数解析为基础URL和查询参数\\n- 使用load_workflow函数读取指定路径的工作流配置文件，解析JSON格式数据\\n- 从工作流数据中定位到提示词节点（节点149）和图片保存节点（节点167）\\n- 将用户输入的prompt文本赋值给提示词节点的t5xxl输入参数\\n- 将用户指定的Picture_name设置为图片保存节点的filename_prefix参数\\n- 构造包含完整工作流的JSON数据，通过queue_prompt函数发送POST请求到ComfyUI的/prompt端点\\n- 发送请求后返回\"生成图片成功\"的结果状态信息'

# 为 Inputs 和 Outputs 赋值属性
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
Inputs[0]['name'] = 'comfyui_url'
Inputs[1]['Kind'] = 'String_FilePath'
Inputs[1]['name'] = 'workflow_file_path'
Inputs[2]['name'] = 'prompt'
Inputs[3]['name'] = 'Picture_name'
Outputs[0]['name'] = 'result'

# 函数定义
def split_url(url):
    # 找到第一个'/'后的部分
    split_position = url.find('/', url.find('//') + 2)
    if split_position != -1:
        # 基础 URL 是从头到最后一个 '/'
        base_url = url[:split_position + 1]
        # 剩余部分是从 '?' 开始
        query_position = url.find('?')
        if query_position != -1:
            rest_of_url = url[query_position:]  # 剩余部分从 '?' 开始
        else:
            rest_of_url = ''
        return base_url, rest_of_url
    else:
        return url, None
def ChangeFilePath(file_path):
    # 替换反斜杠为正斜杠

    return file_path
def run_node(node):
    URL= node['Inputs'][0]['Context']
    workflow_file_path = ChangeFilePath(node['Inputs'][1]['Context'])
    prompt = node['Inputs'][2]['Context']
    Picture_name = node['Inputs'][3]['Context']
    comfyui_url, Last_text = split_url(URL)

    # 从文件加载工作流
    def load_workflow(workflow_path):
        with open(workflow_path, 'r', encoding='utf-8') as file:
            workflow_data = json.load(file)
        return workflow_data

    # 将 prompt 队列到 ComfyUI API
    def queue_prompt(prompt_workflow):
        p = {"prompt": prompt_workflow}
        data = json.dumps(p).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url=comfyui_url + "/prompt", data=data, headers=headers, verify=False)
        
        if response.ok:
            print("请求成功，响应内容：", response.json())
        else:
            print("请求失败，状态码：", response.status_code)
        return response

    # 带重试的下载图片函数
    # 执行主要工作流
    workflow_data = load_workflow(workflow_file_path)

    # 给节点赋值
    prompt_pos_node = workflow_data["149"]
    save_image_node = workflow_data["167"]

    filename_prefixes = []
    prompt_pos_node["inputs"]["t5xxl"] = prompt
    filename_prefix = Picture_name
    save_image_node["inputs"]["filename_prefix"] = filename_prefix
    filename_prefixes.append(filename_prefix)
    queue_prompt(workflow_data)
    result = f"生成图片成功"
    # 返回结果
    Outputs[0]['Context'] = result
    return Outputs
