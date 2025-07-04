import pandas as pd
from io import StringIO
import re
import networkx as nx
from pyvis.network import Network

# 初始化输出和输入数组并直接分配名称
OutPutNum = 1
InPutNum = 1
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个将Markdown格式的图数据转换为可视化网络图的程序，能够解析包含节点和边信息的Markdown文本，并生成交互式的HTML网络图。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n程序通过正则表达式解析Markdown文本，提取节点和边的信息并转换为DataFrame格式，然后使用NetworkX创建有向图结构，最后通过pyvis库生成可交互的HTML网络可视化图。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: Input1\\n    type: string\\n    required: true\\n    description: Markdown格式的文本数据，包含节点信息和边信息两部分\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 输出确认消息，表示网络图已成功创建并保存\\n```\\n\\n运行逻辑\\n- 使用正则表达式将输入的Markdown文本按\"##\"分割成不同章节\\n- 解析每个章节，将其转换为DataFrame格式并清理数据（去除多余空格和竖线）\\n- 根据章节名称区分节点信息和边信息，分别存储到不同的数组中\\n- 使用NetworkX创建有向图对象DiGraph\\n- 遍历节点数据，为图添加节点并建立节点标签映射关系\\n- 遍历边数据，为图添加边连接关系并建立边标签映射关系\\n- 使用pyvis库创建交互式网络图对象\\n- 为每个节点添加悬停提示信息，包含节点ID和标签\\n- 为每条边添加悬停提示信息，显示关系类型\\n- 生成并保存HTML格式的可视化网络图文件\\n- 返回确认消息表示图形已成功创建和保存'
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
NodeKind = 'Normal'
Label = [{'Id': 'Label1', 'Kind': 'None'}]

# 分配输入和输出的属性
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'

# 解析Markdown章节
def parse_markdown_sections(markdown_data):
    sections = re.split(r'##\s+', markdown_data.strip())
    sections = [section for section in sections if section]
    return sections

# 将Markdown章节解析为DataFrame
def parse_section_to_df(section):
    lines = section.strip().split('\n')
    section_name = lines[0].strip()
    data = '\n'.join(lines[1:])
    data = re.sub(r'\|\s*$', '', data, flags=re.MULTILINE)  # 去除行末的额外竖线
    df = pd.read_csv(StringIO(data), sep='|', skipinitialspace=True)
    df.columns = df.columns.str.strip()  # 去除列名中的空格
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)  # 去除数据中的空格
    return section_name, df

# 测试解析Markdown数据
def run_node(node):
    Markdown = node['Inputs'][0]['Context']
    sections = parse_markdown_sections(Markdown)
    nodes = []
    edges = []

    for section in sections:
        section_name, df = parse_section_to_df(section)
        if 'Edge' in section_name:
            edges.append((section_name, df))
        else:
            nodes.append((section_name, df))

    # 创建NetworkX图
    G = nx.DiGraph()

    # 添加节点
    node_labels = {}
    for name, df in nodes:
        for index, row in df.iterrows():
            G.add_node(row['id'], label=row['name'])
            node_labels[row['id']] = row['name']

    # 添加边
    edge_labels = {}
    for name, df in edges:
        for index, row in df.iterrows():
            G.add_edge(row['sourceId'], row['targetId'], label=row['relationship'])
            edge_labels[(row['sourceId'], row['targetId'])] = row['relationship']

    # 使用pyvis进行可视化
    net = Network(notebook=False)
    net.from_nx(G)
    for node in net.nodes:
        node['title'] = f"ID: {node['id']}<br>Label: {node_labels[node['id']]}"
        node['label'] = node_labels[node['id']]

    for edge in net.edges:
        edge['title'] = f"Relationship: {edge_labels[(edge['from'], edge['to'])]}"
        edge['label'] = edge_labels[(edge['from'], edge['to'])]

    net.show('graph.html')
    
    content = "Graph visualization created and saved as graph.html"
    Outputs[0]['Context'] = content
    return Outputs