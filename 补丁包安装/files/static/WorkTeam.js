document.addEventListener('DOMContentLoaded', () => {
    initMessageSelector();
    const saveBtn = document.getElementById('saveBtn');
    const IsAllVisibleVbtn = document.getElementById('IsAllVisibilityIcon');
    const saveModal = document.getElementById('saveModal');
    const Open_All_Agents = document.getElementById('OpenAgents');
    const saveAsBtn = document.getElementById('saveAsBtn');
    const cancelSaveBtn = document.getElementById('cancelSaveBtn');
    const fileNameInput = document.getElementById('fileNameInput');
    const IsTempSaveBtn = document.getElementById('IsTempSave');
    const dragOverlay = document.createElement('div');
    let headName='New Item'
    let IsTempSave=false
    dragOverlay.id = 'dragOverlay';
    dragOverlay.innerHTML = '<div>拖拽 JSON 文件到这里以加载数据</div>';
    dragOverlay.style.display = 'none';
    document.body.appendChild(dragOverlay);

    // 防止浏览器默认行为
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        document.body.addEventListener(eventName, preventDefaults, false);
    });
    const SELECTORS = {
        createAgentBtn: '#createAgentBtn',
        createLimitBtn: '#createLimitBtn',
        sendMessageBtn: '#sendMessageBtn',
        agentList: '#agentList',
        limitList: '#limitList',
        chatBox: '#chatBox',
        toInput: '#toInput',
        messageInput: '#messageInput'
    };

    let state = {
        version: 0,
        agents: [],
        messages: [],
        limits: []
    };
    // 初始化消息选择器
        // 初始化消息选择器
        // 加载现有消息文件
    
    
    const elements = Object.entries(SELECTORS).reduce((acc, [key, selector]) => {
        acc[key] = document.querySelector(selector);
        return acc;
    }, {});
    window.onload = function() {
        keepPageActive();
        // 其他初始化代码...
      };
    function keepPageActive() {
        // 每隔 15 秒执行一次
        setInterval(function() {
            // 方法1：更新一个隐藏的 DOM 元素
            const hiddenElement = document.getElementById('hidden-element');
            if (hiddenElement) {
                hiddenElement.textContent = new Date().toLocaleTimeString();
            }
            const event = new Event('keepAliveEvent');
            document.dispatchEvent(event);
      
            console.log('Executed keep-alive tasks',new Date().toLocaleTimeString());
        }, 5000); // 每 15 秒执行一次
      }
    const updateState = async () => {
        try {
            const response = await fetch('/update_state', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ ...state, version: state.version })
            });
    
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
    
            const newState = await response.json();
    
            // 合并新状态
            mergeState(newState);
    
            // 渲染消息
            renderMessages();
    
            // 保存到 localStorage
            localStorage.setItem('chatState', JSON.stringify(state));
    
            console.log('State updated and saved successfully');
        } catch (error) {
            console.error('Error updating state:', error);
        }
    };
    async function initMessageSelector() {
        const selector = document.getElementById('messageSelector');
        const saveMessageBtn = document.getElementById('saveMessageBtn');
        const createMessageBtn = document.getElementById('createMessageBtn');
        let currentMessages ;
        // 保存初始的当前消息
        setTimeout(() => {
            currentMessages = [...state.messages];
        }, 1000);
        
    
        async function loadMessageFiles() {
            try {
                const response = await fetch('/get_message_files');
                const files = await response.json();
                
                // 清除现有选项（除了 Now Message）
                while (selector.options.length > 1) {
                    selector.remove(1);
                }
                
                // 添加文件选项
                files.forEach(file => {
                    const option = new Option(file, file);
                    selector.add(option);
                });
            } catch (error) {
                console.error('Error loading message files:', error);
            }
        }
    
        // 添加选择器变更事件
        selector.addEventListener('change', async (e) => {
            const selectedValue = e.target.value;
            console.log('Selected message file:', selectedValue);
            
            if (selectedValue === 'current') {
                // 切换回 Now Message 时恢复保存的当前消息
                state.messages = [...currentMessages];
                renderMessages();
                return;
            }
            
            try {
                const response = await fetch('/load_message_file', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ filename: selectedValue })
                });
                
                const result = await response.json();
                if (result.success) {
                    // 在切换到新文件之前，如果当前是 Now Message，保存其状态
                    if (selector.value === 'current') {
                        currentMessages = [...state.messages];
                    }
                    
                    state.messages = result.messages;
                    renderMessages();
                    console.log('Messages loaded:', result.messages);
                } else {
                    throw new Error(result.error);
                }
            } catch (error) {
                console.error('Error loading messages:', error);
                alert('Failed to load messages: ' + error.message);
            }
        });
        

// 初始化自动保存功能
setInterval(async () => {
    if(IsTempSave == true)
    {
        if (IsTempSave) {
            const timestamp = new Date().getTime();
            const tempFilename = `TempMessage`;
            
            try {
                const response = await fetch('/save_message_file', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        filename: tempFilename,
                        messages: state.messages
                    })
                });
                
                const result = await response.json();
                if (!result.success) {
                    console.error('Auto-save failed:', result.error);
                }
            } catch (error) {
                console.error('Error during auto-save:', error);
            }
        }
    }
        
}, 60000); // 1分钟 = 60000毫秒


saveMessageBtn.addEventListener('click', async () => {
    const currentFile = selector.value !== 'current' ? selector.value : `messages_${getFormattedDate()}`;
    // 确保提示不带.json后缀
    const baseFilename = currentFile.endsWith('.json') ? currentFile.slice(0, -5) : currentFile;
    let filename = prompt('Enter filename to save messages:', baseFilename);
    
    if (!filename) return;
    
    // 移除用户可能输入的.json后缀
    if (filename.endsWith('.json')) {
        filename = filename.slice(0, -5);
    }
    
    try {
        const response = await fetch('/save_message_file', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                filename: filename, // 服务器端会自动添加.json后缀
                messages: state.messages
            })
        });
        
        const result = await response.json();
        if (result.success) {
            alert('Messages saved successfully!');
            await loadMessageFiles();
            // 选择器中显示的可能带有.json后缀，根据服务器实现调整
            selector.value = filename.endsWith('.json') ? filename : `${filename}.json`;
        } else {
            throw new Error(result.error);
        }
    } catch (error) {
        console.error('Error saving messages:', error);
        alert('Failed to save messages: ' + error.message);
    }
});

