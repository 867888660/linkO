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
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个视频处理节点，主要用于创建或更新视频文件并管理其对应的字幕文件。支持向现有视频追加音频内容，同时自动维护字幕的时间轴同步。\n\n代码功能摘要（概括核心算法或主要处理步骤）\\n核心算法包括视频文件检测与创建、字幕时间轴计算、音频视频拼接处理。主要步骤为：检查目标路径视频文件存在性，不存在则创建空白视频；解析现有字幕文件获取最后时间戳；将新音频转换为黑屏视频片段并拼接到原视频末尾；根据时间轴计算为新内容生成对应字幕条目。\n\n参数\\n```yaml\\ninputs:\\n  - name: save_path\\n    type: string\\n    required: true\\n    description: 视频文件保存的目录路径\\n  - name: save_name\\n    type: string\\n    required: true\\n    description: 视频文件名称（不含扩展名）\\n  - name: use_voice\\n    type: string\\n    required: false\\n    description: 要添加的音频文件路径，为空则不添加音频\\n  - name: use_txt\\n    type: string\\n    required: false\\n    description: 要添加到字幕的文本文件路径，为空则不添加字幕\\noutputs:\\n  - name: result\\n    type: string\\n    description: 返回处理结果描述，包含更新后的视频和字幕文件路径\\n```\n\n运行逻辑（用 - 列表描写详细流程）\\n- 从输入参数获取保存路径、文件名、音频文件路径和文本文件路径\\n- 构建目标视频文件路径和字幕文件路径（.mp4和.srt格式）\\n- 检查视频文件是否存在，如不存在则创建一个显示\"空白视频\"文字的0.5秒短视频\\n- 检查字幕文件是否存在，如不存在且提供了文本文件，则创建新字幕文件并写入文本内容\\n- 加载现有视频文件为VideoFileClip对象\\n- 如果提供了音频文件，加载音频并创建对应时长的黑色背景视频片段\\n- 将音频设置到黑色视频片段上，然后与原视频进行拼接\\n- 解析现有字幕文件，使用正则表达式提取时间戳，计算最后一个字幕的结束时间\\n- 如果提供了文本文件，读取文本内容并计算新字幕的开始和结束时间\\n- 将新字幕条目追加到字幕文件末尾，保持时间轴的连续性\\n- 保存更新后的视频文件，设置fps为24\\n- 返回包含视频和字幕文件路径的结果字符串'

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

# **Function to create a video from an image using Pillow
def create_text_image(text, size=(1280, 720), fontsize=70):
    img = Image.new("RGB", size, color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("arial.ttf", fontsize)  # 替换为本地字体路径
    text_w, text_h = draw.textsize(text, font=font)
    position = ((size[0] - text_w) // 2, (size[1] - text_h) // 2)
    draw.text(position, text, font=font, fill=(255, 255, 255))
    image_path = os.path.join(os.getcwd(), "temp_image.png")
    img.save(image_path)
    return image_path

# Function to get the last timestamp from an existing SRT file
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

# **Function to check or create video and srt files
def find_or_create_video_and_srt(save_path, save_name, use_txt=None):
    video_path = os.path.join(save_path, save_name + ".mp4")
    srt_path = os.path.join(save_path, save_name + ".srt")

    # 如果视频不存在，则创建空白视频
    if not os.path.exists(video_path):
        print(f"未找到视频文件，正在创建空白视频: {video_path}")
        image_path = create_text_image("空白视频")
        blank_video = ImageClip(image_path, duration=0.5)
        blank_video.write_videofile(video_path, fps=24)

    # 如果字幕不存在，则创建空白字幕文件，内容来自文本
    if not os.path.exists(srt_path) and use_txt:
        print(f"未找到字幕文件，正在创建字幕: {srt_path}")
        with open(srt_path, 'w', encoding='utf-8') as f:
            with open(use_txt, 'r', encoding='utf-8') as txt_file:
                text_content = txt_file.read()
            f.write(f"1\n00:00:00,000 --> 00:00:{int(VideoFileClip(video_path).duration):02d},000\n{text_content}\n\n")

    return video_path, srt_path

# **Function to add voice and txt to video and srt files
def add_voice_and_txt_to_video(video_path, srt_path, use_voice=None, use_txt=None):
    video = VideoFileClip(video_path)

    # 添加音频，附加到视频末尾，而不是覆盖
    if use_voice and os.path.exists(use_voice):
        audio_clip = AudioFileClip(use_voice)
        audio_duration = audio_clip.duration

        # 创建一个只有音频的黑色视频剪辑，长度为音频的时长
        audio_video = ColorClip(size=(video.w, video.h), color=(0, 0, 0), duration=audio_duration)
        audio_video = audio_video.set_audio(audio_clip)

        # 将原视频和带有新音频的剪辑拼接起来
        final_video = concatenate_videoclips([video, audio_video])
        print(f"已将 {use_voice} 音频附加到视频末尾")
    else:
        final_video = video  # 如果没有音频，则保持原视频

    # 保存更新后的视频
    final_video.write_videofile(video_path, fps=24)

    # 获取现有字幕的最后时间
    last_timestamp = get_last_timestamp_from_srt(srt_path)
    
    # 添加文本到字幕文件，字幕内容来自txt文件
    if use_txt and os.path.exists(use_txt):
        with open(srt_path, 'a', encoding='utf-8') as f:
            with open(use_txt, 'r', encoding='utf-8') as txt_file:
                text_content = txt_file.read()

            # 计算新字幕的开始时间和结束时间
            start_time = last_timestamp
            end_time = start_time + final_video.duration

            # 将新字幕的时间格式化
            start_time_str = "{:02}:{:02}:{:02},{:03}".format(
                int(start_time // 3600), int((start_time % 3600) // 60), int(start_time % 60),
                int((start_time * 1000) % 1000)
            )
            end_time_str = "{:02}:{:02}:{:02},{:03}".format(
                int(end_time // 3600), int((end_time % 3600) // 60), int(end_time % 60),
                int((end_time * 1000) % 1000)
            )

            # 写入新的字幕
            f.write(f"{2}\n{start_time_str} --> {end_time_str}\n{text_content}\n\n")
        print(f"已将 {use_txt} 的内容添加到字幕文件中")

# **Main function to execute the process
def run_node(node):
    save_path = node['Inputs'][0]['Context']  # 获取 save_path
    save_name = node['Inputs'][1]['Context']  # 获取 save_name
    use_voice = node['Inputs'][2]['Context']  # 获取 use_voice
    use_txt = node['Inputs'][3]['Context']    # 获取 use_txt

    # 检查并创建视频和字幕文件
    video_path, srt_path = find_or_create_video_and_srt(save_path, save_name, use_txt)
    
    # 添加音频和字幕
    add_voice_and_txt_to_video(video_path, srt_path, use_voice, use_txt)

    # 返回结果
    result = f"视频已更新: {video_path}, 字幕文件已更新: {srt_path}"
    Outputs[0]['Context'] = result
    return Outputs
