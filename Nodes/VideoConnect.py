import os
import json
import logging
from moviepy.editor import (
    VideoFileClip,
    concatenate_videoclips,
    vfx
)
import re

# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 2

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': None,
            'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': None,
           'Id': f'Input{i + 1}', 'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]

FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个视频处理和合并节点，用于将多个分散在不同数字文件夹中的视频文件按顺序合并成一个完整的视频文件，并在合并过程中对每个视频进行1.1倍速处理。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n该节点通过自然数字排序算法定位并收集指定目录结构下的视频文件，使用MoviePy库对每个视频进行速度调整，然后将所有处理后的视频片段按顺序合并为单一视频文件，最终输出到指定路径。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: Base_Path\\n    type: string\\n    required: true\\n    description: 基础文件路径，用于指定待处理视频文件所在的根目录\\n  - name: SaveName\\n    type: string\\n    required: true\\n    description: 保存的文件名，不需要扩展名，最终合并的视频将自动添加.mp4扩展名\\noutputs:\\n  - name: Result\\n    type: string\\n    description: 输出处理结果的详细信息字符串，包含处理过程中的每个步骤信息和最终视频的输出路径\\n```\\n\\n运行逻辑（用 - 列表描写详细流程）\\n- 验证输入的基础路径是否存在，如果路径无效则抛出异常\\n- 扫描基础路径下的所有子文件夹，筛选出以纯数字命名的文件夹\\n- 使用自然数字排序算法对数字文件夹进行排序，确保按正确的数字顺序处理\\n- 在每个数字文件夹的\"完整音频\"子目录中查找\"Srt+Video.mp4\"文件\\n- 收集所有找到的有效视频文件路径，如果未找到任何视频文件则抛出异常\\n- 逐个加载视频文件，创建VideoFileClip对象（包含音频轨道）\\n- 对每个视频剪辑应用1.1倍速效果，同时保持音频同步\\n- 将所有处理后的视频剪辑添加到剪辑列表中\\n- 使用concatenate_videoclips方法将所有视频剪辑按顺序合并成一个完整视频\\n- 构建输出文件路径，使用指定的SaveName加上.mp4扩展名\\n- 将合并后的视频写入文件，使用libx264视频编码器和aac音频编码器\\n- 清理所有视频剪辑资源，关闭文件句柄以释放内存\\n- 返回包含详细处理过程日志和最终输出路径的结果字符串\\n- 如果处理过程中出现任何异常，记录错误信息并返回失败状态'
NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Assign properties to Inputs and Outputs
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'Base_Path'
Inputs[1]['Kind'] = 'String'  # 确保 Kind 设置为 'String'
Inputs[1]['name'] = 'SaveName'  # 这是文件名
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'



def natural_sort_key(s):
    """Sort strings containing numbers in natural order"""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', s)]

def run_node(node):
    result_messages = []
    try:
        # Get and process paths
        Base_Path = node['Inputs'][0]['Context']
        SaveName = node['Inputs'][1]['Context']
        
        result_messages.append(f"处理基础路径: {Base_Path}")
        
        # Validate inputs
        if not os.path.exists(Base_Path):
            raise Exception(f"基础路径不存在: {Base_Path}")
        result_messages.append(f"基础路径验证成功: {Base_Path}")

        # Find all numeric folders and their video files
        video_files = []
        for folder in sorted(os.listdir(Base_Path), key=natural_sort_key):
            if folder.isdigit():
                video_path = os.path.join(Base_Path, folder, "完整音频", "Srt+Video.mp4")
                if os.path.exists(video_path):
                    video_files.append(video_path)
                    result_messages.append(f"找到视频文件: {video_path}")

        if not video_files:
            raise Exception("未找到有效的视频文件")
        result_messages.append(f"共找到 {len(video_files)} 个视频文件")

        # Process videos (with audio)
        video_clips = []
        for video_path in video_files:
            clip = VideoFileClip(video_path)
            clip = clip.fx(vfx.speedx, 1.1)  # 调整视频和音频速度
            video_clips.append(clip)
            result_messages.append(f"已加载并加速视频: {video_path}")

        # 合并视频剪辑
        final_video = concatenate_videoclips(video_clips, method='compose')
        result_messages.append("视频合并完成")

        # Create output path
        output_path = os.path.join(Base_Path, f"{SaveName}.mp4")
        final_video.write_videofile(output_path, codec='libx264', audio_codec='aac')
        result_messages.append(f"视频保存成功: {output_path}")

        # Clean up
        final_video.close()
        for clip in video_clips:
            clip.close()
        
        node['Outputs'][0]['Context'] = "\n".join(result_messages) + f"\n最终输出路径: {output_path}"
        node['Outputs'][0]['Boolean'] = True
        
    except Exception as e:
        error_message = f"处理失败: {str(e)}"
        result_messages.append(error_message)
        logging.error(error_message)
        node['Outputs'][0]['Context'] = "\n".join(result_messages)
        node['Outputs'][0]['Boolean'] = False
    
    return node['Outputs']
