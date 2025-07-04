import os
import pandas as pd
from tabulate import tabulate
import logging
import numpy as np
import json
import cv2
from PIL import Image, ImageDraw

# **Function definition**

# **Define the number of outputs and inputs**
OutPutNum = 1
InPutNum = 2
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly**
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个图像边界框标注组件，用于在图像上绘制文本检测结果的边界框和对应文字。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n该组件接收图片路径和包含文字位置信息的JSON数据，解析JSON中的prism_wordsInfo数组获取文字的多边形边界框坐标和内容，然后使用OpenCV和PIL库在图像上绘制红色边界框和绿色文字标注，最终保存为带有\"_annotated\"后缀的标注图片。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: PicPath\\n    type: file\\n    required: true\\n    description: 输入图片文件路径\\n  - name: Bounding\\n    type: string\\n    required: true\\n    description: 包含文字位置和内容信息的JSON格式数据\\noutputs:\\n  - name: Result\\n    type: string\\n    description: 标注后的图片保存路径\\n```\\n\\n运行逻辑（用 - 列表描写详细流程）\\n- 接收输入的图片路径和边界框JSON数据\\n- 规范化文件路径，处理双反斜杠等路径问题\\n- 检查图片文件是否存在，如不存在则尝试查找大小写不同的同名文件\\n- 解析输入的JSON字符串，提取prism_wordsInfo数组中的文字信息\\n- 尝试使用OpenCV读取图片，失败则使用PIL读取\\n- 如果图片读取失败，根据JSON中的尺寸信息创建空白画布\\n- 将OpenCV图像转换为PIL格式以支持中文字体渲染\\n- 尝试加载支持中文的系统字体（SimHei、SimSun、Microsoft YaHei等）\\n- 遍历每个文字信息，提取多边形边界框坐标点\\n- 使用OpenCV在图像上绘制红色多边形边界框\\n- 使用PIL在边界框上方绘制绿色文字内容\\n- 生成输出文件名，在原文件名后添加\"_annotated\"后缀\\n- 尝试使用OpenCV保存图片，失败则使用PIL保存\\n- 验证输出文件是否成功创建且大小不为零\\n- 返回标注后图片的完整路径'
# ... existing code ...

# **Assign properties to Inputs**
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String_FilePath'

Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'PicPath'
Inputs[0]['Description'] = '输入图片文件路径'
Inputs[1]['name'] = 'Bounding'
Inputs[1]['Kind'] = 'String'
Inputs[1]['Description'] = '边界框JSON数据'
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'
Outputs[0]['Description'] = '标注后的图片路径'
# **Assign properties to Inputs**

