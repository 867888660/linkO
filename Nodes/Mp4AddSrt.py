import os
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, ColorClip
from moviepy.video.tools.subtitles import SubtitlesClip
from moviepy.config import change_settings
import re

# 如果您使用Windows，并且ImageMagick的路径不在系统环境变量中，需要指定其路径
change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})

# 定义节点的输入输出（根据您的需求，如果不需要可以忽略）
OutPutNum = 1
InPutNum = 3

Outputs = [{'Num': None,'Context': None,'Boolean':False,'Kind': None, 'Id': f'Output{i + 1}', 'name': 'Result', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None,'Context': None,'Boolean':False, 'Kind': None, 'Id': f'Input{i + 1}',  'Isnecessary': True, 'name': name, 'Link': 0, 'IsLabel': False} 
          for i, name in enumerate(['MP4_FilePath', 'Srt_FilePath', 'SaveName'])]

# 节点配置（如果需要）
FunctionIntroduction='这是一个视频字幕添加程序。\n\n输入：\n1. MP4_FilePath (String_FilePath类型) - 视频文件的路径\n2. Srt_FilePath (String_FilePath类型) - SRT格式字幕文件的路径\n3. SaveName (String类型) - 输出视频的保存名称\n\n输出：\nResult (String类型) - 处理过程的详细日志信息\n\n运行逻辑：\n1. 程序首先验证输入路径和ImageMagick环境配置\n2. 通过parse_srt函数解析SRT字幕文件，将其转换为时间戳和文本的列表格式\n3. 使用VideoFileClip加载原始视频\n4. create_subtitle_clips函数负责创建电影风格的字幕效果：\n   - 使用白色字体配黑色描边\n   - 字幕居中显示在底部\n   - 支持中文字体(默认微软雅黑)\n   - 字幕大小自适应视频宽度\n5. 使用SubtitlesClip将所有字幕片段组合\n6. 通过CompositeVideoClip将字幕叠加到原视频上\n7. 最后导出最终视频，保持原视频质量，并提供详细的处理日志\n\n特点：\n- 支持标准SRT字幕格式\n- 提供专业的电影字幕效果\n- 保持视频原有质量\n- 有完善的错误处理机制\n- 提供详细的处理日志输出\n\n注意事项：\n- 需要正确配置ImageMagick\n- 输入文件必须存在且格式正确\n- 输出视频将保存在与输入视频相同的目录下'
NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# 输入和输出配置（如果需要）
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'MP4_FilePath'
Inputs[1]['Kind'] = 'String_FilePath'
Inputs[1]['name'] = 'Srt_FilePath'
Inputs[2]['Kind'] = 'String'
Inputs[2]['name'] = 'SaveName'
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'

def time_to_seconds(time_str):
    """将时间字符串转换为秒"""
    try:
        if ',' in time_str:
            time_parts, ms = time_str.split(',')
        elif '.' in time_str:
            time_parts, ms = time_str.split('.')
        else:
            time_parts = time_str
            ms = '0'

        h, m, s = time_parts.split(':')

        total_seconds = int(h) * 3600 + int(m) * 60 + float(s) + float('0.' + ms)
        return total_seconds

    except Exception as e:
        print(f"时间转换错误，输入值: {time_str}")
        print(f"错误信息: {str(e)}")
        return 0

