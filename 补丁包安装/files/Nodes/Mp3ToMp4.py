import os
import json
import logging
from moviepy.editor import AudioFileClip, ColorClip
# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 3
# Define the number of outputs and inputs

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None,'Context': None,'Boolean':False,'Kind': None, 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None,'Context': None,'Boolean':False, 'Kind': None, 'Id': f'Input{i + 1}',  'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
# Initialize Outputs and Inputs arrays and assign names directly
FunctionIntroduction='组件功能：\n这是一个将MP3音频文件转换成MP4视频文件的功能组件。该组件将音频文件与一个黑色背景视频结合，生成一个新的MP4视频文件。\n\n输入：\n1. File_Path (String_FilePath类型)：必填，输入MP3音频文件的完整路径\n2. Save_Path (String_FilePath类型)：必填，输出MP4文件的保存目录路径\n3. Save_Name (String类型)：必填，指定保存文件的名称\n\n输出：\n- Result (String类型)：转换操作的结果信息，成功时返回转换完成的文件路径，失败时返回错误信息\n\n大概的运行逻辑：\n1. 首先验证输入条件：\n   - 检查输入的MP3文件是否存在\n   - 验证文件是否为MP3格式\n   - 确保保存路径存在，不存在则创建\n\n2. 处理输出文件名：\n   - 如果提供了保存名称，确保具有.mp4后缀\n   - 如果未提供保存名称，使用原文件名并改为.mp4后缀\n\n3. 转换处理：\n   - 使用AudioFileClip加载MP3音频\n   - 创建一个640x480像素的黑色背景视频片段\n   - 将音频与视频合并\n   - 保存为MP4格式文件\n\n4. 结果处理：\n   - 如果转换成功，输出成功信息和保存路径\n   - 如果转换失败，输出详细的错误信息\n\n整个程序使用try-except结构进行错误处理，确保在转换过程中的任何异常都能被捕获并报告。同时，程序会自动处理文件格式和路径问题，使用户使用更加方便。'
NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Assign properties to Inputs and Outputs
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'File_Path'
Inputs[1]['Kind'] = 'String_FilePath'
Inputs[1]['name'] = 'Save_Path'
Inputs[2]['Kind'] = 'String'
Inputs[2]['name'] = 'Save_Name'
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'
# Assign properties to Inputs and Outputs

# Function definition
def run_node(node):
    filepath = node['Inputs'][0]['Context']
    save_path = node['Inputs'][1]['Context']
    save_name = node['Inputs'][2]['Context']
    try:
        # Check if input file exists
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Input file not found: {filepath}")
            
        # Check if file is mp3
        if not filepath.lower().endswith('.mp3'):
            raise ValueError("Input file must be an MP3 file")
            
        # Create save directory if it doesn't exist
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        
        # Combine save path and name
        if save_name:
            # Ensure save name has .mp4 extension
            if not save_name.lower().endswith('.mp4'):
                save_name = f"{save_name}.mp4"
            full_save_path = os.path.join(save_path, save_name)
        else:
            # Use original filename if no save name provided
            original_name = os.path.basename(filepath)
            save_name = os.path.splitext(original_name)[0] + '.mp4'
            full_save_path = os.path.join(save_path, save_name)
        
        # Load audio file
        audio = AudioFileClip(filepath)
        
        # Create a black video clip with same duration as audio
        video = ColorClip(size=(640, 480), color=(0, 0, 0), duration=audio.duration)
        
        # Combine audio with video
        final_clip = video.set_audio(audio)
        
        # Write the result to the specified save path
        final_clip.write_videofile(full_save_path, fps=24, codec='libx264', audio_codec='aac')
        
        # Clean up
        audio.close()
        final_clip.close()
        
        Outputs[0]['Context'] = f"Successfully converted {filepath} to {full_save_path}"
        
    except Exception as e:
        error_message = f"Error converting MP3 to MP4: {str(e)}"
        logging.error(error_message)
        Outputs[0]['Context'] = error_message
        raise Exception(error_message)
        
    return Outputs