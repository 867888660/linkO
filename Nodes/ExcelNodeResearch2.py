import pandas as pd
from tabulate import tabulate

# Define the number of outputs and inputs
OutPutNum = 3
InPutNum = 2

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Input{i + 1}', 'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction ='这是用来查找模糊查询多个文件中的节点和边的节点。\n\n输入：Excel 文件路径，节点名称。\n\n输出：节点信息，边信息，相连的节点信息。'
NodeKind = 'Normal'
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'Excel_FilePath'
Inputs[1]['name'] = 'Node_Name'
Inputs[1]['Kind'] = 'String'
Outputs[0]['name'] = 'Node_Info'
Outputs[1]['name'] = 'Edge_Info'
Outputs[2]['name'] = 'Adjacent_Node_Info'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Function to get adjacent edges and nodes
def get_adjacent_edges_and_nodes(node_name, edges_dfs, nodes_dfs):
    adjacent_edges = pd.DataFrame()
    adjacent_nodes = pd.DataFrame()

    for edges_df in edges_dfs:
        if 'sourceId' in edges_df.columns and 'targetId' in edges_df.columns:
            adj_edges = edges_df[(edges_df['sourceName'].str.contains(node_name, na=False)) | (edges_df['targetName'].str.contains(node_name, na=False))]
            adjacent_edges = pd.concat([adjacent_edges, adj_edges])

            adj_node_names = set(adj_edges['sourceId'].tolist() + adj_edges['targetId'].tolist())

            for nodes_df in nodes_dfs:
                if 'name' in nodes_df.columns:
                    adj_nodes = nodes_df[nodes_df['name'].isin(adj_node_names)]
                    adjacent_nodes = pd.concat([adjacent_nodes, adj_nodes])

    return adjacent_edges.drop_duplicates(), adjacent_nodes.drop_duplicates()

# Function definition
def run_node(node):
    file_path = node['Inputs'][0]['Context']
    node_names = node['Inputs'][1]['Context'].split('#^#')

    print("Reading file:", file_path)
    xls = pd.ExcelFile(file_path)
    
    # 区分节点和边的 sheet
    nodes_dfs = []
    edges_dfs = []
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        if 'Edge' in sheet_name:
            edges_dfs.append(df)
        else:
            nodes_dfs.append(df)
    print("Loaded sheets. Node sheets:", len(nodes_dfs), "Edge sheets:", len(edges_dfs))
    
    # 创建最终的输出字符串
    final_output_event = []
    final_output_edges = []
    final_output_nodes = []

    for node_name in node_names:
        # 找到包含节点的 sheet
        found_node_df = pd.DataFrame()
        for nodes_df in nodes_dfs:
            if 'name' in nodes_df.columns:
                found_node_df = pd.concat([found_node_df, nodes_df[nodes_df['name'].str.contains(node_name, na=False)]])

        if not found_node_df.empty:
            # 将匹配的节点行放入 final_output_event
            output_event = tabulate(found_node_df, headers='keys', tablefmt='pipe', showindex=False)
            final_output_event.append(output_event)

            all_adj_edges = pd.DataFrame()
            all_adj_nodes = pd.DataFrame()

            print(f"Processing node_name: {node_name}")
            adj_edges_df, adj_nodes_df = get_adjacent_edges_and_nodes(node_name, edges_dfs, nodes_dfs)
            all_adj_edges = pd.concat([all_adj_edges, adj_edges_df])
            all_adj_nodes = pd.concat([all_adj_nodes, adj_nodes_df])

            # 将相关的边信息放入 final_output_edges
            output_edges = tabulate(all_adj_edges.drop_duplicates(), headers='keys', tablefmt='pipe', showindex=False) if not all_adj_edges.empty else "No data"
            final_output_edges.append(output_edges)

            # 将相连的节点信息放入 final_output_nodes
            output_nodes = tabulate(all_adj_nodes.drop_duplicates(), headers='keys', tablefmt='pipe', showindex=False) if not all_adj_nodes.empty else "No data"
            final_output_nodes.append(output_nodes)

    # 将结果用“#^#\n”连接并放入 Outputs
    Outputs[0]['Context'] = '#^#\n'.join(final_output_event)
    Outputs[1]['Context'] = '#^#\n'.join(final_output_edges)
    Outputs[2]['Context'] = '#^#\n'.join(final_output_nodes)

    print("Finished processing and returning Array.")
    
    return Outputs
