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
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个基于MCP协议的文件信息获取组件，通过与外部工具通信来获取指定文件的详细信息。\n\n代码功能摘要（概括核心算法或主要处理步骤）\\n组件使用MCP（Message Control Protocol）协议建立与外部工具的通信连接，通过stdio客户端调用get_file_info工具来获取文件信息。核心流程包括配置服务器参数、建立异步会话、调用工具接口并返回文件信息结果。\n\n参数\\n```yaml\\ninputs:\\n  - name: Input1\\n    type: string\\n    required: true\\n    description: 需要获取信息的文件路径\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 返回的文件信息内容\\n```\n\n运行逻辑\\n- 从输入节点Input1获取目标文件路径\\n- 根据操作系统类型配置MCP服务器参数，Windows使用cmd命令，其他系统使用npx命令\\n- 设置环境变量和15秒超时时间\\n- 建立stdio客户端连接\\n- 创建异步客户端会话并初始化\\n- 调用get_file_info工具，传入文件路径参数\\n- 获取工具返回的文件信息内容\\n- 将文件信息结果存储到输出节点OutPut1中\\n- 返回包含文件信息的输出数组'
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
def make_server_params() -> StdioServerParameters:
    env = os.environ.copy()                    # 保留 PATH，避免 npx 解析失败
    #env["API_KEY"] =
    is_win = platform.system() == "Windows"
    return StdioServerParameters(
        command="cmd" if is_win else "npx",
        args=["/c", "npx", "-y", "调用名称"] if is_win
             else ["-y", "调用名称"],
        env=env, timeout=15000,
    )
#调用mcp的函数
async def main():
    async with stdio_client(make_server_params()) as (r, w):
        async with ClientSession(r, w) as sess:
            await sess.initialize()

            out = await sess.call_tool(
                "get_file_info",
                arguments={
                    "path": "C:\\Users\\YMXD\\Desktop\\linkO\\linkel\\Mcp\\McpList.json"
                },
            )

            print(out.content)
def run_node(node):
    file_path = node['Inputs'][0]['Context']
    content = ""
    Debugging = []
        
    asyncio.run(main())
    Outputs[0]['Context'] = content
    return Outputs
##写出你需要的功能，有需要可以用Debugging输出调试信息，调试信息会在控制台输出，也会在输出节点中输出，方便调试。
# **Function definition**