// 清理函数，确保在组件卸载时清除定时器
function cleanup() {
    if (tempSaveInterval) {
        clearInterval(tempSaveInterval);
    }
}


        
        // 创建消息按钮点击事件
        createMessageBtn.addEventListener('click', async () => {
            const filename = prompt('Enter filename for the new message file:', `new_message_${getFormattedDate()}.json`);
            if (!filename) return;
            
            try {
                const response = await fetch('/create_message_file', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ filename: filename })
                });
                
                const result = await response.json();
                if (result.success) {
                    alert('New message file created successfully!');
                    state.messages = [];
                    renderMessages();
                    await loadMessageFiles();
                    selector.value = filename;
                } else {
                    throw new Error(result.error);
                }
            } catch (error) {
                console.error('Error creating message file:', error);
                alert('Failed to create message file: ' + error.message);
            }
        });
    
        // 初始化加载文件列表
        await loadMessageFiles();
    }
        

    // 获取格式化的日期时间字符串
    function getFormattedDate() {
        return new Date().toISOString().slice(0,19).replace(/[:T]/g, '-');
    } 
    // 确保createMessageElement函数在全局作用域中可用
    const createMessageElement = (message) => {
        // 创建消息容器
        const messageWrapper = document.createElement('div');
        messageWrapper.className = 'message-wrapper';
        
        // 创建基础消息元素
        const messageElement = document.createElement('div');
        const messageType = message.from === 'User' ? 'sent' : 'received';
        messageElement.className = `message-bubble ${messageType}`;
        if(message.Received.length==0)
        {
            
        }
        // 如果是限制消息，添加限制类
        if (message.IsLimit) {
            messageElement.classList.add('limited');
        }
        // HTML转义函数
        const escapeHtml = (text) => {
            const entityMap = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            };
            return text.replace(/[&<>"']/g, s => entityMap[s]);
        };
        // 获取发送者的颜色
        const agent = state.agents.find(agent => agent.name === message.from);
        const headerColor = agent && agent.color ? agent.color : (message.from === 'User' ? '#2ecc71' : '#3498db');
        // 创建操作按钮
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'message-actions';
        actionsDiv.innerHTML = `
            <button class="action-btn edit-btn" title="编辑">
                <i class="fas fa-edit"></i>
            </button>
            <button class="action-btn delete-btn" title="删除">
                <i class="fas fa-trash"></i>
            </button>
            <button class="action-btn confirm-btn" title="确认">
                <i class="fas fa-check"></i>
            </button>
        `;
        // 设置消息内容
        const processContent = (content) => {
            let processedContent = escapeHtml(content);
        
            // URL识别正则
            const urlRegex = /https?:\/\/[^\s<>"]+/g;
            // 文件路径识别正则（支持多种格式）
            const pathRegex = /(@TempFiles[\/\\][^<>"|?*\r\n]+|[A-Za-z]:[\/\\][^<>"|?*\r\n]+)/g;
        
            // 处理URL和路径
            const processLinksAndPaths = (text) => {
                let lastIndex = 0;
                let result = '';
                
                // 先收集所有匹配（包括URL和文件路径）
                let matches = [];
                let match;
                
                // 收集URL
                while ((match = urlRegex.exec(text)) !== null) {
                    matches.push({
                        index: match.index,
                        text: match[0],
                        type: 'url',
                        end: urlRegex.lastIndex
                    });
                }
                
                // 收集文件路径
                while ((match = pathRegex.exec(text)) !== null) {
                    // 检查这个路径是否已经被包含在之前匹配的URL中
                    const isPartOfUrl = matches.some(m => 
                        m.type === 'url' && 
                        m.index <= match.index && 
                        m.end >= pathRegex.lastIndex
                    );
                    
                    if (!isPartOfUrl) {
                        // 标准化路径分隔符
                        const normalizedPath = match[0].replace(/\//g, '\\');
                        matches.push({
                            index: match.index,
                            text: normalizedPath,
                            type: 'path',
                            end: pathRegex.lastIndex
                        });
                    }
                }
        
                // 按位置排序
                matches.sort((a, b) => a.index - b.index);
        
                // 处理所有匹配
                matches.forEach(match => {
                    result += text.slice(lastIndex, match.index);
                    
                    if (match.type === 'url') {
                        // URL处理
                        result += `<a href="${match.text}" target="_blank" class="url-link">
                                    <i class="fas fa-link"></i>${match.text}
                                 </a>`;
                    } else {
                        // 文件路径处理
                        const isDirectory = !match.text.split(/[\/\\]/).pop().includes('.');
                        const iconClass = isDirectory ? 'fa-folder' : 'fa-file';
                        result += `<span class="file-path" data-path="${match.text}">
                                    <i class="fas ${iconClass}"></i>${match.text}
                                 </span>`;
                    }
                    
                    lastIndex = match.end;
                });
        
                result += text.slice(lastIndex);
                return result;
            };
        
            processedContent = processLinksAndPaths(processedContent);
            return processedContent.replace(/\n/g, '<br>');
        };
        
        // 设置消息内容
        // 获取发送者的颜色
        
        // 计算徽章的颜色（基于headerColor）
        const getBadgeStyles = (headerColor) => {
            // 将headerColor转换为HSL以便于调整亮度和饱和度
            const hslColor = tinycolor(headerColor);
            
            return {
                new: {
                    background: hslColor.clone().saturate(20).darken(10).toString(),
                    color: '#ffffff'
                },
                received: {
                    background: 'rgba(255, 255, 255, 0.9)',
                    border: `2px solid ${hslColor.clone().saturate(10).toString()}`,
                    color: hslColor.clone().darken(15).toString()
                }
            };
        };

        const badgeStyles = getBadgeStyles(headerColor);
        
        // 设置消息内容
        messageElement.innerHTML = `
            <div class="message-inner">
                <div class="header" style="background-color: ${headerColor};">
                    From: ${escapeHtml(message.from)} To: ${escapeHtml(message.to)}
                    <span class="message-status ${message.Received.length === 0 ? 'new' : 'received'}"
                        style="${message.Received.length === 0 
                            ? `background-color: ${badgeStyles.new.background}; color: ${badgeStyles.new.color};` 
                            : `background-color: ${badgeStyles.received.background}; 
                                border: ${badgeStyles.received.border}; 
                                color: ${badgeStyles.received.color};`}">
                        ${message.Received.length === 0 ? 
                            '<i class="fas fa-circle"></i> New' : 
                            `<i class="fas fa-check"></i> ${message.Received.length}`}
                    </span>
                </div>
                <div class="content">${processContent(message.content)}</div>
                <div class="timestamp">${new Date(message.timestamp).toLocaleString()}</div>
            </div>
        `;
    
        // 添加文件路径点击事件处理
        messageElement.querySelectorAll('.file-path').forEach(element => {
            element.addEventListener('click', async (e) => {
                const path = e.currentTarget.dataset.path;
                try {
                    const response = await fetch('/open_file', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ path: path })
                    });
                    
                    const result = await response.json();
                    if (!result.success) {
                        throw new Error(result.error);
                    }
                } catch (error) {
                    console.error('Error opening file:', error);
                    alert('无法打开文件：' + error.message);
                }
            });
        });
        
        
        // 将消息气泡添加到包装器中
        messageWrapper.appendChild(messageElement);
        // 将操作按钮添加到消息气泡中（而不是最前面）
        messageElement.appendChild(actionsDiv);
        // 添加事件监听器
        const setupActionButton = (selector, handler) => {
            const button = actionsDiv.querySelector(selector);
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                handler(message);
            });
        };
        setupActionButton('.delete-btn', deleteMessage);
        setupActionButton('.edit-btn', showEditForm);
        setupActionButton('.confirm-btn', confirmMessage);
        return messageWrapper;
    };
    
    
    
    const deleteMessage = (message) => {
        if (confirm('确定要删除这条消息吗？')) {
            const index = state.messages.findIndex(m => 
                m.from === message.from && 
                m.timestamp === message.timestamp
            );
            if (index !== -1) {
                state.messages.splice(index, 1);
                updateState();
                renderMessages();
            }
        }
    };
    const showEditForm = (message) => {
        // 状态变量
        let fromSuggestionsContainer = null;
        let toSuggestionsContainer = null;
        let currentFromSuggestions = [];
        let currentToSuggestions = [];
        let selectedFromIndex = -1;
        let selectedToIndex = -1;
    
        // 创建表单
        const form = document.createElement('div');
        form.className = 'edit-form';
        form.innerHTML = `
            <h3>编辑消息</h3>
            <div class="input-group">
                <input type="text" id="edit-from" value="${message.from}" placeholder="发送者">
            </div>
            <div class="input-group">
                <input type="text" id="edit-to" value="${message.to}" placeholder="接收者">
            </div>
            <textarea id="edit-content" placeholder="消息内容">${message.content}</textarea>
            <div class="form-buttons">
                <button id="save-edit" class="action-btn save-btn">
                    <i class="fas fa-save"></i> 保存
                </button>
                <button id="cancel-edit" class="action-btn cancel-btn">
                    <i class="fas fa-times"></i> 取消
                </button>
            </div>
        `;
    
        document.body.appendChild(form);
    
        // 获取输入元素
        const fromInput = form.querySelector('#edit-from');
        const toInput = form.querySelector('#edit-to');
    
        // 创建建议容器函数
        const createSuggestionsContainer = () => {
            const container = document.createElement('div');
            container.className = 'suggestions-container';
            document.body.appendChild(container);
            return container;
        };
    
        // 显示建议列表
        const showSuggestions = (inputElement, container, suggestions, selectedIndex) => {
            if (!container) return;
            
            container.innerHTML = '';
            suggestions.forEach((suggestion, index) => {
                const div = document.createElement('div');
                div.className = 'suggestion-item';
                div.textContent = suggestion;
                
                if (index === selectedIndex) {
                    div.classList.add('selected');
                }
    
                div.addEventListener('click', () => {
                    inputElement.value = suggestion;
                    hideSuggestions(container);
                });
    
                container.appendChild(div);
            });
    
            if (suggestions.length > 0) {
                const rect = inputElement.getBoundingClientRect();
                container.style.display = 'block';
                container.style.left = `${rect.left}px`;
                container.style.top = `${rect.bottom + window.scrollY}px`;
                container.style.width = `${Math.max(inputElement.offsetWidth, 200)}px`;
            } else {
                hideSuggestions(container);
            }
        };
    
        // 隐藏建议列表
        const hideSuggestions = (container) => {
            if (container) {
                container.style.display = 'none';
            }
        };
    
        // 处理输入事件
        const handleInput = (inputElement, container, isFromInput = true) => {
            const value = inputElement.value.toLowerCase();
            const suggestions = state.agents
                .map(agent => agent.name)
                .filter(name => name.toLowerCase().includes(value));
            
            if (isFromInput) {
                currentFromSuggestions = suggestions;
                selectedFromIndex = -1;
                showSuggestions(inputElement, container, suggestions, selectedFromIndex);
            } else {
                currentToSuggestions = suggestions;
                selectedToIndex = -1;
                showSuggestions(inputElement, container, suggestions, selectedToIndex);
            }
        };
            // 处理键盘导航
    const handleKeydown = (e, input, container, suggestions, isFromInput = true) => {
        if (!container || container.style.display === 'none') return;
        const currentIndex = isFromInput ? selectedFromIndex : selectedToIndex;
        
        switch(e.key) {
            case 'ArrowDown':
            case 'ArrowUp':
                e.preventDefault();
                const direction = e.key === 'ArrowDown' ? 1 : -1;
                const newIndex = (currentIndex + direction + suggestions.length) % suggestions.length;
                
                if (isFromInput) {
                    selectedFromIndex = newIndex;
                    showSuggestions(input, container, suggestions, selectedFromIndex);
                } else {
                    selectedToIndex = newIndex;
                    showSuggestions(input, container, suggestions, selectedToIndex);
                }
                break;
            case 'Enter':
                if (currentIndex !== -1) {
                    e.preventDefault();
                    input.value = suggestions[currentIndex];
                    hideSuggestions(container);
                }
                break;
            case 'Escape':
                hideSuggestions(container);
                break;
        }
    };
    // 初始化建议容器
    fromSuggestionsContainer = createSuggestionsContainer();
    toSuggestionsContainer = createSuggestionsContainer();
    // 添加事件监听
    fromInput.addEventListener('input', () => handleInput(fromInput, fromSuggestionsContainer, true));
    toInput.addEventListener('input', () => handleInput(toInput, toSuggestionsContainer, false));
    fromInput.addEventListener('keydown', (e) => handleKeydown(e, fromInput, fromSuggestionsContainer, currentFromSuggestions, true));
    toInput.addEventListener('keydown', (e) => handleKeydown(e, toInput, toSuggestionsContainer, currentToSuggestions, false));
    // 点击外部关闭建议列表
    document.addEventListener('click', (e) => {
        if (!fromInput.contains(e.target) && !fromSuggestionsContainer.contains(e.target)) {
            hideSuggestions(fromSuggestionsContainer);
        }
        if (!toInput.contains(e.target) && !toSuggestionsContainer.contains(e.target)) {
            hideSuggestions(toSuggestionsContainer);
        }
    });
    // 保存处理函数
    const saveHandler = () => {
        const newFrom = fromInput.value.trim();
        const newTo = toInput.value.trim();
        const newContent = form.querySelector('#edit-content').value.trim();
        
        if (newFrom && newTo && newContent) {
            const index = state.messages.findIndex(m => 
                m.timestamp === message.timestamp
            );
            
            if (index !== -1) {
                // 直接修改现有消息对象的属性
                // 更新本地状态
                const targetMessage = state.messages[index];
                const editedAt = new Date().toISOString();
                targetMessage.from = newFrom;
                targetMessage.to = newTo;
                targetMessage.content = newContent;
                targetMessage.editedAt = editedAt;

                // 发送请求到服务器以更新消息
                fetch('/edit_message', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        timestamp: targetMessage.timestamp,
                        from: newFrom,
                        to: newTo,
                        content: newContent,
                        editedAt: editedAt
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        console.log('Message updated successfully:', data.data);
                        updateState();
                        renderMessages();
                    } else {
                        console.error('Error updating message:', data.message);
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                });
                
                updateState();
                renderMessages();
                cleanup();
            }
        } else {
            alert('所有字段都必须填写！');
        }
    };
    
    // 清理函数
    const cleanup = () => {
        if (fromSuggestionsContainer) {
            fromSuggestionsContainer.remove();
        }
        if (toSuggestionsContainer) {
            toSuggestionsContainer.remove();
        }
        form.remove();
    };
    // 添加按钮事件监听
    form.querySelector('#save-edit').addEventListener('click', saveHandler);
    form.querySelector('#cancel-edit').addEventListener('click', cleanup);
    // 添加快捷键
    form.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.ctrlKey) {
            saveHandler();
        }
    });
};
// 添加样式
const style = document.createElement('style');
style.textContent = `
    .edit-form {
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: white;
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        z-index: 1000;
        min-width: 300px;
    }
    .edit-form h3 {
        margin-top: 0;
        margin-bottom: 15px;
    }
    .input-group {
        position: relative;
        margin-bottom: 10px;
    }
    .edit-form input,
    .edit-form textarea {
        width: 100%;
        padding: 8px;
        margin-bottom: 10px;
        border: 1px solid #ddd;
        border-radius: 4px;
        box-sizing: border-box;
    }
    .edit-form textarea {
        height: 100px;
        resize: vertical;
    }
    .form-buttons {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
    }
    .action-btn {
        padding: 8px 15px;
        border: none;
        border-radius: 4px;
        color: white;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 5px;
    }
    .save-btn {
        background-color: #2ecc71;
    }
    .cancel-btn {
        background-color: #e74c3c;
    }
    .suggestions-container {
        position: absolute;
        background: white;
        border: 1px solid #ddd;
        border-radius: 4px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        max-height: 200px;
        overflow-y: auto;
        display: none;
        z-index: 1001;
    }
    .suggestion-item {
        padding: 8px 10px;
        cursor: pointer;
        transition: background-color 0.2s;
    }
    .suggestion-item:hover {
        background-color: #f5f5f5;
    }
    .suggestion-item.selected {
        background-color: #e8e8e8;
    }
`;
document.head.appendChild(style);
const confirmMessage = (message) => {
    if (confirm('确定要再次接收这条消息吗？')) {
        const index = state.messages.findIndex(m => 
            m.from === message.from && 
            m.timestamp === message.timestamp
        );
        
        if (index !== -1) {
            state.messages[index] = {
                ...state.messages[index],
                Received: [],
                IsLimit: false,
                shouldUpdateFields: true
            };
            
            // 移动消息到末尾
            const [msg] = state.messages.splice(index, 1);
            state.messages.push(msg);
            
            updateState();
            renderMessages();
        }
    }
};

