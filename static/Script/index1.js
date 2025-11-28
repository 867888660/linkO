   NodeNums=0;
   function initializeDragAndResize(Nodes,maxWidth,maxHeight) {
        NodeNum=NodeNums;
        NodeNums++;
        console.log("初始化",NodeNum);
        let onMove = false;
        let offsetX, offsetY;

        // 获取初始样式以便之后计算
        let oddStyle = window.getComputedStyle(Nodes);
        const content = document.getElementById('content'); // 假设这是外层容器，已正确设置
        // 假设 scaleX 和 scaleY 已在外部定义
        const dragElement = Nodes.querySelector(".drag-bar"); // 假设你的 Nodes 元素内部有 .drag-bar 元素
        if (dragElement) {
            dragElement.addEventListener("mousedown", function(e) {
                onMove = true;
                const contentRect = content.getBoundingClientRect();
                // 考虑缩放和content位置，调整鼠标位置计算
                offsetX = (e.clientX - contentRect.left) / scaleX - parseFloat(oddStyle.left);
                offsetY = (e.clientY - contentRect.top) / scaleY - parseFloat(oddStyle.top);
                document.addEventListener("mousemove", onMouseMove);
                document.addEventListener("mouseup", onMouseUp);
            });
        }


        let svg = null; // 用于跟踪当前的SVG元素
        let path = null; // 用于跟踪当前的路径元素
        let startNode;
        let lining = false;
        let liningObject = {
            svg,
            path,
            lining,
            startElement: null
        }
        let startX, startY; // 起始点
       const stopLining = (event, obj) => {
            event.stopPropagation();
           if (obj.lining) {
               console.log('stop line')
               const line = obj.svg.cloneNode(true);
                const main = document.getElementById('content');
                line.style.pointerEvents = 'none';
                line.style.zIndex = '99';
                const paths = line.childNodes;
                for (let i = 0; i < paths.length; i++) {
                    const path1 = paths[i];
                    path1.style.pointerEvents = 'all';
                }
                event.target.style.backgroundColor = '#06a6f6';
                main.append(line);
                obj.svg.remove(); // 移除SVG元素
                obj.svg = null;
                obj.path = null;
                obj.lining  = false;
           }
        }
        const startLining = (event) => {
            const circle = event.target
            const circleRect = circle.getBoundingClientRect(); // 获取最新的.circle边界
            const contentRect = document.getElementById('content').getBoundingClientRect(); // 获取最新的content边界
            startNode = circle;
            // 计算 .circle 中心点的位置，相对于 content 元素（没有缩放时scaleX和scaleY为1）
            startX = (circleRect.left + circleRect.width / 2 - contentRect.left) / scaleX;
            startY = (circleRect.top + circleRect.height / 2 - contentRect.top) / scaleY;
            // console.log('起始点',startX,startY);
            // 创建SVG元素
            liningObject.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            liningObject.svg.setAttribute('style', 'position: absolute; left: 0; top: 0; overflow: visible; width: 100%; height: 100%');
            document.getElementById('lineContainer').appendChild(liningObject.svg);

            // 创建路径元素
            liningObject.path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            liningObject.path.setAttribute('stroke', 'black');
            liningObject.path.setAttribute('stroke-width', '2');
            liningObject.path.setAttribute('fill', 'none');
            liningObject.svg.appendChild(liningObject.path);

            event.preventDefault();
            circle.style.backgroundColor = '#06a6f6';
            liningObject.lining = true;
            liningObject.startElement = circle
            console.log(liningObject);
        }
    // 为 Nodes 内的所有 .circle 元素添加事件监听器
    Nodes.querySelectorAll('.circle').forEach(circle => {
        circle.addEventListener('mousedown', startLining);

        document.addEventListener('mousemove', (event) => {
            if (liningObject.lining) {
                const contentRect = document.getElementById('content').getBoundingClientRect(); // 再次获取 'content' 的当前位置和尺寸
                // 计算鼠标位置相对于 'content' 元素的偏移
                const endX = (event.clientX - contentRect.left) / scaleX;
                const endY = (event.clientY - contentRect.top) / scaleY;
                // console.log('终止点',endX,endY);
                // 更新路径使用贝塞尔曲线。这里假设起始点(startX, startY)已经根据 '.circle' 的中心设置好
                const d = `M ${startX},${startY} C ${(startX + endX) / 2},${startY} ${(startX + endX) / 2},${endY} ${endX},${endY}`;
                liningObject.path.setAttribute('d', d);
            }
        });

        document.addEventListener('mouseup', (event) => {
            if (liningObject.lining && !/circle/.test(event.target.className)) {
                liningObject.svg.remove(); // 移除SVG元素
                liningObject.svg = null;
                liningObject.path = null;
                liningObject.circle.style.backgroundColor = '#ffffff'; // 恢复circle的样式为白色
                liningObject.lining = false;
            } else if (liningObject.lining && /circle/.test(event.target.className)) {
                if (event.target === liningObject.startElement) {
                    liningObject.svg.remove(); // 移除SVG元素
                    liningObject.svg = null;
                    liningObject.path = null;
                    liningObject.circle.style.backgroundColor = '#ffffff'; // 恢复circle的样式为白色
                    liningObject.lining = false;
                }
                stopLining(event, liningObject)
            }
        });

        // circle.addEventListener('mouseup', stopLining)
     });


        function onMouseMove(e) {
            if (onMove) {
                const contentRect = content.getBoundingClientRect();
                let boxWidth = parseFloat(oddStyle.width);
                let boxHeight = parseFloat(oddStyle.height);
                // 考虑缩放和content位置，调整元素新位置的计算
                let newX = (e.clientX - contentRect.left) / scaleX - offsetX;
                let newY = (e.clientY - contentRect.top) / scaleY - offsetY;
                newX = Math.min(content.clientWidth / scaleX - boxWidth, Math.max(0, newX));
                newY = Math.min(content.clientHeight / scaleY - boxHeight, Math.max(0, newY));
                Nodes.style.left = `${newX}px`;
                Nodes.style.top = `${newY}px`;
            }
        }

        function onMouseUp() {
            onMove = false;
            document.removeEventListener("mousemove", onMouseMove);
            document.removeEventListener("mouseup", onMouseUp);
        }
        // 边缘调整大小的初始化
        resizeOnEdge(Nodes, ".edge-right", "width",maxWidth);
        resizeOnEdge(Nodes, ".edge-left", "width",maxWidth);
        resizeOnEdge(Nodes, ".edge-top", "height",maxHeight);
        resizeOnEdge(Nodes, ".edge-bottom", "height",maxHeight);
    }

    function resizeOnEdge(Nodes, edgeClass, moveAxis,maxNum) {
        const target = Nodes.querySelector(edgeClass);
        const content = document.getElementById('content'); // 获取缩放容器
        // 假设scaleX和scaleY变量已经根据容器的缩放比例进行了设置
        if (!target) return;

        target.addEventListener("mousedown", function(e) {
            const contentRect = content.getBoundingClientRect();
            let startWidth = parseFloat(window.getComputedStyle(Nodes).width);
            let startHeight = parseFloat(window.getComputedStyle(Nodes).height);
            let startX = (e.clientX - contentRect.left) / scaleX;
            let startY = (e.clientY - contentRect.top) / scaleY;
            let startPos = { left: parseFloat(Nodes.style.left || 0), top: parseFloat(Nodes.style.top || 0) };

            function onMouseMove(e) {
                let mouseX = (e.clientX - contentRect.left) / scaleX;
                let mouseY = (e.clientY - contentRect.top) / scaleY;
                let deltaWidth = mouseX - startX;
                let deltaHeight = mouseY - startY;

                if (moveAxis === "width") {

                    if (edgeClass.includes("-left")) {
                        let newWidth = startWidth - deltaWidth;
                        Nodes.style.width = `${Math.max(maxNum, newWidth)}px`;
                        Nodes.style.left = `${startPos.left + deltaWidth}px`;
                    }
                    else
                    {
                        let newWidth = startWidth + deltaWidth;
                        Nodes.style.width = `${Math.max(maxNum, newWidth)}px`;
                    }

                } else if (moveAxis === "height") {

                    if (edgeClass.includes("-top")) {
                        let newHeight = startHeight - deltaHeight;
                        Nodes.style.top = `${startPos.top + deltaHeight}px`;
                        Nodes.style.height = `${Math.max(maxNum, newHeight)}px`;
                    }
                    else
                    {
                        let newHeight = startHeight + deltaHeight;
                        Nodes.style.height = `${Math.max(maxNum, newHeight)}px`;
                    }
                }
            }

            function onMouseUp() {
                document.removeEventListener("mousemove", onMouseMove);
                document.removeEventListener("mouseup", onMouseUp);
            }

            document.addEventListener("mousemove", onMouseMove);
            document.addEventListener("mouseup", onMouseUp);
            e.preventDefault();
        });
    }





    //分割边框
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
        //const left = (windowSize.width - contentSize.width) / 2;
        //const top = (windowSize.height - contentSize.height) / 2;
       // content.style.left = `${left}px`;
        //content.style.top = `${top}px`;
    }

    // 计算并存储 content 中心的位置
    //centerX = (content.offsetWidth - windowSize.width) / 2;
    //centerY = (content.offsetHeight - windowSize.height) / 2;

    // 设置初始视图位置
    //window.scrollTo(centerX, centerY);



    // 获取窗口大小
    function getWindowSize()
    {
        return {
            width: window.innerWidth,
            height: window.innerHeight
        };
    }

    // 更新缩放并确保 content 不小于屏幕大小

