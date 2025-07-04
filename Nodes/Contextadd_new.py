import json
import re
import http.client
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
#**Define the number of outputs and inputs

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':'answer'} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum)]
#**Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'LLm'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]


#**Assign properties to Inputs

for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
#**Assign properties to Inputs

#**Function definition
def run_node(node):
    Outputs.clear()
    for i in range(len(node['Outputs'])):
        Outputs.append(node['Outputs'][i])
    
    # Process Outputs[0] as before
    for i in range(len(node['Outputs'])):
        Outputs[i]['Context'] = node['ExprotPrompt']
        print(Outputs[i]['Context'])
        last_please_index = Outputs[i]['Context'].rfind('Please')

        if last_please_index != -1:
            previous_newline_index = Outputs[i]['Context'][:last_please_index].rfind('\n')
            if previous_newline_index != -1:
                Outputs[i]['Context'] = Outputs[i]['Context'][:previous_newline_index]
            else:
                Outputs[i]['Context'] = Outputs[i]['Context'][:last_please_index]

    #Outputs[0]['Context'] = re.sub(r'\n', '', Outputs[0]['Context']).strip()

    # Process Outputs[1-n] with new logic
    for i in range(0, len(node['Outputs'])):
        description = Outputs[i]['Description']
        match = re.search(r'<@find:"(.*?)">', description)
        print('测试',description,match,'\n',Outputs[i]['Context'])
        if match != None:
            context_to_find = match.group(1)
            lines = node['ExprotPrompt'].split('\n')
            for line in lines:
                if line.startswith(context_to_find):
                    # Get the context after the search term
                    context_part = line[len(context_to_find):].strip()
                    # Remove the <@find:"..."> pattern and combine with remaining description
                    remaining_description = re.sub(r'<@find:".*?">', '', description).strip()
                    Outputs[i]['Context'] = context_part + remaining_description
                    break
            else:
                Outputs[i]['Context'] = ''  # Default to empty if not found
        else:
            print('没有',Outputs[i]['Context'],'阿松大;',description)
            Outputs[i]['Context'] = Outputs[i]['Context']+description



    return Outputs