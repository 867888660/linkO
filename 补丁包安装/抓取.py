import os
import shutil

# 获取当前脚本文件的路径
current_script_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_script_path)

# 回退一级为基础目录
base_dir = os.path.dirname(current_dir)

# 文件相对路径列表（相对于基础目录）
file_paths = [
    r"templates\appindex.html",
    r"templates\index.html",
    r"templates\Message.html",
    r"templates\workTeam.html",
    r"static\Message.css",
    r"static\Message.js",
    r"static\scripts.js",
    r"static\styles.css",
    r"static\WorkTeam.js",
    r"static\WorkTeam.css",
    r"static\Script\index.css",
    r"static\Script\index.js",
    r"启动程序.py",
    r"app.py"
]

# 目标保存目录
target_base_dir = os.path.join(current_dir, "files")

# 开始复制文件
for relative_path in file_paths:
    source_file = os.path.join(base_dir, relative_path)
    target_file = os.path.join(target_base_dir, relative_path)

    # 创建目标目录（如果不存在）
    os.makedirs(os.path.dirname(target_file), exist_ok=True)

    # 复制文件
    try:
        shutil.copy2(source_file, target_file)
        print(f"✅ 复制成功: {relative_path}")
    except FileNotFoundError:
        print(f"❌ 未找到文件: {relative_path}")
    except Exception as e:
        print(f"⚠️ 复制失败: {relative_path}，错误信息: {e}")