def parse_srt(srt_path):
    """解析SRT文件，返回 [((t1,t2), text), ...] 格式"""
    try:
        with open(srt_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        subtitles = []
        i = 0
        debug_info = []  # 用于收集调试信息
        debug_info.append(f"开始解析SRT文件，总行数: {len(lines)}")

        while i < len(lines):
            line = lines[i].strip()

            if not line or line.isdigit():
                i += 1
                continue

            if '-->' in line:
                try:
                    time_parts = line.split(' --> ')
                    if len(time_parts) != 2:
                        debug_info.append(f"时间格式错误: {line}")
                        i += 1
                        continue

                    start_time, end_time = time_parts

                    text_lines = []
                    i += 1
                    while i < len(lines) and lines[i].strip():
                        text_lines.append(lines[i].strip())
                        i += 1

                    if text_lines:
                        start_sec = time_to_seconds(start_time)
                        end_sec = time_to_seconds(end_time)
                        subtitle_text = '\n'.join(text_lines)
                        
                        debug_info.append(f"找到字幕: {start_time} --> {end_time} : {subtitle_text}")
                        subtitles.append(((start_sec, end_sec), subtitle_text))
                except Exception as e:
                    debug_info.append(f"解析单个字幕时出错: {str(e)}")

            else:
                i += 1

        debug_info.append(f"解析完成，共找到 {len(subtitles)} 条字幕")
        if not subtitles:
            debug_info.append("警告: 未找到有效字幕")
            return [((0, 1), " ")], debug_info

        return subtitles, debug_info

    except Exception as e:
        return [((0, 1), " ")], [f"解析字幕文件时出错: {str(e)}"]

def create_subtitle_clips(txt):
    """创建电影风格的字幕片段，优化字体外观"""
    if not txt or txt.isspace():
        return TextClip(" ", fontsize=1, color='white', size=(2, 2))
    
    # 指定字体文件的路径（请根据您的字体文件实际路径进行修改）
    # 例如，如果使用微软雅黑字体：
    font_path = 'C:/Windows/Fonts/msyhbd.ttc'  # 微软雅黑粗体
    # 或者使用思源黑体：
    # font_path = '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc'  # Linux 平台
    
    text_clip = TextClip(
        txt, 
        font=font_path,          # 使用字体文件的完整路径
        fontsize=60,             # 根据需要调整字体大小
        color='white',
        stroke_color='black',   
        stroke_width=2,          # 根据需要调整描边宽度
        size=(video.w - 40, None), 
        method='caption',
        align='center',
    )
    return text_clip

def run_node(node):
    global video
    debug_messages = []
    try:
        # 获取输入参数
        MP4_FilePath = node['Inputs'][0]['Context']
        Srt_FilePath = node['Inputs'][1]['Context']
        SaveName = node['Inputs'][2]['Context']

        # 规范化路径，移除多余的反斜杠
        MP4_FilePath = os.path.normpath(MP4_FilePath)
        Srt_FilePath = os.path.normpath(Srt_FilePath)
        
        debug_messages.append(f"规范化后的路径: \nMP4: {MP4_FilePath}\nSRT: {Srt_FilePath}")

        # 处理输出路径
        if not SaveName.lower().endswith('.mp4'):
            SaveName += '.mp4'
        output_dir = os.path.dirname(MP4_FilePath)
        output_path = os.path.normpath(os.path.join(output_dir, SaveName))
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

        # 验证输入文件
        if not os.path.exists(MP4_FilePath):
            raise FileNotFoundError(f"MP4 文件未找到: {MP4_FilePath}")
        if not os.path.exists(Srt_FilePath):
            raise FileNotFoundError(f"SRT 文件未找到: {Srt_FilePath}")

        # 加载视频
        print("正在加载视频...")
        video = VideoFileClip(MP4_FilePath)
        debug_messages.append(f"视频加载成功，时长: {video.duration}秒")

        # 解析字幕并创建字幕剪辑
        debug_messages.append("正在处理字幕...")
        subs, srt_debug_info = parse_srt(Srt_FilePath)
        debug_messages.extend(srt_debug_info)

        if not subs:
            debug_messages.append("警告: 没有找到有效字幕，将创建空字幕")
            subs = [((0, 1), " ")]

        subtitles = SubtitlesClip(subs, create_subtitle_clips)

        # 创建半透明的背景条带
        subtitle_bg = ColorClip(
            size=(video.w, 100),      # 宽度等于视频宽度，高度可根据需要调整
            color=(0, 0, 0)           # 纯黑色
        ).set_opacity(0.4).set_position(("center", "bottom")).set_duration(video.duration)

        # 合成视频时将字幕和背景叠加在视频上
        debug_messages.append("正在合成视频...")
        # 在合成视频时，直接使用字幕，不添加背景条带
        final_video = CompositeVideoClip([
            video,
            subtitles.set_position(('center', 'bottom'))  # 设置字幕位置
        ])
        debug_messages.append("视频合成成功")

        # 导出视频
        debug_messages.append("正在保存视频...")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            fps=video.fps,
            threads=4,
            preset='medium',
            ffmpeg_params=["-crf", "18"]  # 提升画质
        )

        # 清理资源
        video.close()
        final_video.close()

        debug_messages.append(f"视频已保存到: {output_path}")
        Outputs[0]['Context'] = "\n".join(debug_messages)  # 将所有调试信息写入输出

    except Exception as e:
        error_msg = f"发生错误: {str(e)}\n"
        import traceback
        error_msg += f"详细错误信息:\n{traceback.format_exc()}"
        debug_messages.append(error_msg)
        Outputs[0]['Context'] = "\n".join(debug_messages)

    return Outputs


