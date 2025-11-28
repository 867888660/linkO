from multiprocessing import Process
import subprocess
import time
import webbrowser

def run_app(port):
    subprocess.run(["python", "app.py", str(port)])

if __name__ == '__main__':
    ports = [5000, 5001]  # 定义要使用的端口
    processes = []

    for port in ports:
        p = Process(target=run_app, args=(port,))
        p.start()
        processes.append(p)
        time.sleep(1)  # 确保每个进程有时间启动

    # 打开默认浏览器中的第一个实例
    webbrowser.open(f'http://127.0.0.1:{ports[0]}')

    for p in processes:
        p.join()
