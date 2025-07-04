import os
import shutil

# 获取当前脚本路径
current_script_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_script_path)

# 获取基础路径（上一级）
base_dir = os.path.dirname(current_dir)

# 获取 files 文件夹路径
files_dir = os.path.join(current_dir, "files")

# 遍历 files 目录中的所有文件
for root, dirs, files in os.walk(files_dir):
    for file in files:
        # 相对路径：从 files 文件夹开始
        rel_path = os.path.relpath(os.path.join(root, file), files_dir)

        # 源文件路径（在 files 文件夹中）
        src_file = os.path.join(root, file)

        # 目标路径（在基础目录中）
        target_file = os.path.join(base_dir, rel_path)

        # 确保目标目录存在
        os.makedirs(os.path.dirname(target_file), exist_ok=True)

        # 执行替换
        try:
            shutil.copy2(src_file, target_file)
            print(f"✅ 替换成功: {rel_path}")
        except Exception as e:
            print(f"⚠️ 替换失败: {rel_path}，错误信息: {e}")
