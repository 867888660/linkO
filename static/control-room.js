// ==================== Control Room - 实例监控面板 ====================

const HUB_PORT = window.location.port || 3001;
const HUB_URL = `http://127.0.0.1:${HUB_PORT}`;

let instances = {};
// 记录每个端口对应的当前工作流ID，便于暂停/恢复/结束运行
let appWorkflowIds = {};
// 记录每个端口当前的工作流状态（idle/running/paused）
let appWorkflowStates = {};
let refreshInterval = null;

console.log('[DEBUG] Control Room 初始化');
console.log('[DEBUG] 当前页面端口:', window.location.port);
console.log('[DEBUG] HUB_PORT:', HUB_PORT);
console.log('[DEBUG] HUB_URL:', HUB_URL);

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', () => {
    console.log('[DEBUG] DOM 加载完成');
    initEventListeners();
    loadInstances();
    startAutoRefresh();
});

// ==================== 事件监听 ====================
function initEventListeners() {
    document.getElementById('scanBtn').addEventListener('click', scanPorts);
    document.getElementById('newAppBtn').addEventListener('click', createNewApp);
    document.getElementById('newWorkteamBtn').addEventListener('click', createNewWorkteam);
    document.getElementById('refreshBtn').addEventListener('click', () => {
        loadInstances();
        showToast('已刷新实例列表');
    });
}

// ==================== 加载实例列表 ====================
async function loadInstances() {
    console.log('[DEBUG] 开始加载实例列表...');
    console.log('[DEBUG] HUB_URL:', HUB_URL);
    
    try {
        const response = await fetch(`${HUB_URL}/hub/instances`);
        console.log('[DEBUG] Response status:', response.status);
        
        if (!response.ok) {
            console.error('[DEBUG] 请求失败:', response.status, response.statusText);
            throw new Error('获取实例列表失败');
        }
        
        const data = await response.json();
        console.log('[DEBUG] 获取到的数据:', data);
        
        instances = data.instances || {};
        console.log('[DEBUG] 解析后的实例:', instances);
        console.log('[DEBUG] 实例数量:', Object.keys(instances).length);
        
        renderInstances();
        updateStats();
    } catch (error) {
        console.error('[DEBUG] 加载实例失败:', error);
        showToast('加载失败: ' + error.message, 'error');
    }
}

