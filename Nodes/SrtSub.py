import json
import chardet

OutPutNum = 1
InPutNum = 2
# Define the number of outputs and inputs

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Input{i + 1}', 'Isnecessary': True if i == 0 else False, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
# Initialize Outputs and Inputs arrays and assign names directly

FunctionIntroduction='输入srt，和中止的时间轨道，输出剪辑后的srt'
NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

Inputs[0]['name'] = 'InputSrt'
Inputs[0]['Kind'] = 'String'
Inputs[1]['name'] = 'Time'
Inputs[1]['Kind'] = 'String'
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'OutputSrt'

# Function definition
# ... existing code ...

def parse_time(time_str):
    """Extract timestamp from various formats"""
    import re
    # Match pattern like "00:00:03,490" from different formats
    time_pattern = r'(\d{2}:\d{2}:\d{2},\d{3})'
    match = re.search(time_pattern, time_str)
    if match:
        return match.group(1)
    return None

def parse_srt(srt_content):
    """Parse SRT content into structured format"""
    blocks = []
    current_block = {}
    lines = srt_content.strip().split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            if current_block:
                blocks.append(current_block)
                current_block = {}
            i += 1
            continue
        
        # Try to parse as index (number)
        if line.isdigit():
            if current_block:
                blocks.append(current_block)
            current_block = {'index': line}
            i += 1
            continue
        
        # Try to parse as timestamp
        if '-->' in line or '==>' in line:
            current_block['time'] = line
            i += 1
            continue
            
        # Must be content
        if 'content' in current_block:
            current_block['content'] += '\n' + line
        else:
            current_block['content'] = line
        i += 1
    
    # Don't forget the last block
    if current_block:
        blocks.append(current_block)
    
    return blocks

def parse_time(time_str):
    """Extract timestamp from various formats"""
    import re
    
    # Handle nan case
    if not isinstance(time_str, str) or time_str.lower() == 'nan':
        return None
        
    # Match pattern like "00:00:03,490" from different formats
    time_pattern = r'(\d{2}:\d{2}:\d{2}[,\.]\d{3})'
    match = re.search(time_pattern, time_str)
    if match:
        return match.group(1).replace('.', ',')  # Normalize to use comma
    return None

def run_node(node):
    srt_content = node['Inputs'][0]['Context']
    cut_time = node['Inputs'][1]['Context']
    
    # Handle empty or nan cut_time - return original content
    if not cut_time or str(cut_time).lower() == 'nan':
        Outputs[0]['Context'] = srt_content
        return Outputs
    
    # Clean input strings
    srt_content = str(srt_content).strip()
    cut_time = str(cut_time).strip()
    
    try:
        # Parse the cut time
        cut_timestamp = parse_time(cut_time)
        if not cut_timestamp:
            # If can't parse cut time, return original content
            Outputs[0]['Context'] = srt_content
            return Outputs
        
        # Rest of the code remains the same...
        srt_blocks = parse_srt(srt_content)
        result_blocks = []
        
        for block in srt_blocks:
            if 'time' not in block or 'content' not in block:
                continue
                
            time_line = block['time']
            times = time_line.replace('==>', '-->').split('-->')
            start_time = parse_time(times[0])
            
            if not start_time or start_time >= cut_timestamp:
                result_blocks.append(block)
        
        # Format output
        output_srt = ''
        for block in result_blocks:
            output_srt += f"{block['time']}\n{block['content']}\n\n"
        
        Outputs[0]['Context'] = output_srt.strip()
        
    except Exception as e:
        # If any error occurs, return original content
        print(f"Error processing SRT: {str(e)}")
        Outputs[0]['Context'] = srt_content
        
    return Outputs
