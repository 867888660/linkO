import requests
import os
import logging
from gradio_client import Client
import shutil

# **Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 8
# **Define the number of outputs and inputs

# **Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能：这是一个AI语音生成组件，通过调用Gradio API将文本转换为语音，支持参考音频的声音特征克隆功能。\\n\\n代码功能摘要：该组件通过Gradio客户端连接到TTS（文本转语音）API，使用参考音频文件和对应文本来克隆声音特征，将目标文本转换为具有相同声音特色的语音文件，并保存到指定位置。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: remove_silence\\n    type: boolean\\n    required: true\\n    description: 是否移除生成音频中的静音部分\\n    default: false\\n  - name: api_url\\n    type: string\\n    required: true\\n    description: 语音生成API的URL地址\\n  - name: ref_audio_filepath\\n    type: file\\n    required: true\\n    description: 参考音频文件路径，用于声音克隆\\n  - name: ref_audio_txt\\n    type: string\\n    required: true\\n    description: 参考音频对应的文本内容\\n  - name: save_path\\n    type: file\\n    required: true\\n    description: 生成音频文件的保存目录路径\\n  - name: gen_name\\n    type: string\\n    required: true\\n    description: 生成音频文件的名称（不含扩展名）\\n  - name: gen_text_input\\n    type: string\\n    required: true\\n    description: 需要转换成语音的目标文本内容\\n  - name: Speed\\n    type: string\\n    required: true\\n    description: 语音生成的速度参数，范围0.1-2.0\\n    default: \\\"0.3\\\"\\noutputs:\\n  - name: result\\n    type: string\\n    description: 音频生成结果消息，包含成功状态和保存路径信息\\n```\\n\\n运行逻辑：\\n- 获取并验证所有输入参数，特别是速度参数的类型转换和范围限制（0.1-2.0）\\n- 确保音频保存目录存在，如不存在则自动创建\\n- 使用提供的API URL创建Gradio客户端连接\\n- 调用TTS API的/basic_tts接口，传入参考音频文件、参考文本、目标文本、静音移除选项、交叉淡化时长和语速参数\\n- 检查API返回结果是否为空，如为空则抛出异常\\n- 验证生成的音频文件是否实际存在于返回的路径中\\n- 将生成的音频文件复制到用户指定的保存路径，并重命名为指定的文件名（.wav格式）\\n- 构造成功消息并设置到输出结果中\\n- 如果过程中发生任何异常，捕获错误并将错误信息作为结果输出，同时记录到日志中'

# **Assign properties to Inputs
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
    
Inputs[0]['name'] = 'remove_silence'
Inputs[0]['Boolean'] = False
Inputs[0]['Kind'] = 'Boolean'
Inputs[1]['name'] = 'api_url'
Inputs[2]['name'] = 'ref_audio_filepath'
Inputs[2]['Kind'] = 'String_FilePath'
Inputs[3]['name'] = 'ref_audio_txt'
Inputs[3]['Kind'] = 'String'
Inputs[4]['name'] = 'save_path'
Inputs[4]['Kind'] = 'String_FilePath'
Inputs[5]['name'] = 'gen_name'
Inputs[6]['name'] = 'gen_text_input'
Inputs[6]['Kind'] = 'String'
Inputs[7]['name'] = 'Speed'
Inputs[7]['Kind'] = 'String'
Outputs[0]['name'] = 'result'


def run_node(node):
    try:
        from gradio_client import Client, handle_file  # 添加 handle_file 导入
        
        # 获取输入参数
        remove_silence = node['Inputs'][0]['Boolean']
        api_url = node['Inputs'][1]['Context']
        ref_audio_filepath = node['Inputs'][2]['Context']
        ref_audio_txt = node['Inputs'][3]['Context']
        save_path = node['Inputs'][4]['Context']
        gen_name = node['Inputs'][5]['Context']
        gen_text_input = node['Inputs'][6]['Context']
        speed = float(node['Inputs'][7]['Context']) if node['Inputs'][7]['Context'] else 1.0
        # 速度参数处理
        try:
            speed_input = node['Inputs'][7]['Context']
            speed = float(speed_input) if speed_input and speed_input.strip() else 0.3
            # 确保速度在合理范围内
            speed = max(0.1, min(speed, 2.0))  # 假设速度范围是 0.1-2.0
        except (ValueError, TypeError):
            speed = 0.5  # 如果转换失败，使用默认值
        # 确保保存目录存在
        os.makedirs(save_path, exist_ok=True)

        # 创建Gradio客户端
        client = Client(api_url)

        # 调用TTS API
        result = client.predict(
            ref_audio_input=handle_file(ref_audio_filepath),  # 使用 handle_file
            ref_text_input=ref_audio_txt.strip(),
            gen_text_input=gen_text_input,
            remove_silence=remove_silence,
            cross_fade_duration_slider=0.15,  # 添加缺失的参数
            speed_slider=speed,
            api_name="/basic_tts"
        )

        # 检查返回结果
        if not result or len(result) == 0:
            raise Exception("API返回结果为空")

        # 获取生成的音频文件路径
        output_filepath = result[0]
        
        # 检查生成的文件是否存在
        if not os.path.exists(output_filepath):
            raise Exception(f"生成的音频文件不存在: {output_filepath}")

        # 将生成的音频文件复制到指定位置
        final_save_path = os.path.join(save_path, f"{gen_name}.wav")
        shutil.copy2(output_filepath, final_save_path)

        # 设置输出结果
        result_message = f"音频生成成功！保存路径：{final_save_path}"
        Outputs[0]['Context'] = result_message

    except Exception as e:
        error_message = f"音频生成失败：{str(e)}"
        logging.error(error_message)
        Outputs[0]['Context'] = error_message

    return Outputs
