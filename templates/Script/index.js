    const content = document.getElementById('content');
    let scale = 1;
    const windowSize = getWindowSize();
    let ZoomTime=0;//放大次数
    // 计算 content 中心的位置
    function centerContent()
    {
        const windowSize = getWindowSize();
        const contentSize = {
            width: content.offsetWidth,
            height: content.offsetHeight
        };

        // 将 #content 移动到视窗中心
        const left = (windowSize.width - contentSize.width) / 2;
        const top = (windowSize.height - contentSize.height) / 2;
        content.style.left = `${left}px`;
        content.style.top = `${top}px`;
    }

    // 计算并存储 content 中心的位置
    centerX = (content.offsetWidth - windowSize.width) / 2;
    centerY = (content.offsetHeight - windowSize.height) / 2;

    // 设置初始视图位置
    window.scrollTo(centerX, centerY);

  

    // 获取窗口大小
    function getWindowSize() 
    {
        return {
            width: window.innerWidth,
            height: window.innerHeight
        };
    }

    // 更新缩放并确保 content 不小于屏幕大小
function updateScale() 
{
    
}
function adjustContentPosition() 
{
    const windowSize = getWindowSize();
    let newLeft = parseInt(content.style.left, 10) || 0;
    let newTop = parseInt(content.style.top, 10) || 0;

    // 检查并调整位置以确保 content 边缘不超出屏幕
    if (newLeft > 0) newLeft = 0;
    if (newTop > 0) newTop = 0;
    if ((-newLeft + windowSize.width) / scale > content.offsetWidth) {
        newLeft = -(content.offsetWidth * scale - windowSize.width);
    }
    if ((-newTop + windowSize.height) / scale > content.offsetHeight) {
        newTop = -(content.offsetHeight * scale - windowSize.height);
    }

    content.style.left = newLeft + 'px';
    content.style.top = newTop + 'px';
}      

    document.getElementById('zoom-in').addEventListener('click', () => {
        if(ZoomTime<10){
            ZoomTime++;
            scale += 0.2;
        updateScale();
        }
        
    });
    document.getElementById('zoom-out').addEventListener('click', () => {
        if(ZoomTime>-10){
            ZoomTime--;
            scale = Math.max(0.2, scale - 0.2);
            updateScale();
        }
    });
    document.addEventListener('wheel', function(event) {
        if (event.ctrlKey) {
            event.preventDefault();  // 阻止默认缩放行为
            if (event.deltaY < 0) {
                console.log('执行向前滚动的自定义行为');
                // 自定义向前滚动时的行为
            } else if (event.deltaY > 0) {
                console.log('执行向后滚动的自定义行为');
                // 自定义向后滚动时的行为
            }
        }
}, { passive: false });

    function getCenterCoordinates() 
    {
        const rect = content.getBoundingClientRect(); // 获取元素相对于视口的位置
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;

        return { centerX, centerY };
    }

    // 监听窗口大小变化
    window.addEventListener('resize', updateScale);

    // 初始化时执行一次以设置初始缩放
    updateScale();
    //窗口大小
    let isDragging = false;
    let prevX, prevY;
    //
    
    document.addEventListener('mousedown', (event) => {
        // 检查是否是鼠标左键被按下
        if (event.button === 0 && event.target === content) {
            isDragging = true;
            prevX = event.clientX;
            prevY = event.clientY;
        }

    document.addEventListener('mousemove', (event) => {
        if (isDragging) {
                const newX = event.clientX;
                const newY = event.clientY;
                const dx = newX - prevX;
                const dy = newY - prevY;

                content.style.left = (content.offsetLeft + dx) + 'px';
                content.style.top = (content.offsetTop + dy) + 'px';

                prevX = newX;
                prevY = newY;

                //adjustContentPosition();  // 确保重新启用此行
            }
    });



        document.addEventListener('mouseup', () => {
            isDragging = false;
        });
    });
    $(document).ready(function() {
        $("#content").contextmenu(function(e) {
            e.preventDefault();
            $("#context-menu").css("top", e.pageY).css("left", e.pageX).show();
        });

        $(document).click(function() {
            $("#context-menu").hide();
        });

        $("#create-option").mouseenter(function() {
        $.getJSON('/get-python-files', function(data) {
            // 清除旧的文件列表
            $("#context-menu ul").empty();
            // 添加新的文件列表
            data.forEach(function(file) {
                // 创建新的列表项并绑定点击事件
                var listItem = $("<li>" + file + "</li>").click(function() {
                    //去除后缀.py
                    let filename_without_ext = file.replace(".py", "")
                    MakeNode(file, event.clientX, event.clientY);
                });
                $("#context-menu ul").append(listItem);
            });
        });
    });


});

// 定义 MakeNode 函数
function MakeNode(nodeName, x, y) {
    fetch(`/get-node-details/${nodeName}`)
    .then(response => response.json())
    .then(data => {
        //console.log('Node details:', data);
        
        if (data.InPutName && data.OutPutName) {
                const xPosition = x + window.scrollX;
                const yPosition = y + window.scrollY;
                console.log('位置',x,y,xPosition,yPosition);
                const nodeContainer = $('<div class="node-container"></div>').css({
                    
                    position: 'absolute', // 确保使用绝对定位
                    left: `${xPosition}px`, // 使用调整后的x位置
                    top: `${yPosition}px` // 使用调整后的y位置
                });
                // 创建输入列
                const inputColumn = $('<div class="column inputs"></div>');
                data.InPutName.forEach(name => {
                    inputColumn.append(`<div class="input-name"><span class="circle"></span> ${name}</div>`);
                });

                // 创建输出列
                const outputColumn = $('<div class="column outputs"></div>');
                data.OutPutName.forEach(name => {
                    outputColumn.append(`<div class="output-name">${name} <span class="circle"></span></div>`);
                });

                // 将输入和输出列添加到节点容器中
                nodeContainer.append(inputColumn).append(outputColumn);
    
                // 添加节点容器到content
                $('#content').append(nodeContainer);

                // 计算宽度
                const additionalWidth = 0; // 这是额外添加的固定宽度值
                // 获取最宽的输入或输出名的宽度
                let maxWidth = 0;
                nodeContainer.find('.input-name').each(function() {
                    maxWidth += Math.max(maxWidth, $(this).width());
                });
                //console.log(maxWidth);
                nodeContainer.find('.output-name').each(function() {
                    maxWidth += Math.max(maxWidth, $(this).width());
                });
                //console.log(maxWidth);
                // 设置node-container的宽度为最大宽度+额外宽度
                nodeContainer.width((maxWidth + additionalWidth)/2);
            }
        })
        .catch(error => {
            console.error('Error fetching node details:', error);
        });
    }
