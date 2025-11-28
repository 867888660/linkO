import os
import re
import tempfile
import shutil
from moviepy.editor import AudioFileClip, CompositeAudioClip

# **Define the number of outputs and inputs**
OutPutNum = 1
InPutNum = 6
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0}
           for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,
           'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': False}
          for i in range(InPutNum)]
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能\\n这是一个音频合成处理节点，主要用于将多个音效按照指定时间点插入到主音频中，并进行音量调整和保存。\\n\\n代码功能摘要\\n该节点通过解析音效配置文本，提取音效名称和时间信息，在指定文件夹中查找对应的音效文件，然后将这些音效按时间轴合成到主音频中。支持多种时间格式解析和音频格式处理，使用临时文件机制解决中文路径问题，最终输出高质量的合成音频文件。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: Voice_path\\n    type: file\\n    required: true\\n    description: 主音频文件路径\\n  - name: Soundtxt\\n    type: string\\n    required: true\\n    description: 音效配置文本，使用**^^**分隔不同音效段\\n  - name: Sound_Path\\n    type: file\\n    required: true\\n    description: 音效文件所在文件夹路径\\n  - name: Save_path\\n    type: file\\n    required: true\\n    description: 合成后音频的保存文件夹路径\\n  - name: Save_name\\n    type: string\\n    required: true\\n    description: 合成后音频的文件名\\n  - name: Volume\\n    type: string\\n    required: true\\n    description: 音效的音量大小（数字格式）\\noutputs:\\n  - name: result\\n    type: string\\n    description: 处理结果信息，包括成功保存路径或错误信息\\n```\\n\\n运行逻辑\\n- 验证输入参数的有效性，包括文件路径存在性和音量值的数字格式\\n- 加载主音频文件，检查文件是否可正常读取\\n- 解析音效配置文本，使用**^^**分隔符将其分割成独立的音效信息段\\n- 对每个音效段提取音效名称和时间点信息，支持多种时间格式（HH:MM:SS、MM:SS、SS）\\n- 在音效文件夹中查找匹配的音效文件，支持mp3、wav、ogg等格式\\n- 加载找到的音效文件并设置其开始时间、音量和最大时长限制（5秒）\\n- 验证所有音效的时间轴是否在主音频时长范围内，过滤无效音效\\n- 使用CompositeAudioClip将主音频和所有有效音效合成为最终音频\\n- 创建临时文件处理中文路径问题，设置输出音频质量（44.1kHz采样率，192k比特率）\\n- 将临时文件移动到指定保存位置，确保目标目录存在\\n- 清理所有音频资源，返回处理结果信息'

# **Assign properties to Inputs**
Inputs[0]['name'] = 'Voice_path'
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[1]['name'] = 'Soundtxt'
Inputs[1]['Kind'] = 'String'
Inputs[2]['name'] = 'Sound_Path'
Inputs[2]['Kind'] = 'String_FilePath'
Inputs[3]['name'] = 'Save_path'
Inputs[3]['Kind'] = 'String_FilePath'
Inputs[4]['name'] = 'Save_name'
Inputs[4]['Kind'] = 'String'
Inputs[5]['name'] = 'Volume'
Inputs[5]['Kind'] = 'String'
Outputs[0]['name'] = 'result'
Outputs[0]['Kind'] = 'String'

def parse_time(time_str):
    """Parse various time formats to seconds"""
    clean_time = re.sub(r'[^0-9:]', '', time_str.strip())

    try:
        parts = clean_time.split(':')
        if len(parts) == 3:  # HH:MM:SS
            h, m, s = map(int, parts)
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:  # MM:SS
            m, s = map(int, parts)
            return m * 60 + s
        elif len(parts) == 1:  # SS
            return int(parts[0])
        else:
            raise ValueError(f"Invalid time format: {time_str}")
    except Exception as e:
        raise ValueError(f"Could not parse time: {time_str}, error: {str(e)}")

def extract_sound_info(segment):
    """Extract sound name and timestamp from text segment"""
    lines = [line.strip() for line in segment.split('\n') if line.strip()]
    if not lines:
        return None

    # Remove prefixes like '音效名：', '音效：', 'sound name:', etc.
    prefix_patterns = [
        r'^音效名[:：\s]*',
        r'^音效[:：\s]*',
        r'^Sound name[:：\s]*',
        r'^Sound[:：\s]*',
    ]
    name_line = lines[0]
    for pattern in prefix_patterns:
        name_line = re.sub(pattern, '', name_line, flags=re.IGNORECASE)

    sound_info = {
        'name': name_line.strip(),
        'time': None
    }

    # Remove any text inside parentheses
    sound_info['name'] = re.sub(r'\(.*?\)', '', sound_info['name']).strip()

    for line in lines[1:]:
        # Remove prefixes like '时间轴', '时间', 'Time:', etc.
        time_line = line
        time_prefix_patterns = [
            r'^时间轴[:：\s]*',
            r'^时间点[:：\s]*',
            r'^时间[:：\s]*',
            r'^Time[:：\s]*',
        ]
        for pattern in time_prefix_patterns:
            time_line = re.sub(pattern, '', time_line, flags=re.IGNORECASE)

        if re.search(r'\d{1,2}:\d{2}(:\d{2})?', time_line):
            try:
                sound_info['time'] = parse_time(time_line)
                break
            except ValueError:
                continue

    return sound_info if sound_info['time'] is not None else None

def find_sound_file(sound_name, sound_path):
    """Find matching sound file in directory"""
    sound_name = sound_name.lower()
    for file in os.listdir(sound_path):
        file_lower = file.lower()
        file_base = os.path.splitext(file_lower)[0]
        if (sound_name == file_base or sound_name in file_base) and \
           any(file_lower.endswith(ext) for ext in ['.mp3', '.wav', '.ogg']):
            return os.path.join(sound_path, file)
    return None

def run_node(node):
    try:
        # Get input values
        Voice_path = node['Inputs'][0]['Context']
        Soundtxt = node['Inputs'][1]['Context']
        Sound_Path = node['Inputs'][2]['Context']
        Save_path = node['Inputs'][3]['Context']
        Save_name = node['Inputs'][4]['Context']
        Volume_str = node['Inputs'][5]['Context']

        try:
            Volume = float(Volume_str)
        except ValueError:
            result = f"Error: Volume '{Volume_str}' is not a valid number."
            node['Outputs'][0]['Context'] = result
            return node['Outputs']


        # Convert paths
        Voice_path = Voice_path
        Sound_Path = Sound_Path
        Save_path = Save_path

        # Validate inputs
        if not os.path.exists(Voice_path):
            result = f'Error: Main audio file not found at {Voice_path}'
            node['Outputs'][0]['Context'] = result
            return node['Outputs']
        if not os.path.exists(Sound_Path):
            result = f'Error: Sound folder not found at {Sound_Path}'
            node['Outputs'][0]['Context'] = result
            return node['Outputs']

        # Load main audio
        try:
            main_audio = AudioFileClip(Voice_path)
        except Exception as e:
            result = f"Error: Failed to load main audio file: {str(e)}"
            node['Outputs'][0]['Context'] = result
            return node['Outputs']

        sound_effects = []

        # Process segments
        segments = [seg.strip() for seg in Soundtxt.split('**^^**') if seg.strip()]

        for segment in segments:
            sound_info = extract_sound_info(segment)
            if not sound_info:
                print(f"Warning: Could not extract sound info from segment: {segment}")
                continue

            sound_file = find_sound_file(sound_info['name'], Sound_Path)
            if not sound_file:
                print(f"Warning: Sound file not found for: {sound_info['name']}")
                continue

            try:
                # Debug: print the sound file path
                print(f"Found sound file: {sound_file}")
                effect = AudioFileClip(sound_file)
                # 设置音效的持续时间，避免音效太长
                original_duration = effect.duration
                effect = effect.set_start(float(sound_info['time']))
                # 如果音效时长超过5秒，将其限制为5秒
                if original_duration > 5:
                    effect = effect.subclip(0, 5)
                effect = effect.volumex(Volume)
                sound_effects.append(effect)
                print(f"Successfully added sound effect: {sound_info['name']} at time {sound_info['time']}")
            except Exception as e:
                print(f"Warning: Failed to process sound '{sound_info['name']}': {str(e)}")
                continue

        # Combine audio clips
        if sound_effects:
            try:
                # 确保所有音效的时长不超过主音频
                sound_effects = [
                    effect.set_duration(
                        min(effect.duration, main_audio.duration - effect.start)
                    ) for effect in sound_effects
                ]

                # 检查是否所有音效的起始时间都在主音频的范围内
                valid_effects = []
                for effect in sound_effects:
                    if effect.start <= main_audio.duration:
                        valid_effects.append(effect)
                    else:
                        print(f"Warning: Sound effect starting at {effect.start}s exceeds main audio duration.")

                final_audio = CompositeAudioClip([main_audio] + valid_effects)

                # 创建一个临时文件，确保路径中没有中文字符
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_audio_file:
                    temp_output_path = temp_audio_file.name

                # 保存音频文件到临时路径
                final_audio.write_audiofile(
                    temp_output_path,
                    fps=44100,
                    codec='libmp3lame',
                    bitrate='192k'
                )

                # 确保保存目录存在
                os.makedirs(Save_path, exist_ok=True)

                # 将临时文件移动到目标路径
                output_path = os.path.join(Save_path, Save_name if Save_name.endswith('.mp3') else Save_name + '.mp3')
                shutil.move(temp_output_path, output_path)

                # 清理资源
                main_audio.close()
                final_audio.close()
                for effect in valid_effects:
                    effect.close()

                result = f'Successfully saved combined audio to {output_path}'
                node['Outputs'][0]['Context'] = result
                return node['Outputs']

            except Exception as e:
                main_audio.close()
                for effect in sound_effects:
                    effect.close()
                result = f'Error during audio processing: {str(e)}'
                node['Outputs'][0]['Context'] = result
                return node['Outputs']
        else:
            try:
                # 创建一个临时文件，确保路径中没有中文字符
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_audio_file:
                    temp_output_path = temp_audio_file.name

                # 保存主音频到临时路径
                main_audio.write_audiofile(
                    temp_output_path,
                    fps=44100,
                    codec='libmp3lame',
                    bitrate='192k'
                )

                # 确保保存目录存在
                os.makedirs(Save_path, exist_ok=True)

                # 将临时文件移动到目标路径
                output_path = os.path.join(Save_path, Save_name if Save_name.endswith('.mp3') else Save_name + '.mp3')
                shutil.move(temp_output_path, output_path)

                # 清理资源
                main_audio.close()

                result = f'Successfully saved main audio to {output_path}'
                node['Outputs'][0]['Context'] = result
                return node['Outputs']
            except Exception as e:
                main_audio.close()
                result = f'Error saving main audio: {str(e)}'
                node['Outputs'][0]['Context'] = result
                return node['Outputs']

    except Exception as e:
        result = f'Error: {str(e)}'
        node['Outputs'][0]['Context'] = result
        return node['Outputs']