function adjustContentPosition()
{
    const windowSize = getWindowSize();
    let newLeft = parseInt(content.style.left, 10) || 0;
    let newTop = parseInt(content.style.top, 10) || 0;

    // 检查并调整位置以确保 content 边缘不超出屏幕

    if ((-newLeft + windowSize.width) / scale > content.offsetWidth) {
        newLeft = -(content.offsetWidth * scale - windowSize.width);
    }
    if ((-newTop + windowSize.height) / scale > content.offsetHeight) {
        newTop = -(content.offsetHeight * scale - windowSize.height);
    }
    if (newLeft > 0) newLeft = 0;
    if (newTop > 0) newTop = 0;
    console.log(newLeft,newTop)
    content.style.left = newLeft + 'px';
    content.style.top = newTop + 'px';
}

    let scaleX = 1; // 初始X轴缩放级别
    let scaleY = 1; // 初始Y轴缩放级别

    function updateScale() {
        const content = document.getElementById('content');
        const contentRect = content.getBoundingClientRect();

        // 计算视窗中心坐标
        const viewportCenterX = window.innerWidth / 2;
        const viewportCenterY = window.innerHeight / 2;
        // 鼠标相对于content的位置（考虑缩放）
        const mouseX = viewportCenterX - contentRect.left;
        const mouseY = viewportCenterY - contentRect.top;

        // 计算缩放中心点在content内的百分比位置（保持不变）
        const originX = mouseX / contentRect.width;
        const originY = mouseY / contentRect.height;

        // 根据滚轮方向调整缩放级别
        const scaleFactor = 1.02;
        scaleX *= scaleFactor;
        scaleY *= scaleFactor;
        scaleX = Math.min(Math.max(scaleX, 0.5), 2);
        scaleY = Math.min(Math.max(scaleY, 0.5), 2);
        // 设置缩放中心
        content.style.transformOrigin = `${originX * 100}% ${originY * 100}%`;
        content.style.transform = `scale(${scaleX}, ${scaleY})`;

        // 限制缩放级别在 0.5 到 2 倍之间

    }


    function zoomIn() {
        // 假设我们限制最大缩放为2倍
        if (scaleX < 2) {
            scaleX *= 1.1;
            scaleY *= 1.1; // 保持scaleY与scaleX同步
            updateScale();
        }
    }

    function zoomOut() {
        // 假设我们限制最小缩放为0.5倍
        if (scaleX > 0.5) {
            scaleX /= 1.1;
            scaleY /= 1.1; // 保持scaleY与scaleX同步
            updateScale();
        }
    }

    // 绑定缩放按钮事件监听器
    document.getElementById('zoom-in').addEventListener('click', zoomIn);
    document.getElementById('zoom-out').addEventListener('click', zoomOut);

    // 禁用Ctrl+加号/减号的默认页面缩放行为，并绑定自定义缩放操作
    document.addEventListener('keydown', function(event) {
        if (event.ctrlKey && (event.key === '+' || event.key === '-' || event.key === '=')) {
            event.preventDefault(); // 阻止默认行为
            if (event.key === '+' || event.key === '=') {
                zoomIn();
            } else if (event.key === '-') {
                zoomOut();
            }
        }
    }, { passive: false });

        document.addEventListener('wheel', function(event) {
            const content = document.getElementById('content');
            if (event.ctrlKey) {
                event.preventDefault();  // 阻止默认缩放行为

                const contentRect = content.getBoundingClientRect();
                // 鼠标相对于content的位置（考虑缩放）
                const mouseX = event.clientX - contentRect.left;
                const mouseY = event.clientY - contentRect.top;

                // 计算缩放中心点在content内的百分比位置（保持不变）
                const originX = mouseX / contentRect.width;
                const originY = mouseY / contentRect.height;

                // 根据滚轮方向调整缩放级别
                const scaleFactor = event.deltaY < 0 ? 1.02 : 1 / 1.02;
                scaleX *= scaleFactor;
                scaleY *= scaleFactor;
                // 设置缩放中心
                content.style.transformOrigin = `${originX * 100}% ${originY * 100}%`;
                content.style.transform = `scale(${scaleX}, ${scaleY})`;

                // 限制缩放级别在 0.5 到 2 倍之间
                scaleX = Math.min(Math.max(scaleX, 0.5), 2);
                scaleY = Math.min(Math.max(scaleY, 0.5), 2);
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
                let finalX = content.offsetLeft + dx / scale
                let finalY = content.offsetTop + dy / scale
                const parent = content.parentElement;
                const ph = parent.offsetHeight;
                const pw = parent.offsetWidth;
                if (finalX > 0 ) finalX = 0
                if (finalY > 0 ) finalY = 0
                const height = parseInt(getComputedStyle(content).height);
                const width = parseInt(getComputedStyle(content).width);
                if (finalX < -width + pw ) finalX = -width + pw
                if (finalY < -height + ph ) finalY = -height + ph
                content.style.left = (finalX) + 'px';
                content.style.top = (finalY) + 'px';
                prevX = newX;
                prevY = newY;
                //adjustContentPosition();  // 确保重新启用此行
            }
    });



        document.addEventListener('mouseup', () => {
            isDragging = false;
        });
    });
    document.addEventListener('DOMContentLoaded', function() {
        var content = document.getElementById('content');
        var contextMenu = document.getElementById('context-menu');
        var createOption = document.getElementById('create-option');

        content.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            contextMenu.style.top = e.pageY + 'px';
            contextMenu.style.left = e.pageX + 'px';
            contextMenu.style.display = 'block';
        });

        document.addEventListener('click', function() {
            contextMenu.style.display = 'none';
        });

        createOption.addEventListener('mouseenter', function() {
            fetch('/get-python-files')
                .then(response => response.json())
                .then(data => {
                    // 清除旧的文件列表
                    var ul = contextMenu.querySelector('ul');
                    ul.innerHTML = ''; // 清空列表
                    // 添加新的文件列表
                    data.forEach(function(file) {
                        var listItem = document.createElement('li');
                        listItem.textContent = file;
                        listItem.addEventListener('click', function(event) {
                            //去除后缀.py
                            let filename_without_ext = file.replace(".py", "");
                            MakeNode(filename_without_ext, event.clientX, event.clientY);
                        });
                        ul.appendChild(listItem);
                    });
                })
                .catch(error => console.error('Error:', error));
        });
    });

    function createNodesElement(data, xPosition, yPosition) {
        console.log(data);
        const Nodes = document.createElement('div');
        Nodes.className = 'Nodes';
        Nodes.style.position = 'absolute';
        Nodes.style.left = `${xPosition}px`;
        Nodes.style.top = `${yPosition}px`;

        // 创建 .drag-bar 并添加图标
        const dragBar = document.createElement('div');
        dragBar.className = 'drag-bar';
        Nodes.appendChild(dragBar);

        // 添加图标到 .drag-bar
        const icons = ['w-out', 'w-narrow', 'w-ext'];
        icons.forEach(iconClass => {
            const icon = document.createElement('div');
            icon.className = iconClass;
            dragBar.appendChild(icon);
        });

        // 创建 .Vessel 并设置内容
        const vessel = document.createElement('div');
        vessel.className = 'Vessel';

        Nodes.appendChild(vessel);

        // 创建边缘可拖动区域
        const edges = ['edge-top', 'edge-bottom', 'edge-right', 'edge-left'];
        edges.forEach(edgeClass => {
            const edge = document.createElement('div');
            edge.className = `edge ${edgeClass}`;
            Nodes.appendChild(edge);
        });

        // 创建角落可拖动区域
        const corners = ['corner-lt', 'corner-lb', 'corner-rt', 'corner-rb'];
        corners.forEach(cornerClass => {
            const corner = document.createElement('div');
            corner.className = `corner ${cornerClass}`;
            Nodes.appendChild(corner);
        });
        const inputColumn = document.createElement('div');
        inputColumn.className = 'column inputs';
        data.InPutName.forEach(name => {
            const inputName = document.createElement('div');
            inputName.className = 'input-name';
            inputName.innerHTML = `<span class="circle"></span> ${name}`;
            inputColumn.appendChild(inputName);
        });

        // 创建输出列
        const outputColumn = document.createElement('div');
        outputColumn.className = 'column outputs';
        data.OutPutName.forEach(name => {
            const outputName = document.createElement('div');
            outputName.className = 'output-name';
            outputName.innerHTML = `${name} <span class="circle"></span>`;
            outputColumn.appendChild(outputName);
        });

        // 将输入和输出列添加到节点容器中
        vessel.appendChild(inputColumn);
        vessel.appendChild(outputColumn);
        // 添加元素到 DOM
        Nodes.appendChild(vessel);

        // 使用 requestAnimationFrame 确保渲染完成
        requestAnimationFrame(() => {
            let maxWidth = 0;
            let maxHeight = 0;
            vessel.querySelectorAll('.input-name, .output-name').forEach(element => {
                const rect = element.getBoundingClientRect();
                maxWidth = Math.max(maxWidth, rect.width);
                maxHeight += rect.height; // 计算总高度
            });
            // 更新宽度和高度设置

            initializeDragAndResize(Nodes,maxWidth + 150,maxHeight+20);
            Nodes.style.width = `${(maxWidth + 150)}px`; // 假设额外宽度为20px
            Nodes.style.height = `${(maxHeight + 20)}px`; // 假设额外高度为20px
            // 更新列的位置，使它们水平布局
            inputColumn.style.position = 'absolute';
            inputColumn.style.left = '5px'; // 输入列在左侧
            inputColumn.style.top = '30px'; // 置顶对齐

            outputColumn.style.position = 'absolute';
            outputColumn.style.right = '5px'; // 输出列在右侧
            outputColumn.style.top = '30px'; // 置顶对齐

        });

        // 将 .Nodes 添加到页面的指定容器中
        document.getElementById('content').appendChild(Nodes);
    }


// 定义 MakeNode 函数
        function MakeNode(nodeName, x, y) {
            fetch(`/get-node-details/${nodeName}`)
            .then(response => response.json())
            .then(data => {
                if (data.InPutName && data.OutPutName) {
                    const contentRect = document.getElementById('content').getBoundingClientRect();

                    // 计算鼠标在content内的相对位置
                    // 减去content的边界偏移量
                    const scaleAdjustedX = (x - contentRect.left) / scaleX;
                    const scaleAdjustedY = (y - contentRect.top) / scaleY;
                    // 创建节点容器


                    createNodesElement(data,scaleAdjustedX,scaleAdjustedY);

                    // 创建输入列

                }
            })
            .catch(error => {
                console.error('Error fetching node details:', error);
            });
}
