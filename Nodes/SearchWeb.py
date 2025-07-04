import json
import requests
from markdownify import markdownify as md

# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 1
# Define the number of outputs and inputs

FunctionIntroduction='组件功能：这是一个网页内容转Markdown格式转换器，用于将指定URL的网页内容抓取并转换为Markdown格式文本。\\n\\n代码功能摘要：通过HTTP请求获取网页HTML内容，使用markdownify库将HTML转换为Markdown格式，转换过程中会移除script和style标签，将标题转为ATX格式，列表转为星号格式。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: WebInput\\n    type: string\\n    required: true\\n    description: 需要转换的网页URL地址\\noutputs:\\n  - name: WebOutput\\n    type: string\\n    description: 转换后的Markdown格式文本内容\\n```\\n\\n运行逻辑：\\n- 从输入节点获取网页URL地址\\n- 设置User-Agent请求头模拟浏览器访问，避免被网站拦截\\n- 使用requests库发送GET请求获取目标网页的HTML内容\\n- 调用response.raise_for_status()确保请求成功，如有错误则抛出异常\\n- 使用markdownify库将获取的HTML内容转换为Markdown格式\\n- 转换时配置heading_style为ATX格式（使用#号表示标题）\\n- 设置strip参数移除script和style标签内容\\n- 设置bullets参数将列表项转换为星号格式\\n- 将转换完成的Markdown内容存储到输出节点中\\n- 返回包含转换结果的输出数组'
# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Input{i + 1}', 'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
# Initialize Outputs and Inputs arrays and assign names directly

NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Assign properties to Inputs and Outputs
for output in Outputs:
    output['Kind'] = 'String'
    output['name'] = 'WebOutput'

for input in Inputs:
    input['Kind'] = 'String'
    input['Isnecessary'] = True
    input['name'] = 'WebInput'
# Assign properties to Inputs and Outputs

# Function to fetch webpage content and convert to Markdown
def fetch_webpage_as_markdown(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # Ensure we notice bad responses
    html_content = response.text
    markdown_content = md(html_content, heading_style="ATX", strip=["script", "style"], bullets="*")
    return markdown_content

# Function definition
def run_node(node):
    url = node['Inputs'][0]['Context']
    markdown_content = fetch_webpage_as_markdown(url)
    Outputs[0]['Context'] = markdown_content
    return Outputs
# Function definition
