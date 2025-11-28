document.addEventListener('DOMContentLoaded', async () => {
    await loadHistoryProjects();
    await loadWorkTeamProjects();
    
    // 打开 Control Room
    document.getElementById('openControlRoom').addEventListener('click', () => {
        window.open('/control-room', '_blank');
    });
    
    // 设置菜单
    initSettingsMenu();
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
    
    let projectCount = 0;

    const folders = {};

    projects.forEach(project => {
        if (project.type === 'file') {
            projectCount++;
        }
        
        if (project.type === 'folder') {
            const li = document.createElement('li');
            li.className = 'folder-item';
            
            li.innerHTML = `
                <div class="project-item">
                    <div class="project-info">
                        <div class="project-name">
                            <i class="fas fa-folder"></i>
                            ${project.name}
                        </div>
                    </div>
                </div>
            `;
            
            const toggleBtn = document.createElement('button');
            toggleBtn.innerHTML = '<i class="fas fa-chevron-down"></i>';
            toggleBtn.className = 'folder-toggle';
            toggleBtn.onclick = () => {
                const filesList = folders[project.name];
                if (filesList.style.display === 'none') {
                    filesList.style.display = 'block';
                    toggleBtn.innerHTML = '<i class="fas fa-chevron-up"></i>';
                } else {
                    filesList.style.display = 'none';
                    toggleBtn.innerHTML = '<i class="fas fa-chevron-down"></i>';
                }
            };

            const filesList = document.createElement('ul');
            filesList.style.display = 'none';
            filesList.className = 'subfolder-list';
            folders[project.name] = filesList;

            li.querySelector('.project-item').prepend(toggleBtn);
            projectList.appendChild(li);
            projectList.appendChild(filesList);
        } else if (project.type === 'file') {
            const li = document.createElement('li');
            li.className = 'file-item';
            
            li.innerHTML = `
                <div class="project-item">
                    <div class="project-info">
                        <div class="project-name">
                            <i class="fas fa-file-code"></i>
                            ${project.name}
                        </div>
                        <div class="project-path">${project.folder}</div>
                    </div>
                    <div class="project-actions">
                        <div class="action-icon action-load" title="加载项目">
                            <i class="fas fa-play"></i>
                        </div>
                        <div class="action-icon action-delete" title="删除项目">
                            <i class="fas fa-trash"></i>
                        </div>
                    </div>
                </div>
            `;
            
            li.querySelector('.action-load').addEventListener('click', (e) => {
                e.stopPropagation();
                startNewInstance(project);
            });
            
            li.querySelector('.action-delete').addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm(`确定要删除项目 "${project.name}" 吗？`)) {
                    deleteProject(project.name, project.folder);
                }
            });

            if (folders[project.folder]) {
                folders[project.folder].appendChild(li);
            } else {
                projectList.appendChild(li);
            }
        }
    });
    
    // 更新统计数字
    document.getElementById('historyCount').textContent = projectCount;
    
    if (projectCount === 0) {
        projectList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-folder-open"></i>
                <p>暂无历史项目</p>
            </div>
        `;
    }
}

async function loadWorkTeamProjects() {
    const res = await fetch('/get-workteam-projects');
    const projects = await res.json();

    if (projects.error) {
        console.error('Error loading WorkTeam projects:', projects.error);
        return;
    }

    const workTeamProjectList = document.getElementById('workTeamProjectList');
    workTeamProjectList.innerHTML = '';
    
    // 更新统计数字
    document.getElementById('workteamCount').textContent = projects.length;

    if (projects.length === 0) {
        workTeamProjectList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-users-slash"></i>
                <p>暂无 WorkTeam 项目</p>
            </div>
        `;
        return;
    }

    projects.forEach(project => {
        const li = document.createElement('li');
        li.className = 'file-item';
        
        li.innerHTML = `
            <div class="project-item">
                <div class="project-info">
                    <div class="project-name">
                        <i class="fas fa-users"></i>
                        ${project}
                    </div>
                    <div class="project-path">WorkTeam</div>
                </div>
                <div class="project-actions">
                    <div class="action-icon action-load" title="启动 WorkTeam">
                        <i class="fas fa-play"></i>
                    </div>
                    <div class="action-icon action-delete" title="删除项目">
                        <i class="fas fa-trash"></i>
                    </div>
                </div>
            </div>
        `;
        
        li.querySelector('.action-load').addEventListener('click', (e) => {
            e.stopPropagation();
            startWorkTeam(project);
        });
        
        li.querySelector('.action-delete').addEventListener('click', (e) => {
            e.stopPropagation();
            if (confirm(`确定要删除项目 "${project}" 吗？`)) {
                deleteProject(project, 'WorkTeam');
            }
        });

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

// ==================== 设置菜单功能 ====================
let secretsConfig = { secrets: [], llmMappings: {} };
let llmNodes = [];
let selectedSecretIndex = -1;
let settingsTabsInitialized = false;

async function initSettingsMenu() {
    const settingsBtn = document.getElementById('settingsBtn');
    const settingsModal = document.getElementById('settingsModal');
    const settingsCloseBtn = document.getElementById('settingsCloseBtn');
    const settingsCancelBtn = document.getElementById('settingsCancelBtn');
    const settingsApplyBtn = document.getElementById('settingsApplyBtn');
    const settingsAddBtn = document.getElementById('settingsAddBtn');
    const settingsDeleteBtn = document.getElementById('settingsDeleteBtn');
    
    settingsBtn.addEventListener('click', () => {
        settingsModal.style.display = 'flex';
        document.body.classList.add('modal-open');
        loadSecretsConfig();
        initSettingsTabs();
    });
    
    settingsCloseBtn.addEventListener('click', () => {
        settingsModal.style.display = 'none';
        document.body.classList.remove('modal-open');
    });
    
    settingsCancelBtn.addEventListener('click', () => {
        settingsModal.style.display = 'none';
        document.body.classList.remove('modal-open');
    });
    
    settingsModal.addEventListener('click', (e) => {
        if (e.target === settingsModal) {
            settingsModal.style.display = 'none';
            document.body.classList.remove('modal-open');
        }
    });
    
    settingsAddBtn.addEventListener('click', () => {
        addSecretItem();
    });
    
    settingsDeleteBtn.addEventListener('click', () => {
        if (selectedSecretIndex >= 0) {
            deleteSecretItem(selectedSecretIndex);
        }
    });
    
    settingsApplyBtn.addEventListener('click', async () => {
        await saveSecretsConfig();
        settingsModal.style.display = 'none';
        document.body.classList.remove('modal-open');
    });
}

async function loadSecretsConfig() {
    try {
        const res = await fetch('/api/secrets/get-config');
        const data = await res.json();
        secretsConfig = {
            secrets: data.secrets || [],
            llmMappings: data.llmMappings || {}
        };
        
        const llmRes = await fetch('/api/secrets/get-llm-nodes');
        const llmData = await llmRes.json();
        llmNodes = llmData.nodes || [];
        
        renderSecretsList();
        renderLlmKeyList();
    } catch (error) {
        console.error('加载配置失败:', error);
        secretsConfig = { secrets: [], llmMappings: {} };
        llmNodes = [];
        renderSecretsList();
        renderLlmKeyList();
    }
}

function renderSecretsList() {
    const secretsList = document.getElementById('secretsList');
    secretsList.innerHTML = '';
    
    if (secretsConfig.secrets.length === 0) {
        secretsList.innerHTML = '<div style="text-align: center; color: #888; padding: 40px;">暂无密钥，点击左上角"+"添加</div>';
        return;
    }
    
    secretsConfig.secrets.forEach((secret, index) => {
        const secretItem = document.createElement('div');
        secretItem.className = 'secret-item';
        secretItem.innerHTML = `
            <div class="secret-item-header">
                <div class="secret-item-title">${secret.name || '未命名密钥'}</div>
                <button class="secret-item-delete" onclick="deleteSecretItem(${index})">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
            <div class="secret-form-group">
                <label>密钥名称</label>
                <input type="text" class="secret-name-input" value="${secret.name || ''}" 
                       data-old-name="${secret.name || ''}"
                       onchange="updateSecretName(${index}, this)">
            </div>
            <div class="secret-form-group">
                <label>密钥项目</label>
                <input type="${secret.visible ? 'text' : 'password'}" class="secret-value-input" 
                       value="${secret.value || ''}" 
                       onchange="updateSecret(${index}, 'value', this.value)">
            </div>
            <div class="secret-form-group">
                <label>是否可见</label>
                <div class="secret-visibility-toggle">
                    <input type="checkbox" class="secret-visible-checkbox" 
                           ${secret.visible ? 'checked' : ''} 
                           onchange="toggleSecretVisibility(${index}, this.checked)">
                    <span>显示密钥内容</span>
                </div>
            </div>
        `;
        secretsList.appendChild(secretItem);
    });
}

function addSecretItem() {
    if (!secretsConfig.secrets) {
        secretsConfig.secrets = [];
    }
    secretsConfig.secrets.push({
        name: '',
        value: '',
        visible: false
    });
    selectedSecretIndex = secretsConfig.secrets.length - 1;
    renderSecretsList();
    renderLlmKeyList();
}

function deleteSecretItem(index) {
    if (confirm('确定要删除这个密钥吗？')) {
        secretsConfig.secrets.splice(index, 1);
        if (secretsConfig.llmMappings) {
            Object.keys(secretsConfig.llmMappings).forEach(node => {
                if (secretsConfig.llmMappings[node] === undefined) return;
                const secretName = secretsConfig.llmMappings[node];
                const exists = secretsConfig.secrets.some(sec => sec.name === secretName);
                if (!exists) {
                    delete secretsConfig.llmMappings[node];
                }
            });
        }
        selectedSecretIndex = -1;
        renderSecretsList();
        renderLlmKeyList();
    }
}

function updateSecret(index, field, value) {
    if (secretsConfig.secrets[index]) {
        secretsConfig.secrets[index][field] = value;
    }
}

function updateSecretName(index, input) {
    const oldName = input.dataset.oldName || '';
    const newName = input.value;
    if (secretsConfig.secrets[index]) {
        secretsConfig.secrets[index].name = newName;
        if (oldName !== newName) {
            if (!secretsConfig.llmMappings) {
                secretsConfig.llmMappings = {};
            }
            Object.keys(secretsConfig.llmMappings).forEach(node => {
                if (secretsConfig.llmMappings[node] === oldName) {
                    secretsConfig.llmMappings[node] = newName;
                }
            });
            input.dataset.oldName = newName;
    renderSecretsList();
    renderLlmKeyList();
        }
    }
}

function toggleSecretVisibility(index, visible) {
    if (secretsConfig.secrets[index]) {
        secretsConfig.secrets[index].visible = visible;
        const valueInput = document.querySelectorAll('.secret-value-input')[index];
        if (valueInput) {
            valueInput.type = visible ? 'text' : 'password';
        }
    }
}

async function saveSecretsConfig() {
    try {
        const res = await fetch('/api/secrets/save-config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(secretsConfig)
        });
        
        if (res.ok) {
            alert('配置已保存');
        } else {
            alert('保存失败');
        }
    } catch (error) {
        console.error('保存配置失败:', error);
        alert('保存失败: ' + error.message);
    }
}

function initSettingsTabs() {
    if (settingsTabsInitialized) return;
    const menuItems = document.querySelectorAll('.settings-menu-item');
    const sections = {
        secrets: document.getElementById('secretsSection'),
        'llm-key': document.getElementById('llmKeySection')
    };
    
    menuItems.forEach(item => {
        item.addEventListener('click', () => {
            const target = item.dataset.section;
            menuItems.forEach(m => m.classList.remove('active'));
            item.classList.add('active');
            Object.keys(sections).forEach(key => {
                if (sections[key]) {
                    sections[key].style.display = key === target ? 'block' : 'none';
                }
            });
        });
    });
    settingsTabsInitialized = true;
}

function renderLlmKeyList() {
    const llmKeyList = document.getElementById('llmKeyList');
    if (!llmKeyList) return;
    
    llmKeyList.innerHTML = '';
    
    if (!llmNodes.length) {
        llmKeyList.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">未检测到 LLM 组件</div>';
        return;
    }
    
    const secretOptions = secretsConfig.secrets || [];
    
    llmNodes.forEach(node => {
        const item = document.createElement('div');
        item.className = 'llm-key-item';
        const currentSecret = secretsConfig.llmMappings?.[node] || '';
        
        const info = document.createElement('div');
        info.className = 'llm-key-info';
        info.innerHTML = `
            <div class="llm-key-name">${node}</div>
            <div class="llm-key-desc">为该 LLM 组件选择默认密钥</div>
        `;
        
        const select = document.createElement('select');
        select.className = 'secret-llm-select llm-key-select';
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = '-- 选择密钥 --';
        select.appendChild(defaultOption);
        secretOptions.forEach(sec => {
            const opt = document.createElement('option');
            opt.value = sec.name || '';
            opt.textContent = sec.name || '未命名密钥';
            select.appendChild(opt);
        });
        select.value = currentSecret || '';
        select.addEventListener('change', () => updateLlmMapping(node, select.value));
        
        item.appendChild(info);
        item.appendChild(select);
        llmKeyList.appendChild(item);
    });
}

function updateLlmMapping(node, secretName) {
    if (!secretsConfig.llmMappings) {
        secretsConfig.llmMappings = {};
    }
    if (!secretName) {
        delete secretsConfig.llmMappings[node];
    } else {
        secretsConfig.llmMappings[node] = secretName;
    }
}

