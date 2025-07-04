import os
import re
from moviepy.editor import AudioFileClip, concatenate_audioclips
from moviepy.audio.AudioClip import AudioArrayClip
import numpy as np

# **Define the number of outputs and inputs**
OutPutNum = 1
InPutNum = 4
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能：这是一个音频合成与字幕生成的处理节点，能够将多个音频文件按顺序合并成一个MP3文件，同时生成对应的SRT字幕文件，支持在现有音频基础上追加新内容。\\n\\n代码功能摘要：通过MoviePy库实现音频文件的读取、拼接和导出，在音频片段间插入静音间隙，同时根据音频时长和对应文本内容生成标准SRT格式字幕文件，支持批量处理和追加模式。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: save_path\\n    type: string\\n    required: true\\n    description: 保存生成文件的目标文件夹路径\\n  - name: save_name\\n    type: string\\n    required: true\\n    description: 生成的音频和字幕文件的基础名称（不含扩展名）\\n  - name: use_voice\\n    type: string\\n    required: true\\n    description: 音频文件路径，支持单个文件路径或文件路径列表\\n  - name: use_txt\\n    type: string\\n    required: true\\n    description: 对应的文本文件路径，与音频文件一一对应，用于生成字幕内容\\noutputs:\\n  - name: result\\n    type: string\\n    description: 返回处理结果信息，包含生成的音频和字幕文件路径\\n```\\n\\n运行逻辑：\\n- 获取输入参数并检查音频和文本文件列表格式，如果是单个字符串则转换为列表\\n- 构建输出文件路径，包括MP3音频文件和SRT字幕文件的完整路径\\n- 检查目标音频文件是否已存在，如果存在则加载作为基础音频，获取其时长作为起始时间\\n- 遍历输入的音频文件列表，依次处理每个音频文件\\n- 对每个音频文件执行加载操作，获取音频时长信息\\n- 读取对应的文本文件内容，如果文件不存在则使用\"无文本\"作为默认内容\\n- 根据当前时间位置和音频时长计算字幕的开始和结束时间戳\\n- 将音频片段和对应的字幕条目添加到处理列表中\\n- 在每个音频片段之间插入0.3秒的静音间隙\\n- 使用concatenate_audioclips函数将所有音频片段（包括原有音频、新音频和静音间隙）合并\\n- 将合并后的音频导出为MP3格式文件\\n- 将生成的字幕条目按SRT标准格式写入字幕文件，使用追加模式保留原有内容\\n- 返回包含生成文件路径信息的结果字符串'

# **Assign properties to Inputs**
for output in Outputs:
    output['Kind'] = 'String'
for input in Inputs:
    input['Kind'] = 'String'
Inputs[0]['name'] = 'save_path'
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[1]['name'] = 'save_name'
Inputs[2]['name'] = 'use_voice'
Inputs[3]['name'] = 'use_txt'
Outputs[0]['name'] = 'result'

# **格式化时间为SRT格式**
def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds * 1000) % 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"

# **获取现有SRT文件的最后时间戳**
def get_last_timestamp_from_srt(srt_path):
    last_timestamp = 0
    if os.path.exists(srt_path):
        with open(srt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            time_pattern = r"(\d{2}):(\d{2}):(\d{2}),(\d{3})"
            for line in lines:
                match = re.search(time_pattern, line)
                if match:
                    hours, minutes, seconds, milliseconds = map(int, match.groups())
                    last_timestamp = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
    return last_timestamp

# **生成指定时长的静音片段**
def generate_silence(duration, fps=44100, nchannels=1):
    silence = np.zeros((int(duration * fps), nchannels))  # 生成二维全零数组，表示静音
    return AudioArrayClip(silence, fps=fps)

# **拼接音频文件并生成SRT字幕**
def add_audio_with_gaps_and_srt(audio_path, srt_path, audio_files, txt_files, gap_duration):
    audio_clips = []
    srt_entries = []
    current_time = 0  # 如果没有原始音频，时间从0开始

    # 如果音频文件已经存在，加载现有的音频
    if os.path.exists(audio_path):
        original_audio = AudioFileClip(audio_path)
        current_time = original_audio.duration  # 设置当前时间为原音频的时长
        audio_clips.append(original_audio)  # 保留原音频

    for i, audio_file in enumerate(audio_files):
        audio_file = os.path.normpath(audio_file)  # 确保路径格式正确
        txt_file = txt_files[i] if i < len(txt_files) else "（无文本）"  # 确保 txt_files 和音频文件匹配
        print(f"正在处理音频文件: {audio_file}")

        if os.path.exists(audio_file):
            audio_clip = AudioFileClip(audio_file)
            audio_duration = audio_clip.duration
            print(f"音频文件时长: {audio_duration}")

            # 将音频剪辑添加到列表
            audio_clips.append(audio_clip)

            # 读取对应的txt文本内容
            if os.path.exists(txt_file):
                with open(txt_file, 'r', encoding='utf-8') as f:
                    text_content = f.read().strip()
            else:
                text_content = "无文本"

            # 记录SRT字幕的时间和内容
            start_time = current_time
            end_time = start_time + audio_duration

            # 格式化SRT条目，记录文本内容而非文件路径
            srt_entries.append(f"{i+1}\n{format_time(start_time)} --> {format_time(end_time)}\n{text_content}\n")

            # 更新当前时间，考虑间隙
            current_time = end_time + gap_duration  
        else:
            print(f"音频文件未找到: {audio_file}")  # 打印未找到的文件

    # 添加静音间隙段
    silent_gap = generate_silence(gap_duration)
    audio_clips.append(silent_gap)

    # 拼接所有音频片段
    final_audio = concatenate_audioclips(audio_clips)

    # 保存为MP3文件
    final_audio.write_audiofile(audio_path, codec="mp3")

    # 创建或更新SRT文件，使用 'a' 模式追加内容
    with open(srt_path, 'a', encoding='utf-8') as f:
        for entry in srt_entries:
            f.write(entry)

    print(f"已生成音频：{audio_path}，并生成了SRT字幕文件：{srt_path}")

# **主函数执行流程**
def run_node(node):
    save_path = node['Inputs'][0]['Context']  # 获取保存路径
    save_name = node['Inputs'][1]['Context']  # 获取保存文件名
    use_voice = node['Inputs'][2]['Context']  # 获取音频文件列表
    use_txt = node['Inputs'][3]['Context']  # 获取对应的文本文件列表
    gap_duration = 0.3  # 设置音频间隙

    # 检查 use_voice 和 use_txt 是否是列表，如果不是，则转换为列表
    if isinstance(use_voice, str):
        use_voice = [use_voice]
    
    if isinstance(use_txt, str):
        use_txt = [use_txt]
    
    # 打印音频文件列表以检查是否正确
    print(f"音频文件列表: {use_voice}")
    print(f"文本文件列表: {use_txt}")

    audio_path = os.path.normpath(os.path.join(save_path, save_name + ".mp3"))
    srt_path = os.path.normpath(os.path.join(save_path, save_name + ".srt"))

    # 添加音频并生成 SRT 字幕文件
    add_audio_with_gaps_and_srt(audio_path, srt_path, use_voice, use_txt, gap_duration)

    # 返回结果
    result = f"音频已更新: {audio_path}，并生成了SRT字幕文件：{srt_path}"
    node['Outputs'][0]['Context'] = result
    return node['Outputs']