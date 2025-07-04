import json
import os
import http.client
import requests
import re
import PyPDF2
import docx2txt
import pandas as pd
from tabulate import tabulate
import networkx as nx
from pyvis.network import Network
import webbrowser

# **Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 1
# **Define the number of outputs and inputs

# **Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='这是用来将Excel文件转换为图形的节点。\n\n输入：Excel文件路径。\n\n输出：图形可视化的HTML文件路径。'
# **Assign properties to Inputs
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String_FilePath'
# **Assign properties to Inputs

# **Function definition
def run_node(node):
    file_path = node['Inputs'][0]['Context']
    content = ""

    def create_graph_from_excel(file_path):
        try:
            # 读取Excel文件
            xls = pd.ExcelFile(file_path)
            
            # 初始化节点和边的DataFrame列表
            nodes_dfs = []
            edges_dfs = []

            # 遍历所有sheet，根据名称区分节点和边数据
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                if 'Edge' in sheet_name:
                    edges_dfs.append(df)
                else:
                    nodes_dfs.append(df)

            # 打印检查
            for nodes_df in nodes_dfs:
                print("Nodes DataFrame:")
                print(nodes_df.head())
            for edges_df in edges_dfs:
                print("\nEdges DataFrame:")
                print(edges_df.head())
            
            # 创建NetworkX图
            G = nx.DiGraph()

            # 添加节点
            node_labels = {}
            node_colors = {}
            node_info = {}
            outer_colors = {
                'Character': '#3498db',  # blue
                'Event': '#2ecc71',      # green
                'Prop': '#e67e22',       # orange
                'Chapter': '#e74c3c',      # red
                'Skill': '#e74c33',      # yellow
                'Foreshadowing': '#9b59b6'  # purple
            }
            inner_colors = {
                'Character': '#85c1e9',  # light blue
                'Event': '#58d68d',      # light green
                'Prop': '#f0b27a',       # light orange
                'Chapter': '#f1948a',      # light red
                'Skill': '#e74c33',      # yellow
                'Foreshadowing': '#c39bd3'  # light purple
            }
            for nodes_df in nodes_dfs:
                for index, row in nodes_df.iterrows():
                    G.add_node(row['id'], label=row['name'])
                    node_labels[row['id']] = row['name']
                    node_colors[row['id']] = (outer_colors.get(row['type'], 'gray'), inner_colors.get(row['type'], 'lightgray'))
                    node_info[row['id']] = row.to_dict()

            # 添加边
            edge_labels = {}
            for edges_df in edges_dfs:
                for index, row in edges_df.iterrows():
                    G.add_edge(row['sourceId'], row['targetId'], label=row['relationship'])
                    edge_labels[(row['sourceId'], row['targetId'])] = row.to_dict()

            # 使用pyvis进行可视化
            net = Network(notebook=False, width="100%", height="900px", bgcolor='#ffffff', font_color='#000000')
            net.from_nx(G)
            for node in net.nodes:
                outer_color, inner_color = node_colors[node['id']]
                info = node_info[node['id']]
                node['title'] = "\n".join([f"{key}: {value}" for key, value in info.items()])
                node['label'] = node_labels[node['id']]
                node['color'] = {
                    'border': outer_color,
                    'background': inner_color,
                    'highlight': {
                        'border': outer_color,
                        'background': inner_color
                    }
                }

            for edge in net.edges:
                # 假设 edge_labels 是一个包含边信息的字典
                try:
                    info_from_to = edge_labels.get((edge['from'], edge['to']), {})
                    info_to_from = edge_labels.get((edge['to'], edge['from']), {})

                    # 初始化一个新的字典来存储合并信息
                    info_combined = {}

                    # 为 from-to 方向的键添加数字后缀 1
                    for key, value in info_from_to.items():
                        info_combined[f"{key}_1"] = value

                    # 为 to-from 方向的键添加数字后缀 2
                    for key, value in info_to_from.items():
                        info_combined[f"{key}_2"] = value

                    # 调试信息：打印获取到的信息
                    print('测试分割\n\n\n')
                    print(f"info_from_to: {info_from_to}")
                    print(f"info_to_from: {info_to_from}")
                    print(f"info_combined: {info_combined}")

                    # 将信息格式化为字符串并赋值给 edge['title']
                    edge['title'] = "\n".join([f"{key}: {value}" for key, value in info_combined.items()])

                    # 设置边的标签
                    edge['label'] = info_from_to.get('relationship', 'No relationship')

                    # 判断边的类型，决定是否为单向边
                    # 判断边的类型和数量，决定是否为单向边
                    if (info_from_to.get('type') in ['CharacterToCharacterEdge', 'EventAndEventEdge'] and not info_to_from) or \
                    (info_to_from.get('type') in ['CharacterToCharacterEdge', 'EventAndEventEdge'] and not info_from_to):
                        edge['arrows'] = 'to'
                    else:
                        edge['arrows'] = 'none'
                        
                except Exception as e:
                    # 如果发生异常，打印异常信息
                    print(f"Error: {e}")
                    edge['title'] = "Error occurred during edge processing"


            # 设置布局以减少拥挤
            net.repulsion(
                node_distance=200,
                central_gravity=0.1,
                spring_length=200,
                spring_strength=0.05,
                damping=0.09
            )

            # 添加图例
            legend_html = """
            <div style="position:absolute; top:10px; left:10px; background:white; padding:10px; border: 1px solid black; z-index: 1000;">
                <b>Legend</b><br>
                <span style="color:#3498db;">&#9679;</span> Character<br>
                <span style="color:#2ecc71;">&#9679;</span> Event<br>
                <span style="color:#e67e22;">&#9679;</span> Prop<br>
                <span style="color:#e74c3c;">&#9679;</span> Chapter<br>
                <span style="color:#e74c33;">&#9679;</span> Skill<br>
                <span style="color:#9b59b6;">&#9679;</span> Foreshadowing<br>
            </div>
            """

            net.html = net.html.replace('</body>', legend_html + '</body>')

            # 确定保存路径
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            save_path = os.path.join(os.path.dirname(file_path), f'{base_name}.html')
            net.save_graph(save_path)
            
            # 打开生成的HTML文件
            webbrowser.open('file://' + os.path.realpath(save_path))
            
            return f"Graph visualization created and saved as {save_path}"
        
        except Exception as e:
            print(f"Error: {e}")
            return "Error occurred during graph creation."

    # 读取不同类型的文件
    if file_path.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    elif file_path.endswith('.json'):
        with open(file_path, 'r', encoding='utf-8') as file:
            json_content = json.load(file)
            content = json.dumps(json_content, ensure_ascii=False, indent=4)
    elif file_path.endswith('.pdf'):
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            content = ""
            for page in reader.pages:
                content += page.extract_text()
    elif file_path.endswith('.docx'):
        content = docx2txt.process(file_path)
    elif file_path.endswith('.xlsx') or file_path.endswith('.xls'):
        content = create_graph_from_excel(file_path)
    else:
        content = "Unsupported file format"

    Outputs[0]['Context'] = content
    return Outputs