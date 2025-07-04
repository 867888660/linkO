import os
import json
import logging
from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    concatenate_videoclips,
    vfx,
    CompositeAudioClip
)

# Define the number of outputs and inputs
OutPutNum = 2
InPutNum = 7

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': None,
            'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': None,
           'Id': f'Input{i + 1}', 'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]

FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个视频音频合并处理组件，用于将外部音频文件与视频文件进行合并，支持音频循环播放、音量调节、插入时间控制等功能。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n使用 MoviePy 库加载视频和音频文件，对音频进行音量调节和时间裁剪处理，根据需要循环音频以匹配视频时长，将处理后的音频与视频原有音轨进行混合，最终输出合并后的视频文件。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: Video_Path\\n    type: file\\n    required: true\\n    description: 输入视频文件的路径\\n  - name: Mp3_Path\\n    type: file\\n    required: true\\n    description: 要合并的音频文件路径\\n  - name: SaveName\\n    type: string\\n    required: true\\n    description: 输出视频文件的名称\\n  - name: Is_Loop\\n    type: boolean\\n    required: true\\n    description: 是否循环播放音频以匹配视频时长\\n  - name: Mp3_Volumn\\n    type: string\\n    required: true\\n    description: 音频音量大小（浮点数字符串）\\n  - name: StartTime\\n    type: string\\n    required: true\\n    description: 音频开始插入的时间点（HH:MM:SS格式）\\n  - name: SavePath\\n    type: file\\n    required: true\\n    description: 输出文件保存目录路径\\noutputs:\\n  - name: Result\\n    type: string\\n    description: 处理结果状态信息\\n  - name: File_Path\\n    type: string\\n    description: 合并后视频文件的完整路径\\n```\\n\\n运行逻辑\\n- 获取并验证输入的视频文件路径和音频文件路径是否存在\\n- 解析音量参数为浮点数，如果解析失败则使用默认值0.3\\n- 解析开始时间字符串为秒数，格式必须为HH:MM:SS\\n- 使用MoviePy加载视频文件和音频文件\\n- 对音频应用音量调节效果\\n- 计算从开始时间到视频结束需要的音频时长\\n- 根据Is_Loop参数决定是否循环音频以匹配所需时长\\n- 如果循环，对音频应用淡入淡出效果以平滑过渡\\n- 如果不循环，裁剪音频到所需时长\\n- 设置音频的开始时间点\\n- 将处理后的音频与视频原有音轨进行混合\\n- 构建输出文件路径，如果未指定保存路径则使用默认临时目录\\n- 使用libx264视频编码器和aac音频编码器保存合并后的视频\\n- 清理资源并返回处理结果和输出文件路径'
NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Assign properties to Inputs and Outputs
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'Video_Path'
Inputs[1]['Kind'] = 'String_FilePath'
Inputs[1]['name'] = 'Mp3_Path'
Inputs[2]['Kind'] = 'String'
Inputs[2]['name'] = 'SaveName'
Inputs[3]['Kind'] = 'Boolean'
Inputs[3]['name'] = 'Is_Loop'
Inputs[4]['Kind'] = 'String'
Inputs[4]['name'] = 'Mp3_Volumn'
Inputs[5]['Kind'] = 'String'
Inputs[5]['name'] = 'StartTime'
Inputs[6]['Kind'] = 'String_FilePath'
Inputs[6]['name'] = 'SavePath'
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'
Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'File_Path'

def get_actual_path(path):
    """Convert @TempFiles path to actual path"""
    if '@TempFiles' in path:
        current_dir = os.path.abspath(os.path.dirname(__file__))
        parent_dir = os.path.dirname(current_dir)
        parent_temp_path = os.path.join(parent_dir, 'TempFiles')
        
        if os.path.exists(parent_temp_path):
            return path.replace('@TempFiles', parent_temp_path)
        else:
            raise Exception("'TempFiles' directory not found in the parent directory.")
    return path

def parse_timecode(time_str):
    """Parse time in 'HH:MM:SS' format into seconds."""
    try:
        parts = time_str.strip().split(':')
        if len(parts) != 3:
            raise ValueError
        hours, minutes, seconds = parts
        total_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        return total_seconds
    except ValueError:
        raise ValueError(f"Invalid time format: {time_str}, expected 'HH:MM:SS'")

def run_node(node):
    try:
        # Get and process paths
        Base_Path = get_actual_path(node['Inputs'][0]['Context'])
        Mp3_Path = get_actual_path(node['Inputs'][1]['Context'])
        SaveName = node['Inputs'][2]['Context']
        Is_Loop = node['Inputs'][3]['Boolean']
        Mp3_Volumn = node['Inputs'][4]['Context']
        StartTime_str = node['Inputs'][5]['Context']
        SavePath = node['Inputs'][6]['Context']

        # Ensure SaveName has proper extension
        if not SaveName.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            SaveName += '.mp4'

        # Validate and set default values
        if not os.path.exists(Base_Path):
            raise FileNotFoundError(f"Video file not found: {Base_Path}")
        if not os.path.exists(Mp3_Path):
            raise FileNotFoundError(f"Audio file not found: {Mp3_Path}")

        # Handle volume
        try:
            volume = float(Mp3_Volumn)
        except (ValueError, TypeError):
            volume = 0.3  # default volume

        # Handle start time
        try:
            start_time = parse_timecode(StartTime_str)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid 'StartTime': {e}")

        # Load the video
        video = VideoFileClip(Base_Path)

        # Load the audio
        audio = AudioFileClip(Mp3_Path)

        # Apply volume
        audio = audio.volumex(volume)

        # Calculate the duration for looping or trimming the audio
        duration_needed = video.duration - start_time
        if duration_needed <= 0:
            raise ValueError("Start time is greater than or equal to video duration.")

        if Is_Loop:
            # Loop the audio to cover the total duration needed
            audio = audio.fx(vfx.loop, duration=duration_needed)

            # Apply fade-in and fade-out to the looped audio
            fade_duration = min(1.0, duration_needed / 2.0)  # Max fade duration is 1 second or half of the clip
            audio = audio.audio_fadein(fade_duration).audio_fadeout(fade_duration)
        else:
            # Ensure the audio does not go beyond the video's remaining duration
            audio = audio.subclip(0, min(audio.duration, duration_needed))

        # Adjust start time by setting start
        audio = audio.set_start(start_time)

        # Combine with existing video audio if present
        if video.audio:
            final_audio = CompositeAudioClip([video.audio, audio])
        else:
            final_audio = audio

        # Set the audio of the video
        video = video.set_audio(final_audio)

        # Prepare the output path
        if SavePath:
            # Use specified save path
            output_dir = get_actual_path(SavePath)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            output_path = os.path.join(output_dir, SaveName)
            output_relative_path = output_path
        else:
            # Use default @TempFiles path
            output_dir = '@TempFiles'
            output_dir_actual = get_actual_path(output_dir)
            if not os.path.exists(output_dir_actual):
                os.makedirs(output_dir_actual)
            output_path = os.path.join(output_dir_actual, SaveName)
            output_relative_path = output_path.replace(output_dir_actual, output_dir)

        # Save the result
        video.write_videofile(output_path, codec="libx264", audio_codec="aac")

        # Clean up
        video.close()
        audio.close()

        # Set outputs
        node['Outputs'][0]['Context'] = 'Success'
        node['Outputs'][1]['Context'] = output_relative_path
    except Exception as e:
        node['Outputs'][0]['Context'] = f'Error: {str(e)}'
        node['Outputs'][1]['Context'] = ''
        logging.error("Error in run_node: %s", str(e))
    
    return node['Outputs']
