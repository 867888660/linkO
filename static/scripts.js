document.addEventListener('DOMContentLoaded', async () => {
    await loadHistoryProjects();
    await loadWorkTeamProjects();
});
document.getElementById('startNewInstanceBtn').addEventListener('click', async () => {
    await startNewInstance('New project');
});
document.getElementById('startWorkTeam').addEventListener('click', async () => {
    await startWorkTeam('New project');
});
async function loadHistoryProjects() {
    const res = await fetch('/get-history-projects');
    const projects = await res.json();

    if (projects.error) {
        console.error('Error loading history projects:', projects.error);
        return;
    }

    const projectList = document.getElementById('projectList');
    projectList.innerHTML = '';

    const folders = {};

    projects.forEach(project => {
        if (project.type === 'folder') {
            const li = document.createElement('li');
            li.textContent = project.name;

            const toggleBtn = document.createElement('button');
            toggleBtn.textContent = '▼'; // 默认折叠图标
            toggleBtn.onclick = () => {
                const filesList = folders[project.name];
                if (filesList.style.display === 'none') {
                    filesList.style.display = 'block';
                    toggleBtn.textContent = '▲'; // 展开图标
                } else {
                    filesList.style.display = 'none';
                    toggleBtn.textContent = '▼'; // 折叠图标
                }
            };

            const filesList = document.createElement('ul');
            filesList.style.display = 'none'; // 初始隐藏
            folders[project.name] = filesList;

            li.prepend(toggleBtn);
            projectList.appendChild(li);
            projectList.appendChild(filesList);
        } else if (project.type === 'file') {
            const li = document.createElement('li');
            li.style.paddingLeft = '20px'; // 右移
            li.textContent = project.name;

            const deleteBtn = document.createElement('span');
            deleteBtn.textContent = '✖';
            deleteBtn.style.marginLeft = '10px';
            deleteBtn.style.cursor = 'pointer';
            deleteBtn.style.display = 'none'; // 初始隐藏
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm(`Are you sure you want to delete the project "${project.name}"?`)) {
                    deleteProject(project.name,project.folder);
                }
            });
            li.addEventListener('click', () => startNewInstance(project));
            li.addEventListener('mouseover', () => {
                deleteBtn.style.display = 'inline';
            });

            li.addEventListener('mouseout', () => {
                deleteBtn.style.display = 'none';
            });

            li.appendChild(deleteBtn);
            folders[project.folder].appendChild(li);
        }
    });
}

async function loadWorkTeamProjects() {
    const res = await fetch('/get-workteam-projects');  // 需要在后端创建一个新路由返回 WorkTeam 文件夹内容
    const projects = await res.json();

    if (projects.error) {
        console.error('Error loading WorkTeam projects:', projects.error);
        return;
    }

    const workTeamProjectList = document.getElementById('workTeamProjectList');
    workTeamProjectList.innerHTML = '';

    projects.forEach(project => {
        const li = document.createElement('li');
        li.style.paddingLeft = '20px';
        li.textContent = project;

        const deleteBtn = document.createElement('span');
        deleteBtn.textContent = '✖';
        deleteBtn.style.marginLeft = '10px';
        deleteBtn.style.cursor = 'pointer';
        deleteBtn.style.display = 'none';

        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (confirm(`Are you sure you want to delete the project "${project}"?`)) {
                deleteProject(project,'WorkTeam');
            }
        });

        li.addEventListener('mouseover', () => {
            deleteBtn.style.display = 'inline';
        });

        li.addEventListener('mouseout', () => {
            deleteBtn.style.display = 'none';
        });

        li.addEventListener('click', () => startWorkTeam(project));

        li.appendChild(deleteBtn);
        workTeamProjectList.appendChild(li);
    });
}
async function deleteProject(project, filePath) {
    try {
        const res = await fetch('/delete-project', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                project: project,
                filePath: filePath
            }),
        });
        const result = await res.json();

        if (result.success) {
            document.getElementById('output').value += `Project "${project}" deleted successfully.\n`;
            loadHistoryProjects(); // Refresh the project list
        } else {
            document.getElementById('output').value += `Error deleting project "${project}": ${result.error}\n`;
        }
    } catch (error) {
        console.error('Error deleting project:', error);
        document.getElementById('output').value += `Error deleting project "${project}": ${error}\n`;
    }
    await loadHistoryProjects();
    await loadWorkTeamProjects();
}

async function startNewInstance(projectName) {
    console.log('Starting new instance for project:', projectName);
    try {
        const res = await fetch('/start-new-instance', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });

        if (!res.ok) {
            const errorText = await res.text();
            console.error('Error:', errorText);
            document.getElementById('output').value += 'Error starting instance: ' + errorText + '\n';
            return;
        }

        const data = await res.json();
        console.log('Response data:', data);
        document.getElementById('output').value += data.status + '\n';

        const portMatch = data.status.match(/port (\d+)/);
        if (portMatch) {
            const port = portMatch[1];
            await loadProjectToInstance(port, projectName.name,projectName.folder);
            window.open(`http://127.0.0.1:${port}`, '_blank');
        } else {
            console.error('No port found in response:', data.status);
            document.getElementById('output').value += 'No port found in response: ' + data.status + '\n';
        }
    } catch (error) {
        console.error('Fetch error:', error);
        document.getElementById('output').value += 'Fetch error: ' + error.message + '\n';
    }
}
async function startWorkTeam(projectName) {
    console.log('Starting WorkTeam for project:', projectName);
    try {
        const res = await fetch('/start-new-WorkTeam', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({projectName})
        });
        
        if (!res.ok) {
            const errorText = await res.text();
            console.error('Error:', errorText);
            document.getElementById('output').value += 'Error starting instance: ' + errorText + '\n';
            return;
        }

        const data = await res.json();
        console.log('Response data:', data);
        document.getElementById('output').value += data.status + '\n';

        const portMatch = data.status.match(/port (\d+)/);
        if (portMatch) {
            const port = portMatch[1];
            await loadProjectToInstance(port, projectName,'WorkTeam');
            window.open(`http://127.0.0.1:${port}`, '_blank');
        } else {
            console.error('No port found in response:', data.status);
            document.getElementById('output').value += 'No port found in response: ' + data.status + '\n';
        }
    } catch (error) {
        console.error('Fetch error:', error);
        document.getElementById('output').value += 'Fetch error: ' + error.message + '\n';
    }
}
// 前端代码
async function loadProjectToInstance(port, projectName, projectPath) {
    // 显示加载状态
    document.getElementById('output').value += `正在加载项目 ${projectName}...
`;
    
    try {
        console.log('Loading project to instance on port:', port, 'projectName:', projectName);
        
        const res = await fetch(
            `/load-project?port=${port}&name=${encodeURIComponent(projectName)}&path=${encodeURIComponent(projectPath)}`,
            {
                method: 'GET',
                headers: {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            }
        );
        if (!res.ok) {
            throw new Error(`HTTP error! status: ${res.status}`);
        }
        const data = await res.json();
        console.log('Response data:', data);
        if (data.error) {
            throw new Error(data.error);
        }
        document.getElementById('output').value += `✓ 项目 ${projectName} 已成功加载到端口 ${port}
`;
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('output').value += `
❌ 加载失败: ${error.message}
请检查:
1. 实例是否正在运行
2. 端口 ${port} 是否正确
3. 网络连接是否正常
`;
    }
}

