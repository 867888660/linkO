import json
import requests
from docarray import Document, DocumentArray
from markdownify import markdownify as md

# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 1
# Define the number of outputs and inputs

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Input{i + 1}', 'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
# Initialize Outputs and Inputs arrays and assign names directly

NodeKind = 'Normal'
InputIsAdd = True
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
    
    doc = Document(text=html_content)
    doc.convert_text_to_markdown()
    markdown_content = doc.text
    return markdown_content

# Function definition
def run_node(node):
    url = node['Inputs'][0]['Context']
    markdown_content = fetch_webpage_as_markdown(url)
    Outputs[0]['Context'] = markdown_content
    return Outputs
# Function definition
