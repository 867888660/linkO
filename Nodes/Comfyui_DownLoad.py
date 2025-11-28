import json
import requests
import os
import time
import urllib3
import logging
# 定义输出和输入的数量
OutPutNum = 2
InPutNum = 3

# 初始化 Outputs 和 Inputs 数组，并直接赋值名称
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能：这是一个从ComfyUI服务器下载生成图片的节点，可以将ComfyUI生成的图片下载到本地指定路径并保存为PNG格式。\\n\\n代码功能摘要：通过解析ComfyUI的URL地址，构建图片下载链接，使用HTTP请求获取图片数据，并实现带重试机制的下载功能，最终将图片保存到指定目录。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: comfyui_url\\n    type: string\\n    required: true\\n    description: ComfyUI服务器的完整URL地址\\n  - name: Save_path\\n    type: string\\n    required: true\\n    description: 图片保存的本地目录路径\\n  - name: Picture_name\\n    type: string\\n    required: true\\n    description: 保存图片的文件名（不含扩展名）\\noutputs:\\n  - name: result\\n    type: string\\n    description: 下载操作的结果状态，返回\"成功\"或\"失败\"\\n  - name: Picture_Path\\n    type: string\\n    description: 保存图片的完整文件路径\\n```\\n\\n运行逻辑：\\n- 接收ComfyUI的URL地址、保存路径和图片名称作为输入参数\\n- 使用split_url函数解析URL，将其分离为基础URL和查询参数部分\\n- 调用download_image_with_retries函数执行带重试机制的图片下载\\n- 构建完整的图片下载URL，格式为基础URL + \"/fb/api/preview/big/output/\" + 图片名称 + \"_00001_.png\" + 查询参数\\n- 创建HTTP会话并发送GET请求获取图片数据\\n- 检查HTTP响应状态码，验证Content-Type是否为图片类型\\n- 如果下载失败，等待10秒后重试，最多尝试100次\\n- 检查保存目录是否存在，不存在则自动创建\\n- 清理路径和文件名中的多余空格字符\\n- 将图片数据写入本地文件，保存为PNG格式\\n- 返回下载结果状态和完整的图片保存路径'

# 为 Inputs 和 Outputs 赋值属性
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
Inputs[0]['name'] = 'comfyui_url'
Inputs[1]['name'] = 'Save_path'
Inputs[1]['Kind'] = 'String_FilePath'
Inputs[2]['name'] = 'Picture_name'
Outputs[0]['name'] = 'result'
Outputs[1]['name'] ='Picture_Path'

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
    Save_path = ChangeFilePath(node['Inputs'][1]['Context'])
    Picture_name = node['Inputs'][2]['Context']
    comfyui_url, Last_text = split_url(URL)

    # 带重试的下载图片函数
    def download_image_with_retries(Save_path, Picture_name, Url, Last_text, max_retries=100, wait_time=10):
        full_url = f"{Url}/fb/api/preview/big/output/{Picture_name}_00001_.png{Last_text}"
        session = requests.Session()

        for attempt in range(max_retries):
            print(f"尝试下载图片: 尝试 {attempt + 1} / {max_retries}")
            print(f"下载路径: {full_url}")
            response = session.get(full_url, verify=False)

            if response.status_code == 200:
                content_type = response.headers.get('Content-Type')
                print(f"内容类型: {content_type}")

                if 'image' not in content_type:
                    print("警告: 响应内容可能不是图片。")
                    return "失败"

                if not os.path.exists(Save_path):
                    os.makedirs(Save_path)
                # 去除路径中的多余空格
                Save_path = Save_path.strip()  # 去掉路径首尾的空格
                Picture_name = Picture_name.strip()  # 去掉图片名称中的空格

                save_path = os.path.join(Save_path, Picture_name  + ".png")
                print(f"正在下载图片到: {save_path}")

                with open(save_path, "wb") as out_file:
                    out_file.write(response.content)

                print(f"图片已成功下载并保存到: {save_path}")
                return "成功"
            else:
                print(f"下载失败，HTTP 状态码: {response.status_code}")
            
            if attempt < max_retries - 1:
                print(f"等待 {wait_time} 秒后重新尝试下载...")
                time.sleep(wait_time)

        return "失败"


    # 下载图片并重复尝试
    result = download_image_with_retries(Save_path, Picture_name, comfyui_url, Last_text)

    # 返回结果
    Outputs[0]['Context'] = result
    Outputs[1]['Context'] = Save_path+'\\'+Picture_name  + ".png"
    return Outputs