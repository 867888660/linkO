import json
import logging
import os
# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 1
# Define the number of outputs and inputs

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Input{i + 1}', 'Isnecessary': True if i == 0 else False, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
# Initialize Outputs and Inputs arrays and assign names directly

NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]


Inputs[0]['Kind'] = 'String'
Inputs[0]['name'] = 'Input_Id'

Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Output_Id'
FunctionIntroduction='特定节点，用于给id降序。\n\n输入：name_3_1。\n\n输出：name_3_0。'
# Assign properties to Inputs and Outputs


def parse_id(input_id):
    """Parse the input ID into components"""
    try:
        # Split by underscore
        parts = input_id.split('_')
        if len(parts) >= 3:
            base = '_'.join(parts[:-2])  # Everything except last two numbers
            group_num = int(parts[-2])
            seq_num = int(parts[-1])
            return base, group_num, seq_num
    except:
        return None, None, None
    return None, None, None

def run_node(node):
    input_id = node['Inputs'][0]['Context']
    
    # Handle empty or invalid input
    if not input_id or not isinstance(input_id, str):
        Outputs[0]['Context'] = input_id
        return Outputs
    
    try:
        # Parse the input ID
        base, group_num, seq_num = parse_id(input_id)
        
        if base is not None and seq_num > 0:
            # Create new ID with decremented sequence number
            new_id = f"{base}_{group_num}_{seq_num - 1}"
            Outputs[0]['Context'] = new_id
        else:
            # If parsing fails, return original input
            Outputs[0]['Context'] = input_id
            
    except Exception as e:
        logging.error(f"Error processing ID: {str(e)}")
        Outputs[0]['Context'] = input_id
    
    return Outputs