const longPoll = async () => {
    try {
        const response = await fetch('/long_poll', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ version: state.version })
        });

        if (response.status === 200) {
            const newState = await response.json();
            // 合并新状态
            mergeState(newState);

            // 渲染消息
            renderMessages();
            updateMessageColors();

            // 保存到 localStorage
            localStorage.setItem('chatState', JSON.stringify(state));
            console.log('State updated from long poll', state);

        } else if (response.status === 304) {
            console.log('No updates');
        } else if (response.status === 500) {
            const errorData = await response.json();
            console.error('Server error:', errorData.message);
        } else {
            throw new Error('Unexpected response from server');
        }
    } catch (error) {
        console.error('Long polling error:', error);
    } finally {
        setTimeout(longPoll, 1000);
    }
};



// 新增合并状态的函数
const mergeState = (newState) => {
    // 更新版本号
    state.version = newState.version;

    // 更新 agents 和 limits
    state.agents = newState.agents;
    state.limits = newState.limits;

    // 创建一个映射，以便快速查找本地消息
    const localMessagesMap = new Map(state.messages.map(m => [m.timestamp, m]));

    // 合并消息 
    state.messages = newState.messages.map(serverMsg => {
        const localMsg = localMessagesMap.get(serverMsg.timestamp);
        if (localMsg) {
            // 比较编辑时间
            const serverEditTime = serverMsg.editedAt ? new Date(serverMsg.editedAt) : new Date(serverMsg.timestamp);
            const localEditTime = localMsg.editedAt ? new Date(localMsg.editedAt) : new Date(localMsg.timestamp);

            // 如果本地版本更新，保留本地版本
            if (localEditTime > serverEditTime) {
                console.log('保留本地更新版本:', localMsg);
                return localMsg;
            }

            // 如果本地消息有 shouldUpdateFields 标记，保留本地的 Received 和 IsLimit
            if (localMsg.shouldUpdateFields) {
                return {
                    ...serverMsg,
                    Received: localMsg.Received,
                    IsLimit: localMsg.IsLimit,
                    shouldUpdateFields: undefined // 清除标记
                };
            } else {
                return {
                    ...serverMsg,
                    // 保留本地的 Received 信息
                    Received: serverMsg.Received,
                };
            }
        }
        return serverMsg;
    });

    // 添加调试日志
    console.log('合并后的状态:', state.messages);
};
const renderMessages = () => {
    const chatBox = elements.chatBox;
    chatBox.innerHTML = '';
    state.messages.forEach(message => {
        // 首先，找到消息所属的 Agent
        const agent = state.agents.find(agent => agent.name === message.from);

        // 如果 Agent 存在并且 IsVisible 为 false，则跳过渲染
        if (agent && agent.IsVisible === false) {
            return;
        }

        // 如果消息不是限制消息或者是限制消息但不是发送给访问端的
        if (!message.IsLimit || message.to !== 'visitor') {
            const messageElement = createMessageElement(message);
            chatBox.appendChild(messageElement);
        }
    });
};
const updateAgentVisibility = (agentName, isVisible) => {
    const agentIndex = state.agents.findIndex(agent => agent.name === agentName);
    if (agentIndex !== -1) {
        state.agents[agentIndex].IsVisible = isVisible;
        updateState();
    }
};

    // 开始长轮询
    longPoll();
    
    
    const renderSavedState = () => {
        // 清空现有的 UI 元素
        elements.agentList.innerHTML = '';
        elements.limitList.innerHTML = '';
        elements.chatBox.innerHTML = '';

        // 渲染保存的 Agents
        state.agents.forEach(agent => {
            createAgent(agent.name, agent.item, agent.color, false,agent.IsVisible);
        });

        // 渲染保存的 Limits
        state.limits.forEach(limit => {
            createLimit(limit.from, limit.to, false,limit.messages_Time,limit.id);
        });

        // 渲染保存的消息
        state.messages.forEach(message => {
            const messageElement = createMessageElement(message);
            elements.chatBox.appendChild(messageElement);
        });
        // 滚动到聊天框底部
        elements.chatBox.scrollTop = elements.chatBox.scrollHeight;
    };
    const History_project = async () => {
        const res = await fetch('/history-project', {
          method: 'POST'
        });
        return await res.json();
      }
      
    const getHistoryItem = async () => {
        const HistoryItem = await History_project();
        let name = HistoryItem.name;
        let path = HistoryItem.path;
        FilePath = path;
        ProjectName=name;
        // 去除后缀
        // name = name.split('.json')[0];
        
        fetch('/get-project-files', {
            method: 'POST',
            headers: {
            'Content-Type': 'application/json'
            },
            body: JSON.stringify({ json_name: name ,json_path: path })
        })
        .then(response => response.json())
        .then(data => {
            headName=name;
            //加载数据
            loadDataFromJson(data);
            updatePageTitle();
            // 在这里处理返回的JSON数据
        })
        .catch(error => {
            console.error('Error fetching the project file:', error);
        });
    };
        
    // 调用函数以执行请求
    getHistoryItem();
    const loadDataFromJson = (data) => {
        // 清空现有状态
        state.agents = [];
        state.limits = [];
        state.messages = [];

        // 加载新数据
        if (data.agents && Array.isArray(data.agents)) {
            state.agents = data.agents;
        }
        if (data.limits && Array.isArray(data.limits)) {
            state.limits = data.limits;
        }
        if (data.messages && Array.isArray(data.messages)) {
            state.messages = data.messages;
        }
        clearBackendState();
        updateState();
        // 渲染新状态
        RefreshState();
        setTimeout(() => {
            renderSavedState();
        }, 1000);
        // 保存新状态到 localStorage
        localStorage.setItem('chatState', JSON.stringify(state));

        alert('Data loaded successfully',data);
    };
    async function clearBackendState() {
        try {
            const response = await fetch('/clear_state', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
    
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
    
            const result = await response.json();
            console.log('Response from server:', result);
    
            if (result.status === 'success') {
                console.log('State cleared successfully');
            } else {
                console.log('Failed to clear state');
            }
        } catch (error) {
            console.error('Error clearing state:', error);
        }
    }
    function RefreshState() {
        fetch('/refresh_state', {
            method: 'POST',
            headers: {
            'Content-Type': 'application/json'
            },
        })
        .then(response => response.json())
        console.log('State refreshed successfully');
    }
    const fetchShortcutItems = async () => {
        try {
            const response = await fetch('http://localhost:3001/get-history-projects');
            return await response.json();
        } catch (error) {
            console.error('Error fetching shortcut items:', error);
            return [];
        }
    };

    const renderShortcutItems = (items, selectElement, agentName) => {
        // 清空现有选项
        selectElement.innerHTML = '';
        const folderStructure = items.reduce((acc, item) => {
            if (item.type === 'file') {
                if (!acc[item.folder]) {
                    acc[item.folder] = [];
                }
                acc[item.folder].push(item);
            }
            return acc;
        }, {});
    
        Object.entries(folderStructure).forEach(([folderName, files]) => {
            const folderOptgroup = document.createElement('optgroup');
            folderOptgroup.label = folderName;
            
            files.forEach(file => {
                const fileOption = document.createElement('option');
                fileOption.value = JSON.stringify({name: file.name, type: file.type, folder: folderName});
                fileOption.textContent = file.name;
                folderOptgroup.appendChild(fileOption);
            });
            selectElement.appendChild(folderOptgroup);
        });
        // 添加change事件监听器
        selectElement.addEventListener('change', (event) => {
            const selectedValue = JSON.parse(event.target.value);
            updateAgentShortcut(agentName, selectedValue);
        });
    };
    const createAgent = (name = null, shortcut = null, color = null, shouldSave = true,isVisible=true) => {
        const agentName = name || `Agent ${state.agents.length+1}`;
    
        // 检查 IsVisible 属性，如果不存在则默认设置为 true
        const newAgent = {
            name: agentName,
            item: shortcut,
            color: color || '#000000',
            IsVisible: isVisible // 添加 IsVisible 属性
        };
    
        if (!name) {
            state.agents.push(newAgent);
        }
        console.log('Creating agent:', newAgent);
    
        // 以下是生成 Agent 列表项的代码
        const agentItem = document.createElement('div');
        agentItem.className = 'item';
        agentItem.innerHTML = `
        <div class="agent-item">
            <span class="agent-name">${agentName}</span>
            <div class="controls-row">
                <select class="agent-select"></select>
                <input type="color" class="color-picker" value="${newAgent.color}">
                <button class="visibility-btn">${newAgent.IsVisible ? '👁️' : '🚫'}</button>
                <button class="delete-icon-btn">🗑️</button>
                <button class="confirms-btn">Confirm</button>
                <button class="run-btn">Open</button>
                <button class="delete-btn">×</button>
            </div>
        </div>
    `;

    
        elements.agentList.appendChild(agentItem);
        sortAgentList();
        const agentSelect = agentItem.querySelector('.agent-select');
        const runBtn = agentItem.querySelector('.run-btn');
        const colorPicker = agentItem.querySelector('.color-picker');
        const visibilityBtn = agentItem.querySelector('.visibility-btn'); // 获取眼睛按钮
        const deleteBtn = agentItem.querySelector('.delete-icon-btn');
        const nameElement = agentItem.querySelector('.agent-name');
        const confirmsBtn = agentItem.querySelector('.confirms-btn');

    
        // 设置名称编辑、删除等功能
        setupAgentNameEditing(nameElement, newAgent, colorPicker);
        setupAgentDeletion(agentItem.querySelector('.delete-btn'), agentItem);
        
        // 运行按钮事件
        runBtn.addEventListener('click', async () => {
            startAndLoadProject(newAgent);
        });
        // 确认删除信息事件
        deleteBtn.addEventListener('click', () => {
            AllMessageDelete(newAgent); 
        })
        // 颜色选择器事件
        colorPicker.addEventListener('change', (event) => {
            const currentAgentName = nameElement.textContent.trim();
            updateAgentColor(currentAgentName, event.target.value);
        });
        // 确认按钮事件
        confirmsBtn.addEventListener('click', () => {
            confirmAllMessage(newAgent);
        });
        // 可见性按钮事件
        visibilityBtn.addEventListener('click', () => {
            newAgent.IsVisible = !newAgent.IsVisible; // 切换 IsVisible 属性
            visibilityBtn.textContent = newAgent.IsVisible ? '👁️' : '🚫'; // 更新按钮图标
            updateAgentVisibility(newAgent.name, newAgent.IsVisible); // 更新状态
            renderMessages(); // 重新渲染消息
        });
    
        const setupAgentSelection = (select, agent) => {
            select.addEventListener('change', (event) => {
                const selectedShortcut = JSON.parse(event.target.value);
                updateAgentShortcut(agent.name, selectedShortcut);
                agent.item = selectedShortcut;
                updateState();
            });
        };
    
        fetchShortcutItems().then(items => {
            renderShortcutItems(items, agentSelect, agentName);
    
            let selectedOption = null;
    
            if (shortcut) {
                for (let option of agentSelect.options) {
                    try {
                        const optionData = JSON.parse(option.value);
                        if (optionData.name === shortcut.name) {
                            selectedOption = option;
                            break;
                        }
                    } catch (error) {
                        console.error('Error parsing option value:', error);
                    }
                }
    
                if (selectedOption) {
                    console.log('Selected shortcut:', shortcut, shortcut.name);
                } else {
                    console.warn('No matching option found for:', shortcut.name);
                }
            }
    
            if (!selectedOption && agentSelect.options.length > 0) {
                selectedOption = agentSelect.options[0];
            }
    
            if (selectedOption) {
                agentSelect.value = selectedOption.value;
                selectedOption.selected = true;
                try {
                    const selectedShortcut = JSON.parse(selectedOption.value);
                    updateAgentShortcut(agentName, selectedShortcut);
                    newAgent.item = selectedShortcut;
                } catch (error) {
                    console.error('Error parsing selected option value:', error);
                }
            } else {
                console.warn('No options available in the select element');
            }
    
            setupAgentSelection(agentSelect, newAgent);
        });
    
        if (shouldSave) updateState();
    };
    const parseAgentName = (name) => {
        // 将字符串分割成数字和非数字部分的数组
        const parts = name.trim().match(/(\d+|[^\d]+)/g) || [name.trim()];
        return parts;
    };
    
    const compareAgentNames = (a, b) => {
        const partsA = parseAgentName(a);
        const partsB = parseAgentName(b);
        
        // 逐部分比较
        const minLength = Math.min(partsA.length, partsB.length);
        
        for (let i = 0; i < minLength; i++) {
            const partA = partsA[i];
            const partB = partsB[i];
            
            // 检查两部分是否都是数字
            const isNumA = /^\d+$/.test(partA);
            const isNumB = /^\d+$/.test(partB);
            
            if (isNumA && isNumB) {
                // 如果都是数字，进行数字比较
                const diff = parseInt(partA) - parseInt(partB);
                if (diff !== 0) return diff;
            } else {
                // 否则进行字符串比较
                const diff = partA.localeCompare(partB);
                if (diff !== 0) return diff;
            }
        }
        
        // 如果前面部分都相同，较短的排在前面
        return partsA.length - partsB.length;
    };
    const confirmAllMessage = (agent) => {
        if (confirm('是否要重新接收所有关于（' + agent.name + '）的消息吗？')) {
            // Filter the messages that are from the specified agent
            const agentMessages = state.messages.filter(msg => msg.from === agent.name);
            
            // Remove these messages from the original array
            state.messages = state.messages.filter(msg => msg.from !== agent.name);
            
            // Reset the properties and push them to the end of the list
            agentMessages.forEach(msg => {
                state.messages.push({
                    ...msg,
                    Received: [],
                    IsLimit: false,
                    shouldUpdateFields: true
                });
            });
    
            updateState();
            renderMessages();
        }
    }
    
    const AllMessageDelete = (agent) => {
       if (confirm('确定要删除所有关于（'+agent.name+'）的消息吗？')) {
            state.messages = state.messages.filter(msg => msg.from !== agent.name);
            updateState();
            renderMessages();

        }
    }
    const sortAgentList = () => {
        const agentItems = Array.from(elements.agentList.children);
        agentItems.sort((a, b) => {
            const nameA = a.querySelector('.agent-name').textContent;
            const nameB = b.querySelector('.agent-name').textContent;
            return compareAgentNames(nameA, nameB);
        });
    
        // Clear and reappend in sorted order
        elements.agentList.innerHTML = '';
        agentItems.forEach(item => elements.agentList.appendChild(item));
    };
    

    const updateAgentShortcut = (agentName, shortcutValue) => {
        const agentIndex = state.agents.findIndex(agent => agent.name === agentName);
        if (agentIndex !== -1) {
            state.agents[agentIndex].item = shortcutValue;
            // 确保保持 IsVisible 属性
            if (typeof state.agents[agentIndex].IsVisible === 'undefined') {
                state.agents[agentIndex].IsVisible = true; // 默认设置为 true
            }
            updateState();
        }
    };    
    const setupAgentNameEditing = (nameElement, agent, colorPicker) => {
        nameElement.addEventListener('click', function() {
            this.contentEditable = true;
            this.focus();
        });
        nameElement.addEventListener('blur', function() {
            this.contentEditable = false;
            const oldName = agent.name;
            const newName = this.textContent.trim();
            // 更新agent名称
            agent.name = newName;
            const index = state.agents.findIndex(a => a.name === oldName);
            if (index !== -1) {
                state.agents[index] = agent;
            }
            // 更新消息
            state.messages.forEach(message => {
                if (message.from === oldName) {
                    message.from = newName;
                }
                if (message.to === oldName) {
                    message.to = newName;
                }
            });
            // 保存当前颜色
            const currentColor = colorPicker.value;
            // 清空并重新渲染消息
            elements.chatBox.innerHTML = '';
            state.messages.forEach(message => {
                const messageElement = createMessageElement(message);
                elements.chatBox.appendChild(messageElement);
            });
            // 确保颜色保持一致
            agent.color = currentColor;
            updateState();
            updateMessageColors();
        });
        nameElement.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                nameElement.blur();
            }
        });
    };
    const updateAgentColor = (agentName, color) => {
        const agent = state.agents.find(agent => agent.name === agentName);
        if (agent) {
            agent.color = color;
            updateState();
            updateMessageColors();
        } else {
            console.warn(`Agent with name ${agentName} not found`);
        }
    };
    const updateMessageColors = () => {
        const chatMessages = elements.chatBox;
        if (chatMessages) {
            chatMessages.querySelectorAll('.message-bubble').forEach(bubble => {
                
                const headerText = bubble.querySelector('.header').textContent;
                const fromNameMatch = headerText.match(/From:\s*(.*?)\s*To:/);
                if (fromNameMatch) {
                    const fromName = fromNameMatch[1].trim();
                    const agent = state.agents.find(agent => agent.name === fromName);
                    if (agent && agent.color) {
                        bubble.querySelector('.header').style.backgroundColor = agent.color;
                    }
                }
            });
        }
    };

    const setupAgentDeletion = (deleteBtn, agentItem) => {
        deleteBtn.addEventListener('click', () => {
            elements.agentList.removeChild(agentItem);
            const agentName = agentItem.querySelector('.agent-name').textContent;
            const index = state.agents.findIndex(agent => agent.name === agentName);
            if (index !== -1) {
                state.agents.splice(index, 1);
                updateState();
            }
        });
    };
    const createLimit = (from = null, to = null, shouldSave = true,messages_Time=[], id = null) => {
        let limitId = id || Date.now(); // 如果提供了 id 就使用它，否则使用时间戳
        const limitItem = document.createElement('div');
        limitItem.className = 'item';
        limitItem.dataset.limitId = limitId;
        const limitCount = elements.limitList.children.length + 1;
    
        limitItem.innerHTML = `
            <span>Limit ${limitCount}: from </span>
            <input type="text" class="agent-input from-agent" placeholder="Agent1" style="width: 80px;" value="${from || ''}">
            <span> to </span>
            <input type="text" class="agent-input to-agent" placeholder="Agent2" style="width: 80px;" value="${to || ''}">
            <button class="delete-btn">×</button>
        `;
        elements.limitList.appendChild(limitItem);
    
        const fromInput = limitItem.querySelector('.from-agent');
        const toInput = limitItem.querySelector('.to-agent');
    
        setupAutoComplete(fromInput);
        setupAutoComplete(toInput);
    
        // 添加输入事件监听器
        fromInput.addEventListener('input', () => updateLimit(limitId));
        toInput.addEventListener('input', () => updateLimit(limitId));
    
        limitItem.querySelector('.delete-btn').addEventListener('click', () => {
            elements.limitList.removeChild(limitItem);
            const index = state.limits.findIndex(l => l.id === limitId);
            if (index !== -1) {
                state.limits.splice(index, 1);
                updateState();
            }
        });
    
        // 只有在 shouldSave 为 true 且 state.limits 中不存在该 id 的情况下才添加新的 limit
        if (shouldSave && !state.limits.some(limit => limit.id === limitId)) {
            state.limits.push({ id: limitId, from: from || '', to: to || '',messages_Time:messages_Time|| [] });
            updateState();
        }
    };
    const updateLimit = (limitId) => {
        const limitItem = document.querySelector(`.item[data-limit-id="${limitId}"]`);
        if (limitItem) {
            const fromValue = limitItem.querySelector('.from-agent').value.trim();
            const toValue = limitItem.querySelector('.to-agent').value.trim();
            
            // 将 limitId 转换为数字进行比较
            const numericLimitId = Number(limitId);
            let limitIndex = state.limits.findIndex(l => Number(l.id) === numericLimitId);
            
            if (limitIndex !== -1) {
                // 更新现有的 limit
                state.limits[limitIndex] = { id: numericLimitId, from: fromValue, to: toValue,messages_Time:[] };
            } else {
                // 如果没有找到匹配的 limit，创建一个新的
                state.limits.push({ id: numericLimitId, from: fromValue, to: toValue,messages_Time:[] });
            }
            updateState();
        }
    };
    

    const setupAutoComplete = (inputElement) => {
        let currentSuggestions = [];
        let selectedSuggestionIndex = -1;
        let suggestionsContainer = null;
    
        const showSuggestions = () => {
            if (!suggestionsContainer) {
                suggestionsContainer = createSuggestionsContainer(inputElement);
            }
            suggestionsContainer.innerHTML = '';
            currentSuggestions.forEach(suggestion => {
                const div = document.createElement('div');
                div.textContent = suggestion;
                div.style.padding = '8px 10px'; // 增加内边距，使每个项目更高
                div.style.cursor = 'pointer';
                div.addEventListener('click', () => {
                    inputElement.value = suggestion;
                    hideSuggestions();
                    updateLimitFromInput(inputElement);
                });
                suggestionsContainer.appendChild(div);
            });
        
            if (currentSuggestions.length > 0) {
                const rect = inputElement.getBoundingClientRect();
                const windowHeight = window.innerHeight;
                const itemHeight = 36; // 每个建议项的高度（包括内边距）
                const maxItems = 8; // 最大显示的建议数量
                const suggestionsHeight = Math.min(itemHeight * maxItems, currentSuggestions.length * itemHeight);
        
                let topPosition = rect.bottom + window.scrollY;
                let direction = 'down';
        
                if (topPosition + suggestionsHeight > windowHeight + window.scrollY) {
                    topPosition = rect.top + window.scrollY - suggestionsHeight;
                    direction = 'up';
                }
        
                suggestionsContainer.style.display = 'block';
                suggestionsContainer.style.left = `${rect.left}px`;
                suggestionsContainer.style.top = `${topPosition}px`;
                suggestionsContainer.style.width = `${Math.max(inputElement.offsetWidth, 200)}px`; // 确保最小宽度
                suggestionsContainer.style.maxHeight = `${suggestionsHeight}px`;
        
                suggestionsContainer.classList.remove('suggestions-up', 'suggestions-down');
                suggestionsContainer.classList.add(`suggestions-${direction}`);
            } else {
                hideSuggestions();
            }
            selectedSuggestionIndex = -1;
        };
        
    
        const createSuggestionsContainer = () => {
            const container = document.createElement('div');
            container.className = 'suggestions';
            container.style.position = 'absolute';
            container.style.border = '1px solid #ccc';
            container.style.overflowY = 'auto';
            container.style.backgroundColor = 'white';
            container.style.display = 'none';
            container.style.zIndex = '1000';
            container.style.boxShadow = '0 2px 5px rgba(0,0,0,0.1)';
            document.body.appendChild(container);
            return container;
        };
    
        const highlightSuggestion = () => {
            const suggestions = suggestionsContainer.querySelectorAll('div');
            suggestions.forEach((suggestion, index) => {
                suggestion.style.backgroundColor = index === selectedSuggestionIndex ? '#f0f0f0' : '';
            });
        };
    
        const hideSuggestions = () => {
            if (suggestionsContainer) {
                suggestionsContainer.style.display = 'none';
            }
        };
    
        const updateLimitFromInput = (input) => {
            const limitItem = input.closest('.item');
            if (limitItem && limitItem.dataset.limitId) {
                updateLimit(limitItem.dataset.limitId);
            }
        };
    
        // 修改input事件处理
        inputElement.addEventListener('input', function() {
            const inputValue = this.value.toLowerCase();
            const allSuggestions = ['All', ...state.agents.map(agent => agent.name)];
            currentSuggestions = allSuggestions.filter(agentName => 
                agentName.toLowerCase().includes(inputValue)
            );
            showSuggestions();
            updateLimitFromInput(this);
        });

        // 添加点击事件处理
        inputElement.addEventListener('click', function() {
            if (this.value === '') {
                // 如果输入框为空，显示所有选项
                currentSuggestions = ['All', ...state.agents.map(agent => agent.name)];
                showSuggestions();
            }
        });

    
        inputElement.addEventListener('keydown', function(e) {
            switch(e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    selectedSuggestionIndex = Math.min(selectedSuggestionIndex + 1, currentSuggestions.length - 1);
                    highlightSuggestion();
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    selectedSuggestionIndex = Math.max(selectedSuggestionIndex - 1, -1);
                    highlightSuggestion();
                    break;
                case 'Enter':
                    if (selectedSuggestionIndex !== -1) {
                        e.preventDefault();
                        this.value = currentSuggestions[selectedSuggestionIndex];
                        hideSuggestions();
                        updateLimitFromInput(this);
                    }
                    break;
            }
        });
    
        window.addEventListener('resize', () => {
            if (suggestionsContainer && suggestionsContainer.style.display !== 'none') {
                showSuggestions();
            }
        });
    
        const observer = new MutationObserver(mutations => {
            mutations.forEach(mutation => {
                if (mutation.type === 'childList' && !document.contains(inputElement)) {
                    if (suggestionsContainer && suggestionsContainer.parentNode) {
                        suggestionsContainer.parentNode.removeChild(suggestionsContainer);
                    }
                    observer.disconnect();
                }
            });
        });
    
        observer.observe(document.body, { childList: true, subtree: true });
    };
    const sendMessage = () => {
        const message = elements.messageInput.value;
        const to = elements.toInput.value;
        if (message.trim() !== '') {
            const newMessage = {
                type: 'sent',
                from: 'User',
                to: to,
                IsLimit: false,
                Received:[],
                content: message,
                timestamp: new Date().toISOString()
            };
    
            // 添加消息到 state
            if (!state.messages) {
                state.messages = [];
            }
            state.messages.push(newMessage);
    
            // 创建并添加消息元素到 DOM
            const messageElement = createMessageElement(newMessage);
            elements.chatBox.appendChild(messageElement);
    
            // 清空输入框并重置高度
            elements.messageInput.value = '';
            elements.toInput.value = '';
            elements.messageInput.style.height = 'auto';
    
            // 滚动到底部
            elements.chatBox.scrollTop = elements.chatBox.scrollHeight;
    
            // 保存状态
            updateState();
        }
    };

    // Event Listeners
    elements.createAgentBtn.addEventListener('click', () => createAgent());
    elements.createLimitBtn.addEventListener('click', () => createLimit());
    elements.sendMessageBtn.addEventListener('click', sendMessage);
    saveBtn.addEventListener('click', showSaveModal);
    IsAllVisibleVbtn.addEventListener('click', () => {
        const visibilityButtons = document.querySelectorAll('.visibility-btn');
        if(IsAllVisibleVbtn.textContent === '👁️') {
            visibilityButtons.forEach(btn => btn.textContent = '🚫');
            IsAllVisibleVbtn.textContent = '🚫';
            state.agents.forEach(agent => {
                agent.IsVisible=false;
            });
        } else {
            IsAllVisibleVbtn.textContent = '👁️';
            visibilityButtons.forEach(btn => btn.textContent = '👁️');
            state.agents.forEach(agent => {
                agent.IsVisible=true;
            });
        }
        
        updateState();
        updateMessageColors();
    });
    saveAsBtn.addEventListener('click', saveData);
    Open_All_Agents.addEventListener('click', OpenAllAgents);
    cancelSaveBtn.addEventListener('click', hideSaveModal);
    IsTempSaveBtn.addEventListener('click', () => {
        IsTempSave=!IsTempSave;
    })
    elements.messageInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = `${this.scrollHeight}px`;
    });
    elements.messageInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
        if (e.key === 'Enter' && e.shiftKey) {
            this.style.height = `${this.scrollHeight + 24}px`;
        }
    });
    setupAutoComplete(elements.toInput);
    document.body.addEventListener('dragenter', showDragOverlay, false);
    document.body.addEventListener('dragover', showDragOverlay, false);

    // 隐藏拖拽提示层
    document.body.addEventListener('dragleave', hideDragOverlay, false);
    document.body.addEventListener('drop', handleDrop, false);
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 's') {
            e.preventDefault();
            showSaveModal();
        }
    });
    async function OpenAllAgents() {
        for (const agent of state.agents) {
            const agentName = agent.name.split('.json')[0];
            // 检查是否已经存在匹配的"标签页"
            const existingTabUrl = checkForExistingTab(agentName);
            
            if (!existingTabUrl) {
                // 如果不存在匹配的"标签页"，则创建新的
                const newUrl = await startAndLoadProject(agent);
                if (newUrl) {
                    // 标记这个 agent 已经打开，并存储 URL
                    markTabAsOpened(agentName, newUrl);
                }
            } else {
                console.log(`Tab for ${agentName} already exists. Opening...`);
                window.open(existingTabUrl, '_blank');
            }
        }
    }
    
    function checkForExistingTab(agentName) {
        return localStorage.getItem(`openedAgent_${agentName}`);
    }
    
    function markTabAsOpened(agentName, url) {
        localStorage.setItem(`openedAgent_${agentName}`, url);
    }
    
    function showSaveModal() {
        saveModal.style.display = 'flex';
        //去除headName.json
        fileNameInput.value = headName.split('.')[0];
        fileNameInput.focus();
    }
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function showDragOverlay(e) {
        dragOverlay.style.display = 'flex';
    }

    function hideDragOverlay(e) {
        if (!e.relatedTarget || e.relatedTarget === document.body) {
            dragOverlay.style.display = 'none';
        }
    }

    function handleDrop(e) {
        hideDragOverlay(e);
        const dt = e.dataTransfer;
        const files = dt.files;
        headName = files[0].name.split('.')[0];
        updatePageTitle();
        handleFiles(files);
    }

    function handleFiles(files) {
        ([...files]).forEach(readAndLoadFile);
    }

    function readAndLoadFile(file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            try {
                const jsonData = JSON.parse(e.target.result);
                loadDataFromJson(jsonData);
            } catch (error) {
                console.error('Error parsing JSON:', error);
                alert('Invalid JSON file');
            }
        };
        reader.readAsText(file);
    }
    function updatePageTitle() {
        document.title = headName.split('.')[0];
    }
    
    function hideSaveModal() {
        saveModal.style.display = 'none';
    }
    
    function saveData() {
        const fileName = fileNameInput.value.trim();
    
        if (!fileName) {
            alert('Please enter a file name.');
            return;
        }
    
        // 更新 headName 和页面标题
        headName = fileName;
        updatePageTitle();
    
        const data = JSON.stringify(state);
        console.log('Saving data:', state);
        fetch('/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ data, fileName }),
        })
        .then(response => response.json())
        .then(result => {
            alert(result.message);
            hideSaveModal();
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while saving.');
        });
    }
    async function startAndLoadProject(newAgent) {
        try {
            // Start new instance
            const startInstanceResponse = await fetch('http://localhost:3001/start-new-instance', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({})
            });
    
            if (!startInstanceResponse.ok) {
                const errorText = await startInstanceResponse.text();
                console.error('Error starting instance:', errorText);
                return;
            }
    
            const instanceData = await startInstanceResponse.json();
            // Extract port number from response
            const portMatch = instanceData.status.match(/port (\d+)/);
            console.log('Instance started:', instanceData);
            const port = portMatch[1];
    
            // Prepare parameters for loading project
            const params = new URLSearchParams({
                port: port,
                name: newAgent.item.name,
                path: newAgent.item.folder,
                host: location.host,
                callsign: newAgent.name
            });
            
            // Call http://localhost:3001/load-project
            const loadProjectResponse = await fetch(`http://localhost:3001/load-project?${params}`);
            const loadProjectData = await loadProjectResponse.json();
    
            if (loadProjectData.status) {
                const url = `http://127.0.0.1:${port}`;
                // 打开新的网页
                window.open(url, '_blank');
                return url;  // 返回新创建的 URL
            } else if (loadProjectData.error) {
                console.error('Error loading project:', loadProjectData.error);
            }
        } catch (error) {
            console.error('Error:', error);
        }
    }
    
    // 初始化时设置页面标题
    updatePageTitle();
    fileNameInput.addEventListener('input', () => {
        headName = fileNameInput.value;
    });
    // 初始化时设置页面标题
    updatePageTitle();
    

});