// ==================== 渲染实例卡片 ====================
function renderInstances() {
    const grid = document.getElementById('instancesGrid');
    
    if (Object.keys(instances).length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-inbox"></i>
                <h3>暂无运行的实例</h3>
                <p>点击上方按钮创建新实例或扫描端口</p>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = '';
    
    Object.values(instances).forEach(instance => {
        const card = createInstanceCard(instance);
        grid.appendChild(card);
        
        // 加载详细状态
        loadInstanceDetails(instance.port);
    });
}

// ==================== 创建实例卡片 ====================
function createInstanceCard(instance) {
    const card = document.createElement('div');
    card.className = `instance-card ${instance.type} ${instance.status}`;
    card.id = `instance-${instance.port}`;
    
    if (instance.type === 'app') {
        card.innerHTML = createAppCard(instance);
    } else if (instance.type === 'workteam') {
        card.innerHTML = createWorkteamCard(instance);
    }
    
    return card;
}

// ==================== 创建 App 卡片 ====================
function createAppCard(instance) {
    const moonPhases = ['🌑', '🌒', '🌓', '🌔', '🌕', '🌖', '🌗', '🌘'];
    
    // 处理项目名称：去除 .json 后缀
    let displayName = instance.project_name || 'App Instance';
    if (displayName.endsWith('.json')) {
        displayName = displayName.replace('.json', '');
    }
    
    console.log(`[DEBUG] 创建 App 卡片: port=${instance.port}, 实例状态=${instance.status}, name=${displayName}`);
    
    return `
        <div class="card-header">
            <div class="project-name">
                <i class="fas fa-laptop-code"></i>
                <span>${displayName}</span>
            </div>
            <span class="status-badge stopped">加载中...</span>
        </div>
        
        <div class="card-content">
            <div class="port-display">
                <div class="port-number">${instance.port}</div>
            </div>
            
            <div class="workflow-status">
                <div class="info-row">
                    <span class="info-label">工作流状态</span>
                    <span class="info-value" id="workflow-status-${instance.port}">加载中...</span>
                </div>
                <div class="workflow-indicators" id="workflow-indicators-${instance.port}">
                    <div class="indicator-item">
                        <span class="indicator-bracket">{</span>
                        <span class="passivity-count">0</span>
                        <span class="indicator-bracket">}</span>
                    </div>
                    <div class="indicator-item">
                        <span class="indicator-bracket">[</span>
                        <span class="array-count">0</span>
                        <span class="indicator-bracket">]</span>
                    </div>
                </div>
            </div>
            
            <div class="concurrency-control">
                <div class="concurrency-label">并发数量</div>
                <div class="concurrency-input">
                    <input type="number" id="concurrency-${instance.port}" value="4" min="1" max="20">
                    <button onclick="updateConcurrency(${instance.port})">
                        <i class="fas fa-check"></i>
                    </button>
                </div>
            </div>
            
            <div class="info-row">
                <span class="info-label">启动时间</span>
                <span class="info-value">${formatTime(instance.start_time)}</span>
            </div>
        </div>
        
        <div class="card-actions">
            <button class="action-btn open" onclick="openInstance(${instance.port})">
                <i class="fas fa-external-link-alt"></i> 打开
            </button>
            <button class="action-btn run-toggle" onclick="toggleRunInstance(${instance.port})" id="run-toggle-${instance.port}">
                <i class="fas fa-play"></i> 运行
            </button>
            <button class="action-btn close" onclick="closeInstance(${instance.port})">
                <i class="fas fa-times-circle"></i> 关闭
            </button>
        </div>
    `;
}

// ==================== 创建 WorkTeam 卡片 ====================
function createWorkteamCard(instance) {
    // 处理项目名称：去除 .json 后缀
    let displayName = instance.project_name || 'WorkTeam Instance';
    if (displayName.endsWith('.json')) {
        displayName = displayName.split('.')[0];  // 使用 split 方式，与 WorkTeam.js 保持一致
    }
    
    console.log(`[DEBUG] 创建 WorkTeam 卡片: port=${instance.port}, status=${instance.status}, name=${displayName}`);
    
    return `
        <div class="card-header">
            <div class="project-name">
                <i class="fas fa-users"></i>
                <span>${displayName}</span>
            </div>
            <span class="status-badge ${instance.status}">${getStatusText(instance.status)}</span>
        </div>
        
        <div class="card-content">
            <div class="port-display">
                <div class="port-number">${instance.port}</div>
            </div>
            
            <div class="message-stats">
                <div class="info-row">
                    <span class="info-label">消息统计</span>
                </div>
                <div class="stats-row" id="message-stats-${instance.port}">
                    <div class="stat">
                        <div class="stat-value">-</div>
                        <div class="stat-label">总消息</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">-</div>
                        <div class="stat-label">已读</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">-</div>
                        <div class="stat-label">未读</div>
                    </div>
                </div>
            </div>
            
            <div class="info-row">
                <span class="info-label">启动时间</span>
                <span class="info-value">${formatTime(instance.start_time)}</span>
            </div>
        </div>
        
        <div class="card-actions">
            <button class="action-btn open" onclick="openInstance(${instance.port})">
                <i class="fas fa-external-link-alt"></i> 打开
            </button>
            <button class="action-btn close" onclick="closeInstance(${instance.port})">
                <i class="fas fa-times-circle"></i> 关闭
            </button>
        </div>
    `;
}

// ==================== 加载实例详细信息 ====================
async function loadInstanceDetails(port) {
    console.log('[DEBUG] 加载实例详情:', port);
    
    try {
        const response = await fetch(`${HUB_URL}/hub/instance/${port}/status`);
        console.log(`[DEBUG] 实例 ${port} 状态码:`, response.status);
        
        if (!response.ok) {
            console.warn(`[DEBUG] 实例 ${port} 详情获取失败`);
            return;
        }
        
        const data = await response.json();
        console.log(`[DEBUG] 实例 ${port} 详情数据:`, data);
        
        if (data.type === 'app') {
            console.log(`[DEBUG] 更新 App 实例 ${port}`);
            updateAppDetails(port, data);
        } else if (data.type === 'workteam') {
            console.log(`[DEBUG] 更新 WorkTeam 实例 ${port}`);
            updateWorkteamDetails(port, data);
        }
    } catch (error) {
        console.error(`[DEBUG] 加载实例 ${port} 详细信息失败:`, error);
    }
}

// ==================== 更新 App 详细信息 ====================
function updateAppDetails(port, data) {
    console.log(`[DEBUG] ========== 更新 App ${port} 详情 ==========`);
    console.log(`[DEBUG] workflow_status:`, data.workflow_status);
    
    const workflowStatus = data.workflow_status?.status || 'idle';
    const workflowId = data.workflow_status?.workflow_id || null;
    appWorkflowIds[port] = workflowId;
    appWorkflowStates[port] = workflowStatus;
    console.log(`[DEBUG] 🔥 工作流状态: ${workflowStatus}, workflow_id: ${workflowId}`);
    
    // 更新工作流状态显示
    const statusEl = document.getElementById(`workflow-status-${port}`);
    if (statusEl) {
        const statusText = workflowStatus === 'running' ? '运行中' : '空闲';
        statusEl.textContent = statusText;
        
        // 根据状态设置颜色
        if (workflowStatus === 'running') {
            statusEl.className = 'info-value highlight';
        } else {
            statusEl.className = 'info-value';
        }
        console.log(`[DEBUG] 状态元素已更新: ${statusText}`);
    }
    
    // 🔥 从 queue_data 获取队列数据（而非 graph_data）
    const indicatorsEl = document.getElementById(`workflow-indicators-${port}`);
    if (indicatorsEl) {
        const queueData = data.workflow_status?.queue_data || {};
        const passivityQueue = queueData.passivity_queue || 0;
        const arrayQueue = queueData.array_queue || 0;
        
        console.log(`[DEBUG] 🔥 被动队列: ${passivityQueue}, 数组队列: ${arrayQueue}`);
        
        indicatorsEl.innerHTML = `
            <div class="indicator-item">
                <span class="indicator-bracket">{</span>
                <span class="passivity-count">${passivityQueue}</span>
                <span class="indicator-bracket">}</span>
            </div>
            <div class="indicator-item">
                <span class="indicator-bracket">[</span>
                <span class="array-count">${arrayQueue}</span>
                <span class="indicator-bracket">]</span>
            </div>
        `;
    }
    
    // 🔥 关键：根据工作流状态（而非实例状态）更新卡片
    const card = document.getElementById(`instance-${port}`);
    if (card) {
        // 移除所有状态类
        card.classList.remove('running', 'stopped', 'paused');
        
        // 🔥 根据工作流状态添加类
        if (workflowStatus === 'running') {
            card.classList.add('running');
            // 启动月亮动画
            const projectName = card.querySelector('.project-name span');
            if (projectName && !projectName.querySelector('.moon-animation')) {
                const moonSpan = document.createElement('span');
                moonSpan.className = 'moon-animation';
                moonSpan.textContent = '🌑';
                projectName.insertBefore(moonSpan, projectName.firstChild);
                animateMoon(port);
            }
            console.log(`[DEBUG] 🔥 卡片标记为运行中`);
        } else {
            card.classList.remove('running');
            // 移除月亮动画
            const moonSpan = card.querySelector('.moon-animation');
            if (moonSpan) moonSpan.remove();
            console.log(`[DEBUG] 🔥 卡片标记为空闲`);
        }
        
        // 🔥 更新状态徽章文本（基于工作流状态，不是实例状态！）
        const statusBadge = card.querySelector('.status-badge');
        if (statusBadge) {
            statusBadge.classList.remove('running', 'stopped', 'paused');
            
            if (workflowStatus === 'running') {
                statusBadge.classList.add('running');
                statusBadge.textContent = '运行中';
            } else {
                statusBadge.classList.add('stopped');
                statusBadge.textContent = '空闲';
            }
            console.log(`[DEBUG] 🔥 状态徽章已更新: ${statusBadge.textContent} (基于工作流状态)`);
        }
    }
    
    // 🔥 更新“运行 / 结束运行”按钮文案（只负责文字，不搞复杂逻辑）
    const runToggleBtn = document.getElementById(`run-toggle-${port}`);
    if (runToggleBtn) {
        if (workflowStatus === 'running' || workflowStatus === 'paused') {
            runToggleBtn.innerHTML = '<i class="fas fa-stop"></i> 结束运行';
        } else {
            runToggleBtn.innerHTML = '<i class="fas fa-play"></i> 运行';
        }
    }
    
    console.log(`[DEBUG] ========== App ${port} 更新完成 ==========`);
}

// ==================== 更新 WorkTeam 详细信息 ====================
function updateWorkteamDetails(port, data) {
    const statsEl = document.getElementById(`message-stats-${port}`);
    if (statsEl && data.message_stats) {
        const stats = data.message_stats;
        statsEl.innerHTML = `
            <div class="stat">
                <div class="stat-value">${stats.total || 0}</div>
                <div class="stat-label">总消息</div>
            </div>
            <div class="stat">
                <div class="stat-value">${stats.confirmed || 0}</div>
                <div class="stat-label">已读</div>
            </div>
            <div class="stat">
                <div class="stat-value">${stats.unconfirmed || 0}</div>
                <div class="stat-label">未读</div>
            </div>
        `;
    }
}

// ==================== 月亮动画 ====================
function animateMoon(port) {
    const moonPhases = ['🌑', '🌒', '🌓', '🌔', '🌕', '🌖', '🌗', '🌘'];
    const card = document.getElementById(`instance-${port}`);
    if (!card) return;
    
    const moonEl = card.querySelector('.moon-animation');
    if (!moonEl) return;
    
    let phaseIndex = 0;
    const interval = setInterval(() => {
        if (!document.getElementById(`instance-${port}`)) {
            clearInterval(interval);
            return;
        }
        
        const currentMoonEl = card.querySelector('.moon-animation');
        if (currentMoonEl) {
            currentMoonEl.textContent = moonPhases[phaseIndex];
            phaseIndex = (phaseIndex + 1) % moonPhases.length;
        }
    }, 500);
}

// ==================== 更新统计信息 ====================
function updateStats() {
    const total = Object.keys(instances).length;
    const running = Object.values(instances).filter(i => i.status === 'running').length;
    const appCount = Object.values(instances).filter(i => i.type === 'app').length;
    const workteamCount = Object.values(instances).filter(i => i.type === 'workteam').length;
    
    document.getElementById('totalCount').textContent = total;
    document.getElementById('runningCount').textContent = running;
    document.getElementById('appCount').textContent = appCount;
    document.getElementById('workteamCount').textContent = workteamCount;
}

// ==================== 实例操作 ====================
async function openInstance(port) {
    window.open(`http://127.0.0.1:${port}`, '_blank');
}

// 运行 / 结束运行：尽量贴近前端 runButton 的语义，但不在这里“整花活”
async function toggleRunInstance(port) {
    const status = appWorkflowStates[port] || 'idle';
    try {
        if (status === 'running' || status === 'paused') {
            // 有工作流在跑：结束运行（只停工作流，不关进程）
            const workflowId = appWorkflowIds[port] || null;
            const body = workflowId ? JSON.stringify({ workflow_id: workflowId }) : JSON.stringify({});

            const response = await fetch(`${HUB_URL}/hub/instance/${port}/stop-workflow`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body
            });
            if (!response.ok) throw new Error('结束运行失败');
            showToast('工作流已结束', 'success');
        } else {
            // 没有工作流在跑：通过 Hub 直接在后端启动一次工作流
            console.log(`[DEBUG] Control Room 请求在端口 ${port} 启动工作流`);
            const response = await fetch(`${HUB_URL}/hub/instance/${port}/run-workflow`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            if (!response.ok) {
                let msg = '启动工作流失败';
                try {
                    const err = await response.json();
                    if (err && err.error) msg = err.error;
                } catch (_) {}
                throw new Error(msg);
            }
            showToast('工作流已启动', 'success');
        }
        loadInstances();
    } catch (error) {
        console.error('[DEBUG] 运行/结束运行失败:', error);
        showToast('操作失败: ' + error.message, 'error');
    }
}

async function pauseInstance(port) {
    try {
        const workflowId = appWorkflowIds[port] || null;
        const body = workflowId ? JSON.stringify({ workflow_id: workflowId }) : JSON.stringify({});

        // 通过 Hub 发送暂停请求，避免前端跨域
        const response = await fetch(`${HUB_URL}/hub/instance/${port}/pause`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body
        });
        if (!response.ok) throw new Error('暂停失败');
        
        showToast('实例已暂停');
        loadInstances();
    } catch (error) {
        console.error('[DEBUG] 暂停失败:', error);
        showToast('暂停失败: ' + error.message, 'error');
    }
}

