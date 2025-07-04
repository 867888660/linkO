import json
import logging
import os
import re

# === 参数区 ===
OutPutNum = 1
InPutNum = 4  # ssid, password, server_url, control_code

Outputs = [
    {'Num': None, 'Kind': 'String', 'Boolean': False, 'Id': 'Output1', 'Context': None, 'name': 'Result', 'Link': 0, 'Description': 'ESP32反馈'}
]
Inputs = [
    {'Num': None, 'Kind': 'String', 'Id': 'Input1', 'Context': None, 'Isnecessary': True, 'name': 'WiFi_SSID', 'Link': 0, 'IsLabel': True},
    {'Num': None, 'Kind': 'String', 'Id': 'Input2', 'Context': None, 'Isnecessary': True, 'name': 'WiFi_Password', 'Link': 0, 'IsLabel': True},
    {'Num': None, 'Kind': 'String', 'Id': 'Input3', 'Context': None, 'Isnecessary': True, 'name': 'Server_URL', 'Link': 0, 'IsLabel': True},
    {'Num': None, 'Kind': 'String', 'Id': 'Input4', 'Context': None, 'Isnecessary': False, 'name': 'Control_Code', 'Link': 0, 'IsLabel': False}
]
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个ESP32嵌入式开发节点，用于生成ESP32微控制器的WiFi连接和HTTP通信代码模板。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n接收WiFi连接参数和服务器地址，自动生成包含WiFi连接、HTTP客户端通信功能的完整ESP32 Arduino代码，支持从指定服务器获取控制指令并通过串口输出。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: WiFi_SSID\\n    type: string\\n    required: true\\n    description: WiFi网络名称\\n  - name: WiFi_Password\\n    type: string\\n    required: true\\n    description: WiFi网络密码\\n  - name: Server_URL\\n    type: string\\n    required: true\\n    description: 服务器地址，用于获取控制指令\\n  - name: Control_Code\\n    type: string\\n    required: false\\n    description: 可选的控制代码或指令类型\\noutputs:\\n  - name: Result\\n    type: string\\n    description: 生成的ESP32代码和调试信息\\n```\\n\\n运行逻辑\\n- 从输入参数中获取WiFi SSID、密码、服务器URL和可选的控制代码\\n- 验证必要参数是否完整，缺少时返回错误信息\\n- 收集调试信息，记录所有输入参数\\n- 生成ESP32 Arduino代码模板，包含WiFi连接和HTTP客户端功能\\n- 代码包含setup函数用于初始化WiFi连接，loop函数用于定期从服务器获取指令\\n- 将生成的代码与调试信息合并后输出到Result字段'

def run_node(node):
    ssid = node['Inputs'][0]['Context']
    password = node['Inputs'][1]['Context']
    server_url = node['Inputs'][2]['Context']
    control_code = node['Inputs'][3]['Context'] if len(node['Inputs']) > 3 else ''
    debug_msgs = []
    if not ssid or not password or not server_url:
        Outputs[0]['Context'] = '缺少必要参数（WiFi名称、密码或服务器地址）'
        return Outputs
    debug_msgs.append(f"WiFi名称: {ssid}")
    debug_msgs.append(f"WiFi密码: {password}")
    debug_msgs.append(f"服务器地址: {server_url}")
    if control_code:
        debug_msgs.append(f"控制代码: {control_code}")
    # 生成ESP32代码片段
    code = f'''
#include <WiFi.h>
#include <HTTPClient.h>

const char* ssid = "{ssid}";
const char* password = "{password}";

String getControlCommand() {{
  HTTPClient http;
  http.begin("{server_url}");
  int httpCode = http.GET();
  if (httpCode == 200) {{
    String payload = http.getString();
    http.end();
    return payload;
  }} else {{
    http.end();
    return "";
  }}
}}

void setup() {{
  Serial.begin(115200);
  Serial.println("ESP32 Ready");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {{
    delay(500);
    Serial.println("连接中...");
  }}
  Serial.println("连接成功！");
}}

void loop() {{
  String command = getControlCommand();
  if (command.length() > 0) {{
    Serial.print("Command: ");
    Serial.println(command);
    Serial.println();
    delay(200);
  }}
  delay(3000);
}}
'''
    Outputs[0]['Context'] = code + '\n\n调试信息:\n' + '\n'.join(debug_msgs)
    return Outputs
