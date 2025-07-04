import asyncio, os, platform
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

# **Function definition**

# **Define the number of outputs and inputs**输入节点与输出节点的数量
OutPutNum = 1
InPutNum = 1
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly**
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='这个程序是一个基于MCP协议的网页内容抓取工具。\\n\\n代码功能摘要：通过MCP(Message Channel Protocol)协议调用fetcher-mcp工具，异步获取指定URL的网页内容并提取文本信息，支持多种数据格式的统一转换处理。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: Input1\\n    type: string\\n    required: true\\n    description: 需要抓取内容的网页URL地址\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 抓取到的网页文本内容\\n```\\n\\n运行逻辑：\\n- 从输入节点获取目标网页的URL地址\\n- 调用make_server_params()函数配置MCP服务器参数，包括设置环境变量、适配Windows和非Windows系统的不同执行命令、设置15秒超时保护\\n- 通过MCP_SEVER()异步函数建立与fetcher-mcp工具的连接\\n- 在ClientSession中调用fetch_url工具，传入URL参数和extractContent标志\\n- 使用to_str()函数处理返回的各种数据格式：bytes类型数据解码、Response对象的text属性提取、content属性处理、可迭代对象的拼接转换\\n- 将处理后的文本内容写入输出节点并返回结果'
# **Assign properties to Inputs**
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
#            节点类别有String,Num,Boolean,String_FilePath
#Inputs[0]['Kind'] = 'String_FilePath'
#                 节点名称
#Inputs[0]['name'] = 'File_Path'
#             节点是否需要输入
#Inputs[0]['Isnecessary'] = True
#              节点是否是标签
#Inputs[0]['IsLabel'] = True

#Outputs[0]['Kind'] = 'String'
#Outputs[0]['name'] = 'Result'

### DeBugging用于解锁调试功能，输出调试信息
#Outputs[1]['Kind'] = 'String'
#Outputs[1]['name'] = 'DeBugging'
###
# **Assign properties to Inputs**
# **Function definition**
#配置mcp的参数
def to_str(out):
    # 如果就是 bytes
    if isinstance(out, (bytes, bytearray)):
        return out.decode('utf-8', errors='replace')

    # requests.Response 或类似有 text 属性的
    if hasattr(out, 'text'):
        return out.text

    # 有 content 属性（可能是 bytes，也可能是其它类型）
    if hasattr(out, 'content'):
        data = out.content
        if isinstance(data, (bytes, bytearray)):
            # 尝试用 out.encoding，没有就 utf-8
            encoding = getattr(out, 'encoding', 'utf-8')
            try:
                return data.decode(encoding)
            except Exception:
                return data.decode(encoding, errors='replace')
        else:
            return str(data)

    # 如果是个可迭代的列表/元组（比如 MCP 返回的 [TextContent,...]）
    if isinstance(out, (list, tuple)):
        return ''.join(to_str(item) for item in out)

    # 兜底
    return str(out)

def make_server_params() -> StdioServerParameters:
    env = os.environ.copy()                    # 保留 PATH，避免 npx 解析失败
    #env["API_KEY"] =
    is_win = platform.system() == "Windows"
    return StdioServerParameters(
        command="cmd" if is_win else "npx",
        args=["/c", "npx", "-y", "fetcher-mcp"] if is_win
             else ["-y", "fetcher-mcp"],
        env=env, timeout=15000,
    )
#调用mcp的函数
async def MCP_SEVER(search_content):
    async with stdio_client(make_server_params()) as (r, w):
        async with ClientSession(r, w) as sess:
            await sess.initialize()

            out = await sess.call_tool(
                "fetch_url",
                arguments={
                    "url": search_content,
                    "extractContent": True,
                },
            )
            decoded=to_str(out.content)
            return decoded
def run_node(node):
    # 1. 先从 node 里取出 Outputs（如果没有，就初始化一个空列表）
    Outputs = node.get('Outputs', [])
    if not Outputs:
        # 如果根本没 Outputs，就新建一个
        Outputs = [{"Context": ""}]

    # 2. 取出输入内容
    search_content = node['Inputs'][0]['Context']

    # 3. 调用异步函数，务必保证 main 有 return
    content = asyncio.run(MCP_SEVER(search_content))
    print('抓取到的内容:', content)
    # 4. 填回 Outputs
    Outputs[0]['Context'] = content


    return Outputs
##写出你需要的功能，有需要可以用Debugging输出调试信息，调试信息会在控制台输出，也会在输出节点中输出，方便调试。
# **Function definition**