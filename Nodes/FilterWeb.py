import json

# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 1

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': None, 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': None, 'Id': f'Input{i + 1}', 'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]

NodeKind = 'Normal'
InputIsAdd = True
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Assign properties to Inputs and Outputs
for output in Outputs:
    output['Kind'] = 'Context'
    output['name'] = 'WebOutput'

for input in Inputs:
    input['Kind'] = 'Context'
    input['Isnecessary'] = True
    input['name'] = 'WebInput'

# Function definition
def run_node(node):
    Outputs.clear()
    data = node['Inputs'][0]['Context']
    
    # Debugging information
    print("Raw input data:", repr(data))
    print("Input data length:", len(data))

    # Validate and parse JSON input
    try:
        # Strip any extraneous whitespace
        data = data.strip()
        print("Stripped input data:", repr(data))
        print("Stripped input data length:", len(data))
        
        # Ensure the input data is a valid JSON string
        if not (data.startswith('[') or data.startswith('{')):
            raise ValueError("Invalid JSON format: must start with '[' or '{'")
        
        parsed_data = json.loads(data)
        print("Parsed data:", parsed_data)
    except (json.JSONDecodeError, ValueError) as e:
        error_message = f"Invalid JSON input: {str(e)}"
        print(error_message)
        Outputs.append({'Num': None, 'Kind': 'Context', 'Id': 'Output1', 'Context': error_message, 'name': 'WebOutput', 'Link': 0})
        return Outputs
    
    def clean_data(item):
        # Remove unnecessary fields and clean the data
        necessary_fields = ['owner', 'desc', 'src']
        cleaned_item = {key: item.get(key, '') for key in necessary_fields}
        # Clean empty or irrelevant data
        if not cleaned_item['desc']:
            cleaned_item['desc'] = 'No description'
        if not cleaned_item['src']:
            cleaned_item['src'] = 'No image source'
        return cleaned_item

    def extract_to_markdown(data):
        markdown_list = []
        for item in data:
            cleaned_item = clean_data(item)
            owner = cleaned_item['owner'] or 'Unknown'
            desc = cleaned_item['desc']
            img_url = cleaned_item['src']
            markdown_item = f"### {owner}\n\n{desc}\n\n![Image]({img_url})\n"
            markdown_list.append(markdown_item)
        return "\n".join(markdown_list)

    markdown_content = extract_to_markdown(parsed_data)
    
    Outputs.append({'Num': None, 'Kind': 'Context', 'Id': 'Output1', 'Context': markdown_content, 'name': 'WebOutput', 'Link': 0})
    return Outputs