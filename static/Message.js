document.addEventListener('DOMContentLoaded', function() {
    const fileSelect = document.getElementById('fileSelect');
    const chatBox = document.getElementById('chatBox');

    let lastSelectedFile = '';
    let isFileSetByUser = false; // 标志是否通过 SetProjsetName 设置了文件名

    window.displayMessages = function(data) { // 使用 window 使其成为全局函数
        chatBox.innerHTML = '';
        console.log('显示消息:', data); // 日志输出
        data.forEach(conversation => {
            conversation.forEach(message => {
                if (message.name === 'New started') {
                    const divider = document.createElement('div');
                    divider.className = 'new-message';
                    divider.textContent = '------------**New Message**------------';
                    chatBox.appendChild(divider);
                } else {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `message ${message.NodeKind ? message.NodeKind.toLowerCase() : 'normal'}`;
                    const messageHeader = document.createElement('div');
                    messageHeader.className = 'message-header';
                    messageHeader.textContent = message.label;
                    messageDiv.appendChild(messageHeader);

                    // 显示Inputs部分
                    const inputSection = document.createElement('div');
                    inputSection.className = 'input-section';
                    const inputTitle = document.createElement('div');
                    inputTitle.className = 'section-title';
                    inputTitle.textContent = 'Inputs:';
                    inputSection.appendChild(inputTitle);

                    if (message.Inputs) {
                        message.Inputs.forEach(input => {
                            const inputDiv = document.createElement('div');
                            inputDiv.className = `input ${input.Kind ? input.Kind.toLowerCase() : 'string'}`;
                            const inputName = document.createElement('span');
                            inputName.className = 'input-name';
                            inputName.textContent = input.name + ': ';
                            inputDiv.appendChild(inputName);
                    
                            const inputContent = document.createElement('span');
                            if (input.Kind === 'String') {
                                if (typeof input.Context === 'object' && input.Context !== null) {
                                    input.Context = JSON.stringify(input.Context);
                                }
                                inputContent.innerHTML = input.Context.replace(/\n/g, '<br>');
                            } else if (input.Kind === 'Num') {
                                inputContent.textContent = input.Num;
                            } else if (input.Kind === 'Boolean' || input.Kind === 'Trigger') {
                                inputContent.textContent = input.Boolean;
                            }
                            inputDiv.appendChild(inputContent);
                            inputSection.appendChild(inputDiv);
                        });
                    }
                    
                    messageDiv.appendChild(inputSection);

                    // 显示Outputs部分
                    const outputSection = document.createElement('div');
                    outputSection.className = 'output-section';
                    const outputTitle = document.createElement('div');
                    outputTitle.className = 'section-title';
                    outputTitle.textContent = 'Outputs:';
                    outputSection.appendChild(outputTitle);

                    if (message.Outputs) {
                        message.Outputs.forEach(output => {
                            const outputDiv = document.createElement('div');
                            outputDiv.className = `output ${output.Kind ? output.Kind.toLowerCase() : 'string'}`;
                            const outputName = document.createElement('span');
                            outputName.className = 'output-name';
                            outputName.textContent = output.name + ': ';
                            outputDiv.appendChild(outputName);

                            const outputContent = document.createElement('span');
                            if (output.Kind === 'String') {
                                if (typeof output.Context === 'object' && output.Context !== null) {
                                    output.Context = JSON.stringify(output.Context);
                                }
                                outputContent.innerHTML= output.Context.replace(/\n/g, '<br>');
                            } else if (output.Kind === 'Num') {
                                outputContent.textContent = output.Num;
                            } else if (output.Kind === 'Boolean' || output.Kind === 'Trigger') {
                                outputContent.textContent = output.Boolean;
                            }
                            outputDiv.appendChild(outputContent);
                            outputSection.appendChild(outputDiv);
                        });
                    }
                    messageDiv.appendChild(outputSection);

                    chatBox.appendChild(messageDiv);
                }
            });
        });
    }

    window.SetProjsetName = function(filename) {
        //filename加json后缀
        filename = filename + '.json';
        fileSelect.value = filename;
        lastSelectedFile = filename;
        isFileSetByUser = true; // 设置标志
    }

    function fetchFiles() {
        fetch('/get_files')
            .then(response => response.json())
            .then(files => {
                console.log('文件获取成功:', files); // 日志输出
                if (files.length > 0) {
                    files.forEach(file => {
                        const option = document.createElement('option');
                        option.value = file;
                        option.textContent = file;
                        fileSelect.appendChild(option);
                    });
                    // 检查标志，决定是否自动选择第一个文件
                    if (!isFileSetByUser) {
                        lastSelectedFile = files[0];
                        fetchData(files[0]);
                    }
                }
            })
            .catch(error => console.error('获取文件时出错:', error));
    }

    function fetchData(file) {
        console.log('正在获取数据:', file);
        fetch(`/get_data?file=${file}`)
            .then(response => response.json())
            .then(data => {
                console.log('数据获取成功:', data); // 日志输出
                displayMessages(data);
            })
            .catch(error => console.error('获取数据时出错:', error));
    }

    fileSelect.addEventListener('change', function() {
        const selectedFile = fileSelect.value;
        lastSelectedFile = selectedFile;
        fetchData(selectedFile);
    });

    function checkForUpdates() {
        if (lastSelectedFile) {
            console.log('检查更新:', lastSelectedFile);
            fetchData(lastSelectedFile);
        }
    }
    RefreshButton.addEventListener('click', function() {
        checkForUpdates();
    });
    fetchFiles();

});

