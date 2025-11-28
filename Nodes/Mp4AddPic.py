import os
import json
import logging
import subprocess

# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 5

# Initialize Outputs and Inputs arrays
Outputs = [{'Num': None,'Context': None,'Boolean':False,'Kind': None, 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None,'Context': None,'Boolean':False, 'Kind': None, 'Id': f'Input{i + 1}',  'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]

# Node configuration
FunctionIntroduction='组件功能：这是一个在MP4视频中添加图片叠加层的视频处理节点，能够在指定时间段内将图片居中显示在视频上。\\n\\n代码功能摘要：使用FFmpeg工具对视频和图片进行缩放处理，将图片作为叠加层添加到视频的指定时间段内，支持多种时间格式输入和智能时间解析，最终输出处理后的视频文件。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: MP4_FilePath\\n    type: file\\n    required: true\\n    description: 需要添加图片的MP4视频文件路径\\n  - name: Pic_FilePath\\n    type: file\\n    required: true\\n    description: 要叠加到视频上的图片文件路径\\n  - name: StartTime\\n    type: string\\n    required: true\\n    description: 图片开始显示的时间点，支持HH:MM:SS或MM:SS格式\\n  - name: EndTime\\n    type: string\\n    required: true\\n    description: 图片结束显示的时间点，支持HH:MM:SS、MM:SS格式或\\\"END\\\"表示到视频结束\\n  - name: WebInput\\n    type: string\\n    required: true\\n    description: 第五个输入参数（未使用）\\noutputs:\\n  - name: Result\\n    type: string\\n    description: 返回处理后的视频文件路径或错误信息\\n```\\n\\n运行逻辑：\\n- 获取输入的视频文件路径、图片文件路径和时间参数\\n- 对输入的时间字符串进行预处理，将中文冒号转换为英文冒号\\n- 使用正则表达式解析时间格式，支持HH:MM:SS和MM:SS两种格式，并处理MM:SS:00误输入情况\\n- 验证时间值的有效性，确保分钟和秒数不超过60\\n- 检查图片文件是否存在，不存在则抛出异常\\n- 将开始时间和结束时间转换为秒数，特殊处理\"END\"关键字\\n- 创建临时输出文件路径，避免直接覆盖原文件\\n- 构建FFmpeg命令，设置视频和图片都缩放到1080x1080分辨率\\n- 使用filter_complex参数实现图片居中叠加效果，在指定时间段内显示\\n- 配置编码参数使用ultrafast预设提高处理速度\\n- 执行FFmpeg命令进行视频处理\\n- 处理成功后用临时文件替换原始文件\\n- 如果处理失败则清理临时文件并抛出详细错误信息\\n- 将最终的输出文件路径或错误信息设置到输出参数中'
NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Configure inputs and outputs
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'MP4_FilePath'
Inputs[1]['Kind'] = 'String_FilePath'
Inputs[1]['name'] = 'Pic_FilePath'
Inputs[2]['Kind'] = 'String'
Inputs[2]['name'] = 'StartTime'
Inputs[3]['Kind'] = 'String'
Inputs[3]['name'] = 'EndTime'
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'

def time_str_to_seconds(time_str):
    """
    Convert time string to seconds. Extract HH:MM:SS or MM:SS format from the input string,
    ignoring any other text. Also handles the case where MM:SS:00 is mistakenly input instead of HH:MM:SS.
    """
    import re
    try:
        # Replace Chinese colons with English colons
        time_str = time_str.replace('：', ':')
        
        # Try to find time pattern HH:MM:SS or MM:SS
        time_patterns = [
            r'(\d{1,2}):(\d{1,2}):(\d{1,2})',  # HH:MM:SS
            r'(\d{1,2}):(\d{1,2})'             # MM:SS
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, time_str)
            if match:
                numbers = [int(x) for x in match.groups()]
                if len(numbers) == 3:  # HH:MM:SS format
                    h, m, s = numbers
                    # 处理MM:SS:00被误输入为HH:MM:SS的情况
                    if h > 0 and s == 0 and m < 60:
                        # 将MM:SS:00转换为00:MM:SS格式
                        h, m, s = 0, h, m
                else:  # MM:SS format
                    h = 0
                    m, s = numbers
                
                # Validate the time values
                if m >= 60 or s >= 60:
                    raise ValueError("Minutes and seconds must be less than 60")
                    
                return h * 3600 + m * 60 + s
        
        # If no time pattern found, try to extract just numbers
        numbers = re.findall(r'\d+', time_str)
        if numbers:
            numbers = [int(n) for n in numbers]
            if len(numbers) >= 3:
                h, m, s = numbers[-3], numbers[-2], numbers[-1]
                # 处理MM:SS:00被误输入为HH:MM:SS的情况
                if h > 0 and s == 0 and m < 60:
                    h, m, s = 0, h, m
            elif len(numbers) == 2:
                h = 0
                m, s = numbers[-2], numbers[-1]
            elif len(numbers) == 1:
                h = 0
                m = 0
                s = numbers[-1]
            else:
                raise ValueError("No valid time format found")
                
            # Validate the time values
            if m >= 60 or s >= 60:
                raise ValueError("Minutes and seconds must be less than 60")
                
            return h * 3600 + m * 60 + s
            
        raise ValueError("No valid time format found in the input string")
        
    except Exception as e:
        raise ValueError(f"Invalid time format in '{time_str}'. Expected format: HH:MM:SS or MM:SS. Error: {e}")
    
def run_node(node):
    # 添加 FFmpeg 路径配置
    FFMPEG_PATH = r"C:\Empeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
    try:
        # 获取输入参数
        mp4_filepath = os.path.normpath(node['Inputs'][0]['Context'])
        pic_filepath = os.path.normpath(node['Inputs'][1]['Context'])
        start_time_str = node['Inputs'][2]['Context']
        end_time_str = node['Inputs'][3]['Context']
        # Remove the save_name related code and use the original mp4_filepath
        output_path = mp4_filepath

        # Create a temporary output file in the same directory
        temp_output = os.path.splitext(output_path)[0] + '_temp.mp4'

        if not os.path.exists(pic_filepath):
            raise FileNotFoundError(f"Picture file not found: {pic_filepath}")

        # 将时间转换为秒
        start_time = time_str_to_seconds(start_time_str)
        if end_time_str.upper() == "END":
            end_time = 999999  # 一个足够大的数字
        else:
            end_time = time_str_to_seconds(end_time_str)
        
        # 使用原始文件路径作为输出路径
        output_path = mp4_filepath
        
        # 创建临时输出文件路径
        temp_output = os.path.splitext(output_path)[0] + '_temp.mp4'
        
        # 构建 FFmpeg 命令
        # 修改分辨率设置
        width = 1080  # 修改为 1920
        height = 1080  # 修改为 1080
        filter_complex = (
            f'[0:v]scale={width}:{height},setsar=1[base];'  # 首先缩放视频
            f'[1:v]scale={width}:{height}:force_original_aspect_ratio=disable[scaled];'  # 缩放图片
            '[base][scaled]overlay=(W-w)/2:(H-h)/2:enable=\'between(t\\,'
            f'{start_time}\\,{end_time})\'[outv]'
        )
        
        ffmpeg_cmd = [
            FFMPEG_PATH, '-y',
            '-i', mp4_filepath if os.path.exists(mp4_filepath) else f'color=c=black:s={width}x{height}:d=10',
            '-i', pic_filepath,
            '-filter_complex', filter_complex,
            '-map', '[outv]',
            '-map', '0:a?',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'fastdecode',
            '-profile:v', 'baseline',
            '-movflags', '+faststart',
            '-c:a', 'copy',
            temp_output
        ]

        # 打印命令用于调试
        print("Executing FFmpeg command:", ' '.join(ffmpeg_cmd))

        try:
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Replace the original file with the temporary file
            if os.path.exists(temp_output):
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(temp_output, output_path)
            
        except subprocess.CalledProcessError as e:
            if os.path.exists(temp_output):
                os.remove(temp_output)
            error_msg = f"FFmpeg failed with return code {e.returncode}\n"
            error_msg += f"Command: {' '.join(ffmpeg_cmd)}\n"
            error_msg += f"Error output: {e.stderr}\n"
            error_msg += f"Standard output: {e.stdout}"
            raise Exception(error_msg)

        # Set the output to the original file path
        Outputs[0]['Context'] = output_path

    except Exception as e:
        error_message = f"Error processing video: {str(e)}"
        logging.error(error_message)
        Outputs[0]['Context'] = error_message
        raise Exception(error_message)

    return Outputs
