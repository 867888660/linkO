import pandas as pd
from tabulate import tabulate

# Define the number of outputs and inputs
OutPutNum = 3
InPutNum = 2
# Define the number of outputs and inputs

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Input{i + 1}', 'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
# Initialize Outputs and Inputs arrays and assign names directly

NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'Excel_FilePath'
Inputs[1]['name'] = 'Event_Id'
Inputs[1]['Kind'] = 'String'
Outputs[0]['name'] = 'Event_Info'
Outputs[1]['name'] = 'Edge_Info'
Outputs[2]['name'] = 'Adjacent_Node_Info'
FunctionIntroduction ='这是用来查找事件的节点。\n\n输入：Excel 文件路径，事件 ID。\n\n输出：事件信息，边信息，相连的节点信息。'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Function to get adjacent edges and nodes
def get_adjacent_edges_and_nodes(node_id, edges_dfs, nodes_dfs):
    adjacent_edges = pd.DataFrame()
    adjacent_nodes = pd.DataFrame()

    for edges_df in edges_dfs:
        if 'sourceId' in edges_df.columns and 'targetId' in edges_df.columns:
            adj_edges = edges_df[(edges_df['sourceId'] == node_id) | (edges_df['targetId'] == node_id)]
            adjacent_edges = pd.concat([adjacent_edges, adj_edges])

            adj_node_ids = set(adj_edges['sourceId'].tolist() + adj_edges['targetId'].tolist()) - {node_id}

            for nodes_df in nodes_dfs:
                if 'id' in nodes_df.columns:
                    adj_nodes = nodes_df[nodes_df['id'].isin(adj_node_ids)]
                    adjacent_nodes = pd.concat([adjacent_nodes, adj_nodes])

    return adjacent_edges.drop_duplicates(), adjacent_nodes.drop_duplicates()

# Function definition
def run_node(node):

    file_path = node['Inputs'][0]['Context']
    event_id = node['Inputs'][1]['Context']

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
    
    # 找到 'Event' sheet 中的节点
    event_nodes_df = None
    for sheet_name in xls.sheet_names:
        if 'Event' in sheet_name:
            event_nodes_df = pd.read_excel(xls, sheet_name=sheet_name)
            break

    if event_nodes_df is not None and 'id' in event_nodes_df.columns and 'IsWrite' in event_nodes_df.columns:
        # 将 IsWrite 列转换为字符串类型，然后处理空值和非布尔值
        event_nodes_df['IsWrite'] = event_nodes_df['IsWrite'].astype(str)
        event_nodes_df_filtered = event_nodes_df[event_nodes_df['id']==event_id]
        
        print("Filtered Event nodes DataFrame:", event_nodes_df_filtered)

        # 将 event_nodes_df_filtered 中的 IsWrite 列更新为 'True'
        

        print("Updated 'IsWrite' column to 'True' and saved to file.")
        
        if not event_nodes_df_filtered.empty:
            # 依次处理每个符合条件的事件行
            for idx, row in event_nodes_df_filtered.iterrows():
               
                
                # 将事件行放入 Outputs[0]
                output_event = {
                    'Num': None,
                    'Kind': 'String',
                    'Boolean': False,
                    'Id': 'Output1',
                    'Context': tabulate(pd.DataFrame([row]), headers='keys', tablefmt='pipe', showindex=False),
                    'name': 'WebOutput',
                    'Link': 0,
                    'Description': ''
                }
                
                all_adj_edges = pd.DataFrame()
                all_adj_nodes = pd.DataFrame()

                print(f"Processing node_id: {row['id']}")
                adj_edges_df, adj_nodes_df = get_adjacent_edges_and_nodes(row['id'], edges_dfs, nodes_dfs)
                all_adj_edges = pd.concat([all_adj_edges, adj_edges_df])
                all_adj_nodes = pd.concat([all_adj_nodes, adj_nodes_df])
                for sheet_name in ['Character', 'Prop']:
                    if sheet_name in xls.sheet_names:
                        df = pd.read_excel(xls, sheet_name=sheet_name)
                        matched_rows = df[df['id'].isin(all_adj_nodes['id'])]
                        df.loc[matched_rows.index, 'IsFirstAppeared'] = 'No'
                        with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
                            df.to_excel(writer, sheet_name=sheet_name, index=False)

                # 将相关的边信息放入 Outputs[1]
                output_edges = {
                    'Num': None,
                    'Kind': 'String',
                    'Boolean': False,
                    'Id': 'Output2',
                    'Context': tabulate(all_adj_edges.drop_duplicates(), headers='keys', tablefmt='pipe', showindex=False) if not all_adj_edges.empty else "No data",
                    'name': 'WebOutput',
                    'Link': 0,
                    'Description': ''
                }

                # 将相连的节点信息放入 Outputs[2]
                output_nodes = {
                    'Num': None,
                    'Kind': 'String',
                    'Boolean': False,
                    'Id': 'Output3',
                    'Context': tabulate(all_adj_nodes.drop_duplicates(), headers='keys', tablefmt='pipe', showindex=False) if not all_adj_nodes.empty else "No data",
                    'name': 'WebOutput',
                    'Link': 0,
                    'Description': ''
                }

                # 将 Outputs[0], Outputs[1], Outputs[2] 依次加入 Array
                Outputs[0]['Context'] = output_event['Context']
                Outputs[1]['Context'] = output_edges['Context']
                Outputs[2]['Context'] = output_nodes['Context']

            print("Finished processing and returning Array.")

    return Outputs


