import requests
import os

# **Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 9

# **Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能：这是一个Azure文本转语音(TTS)转换节点，用于将文本内容转换为语音文件并保存到指定路径。\\n\\n代码功能摘要：通过Azure语音服务API，使用SSML格式构建请求体，支持自定义语音角色、情感和语速参数，将文本转换为MP3音频文件，同时保存音频描述文件。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: Authorization\\n    type: string\\n    required: true\\n    description: Azure语音服务认证密钥\\n  - name: Prompt\\n    type: string\\n    required: true\\n    description: 需要转换为语音的文本内容\\n  - name: Voice\\n    type: string\\n    required: true\\n    description: 语音角色名称\\n  - name: Url\\n    type: string\\n    required: true\\n    description: Azure语音服务API地址\\n  - name: save_path\\n    type: file\\n    required: true\\n    description: 音频文件保存路径\\n  - name: audio_name\\n    type: string\\n    required: true\\n    description: 音频文件名称（不含扩展名）\\n  - name: audio_descript\\n    type: string\\n    required: true\\n    description: 音频描述内容\\n  - name: Emotion\\n    type: string\\n    required: false\\n    description: 语音情感风格（可选）\\n  - name: Speed\\n    type: string\\n    required: false\\n    description: 语音速度（可选，默认1.0）\\n    default: \\\"1.0\\\"\\noutputs:\\n  - name: result\\n    type: string\\n    description: 转换结果，成功返回Success，失败返回错误信息\\n```\\n\\n运行逻辑：\\n- 获取所有输入参数，包括认证密钥、文本内容、语音角色等\\n- 对URL进行格式化处理，确保以/cognitiveservices/v1结尾\\n- 清理和处理语音角色、情感和速度参数\\n- 根据是否有情感参数构建不同的语音标签\\n- 使用SSML格式构建请求体，包含voice标签和prosody标签控制语速\\n- 设置HTTP请求头，包含认证密钥和输出格式\\n- 发送POST请求到Azure语音服务API\\n- 检查响应状态码，如果成功（200）则继续处理\\n- 确保保存目录存在，不存在则创建\\n- 将响应的音频内容保存为MP3文件\\n- 创建同名的txt文件保存音频描述信息\\n- 返回处理结果，成功返回Success，失败返回具体错误信息\\n- 整个过程包含完整的异常处理和调试日志输出'

# **Assign properties to Inputs
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
Inputs[0]['name'] = 'Authorization'
Inputs[1]['name'] = 'Prompt'
Inputs[2]['name'] = 'Voice'
Inputs[3]['name'] = 'Url'
Inputs[4]['name'] = 'save_path'
Inputs[4]['Kind'] = 'String_FilePath'
Inputs[5]['name'] = 'audio_name'
Inputs[6]['name'] = 'audio_descript'
Inputs[7]['Kind'] = 'String'
Inputs[7]['name'] = 'Emotion'
Inputs[7]['Isnecessary'] = False
Inputs[8]['name'] = 'Speed'
Inputs[8]['Kind'] = 'String'
Inputs[8]['Isnecessary'] = False
Outputs[0]['name'] = 'result'

# **Function definition
def run_node(node):
    Authorization = node['Inputs'][0]['Context']
    Prompt = node['Inputs'][1]['Context']
    Voice = node['Inputs'][2]['Context']
    Url = node['Inputs'][3]['Context']
    save_path = node['Inputs'][4]['Context']
    audio_name = node['Inputs'][5]['Context']
    audio_descript = node['Inputs'][6]['Context']
    Emotion = node['Inputs'][7]['Context']
    Speed = node['Inputs'][8]['Context']

    def generate_audio(prompt, url, voice, save_path, audio_name, audio_descript, emotion, speed):
        # Clean up URL and ensure it ends with the correct path
        url = url.strip()
        if not url.endswith('/cognitiveservices/v1'):
            url = url.rstrip('/') + '/cognitiveservices/v1'

        # Clean up voice input
        voice = voice.strip()

        # Clean up emotion input
        if emotion:
            emotion = emotion.strip()

        # Clean up speed input
        if speed and speed != 'None':
            speed = speed.strip()
        else:
            speed = '1.0'  # Default speed is normal (100%)

        print(f"Processed URL: {url}")
        print(f"Processed voice: {voice}")
        print(f"Processed speed: {speed}")

        # Build the voice tag with optional style attribute
        if emotion and emotion != 'None':
            voice_tag = f"<voice name='{voice}' style='{emotion}'>"
        else:
            voice_tag = f"<voice name='{voice}'>"

        # SSML formatted request body with prosody tag for controlling speech speed
        data = f"""
<speak version='1.0' xml:lang='en-US'>
    {voice_tag}
        <prosody rate='{speed}'>
            {prompt}
        </prosody>
    </voice>
</speak>
"""

        headers = {
            'Ocp-Apim-Subscription-Key': Authorization,
            'Content-Type': 'application/ssml+xml',
            'X-Microsoft-OutputFormat': 'audio-16khz-128kbitrate-mono-mp3', 
        }

        # 输出请求数据用于调试
        print(f'Request data: {data}')

        try:
            # 发送 POST 请求到 Azure Speech Services
            response = requests.post(url, headers=headers, data=data)
            print(f'Response status code: {response.status_code}')

            # 检查请求是否成功
            if response.status_code == 200:
                audio_content = response.content

                # 确保保存路径存在
                if not os.path.exists(save_path):
                    os.makedirs(save_path)

                # 保存音频文件
                audio_filename = os.path.join(save_path, f"{audio_name}.mp3")
                with open(audio_filename, 'wb') as f:
                    f.write(audio_content)
                print(f'Audio saved as: {audio_filename}')

                # 保存音频描述
                description_filename = os.path.join(save_path, f"{audio_name}.txt")
                try:
                    with open(description_filename, 'w', encoding='utf-8') as desc_file:
                        desc_file.write(audio_descript)
                    print(f'Description saved as: {description_filename}')
                except Exception as e:
                    print(f'Failed to write description file: {e}')
                    return "Description writing failed"

                return "Success"
            else:
                print(f'Failed request, status code: {response.status_code}, response: {response.text}')
                return f"Failed with status code {response.status_code}"

        except requests.exceptions.RequestException as e:
            print(f'Request error: {e}')
            return f'Request error: {e}'

    # **Main workflow execution
    result = generate_audio(Prompt, Url, Voice, save_path, audio_name, audio_descript, Emotion, Speed)

    # **Return result
    Outputs[0]['Context'] = result
    return Outputs
# **Function definition