async function resumeInstance(port) {
    try {
        const workflowId = appWorkflowIds[port] || null;
        const body = workflowId ? JSON.stringify({ workflow_id: workflowId }) : JSON.stringify({});

        // 通过 Hub 发送恢复请求，避免前端跨域
        const response = await fetch(`${HUB_URL}/hub/instance/${port}/resume`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body
        });
        if (!response.ok) throw new Error('恢复失败');
        
        showToast('实例已恢复');
        loadInstances();
    } catch (error) {
        console.error('[DEBUG] 恢复失败:', error);
        showToast('恢复失败: ' + error.message, 'error');
    }
}

async function closeInstance(port) {
    if (!confirm(`确定要关闭端口 ${port} 上的实例吗？`)) {
        return;
    }
    
    try {
        const response = await fetch(`${HUB_URL}/hub/instance/${port}/stop`, { method: 'POST' });
        if (!response.ok) throw new Error('关闭失败');
        
        showToast('实例已关闭');
        setTimeout(() => loadInstances(), 1000);
    } catch (error) {
        showToast('关闭失败: ' + error.message, 'error');
    }
}

async function updateConcurrency(port) {
    const input = document.getElementById(`concurrency-${port}`);
    const value = parseInt(input.value);
    
    if (value < 1 || value > 20) {
        showToast('并发数量必须在 1-20 之间', 'error');
        return;
    }
    
    // TODO: 实现并发数量更新接口
    showToast(`并发数量已设置为 ${value}`, 'success');
}

