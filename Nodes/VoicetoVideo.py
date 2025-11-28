import os
import re
from moviepy.editor import AudioFileClip, concatenate_audioclips

# **Define the number of outputs and inputs**
OutPutNum = 2
InPutNum = 4
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能：这是一个音频文件合并与字幕生成的组件，能够将多个音频文件按数字顺序合并，并根据对应的文本文件生成同步的字幕文件。\\n\\n代码功能摘要：使用moviepy库处理音频合并，通过文件名中的数字进行排序，根据音频时长计算字幕时间戳，最终输出合并的MP3音频文件和SRT/TXT格式的字幕文件。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: save_path\\n    type: file\\n    required: true\\n    description: 输出文件保存路径\\n  - name: save_name\\n    type: string\\n    required: true\\n    description: 输出文件名称（不含扩展名）\\n  - name: Voice_Path\\n    type: file\\n    required: true\\n    description: 音频文件夹路径，支持mp3和wav格式\\n  - name: Txt_path\\n    type: file\\n    required: true\\n    description: 字幕文本文件夹路径\\noutputs:\\n  - name: result\\n    type: string\\n    description: 操作执行结果的描述信息\\n  - name: File_Path\\n    type: string\\n    description: 合并后音频文件的完整路径\\n```\\n\\n运行逻辑：\\n- 从指定的音频目录读取所有mp3和wav格式的音频文件\\n- 从指定的文本目录读取所有txt格式的字幕文件\\n- 通过正则表达式提取文件名中的数字，对音频文件和文本文件进行排序\\n- 使用moviepy库逐个加载音频文件，创建音频剪辑对象\\n- 读取对应的txt文件内容作为字幕文本\\n- 根据音频时长计算每段字幕的开始和结束时间戳\\n- 生成SRT格式的字幕条目，包含时间范围和文本内容\\n- 使用concatenate_audioclips函数将所有音频剪辑合并为一个完整的音频\\n- 将合并后的音频导出为MP3格式文件\\n- 将字幕条目写入SRT格式文件和TXT格式文件\\n- 返回操作结果描述和输出音频文件的完整路径'

# **Assign properties to Inputs**
for output in Outputs:
    output['Kind'] = 'String'
for input in Inputs:
    input['Kind'] = 'String'
Inputs[0]['name'] = 'save_path'
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[1]['name'] = 'save_name'
Inputs[2]['name'] = 'Voice_Path'
Inputs[2]['Kind'] = 'String_FilePath'
Inputs[3]['name'] = 'Txt_path'
Inputs[3]['Kind'] = 'String_FilePath'
Outputs[0]['name'] = 'result'
Outputs[1]['name'] ='File_Path'

# **Retrieve and sort files**
def get_sorted_files(directory, file_extension):
    files = [f for f in os.listdir(directory) if f.endswith(file_extension)]
    # Sort files by the number in their filenames (e.g., "朗读1" -> 1)
    sorted_files = sorted(files, key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else float('inf'))
    return [os.path.join(directory, f) for f in sorted_files]

# **Format time for SRT**
def format_srt_time(seconds):
    millis = int((seconds - int(seconds)) * 1000)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02},{millis:03}"

# **Combine audio files using moviepy and create SRT and TXT files**
def combine_audio_and_subtitles(audio_dir, txt_dir, output_audio_path, output_txt_path, output_srt_path, gap_duration):
    # Get sorted audio and txt files
    audio_files = get_sorted_files(audio_dir, '.mp3') + get_sorted_files(audio_dir, '.wav')  # Support both .mp3 and .wav files
    txt_files = get_sorted_files(txt_dir, '.txt')
    
    if not audio_files:
        print(f"No audio files found in directory: {audio_dir}")
        return
    if not txt_files:
        print(f"No TXT files found in directory: {txt_dir}")
        return

    # Initialize the current time for subtitle timing
    current_time = 0
    srt_entries = []
    audio_clips = []

    for i, audio_file in enumerate(audio_files):
        try:
            # Process audio file using moviepy
            print(f"Processing audio file: {audio_file}")
            audio_clip = AudioFileClip(audio_file)
            audio_clips.append(audio_clip)

            # Add a silent clip of gap_duration seconds
            if gap_duration > 0:
                silent_clip = AudioFileClip(os.path.join(audio_dir, audio_file)).set_duration(gap_duration).volumex(0)
                audio_clips.append(silent_clip)

            # Process corresponding TXT file
            if i < len(txt_files):
                with open(txt_files[i], 'r', encoding='utf-8') as txt_file:
                    txt_content = txt_file.read().strip()

                    # Create SRT entry
                    start_time = format_srt_time(current_time)
                    end_time = format_srt_time(current_time + audio_clip.duration)
                    srt_entries.append(f"{start_time} --> {end_time}\n{txt_content}\n")

            # Update current time considering the gap
            current_time += audio_clip.duration + gap_duration

        except Exception as e:
            print(f"Error processing file {audio_file}: {e}")
            continue

    # Concatenate all audio clips
    try:
        final_audio = concatenate_audioclips(audio_clips)
        # Export final audio to MP3
        print(f"Exporting final audio to: {output_audio_path}")
        final_audio.write_audiofile(output_audio_path)
    except Exception as e:
        print(f"Error exporting audio to {output_audio_path}: {e}")
        return

    # Combine all SRT entries into one and save as both SRT and TXT files
    try:
        print(f"Exporting final SRT to: {output_srt_path}")
        with open(output_srt_path, 'w', encoding='utf-8') as output_srt:
            for entry in srt_entries:
                output_srt.write(entry + "\n")

        # Also save the SRT content to a TXT file
        print(f"Exporting final TXT to: {output_txt_path}")
        with open(output_txt_path, 'w', encoding='utf-8') as output_txt:
            for entry in srt_entries:
                output_txt.write(entry + "\n")
    except Exception as e:
        print(f"Error writing SRT or TXT files: {e}")
        return

    print(f"Final MP3 audio saved to: {output_audio_path}")
    print(f"Combined SRT file saved to: {output_srt_path}")
    print(f"Combined TXT file saved to: {output_txt_path}")

# **Main function to run**
def run_node(node):
    audio_dir = node['Inputs'][2]['Context']  # Audio files directory
    txt_dir = node['Inputs'][3]['Context']  # Subtitle (txt) files directory
    save_path = node['Inputs'][0]['Context']  # Output directory
    save_name = node['Inputs'][1]['Context']  # Output filename without extension
    gap_duration = 0  # Gap duration between audio files in seconds

    # Ensure save_path exists
    if not os.path.exists(save_path):
        print(f"Output directory does not exist: {save_path}")
        return

    # Output file paths
    output_audio_path = os.path.join(save_path, save_name + ".mp3")
    output_txt_path = os.path.join(save_path, save_name + ".txt")
    output_srt_path = os.path.join(save_path, save_name + ".srt")

    # Combine audio and generate SRT and TXT files
    combine_audio_and_subtitles(audio_dir, txt_dir, output_audio_path, output_txt_path, output_srt_path, gap_duration)

    # Return result
    result = f"Combined audio saved to: {output_audio_path}, Combined SRT file saved to: {output_srt_path}, Combined TXT file saved to: {output_txt_path}"
    node['Outputs'][0]['Context'] = result
    node['Outputs'][1]['Context'] = output_audio_path
    return node['Outputs']
