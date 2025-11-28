import os
import re
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip, ColorClip, ImageClip


# **Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 4
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个音视频合成和字幕生成节点，能够将多个音频文件合成为一个视频，并自动生成同步的SRT字幕文件，支持追加模式向现有视频添加新内容。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n核心算法包括：检查现有视频文件并获取时长作为新内容起始点，为每个音频文件创建黑色背景视频片段并添加音频，读取对应文本文件生成SRT格式字幕，在音频片段间添加间隙，最后将所有片段拼接成完整视频并保存。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: save_path\\n    type: string\\n    required: true\\n    description: 视频和字幕文件的保存路径\\n  - name: save_name\\n    type: string\\n    required: true\\n    description: 保存的文件名称（不含扩展名）\\n  - name: use_voice\\n    type: string\\n    required: true\\n    description: 音频文件路径列表，支持单个文件或多个文件\\n  - name: use_txt\\n    type: string\\n    required: true\\n    description: 对应的文本文件路径列表，用于生成字幕\\noutputs:\\n  - name: result\\n    type: string\\n    description: 返回生成的视频和SRT字幕文件的路径信息\\n```\\n\\n运行逻辑\\n- 检查保存路径下是否存在同名MP4视频文件，如果存在则获取现有视频时长作为新内容的起始时间点，否则从0开始\\n- 将输入的音频文件和文本文件转换为列表格式，确保数据类型一致性\\n- 遍历每个音频文件，创建1280x720分辨率的黑色背景视频片段\\n- 为每个视频片段添加对应的音频轨道，设置精确的音频时长\\n- 读取对应的文本文件内容，如果文件不存在则使用默认文本\\n- 计算每个音频片段的开始和结束时间戳，生成SRT格式的字幕条目\\n- 在音频片段之间添加0.1秒的静音间隙，避免音频间的突兀切换\\n- 将所有视频片段（包括原视频、新音频片段和间隙）按顺序拼接\\n- 精确控制最终视频时长，去除多余的0.05秒以确保时长准确\\n- 将拼接后的视频以30fps的帧率保存为MP4格式\\n- 以追加模式将生成的SRT字幕条目写入字幕文件\\n- 返回包含视频文件路径和字幕文件路径的结果信息'

# **Assign properties to Inputs
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

def add_audio_with_gaps_and_srt(video_path, srt_path, audio_files, txt_files, gap_duration):
    clips = []
    srt_entries = []
    
    # 如果视频文件存在，加载现有视频，并设置当前时间
    if os.path.exists(video_path):
        video = VideoFileClip(video_path)
        current_time = video.duration
        print(f"现有视频时长: {video.duration}")
        clips.append(video)  # 保留原视频
    else:
        current_time = 0  # 如果没有原视频，当前时间从0开始

    for i, audio_file in enumerate(audio_files):
        audio_file = os.path.normpath(audio_file)  # 确保路径格式正确
        txt_file = txt_files[i] if i < len(txt_files) else "（无文本）"  # 确保 txt_files 和音频文件匹配
        print(f"正在处理音频文件: {audio_file}")

        if os.path.exists(audio_file):
            audio_clip = AudioFileClip(audio_file)
            audio_duration = audio_clip.duration
            print(f"音频文件时长: {audio_duration}")

            # 创建音频的黑色视频剪辑，确保时长精确
            audio_video = ColorClip(size=(1280, 720), color=(0, 0, 0), duration=audio_duration)
            audio_video = audio_video.set_audio(audio_clip)

            # 将音频视频添加到剪辑列表
            clips.append(audio_video)

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

    # 添加最后的静音间隙段
    silent_gap = ColorClip(size=(1280, 720), color=(0, 0, 0), duration=gap_duration).set_audio(None)  # 最后一个 gap 强制静音
    clips.append(silent_gap)

    # 拼接原视频和音频片段
    if clips:
        final_video = concatenate_videoclips(clips)

        # 强制裁剪视频的时长，避免多出的 0.05 秒
        final_video_duration = sum([clip.duration for clip in clips])
        final_video = final_video.subclip(0, final_video_duration-0.05)

        final_video.write_videofile(video_path, fps=30)
        # 输出final_video时长
        print(f"final_video时长: {final_video.duration}")

    # 创建或更新SRT文件，使用 'a' 模式追加内容
    with open(srt_path, 'a', encoding='utf-8') as f:
        for entry in srt_entries:
            f.write(entry)

    print(f"已生成视频：{video_path}，并生成了SRT字幕文件：{srt_path}")


# **格式化时间为SRT格式**
def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds * 1000) % 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"

# **主函数执行流程**
def run_node(node):
    save_path = node['Inputs'][0]['Context']  # 获取保存路径
    save_name = node['Inputs'][1]['Context']  # 获取保存文件名
    use_voice = node['Inputs'][2]['Context']  # 获取音频文件列表
    use_txt = node['Inputs'][3]['Context']  # 获取对应的文本文件列表
    gap_duration = 0.1  # 设置音频间隙

    # 检查 use_voice 和 use_txt 是否是列表，如果不是，则转换为列表
    if isinstance(use_voice, str):
        use_voice = [use_voice]
    
    if isinstance(use_txt, str):
        use_txt = [use_txt]
    
    # 打印音频文件列表以检查是否正确
    print(f"音频文件列表: {use_voice}")
    print(f"文本文件列表: {use_txt}")

    video_path = os.path.normpath(os.path.join(save_path, save_name + ".mp4"))
    srt_path = os.path.normpath(os.path.join(save_path, save_name + ".srt"))

    # 添加音频并生成 SRT 字幕文件
    add_audio_with_gaps_and_srt(video_path, srt_path, use_voice, use_txt, gap_duration)

    # 返回结果
    result = f"视频已更新: {video_path}，并生成了SRT字幕文件：{srt_path}"
    node['Outputs'][0]['Context'] = result
    return node['Outputs']