// ==================== 创建新实例 ====================
async function createNewApp() {
    try {
        const response = await fetch(`${HUB_URL}/start-new-instance`, { method: 'POST' });
        if (!response.ok) throw new Error('创建失败');
        
        const data = await response.json();
        showToast('App 实例创建成功');
        setTimeout(() => loadInstances(), 2000);
    } catch (error) {
        showToast('创建失败: ' + error.message, 'error');
    }
}

async function createNewWorkteam() {
    const projectName = prompt('请输入项目名称:');
    if (!projectName) return;
    
    try {
        const response = await fetch(`${HUB_URL}/start-new-WorkTeam`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ projectName })
        });
        
        if (!response.ok) throw new Error('创建失败');
        
        const data = await response.json();
        showToast('WorkTeam 实例创建成功');
        setTimeout(() => loadInstances(), 2000);
    } catch (error) {
        showToast('创建失败: ' + error.message, 'error');
    }
}

// ==================== 端口扫描 ====================
async function scanPorts() {
    const btn = document.getElementById('scanBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 扫描中...';
    
    try {
        const response = await fetch(`${HUB_URL}/hub/scan-ports`);
        if (!response.ok) throw new Error('扫描失败');
        
        const data = await response.json();
        const found = data.found || [];
        
        if (found.length === 0) {
            showToast('未发现新实例');
        } else {
            showToast(`发现 ${found.length} 个实例`);
            setTimeout(() => loadInstances(), 1000);
        }
    } catch (error) {
        showToast('扫描失败: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-radar"></i> 扫描端口';
    }
}

// ==================== 自动刷新 ====================
function startAutoRefresh() {
    refreshInterval = setInterval(() => {
        loadInstances();
    }, 5000); // 每5秒刷新一次
}

// ==================== 工具函数 ====================
function getStatusText(status) {
    const statusMap = {
        'running': '运行中',
        'stopped': '已停止',
        'paused': '已暂停'
    };
    return statusMap[status] || status;
}

function formatTime(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp * 1000);
    return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function showToast(message, type = 'info') {
    // 简单的 toast 实现
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 25px;
        background: ${type === 'error' ? '#dc3545' : type === 'success' ? '#28a745' : '#17a2b8'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ==================== CSS 动画 ====================
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(400px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(400px); opacity: 0; }
    }
`;
document.head.appendChild(style);