# **Function definition**
def run_node(node):
    file_path = node['Inputs'][0]['Context']
    bounding_json = node['Inputs'][1]['Context']

    # Fix path issues with double backslashes
    file_path = file_path.replace('\\\\', '\\')
    
    # Normalize path to handle any other path issues
    file_path = os.path.normpath(file_path)
    
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            # Try to find the file by checking if there are encoding issues or case sensitivity issues
            dir_name = os.path.dirname(file_path)
            base_name = os.path.basename(file_path)
            
            if os.path.exists(dir_name):
                # Check if the file exists with a different case
                for file in os.listdir(dir_name):
                    if file.lower() == base_name.lower():
                        file_path = os.path.join(dir_name, file)
                        break
            
            # If still not found
            if not os.path.exists(file_path):
                error_message = f"Image file not found: {file_path}"
                logging.error(error_message)
                Outputs[0]['Context'] = error_message
                return Outputs
        
        # Parse bounding box JSON
        try:
            # Find JSON content in the input string
            if '{' in bounding_json and '}' in bounding_json:
                # Extract the entire JSON object
                json_content = bounding_json
                # Try to parse as is first
                try:
                    data = json.loads(json_content)
                except:
                    # If that fails, try to extract just the JSON part
                    start_idx = bounding_json.find('{')
                    end_idx = bounding_json.rfind('}') + 1
                    if start_idx >= 0 and end_idx > start_idx:
                        json_content = bounding_json[start_idx:end_idx]
                        data = json.loads(json_content)
            else:
                data = json.loads(bounding_json)
                
            # Extract the wordsInfo array which contains character positions
            if 'prism_wordsInfo' in data:
                words_info = data['prism_wordsInfo']
            else:
                words_info = []
                error_message = "No 'prism_wordsInfo' found in JSON"
                logging.warning(error_message)
                
        except json.JSONDecodeError as e:
            error_message = f"Invalid JSON format: {str(e)}"
            logging.error(error_message)
            Outputs[0]['Context'] = error_message
            return Outputs
        
        # Read the image - try multiple methods
        image = None
        
        # Method 1: OpenCV
        try:
            image = cv2.imread(file_path)
        except Exception as e:
            logging.warning(f"OpenCV failed to read image: {str(e)}")
        
        # Method 2: PIL if OpenCV failed
        if image is None:
            try:
                pil_image = Image.open(file_path)
                image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            except Exception as e:
                logging.warning(f"PIL failed to read image: {str(e)}")
        
        # If both methods failed, create a blank image based on dimensions in JSON
        if image is None:
            try:
                if 'height' in data and 'width' in data:
                    height = data['height']
                    width = data['width']
                    image = np.ones((height, width, 3), dtype=np.uint8) * 255
                    logging.warning(f"Created blank image with dimensions {width}x{height}")
                else:
                    # Default size if no dimensions provided
                    image = np.ones((1500, 1100, 3), dtype=np.uint8) * 255
                    logging.warning("Created default blank image")
            except Exception as e:
                error_message = f"Failed to create image: {str(e)}"
                logging.error(error_message)
                Outputs[0]['Context'] = error_message
                return Outputs
        
        # Convert OpenCV image to PIL for text rendering
        pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)
        
        # Try to load a font that supports Chinese characters
        try:
            # Try to find a system font that supports Chinese
            # On Windows, you might use something like "SimSun" or "Microsoft YaHei"
            # On Linux, you might use something like "WenQuanYi Micro Hei"
            font_size = 20
            try:
                from PIL import ImageFont
                font = ImageFont.truetype("simhei.ttf", font_size)  # Try SimHei first
            except:
                try:
                    font = ImageFont.truetype("simsun.ttc", font_size)  # Try SimSun next
                except:
                    try:
                        font = ImageFont.truetype("msyh.ttc", font_size)  # Try Microsoft YaHei next
                    except:
                        try:
                            font = ImageFont.truetype("wqy-microhei.ttc", font_size)  # Try WenQuanYi Micro Hei
                        except:
                            # If all else fails, use default font
                            font = ImageFont.load_default()
                            logging.warning("Using default font, Chinese characters may not display correctly")
        except Exception as e:
            logging.warning(f"Failed to load font: {str(e)}, using default")
            font = None
        
        # Draw bounding boxes and text for each character
        for word_info in words_info:
            if 'pos' in word_info and 'word' in word_info:
                # Get the polygon points for the bounding box
                polygon = word_info['pos']
                
                # Extract coordinates from the polygon points
                points = []
                for point in polygon:
                    if isinstance(point, dict) and 'x' in point and 'y' in point:
                        points.append([int(point['x']), int(point['y'])])
                    elif isinstance(point, list) and len(point) >= 2:
                        points.append([int(point[0]), int(point[1])])
                
                if not points:
                    continue
                
                # Convert points to numpy array for OpenCV
                np_points = np.array(points, np.int32)
                np_points = np_points.reshape((-1, 1, 2))
                
                # Draw red bounding box using OpenCV
                cv2_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
                cv2.polylines(cv2_image, [np_points], True, (0, 0, 255), 2)
                pil_image = Image.fromarray(cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB))
                draw = ImageDraw.Draw(pil_image)
                
                # Get the text and position
                text = word_info['word']
                
                # Calculate text position (use the top-left corner of the bounding box)
                x_values = [p[0] for p in points]
                y_values = [p[1] for p in points]
                x = min(x_values) if x_values else 0
                y = min(y_values) if y_values else 0
                
                # Draw green text using PIL (which handles Chinese characters correctly)
                draw.text((x, y - 30), text, fill=(0, 255, 0), font=font)
        
        # Convert back to OpenCV format for saving
        image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        
        # Generate output filename
        file_name = os.path.basename(file_path)
        file_dir = os.path.dirname(file_path)
        name, ext = os.path.splitext(file_name)
        output_path = os.path.join(file_dir, f"{name}_annotated{ext}")
        
        # If the input is not an image file, save as PNG
        if not ext or ext.lower() not in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
            output_path = os.path.join(file_dir, f"{name}_annotated.png")
        
        # Ensure the output directory exists
        os.makedirs(file_dir, exist_ok=True)
        
        # Save the annotated image
        save_success = False
        
        # Method 1: OpenCV
        try:
            save_result = cv2.imwrite(output_path, image)
            if save_result:
                save_success = True
            else:
                logging.warning(f"OpenCV imwrite returned False for {output_path}")
        except Exception as e:
            logging.warning(f"OpenCV failed to save image: {str(e)}")
        
        # Method 2: PIL if OpenCV failed
        if not save_success:
            try:
                pil_image.save(output_path)
                save_success = True
            except Exception as e:
                logging.warning(f"PIL failed to save image: {str(e)}")
        
        # Verify the file was created
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            error_message = f"Failed to save image to {output_path}"
            logging.error(error_message)
            Outputs[0]['Context'] = error_message
            return Outputs
        
        # Return the path to the annotated image
        Result = output_path
        logging.info(f"Successfully saved annotated image to: {output_path}")
        
    except Exception as e:
        error_message = f"Error processing image: {str(e)}"
        logging.error(error_message)
        Result = error_message
    
    Outputs[0]['Context'] = Result
    return Outputs
