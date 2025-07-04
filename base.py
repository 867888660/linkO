import base64

def image_to_base64(image_path):
    # 打开图片文件并读取内容
    with open(image_path, "rb") as image_file:
        # 将图片内容转换为Base64编码
        encoded_image = base64.b64encode(image_file.read())
        # 将Base64编码的bytes类型转换为字符串，并解码为utf-8格式
        base64_image = encoded_image.decode('utf-8')
    return base64_image

# 指定你的图片文件路径
image_path = 'E:\实用工具\下载\Flux Workflow + Upscalers.png'
# 调用函数进行转换
base64_image = image_to_base64(image_path)
print(base64_image)