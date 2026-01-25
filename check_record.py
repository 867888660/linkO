import json

with open(r'c:\polymarket\linkO\History\PolyMarket_Evaluate\20260115_014726_b149da.json', encoding='utf-8') as f:
    data = json.load(f)

print('=== 所有节点输出状态 ===')
for node in data.get('nodes', []):
    nid = node.get('id', '')
    outputs = node.get('data', {}).get('output', [])
    has_output = False
    for out in outputs:
        ctx = out.get('Context', '')
        if ctx:
            has_output = True
            break
    status = '✅ 有输出' if has_output else '❌ 无输出'
    print(f'{status} | {nid}')

print('\n\n=== DataBase_Array 节点详情（起始节点）===')
for node in data.get('nodes', []):
    if 'DataBase_Array' in node.get('id', ''):
        print(f'\n[{node.get("id")}]')
        inputs = node.get('data', {}).get('input', [])
        print('Inputs:')
        for inp in inputs:
            name = inp.get('name', '')
            ctx = inp.get('Context', '')
            print(f'  {name}: {ctx}')
        outputs = node.get('data', {}).get('output', [])
        print(f'Outputs count: {len(outputs)}')
