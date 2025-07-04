
let graph;
let domBlocks = [];
let SaveGraph=[];
let IsFirstRunArrayTrigger = false;
let NowNode;
let visualCenter = { x: 0, y: 0 };
let lastPosition = { x: 0, y: 0 };
let isDragging = false;
let fileList;
let FilePath='WorkFlow'
let CopyNodeTemp;
let FileName='';
let Callsign='';
let HostPost='localhost:8000';//默认的主机地址
let ProjectName='Temp';
let TemptNum=0;//临时使用的数据
let MemoryIndex=-1;
let passivityTriggerArray = [];
let ArrayTriggerArray = [];
let IsTriggerNode = true; // 假设这个变量在其他地方被定义
let IsRunningFunction = false;
let TempMessageNode;
let workflowFileList = [];
let draggedWorkflowNode = null;
//#region 浮窗栏
const tooltip = document.createElement('div');
tooltip.className = 'tooltip';
document.body.appendChild(tooltip);
//#endregion
// 请求所有节点信息 todo：如果需要更新的，建议发通知更新或者定时拉取
const requestNodeList = async () => {
  const res = await fetch('/get-python-files');
  return await res.json();
};

const refreshFileList = async () => {
  fileList = await requestNodeList();
  console.log('Updated file list:', fileList);
};

refreshFileList();
const History_project = async () => {
  const res = await fetch('/history-project', {
    method: 'POST'
  });
  return await res.json();
}

const getHistoryItem = async () => {
  const HistoryItem = await History_project();
  console.log('载入记录',HistoryItem);
  let name = HistoryItem.name;
  let path = HistoryItem.path;
  HostPost=HistoryItem.host;
  Callsign=HistoryItem.callsign;
  FilePath = path;
  console.log('载入记录',name,path,HostPost);
  document.title = FileName.substring(FileName.lastIndexOf(':') + 1);
  ProjectName=name;
  if(Callsign!=null)
    document.title=Callsign+':'+name.replace('.json','');
  if (path === "WorkFlow\\WorkFlow") {
    path = "WorkFlow";
  }

  // 去除路径
  // path = path.split('/').pop();
  // 去除后缀
  // name = name.split('.json')[0];
  console.log('载入记录',name,path);  
  fetch('/get-project-files', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ json_name: name ,json_path: path })
  })
  .then(response => response.json())
  .then(data => {
    console.log(data);
    LoadWorkFlow(data,name,HostPost,Callsign);
    // 在这里处理返回的JSON数据
  })
  
};

// 调用函数以执行请求
getHistoryItem();



// 请求节点详细信息
const requestNodeInfo = async (nodeName) => {
  const res = await fetch(`/get-node-details/${nodeName}`)
  return await res.json()
}

//删除节点
const removeNode = (item) => {
  graph.remove(item);
  RefreshEdge();
};
// 删除边
const removeEdge = (item) => {
  graph.remove(item);
  RefreshEdge();
};
const OpenCode = async (item) => {
  const n = item.name.split('.py')[0];
  const res = await fetch(`/open-code-editor`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ name: `${n}.py` }),
  });

  if (res.ok) {
    const data = await res.json();
    if (data.status === 'success') {
      console.log('File opened successfully in VSCode');
    } else {
      console.error('Failed to open file:', data.error);
    }
  } else {
    const errorData = await res.json();
    console.error('Error:', errorData.error);
  }
};

const runNode = (item) => {
  const isCheckMode = document.getElementById('runButton').textContent !== '运行';
  createSideWindow(item, isCheckMode);
};
async function NodeDetail(item, event) {
  // event兼容处理
  event = event || window.event;

  // 异步请求节点列表数据
  const fileList = await requestNodeList();
  console.log('Updated file list:', item, fileList);

  // 获取节点信息
  const n = item.name.split('.py')[0];
  const nodeInfo = fileList.find(node => node.filename === `${n}.py`);

  /* ---------- 彻底反转义，保留真实换行 ---------- */
  const introductionText = nodeInfo.NodeFunction
    .replace(/\\\\/g, '\\')   // \\  →  \
    .replace(/\\n/g, '\n')    // \n → 换行
    .replace(/\\"/g, '"')     // \" → "
    .replace(/\\</g, '<')     // \< → <
    .replace(/\\>/g, '>');    // \> → >

  /* ---------- 首行放脚本名 ---------- */
  const windowIntroduce =
    `${nodeInfo.filename.replace(/\.py$/, '')}\n${introductionText}`;

  /* ---------- 创建浮窗 ---------- */
  const floatingWindow = document.createElement('div');
  floatingWindow.classList.add('node-detail-floating-window');

  /* 直接用 textContent + white-space: pre-line 渲染换行 */
  floatingWindow.textContent = windowIntroduce;
  floatingWindow.style.whiteSpace = 'pre-line';

  // 设置浮窗样式
Object.assign(floatingWindow.style, {
  position: 'absolute',

  /* —— 黑白灰主配色 —— */
  backgroundColor: '#2a2a2a',      // 深灰背景（比纯黑柔和）
  border: '1px solid #4a4a4a',     // 略浅的边框灰
  color: '#ffffff',                // 字体白色
  fontWeight: '600',               // 加粗

  /* —— 细节保持一致 —— */
  padding: '12px',
  borderRadius: '8px',
  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.25)',  // 更深的阴影层次
  transition: 'opacity 0.8s ease-out',
  opacity: '1',
  zIndex: 1000,
  maxWidth: '300px',
  fontFamily: 'Arial, sans-serif',
  fontSize: '14px',
  lineHeight: '1.5'
});


  // 若获取到了点击位置，则在鼠标下方显示
  if (event && typeof event.clientX === 'number' && typeof event.clientY === 'number') {
    floatingWindow.style.top = (event.clientY + 10) + 'px';
    floatingWindow.style.left = (event.clientX + 10) + 'px';
  } else {
    floatingWindow.style.top = '150px';
    floatingWindow.style.left = '150px';
  }

  // 将浮窗添加到页面中
  document.body.appendChild(floatingWindow);

  // 定义淡出并移除浮窗的函数
  function fadeOutAndRemove() {
    floatingWindow.style.opacity = '0';
    setTimeout(() => {
      if (floatingWindow && floatingWindow.parentNode) {
        floatingWindow.parentNode.removeChild(floatingWindow);
      }
    }, 800);
  }

  // 定义一个 hideTimeout 用于控制 3 秒后自动消失
  let hideTimeout = null;

  // 开启 3 秒后自动淡出移除
  function startHideTimer() {
    // 如果已有计时器，则先清除
    clearHideTimer();
    hideTimeout = setTimeout(() => {
      fadeOutAndRemove();
    }, 3000);
  }

  // 清除自动移除计时器
  function clearHideTimer() {
    if (hideTimeout) {
      clearTimeout(hideTimeout);
      hideTimeout = null;
    }
  }

  // 初次加载后，开始倒计时
  startHideTimer();

  // 如果鼠标移入浮窗，清除自动消失计时
  floatingWindow.addEventListener('mouseenter', () => {
    clearHideTimer();
  });

  // 如果鼠标移出浮窗，重新开启自动消失计时
  floatingWindow.addEventListener('mouseleave', () => {
    startHideTimer();
  });

  // 如果用户点击浮窗，立即淡出移除
  floatingWindow.addEventListener('click', () => {
    fadeOutAndRemove();
  });
}



const changeEdge = (item) => {
  console.log('改变连线', item);
  //改变变得颜色并重新渲染
  graph.updateItem(item, {
    style: {
      stroke: 'red',
    }
  });
};
// 手动添加节点
const addcombo = (item,x,y) => {

  graph.addItem('combo', {
    id: 'combo1',
    label: 'Combo',
    x: x,
    y: y,
    width: 800,
    height: 600,
    size: [200, 200],
    padding: [20, 20, 20, 20],
    type: 'rect', // 确保是矩形
    style: {
      fill: 'rgba(255, 255, 255, 0.8)', // 设置透明度
      stroke: '#999',
      lineWidth: 3,
      radius: 4
    },
  }, [item._cfg.id]);
  const combo = {
    id: 'combo1',
    label: 'Combo',
    x: x,
    y: y,
    width: 800,
    height: 600,
    size: [200, 200],
    padding: [20, 20, 20, 20],
    type: 'rect', // 确保是矩形
    style: {
      fill: 'rgba(255, 255, 255, 0.8)', // 设置透明度
      stroke: '#999',
      lineWidth: 3,
      radius: 4
    },

  }
  graph.addItem('combo', combo);
}
const copyNode = (node, x, y) => {
  const n = node.name.split('.py')[0];

  requestNodeInfo(n).then((nodeInfo) => {
      const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
      const anchorPoints = node.Inputs.map((node, index) => {
        const anchorHeight = 60 + index * 20;
        return [0.05, anchorHeight / maxHeight]
      }).concat(node.Outputs.map((node, index) => {
        const anchorHeight = 60 + index * 20;
        return [0.95, anchorHeight / maxHeight]
      })).concat([[0, 0]]);
      const TempId=node.id;
      const TempNode1 = graph.save().nodes.find((node) => node.id === TempId);
      const TempId1=node.name + Date.now();
      let TempOutput=structuredClone(TempNode1.Outputs)
      TempOutput.forEach((output) => {
        output.Link=0;
      });
      let TempInput=structuredClone(TempNode1.Inputs)
      TempInput.forEach((input) => {
        input.Link=0;
      });
      const TempNode = {
        // 可以添加随机数或时间戳来达到重复导入的效果
        id: TempId1,
        name: node.name,
        label: node.name + graph.getNodes().length,
        x,
        IsHovor:false,
        y,
        TriggerLink:0,
        IsBlock:false,
        IsStartNode:false,
        IsRunning:false,
        IsError:false,
        isFinish:false,
        RecursionBehavior:node.RecursionBehavior || 'STOP',
        OriginalTextSelector:node.OriginalTextSelector,
        ErrorContext:'',
        Kind: node.Kind,
        ReTryNum:node.ReTryNum,
        prompt: node.prompt,
        ExportPrompt: node.ExportPrompt,
        ExprotAfterPrompt: node.ExprotAfterPrompt,
        TempOutPuts:node.TempOutPuts,
        anchorPoints,
        temperature:node.temperature,
        Top_p:node.Top_p,
        OriginalTextArray:node.OriginalTextArray,
        frequency_penalty:node.frequency_penalty,
        presence_penalty:node.presence_penalty,
        max_tokens:node.max_tokens,
        IsLoadSuccess:node.IsLoadSuccess,
        ...nodeInfo,

        // 深拷贝Outputs和Inputs，以确保它们在TempNode中是独立的
        Outputs: TempOutput,
        Inputs: TempInput,
    };

      graph.addItem('node', TempNode);

  });


}
const addNode = (name, x, y, Kind) => {
  const nodes = graph.save().nodes;
  const checkExistingNode = (nodeKind) => {
    return nodes.some(node => node.NodeKind.includes(nodeKind));
  };

  const handleExistingNode = (nodeKind) => {
    showMessage(`已经存在${nodeKind}节点`, '#ff0000');
    return true; // 表示存在重复节点
  };

  if (Kind.includes('passivityTrigger') && checkExistingNode('passivityTrigger')) {
    if (handleExistingNode('passivityTrigger')) return; // 直接终止函数执行
  }

  if (Kind.includes('ArrayTrigger') && checkExistingNode('ArrayTrigger')) {
    if (handleExistingNode('ArrayTrigger')) return; // 直接终止函数执行
  }
  // 获取容器的宽度和高度
  const width = graph.get('width');
  const height = graph.get('height');
  const center = graph
  const n = name.split('.py')[0];
  requestNodeInfo(n).then((nodeInfo) => {
    // ... 剩余的代码保持不变
    const maxHeight = Math.max(nodeInfo.Inputs.length, nodeInfo.Outputs.length) * 20 + 60;
    const anchorPoints = [
      ...nodeInfo.Inputs.map((_, index) => [0.05, (60 + index * 20) / maxHeight]),
      ...nodeInfo.Outputs.map((_, index) => [0.95, (60 + index * 20) / maxHeight]),
      [0, 0]
    ];
    let TempX=x-visualCenter.x;
    let TempY=y+visualCenter.y;
    const point = graph.getPointByClient(x, y);
    const node = {
      id: `${name}_${Date.now()}`,
      name: name,
      label: `${name.replace('.py', '')}${graph.getNodes().length}`,
      x: point.x,
      y: point.y,
      TriggerLink: 0,
      IsHovor: false,
      IsStartNode: false,
      IsBlock: false,
      IsRunning: false,
      isFinish: false,
      IsError: false,
      RecursionBehavior: 'STOP',
      OriginalTextSelector: 'Json',
      ErrorContext: '',
      Kind: Kind,
      prompt: '',
      ExportPrompt: '',
      ExprotAfterPrompt: '',
      ReTryNum: 0,
      anchorPoints,
      OriginalTextArray: [{
        'Num': null,
        'Kind': 'String',
        'Boolean': false,
        'Id': 'Output1',
        'Context': null,
        'name': 'OriginalText',
        'Link': 0,
        'Description': 'answer'
      }],
      TempOutPuts: [],
      Top_p: 0.9,
      temperature: 0.7,
      frequency_penalty: 0.0,
      presence_penalty: 0.0,
      max_tokens: 4096,
      ...nodeInfo
    };
    
    graph.addItem('node', node);
  }).catch(error => {
    console.error('Error adding node:', error);
    showMessage('添加节点时发生错误', '#ff0000');
    
  });
  setTimeout(() => {
      RefreshEdge(); 
    }, 10);
};

// 右键点击菜单实现
const contextMenu = new G6.Menu({
  getContent(evt) {
    let menu = '';
    if (evt.target && evt.target.isCanvas && evt.target.isCanvas()) {
      if (document.getElementById('runButton').textContent == '运行') {
        menu = `<div class="title">添加节点</div>`;
        refreshFileList();
        // 对 fileList 进行分组
        const groupedFiles = fileList.reduce((acc, file) => {
          // 只取 file.NodeKind 中 _ 前面的部分
          const key = file.NodeKind.split('_')[0];
        
          if (!acc[key]) {
            acc[key] = [];
          }
          acc[key].push(file);
          return acc;
        }, {});
        

        // 自定义样式设置
        const titleStyle = {
          fontSize: '20px',
          color: '#000',
          fontWeight: 'bold', // 'normal' or 'bold'
          fontFamily: 'Arial, sans-serif'
        };

        // 按分类生成菜单
        Object.keys(groupedFiles).forEach(kind => {
          menu += `<div class="node-kind" style="font-size: ${titleStyle.fontSize}; color: ${titleStyle.color}; font-weight: ${titleStyle.fontWeight}; font-family: ${titleStyle.fontFamily};"><strong>${kind}</strong></div>`;
          groupedFiles[kind].forEach(file => {
            const fileName = file.filename.replace(/\.py$/, ''); // 移除 .py 后缀
            menu += `<div class="menu-item" data-behavior="addNode"  data-canvasx="${evt.canvasX}" data-canvasy="${evt.canvasY}" data-Kind="${file.NodeKind}">${fileName}</div>`;
          });
        });
      }
    } else if (evt.item) {
      const itemType = evt.item.getType();
      if (itemType === 'node') {
        if (document.getElementById('runButton').textContent == '运行') {
          menu = `
            <div class="menu-item" data-behavior="removeNode">删除节点</div>
            <div class="menu-item" data-behavior="copyNode" data-canvasx="${evt.canvasX}" data-canvasy="${evt.canvasY}">复制节点</div>
            <div class="menu-item" data-behavior="OpenCode">打开源代码</div>
            <div class="menu-item" data-behavior="runNode">运行单个节点</div>
            <div class="menu-item" data-behavior="NodeDetail">节点注释</div>
          `;
        } else {
          menu = `
            <div class="menu-item" data-behavior="runNode">检查单个节点</div>
          `;
        }
      } else if (itemType === 'edge') {
        menu = `
          <div class="menu-item" data-behavior="removeEdge">删除连线</div>
          <div class="menu-item" data-behavior="changeEdge">改变连线</div>
        `;
      } else if (itemType === 'combo') {
        menu = `
          <div class="menu-item" data-behavior="removeNode">删除Combo</div>
        `;
      }
    }
    return `<div class="new-context-menu">${menu}</div>`;
  },
  handleMenuClick: (target, item) => {
    const targetText = target.dataset.behavior;
    switch (targetText) {
      case 'addNode':
        addNode(target.innerText, target.dataset.canvasx, target.dataset.canvasy, target.dataset.Kind);
        break;
      case 'addCombo':
        addcombo(item, target.dataset.canvasx, target.dataset.canvasy);
        break;
      case 'removeNode':
        removeNode(item);
        break;
      case 'copyNode':
        copyNode(item.getModel(), target.dataset.canvasx, target.dataset.canvasy);
        break;
      case 'removeEdge':
        removeEdge(item);
        break;
      case 'runNode':
        runNode(item.getModel());
        break;
      case 'OpenCode':
        OpenCode(item.getModel());
        break;
      case 'changeEdge':
        changeEdge(item);
        break;
      case 'NodeDetail':
        NodeDetail(item.getModel());
        break;
      default:
        break;
    }
  },
  offsetX: 0,
  offsetY: 0,
  itemTypes: ['node', 'edge', 'canvas'],
});


// 实现自定义节点
G6.registerCombo('resizable-combo', {
  drawShape(cfg, group) {
    const { size } = cfg;
    const width = size[0];
    const height = size[1];
    const shape = group.addShape('rect', {
      attrs: {
        x: -width / 2,
        y: -height / 2,
        width,
        height,
        fill: cfg.style.fill,
        stroke: cfg.style.stroke,
      },
      draggable: true,
      name: 'combo-rect',
    });
    // 添加四个控制点
    const points = [
      [-width / 2, 0], // 左侧中点
      [width / 2, 0], // 右侧中点
      [0, -height / 2], // 上侧中点
      [0, height / 2], // 下侧中点
    ];
    points.forEach((point, index) => {
      group.addShape('circle', {
        attrs: {
          x: point[0],
          y: point[1],
          r: 5,
          fill: 'red',
        },
        name: `resize-handle-${index}`,
        draggable: true,
      });
    });
    return shape;
  },
});
/* ========= 统一状态名 ========= */
const STATE = {
  RED    : 'linkRed',     // 错误 / 悬停高亮
  BLUE   : 'linkBlue',    // 节点悬停高亮
  GREEN  : 'linkGreen',   // 成功
  ORANGE : 'linkOrange',  // IfNode ➜ 普通分支
  PURPLE : 'linkPurple',  // IfNode ➜ STOP 分支
  FLOW   : 'linked'       // 流动动画
};

/* ========= 自定义线条 ========= */
G6.registerEdge('line-dash', {
  /* ---- 状态响应 ---- */
  setState(name, value, edge) {
    const shape = edge.getKeyShape();

    // ★ 统一恢复底色 ★
    const back = () => {
      const s   = edge.getStates();
      const set = (c, w) =>
        shape.attr({ stroke:c, lineWidth:w, shadowBlur:0, opacity:1 });

      if      (s.includes(STATE.RED))    set('#ff4d4f', 6);
      else if (s.includes(STATE.BLUE))   set('#32d7ff', 5);
      else if (s.includes(STATE.GREEN))  set('#30c57b', 4);
      else if (s.includes(STATE.ORANGE)) set('#fa8c16', 4);  // 优化后的橘色
      else if (s.includes(STATE.PURPLE)) set('#e205ff', 4);  // 优化后的深紫
      else                               set('#000',     3); // ← 纯黑默认
    };
    switch (name) {
      /* ——— 高亮 ——— */
      case STATE.RED:
        value ? shape.attr({ stroke:'#ff4d4f', lineWidth:6, shadowColor:'#ff6d6f', shadowBlur:8 })
              : back();
        break;
      case STATE.BLUE:
        value ? shape.attr({ stroke:'#32d7ff', lineWidth:5, shadowColor:'#32d7ff', shadowBlur:8 })
              : back();
        break;

      /* ——— 常驻底色 ——— */
      case STATE.GREEN:  if (value) back(); else back(); break;
      case STATE.ORANGE: if (value) back(); else back(); break;
      case STATE.PURPLE: if (value) back(); else back(); break;

      /* ——— 流动动画 ——— */
      case STATE.FLOW:
        if (value) {
          let i = 0;
          shape.animate(() => {
            i = (i + 1) % 12;
            return {
              lineDash: [12, 6],
              lineDashOffset: -i
            };
          }, { repeat:true, duration:3000, easing:'easePolyInOut' });
        } else {
          shape.stopAnimate();
          shape.attr({ lineDash:null, lineDashOffset:0 });
        }
        break;

      default: break;
    }
  },

  /* ---- 贝塞尔控制点（保持你的逻辑） ---- */
  getControlPoints(cfg) {
    const { startPoint, endPoint } = cfg;
    const midX   = (startPoint.x + endPoint.x - 100) / 2;
    const segLen = 20;
    return [
      { x: midX,                 y: startPoint.y },
      { x: endPoint.x - 100,     y: endPoint.y },
      { x: endPoint.x - segLen/2,y: endPoint.y }
    ];
  },

  /* ---- 默认样式（美化阴影、圆角端点） ---- */
  options: {
    style: {
      lineWidth : 3,
      stroke    : '#666',
      endArrow  : {
        path     : 'M 0,0 L 6,3 L 0,6 Z',
        d        : 6,
        fill     : '#666'
      },
      lineAppendWidth : 8,    // 提高可点击范围
      shadowBlur      : 0,    // 默认无阴影，高亮时会加
      shadowColor     : '#666',
      lineCap         : 'round'
    }
  }
}, 'cubic');
/* ========= 自定义节点 ========= */

G6.registerNode('fileNode', {
  draw(cfg, group) {
    let maxHeight =1;
    //先判定cfg.Inputs和Outputs的长度是否存在
    if(cfg.Inputs==undefined)
    {
      cfg.Inputs=[];
    }
    if(cfg.Outputs==undefined)
    {
      cfg.Outputs=[];
    }
    maxHeight = Math.max(cfg.Inputs.length, cfg.Outputs.length)  
    let maxWidth = 0;
    cfg.draggable = false;
    cfg.Inputs.map((input, index) => {
      let Temp=''
      const maxDisplayLength = 50;
      if(input.IsLabel == true) {
          if(input.Kind .includes('String')) {
              Temp = ':' + truncateTextWithEllipsis(input.Context, maxDisplayLength);
          }
          if(input.Kind == 'Num') {
              Temp = ':' + input.Num;
          }
      }
      const textShape =group.addShape('text', {
        attrs: {
          x: 25,
          y: 54 + index * 20,
          text: input.name+':'+Temp, // 使用 input.Id 替代 name
          fill: '#000000',
          textBaseline: 'top',
          fontWeight: 600,
          fontSize: 14,
          fontFamily: 'Microsoft YaHei',
          textAlign: 'left',
        },
        capture: false,
        name: 'nameText',
      });
      const textWidth = textShape.getBBox().width;
      maxWidth = Math.max(maxWidth, textWidth);
      group.removeChild(textShape)
    }); // Inputs 标题文字
    cfg.Outputs.map((output, index) => {
      const textShape =group.addShape('text', {
        attrs: {
          x: 425,
          y: 54 + index * 20,
          text: output.name,
          fill: '#000000',
          textBaseline: 'top',
          fontWeight: 600,
          fontSize: 14,
          fontFamily: 'Microsoft YaHei',
          textAlign: 'right',
        },
        capture: false,
        name: 'nameText',
      });
      const textWidth = textShape.getBBox().width;
      maxWidth = Math.max(maxWidth, textWidth);
      group.removeChild(textShape)

    }); // Inputs 标题文字
    maxWidth = maxWidth+120;
    cfg.height = maxHeight* 20;
    cfg.width = maxWidth;
    if(cfg.IsHovor==true || cfg.IsBlock==true ||cfg.IsError==true)
    {
      let TempColor='#5a5a5a'
      if(cfg.isFinish==true && cfg.IsBlock==true && (cfg.TriggerLink==0 || (cfg.TriggerLink!=0 && cfg.RecursionBehavior=='Run')))//为绿色
      {
        TempColor='#009f2a'
      }
      else if(cfg.IsRunning==true && cfg.IsBlock==true )//为蓝色
      {
        TempColor='#0062c3'
      }
      else if(cfg.TriggerLink!=0 && cfg.IsBlock==true )//为紫粉色
      {
        TempColor='#ff00ff'
      }
      if(cfg.IsError==true || cfg.IsLoadSuccess==false)//为红色
      {
        TempColor='#ff0000'
      }
      const selectionBorder = group.addShape('rect', {
        attrs: {
          x: -5,
          y: -5,
          width: maxWidth + 10,
          height: 70 + maxHeight * 20,
          stroke: TempColor, // 淡蓝色边框
          lineWidth: 3,
          radius: [10, 10],
          shadowColor: '#666', // 添加阴影颜色
          shadowBlur: 10, // 阴影的模糊级别
          shadowOffsetX: 2, // 阴影在X轴的偏移量
          shadowOffsetY: 2, // 阴影在Y轴的偏移量
          fill: 'transparent',
        },
        name: 'selection-border',
      });
    }
    const container = group.addShape('rect', {
      attrs: {
        x: 0,
        y: 0,
        width: maxWidth,
        height: 60 + maxHeight * 20,
        stroke: 'black',
        radius: [8, 8],
        fill: 'rgb(238,241,243)', // todo 节点背景框颜色
      },
      name: 'rect',
    });// 最外层灰色的框
    const shape = group.findById('rect'); // 通过 id 获取矩形图形
    let TitleColor = 'rgb(3,197,136)';
    if (cfg.NodeKind == undefined) {
      cfg.NodeKind = 'Normal';
    }
    if (cfg.IsLoadSuccess == false) {
      TitleColor = '#ff0000'; // Set TitleColor to red if IsLoadSuccess is false
    } else if (cfg.NodeKind.includes('LLm')) {
      TitleColor = '#009fcb';
    } else if (cfg.NodeKind == 'IfNode') {
      TitleColor = '#b300ff';
    } else if (cfg.NodeKind.includes('passivityTrigger')) {
      TitleColor = '#ff9100';
    } else if (cfg.NodeKind.includes('ArrayTrigger')) {
      TitleColor = '#e75500';
    }
    group.addShape('rect', {
      attrs: {
        x: 0,
        y: 0,
        width: maxWidth,
        height: 40,
        radius: [8, 8, 0, 0],
        fill: TitleColor, // todo 节点标题栏颜色
      },
      capture: false,
      name: 'rect',
    }); // 标题绿色的栏
    // If IsLoadSuccess is false, draw the black square with a red exclamation mark
    if (cfg.IsLoadSuccess == false) {
      group.addShape('rect', {
        attrs: {
          x: maxWidth - 35, // Moved slightly to the left
          y: 8, // Slightly moved upward
          width: 25, // Slightly wider
          height: 25, // Slightly taller
          fill: '#000000', // Black square
        },
        name: 'warningRect',
      });
    
      group.addShape('text', {
        attrs: {
          x: maxWidth - 22, // Adjusted to stay centered in the larger square
          y: 20, // Adjusted to stay vertically centered
          text: '!',
          fill: '#ff0000', // Red exclamation mark
          fontSize: 18, // Slightly larger font size
          fontWeight: 600,
          textAlign: 'center',
          textBaseline: 'middle',
        },
        name: 'warningText',
      });
    }
    
    group.addShape('text', {
      attrs: {
        x: 30,
        y: 20,
        //text: cfg.name.replace(".py", ""),
        text: cfg.label,
        fill: '#fff',
        textBaseline: 'middle',
        fontWeight: 600,
        fontSize: 16,
        fontFamily: 'Microsoft YaHei',
        textAlign: 'left',
      },
      capture: false,
      name: 'nameText',
    }); // 文件名的文字
    cfg.Inputs.map((input, index) => {
      let Temp=''
      // 定义每行显示的最大字符数
      const maxDisplayLength = 50;

    if(input.IsLabel == true) {
        if(input.Kind.includes('String')) {
            Temp = ':' + truncateTextWithEllipsis(input.Context, maxDisplayLength);
        }
        if(input.Kind == 'Num') {
            Temp = ':' + input.Num;
        }
        if(input.Kind == 'Boolean') {
            Temp = ':' + input.Boolean;
        }
    }

      group.addShape('text', {
        attrs: {
          x: 15,
          y: 54 + index * 20,
          text: input.name+Temp, // 使用 input.Id 替代 name
          fill: '#000000',
          textBaseline: 'top',
          fontWeight: 600,
          fontSize: 14,
          fontFamily: 'Microsoft YaHei',
          textAlign: 'left',
        },
        capture: false,
        name: 'nameText',
      });
    }); // Inputs 标题文字

    cfg.Outputs.map((output, index) => {
      group.addShape('text', {
        attrs: {
          x: maxWidth -15,
          y: 54 + index * 20,
          text: output.name,
          fill: '#000000',
          textBaseline: 'top',
          fontWeight: 600,
          fontSize: 14,
          fontFamily: 'Microsoft YaHei',
          textAlign: 'right',
        },
        capture: false,
        name: 'nameText',
      });
    }); // Inputs 标题文字
    const anchorPoints = this.getAnchorPoints(cfg);
    anchorPoints.forEach((anchorPos, i) => {
    let Kind=''
      if(i<cfg.Inputs.length )
      {
        if(cfg.Inputs[i].Kind == 'Num' || cfg.Inputs[i].Kind .includes('String')   || cfg.Inputs[i].Kind == 'Boolean' || cfg.Inputs[i].Kind == 'Trigger') {
          Kind = 'input';
          var strokecolor = ''; // 在使用之前定义变量
          if(cfg.Inputs[i].Kind .includes('String'))
              strokecolor = '#00c788';
          else if(cfg.Inputs[i].Kind == 'Num')
              strokecolor = '#5F95FF';
          else if(cfg.Inputs[i].Kind == 'Boolean')
              strokecolor = '#ff00ff';
              let circleColor = '#fff';
          
              if(cfg.Inputs[i].Link>0)
              {
                circleColor = '#78bbe5';
              }
              if(cfg.Inputs[i].IsLabel == false)
              {
                if(cfg.Inputs[i].Isnecessary==true)
                {
                  group.addShape('circle', {
                    attrs: {
                        r: 8, // 外圈的半径比内圈大，可以根据需要调整大小
                        x: 6, // 固定在左侧
                        y: (60 + maxHeight * 20) * anchorPos[1],
                        fill: 'none', // 通常外圈填充为透明
                        stroke: '#E80000', // 使用外圈的颜色
                        lineWidth: 2 // 设置外圈边框粗细为 2，可以根据需要调整
                    },
                });
                }
                  group.addShape('circle', {
                    attrs: {
                        r: 6,
                        x: 6, // 固定在左侧
                        y: (60 + maxHeight * 20) * anchorPos[1],

                        fill: circleColor,
                        stroke: strokecolor,
                        lineWidth: 3 // 设置边框粗细为 3

                        //外圈在设置一个边框

                    },
                    name: `anchor-point`, // the name, for searching by group.find(ele => ele.get('name') === 'anchor-point')
                    anchorPointIdx: i, // flag the idx of the anchor-point circle
                    links: cfg.Inputs[i].Link, // cache the number of edges connected to this shape
                    visible: true, // invisible by default, shows up when links > 1 or the node is in showAnchors state
                    draggable: true,
                    Kind: Kind,
                    Id:cfg.id,
                    AnChorKind:cfg.Inputs[i].Kind
                  });

              }
              else
              {
                let Temp=''
                if(cfg.Inputs[i].Kind .includes('String'))
                {
                  Temp=cfg.Inputs[i].Context
                }
                else if(cfg.Inputs[i].Kind == 'Num')
                {
                  Temp=cfg.Inputs[i].Num
                }
                group.addShape('circle', {
                  attrs: {
                      r: 0,
                      x: -3, // 固定在左侧
                      y: (60 + maxHeight * 20) * anchorPos[1],

                      fill: circleColor,
                      stroke: strokecolor,
                      lineWidth: 0 // 设置边框粗细为 3
                  },
                  name: `anchor-point`, // the name, for searching by group.find(ele => ele.get('name') === 'anchor-point')
                  anchorPointIdx: i, // flag the idx of the anchor-point circle
                  links: cfg.Inputs[i].Link, // cache the number of edges connected to this shape
                  visible: true, // invisible by default, shows up when links > 1 or the node is in showAnchors state
                  draggable: true,
                  Kind: Kind,
                  Id:cfg.id,
                  AnChorKind:cfg.Inputs[i].Kind
                  });
              }

      }
        if (cfg.Inputs[i].Kind == 'Label') {
          group.addShape('rect', { // 使用 rect 形状作为输入框的外观
            attrs: {
              width: 40, // 输入框的宽度
              height: 20, // 输入框的高度
              x: 10, // 位置 X
              y: (60 + maxHeight * 20) * anchorPos[1], // 位置 Y
              fill: '#fff', // 背景颜色
              stroke: '#5F95FF', // 边框颜色
            },
            name: 'num-input-box', // 名称，用于搜索
          });
          group.addShape('text', { // 使用 text 形状在输入框中显示默认值
            attrs: {
              text: '0', // 默认值
              x: 15, // 位置 X，稍微偏移以居中显示
              y: (60 + maxHeight * 20) * anchorPos[1] + 15, // 位置 Y，稍微偏移以居中显示
              fill: '#333', // 文本颜色
              textAlign: 'left', // 文本对齐方式
              textBaseline: 'middle', // 文本基线
              fontSize: 14, // 文本字体大小
            },
            name: 'num-input-text', // 名称，用于搜索
          });
        }


      }
      else if(i>=cfg.Inputs.length && i<cfg.Inputs.length+cfg.Outputs.length )
      {
          Kind='output'
              if(cfg.Outputs[i-cfg.Inputs.length].Kind=='Num' || cfg.Outputs[i-cfg.Inputs.length].Kind.includes('String')  || cfg.Outputs[i-cfg.Inputs.length].Kind=='Boolean' || cfg.Outputs[i-cfg.Inputs.length].Kind=='Trigger' )
                {
                  var strokecolor = ''; // 在使用之前定义变量
                  if(cfg.Outputs[i-cfg.Inputs.length].Kind .includes('String'))
                    strokecolor = '#00c788';
                  else if(cfg.Outputs[i-cfg.Inputs.length].Kind == 'Num')
                    strokecolor = '#5F95FF';
                  else if(cfg.Outputs[i-cfg.Inputs.length].Kind == 'Boolean')
                    strokecolor = '#ff00ff';
                  else if(cfg.Outputs[i-cfg.Inputs.length].Kind == 'Trigger')
                    strokecolor = '#ff9100';
                  let circleColor = '#fff';
                  if(cfg.Outputs[i-cfg.Inputs.length].Link>0)
                  {
                    circleColor = '#78bbe5';
                  }
                  group.addShape('circle', {
                    attrs: {
                      r: 6,
                      x: maxWidth - 7, // 固定在右侧
                      y: (60 + maxHeight * 20) * anchorPos[1],
                      fill: circleColor,
                      stroke: strokecolor,
                      lineWidth: 3 // 设置边框粗细为 3
                    },
                    name: `anchor-point`, // the name, for searching by group.find(ele => ele.get('name') === 'anchor-point')
                    anchorPointIdx: i, // flag the idx of the anchor-point circle
                    AnChorKind:cfg.Outputs[i-cfg.Inputs.length].Kind,
                    Description:cfg.Outputs[i-cfg.Inputs.length].Description,
                    links: cfg.Outputs[i-cfg.Inputs.length].Link, // cache the number of edges connected to this shape
                    visible: true, // invisible by default, shows up when links > 1 or the node is in showAnchors state
                    draggable: true,
                    Kind:Kind,
                    Id:cfg.id,
                });
              }
      }
      else if(i==cfg.Inputs.length+cfg.Outputs.length && cfg.NodeKind!='Trigger')
      {
              Kind='Trigger'
              var strokecolor = ''; // 在使用之前定义变量
              strokecolor = '#ff9100';
              let circleColor = '#fff';
              if(cfg.TriggerLink>0)
              {
                circleColor = '#78bbe5';
              }
              group.addShape('circle', {
                attrs: {
                  r: 6,
                  x: 10, // 固定在右侧
                  y: 10,
                  fill: circleColor,
                  stroke: strokecolor,
                  lineWidth: 3 // 设置边框粗细为 3
                },
                name: `Triggle-anchor-point`, // the name, for searching by group.find(ele => ele.get('name') === 'anchor-point')
                anchorPointIdx: i, // flag the idx of the anchor-point circle
                AnChorKind:'Trigger',
                Description:'Trigger',
                links: cfg.TriggerLink, // cache the number of edges connected to this shape
                visible: true, // invisible by default, shows up when links > 1 or the node is in showAnchors state
                draggable: true,
                Kind:Kind,
                Id:cfg.id,
            });

      }
    }) // 圆圈锚点
    //从新定义anchorPoints，位置为6/maxWidth与maxWidth - 7/maxWidth
    cfg.anchorPoints.forEach((anchorPos, i) => {
      if(i<cfg.Inputs.length)
      {

        anchorPos[0] = 6/maxWidth;
      }
      else if(i>=cfg.Inputs.length && i<cfg.Inputs.length+cfg.Outputs.length)
      {
        anchorPos[0]= (maxWidth - 7)/maxWidth;
      }
      else if(i==cfg.Inputs.length+cfg.Outputs.length)
      {
        anchorPos[0]= 10/maxWidth;
        anchorPos[1]=10/(60 + maxHeight * 20);
      }
    });
    //console.log('cfg',cfg.anchorPoints)
    return container;
  },
  getAnchorPoints(cfg) {
    return cfg.anchorPoints;
  },

});
// 记录锚点
let sourceAnchorIdx, targetAnchorIdx, sourceAnchor, startType, isDropingFile = false;
// 处理平行和不同锚点的边
function truncateTextWithEllipsis(text, maxLength) {
  // 检查 text 是否为 null 或 undefined
  if (text == null) {
    return ''; // 或者你可以返回一个默认值
  }

  // 检查文本中是否包含换行符
  const newLineIndex = text.indexOf('\n');

  // 如果有换行符，并且换行符的位置在最大显示长度之前，则截断到换行符位置
  if (newLineIndex !== -1 && newLineIndex < maxLength) {
      return text.substring(0, newLineIndex) + '...';
  }

  // 如果文本长度超过最大显示长度，进行截断并添加省略号
  if (text.length > maxLength) {
      return text.substring(0, maxLength) + '...';
  } else {
      return text;
  }
}

// 初始化图
function ChangeLink(Anchor)
{
    const Kind=Anchor.get('Kind')
    const Id=Anchor.cfg.Id
    const anchorPointIdx=Anchor.get('anchorPointIdx')
    const Num=Anchor.get('links')
    let nodes=graph.save().nodes;
    if(Kind=='input')
    {
      nodes.forEach((node) => {
        if(node.id === Id) {
            node.Inputs.forEach((input, index) => {
                if(index==anchorPointIdx)
                {
                  input.Link = Num;
                }
              });
        }
      });
    }
    else if(Kind=='output')
    {
      nodes.forEach((node) => {
        if(node.id === Id) {
          if(anchorPointIdx!=-1)
          {
            node.Outputs.forEach((output, index) => {
                if(index+node.Inputs.length==anchorPointIdx)
                {
                  output.Link = Num;
                }
            });
          }
          else
          {
            node.TriggerLink = Num;
          }
        }
      });
    }
    else if(Kind=='Trigger')
    {
      nodes.forEach((node) => {
        if(node.id === Id) {
          node.TriggerLink = Num;
        }
      });
    }
    ChangeDatas(nodes);
}
const initGraph = async (id = null) => {
    if (id) {
      await requestGraphData(id);
    }
    const w = window.innerWidth;
    const h = window.innerHeight;
    graph = new G6.Graph({
      container: 'mountNode',
      // 画布宽高
      width: w,
      height: h,
      modes: {
        default: [
          {
            type: 'drag-canvas',
            scalableRange: -1,
          },
          {
            type: 'click-select',
          },
          {
            type: 'drag-combo',
          },
          'zoom-canvas',
          {
            type: 'drag-node',
            shouldBegin: e => {
              const { item } = e;
              const model = item.getModel();
              // 如果节点的isBlock属性为true，阻止拖动
              console.log('model',model)
              if (model.IsBlock) {
                showMessage("Now is Running, Nodes Is Blocking",'#000000');
                return false;
              }
              // 可以进一步细化，例如不允许拖动特定部分
              if (e.target.get('name') === 'anchor-point') {
                return false;
              }
              return true; // 其他情况允许拖动
            }
          },
          {
            type: 'create-edge',
            trigger: 'drag', // set the trigger to be drag to make the create-edge triggered by drag
            shouldBegin: e => {
              // avoid beginning at other shapes on the node
              if (e.target && e.target.get('name') !== 'anchor-point' && e.target.get('name') !== 'Triggle-anchor-point') return false;
              startType = e.target.get('Kind');
              sourceAnchorIdx = e.target.get('anchorPointIdx');
              e.target.attr('fill', '#78bbe5');
              sourceAnchor = e.target;
              sourceAnchor.set('links', sourceAnchor.get('links') + 1); // cache the number of edge connected to this anchor-point circle
              ChangeLink(e.target);
              return true;
            },
            shouldEnd: e => {
              // avoid ending at other shapes on the node
              //if(e.target&&e.target.get('Kind')!=sourceAnchor.get('Kind')) return false;
              const sourceKind=sourceAnchor.get('Kind');
              const targetKind=e.target.get('Kind');
              const sourceLinks=sourceAnchor.get('links');
              const targetLinks=e.target.get('links');
              let Temp=e.target;
              let SourceNodeKind=''
              const data=graph.save().nodes;
              data.forEach((node) => {
                if(node.id === sourceAnchor.cfg.Id) {
                  SourceNodeKind=node.NodeKind
                }
              });
              if (e.target && e.target.get('name') !== 'anchor-point' && (e.target.get('name')!=='Triggle-anchor-point' && SourceNodeKind=='IfNode')) return false;
              if(sourceKind==targetKind) return false;
              if(sourceLinks>=2 && sourceKind=='input') return false;
              if(targetLinks>=1 && targetKind=='input') return false;
              if (getBeforeUnderscore(e.target.get('AnChorKind')) !== getBeforeUnderscore(sourceAnchor.get('AnChorKind'))) return false;

              // 辅助函数，用于获取 '_' 之前的字符串部分
              function getBeforeUnderscore(str) {
                return str?.toString().split('_')[0] ?? '';
            }
            

              if (e.target) {
                targetAnchorIdx = e.target.get('anchorPointIdx');
                e.target.set('links', e.target.get('links') + 1);  // cache the number of edge connected to this anchor-point circl
                let nodes=graph.save().nodes;
                ChangeLink(e.target);
                e.target.attr('fill', '#78bbe5')
                return true;
              }
              else if(sourceLinks>=1 )
              {
                sourceAnchor.attr('fill', '#fff')
                sourceAnchor = undefined;
                return false;
              }
            },
          }

        ], // 允许拖拽画布、放缩画布、拖拽节点
      },
      animate: true, // Boolean，切换布局时是否使用动画过度，默认为 false
      animateCfg: {
        duration: 500, // Number，一次动画的时长
        easing: 'easeLinear', // String，动画函数
      },
      defaultNode: {
        type: 'fileNode',
        stateStyles: {
          hover: {
            fill: 'lightgreen',
          },
          active: {
            stroke: '#ff0000',
            lineWidth: 100,
          }
        },
      },
      defaultCombo: {
        type: 'resizable-combo',
        style: {
          fill: '#f0f0f0',
          stroke: '#888888',
        },
      },
      defaultEdge: {
        type: 'line-dash',
        style: {
          lineWidth: 3,
          stroke: '#000',
          endArrow: {
            path: 'M 0,0 L 12,6 L 12,-6 Z',
            fill: '#5c95ff',
            d: 0,
          },
        },
        curveOffset: 20,
        minCurveOffset: 10,
      },
      plugins: [
        contextMenu,
      ]
    });
// 读取数据
    graph.data([]);
// 渲染图
    graph.render();
    // todo 可以自行添加背景图

    let backgroundImag = graph.getGroup().addShape('image', {
      attrs: {
        width: graph.getWidth(),
        height: graph.getHeight(),
        img: '',
      },
      capture: false
    });
    let shift = true;
    const switchDiv = document.createElement('div');
    backgroundImag.toBack();

    // 添加边后更新锚点-旧
    // graph.on('aftercreateedge', (e) => {
    //   // update the sourceAnchor and targetAnchor for the newly added edge
    //   graph.updateItem(e.edge, {
    //     sourceAnchor: sourceAnchorIdx,
    //     targetAnchor: targetAnchorIdx
    //   })

    //   // update the curveOffset for parallel edges
    //   const edges = graph.save().edges;
    //   processParallelEdgesOnAnchorPoint(edges);
    //   graph.getEdges().forEach((edge, i) => {
    //     graph.updateItem(edge, {
    //       curveOffset: edges[i].curveOffset,
    //       curvePosition: edges[i].curvePosition,
    //     });
    //   });
    // });
    // 添加节流函数
    const throttle = (fn, delay) => {
      let lastCall = 0;
      return function (...args) {
        const now = Date.now();
        if (now - lastCall >= delay) {
          fn.apply(this, args);
          lastCall = now;
        }
      };
    };
    
    // 画布拖拽处理
    graph.on('canvas:dragstart', (evt) => {
      isDragging = true;
      lastPosition = {
        x: evt.clientX,
        y: evt.clientY
      };
    });
    
    graph.on('canvas:drag', throttle((evt) => {
      if (!isDragging) return;
    
      // 计算实际位移
      const deltaX = evt.clientX - lastPosition.x;
      const deltaY = evt.clientY - lastPosition.y;
    
      // 更新上一次位置
      lastPosition = {
        x: evt.clientX,
        y: evt.clientY
      };
    
      // 计算新的视觉中心点
      visualCenter = {
        x: visualCenter.x + deltaX,
        y: visualCenter.y + deltaY
      };
    
      // 添加边界检查（根据实际画布大小调整）
      const canvasWidth = graph.get('width');
      const canvasHeight = graph.get('height');
      
      visualCenter.x = Math.max(0, Math.min(visualCenter.x, canvasWidth));
      visualCenter.y = Math.max(0, Math.min(visualCenter.y, canvasHeight));
    
      // 可以添加自定义的视图更新逻辑
      //graph.translate(deltaX, deltaY);
    
      console.log(`画布位移：X=${deltaX}, Y=${deltaY}`);
      console.log(`当前视觉中心点：(${visualCenter.x}, ${visualCenter.y})`);
    }, 16)); // 约60fps的刷新率
    
    graph.on('canvas:dragend', () => {
      isDragging = false;
    });
    
    // 可选：添加缩放事件监听
    graph.on('wheel', (evt) => {
      evt.preventDefault();
      const { deltaY } = evt;
      const zoom = graph.getZoom();
      const nextZoom = zoom - deltaY / 1000;
      
      // 限制缩放范围
      graph.zoomTo(Math.max(0.1, Math.min(nextZoom, 2)), {
        x: evt.clientX,
        y: evt.clientY
      });
    });
    graph.on('afteradditem', e => {
      if (e.item && e.item.getType() === 'edge' && !isDropingFile) {
        graph.updateItem(e.item, {
          sourceAnchor: sourceAnchorIdx
        });
      }
      if(e.item && e.item.getType() === 'node') {
        let data = graph.save()
        //data.nodes.forEach((node) => {
            //if(node.id === e.item._cfg.id) {
              //node.Inputs.forEach((input, index) => {
                //input.Id += index.toString();
              //});
             // node.Outputs.forEach((output, index) => {
                //output.Id+=index.toString();
             // });
           // }
          //});
          ChangeDatas(data);
      }
    })
    //combo有关
    //#region

    // 在文档中添加一个用于显示错误信息的浮窗元素
    /* ========= 常量 ========= */
    const STATE = {
      ORANGE : 'linkOrange',  // IfNode ➜ 普通分支
      PURPLE : 'linkPurple',  // IfNode ➜ STOP 分支
      HOVER  : 'linkBlue',    // 悬停高亮
      ERROR  : 'linkRed'      // 连线鼠标悬停高亮
    };

    /* ========= 工具函数 ========= */
    // 给一条边重新计算并设置“底色”
    function setEdgeBaseColor(edge) {
      edge.clearStates([STATE.ORANGE, STATE.PURPLE]);   // 先清掉旧底色
      const m       = edge.getModel();
      const srcNode = graph.findById(m.source);
      if (!srcNode) return;

      const srcData = srcNode.getModel();
      if (srcData.NodeKind === 'IfNode') {
        // 计算对应输出下标：sourceAnchor 从 0 开始，
        // 先减掉输入个数，剩下就是输出下标
        const outIdx = (m.sourceAnchor || 0) - (srcData.Inputs?.length || 0);
        const out    = srcData.Outputs?.[outIdx];
        if (out && out.TriggerKind === 'STOP') {
          edge.setState(STATE.PURPLE, true);
        } else {
          edge.setState(STATE.ORANGE, true);
        }
      }
    }


    /* ========= 辅助 ========= */
    const isRunning = () =>
      document.getElementById('runButton').textContent === '运行中...';

    /* ========= 节点悬停：蓝光高亮关联边 ========= */
    /* ========= 提前拿到 tooltip DOM ========= */
    const tooltip = document.getElementById('tooltip') || (() => {
      // 如果页面里还没有 tooltip 元素，就创建一个
      const tip = document.createElement('div');
      tip.id = 'tooltip';
      Object.assign(tip.style, {
        position: 'fixed',
        zIndex  : 9999,
        maxWidth: '280px',
        padding : '6px 10px',
        fontSize: '12px',
        color   : '#fff',
        background:'#333',
        borderRadius:'4px',
        boxShadow:'0 2px 8px rgba(0,0,0,.25)',
        display :'none',
        pointerEvents:'none'
      });
      document.body.appendChild(tip);
      return tip;
    })();

    /* ========= 节点悬停 ========= */
    graph.on('node:mouseenter', e => {
      /* ——— tooltip 逻辑（保持你原有判断） ——— */
      const node = e.item;
      node.update({ IsHovor:true });
      const m = node.getModel();
      tooltip.style.display = 'block';
      tooltip.style.fontColor = 'RED';
      if (m.IsLoadSuccess === false) {
        tooltip.textContent = 'Load Failed';
      } else if (m.IsError === true) {
        tooltip.textContent = m.ErrorContext || 'Error';
      } else {
        tooltip.style.display = 'none';
      }

      if (m.IsLoadSuccess === false || m.IsError === true) {
        tooltip.style.left   = `${e.clientX + 10}px`;
        tooltip.style.top    = `${e.clientY + 10}px`;
        tooltip.style.display= 'block';
      }
      // 显示 tooltip
      
      if (isRunning()) return;

      /* ——— 高亮关联边 ——— */
      const nodeId = node.getID();
      graph.getEdges().forEach(edgeItem => {
        const { source, target } = edgeItem.getModel();
        if (source === nodeId || target === nodeId) {
          if (!edgeItem.hasState('linkOrange') &&
              !edgeItem.hasState('linkPurple') &&
              !edgeItem.hasState('linkGreen')) {
            edgeItem.setState('linkBlue', true);
          } else {
            // 橘 / 紫 / 绿加小发光
            edgeItem.getKeyShape().attr({ lineWidth:4, shadowColor:'#fff', shadowBlur:4 });
          }
        }
      });

      
    });

    graph.on('node:mouseleave', e => {
      /* ——— 隐藏 tooltip ——— */
      tooltip.style.display = 'none';
      if (isRunning()) return;
    
      const node = e.item;
      node.update({ IsHovor:false });
    
      /* ——— 取消关联边高亮 ——— */
      const nodeId = node.getID();
      graph.getEdges().forEach(edgeItem => {
        const { source, target } = edgeItem.getModel();
        if (source === nodeId || target === nodeId) {
          edgeItem.setState('linkBlue', false);
    
          if (edgeItem.hasState('linkOrange') ||
              edgeItem.hasState('linkPurple') ||
              edgeItem.hasState('linkGreen')) {
            edgeItem.getKeyShape().attr({ lineWidth:3, shadowBlur:0 });
          } else {
            /* ★★★ 普通边恢复为纯黑 + 3px，无透明感 ★★★ */
            edgeItem.getKeyShape().attr({
              stroke:'#000',
              lineWidth:3,
              shadowBlur:0,
              opacity:1               // 万一被外部代码改过透明度
            });
          }
        }
      });
    
      
    });
    

    

    /* ========= 边悬停：红光高亮 ========= */
    graph.on('edge:mouseenter', e => {
      if (isRunning()) return;               // 仍然遵守“运行中不高亮”
    
      const edge = e.item;
      edge._prevStates = edge.getStates();   // 记录原状态
    
      // ==== ★ 如果本身是橘 / 紫 / 绿，不改变 stroke，只加光晕 ====
      if (edge.hasState('linkOrange') || edge.hasState('linkPurple') || edge.hasState('linkGreen')) {
        edge.getKeyShape().attr({ shadowColor:'#ff4d4f', shadowBlur:8 });
      } else {
        edge.setState('linkRed', true);      // 普通边 ➜ 红高亮
      }
    });
    
    graph.on('edge:mouseleave', e => {
      if (isRunning()) return;
    
      const edge = e.item;
    
      // ==== 恢复所有状态 + 去掉阴影 ====
      edge.setState('linkRed', false);
      edge.getKeyShape().attr({ shadowBlur:0 });
      (edge._prevStates || []).forEach(s => edge.setState(s, true));
      edge._prevStates = null;
    
      /* ★★★ 如果这条边原本没有任何颜色状态，显式设回黑色 ★★★ */
      if (!edge.hasState('linkOrange') &&
          !edge.hasState('linkPurple') &&
          !edge.hasState('linkGreen') &&
          !edge.hasState('linkBlue')) {
        edge.getKeyShape().attr({
          stroke:'#000',
          lineWidth:3,
          opacity:1
        });
      }
    });
    
    
    /* ========= 图初始化后，把所有边先打一遍底色 ========= */
    graph.on('afterrender', () => {
      graph.getEdges().forEach(setEdgeBaseColor);
    });

    
    graph.on('edge:click', (e) => {
      if (document.getElementById('runButton').textContent === '运行') {
        removeEdge(e.item._cfg.id);
      }
    });
    
    
    


    graph.on('node:click', (e) => {
      const nodeItem = e.item;
      // 如果当前是 active 状态，则取消，否则设置为 active
      graph.setItemState(nodeItem, 'active', false);

    });
    graph.on('node:mousedown', (e) => {
      //检测是否是左键
      const nodeItem = e.item;
      console.log('node:mousedown', e);
        let nodes=graph.save().nodes;
        nodes.forEach((node) => {
          if(node.id === nodeItem._cfg.id) {
            if(isRunning())
            {
              return;
            }
            node.IsError=false;
          }
        });
        ChangeDatas(nodes);
    });
    //#endregion
    //combo有关
    graph.on('beforeremoveitem', (e) => {
      if (e && e.type === 'edge' && e.item) {
        const edge = graph.findById(e.item.id);
        //if edge为undefined，说明是删除节点直接终止
        if (!edge) return;
        const sourceNode = edge.getSource();
        const targetNode = edge.getTarget();
        const sourceAnchor = sourceNode.getContainer().find(ele => ele.get('anchorPointIdx') === e.item.sourceAnchor);
        sourceAnchor.set('links', sourceAnchor.get('links') - 1);
        ChangeLink(sourceAnchor);
        if (targetNode && typeof targetNode.getContainer === 'function') {
          const targetAnchor = targetNode.getContainer().find(ele => ele.get('anchorPointIdx') === e.item.targetAnchor);
          targetAnchor.set('links', targetAnchor.get('links') - 1);
          ChangeLink(targetAnchor);
        }

        //const targetNode = edge.getTarget();
        //const targetAnchor = targetNode.getContainer()?.find(ele => ele.get('anchorPointIdx') === e.item.targetAnchor);
        //targetAnchor && targetAnchor.attr('fill', '#fff');
      }
    });
    graph.on('beforecreateedge', (e) => {

    });
    graph.on('aftercreateedge', (e) => {
      // update the sourceAnchor and targetAnchor for the newly added edge
      // todo：当检测到不是要求的方向的时候，互换point 和 anchor
      if (startType !== 'output') {
        const {source, target} = e.edge.getModel()
        const nodes = graph.save().nodes;
        const targetNode = nodes.find(node => node.id === target);
        const sourceNode = nodes.find(node => node.id === source);
        let sourceAnchorID=targetNode.Outputs[targetAnchorIdx- targetNode.Inputs.length].Id;
        let targetAnchorID=sourceNode.Inputs[sourceAnchorIdx].Id;
        if(targetNode.NodeKind=='IfNode')
        {
          sourceAnchorID=targetNode.Id;
          targetAnchorID=sourceNode.Inputs[sourceAnchorIdx].Id;
        }
        graph.updateItem(e.edge, {
          source: target,
          target: source,
          sourceAnchorID:sourceAnchorID,
          targetAnchorID:targetAnchorID,
          sourceAnchor: targetAnchorIdx,
          targetAnchor: sourceAnchorIdx,
        })
      } else {
        const {source, target} = e.edge.getModel();
        const nodes = graph.save().nodes;
        const targetNode = nodes.find(node => node.id === target);
        const sourceNode = nodes.find(node => node.id === source);
        let sourceKind=''
        const data=graph.save().nodes;
        data.forEach((node) => {
          if(node.id === source) {
            sourceKind=node.NodeKind
          }
        });
        console.log('sourceKind',sourceKind)
        if(sourceKind==='IfNode')
        {
          graph.updateItem(e.edge, {
            sourceAnchor: sourceAnchorIdx,
            targetAnchor: targetAnchorIdx,
            sourceAnchorID:sourceNode.Outputs[sourceAnchorIdx-sourceNode.Inputs.length].Id,
            targetAnchorID:targetNode.Id,
          })
        }
        else
        {
          graph.updateItem(e.edge, {
            sourceAnchor: sourceAnchorIdx,
            targetAnchor: targetAnchorIdx,
            sourceAnchorID:sourceNode.Outputs[sourceAnchorIdx-sourceNode.Inputs.length].Id,
            targetAnchorID:targetNode.Inputs[targetAnchorIdx].Id,
          })
        }

      }
      // update the curveOffset for parallel edges
      const edges = graph.save().edges;
      graph.getEdges().forEach((edge, i) => {
        graph.updateItem(edge, {
          // curveOffset: 0,
          // curvePosition: 0,
        });
      });
      //e.edge.setState('linked', true);
      const result=detectCycles(graph.save().nodes, graph.save().edges);
      if(result==null)
      {
        console.log('No cycles detected.');
      }
      else
      {
        console.log('Cycle detected:', result);
        console.log('Cycle detected:', graph.save().edges[result].id,e.edge._cfg.id);
        setTimeout(() => {
          const item = graph.findById(e.edge._cfg.id);
          // Remove the item
          removeEdge(item);
          alert('连接存在循环');
        }, 1);

      }
      setTimeout(() => {
        RefreshEdge(); 
      }, 10);  
      console.log(graph.save())
    });
    graph.on('mousedown', (e) => {
      // e.originEvent 鼠标原生事件
      // e.item // 事件触发的物体 e.target.get('name') !== 'anchor-point'

    })
    graph.on('node:dblclick', (e) => {
      //检测isblock是否为true
      if(e.item._cfg.model.IsBlock==false)
      {
        CreatDetaile(e.item._cfg);
      }
      else
      {
        showMessage("Now is Running, Nodes Is Blocking",'#000000');
      }
    });
    graph.on('node:drag', (e) => {
      updateDomBlock(e.item._cfg);
    });

    graph.on('afterremoveitem', () => {
      console.log(graph.save());
    });
    graph.on('edge:mouseup', (e) => {
      if(e.target.get('name') === 'anchor-point') {
        //console.log('点击了锚点', e.target.get('anchorPointIdx'));
      }
    });
    graph.on('afteradditem', () => {
      //console.log(graph.save());
      // todo 在更改元素的时候保存下来
      //   由graph.save()获取到数据
    });
    window.onresize = () => {
      graph.changeSize(window.innerWidth, window.innerHeight);
    };
  }
;

const requestSaveGraphData = () => {
  // todo 在这里请求你的已保存的图数据
}
//检测循环
function validateConnections(nodes, edges) {
    for (let edge of edges) {
        const sourceNode = nodes.find(node => node.id === edge.source);
        const targetNode = nodes.find(node => node.id === edge.target);
        const sourceAnchor = edge.sourceAnchor;
        const targetAnchor = edge.targetAnchor;

        if (sourceAnchor < sourceNode.Outputs.length && targetAnchor >= targetNode.Inputs.length) {
            throw new Error(`Invalid connection from ${edge.source} to ${edge.target}`);
        }

        if (sourceAnchor >= sourceNode.Outputs.length && targetAnchor < targetNode.Inputs.length) {
            throw new Error(`Invalid connection from ${edge.source} to ${edge.target}`);
        }
    }

    console.log('All connections are valid.');
}

// 使用深度优先搜索检测循环
//
function detectCycles(nodes, edges) {
  const graph = {};
  nodes.forEach(node => graph[node.id] = []);
  edges.forEach((edge, index) => graph[edge.source].push({ target: edge.target, index }));

  const visited = {};
  const recStack = {};

  function dfs(nodeId) {
      if (!visited[nodeId]) {
          visited[nodeId] = true;
          recStack[nodeId] = true;

          for (let { target, index } of graph[nodeId]) {
              if (!visited[target] && dfs(target)) {
                  return index;  // 返回发现循环的边的索引
              } else if (recStack[target]) {
                  return index;  // 返回发现循环的边的索引
              }
          }
      }

      recStack[nodeId] = false;
      return null;  // 如果没有发现循环，返回 null
  }

  for (let node of nodes) {
      const cycleIndex = dfs(node.id);
      if (cycleIndex !== null) {
          return cycleIndex;  // 返回发现循环的边的索引
      }
  }

  console.log('No cycles detected.');
  return null;  // 如果没有发现循环，返回 null
}

//检测循环
initGraph();


let fileInfoArray = [];
InitFunction()
//按键编辑
document.getElementById('saveButton').addEventListener('click', saveFunction);
document.getElementById('NodeButton').addEventListener('click', NodeFunction);
document.getElementById('WorkFlowButton').addEventListener('click', WorkFlowFunction);
document.getElementById('runButton').addEventListener('click', runFunction);
document.getElementById('exportButton').addEventListener('click', exportFunction);
document.getElementById('recoderButton').addEventListener('click', recoderFunction);
let sideWindowVisible = false;
function saveUIState() {
  const uiState = {};
  const kindElements = document.querySelectorAll('.LeftSideWindow_node-content');
  
  kindElements.forEach(kindElement => {
      const kindId = kindElement.id;
      const isExpanded = kindElement.style.display === 'block';
      const scrollTop = kindElement.scrollTop;

      uiState[kindId] = {
          isExpanded: isExpanded,
          scrollTop: scrollTop
      };
  });

  return uiState;
}

function restoreUIState(uiState) {
  Object.keys(uiState).forEach(kindId => {
      const kindElement = document.getElementById(kindId);
      if (kindElement) {
          const state = uiState[kindId];
          kindElement.style.display = state.isExpanded ? 'block' : 'none';
          kindElement.scrollTop = state.scrollTop;
          
          // 更新箭头方向
          const toggleIcon = kindElement.previousElementSibling.querySelector('.LeftSideWindow_toggle-icon');
          if (toggleIcon) {
              toggleIcon.textContent = state.isExpanded ? '▼' : '▶';
          }
      }
  });
}
// 在全局或更高的作用域下保存初始节点信息
let initialNodes = [];
let draggedNode = null;
function bindNodeEvents(nodeDiv, node) {
  // 悬停事件监听 - 显示浮窗
  let hoverTimeout;
  nodeDiv.addEventListener('mouseover', (event) => {
      hoverTimeout = setTimeout(() => {
          const floatingWindow = document.createElement('div');
          floatingWindow.classList.add('LeftSideWindow_floating-window');

          let introductionText = '';
          if (typeof node.NodeFunction.includes('String')) {
            // ① 彻底反转义
            const decoded = node.NodeFunction
              .replace(/\\\\/g, '\\')   // \\  →  \
              .replace(/\\n/g, '\n')    // \n  →  实际换行
              .replace(/\\"/g, '"')     // \"  →  "
              .replace(/\\</g, '<')     // \< →  <
              .replace(/\\>/g, '>');    // \> →  >

            // ② 把真实换行变成 <br> 方便 HTML 显示
            introductionText = decoded.replace(/\n+/g, '<br>');


          } else {
              introductionText = 'No introduction available';
          }
          floatingWindow.innerHTML = introductionText;

          document.body.appendChild(floatingWindow);

          // 设置浮窗位置紧随鼠标
          floatingWindow.style.top = `${event.clientY + 10}px`;
          floatingWindow.style.left = `${event.clientX + 10}px`;

          event.target.addEventListener('mousemove', (moveEvent) => {
              floatingWindow.style.top = `${moveEvent.clientY + 10}px`;
              floatingWindow.style.left = `${moveEvent.clientX + 10}px`;
          });

          event.target.addEventListener('mouseleave', () => {
              floatingWindow.remove();
              clearTimeout(hoverTimeout); // 清除定时器，避免内存泄漏
          });
      }, 500); // 延迟0.5秒显示浮窗
  });

  nodeDiv.addEventListener('mouseleave', () => {
      clearTimeout(hoverTimeout); // 如果鼠标在0.5秒内移出，取消显示浮窗
  });

  nodeDiv.addEventListener('dragstart', (event) => {
      draggedNode = {
          name: node.filename,
          kind: node.NodeKind,
      };
  });
}
function NodeFunction() {
  // 保存当前UI状态
  const uiState = saveUIState();

  refreshFileList();
  console.log('NodeFunction', fileList);

  const sideWindow = document.getElementById('LeftSideWindow_side-window');
  if (!sideWindowVisible) {
      sideWindow.classList.add('visible');
  } else {
      sideWindow.classList.remove('visible');
  }
  sideWindowVisible = !sideWindowVisible;

  const container = document.getElementById('LeftSideWindow_KIND-container');

  // 先清空 initialNodes
  initialNodes = [];

  // 清空容器内容
  container.innerHTML = '';

  // 保留搜索框元素
  const searchInput = document.getElementById('LeftSideWindow_search');
  const searchContainer = searchInput ? searchInput.parentNode : document.createElement('div');

  if (!searchInput) {
      // 添加搜索框到侧边栏顶部
      searchContainer.style.padding = '5px'; // 调整边距

      const newSearchInput = document.createElement('input');
      newSearchInput.type = 'text';
      newSearchInput.id = 'LeftSideWindow_search';
      newSearchInput.placeholder = 'Search...';
      newSearchInput.style.width = '100%';
      newSearchInput.style.padding = '5px';
      newSearchInput.style.borderRadius = '5px';
      newSearchInput.style.border = '1px solid #ccc';

      searchContainer.appendChild(newSearchInput);
      container.appendChild(searchContainer);

      newSearchInput.addEventListener('input', (event) => {
          const keyword = event.target.value.trim();
          filterComponents(keyword, container, newSearchInput, searchContainer);
          function filterComponents(keyword, container, searchInput, searchContainer) {
            let matchingNodes = [];
          
            console.log('Filtering with keyword:', keyword);
            console.log('Initial Nodes:', initialNodes.length);
          
            initialNodes.forEach(node => {
                const text = node.innerText.toLowerCase();
                console.log('text:', text);
                const matches = text.includes(keyword.toLowerCase());
          
                if (matches) {
                    matchingNodes.push(node);
                }
            });
          
            // 在渲染前手动移除浮窗（如果存在）
            removeFloatingWindows();
          
            // 获取搜索框的光标位置
            const cursorPosition = searchInput.selectionStart;
          
            // 清空容器内容，但保留搜索框
            container.innerHTML = '';
            container.appendChild(searchContainer);
          
            console.log('Matching nodes:', matchingNodes.length, matchingNodes);
          
            if (keyword && matchingNodes.length > 0) {
                matchingNodes.forEach(node => {
                    node.style.display = 'block';
                    container.appendChild(node); // 直接将匹配的节点添加到 container 中
                });
            } else {
                // 如果没有关键词或搜索框为空，恢复显示所有类别和组件
                console.log('Restoring all categories');
                
                // 重新构建所有类别及其节点
                const groupedFiles = fileList.reduce((acc, file) => {
                    const key = file.NodeKind.split('_')[0];
                    if (!acc[key]) {
                        acc[key] = [];
                    }
                    acc[key].push(file);
                    return acc;
                }, {});
          
                Object.keys(groupedFiles).forEach(kind => {
                    const kindDiv = document.createElement('div');
                    kindDiv.classList.add('LeftSideWindow_kind');
                    kindDiv.innerHTML = `
                        <div class="LeftSideWindow_node">
                            ${kind} <span class="LeftSideWindow_toggle-icon">▶</span>
                        </div>
                        <div class="LeftSideWindow_node-content" id="LeftSideWindow_${kind}-content">
                        </div>
                    `;
                    container.appendChild(kindDiv);
          
                    const kindContent = kindDiv.querySelector(`#LeftSideWindow_${kind}-content`);
                    groupedFiles[kind].forEach(node => {
                        const nodeDiv = document.createElement('div');
                        nodeDiv.classList.add('LeftSideWindow_node', 'LeftSideWindow_draggable');
                        nodeDiv.innerText = node.filename.slice(0, -3); // 移除 .py 扩展名
                        nodeDiv.draggable = true;
          
                        // 手动重新绑定事件监听器
                        bindNodeEvents(nodeDiv, node);
          
                        kindContent.appendChild(nodeDiv);
                    });
          
                    const kindHeader = kindDiv.querySelector('.LeftSideWindow_node');
                    const toggleIcon = kindHeader.querySelector('.LeftSideWindow_toggle-icon');
                    kindHeader.addEventListener('click', () => {
                        const content = kindDiv.querySelector('.LeftSideWindow_node-content');
                        const isExpanded = content.style.display === 'block';
                        content.style.display = isExpanded ? 'none' : 'block';
                        toggleIcon.textContent = isExpanded ? '▶' : '▼';
                    });
                });
            }
          
            // 恢复搜索框的光标位置和焦点
            searchInput.focus();
            searchInput.setSelectionRange(cursorPosition, cursorPosition);
          }
      });
  }

  // 现在开始渲染文件列表
  const groupedFiles = fileList.reduce((acc, file) => {
      const key = file.NodeKind.split('_')[0];
      if (!acc[key]) {
          acc[key] = [];
      }
      acc[key].push(file);
      return acc;
  }, {});

  Object.keys(groupedFiles).forEach(kind => {
      const kindDiv = document.createElement('div');
      kindDiv.classList.add('LeftSideWindow_kind');
      kindDiv.innerHTML = `
          <div class="LeftSideWindow_node">
              ${kind} <span class="LeftSideWindow_toggle-icon">▶</span>
          </div>
          <div class="LeftSideWindow_node-content" id="LeftSideWindow_${kind}-content">
          </div>
      `;
      container.appendChild(kindDiv);

      const kindContent = kindDiv.querySelector(`#LeftSideWindow_${kind}-content`);
      groupedFiles[kind].forEach(node => {
          const nodeDiv = document.createElement('div');
          nodeDiv.classList.add('LeftSideWindow_node', 'LeftSideWindow_draggable');
          nodeDiv.innerText = node.filename.slice(0, -3); // 移除 .py 扩展名
          nodeDiv.draggable = true;

          // 将节点信息保存到全局存储结构中
          initialNodes.push(nodeDiv);

          // 手动重新绑定事件监听器
          bindNodeEvents(nodeDiv, node);
          
          kindContent.appendChild(nodeDiv);
      });

      const kindHeader = kindDiv.querySelector('.LeftSideWindow_node');
      const toggleIcon = kindHeader.querySelector('.LeftSideWindow_toggle-icon');
      kindHeader.addEventListener('click', () => {
          const content = kindDiv.querySelector('.LeftSideWindow_node-content');
          const isExpanded = content.style.display === 'block';
          content.style.display = isExpanded ? 'none' : 'block';
          toggleIcon.textContent = isExpanded ? '▶' : '▼';
      });
  });

  // 恢复UI状态
  restoreUIState(uiState);
  const canvas = document.getElementById('graph-container'); // 画布的容器

  // 确保 dragover 阻止默认行为
  canvas.addEventListener('dragover', (event) => {
      event.preventDefault(); // 允许放置
      console.log('dragover on canvas');
  });

  // 处理 drop 事件
  document.addEventListener('drop', (event) => {
      event.preventDefault();
      console.log('drop event triggered', draggedNode);

      if (draggedNode) {
          const x = event.clientX - canvas.getBoundingClientRect().left;
          const y = event.clientY - canvas.getBoundingClientRect().top;
          console.log('Add node at position:', x, y);
          addNode(draggedNode.name, x, y, draggedNode.kind);
          draggedNode = null; // 仅在成功放置后重置拖拽的节点
      }
  });
}
// 创建有效的ID


// 主函数
async function WorkFlowFunction() {
  // 保存当前UI状态
  function createValidId(str) {
    return str.replace(/[^a-zA-Z0-9]/g, '_');
  }
  
  // 刷新工作流文件列表
  async function refreshWorkflowFiles() {
    try {
        console.log('Fetching workflow files...');
        const response = await fetch('/workflow-files');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        workflowFileList = await response.json();
        console.log('Workflow files received:', workflowFileList);
    } catch (error) {
        console.error('Error fetching workflow files:', error);
        workflowFileList = [];
    }
  }
  
  // 过滤工作流组件
  function filterWorkflowComponents(
  keyword,
  container,
  searchInput,
  searchContainer,
  initialNodes,
  fileList
) {
  // ---------- 1. 预处理 ----------
  const term = keyword.trim().toLowerCase();
  let matchingNodes = [];

  console.log('Filtering with keyword:', term);
  console.log('Initial Nodes:', initialNodes.length);

  // ---------- 2. 找出匹配节点 ----------
  initialNodes.forEach(node => {
    const text = node.innerText.toLowerCase();
    const matches = text.includes(term);
    if (matches) matchingNodes.push(node);
  });

  // ---------- 3. 渲染前收尾 ----------
  removeFloatingWindows();                                        // 清理悬浮窗
  const cursorPos = searchInput.selectionStart;                   // 记录光标
  container.innerHTML = '';                                       // 清空容器
  container.appendChild(searchContainer);                         // 重插搜索框

  // ---------- 4. 依据搜索词渲染 ----------
  if (term && matchingNodes.length > 0) {
    // 4‑A. 有关键字且命中
    console.log('Matching nodes:', matchingNodes.length);
    matchingNodes.forEach(node => {
      node.style.display = 'block';
      container.appendChild(node);                                // 直接加进容器
    });
  } else {
    // 4‑B. 无关键词或无命中 —— 重新渲染完整分类
    console.log('Restoring all categories');

    const grouped = fileList.reduce((acc, f) => {
      const key = f.NodeKind.split('_')[0];
      (acc[key] ||= []).push(f);
      return acc;
    }, {});

    Object.keys(grouped).forEach(kind => {
      // 创建类别外壳
      const kindDiv = document.createElement('div');
      kindDiv.classList.add('LeftSideWindow_kind');
      kindDiv.innerHTML = `
        <div class="LeftSideWindow_node">
          ${kind} <span class="LeftSideWindow_toggle-icon">▶</span>
        </div>
        <div class="LeftSideWindow_node-content" id="LeftSideWindow_${kind}-content"></div>
      `;
      container.appendChild(kindDiv);

      // 填充节点
      const kindContent = kindDiv.querySelector(`#LeftSideWindow_${kind}-content`);
      grouped[kind].forEach(file => {
        const nodeDiv = document.createElement('div');
        nodeDiv.classList.add('LeftSideWindow_node', 'LeftSideWindow_draggable');
        nodeDiv.innerText = file.filename.replace(/\.py$/, '');   // 去掉 .py
        nodeDiv.draggable = true;
        bindNodeEvents(nodeDiv, file);                            // 重新绑定事件
        kindContent.appendChild(nodeDiv);
      });

      // 折叠/展开逻辑
      const kindHeader = kindDiv.querySelector('.LeftSideWindow_node');
      const toggleIcon = kindHeader.querySelector('.LeftSideWindow_toggle-icon');
      kindHeader.addEventListener('click', () => {
        const content = kindDiv.querySelector('.LeftSideWindow_node-content');
        const expanded = content.style.display === 'block';
        content.style.display = expanded ? 'none' : 'block';
        toggleIcon.textContent = expanded ? '▶' : '▼';
      });
    });
  }

  // ---------- 5. 恢复搜索框状态 ----------
  searchInput.focus();
  searchInput.setSelectionRange(cursorPos, cursorPos);
}
  
  // 保存UI状态
  function saveUIState() {
    const expandedFolders = [];
    document.querySelectorAll('.LeftSideWindow_node-content').forEach(content => {
        if (content.style.display === 'block') {
            expandedFolders.push(content.id);
        }
    });
    return { expandedFolders };
  }
  
  // 恢复UI状态
  function restoreUIState(state) {
    if (state.expandedFolders) {
        state.expandedFolders.forEach(id => {
            const content = document.getElementById(id);
            if (content) {
                content.style.display = 'block';
                const toggleIcon = content.parentElement.querySelector('.LeftSideWindow_toggle-icon');
                if (toggleIcon) {
                    toggleIcon.textContent = '▼';
                }
            }
        });
    }
  }
  
  
  // 添加工作流节点
  
  const uiState = saveUIState();

  // 刷新工作流文件列表
  await refreshWorkflowFiles();

  const sideWindow = document.getElementById('LeftSideWindow_side-window');
  if (!sideWindowVisible) {
      sideWindow.classList.add('visible');
  } else {
      sideWindow.classList.remove('visible');
  }
  sideWindowVisible = !sideWindowVisible;

  const container = document.getElementById('LeftSideWindow_KIND-container');
  container.innerHTML = '';

  // 保留/创建搜索框
  const searchInput = document.getElementById('LeftSideWindow_search');
  const searchContainer = searchInput ? searchInput.parentNode : document.createElement('div');

  if (!searchInput) {
      searchContainer.style.padding = '5px';

      const newSearchInput = document.createElement('input');
      newSearchInput.type = 'text';
      newSearchInput.id = 'LeftSideWindow_search';
      newSearchInput.placeholder = 'Search workflows...';
      newSearchInput.style.width = '100%';
      newSearchInput.style.padding = '5px';
      newSearchInput.style.borderRadius = '5px';
      newSearchInput.style.border = '1px solid #ccc';

      searchContainer.appendChild(newSearchInput);
      container.appendChild(searchContainer);

      newSearchInput.addEventListener('input', (event) => {
          const keyword = event.target.value.trim();
          filterWorkflowComponents(keyword, container, newSearchInput, searchContainer, initialNodes, workflowFileList);
      });
  }

  // 按文件夹分组文件
  const groupedFiles = workflowFileList.reduce((acc, file) => {
      const folderName = file.folder || 'Other';
      if (!acc[folderName]) {
          acc[folderName] = [];
      }
      acc[folderName].push(file);
      return acc;
  }, {});

  // 渲染文件夹和文件
  Object.keys(groupedFiles).forEach(folder => {
      const folderDiv = document.createElement('div');
      folderDiv.classList.add('LeftSideWindow_kind');
      const folderId = createValidId(folder);

      folderDiv.innerHTML = `
          <div class="LeftSideWindow_node">
              ${folder} <span class="LeftSideWindow_toggle-icon">▶</span>
          </div>
          <div class="LeftSideWindow_node-content" id="LeftSideWindow_${folderId}_content">
          </div>
      `;
      container.appendChild(folderDiv);

      const folderContent = folderDiv.querySelector(`#LeftSideWindow_${folderId}_content`);
      groupedFiles[folder].forEach(file => {
          const fileDiv = document.createElement('div');
          fileDiv.classList.add('LeftSideWindow_node', 'LeftSideWindow_draggable');
          fileDiv.innerText = file.filename.slice(0, -5);
          fileDiv.draggable = true;

          // 存储文件信息
          fileDiv.dataset.filepath = file.filepath;
          fileDiv.dataset.folder = folder;

          // 绑定拖拽事件
          bindWorkflowNodeEvents(fileDiv, file);
          folderContent.appendChild(fileDiv);
      });

      // 添加文件夹展开/折叠功能
      const folderHeader = folderDiv.querySelector('.LeftSideWindow_node');
      const toggleIcon = folderHeader.querySelector('.LeftSideWindow_toggle-icon');
      folderHeader.addEventListener('click', () => {
          const content = folderDiv.querySelector('.LeftSideWindow_node-content');
          const isExpanded = content.style.display === 'block';
          content.style.display = isExpanded ? 'none' : 'block';
          toggleIcon.textContent = isExpanded ? '▶' : '▼';
      });
  });

  // 恢复UI状态
  restoreUIState(uiState);
  // 辅助函数：设置画布拖放事件

// 修改bindWorkflowNodeEvents函数以添加更多日志
function bindWorkflowNodeEvents(nodeDiv, fileInfo) {
  console.log('Binding events to node:', fileInfo);

  nodeDiv.addEventListener('dragstart', (event) => {
      console.log('Drag start event triggered', fileInfo);
      draggedWorkflowNode = {
          name: fileInfo.filename.slice(0, -5),
          filepath: fileInfo.filepath,
          folder: fileInfo.folder
      };
      console.log('Set draggedWorkflowNode:', draggedWorkflowNode);
      event.dataTransfer.setData('text/plain', '');
      nodeDiv.classList.add('dragging');
  });

  nodeDiv.addEventListener('dragend', (event) => {
    console.log('Drag end event triggered');
    nodeDiv.classList.remove('dragging');
    // 获取鼠标位置
    const mousePosition = {
        x: event.clientX,
        y: event.clientY
    };
    console.log('Mouse position:', mousePosition);
    AddWorkflowNode(draggedWorkflowNode, mousePosition);
    setTimeout(() => {
      RefreshEdge();
    }, 100);
    
});
}
}

function animateTitle(baseTitle) {
  // 使用星月变化符号，模拟月相变化
  const animation = ['🌑', '🌒', '🌓', '🌔', '🌕', '🌖', '🌗', '🌘'];
  // 或者使用更简约的符号版本
  // const animation = ['○', '◐', '●', '◑'];
  let index = 0;

  return setInterval(() => {
      const isRunning = document.getElementById('runButton')?.textContent === '运行中...';
      
      if (isRunning) {
          let title = baseTitle;
          
          // 保持原有的命名规则
          if (IsRunningFunction) {
              title = title + '{' + passivityTriggerArray.length + '}[' + (ArrayTriggerArray.length+1).toString() + ']';
          } else {
              title = title + '{' + passivityTriggerArray.length + '}[' + ArrayTriggerArray.length + ']';
          }
          
          // 添加动画符号
          document.title = `${title} ${animation[index]}`;
          index = (index + 1) % animation.length;
      } else {
          document.title = baseTitle;
      }
  }, 1000); // 调整为更缓慢的节奏，让动画更优雅
}
// 移除页面上所有的浮窗
function removeFloatingWindows() {
  const floatingWindows = document.querySelectorAll('.LeftSideWindow_floating-window');
  floatingWindows.forEach(window => window.remove());
}

async function recoderFunction() {
  //去除后缀名".josn"
  ProjectName = ProjectName.replace('.json', '');
  console.log('recoderFunction', ProjectName);
  
  const response = await fetch('/start_Message', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ ProjectName })
  });

  if (response.ok) {
    const result = await response.json();
    console.log(result.status);
    // 打开新的域名
    window.open(`http://127.0.0.1:2999/?project_name=${ProjectName}`, '_blank');
  } else {
    console.error('Failed to start project');
  }
}

async function exportFunction() {
  let choice = confirm("是否要保存当前图的代码？选择“确定”继续选择保存类型。");
  if (choice) {
    let option = confirm("选择“确定”保存为完整的 Python 代码，选择“取消”选择独立的 Python 代码。");
    if (option) {
      const graphData = graph.save();
      await exportGraphData(graphData, "full");
    } else {
      const graphData = graph.save();
      await exportGraphData(graphData, "independent");
    }
  }
}

async function exportGraphData(graphData, type) {
  const fileName = prompt("请输入保存的文件名（不含扩展名）：");
  if (fileName) {
    const response = await fetch('/export', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ graphData, fileName, type })
    });

    if (response.ok) {
        alert('图数据已成功导出为 Python 函数');
    } else {
        alert('导出失败');
    }
  }
}

function updateDomBlock(item) {
  // 从 item 中提取模型数据

}
function initializeDragAndResize(Nodes,maxWidth,maxHeight) {
  let onMove = false;
  let offsetX, offsetY;

  // 获取初始样式以便之后计算
  let oddStyle = window.getComputedStyle(Nodes);
  const content = document.getElementById('graph-container'); // 假设这是外层容器，已正确设置
  // 假设 scaleX 和 scaleY 已在外部定义
  const dragElement = Nodes.querySelector(".drag-bar"); // 假设你的 Nodes 元素内部有 .drag-bar 元素
  if (dragElement) {
      dragElement.addEventListener("mousedown", function(e) {
          onMove = true;
          const contentRect = content.getBoundingClientRect();
          // 考虑缩放和content位置，调整鼠标位置计算
          offsetX = (e.clientX - contentRect.left) - parseFloat(oddStyle.left);
          offsetY = (e.clientY - contentRect.top)  - parseFloat(oddStyle.top);
          document.addEventListener("mousemove", onMouseMove);
          document.addEventListener("mouseup", onMouseUp);
      });
  }
// 为 Nodes 内的所有 .circle 元素添加事件监听器

  // circle.addEventListener('mouseup', stopLining)
function onMouseMove(e) {
      if (onMove) {
          const contentRect = content.getBoundingClientRect();
          // 考虑缩放和content位置，调整元素新位置的计算
          let newX = (e.clientX - contentRect.left) - offsetX;
          let newY = (e.clientY - contentRect.top) - offsetY;
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
  //resizeOnEdge(Nodes, ".edge-right", "width",maxWidth);
 // resizeOnEdge(Nodes, ".edge-left", "width",maxWidth);
  //resizeOnEdge(Nodes, ".edge-top", "height",maxHeight);
  //resizeOnEdge(Nodes, ".edge-bottom", "height",maxHeight);
}
function resizeOnEdge(Nodes, edgeClass, moveAxis,maxNum) {
  const target = Nodes.querySelector(edgeClass);
  const content = document.getElementById('graph-container'); // 获取缩放容器
  // 假设scaleX和Viewspace.scaleY变量已经根据容器的缩放比例进行了设置
  if (!target) return;

  target.addEventListener("mousedown", function(e) {
      const contentRect = content.getBoundingClientRect();
      let startWidth = parseFloat(window.getComputedStyle(Nodes).width);
      let startHeight = parseFloat(window.getComputedStyle(Nodes).height);
      let startX = (e.clientX - contentRect.left) ;
      let startY = (e.clientY - contentRect.top) ;
      let startPos = { left: parseFloat(Nodes.style.left || 0), top: parseFloat(Nodes.style.top || 0) };

      function onMouseMove(e) {
          let mouseX = (e.clientX - contentRect.left) ;
          let mouseY = (e.clientY - contentRect.top) ;
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
function showMessage(message,color) {
  const messageContainer = document.getElementById('message-container');
  const messageText = document.getElementById('message-text');

  messageText.textContent = message;
  messageText.style.color = color;
  messageContainer.style.display = 'block'; // 显示消息
  messageContainer.style.opacity = 1; // 重置透明度为完全不透明
  messageContainer.style.top = '20px'; // 重置顶部位置
  messageText.style.fontWeight = 'bold';//粗体字

  // 短暂延迟后应用动画效果
  setTimeout(() => {
    messageContainer.classList.add('message-fade');
  }, 10); // 短暂延迟确保样式应用正确

  // 完成后隐藏和清理消息容器
  setTimeout(() => {
    messageContainer.style.display = 'none';
    messageContainer.classList.remove('message-fade'); // 移除类以重置动画
  }, 3000); // 3秒后隐藏消息
}


function ChangeNodeLabel(id, name, Kind) {
  if (Kind === -1) {
    // 获取当前图形的所有节点数据
    const nodes = graph.save().nodes;

    // 检查是否存在与给定 Name 重名的节点
    const nameExists = nodes.some(node => node.id !== id && node.label === name);

    if (nameExists) {
      // 如果存在重名，弹出提示框并终止函数执行
      alert('已存在相同名称的节点，请选择不同的名称！');
      return;
    }
    let data = graph.save();
    // 如果没有重名，找到对应的节点并更新其名称
    const nodeIndex = data.nodes.findIndex(node => node.id === id);

    // If the node is found, update its label
    if (nodeIndex !== -1) {
      data.nodes[nodeIndex].label = name;

      // Apply the modified data to the graph
      ChangeDatas(data);
    } else {
      // Optional: Alert or log if the specific node id was not found
      console.log('未找到对应的节点ID');
    }
  }
}
function ChangeRetryNum(id,Value) {
  let data = graph.save();
  const nodeIndex = data.nodes.findIndex(node => node.id === id);
  if (nodeIndex != -1) {
    //转换成int
    data.nodes[nodeIndex].ReTryNum = parseInt(Value);
    ChangeDatas(data);
  } else {
    console.log('未找到对应的节点ID');
  }
}
function ChangeLlmSetting(id,Value) {
  const nodes = graph.save().nodes;
  console.log('Value',Value);
  let nameExists = false;
  nodes.forEach(node => {
  if(node.id == id)
  {
    nameExists = true;
    node.name=Value[0]+'.py'
    node.temperature=Value[1]
    node.Top_p=Value[2]
    node.frequency_penalty=Value[3]
    node.presence_penalty=Value[4]
    node.max_tokens=Value[5]
  }
  });
  if(nameExists)
  {
    let data = graph.save();
    ChangeDatas(data);
    console.log('修改成功',data);
  }
  else
  {
    console.log('未找到对应的节点ID');
  }
}
function ChangeAnchorValue(Nodeid,Value,Status,id) {
    if(Status=='Input')
    {
        const nodes = graph.save().nodes;
        let nameExists = false;
        nodes.forEach(node => {
        if(node.id == Nodeid)
        node.Inputs.forEach(input => {
          if (input.Id !== id ) {
            nameExists = true;
          }
        });
      });
      let data = graph.save();
      const nodeIndex = data.nodes.findIndex(node => node.id === Nodeid);
      const anchorIndex = data.nodes[nodeIndex].Inputs.findIndex(input => input.Id === id); // 假设 Inputs 是一个数组
      if (anchorIndex != -1) {
        data.nodes[nodeIndex].Inputs[anchorIndex].IsLabel = true;
        if (data.nodes[nodeIndex].Inputs[anchorIndex].Kind == 'Num')
        {
          data.nodes[nodeIndex].Inputs[anchorIndex].Num = parseInt(Value);
        }
        else if (data.nodes[nodeIndex].Inputs[anchorIndex].Kind.includes('String'))
        {
          data.nodes[nodeIndex].Inputs[anchorIndex].Context = Value.trim();
        }
        else if (data.nodes[nodeIndex].Inputs[anchorIndex].Kind == 'Boolean')
        {
          if(Value == 'true')
          {
            data.nodes[nodeIndex].Inputs[anchorIndex].Boolean = true;
          }
          else
          {
            data.nodes[nodeIndex].Inputs[anchorIndex].Boolean = false;
          }
        }
        data=graph.save();
        data.nodes.forEach(node => {
          if(node.id == Nodeid)
          {
            node.Inputs.forEach(input => {
              if (input.Id == id )
              {
                input.Link = 1;
              }
            });
          }
        });
        const edges = data.edges;
        edges.forEach((edge, index) => {
          if (edge.target == Nodeid && edge.targetAnchorID == id) {
              //移除边
              edges.splice(index, 1);
          }
        });
        ChangeDatas(data);
        RefreshEdge();
      } else {
        console.error('未找到对应的锚点ID');
      }
    }
    else if(Status=='link')
    {
      let data = graph.save();
      const nodeIndex = data.nodes.findIndex(node => node.id === Nodeid);
      const anchorIndex = data.nodes[nodeIndex].Inputs.findIndex(input => input.Id === id); // 假设 Inputs 是一个数组
      if (anchorIndex != -1) {
        data.nodes[nodeIndex].Inputs[anchorIndex].IsLabel = false;
        data.nodes[nodeIndex].Inputs[anchorIndex].Link = 0;
        ChangeDatas(data);
      }
    }

}

function ChangeAnchorLabel(Nodeid, name, Kind,id,IsInput) {
  const nodes = graph.save().nodes;
  console.log('Kind',Kind,'name',name,'Nodeid',Nodeid,'id',id);
  if(typeof Kind === 'string' && Kind.includes('selectBox'))
    {
        let nameExists = false;
        nodes.forEach(node => {
        if(node.id == Nodeid)
        node.Inputs.forEach(input => {
          if (input.Id !== id && input.name === name) {
            nameExists = true;
          }
        });
      });
      if (nameExists) {
          alert('已存在相同名称的锚点，请选择不同的名称！');
          return;
      }
      let data = graph.save();
      const nodeIndex = data.nodes.findIndex(node => node.id === Nodeid);
      const anchorIndex = data.nodes[nodeIndex].Outputs.findIndex(output => output.Id === id);
      if (anchorIndex != -1) {
        //将kind转化成键值
        data.nodes[nodeIndex].Outputs[anchorIndex][Kind]=name;
        ChangeDatas(data);
      } else {
        console.error('未找到对应的锚点ID');
      }
    }  
    else if(typeof Kind === 'string' && Kind=='OriginalText')
    {
      //修改对应node的OriginalTextName
      let nameExists = false;
      nodes.forEach(node => {
      if(node.id == Nodeid)
      {
        nameExists = true;
        node.Outputs[0].name=name;
      }
      });
      if(nameExists)
      {
        let data = graph.save();
        ChangeDatas(data);
      }
      else
      {
        console.log('未找到对应的节点ID');
      }

    }
    else
    {
      if(IsInput==true)
        {
            let nameExists = false;
            nodes.forEach(node => {
            if(node.id == Nodeid)
            node.Inputs.forEach(input => {
              if (input.Id !== id && input.name === name) {
                nameExists = true;
              }
            });
          });
          if (nameExists) {
              alert('已存在相同名称的矛点，请选择不同的名称！');
              return;
          }
          let data = graph.save();
          const nodeIndex = data.nodes.findIndex(node => node.id === Nodeid);
          const anchorIndex = data.nodes[nodeIndex].Inputs.findIndex(input => input.Id === id); // 假设 Inputs 是一个数组
          if (anchorIndex != -1) {
            data.nodes[nodeIndex].Inputs[anchorIndex].name = name;
            ChangeDatas(data);
          } else {
            console.error('未找到对应的锚点ID1');
          }
        }
        else
        {
            let nameExists = false;
            nodes.forEach(node => {
            if(node.id == Nodeid)
            node.Outputs.forEach(output => {
              if (output.Id !== id && output.name === name) {
                nameExists = true;
              }
            });
          });
          if (nameExists) {
            alert('已存在相同名称的矛点，请选择不同的名称1！');
            return;
          }
          let data = graph.save();
          const nodeIndex = data.nodes.findIndex(node => node.id === Nodeid);
          const anchorIndex = data.nodes[nodeIndex].Outputs.findIndex(output => output.Id === id); // 假设 Inputs 是一个数组
          if (anchorIndex != -1) {
            data.nodes[nodeIndex].Outputs[anchorIndex].name = name;
            ChangeDatas(data);
          } else {
            console.error('未找到对应的锚点ID2');
          }
        }
    }
}
function CreatFilePath(id,Nodeid) {
  const nodes = graph.save().nodes;
  let FilePath= '';
  nodes.forEach(node => {
      if(node.id == Nodeid)
      {
        node.Inputs.forEach(input => {
          if (input.Id == id )
          {
            //input.Context包含字符
            if (input.Context && /[\S]/.test(input.Context)) {
              FilePath = input.Context;
          }
          }
        });
      }
  });
  let domElement = document.getElementById(`dom-${Nodeid}-${id}-FilePath`);
  if (!domElement) {
      domElement = document.createElement('div');
      domElement.id = `dom-${Nodeid}-${id}-FilePath`;
      domElement.className = 'Nodes';
      domElement.style.cssText = `
          position: absolute;
          left: 500px;
          top: 500px;
          width: 900px;
          height: 1000px;
          border-radius: 10px;
          border: 2px solid #ccc;  
          background-color: #f9f9f9;
          padding: 0;
          box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.1);
          display: flex;
          flex-direction: column;
          overflow: hidden;
      `;

      const dragBar = document.createElement('div');
      dragBar.className = 'drag-bar';
      dragBar.style.cssText = `
          cursor: move;
          height: 30px;
          width: 100%;
          background-color: #4CAF50;
          border-radius: 10px 10px 0 0;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 0 10px;
      `;
      const title = document.createElement('span');
      title.style.cssText = `
          font-weight: bold;
          color: white;
          font-size: 16px;
      `;
      title.textContent = 'FilePath';
      dragBar.appendChild(title);
      domElement.appendChild(dragBar);

      dragBar.addEventListener('mousedown', function(e) {
          e.preventDefault();
          let posX = e.clientX;
          let posY = e.clientY;
          const onMouseMove = function(e) {
              let dx = e.clientX - posX;
              let dy = e.clientY - posY;
              domElement.style.left = `${domElement.offsetLeft + dx}px`;
              domElement.style.top = `${domElement.offsetTop + dy}px`;
              posX = e.clientX;
              posY = e.clientY;
          };
          const onMouseUp = function() {
              document.removeEventListener('mousemove', onMouseMove);
              document.removeEventListener('mouseup', onMouseUp);
          };
          document.addEventListener('mousemove', onMouseMove);
          document.addEventListener('mouseup', onMouseUp);
      });

      let vessel = document.createElement('div');
      vessel.className = 'Vessel';
      vessel.style.cssText = `
          position: relative;
          flex-grow: 1;
          display: flex;
          flex-direction: row;
          flex-wrap: wrap;
          overflow-y: auto;
          overflow-x: hidden;
          background-color: #f0f0f0;
          padding: 10px;
          border: none;
          align-content: flex-start;
      `;
      domElement.appendChild(vessel);

      const navContainer = document.createElement('div');
      navContainer.style.cssText = `
          display: flex;
          background-color: #f0f0f0;
          padding: 5px;
          border-top: 1px solid #ccc;
          align-items: center;
      `;

      const backButton = document.createElement('button');
      backButton.innerHTML = '&#8592;';
      backButton.style.cssText = `
          width: 48px;
          height: 30px;
      `;
      backButton.addEventListener('click', function() {
          navigateBack();
      });
      navContainer.appendChild(backButton);

      const forwardButton = document.createElement('button');
      forwardButton.innerHTML = '&#8594;';
      forwardButton.style.cssText = `
          width: 48px;
          height: 30px;
          margin-left: 5px;
      `;
      forwardButton.addEventListener('click', function() {
          navigateForward();
      });
      navContainer.appendChild(forwardButton);

      let pathDisplay = document.createElement('input');
      pathDisplay.type = 'text';
      pathDisplay.style.cssText = `
          flex-grow: 1;
          margin: 0 10px;
          padding: 5px;
          border: 1px solid #ccc;
          background-color: #f0f0f0;
          outline: none;
      `;

      navContainer.appendChild(pathDisplay);

      domElement.appendChild(navContainer);

      const buttonContainer = document.createElement('div');
      buttonContainer.style.cssText = `
          display: flex;
          justify-content: space-between;
          padding: 5px;
          border-top: 1px solid #ccc;
      `;

      let selectedFilePathButton = document.createElement('button');
      selectedFilePathButton.textContent = 'Selected File Path';
      selectedFilePathButton.style.cssText = `
          width: 48%;
          margin-top: 5px;
      `;
      selectedFilePathButton.addEventListener('click', function () {
        let data = graph.save();
        const nodeIndex = data.nodes.findIndex(node => node.id === Nodeid);
        const memEl = document.getElementById(`memory-${Nodeid}`);
        if (memEl) {
            const ev = new Event('input', { bubbles: true, cancelable: true });
            memEl.value = pathDisplay.value;
            memEl.dispatchEvent(ev);
            if (domElement && domElement.parentNode) {
                domElement.parentNode.removeChild(domElement);
            } else {
                console.error('domElement or its parentNode is null, cannot remove the element.');
            }
        }
        data.nodes[nodeIndex].Inputs.forEach(input => {
            if (input.Id === id) {
                // 删除旧的文件路径元素
                if (domElement && domElement.parentNode) {
                    domElement.parentNode.removeChild(domElement);
                } else {
                    console.error('domElement or its parentNode is null, cannot remove the element.');
                }

                // 清理 domBlocks
                const index = domBlocks.findIndex(block => block.id === `dom-${Nodeid}-${id}-FilePath`);
                if (index > -1) {
                    domBlocks.splice(index, 1);
                }

                // 保存路径
                input.Context = pathDisplay.value;

                // 同步界面
                const ev = new Event('input', { bubbles: true, cancelable: true });
                const uniqueId = `unique-textarea-${Nodeid}-${input.Id}`;
                const txtEl = document.getElementById(uniqueId);
                if (txtEl) {
                    txtEl.value = pathDisplay.value;
                    txtEl.dispatchEvent(ev);
                }

                return; // 终止循环
            }
        });
    });
    
      buttonContainer.appendChild(selectedFilePathButton);

      const cancelButton = document.createElement('button');
      cancelButton.textContent = 'Cancel';
      cancelButton.style.cssText = `
          width: 48%;
          margin-top: 5px;
      `;
      cancelButton.addEventListener('click', function() {
          domElement.parentNode.removeChild(domElement);
          const index = domBlocks.findIndex(block => block.id === `dom-${id}-FilePath`);
          if (index > -1) {
              domBlocks.splice(index, 1);
          }
      });
      buttonContainer.appendChild(cancelButton);

      domElement.appendChild(buttonContainer);

      let currentPath = '';
      if(FilePath!='')
        currentPath = FilePath;
      let historyStack = [];
      let forwardStack = [];
      loadDirectory(currentPath, vessel, selectedFilePathButton, pathDisplay);
      console.log('Creating domElement:', domElement);
      document.getElementById('graph-container').appendChild(domElement);
      console.log('domElement added to body');

      vessel.addEventListener('click', function(e) {
          if (e.target === vessel) {
              pathDisplay.value = currentPath;
          }
      });

      function formatPath(path) {
          return path.replace(/\\/g, '\\\\').replace(/\\\\+/g, '\\\\');
      }

      function loadDirectory(path, container, selectedFilePathButton, pathDisplay, isUserInput = false) {
          if (path === '') {
              const drives = ['C:\\', 'D:\\', 'E:\\', 'F:\\','@TempFiles','@NoteBook','@Memory','@Nodes','@WorkFlow'];
              container.innerHTML = '';
              drives.forEach(drive => {
                  const element = document.createElement('div');
                  element.className = 'item-container';
                  element.style.cssText = `
                      display: flex;
                      flex-direction: column;
                      align-items: center;
                      width: 80px;
                      margin: 10px;
                      text-align: center;
                  `;
                  
                  const icon = document.createElement('img');
                  icon.src = '/static/icons/drive-icon.png';
                  icon.style.cssText = `
                      width: 48px;
                      height: 48px;
                      margin-bottom: 5px;
                  `;

                  const text = document.createElement('span');
                  text.textContent = drive;
                  text.style.cssText = `
                      color: #121212;
                      font-size: 12px;
                      white-space: pre-wrap;
                      word-wrap: break-word;
                      word-break: break-all;
                  `;

                  element.appendChild(icon);
                  element.appendChild(text);

                  element.addEventListener('click', function() {
                      loadDirectory(drive, container, selectedFilePathButton, pathDisplay);
                  });

                  container.appendChild(element);
              });
          } else {
              if (currentPath && !isUserInput) {
                  historyStack.push(currentPath);
              }

              fetch('/browse', {
                  method: 'POST',
                  headers: {
                      'Content-Type': 'application/json'
                  },
                  body: JSON.stringify({ path: path })
              })
              .then(response => response.json())
              .then(data => {
                  if (data.error) {
                      if (isUserInput) {
                          container.innerHTML = '<p style="padding: 10px; color: red;">路径错误</p>';
                      }
                      console.error('错误:', data.error || '目录中没有文件。');
                  } else {
                      currentPath = formatPath(path);
                      pathDisplay.value = currentPath;
                      updateUI(data, currentPath, container, selectedFilePathButton, pathDisplay);
                  }
              })
              .catch(error => {
                  if (isUserInput) {
                      container.innerHTML = '<p style="padding: 10px; color: red;">路径错误</p>';
                  }
                  console.error('错误:', error);
              });
          }
      }
      pathDisplay.addEventListener('input', function() {
        const newPath = pathDisplay.value;
        if (newPath) {
            fetch('/browse', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ path: newPath })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error || data.length === 0) {
                    vessel.innerHTML = '<p style="padding: 10px; color: red;">路径错误</p>';
                    console.error('错误:', data.error || '目录中没有文件。');
                } else {
                    currentPath = formatPath(newPath);
                    updateUI(data, currentPath, vessel, selectedFilePathButton, pathDisplay);
                }
            })
            .catch(error => {
                vessel.innerHTML = '<p style="padding: 10px; color: red;">路径错误</p>';
                console.error('错误:', error);
            });
        }
    });
    
    function updateUI(items, path, container, selectedFilePathButton, pathDisplay) {
          container.innerHTML = '';
          items.forEach(item => {
              const element = document.createElement('div');
              element.className = 'item-container';
              element.style.cssText = `
                  display: flex;
                  flex-direction: column;
                  align-items: center;
                  width: 80px;
                  margin: 10px;
                  text-align: center;
              `;

              const icon = document.createElement('img');
              icon.src = item.is_dir ? '/static/icons/folder-icon.png' : '/static/icons/file-icon.png';
              icon.style.cssText = `
                  width: 48px;
                  height: 48px;
                  margin-bottom: 5px;
              `;

              const text = document.createElement('span');
              text.textContent = item.name;
              text.style.cssText = `
                  color: #121212;
                  font-size: 12px;
                  white-space: pre-wrap;
                  word-wrap: break-word;
                  word-break: break-all;
              `;

              element.appendChild(icon);
              element.appendChild(text);

              element.addEventListener('click', function(e) {
                  e.stopPropagation();
                  document.querySelectorAll('.item-container').forEach(el => {
                      el.style.backgroundColor = 'white';
                  });
                  element.style.backgroundColor = '#d3d3d3';
                  if (item.is_dir) {
                      loadDirectory(item.path, container, selectedFilePathButton, pathDisplay);
                  } else {
                      pathDisplay.value = formatPath(item.path);
                  }
              });

              container.appendChild(element);
          });
      }
        function navigateBack() {
          // 检测路径是否是根目录或空路径，并检查最后一个 '\' 后面是否有其他字符
          console.log('currentPath:', currentPath, (currentPath.match(/\\/g) || []).length);
      
          // 使用正则表达式来检测路径是否符合要求
          // 匹配根路径或路径中最后一个 '\' 后没有其他字符的情况
          const regex = /^([A-Z]:\\)$|(^[A-Z]:\\[^\\]+$)/i;
      
          if (!regex.test(currentPath) && (currentPath.match(/\\/g) || []).length <= 1) {
              pathDisplay.value = '';
              currentPath = ''; // 清空 currentPath
              loadDirectory('', vessel, selectedFilePathButton, pathDisplay); // 跳转回驱动选择界面
              return;
          }
      
          if (currentPath.includes('\\') && currentPath.lastIndexOf('\\') > 2) {
              forwardStack.push(currentPath);
              currentPath = currentPath.replace(/\\+$/, '');
              let pathParts = currentPath.split('\\');
              pathParts.pop();
              if (pathParts.length > 0) {
                  currentPath = pathParts.join('\\');
                  loadDirectory(currentPath, vessel, selectedFilePathButton, pathDisplay);
              } else {
                  console.log('已经在根目录，无法继续后退');
              }
          }
      }
    
      function navigateForward() {
        if (forwardStack.length > 0) {
            currentPath = forwardStack.pop();
            loadDirectory(currentPath, vessel, selectedFilePathButton, pathDisplay);
        }
      }
  }
}
function populateSelectBoxFromObject(addedKeys, obj, parentKey = "", selectBoxTemp) {
  function addOptionsFromObject(addedKeys, obj, parentKey = "", selectBoxTemp) {
    // 检查 obj 是否为字符串
    if (typeof obj === 'string') {
      // 如果是字符串，直接添加为选项
      if (!addedKeys.has(obj)) {
        const option = document.createElement('option');
        option.value = obj;
        option.color = 'black';
        option.text = obj;
        selectBoxTemp.appendChild(option);
        addedKeys.add(obj);
      }
    }
    // 检查 obj 是否为数组
    else if (Array.isArray(obj)) {
      // 如果是数组，直接排序并添加选项
      const sortedItems = obj.sort((a, b) => {
        const numA = parseInt(a.split('/')[0]);
        const numB = parseInt(b.split('/')[0]);
        return numA - numB;  // 升序排列
      });

      for (let i = 0; i < sortedItems.length; i++) {
        const fullKey = sortedItems[i];
        if (!addedKeys.has(fullKey)) {
          const option = document.createElement('option');
          option.value = fullKey;
          option.color = 'black';
          option.text = fullKey;
          selectBoxTemp.appendChild(option);
          addedKeys.add(fullKey);
        }
      }
    } else if (typeof obj === 'object' && obj !== null) {
      // 如果是对象，保持原有的处理逻辑
      const keys = Object.keys(obj).sort((a, b) => {
        const numA = parseInt(a.split('/')[0]);
        const numB = parseInt(b.split('/')[0]);
        return numB - numA;
      });

      for (let i = keys.length - 1; i >= 0; i--) {
        const key = keys[i];
        if (obj.hasOwnProperty(key)) {
          const fullKey = parentKey ? `${parentKey}/${outputKey}` : key;
          if (!addedKeys.has(fullKey)) {
            const option = document.createElement('option');
            option.value = fullKey;
            option.text = fullKey;
            option.color = 'black';
            option.style.color = 'black';
            selectBoxTemp.appendChild(option);
            addedKeys.add(fullKey);
          }

          const value = obj[key];
          if (typeof value === 'object' && !Array.isArray(value)) {
            addOptionsFromObject(addedKeys, value, fullKey, selectBoxTemp);
          }
        }
      }
    }
  }

  addOptionsFromObject(addedKeys, obj, parentKey, selectBoxTemp);
}


function SearchOutput(id,IdTemp)
{
let dataTemp = graph.save();

let nodeTemp = dataTemp.nodes.filter(node => node.id === id);
let outputTemp = nodeTemp[0].Outputs.filter(output => output.Id === IdTemp)[0];
return outputTemp;
}
function adjustHeight(textarea) {
  textarea.style.height = 'auto'; // 重置高度以获得正确的滚动高度
  textarea.style.height = `${textarea.scrollHeight}px`;
}
function CreatDetaile(Item)
  {
    // 确保 item.model 中包含 x, y 位置和 id
    const { x, y, id,width,height,label,Inputs,Outputs,NodeKind,prompt,SystemPrompt,ReTryNum,name,Top_p,presence_penalty,frequency_penalty,temperature,max_tokens,OriginalTextSelector,OriginalTextName,InputIsAdd,OutputsIsAdd} = Item.model;
    // 创建 DOM 元素或者更新现有元素
    console.log('Inputs',InputIsAdd,OutputsIsAdd,Outputs);
    let domElement = document.getElementById(`dom-${id}`);
  if (!domElement) {
    domElement = document.createElement('div');
    domElement.id = `dom-${id}`;
    document.className = 'Nodes';
    domElement.style.cssText = `
      position: absolute;
      left: ${500}px;
      top: ${500}px;
      width: ${600}px;
      height: ${400}px;
      border-radius: 10px;
    `;
    const NameId = document.createElement('input'); // 创建 input 元素而不是 div
    NameId.value = label; // 设置输入框的初始值为 id
    NameId.style.cssText = `
        position: absolute;
        left: 24px; // 使用 px，因为这是 CSS 中的单位
        top: 30px; // 使用 px
        width: 200px; // 可以根据需要调整宽度
        height: 30px; // 可以根据需要调整高度
    `;
    NameId.addEventListener('focus', function() {
    });

    // 当输入框失去焦点时触发
    NameId.addEventListener('input', function() {
        ChangeNodeLabel(id,NameId.value,-1);
    });
    domElement.appendChild(NameId);
    const dragBar = document.createElement('div');
    dragBar.className = 'drag-bar';
    domElement.appendChild(dragBar);

    // 添加图标到 .drag-bar
    const icons = ['w-out'];
    icons.forEach(iconClass => {
        const icon = document.createElement('div');
        icon.className = iconClass;
        icon.style.left=-5;
        icon.style.top=-5;
        icon.style.width=20;
        icon.style.height=20;
        dragBar.appendChild(icon);
        icon.addEventListener('click', function() {
          domElement.parentNode.removeChild(domElement); // 移除 DOM 元素
          // 从数组中移除
          const index = domBlocks.findIndex(block => block.id === `dom-${id}`);
          if (index > -1) {
            domBlocks.splice(index, 1);
          }
        });
    });
    // 创建 .Vessel 并设置内容

    // 创建边缘可拖动区域
    const edges = ['edge-top', 'edge-bottom', 'edge-right', 'edge-left'];
    edges.forEach(edgeClass => {
        const edge = document.createElement('div');
        edge.className = `edge ${edgeClass}`;
        domElement.appendChild(edge);
    });
    // 创建角落可拖动区域
    const corners = ['corner-lt', 'corner-lb', 'corner-rt', 'corner-rb'];
    corners.forEach(cornerClass => {
        const corner = document.createElement('div');
        corner.className = `corner ${cornerClass}`;
        domElement.appendChild(corner);
    });
    const vessel = document.createElement('div');
    vessel.className = 'Vessel';

    domElement.appendChild(vessel);
    // 修改 ResetColumn 的样式，参考 ReactColumn 的样式
    const ResetColumn = document.createElement('div');
    ResetColumn.className = 'settings-panel'; // 改为使用统一的类名

    // 添加灰色背景和宽度自适应样式
    ResetColumn.style.cssText = `
        background:rgb(163, 163, 163) !important;  /* 灰色背景 */
        width: fit-content !important;   /* 宽度自适应内容 */
        min-width: 580px;               /* 最小宽度 */
        max-width: 580px;               /* 最大宽度（可选） */
`;


    // === ReTryNum 行（label 和 input 要放在同一 .setting-row 里）===
    const inputContainer = document.createElement('div');
    inputContainer.className = 'setting-row';

    const ReTryNumlabel = document.createElement('label');
    ReTryNumlabel.textContent = 'ReTryNum';
    ReTryNumlabel.style.marginRight = '15px';
    ReTryNumlabel.style.fontWeight = 'bold';

    const input = document.createElement('input');
    input.type  = 'number';
    input.id    = `ReTryNum-${id}`;
    input.value = ReTryNum;
    input.min   = '1';

    // 先把 label、input 都塞进 inputContainer，再挂到 ResetColumn
    inputContainer.appendChild(ReTryNumlabel);
    inputContainer.appendChild(input);
    ResetColumn.appendChild(inputContainer);
    input.addEventListener('change',()=>{
      let v = parseInt(input.value);
      if(v<1)
      {
        input.value = 1;
      }
      let nd = graph.save().nodes.find(n=>n.id==id);
      nd.ReTryNum = v;
      ChangeDatas(graph.save());
    });
    
    vessel.appendChild(ResetColumn);


    // 创建输入列
 // 创建输入列
    // 创建输入列并添加标签
    if(NodeKind.includes('LLm'))
    {
      // ====== IsReact 勾选框 ======
      const isReactContainer = document.createElement('div');
      isReactContainer.className = 'setting-row';

      const isReactCheckbox = document.createElement('input');
      isReactCheckbox.type = 'checkbox';
      isReactCheckbox.id = `isReact-${id}`;

      let nodeData = graph.save().nodes.find(n => n.id == id);
      isReactCheckbox.checked = !!(nodeData && nodeData.IsReact);

      const isReactLabel = document.createElement('label');
      isReactLabel.textContent = 'IsReact';
      isReactLabel.htmlFor  = isReactCheckbox.id;
      isReactLabel.style.marginRight = '15px';

      isReactContainer.appendChild(isReactLabel);
      isReactContainer.appendChild(isReactCheckbox);
      

      // ====== ReactNum ======
      const reactNumContainer = document.createElement('div');
      reactNumContainer.className = 'setting-row';
      reactNumContainer.style.display = isReactCheckbox.checked ? 'flex' : 'none';

      const reactNumLabel = document.createElement('label');
      reactNumLabel.textContent = 'ReactNum:';

      const reactNumInput = document.createElement('input');
      reactNumInput.type = 'number';
      reactNumInput.min   = '3';
      reactNumInput.style.width = '60px';
      reactNumInput.value = nodeData && nodeData.ReactNum !== undefined ? nodeData.ReactNum : 3;

      reactNumContainer.appendChild(reactNumLabel);
      reactNumContainer.appendChild(reactNumInput);
      reactNumInput.addEventListener('input', ()=>{
        let v = Math.max(3, parseInt(reactNumInput.value) || 3);
        reactNumInput.value = v;
        let nd = graph.save().nodes.find(n=>n.id==id);
        nd.ReactNum = v;
        ChangeDatas(graph.save());
      });
      // ====== Memory（单独一行） ======
      const memoryContainer = document.createElement('div');
      memoryContainer.className = 'setting-row full-width';   // ← 仅新增这个类名 
      memoryContainer.style.display   = isReactCheckbox.checked ? 'flex' : 'none';
      memoryContainer.style.flexBasis = '100%';           // 换行显示

      const memoryLabel = document.createElement('label');
      memoryLabel.textContent = 'Memory:';

      const memoryInput = document.createElement('input');
      memoryInput.type = 'text';
      memoryInput.id = `memory-${id}`; 
      memoryInput.style.width = '300px';
      memoryInput.placeholder = 'Memory 路径';
      memoryInput.value = (nodeData && nodeData.Memory) ? nodeData.Memory : 'New Memory';

      const memoryBtn = document.createElement('button');
      memoryBtn.textContent = 'FilePath';
      memoryBtn.className   = 'filepath-btn';
      memoryBtn.onclick     = () => CreatFilePath('Memory', id);

      memoryContainer.appendChild(memoryLabel);
      memoryContainer.appendChild(memoryInput);
      memoryContainer.appendChild(memoryBtn);

      // ====== Tools ======
      const toolsLabel = document.createElement('label');
      toolsLabel.textContent = 'Tools:';

      const toolsContainer = document.createElement('div');
      toolsContainer.className = 'tools-container setting-row full-width';
      toolsContainer.style.cssText = `
          display: ${isReactCheckbox.checked ? 'flex' : 'none'};
          flex-wrap: wrap;
          gap: 8px;
          padding: 12px;
          border: 1px solid var(--ui-border);
          border-radius: var(--ui-radius-small);
          background: var(--ui-panel);
          width: fit-content;
          min-width: 200px;
          max-width: 100%;
          min-height: 50px;
          height: auto;
      `;
      // 在创建 toolsContainer 后添加：
      toolsContainer.style.setProperty('--tools-min-width', '300px'); // 调整最小宽度
      toolsContainer.style.setProperty('--tools-max-width', '800px'); // 调整最大宽度  
      toolsContainer.style.setProperty('--tools-min-height', '80px');  // 调整最小高度

      /* 提取 fileListArray 中的 filename 去掉 .py */
      const toolOptions = (typeof fileListArray !== 'undefined')
        ? fileListArray.map(f => (f.filename || '').replace(/\.py$/,''))
        : [];

      /* 渲染工具气泡 */
      function renderToolBubbles(){
        Array.from(toolsContainer.querySelectorAll('.tool-bubble')).forEach(e=>e.remove());
        let nd = graph.save().nodes.find(n=>n.id==id) || {};
        let arr = Array.isArray(nd.Tools) ? nd.Tools : [];
        arr.forEach((tool,idx)=>{
          const bubble = document.createElement('span');
          bubble.className = 'tool-bubble';
          bubble.textContent = tool.name;

          const delBtn = document.createElement('span');
          delBtn.className = 'close';
          delBtn.textContent = '×';
          bubble.appendChild(delBtn);

          delBtn.onclick = e=>{
            e.stopPropagation();
            let d = graph.save().nodes.find(n=>n.id==id);
            if(d && Array.isArray(d.Tools)){
              d.Tools.splice(idx,1);
              ChangeDatas(graph.save());
              renderToolBubbles();
            }
          };

          // 在 renderToolBubbles 函数中，修改 bubble.onclick 部分：
          bubble.onclick = e=>{
            if(e.target===delBtn) return;
            
            // 1. 创建遮罩和弹窗
            let overlay = document.createElement('div');
            overlay.style = `
              position: fixed; left: 0; top: 0; width: 100vw; height: 100vh;
              background: rgba(0,0,0,0.3); z-index: 9999; 
              display: flex; align-items: flex-start; justify-content: center;
              backdrop-filter: blur(8px); padding-top: 60px;
            `;

            // 修改第二处：弹窗容器宽度
            let popup = document.createElement('div');
            popup.style = `
              background: #ffffff; border-radius: 16px; 
              box-shadow: 0 20px 60px rgba(0,0,0,0.15), 0 8px 32px rgba(0,0,0,0.1);
              min-width: 680px; min-height: 200px; 
              position: relative; display: flex; flex-direction: column;
              overflow: hidden; transform: scale(0.9); opacity: 0;
              transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            `;
            // 动画进入效果
            setTimeout(() => {
                popup.style.transform = 'scale(1)';
                popup.style.opacity = '1';
            }, 10);
        
            // 2. 绿色标题栏
            let titleBar = document.createElement('div');
            titleBar.style = `
              background: linear-gradient(135deg, #34D399 0%, #10B981 100%);
              height: 50px; display: flex; align-items: center; justify-content: center;
              user-select: none; position: relative;
              box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
            `;
        
            let titleText = document.createElement('span');
            titleText.textContent = 'Tool Settings';
            titleText.style = `
              color: white; font-weight: 600; font-size: 16px; 
              text-shadow: 0 1px 2px rgba(0,0,0,0.1);
            `;
            titleBar.appendChild(titleText);
        
            // 3. 红色苹果风格关闭按钮
            let closeBtn = document.createElement('div');
            closeBtn.innerHTML = '×';
            closeBtn.style = `
              position: absolute; left: 6px; top: 40%; transform: translateY(-50%);
              width: 30px; height: 30px; border-radius: 50%; 
              background: #FF5F56; color: white; 
              display: flex; align-items: center; justify-content: center;
              font-size: 14px; font-weight: 500; cursor: pointer;
              transition: all 0.2s ease;
              border: 1px solid rgba(255,255,255,0.2);
              box-shadow: 0 2px 4px rgba(255, 95, 86, 0.3);
            `;
            
            closeBtn.onmouseenter = () => {
                closeBtn.style.background = '#FF3B30';
                closeBtn.style.transform = 'translateY(-50%) scale(1.1)';
                closeBtn.style.boxShadow = '0 3px 8px rgba(255, 95, 86, 0.5)';
            };
            closeBtn.onmouseleave = () => {
                closeBtn.style.background = '#FF5F56';
                closeBtn.style.transform = 'translateY(-50%) scale(1)';
                closeBtn.style.boxShadow = '0 2px 4px rgba(255, 95, 86, 0.3)';
            };
            
            closeBtn.onclick = () => {
                popup.style.transform = 'scale(0.9)';
                popup.style.opacity = '0';
                setTimeout(() => document.body.removeChild(overlay), 200);
            };
            
            titleBar.appendChild(closeBtn);
        
            // 4. 内容区域
            let content = document.createElement('div');
            content.style = `
              padding: 32px; display: flex; flex-direction: column; gap: 24px;
              flex: 1;
            `;
        
            // 5. 可编辑的工具名称
            let toolNameLabel = document.createElement('div');
            toolNameLabel.textContent = tool.name;
            toolNameLabel.style = `
              font-size: 20px; font-weight: 600; color: #1F2937;
              padding: 12px 16px; border: 2px solid transparent;
              border-radius: 8px; cursor: pointer; transition: all 0.2s ease;
              background: #F9FAFB; min-height: 24px;
              display: flex; align-items: center;
            `;
            
            // 悬停效果
            toolNameLabel.onmouseenter = () => {
                toolNameLabel.style.borderColor = '#10B981';
                toolNameLabel.style.background = '#F0FDF4';
            };
            toolNameLabel.onmouseleave = () => {
                if (!toolNameLabel.isEditing) {
                    toolNameLabel.style.borderColor = 'transparent';
                    toolNameLabel.style.background = '#F9FAFB';
                }
            };
        
            // 点击编辑功能
            toolNameLabel.onclick = () => {
                if (toolNameLabel.isEditing) return;
                
                toolNameLabel.isEditing = true;
                let currentText = toolNameLabel.textContent;
                
                let input = document.createElement('input');
                input.type = 'text';
                input.value = currentText;
                input.style = `
                  font-size: 20px; font-weight: 600; color: #1F2937;
                  border: none; outline: none; background: transparent;
                  width: 100%; padding: 0;
                `;
                
                toolNameLabel.textContent = '';
                toolNameLabel.appendChild(input);
                toolNameLabel.style.borderColor = '#10B981';
                toolNameLabel.style.background = '#F0FDF4';
                
                input.focus();
                input.select();
                
                // 完成编辑
                const finishEdit = () => {
                    let newName = input.value.trim();
                    toolNameLabel.isEditing = false;
                    
                    if (newName && newName !== currentText) {
                        // 更新数据
                        let d = graph.save().nodes.find(n=>n.id==id);
                        if(d && Array.isArray(d.Tools)){
                            let idx = d.Tools.indexOf(tool);
                            if(idx>-1){
                                d.Tools[idx].name = newName;
                                ChangeDatas(graph.save());
                                renderToolBubbles();
                                toolNameLabel.textContent = newName;
                            }
                        }
                    } else {
                        toolNameLabel.textContent = currentText;
                    }
                    
                    toolNameLabel.style.borderColor = 'transparent';
                    toolNameLabel.style.background = '#F9FAFB';
                };
                
                input.onblur = finishEdit;
                input.onkeydown = (e) => {
                    if (e.key === 'Enter') {
                        finishEdit();
                    } else if (e.key === 'Escape') {
                        toolNameLabel.isEditing = false;
                        toolNameLabel.textContent = currentText;
                        toolNameLabel.style.borderColor = 'transparent';
                        toolNameLabel.style.background = '#F9FAFB';
                    }
                };
            };
        
            let toolSection = document.createElement('div');
            toolSection.style = "display: flex; flex-direction: column; gap: 8px;";
            
            let toolLabel = document.createElement('div');
            toolLabel.textContent = 'Tool Name:';
            toolLabel.style = "font-size: 14px; font-weight: 500; color: #6B7280; margin-bottom: 4px;";
            
            toolSection.appendChild(toolLabel);
            toolSection.appendChild(toolNameLabel);
        
            // 6. 工具选择下拉框
            let filelistfiltered = fileList.filter(f=>f.NodeKind==='Normal');
            if(filelistfiltered.length === 0){
                alert('没有可用的 Normal 文件');
                return;
            }

            let toolSelectSection = document.createElement('div');
            toolSelectSection.style = "display: flex; flex-direction: column; gap: 8px;";

            let toolSelectLabel = document.createElement('div');
            toolSelectLabel.textContent = 'Select Tool:';
            toolSelectLabel.style = "font-size: 14px; font-weight: 500; color: #6B7280; margin-bottom: 4px;";

            let toolSelect = document.createElement('select');
            toolSelect.style = `
                width: 100%; padding: 12px 16px;
                border: 2px solid #E5E7EB; border-radius: 8px;
                font-size: 16px; outline: none; background: white;
                transition: border-color 0.2s ease; cursor: pointer;
            `;

            toolSelect.onfocus = () => toolSelect.style.borderColor = '#10B981';
            toolSelect.onblur = () => toolSelect.style.borderColor = '#E5E7EB';

            // 添加默认选项
            let defaultOpt = document.createElement('option');
            defaultOpt.value = '';
            defaultOpt.textContent = 'Tool Select';
            defaultOpt.disabled = true;
            defaultOpt.selected = true;
            toolSelect.appendChild(defaultOpt);

            // 添加文件选项
            filelistfiltered.forEach((f, index) => {
                let opt = document.createElement('option');
                let name = (f.filename || '').replace(/\.py$/, '');
                opt.value = index;
                opt.textContent = name;
                if (toolNameLabel.textContent === name) {
                    opt.selected = true; // 如果当前文本与选项匹配，则选中该选项
                    // 直接触发onchange事件
                    setTimeout(() => {
                      toolSelect.onchange && toolSelect.onchange();
                    }, 100);
                }
                toolSelect.appendChild(opt);
            });

            // 解析NodeFunction中的inputs信息
            function parseInputs(nodeFunction) {
              if (!nodeFunction) return [];
              
              const inputs = [];
              // 处理转义的换行符
              const text = nodeFunction.replace(/\\n/g, '\n');
              
              // 查找inputs部分
              const inputsMatch = text.match(/inputs?\s*:\s*([\s\S]*?)(?=outputs?|运行逻辑|$)/i);
              if (!inputsMatch) return [];
              
              const inputsText = inputsMatch[1];
              
              // 按行分割并逐行解析
              const lines = inputsText.split('\n').map(line => line.trim()).filter(line => line);
              
              let currentInput = null;
              
              // 清理字段值的函数 - 去掉末尾的反斜杠
              function cleanValue(value) {
                  return value.replace(/\\+$/, '').trim();
              }
              
              for (let i = 0; i < lines.length; i++) {
                  const line = lines[i];
                  
                  // 检测新的input项开始
                  if (line.match(/^\s*-\s*name\s*:/i)) {
                      // 保存上一个input
                      if (currentInput && currentInput.name) {
                          inputs.push(currentInput);
                      }
                      
                      // 开始新的input
                      const nameValue = line.replace(/^\s*-\s*name\s*:\s*/i, '').trim();
                      currentInput = {
                          name: cleanValue(nameValue),
                          type: 'string',
                          required: false,
                          description: ''
                      };
                  }
                  // 解析其他字段
                  else if (currentInput) {
                      if (line.match(/^\s*type\s*:/i)) {
                          const typeValue = line.replace(/^\s*type\s*:\s*/i, '').trim().toLowerCase();
                          currentInput.type = cleanValue(typeValue);
                      }
                      else if (line.match(/^\s*required\s*:/i)) {
                          const reqValue = line.replace(/^\s*required\s*:\s*/i, '').trim().toLowerCase();
                          currentInput.required = cleanValue(reqValue) === 'true';
                      }
                      else if (line.match(/^\s*description\s*:/i)) {
                          const descValue = line.replace(/^\s*description\s*:\s*/i, '').trim();
                          currentInput.description = cleanValue(descValue);
                      }
                  }
              }
              
              // 保存最后一个input
              if (currentInput && currentInput.name) {
                  inputs.push(currentInput);
              }
              
              console.log('最终解析结果:', inputs);
              return inputs;
          }

            // 创建输入控件
            function createInputControl(input) {
              console.log('Creating input control for:', input);
              const container = document.createElement('div');
              container.style = "margin-bottom: 16px;";
              
              // 标签容器
              const labelContainer = document.createElement('div');
              labelContainer.style = "display: flex; align-items: center; margin-bottom: 6px;";
              
              // 必填标记
              if (input.required) {
                  const requiredMark = document.createElement('span');
                  requiredMark.textContent = '*';
                  requiredMark.style = "color: #EF4444; font-weight: bold; margin-right: 4px; font-size: 16px;";
                  labelContainer.appendChild(requiredMark);
              }
              
              // 标签名称 - 黑色加粗
              const label = document.createElement('span');
              label.textContent = input.name;
              label.style = "font-size: 14px; font-weight: bold; color: #000000;";
              labelContainer.appendChild(label);
              
              container.appendChild(labelContainer);
              
              // 描述 - 灰色斜体
              if (input.description) {
                  const desc = document.createElement('div');
                  desc.textContent = input.description;
                  desc.style = `
                      font-size: 12px; color: #6B7280; 
                      margin-bottom: 8px; font-style: italic;
                  `;
                  container.appendChild(desc);
              }
              
              let inputElement;
              
              // 根据类型创建不同的输入控件
              if (input.type.includes('bool')) {
                  // 布尔类型 - 选择框
                  inputElement = document.createElement('select');
                  inputElement.style = `
                      width: 100%; padding: 12px 16px; border: 2px solid #E5E7EB; 
                      border-radius: 8px; font-size: 16px; outline: none; background: white;
                      transition: border-color 0.2s ease;
                  `;
                  
                  const trueOpt = document.createElement('option');
                  trueOpt.value = 'true';
                  trueOpt.textContent = 'True';
                  
                  const falseOpt = document.createElement('option');
                  falseOpt.value = 'false';
                  falseOpt.textContent = 'False';
                  
                  inputElement.appendChild(trueOpt);
                  inputElement.appendChild(falseOpt);
                  
              } else if (input.type.includes('int') || input.type.includes('num')) {
                  // 数字类型 - 数字输入框
                  inputElement = document.createElement('input');
                  inputElement.type = 'number';
                  inputElement.value = '0';
                  inputElement.style = `
                      width: 100%; padding: 12px 16px; border: 2px solid #E5E7EB; 
                      border-radius: 8px; font-size: 16px; outline: none;
                      transition: border-color 0.2s ease;
                  `;
                  
              } else {
                  // 字符串类型 - 文本输入框
                  inputElement = document.createElement('input');
                  inputElement.type = 'text';
                  inputElement.style = `
                      width: 100%; padding: 12px 16px; border: 2px solid #E5E7EB; 
                      border-radius: 8px; font-size: 16px; outline: none;
                      transition: border-color 0.2s ease;
                  `;
              }
              
              // 焦点样式
              inputElement.onfocus = () => inputElement.style.borderColor = '#10B981';
              inputElement.onblur = () => {
                  inputElement.style.borderColor = '#E5E7EB';
                  // 清除验证错误样式
                  if (inputElement.style.borderColor === 'rgb(239, 68, 68)') {
                      inputElement.style.borderColor = '#E5E7EB';
                  }
              };
              
              container.appendChild(inputElement);
              
              return { container, inputElement, input };
          }

            // 修改toolSelect的onchange事件
            toolSelect.onchange = () => {
              let selIndex = parseInt(toolSelect.value);
              if (isNaN(selIndex)) return;
              let file = filelistfiltered[selIndex];
              if (file) {
                  let toolName = (file.filename || '').replace(/\.py$/, '');

                  let d = graph.save().nodes.find(n => n.id == id);
                  if (d && Array.isArray(d.Tools)) {
                      let idx = d.Tools.findIndex(t => t.name === tool.name);
                      if (idx > -1) {
                          const inputs = parseInputs(file.NodeFunction);

                          // 记录当前输入值（如果有老的）
                          let existingTool = d.Tools[idx];
                          let previousInputs = existingTool.Inputs || [];
                          tool.name = toolName;
                          // 保存新的工具信息，仅保存当前值作为 Parameters
                          d.Tools[idx] = {
                              name: toolName,
                              filename: toolName,
                              Inputs: inputs.map((input, index) => {
                                // 直接按序号取 previous
                                let previous = previousInputs[index];
                                console.log('previous', previous, input);
                                return {
                                      Parameters: previous ? previous.Parameters : 'auto_input'  // 仅保存值
                                  };
                              })
                          };
                          toolNameLabel.textContent = toolName;
                          ChangeDatas(graph.save());
                          renderToolBubbles();

                          const existingInputsSection = content.querySelector('.inputs-section');
                          if (existingInputsSection) {
                              existingInputsSection.remove();
                          }

                          if (inputs.length > 0) {
                              const inputsSection = document.createElement('div');
                              inputsSection.className = 'inputs-section';
                              inputsSection.style = `
                                  margin-top: 20px; padding-top: 20px; 
                                  border-top: 1px solid #E5E7EB;
                                  max-height: 400px;
                                  overflow-y: auto;
                              `;

                              const inputsTitle = document.createElement('div');
                              inputsTitle.textContent = 'Tool Parameters:';
                              inputsTitle.style = `
                                  font-size: 16px; font-weight: 600; color: #374151; 
                                  margin-bottom: 16px;
                              `;
                              inputsSection.appendChild(inputsTitle);

                              inputs.forEach((input, index) => {
                                const controlData = createInputControl(input);
                                const savedValue = d.Tools[idx].Inputs[index]?.Parameters;

                                if (controlData.inputElement) {
                                  if (savedValue === 'auto_input') {
                                    controlData.inputElement.value = '';
                                    controlData.inputElement.placeholder = 'auto_input';
                                    controlData.inputElement.style.fontStyle = 'italic';
                                    controlData.inputElement.style.color = '#9CA3AF';
                                  } else {
                                    controlData.inputElement.value = savedValue || '';
                                    controlData.inputElement.placeholder = '';
                                    controlData.inputElement.style.fontStyle = 'normal';
                                    controlData.inputElement.style.color = '#111827';
                                  }

                                  controlData.inputElement.addEventListener('input', () => {
                                    const value = controlData.inputElement.value.trim();
                                    const inputRef = d.Tools[idx].Inputs[index];
                                    if (inputRef) {
                                      inputRef.Parameters = value;
                                    }

                                    if (!value) {
                                      controlData.inputElement.placeholder = 'auto_input';
                                      controlData.inputElement.style.fontStyle = 'italic';
                                      controlData.inputElement.style.color = '#9CA3AF';
                                    } else {
                                      controlData.inputElement.placeholder = '';
                                      controlData.inputElement.style.fontStyle = 'normal';
                                      controlData.inputElement.style.color = '#111827';
                                    }

                                    ChangeDatas(graph.save());
                                  });
                                }

                                inputsSection.appendChild(controlData.container);
                              });


                              content.appendChild(inputsSection);
                          }
                      }
                  }
              }
          };

            toolSelectSection.appendChild(toolSelectLabel);
            toolSelectSection.appendChild(toolSelect);

            // 7. 组装弹窗
            content.appendChild(toolSection);
            content.appendChild(toolSelectSection);
            popup.appendChild(titleBar);
            popup.appendChild(content);
            overlay.appendChild(popup);
            document.body.appendChild(overlay);
            
        };
      
          toolsContainer.appendChild(bubble);
        });
      }

      /* “+” 按钮 & 下拉列表 */
      const addToolBtn = document.createElement('span');
      addToolBtn.className = 'add-tool-btn';
      addToolBtn.textContent = '+';

      const toolSelect = document.createElement('select');
      toolSelect.id    = 'tool-select';
      toolSelect.style.display = 'none';
      toolOptions.forEach(t=>{
        const opt = document.createElement('option');
        opt.value = opt.textContent = t;
        toolSelect.appendChild(opt);
      });

      /* === "+" 按钮：自动递增命名 === */
      addToolBtn.onclick = () => {
        const d = graph.save().nodes.find(n => n.id === id);
        if (!d.Tools) d.Tools = [];

        let seq = 1;
        while (d.Tools.find(t => t.name === `Tool${seq}`)) seq++;
        const newToolName = `Tool${seq}`;

        d.Tools.push({
            name: newToolName,
            filename: null,      // ✅ 用 filename 替代 file
            Inputs: []
        });

        ChangeDatas(graph.save());
        renderToolBubbles();
    };
      toolSelect.onchange = ()=>{
        const newTool = toolSelect.value;
        if(!newTool) return;
        let d = graph.save().nodes.find(n=>n.id==id);
        if(!d.Tools) d.Tools = [];
        if(!d.Tools.includes(newTool)){
          d.Tools.push(newTool);
          ChangeDatas(graph.save());
          renderToolBubbles();
        }
        toolSelect.style.display='none';
      };
      toolsContainer.appendChild(toolsLabel);
      toolsContainer.appendChild(addToolBtn);
      toolsContainer.appendChild(toolSelect);
      
      // 在 toolsContainer 中添加工具气泡

      /* 初始渲染 */
      renderToolBubbles();

      /* 监听区 */
      isReactCheckbox.addEventListener('change',()=>{
        let nd = graph.save().nodes.find(n=>n.id==id);
        nd.IsReact = isReactCheckbox.checked;
        ChangeDatas(graph.save());
        reactNumContainer.style.display = nd.IsReact ? 'flex':'none';
        memoryContainer.style.display   = nd.IsReact ? 'flex':'none';
        toolsContainer.style.display    = nd.IsReact ? 'flex':'none';
        // 如果有 toolsLabelContainer 也要加上
        // toolsLabelContainer.style.display = nd.IsReact ? 'flex':'none';
    });


      reactNumInput.addEventListener('input',()=>{
        let nd = graph.save().nodes.find(n=>n.id==id);
        nd.ReactNum = parseInt(reactNumInput.value)||0;
        ChangeDatas(graph.save());
      });

      memoryInput.addEventListener('input',()=>{
        let nd = graph.save().nodes.find(n=>n.id==id);
        nd.Memory = memoryInput.value || 'New Memory';
        ChangeDatas(graph.save());
      });

      /* 插入到 ResetColumn */
      ResetColumn.appendChild(isReactContainer);
      ResetColumn.appendChild(reactNumContainer);
      ResetColumn.appendChild(memoryContainer);
      ResetColumn.appendChild(toolsContainer);
    }
    if(NodeKind=='ArrayTrigger_DataBase')
    {
      const inputColumn = document.createElement('div');
      inputColumn.className = 'column';
      const inputLabel = document.createElement('div');
      inputLabel.textContent = 'Input'; // 设置文本
      inputLabel.className = 'column-label'; // 设置样式类
      inputColumn.appendChild(inputLabel);
      vessel.appendChild(inputColumn);
      // 调整textarea高度以适应内容
      // 输入框空格键增长逻辑
      let IdTemp='';
      const outputColumn = document.createElement('div');
      outputColumn.className = 'column';
      const addNode1 = document.createElement('div');
      addNode1.className = 'column-AddNode'; // 使用之前定义的样式类
      addNode1.style.left = '60px'; // 设置左边距
      outputColumn.appendChild(addNode1);
      const outputLabel = document.createElement('div');
      outputLabel.textContent = 'Output'; // 设置文本
      outputLabel.className = 'column-label'; // 设置样式类
      outputColumn.appendChild(outputLabel);
      // 将输入和输出列添加到节点容器中
      addNode1.onmousedown = function() {
        let data=graph.save();
        data.nodes.forEach((node) => {
          if(node.id == id && node.TempColumns!=undefined && node.TempColumns!=null && node.TempColumns.length!=0)
          {
            IdTemp='Output' + (node.Outputs.length + 1).toString();
            let TempName = 'Output' + (node.Outputs.length + 1).toString();
            let counter = 1; // 新增一个计数器
            // 检查是否重名，如果重名则+1继续检查
            while (node.Outputs.some(output => output.name === TempName)) {
                TempName = 'Output' + (node.Outputs.length + 1 + counter).toString(); // 使用计数器调整名称
                counter++; // 每次循环递增计数器
            }
            node.Outputs.push({
              'Num': 0,
              'Kind': 'String',
              'Id': IdTemp,
              'Context': '',
              'Boolean': false,
              'Isnecessary': false,
              'name': TempName,
              'Link': 0,
              'IsLabel': false,
          });
          const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
          node.anchorPoints = node.Inputs.map((node, index) => {
              const anchorHeight = 60 + index * 20;
              return [0.05, anchorHeight / maxHeight]
            }).concat(node.Outputs.map((node, index) => {
              const anchorHeight = 60 + index * 20;
              return [0.95, anchorHeight / maxHeight]
            })).concat([[0, 0]]);
          CreatOutputs(node.Outputs[node.Outputs.length - 1],node.Outputs.length - 1,IdTemp);
          ChangeDatas(data);
          }
        });
        RefreshEdge();
      };
      vessel.appendChild(outputColumn);
      // 添加元素到 DOM
    function CreatInputs(input,index,IdTemp)
    {
      const inputContainer = document.createElement('div');
      inputContainer.className = 'input-container';

      // 创建显示输入名称的输入框
      const inputName = document.createElement('input');
      inputName.value = input.name;
      inputContainer.appendChild(inputName);

      // 创建选择框
      const selectBox = document.createElement('select');
      const optionLink = document.createElement('option');
      optionLink.value = 'link';
      optionLink.text = 'Link';
      const optionLabel = document.createElement('option');
      optionLabel.value = 'Input';
      optionLabel.text = 'Input';
      selectBox.appendChild(optionLink);
      selectBox.appendChild(optionLabel);
      inputContainer.appendChild(selectBox);

      function RefreshOutput() {
        // 确保outputColumn是已定义的，并且开始清理操作
        if (outputColumn) {
            // 获取所有子元素
            let children = outputColumn.children;
            // 从后往前遍历子元素，以便安全删除元素
            for (let i = children.length - 1; i >= 0; i--) {
                // 假设我们用className来识别是否是addNode1
                if (children[i].className !== 'column-AddNode' && children[i].className !== 'column-label'&& child.className!=='column-SubNode') {
                    outputColumn.removeChild(children[i]); // 删除不是addNode1的元素
                }
            }
        }

        // 这里添加Outputs中的addNode1元素，或其他处理逻辑
        Outputs.forEach((output, index) => {
            // 检查是否是我们需要添加的特定节点addNode1
              CreatOutputs(output, index, output.Id);
        });
    }


    // 假设Outputs是全局变量，如果不是，需要确保它在这个函数中是可访问的
      if(input.Isnecessary==false)
      {
        const SubNode = document.createElement('div');
        SubNode.className = 'column-SubNode'; // 使用之前定义的样式类
        SubNode.style.left = '450px'; // 设置与标签之间的间距
        inputContainer.appendChild(SubNode);
        SubNode.onmousedown = function() {//删除这个矛点
          let data=graph.save();
          data.nodes.forEach((node) => {
            if(node.id == id)
            {
              //通过IdTemp删除这个矛点
              node.Inputs.forEach((input,index) => {
                  if(input.Id == IdTemp)
                  {
                    node.Inputs.splice(index,1);
                    RefreshOutput();
                  }
                }
              );
              const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
              node.anchorPoints = node.Inputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.05, anchorHeight / maxHeight]
                }).concat(node.Outputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.95, anchorHeight / maxHeight]
                })).concat([[0, 0]]);
              ChangeDatas(data);
              //移除inputContainer
              inputContainer.parentNode.removeChild(inputContainer);
            }
          });
          RefreshEdge();
        }
      }
      let labelTextarea = document.createElement('textarea'); // 在外部声明变量以便在不同的作用域中访问
      labelTextarea.className = 'input-textarea';
      if(input.IsLabel==true)
      {
        selectBox.value = 'Input';
        handleChange('Input');
      }
      // 处理选择框变化
      
      function handleChange(value) {
        console.log('value测试',value);
        let pathButton = null; // 在函数内部初始化为 null
        // 如果之前添加了文本区域且现在选择是“Link”，则移除文本区域
        let data = graph.save();
        data.edges.forEach(edge => {
            if (edge.target == id && edge.targetAnchor == index) {
                const item = graph.findById(edge.id);
                const targetNode = graph.findById(edge.target);
                const targetAnchor = targetNode.getContainer().find(ele => ele.get('anchorPointIdx') === anchorIndex);
                targetAnchor.set('links', targetAnchor.get('links') + 1);
                ChangeLink(targetAnchor);
                graph.remove(item);
            }
        });
    
        if (labelTextarea && value === 'link') {
            inputContainer.removeChild(labelTextarea);
            labelTextarea = null; // 确保引用被清除
            ChangeAnchorValue(id, '', 'link', input.Id);
            
            if (pathButton && inputContainer.contains(pathButton)) {
                inputContainer.removeChild(pathButton);
                pathButton = null; // 确保 pathButton 被正确清除
            }
        } else if (value === 'Input') {
            // 如果当前选择是“Input”，则添加文本区域
            if(index!=1)
            {
              
              labelTextarea = document.createElement('textarea');
              labelTextarea.style.width = '550px'; // 设置固定宽度
              labelTextarea.style.height = '20px'; // 初始高度
              labelTextarea.style.overflow = 'hidden'; // 防止滚动条出现
              labelTextarea.style.verticalAlign = 'top'; // 输入行字符居上
              labelTextarea.style.lineHeight = '20px'; // 设置行高以匹配初始高度
              labelTextarea.style.resize = 'vertical';
              labelTextarea.addEventListener('input', function () {
                // 重置高度以计算新的高度
                this.style.height = 'auto';
                // 设置新的高度
                this.style.height = `${this.scrollHeight}px`;
                let isOk = true; // 假定输入有效
                if (input.Kind == 'Num') {
                    if (labelTextarea.value.match(/^[0-9]+$/)) {
                        isOk = true; // 如果是数字，将 isOk 设置为 true
                    } else {
                        // 如果不符合条件，则弹出提示
                        isOk = false;
                        alert("类型不符，您应该输入数字！");
                    }
                }
                if (labelTextarea.value.trim() === '') {
                    isOk = false; // 如果输入为空，则将 isOk 设置为 false
                    alert("输入不能为空！");
                }
    
                if (isOk) {
                  if (index == 0) {
                      let pathButton = inputContainer.querySelector('button'); 
                      pathButton.innerHTML = 'Select Path <span class="circle-loader"></span>';
                      let filePath = labelTextarea.value;
              
                      fetch('/read_DataBase', {
                          method: 'POST',
                          headers: {
                              'Content-Type': 'application/json'
                          },
                          body: JSON.stringify({ 'file_path': filePath })
                      })
                      .then(response => response.json())
                      .then(data => {
                          if (data.status === 'success') {
                              pathButton.innerHTML = 'Select Path <span style="color: green;">(Load Success)</span>';
                              let dataTemp=graph.save();
                              dataTemp.nodes.forEach((node) => {
                                if(node.id == id)
                                {
                                  node.TempColumns= data.columns;
                                }
                              });
                              ChangeDatas(dataTemp);
                              console.log('Data:', dataTemp);
                              
                          } else {
                              console.error('Error:', data.message,data);
                              pathButton.innerHTML = 'Select Path <span style="color: red;">(Load Fail)</span>';
                          }
                      })
                      .catch(error => {
                          console.error('Error:', error,data);
                          pathButton.innerHTML = 'Select Path <span style="color: red;">(Load Fail)</span>';
                      });
                  }
                  ChangeAnchorValue(id, labelTextarea.value, 'Input', input.Id); // 假定 id 和 ChangeNodeLabel 已定义
              }
              
              });
              //触发labelTextarea.addEventListener('input', function () {
                          
              if (input.Kind == 'Num')
                  labelTextarea.value = input.Num;
              else if (input.Kind.includes('String'))
                  labelTextarea.value = input.Context;
              if(input.Context!=null)
              {
                setTimeout(() => {
                  labelTextarea.dispatchEvent(new Event('input'));
                }, 100);     
              }
            }
            else
            {
              labelTextarea = document.createElement('Select');
              labelTextarea.style.width = '100px'; // 设置固定宽度
              labelTextarea.style.height = '20px'; // 初始高度
              labelTextarea.style.overflow = 'hidden'; // 防止滚动条出现
              labelTextarea.style.verticalAlign = 'top'; // 输入行字符居上
              labelTextarea.style.lineHeight = '20px'; // 设置行高以匹配初始高度
              labelTextarea.style.resize = 'vertical';
              let database = graph.save();
              // 假设 labelTextarea 是一个 <select> 或 <textarea> 元素
              for (let i = 0; i < database.nodes.length; i++) {
                if (database.nodes[i].id == id) {
                  // ① 原先这里是 const TempOutPuts = database.nodes[i].TempOutPuts;
                  //    改用 TempColumns
                  const TempColumns = database.nodes[i].TempColumns;

                  // ② 遍历 TempColumns 的 key 生成下拉选项
                  Object.keys(TempColumns).forEach((key) => {
                    const option = document.createElement('option');
                    option.value = key;
                    option.text = key;
                    labelTextarea.appendChild(option);
                  });
                }
              }

              labelTextarea.addEventListener('click', function () {
                let database = graph.save();

                for (let i = 0; i < database.nodes.length; i++) {
                  if (database.nodes[i].id == id) {
                    // 用于后续比对的标识
                    let isDifferent = false;

                    // ③ 这里同样由 TempOutPuts 换成 TempColumns
                    const TempColumns1 = database.nodes[i].TempColumns;

                    // 从第 1 个选项开始检查(如果第 0 个是“placeholder”或其他)
                    for (let j = 1; j < labelTextarea.options.length; j++) {
                      let currentValue = labelTextarea.options[j].value;
                      isDifferent = true; // 默认先认为不匹配

                      // 遍历 TempColumns1 的所有 key
                      for (let key of Object.keys(TempColumns1)) {
                        if (currentValue === key) {
                          isDifferent = false; // 找到相同键，说明没变
                          break;
                        }
                      }
                      // 如果真有不同，这里不一定需要立即 break，看你后面逻辑需要
                    }

                    // 如果元素数量也不一致，则视为不同
                    if (labelTextarea.options.length !== Object.keys(TempColumns1).length + 1) {
                      isDifferent = true;
                    }

                    // 如果检测到不一致，则先清空所有选项
                    if (isDifferent) {
                      while (labelTextarea.firstChild) {
                        labelTextarea.removeChild(labelTextarea.firstChild);
                      }
                    }

                    // ④ 再次填充最新的列信息
                    const TempColumns2 = database.nodes[i].TempColumns;
                    Object.keys(TempColumns2).forEach((key) => {
                      const option = document.createElement('option');
                      option.value = key;
                      option.text = key;
                      labelTextarea.appendChild(option);
                    });
                  }
                }

                // 回填到 input.Context
                labelTextarea.value = input.Context;
              });

              labelTextarea.addEventListener('change', function () {
                ChangeAnchorValue(id, labelTextarea.value, 'Input', input.Id);
              });
              if(input.Context!=null)
                labelTextarea.value = input.Context;
            }
            //
            let uniqueClass = `unique-textarea-${id}-${input.Id}`; // 使用 input.Id 生成唯一的类名
            
            if (input.Kind == 'String_FilePath') {
                // 创建路径按钮
                // 检查是否已经存在名为 "Select Path" 的按钮，避免重复创建
                let existingPathButton = inputContainer.querySelector('button'); // 假设 inputContainer 中只会有一个按钮

                // 如果不存在按钮，则创建新的
                if (!existingPathButton) {
                    let pathButton = document.createElement('button'); // 创建按钮
                    pathButton.textContent = 'Select Path'; // 设置按钮文本

                    // 文件选择逻辑
                    pathButton.addEventListener('click', function () {
                        CreatFilePath(input.Id, id);
                    });

                    // 将按钮添加到 inputContainer 中
                    inputContainer.appendChild(pathButton);
                } else {
                    console.log('按钮已经存在');
                }

            }
            
            labelTextarea.className = uniqueClass;
            labelTextarea.id = uniqueClass;
            labelTextarea.classList.add(uniqueClass); // 为文本区域添加唯一类名
            
            
    
            inputContainer.appendChild(labelTextarea);
        }
      }
    
      selectBox.addEventListener('change', function() {
        handleChange(this.value);
      });
      // 为输入框添加 blur 监听器
      inputName.addEventListener('input', function() {
          ChangeAnchorLabel(id, inputName.value, index,input.Id,true); // 假定 id 和 ChangeNodeLabel 已定义
      });
      RefreshEdge();
      inputColumn.appendChild(inputContainer);
    }
    function CreatOutputs(output, index, IdTemp) {
      const outputContainer = document.createElement('div');
      outputContainer.className = 'output-container';
      outputContainer.style.display = 'flex';
      outputContainer.style.alignItems = 'flex-start'; // Content aligned at top
      outputContainer.style.flexWrap = 'wrap'; // Allow child elements to wrap
      outputContainer.style.marginBottom = '10px'; // Increase line spacing
      outputContainer.style.maxHeight = '300px'; // Set maximum height
      outputContainer.style.overflowY = 'auto'; // Add vertical scrollbar when needed
    
      // 创建一个 input 来显示/编辑 output name
      const outputName = document.createElement('input');
      outputName.value = output.name;
      outputName.style.width = '100px';
      outputName.style.marginBottom = '5px';
      outputContainer.appendChild(outputName);
    
      // 分隔用的小空div
      const newLineDiv = document.createElement('div');
      newLineDiv.style.width = '5%';
      newLineDiv.style.height = '0';
      outputContainer.appendChild(newLineDiv);
    
      // Label1 + Select1：“组”下拉
      const Label1 = document.createElement('label');
      Label1.textContent = '组';
      Label1.style.flex = '0 0 auto';
      Label1.style.color = '#FFFFFF';
      outputContainer.appendChild(Label1);
    
      const Select1 = document.createElement('select');
      Select1.style.width = '100px';
      outputContainer.appendChild(Select1);
    
      // 获取当前节点的 TempColumns（原本是 TempOutPuts）
      const database = graph.save();
      let TempColumns;
      for (let i = 0; i < database.nodes.length; i++) {
        if (database.nodes[i].id == id) {
          // 原先这里是 TempOutPuts = database.nodes[i].TempOutPuts
          TempColumns = database.nodes[i].TempColumns;
        }
      }
    
      // 如果需要根据某个 key(如 Inputs[1].Context) 去定位 TempColumns 的“表”或“列数据”，则如下写:
      // 注意：只有在 TempColumns[Inputs[1].Context] 是数组或可遍历的结构时，这些操作才有意义
      const addedKeys = new Set();
      if (TempColumns && TempColumns[Inputs[1].Context]) {
        // 若这里确实存储的是多列/多对象，也可继续用 forEach
        if (Array.isArray(TempColumns[Inputs[1].Context])) {
          TempColumns[Inputs[1].Context].forEach(item => {
            console.log('item测试', item);
            if (Array.isArray(item)) {
              item.forEach(subItem => populateSelectBoxFromObject(addedKeys, subItem, "", Select1));
            } else {
              populateSelectBoxFromObject(addedKeys, item, "", Select1);
            }
    
            // 回填 selectBox4 (逻辑保持原样, 仅去掉 TempOutPuts)
            let data = graph.save();
            data.nodes.forEach((node) => {
              if (node.id == id) {
                node.Outputs.forEach((out, idx) => {
                  if (out.Id == IdTemp && out.selectBox4 != null) {
                    Select1.value = out.selectBox4;
                  }
                });
              }
            });
          });
        }
      }
    
      // 增加一行 "All" 选项
      const optionAll = document.createElement('option');
      optionAll.value = 'All';
      optionAll.text = 'All';
      Select1.appendChild(optionAll);
    
      // 再遍历 TempColumns 所有 key（原先是 Object.keys(TempOutPuts)）
      if (TempColumns && Array.isArray(TempColumns[Inputs[1].Context])) {
        TempColumns[Inputs[1].Context].forEach((itemObj) => {
          // 例如想展示 name 字段，可改成 itemObj.name
          const option = document.createElement('option');
          option.value = itemObj.name;
          option.text = itemObj.name;
          Select1.appendChild(option);
        });
      }
      
    
      // 如果之前保存过 selectBox1，就回填
      let TempOutput = SearchOutput(id, IdTemp);
      if (TempOutput.selectBox1 != null) {
        Select1.value = TempOutput.selectBox1;
      }
    
      // 当 Select1 改变时，清除多余元素并更新输出配置
      Select1.addEventListener('change', function() {
        let data = graph.save();
        let child = outputContainer.lastElementChild;
    
        // 移除除 Select1、outputName、newLineDiv、Label1、.column-SubNode 以外的所有子元素
        while (child) {
          const prev = child.previousElementSibling;
          if (
            child !== Select1 &&
            child !== outputName &&
            child !== newLineDiv &&
            child !== Label1 &&
            child.className !== 'column-SubNode'
          ) {
            outputContainer.removeChild(child);
          }
          child = prev;
        }
    
        // 更新节点信息
        data.nodes.forEach((node) => {
          if (node.id == id) {
            node.Outputs.forEach((out) => {
              if (out.Id == IdTemp) {
                out.selectBox1 = Select1.value;
                // out.selectBox5 = null; // 若需要可保留
                out.selectKind = null;
              }
            });
          }
        });
        ChangeDatas(data);
      });
    
      // 为了让它在初始化时也执行一次 change
      setTimeout(function() {
        Select1.dispatchEvent(new Event('change'));
      }, 1000);
      Select1.dispatchEvent(new Event('change'));
    
      // 点击 Select1 时，检测与 TempColumns.keys() 是否一致
      Select1.addEventListener('click', function() {
        let isDifferent = false;
        let data = graph.save();
        let Tempnode = data.nodes.filter(n => n.id == id);
        let CurrentCols = Tempnode[0].TempColumns; // 原先用 TempOutPuts
    
        // 数量 +1 (因为前面插了 "All")
        const optionsLength = Select1.options.length;
        const tempKeys = Object.keys(CurrentCols);
        const tempLength = tempKeys.length;
    
        // 如果数量不一致，直接标记不同
        if (optionsLength !== tempLength + 1) {
          isDifferent = true;
        } else {
          // 若数量一致, 再比较各选项值与 keys
          const optionValues = Array.from(Select1.options).map(opt => opt.value);
          optionValues.sort();
          tempKeys.sort();
    
          for (let index = 0; index < optionsLength; index++) {
            if (optionValues[index] !== (tempKeys[index] || 'All')) {
              // 这里要注意：我们有一个"All"，tempKeys没有，所以你可能还需具体判断
              isDifferent = true;
              break;
            }
          }
        }
    
        // 若有差异，则重置下拉内容
        if (isDifferent) {
          Select1.innerHTML = '';
          // 先插入 "All"
          const optAll = document.createElement('option');
          optAll.value = 'All';
          optAll.text = 'All';
          Select1.appendChild(optAll);
    
          // 如果还需把 TempColumns[Inputs[1].Context] 的内容插回
          const addedKeys = new Set();
          if (CurrentCols[Inputs[1].Context]) {
            if (Array.isArray(CurrentCols[Inputs[1].Context])) {
              CurrentCols[Inputs[1].Context].forEach(item => {
                if (Array.isArray(item)) {
                  item.forEach(subItem => populateSelectBoxFromObject(addedKeys, subItem, "", Select1));
                } else {
                  populateSelectBoxFromObject(addedKeys, item, "", Select1);
                }
    
                // 再做一次回填
                let data2 = graph.save();
                data2.nodes.forEach((node2) => {
                  if (node2.id == id) {
                    node2.Outputs.forEach((out2) => {
                      if (out2.Id == IdTemp && out2.selectBox4 != null) {
                        Select1.value = out2.selectBox4;
                      }
                    });
                  }
                });
              });
            }
          }
          // 再插入 TempColumns.key
          Object.keys(CurrentCols).forEach(k => {
            const option = document.createElement('option');
            option.value = k;
            option.text = k;
            Select1.appendChild(option);
          });
    
          // 回填之前选中的值
          let TempOutput = SearchOutput(id, IdTemp);
          if (TempOutput.selectBox1 != null) {
            Select1.value = TempOutput.selectBox1;
          }
        }
      });
    
      // 创建一个小区域 SubNode 用来删除此输出
      creatSubNode();
      function creatSubNode() {
        let IsBreak = false;
        let data = graph.save();
        data.nodes.forEach((node) => {
          if (node.id == id) {
            node.Outputs.forEach((out) => {
              if (out.Id == IdTemp && out.Isnecessary == true) {
                // 如果该输出是必要的，就不创建可删区域
                IsBreak = true;
                return;
              }
            });
          }
        });
        if (IsBreak) return;
    
        const SubNode = document.createElement('div');
        SubNode.className = 'column-SubNode';
        SubNode.style.left = '112px';
        outputContainer.appendChild(SubNode);
    
        SubNode.onmousedown = function() {
          let data = graph.save();
          data.nodes.forEach((node) => {
            if (node.id == id) {
              // 通过 IdTemp 删除此 Output
              node.Outputs.forEach((out, idx) => {
                if (out.Id == IdTemp) {
                  node.Outputs.splice(idx, 1);
                }
              });
    
              // 重新计算锚点
              const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60;
              node.anchorPoints = node.Inputs
                .map((inp, idx) => {
                  const anchorHeight = 60 + idx * 20;
                  return [0.05, anchorHeight / maxHeight];
                })
                .concat(
                  node.Outputs.map((out, idx) => {
                    const anchorHeight = 60 + idx * 20;
                    return [0.95, anchorHeight / maxHeight];
                  })
                )
                .concat([[0, 0]]);
    
              ChangeDatas(data);
              // 移除界面
              outputContainer.parentNode.removeChild(outputContainer);
            }
          });
          RefreshEdge();
        };
      }
    
      // (如果要在 container 里显示这个输出)
      outputColumn.appendChild(outputContainer);
    }
    
      Inputs.forEach((input, index) => {
        CreatInputs(input,index,input.Id);
      });
      Outputs.forEach((output, index) => {
          CreatOutputs(output,index,output.Id);
      });
    }
    if(NodeKind=='DataBase')
    {
      const inputColumn = document.createElement('div');
      inputColumn.className = 'column';
      const inputLabel = document.createElement('div');
      inputLabel.textContent = 'Input'; // 设置文本
      inputLabel.className = 'column-label'; // 设置样式类
      inputColumn.appendChild(inputLabel);
      const addNode = document.createElement('div');
      addNode.className = 'column-AddNode'; // 使用之前定义的样式类
      vessel.appendChild(inputColumn);
      // 调整textarea高度以适应内容

      // 输入框空格键增长逻辑
      let IdTemp='';
      addNode.onmousedown = function() {
          let data=graph.save();
          data.nodes.forEach((node) => {
            if(node.id == id)
            {
                IdTemp='Input' + (node.Inputs.length + 1).toString();
                let TempName = 'Input' + (node.Inputs.length + 1).toString();
                let counter = 1; // 新增一个计数器
                // 检查是否重名，如果重名则+1继续检查
                while (node.Inputs.some(input => input.name === TempName)) {
                    TempName = 'Input' + (node.Inputs.length + 1 + counter).toString(); // 使用计数器调整名称
                    counter++; // 每次循环递增计数器
                }
                node.Inputs.push({
                  'Num': null,
                  'Kind': 'String',
                  'Id': IdTemp,
                  'Context': null,
                  'Isnecessary': false,
                  'name': TempName,
                  'Link': 0,
                  'IsLabel': false,
              });
              const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
              node.anchorPoints = node.Inputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.05, anchorHeight / maxHeight]
                }).concat(node.Outputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.95, anchorHeight / maxHeight]
                })).concat([[0, 0]]);
              CreatInputs(node.Inputs[node.Inputs.length - 1],node.Inputs.length - 1,IdTemp);
              ChangeDatas(data);
            }
          });

          RefreshEdge();

        };
      //等比例扩大addNode

      // 确定插入位置并将AddNode插入到inputColumn中
      const nextElement = inputLabel.nextSibling; // 获取inputLabel之后的元素
      if (nextElement) {
          // 如果inputLabel后面有其他元素，则在这个元素之前插入addNode
          inputColumn.insertBefore(addNode, nextElement);
      } else {
          // 如果inputLabel是最后一个元素或inputColumn没有其他子元素，则直接追加
          inputColumn.appendChild(addNode);
      }
    const outputColumn = document.createElement('div');
    outputColumn.className = 'column';
    const addNode1 = document.createElement('div');
    addNode1.className = 'column-AddNode'; // 使用之前定义的样式类
    addNode1.style.left = '60px'; // 设置左边距
    outputColumn.appendChild(addNode1);
    const outputLabel = document.createElement('div');
    outputLabel.textContent = 'Output'; // 设置文本
    outputLabel.className = 'column-label'; // 设置样式类
    outputColumn.appendChild(outputLabel);
    // 将输入和输出列添加到节点容器中
    addNode1.onmousedown = function() {
      let data = graph.save();
      data.nodes.forEach((node) => {
        if (node.id == id) {
          // 构造唯一 Id 和默认 name
          const baseCount = node.Outputs.length + 1;
          let IdTemp   = 'Output' + baseCount + Date.now();
          let TempName = 'Output' + baseCount;
          // 保证 name 不重复
          let counter = 1;
          while (node.Outputs.some(o => o.name === TempName)) {
            TempName = 'Output' + (baseCount + counter);
            counter++;
          }
    
          // 推入新的 output 配置，带上三个新字段
          node.Outputs.push({
            Num: 0,
            Kind: 'String',
            Id: IdTemp,
            Context: '',
            Boolean: false,
            Isnecessary: false,
            name: TempName,
            Link: 0,
            IsLabel: false,
          });
    
          // 重新计算锚点
          const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60;
          node.anchorPoints = node.Inputs
            .map((inp, idx) => {
              const y = (60 + idx * 20) / maxHeight;
              return [0.05, y];
            })
            .concat(
              node.Outputs.map((out, idx) => {
                const y = (60 + idx * 20) / maxHeight;
                return [0.95, y];
              })
            )
            .concat([[0, 0]]);
    
          // 渲染新创建的输出 UI
          CreatOutputs(node.Outputs[node.Outputs.length - 1],
                       node.Outputs.length - 1,
                       IdTemp);
    
          ChangeDatas(data);
        }
      });
    
      RefreshEdge();
    };
    
    vessel.appendChild(outputColumn);
    // 添加元素到 DOM
    function CreatInputs(input,index,IdTemp)
    {
      const inputContainer = document.createElement('div');
      inputContainer.className = 'input-container';

      // 创建显示输入名称的输入框
      const inputName = document.createElement('input');
      inputName.value = input.name;
      inputContainer.appendChild(inputName);

      // 创建选择框
      const selectBox = document.createElement('select');
      const optionLink = document.createElement('option');
      optionLink.value = 'link';
      optionLink.text = 'Link';
      const optionLabel = document.createElement('option');
      optionLabel.value = 'Input';
      optionLabel.text = 'Input';
      selectBox.appendChild(optionLink);
      selectBox.appendChild(optionLabel);
      inputContainer.appendChild(selectBox);

      function RefreshOutput() {
        // 确保outputColumn是已定义的，并且开始清理操作
        if (outputColumn) {
            // 获取所有子元素
            let children = outputColumn.children;
            // 从后往前遍历子元素，以便安全删除元素
            for (let i = children.length - 1; i >= 0; i--) {
                // 假设我们用className来识别是否是addNode1
                if (children[i].className !== 'column-AddNode' && children[i].className !== 'column-label'&& child.className!=='column-SubNode') {
                    outputColumn.removeChild(children[i]); // 删除不是addNode1的元素
                }
            }
        }

        // 这里添加Outputs中的addNode1元素，或其他处理逻辑
        Outputs.forEach((output, index) => {
            // 检查是否是我们需要添加的特定节点addNode1
              CreatOutputs(output, index, output.Id);
        });
    }


    // 假设Outputs是全局变量，如果不是，需要确保它在这个函数中是可访问的
      if(input.Isnecessary==false)
      {
        const SubNode = document.createElement('div');
        SubNode.className = 'column-SubNode'; // 使用之前定义的样式类
        SubNode.style.left = '250px'; // 设置与标签之间的间距
        inputContainer.appendChild(SubNode);
        SubNode.onmousedown = function() {//删除这个矛点
          let data=graph.save();
          data.nodes.forEach((node) => {
            if(node.id == id)
            {
              //通过IdTemp删除这个矛点
              node.Inputs.forEach((input,index) => {
                  if(input.Id == IdTemp)
                  {
                    node.Inputs.splice(index,1);
                    RefreshOutput();
                  }
                }
              );
              const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
              node.anchorPoints = node.Inputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.05, anchorHeight / maxHeight]
                }).concat(node.Outputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.95, anchorHeight / maxHeight]
                })).concat([[0, 0]]);
              ChangeDatas(data);
              //移除inputContainer
              inputContainer.parentNode.removeChild(inputContainer);
            }
          });
          RefreshEdge();
        }
      }
      let labelTextarea = document.createElement('textarea'); // 在外部声明变量以便在不同的作用域中访问
      labelTextarea.className = 'input-textarea';
      if(input.IsLabel==true)
      {
        selectBox.value = 'Input';
        handleChange('Input');
      }
      // 处理选择框变化
      
      function handleChange(value) {
        let pathButton = null; // 在函数内部初始化为 null
        // 如果之前添加了文本区域且现在选择是“Link”，则移除文本区域
        let data = graph.save();
        data.edges.forEach(edge => {
            if (edge.target == id && edge.targetAnchor == index) {
                const item = graph.findById(edge.id);
                const targetNode = graph.findById(edge.target);
                const targetAnchor = targetNode.getContainer().find(ele => ele.get('anchorPointIdx') === anchorIndex);
                targetAnchor.set('links', targetAnchor.get('links') + 1);
                ChangeLink(targetAnchor);
                graph.remove(item);
            }
        });
    
        if (labelTextarea && value === 'link') {
            inputContainer.removeChild(labelTextarea);
            labelTextarea = null; // 确保引用被清除
            ChangeAnchorValue(id, '', 'link', input.Id);
            
            if (pathButton && inputContainer.contains(pathButton)) {
                inputContainer.removeChild(pathButton);
                pathButton = null; // 确保 pathButton 被正确清除
            }
        } else if (value === 'Input') {
            // 如果当前选择是“Input”，则添加文本区域
            labelTextarea = document.createElement('textarea');
            labelTextarea.className = 'input-textarea';
            if (input.Kind == 'Num')
                labelTextarea.value = input.Num;
            else if (input.Kind.includes('String'))
                labelTextarea.value = input.Context;
            //
            let uniqueClass = `unique-textarea-${id}-${input.Id}`; // 使用 input.Id 生成唯一的类名
            
            if (input.Kind == 'String_FilePath') {
                // 创建路径按钮
                // 检查是否已经存在名为 "Select Path" 的按钮，避免重复创建
                let existingPathButton = inputContainer.querySelector('button'); // 假设 inputContainer 中只会有一个按钮

                // 如果不存在按钮，则创建新的
                if (!existingPathButton) {
                    let pathButton = document.createElement('button'); // 创建按钮
                    pathButton.textContent = 'Select Path'; // 设置按钮文本

                    // 文件选择逻辑
                    pathButton.addEventListener('click', function () {
                        CreatFilePath(input.Id, id);
                    });

                    // 将按钮添加到 inputContainer 中
                    inputContainer.appendChild(pathButton);
                } else {
                    console.log('按钮已经存在');
                }

            }
            
            labelTextarea.className = uniqueClass;
            labelTextarea.id = uniqueClass;
            labelTextarea.classList.add(uniqueClass); // 为文本区域添加唯一类名
    
            labelTextarea.addEventListener('input', function () {
                let isOk = true; // 假定输入有效
                if (input.Kind == 'Num') {
                    if (labelTextarea.value.match(/^[0-9]+$/)) {
                        isOk = true; // 如果是数字，将 isOk 设置为 true
                    } else {
                        // 如果不符合条件，则弹出提示
                        isOk = false;
                        alert("类型不符，您应该输入数字！");
                    }
                }
                if (labelTextarea.value.trim() === '') {
                    isOk = false; // 如果输入为空，则将 isOk 设置为 false
                    alert("输入不能为空！");
                }
    
                if (isOk) {
                  if (index == 0) {
                      let pathButton = inputContainer.querySelector('button'); 
                      pathButton.innerHTML = 'Select Path <span class="circle-loader"></span>';
                      let filePath = labelTextarea.value;
              
                      fetch('/read_DataBase', {
                          method: 'POST',
                          headers: {
                              'Content-Type': 'application/json'
                          },
                          body: JSON.stringify({ 'file_path': filePath })
                      })
                      .then(response => response.json())
                      .then(data => {
                          if (data.status === 'success') {
                              pathButton.innerHTML = 'Select Path <span style="color: green;">(Load Success)</span>';
                              let dataTemp=graph.save();
                              dataTemp.nodes.forEach((node) => {
                                if(node.id == id)
                                {
                                  node.TempColumns= data.columns;
                                }
                              });
                              ChangeDatas(dataTemp);         
                          } else {
                              console.error('Error:', data.message,data);
                              pathButton.innerHTML = 'Select Path <span style="color: red;">(Load Fail)</span>';
                          }
                      })
                      .catch(error => {
                          console.error('Error:', error,data);
                          pathButton.innerHTML = 'Select Path <span style="color: red;">(Load Fail)</span>';
                      });
                  }
                  ChangeAnchorValue(id, labelTextarea.value, 'Input', input.Id); // 假定 id 和 ChangeNodeLabel 已定义
              }
              
            });
            //触发labelTextarea.addEventListener('input', function () {
            if(input.Context!=null)
            labelTextarea.dispatchEvent(new Event('input'));
            labelTextarea.addEventListener('input', function () {
                // 重置高度以计算新的高度
                this.style.height = 'auto';
                // 设置新的高度
                this.style.height = `${this.scrollHeight}px`;
            });
    
            inputContainer.appendChild(labelTextarea);
        }
      }
    
      selectBox.addEventListener('change', function() {
        handleChange(this.value);
      });
      // 为输入框添加 blur 监听器
      inputName.addEventListener('input', function() {
          ChangeAnchorLabel(id, inputName.value, index,input.Id,true); // 假定 id 和 ChangeNodeLabel 已定义
      });
      RefreshEdge();
      inputColumn.appendChild(inputContainer);
    }
    function CreatOutputs(output, index,IdTemp) {
      function CreatLable(inputEl, SelectLabel){
        /* ===== 基本数据抓取 ===== */
        const Tempoutput = SearchOutput(id, IdTemp);
        const data       = graph.save();
        let   TempColumns = {};
        data.nodes.forEach(n=>{ if(n.id===id) TempColumns = n.TempColumns; });
      
        /* ===== 下拉 DOM（每个输入独立创建，失焦后销毁） ===== */
        const dropdown  = document.createElement('ul');
        dropdown.className = 'quick-dropdown';
        document.body.appendChild(dropdown);
      
        let itemsList    = [];
        let currentIndex = -1;
      
        /* ========== 核心工具函数 ========== */
        function buildCandidates(keyword){
          const S = new Set();
      
          /* ① 变量占位符 {{InputName}} */
          for(let i=1;i<Inputs.length;i++) S.add(`{{${Inputs[i].name}}}`);
      
          /* ② 取列值做补全（若非 Json输入/修改） */
          if(!Tempoutput.selectBox5 || (!Tempoutput.selectBox5.includes('Json输入') && !Tempoutput.selectBox5.includes('修改'))){
            const colData = TempColumns?.[Tempoutput.selectBox1];
            if(colData){
              (Array.isArray(colData)?colData:[colData])
                .flat(Infinity)
                .forEach(v=>{
                  const txt = (v??'').toString();
                  if(txt.toLowerCase().includes(keyword)) S.add(txt);
                });
            }
          }
          return Array.from(S);
        }
      
        function render(){
          dropdown.innerHTML = '';
          if(!itemsList.length){ dropdown.style.display='none'; return; }
      
          itemsList.forEach((txt,idx)=>{
            const li=document.createElement('li');
            li.textContent=txt;
            if(idx===currentIndex) li.classList.add('active');
      
            li.onmouseenter = ()=>{ currentIndex=idx; highlight(); };
            li.onmousedown  = e=>{ e.preventDefault(); confirm(); }; // mousedown防止 blur
      
            dropdown.appendChild(li);
          });
      
          /* —— 自动宽度范围 —— */
          const width = Math.min(Math.max(inputEl.offsetWidth,140),300);
          dropdown.style.width = width+'px';
      
          /* —— 定位（防止溢出） —— */
          const rect = inputEl.getBoundingClientRect();
          const vw   = document.documentElement.clientWidth;
          const vh   = document.documentElement.clientHeight;
      
          let left = rect.left;
          if(left + width > vw - 8) left = vw - width - 8;
      
          let top  = rect.bottom + 2;
          if(top + dropdown.offsetHeight > vh - 8)
            top = rect.top - dropdown.offsetHeight - 2;
      
          dropdown.style.left = left + 'px';
          dropdown.style.top  = top  + 'px';
          dropdown.style.display='block';
        }
      
        const highlight = ()=>Array.from(dropdown.children)
            .forEach((li,i)=>li.classList.toggle('active',i===currentIndex));
      
            function confirm(){
              if (currentIndex < 0 || currentIndex >= itemsList.length) return;
            
              // 设置输入框内容
              inputEl.value = itemsList[currentIndex];
            
              // ★★★ 手动派发 input 事件，触发你外层的监听器
              inputEl.dispatchEvent(new Event('input', { bubbles: true }));
            
              // 原有逻辑
              ChangeAnchorLabel(id, inputEl.value, SelectLabel, IdTemp, false);
              hide();
            }
      
        const hide = ()=>{ dropdown.style.display='none'; currentIndex=-1; };
      
        /* ========== 事件绑定 ========== */
        inputEl.addEventListener('input', ()=>{
          console.log('inputEl.value',inputEl.value);
          itemsList    = buildCandidates(inputEl.value.toLowerCase());
          currentIndex = 0;
          render();
        });
      
        inputEl.addEventListener('focus', ()=>{
          console.log('focus');
          itemsList    = buildCandidates('');
          currentIndex = 0;
          render();
        });
      
        inputEl.addEventListener('keydown', e=>{
          console.log('keydown',e.key);
          if(dropdown.style.display!=='block') return;
      
          if(e.key==='ArrowDown'){
            currentIndex = (currentIndex+1)%itemsList.length; highlight(); e.preventDefault();
          }else if(e.key==='ArrowUp'){
            currentIndex = (currentIndex-1+itemsList.length)%itemsList.length; highlight(); e.preventDefault();
          }else if(e.key==='Enter' || e.key===' '){
            confirm(); e.preventDefault();
          }else if(e.key==='Escape'){
            hide();
          }
        });
      
        /* 点击输入框外部关闭 */
        document.addEventListener('mousedown', onDocClick);
        function onDocClick(evt){
          if(evt.target!==inputEl && !dropdown.contains(evt.target)) hide();
        }
      
        /* 失焦稍延时关闭（给点击选项留时间） */
        inputEl.addEventListener('blur', ()=>setTimeout(hide,150));
      
        /* 组件销毁时清理监听（防止内存泄漏） */
        inputEl.__destroyQuick = ()=>{ document.removeEventListener('mousedown', onDocClick); dropdown.remove(); };
      }
      

      const outputContainer = document.createElement('div');
      outputContainer.className = 'output-container';
      outputContainer.style.display = 'flex';
      outputContainer.style.alignItems = 'flex-start'; // Content aligned at top
      outputContainer.style.flexWrap = 'wrap'; // Allow child elements to wrap
      outputContainer.style.marginBottom = '10px'; // Increase line spacing
      outputContainer.style.maxHeight = '300px'; // Set maximum height
      outputContainer.style.overflowY = 'auto'; // Add vertical scrollbar when needed
      // Create an input box to display the output name
      const outputName = document.createElement('input');
      outputName.value = output.name;
      outputName.style.width = '100px'; // 设置固定宽度
      outputName.style.marginBottom = '5px'; // 增加10px的下边距，增加行距
      outputContainer.appendChild(outputName);
      outputName.addEventListener('input', function() {
        ChangeAnchorLabel(id, outputName.value, index, IdTemp, false);
      })
      // 添加一个宽度为100%的透明div来强制换行
      const newLineDiv1 = document.createElement('div');
      newLineDiv1.style.width = '3%'; // 设置宽度为100%
      newLineDiv1.style.height = '0'; // 高度设置为0，使其不影响视觉效果
      outputContainer.appendChild(newLineDiv1);

      
      if (index != 0) {
        const Label5 = document.createElement('label');
        Label5.textContent = '类型';
        Label5.style.flex = '0 0 auto';
        Label5.style.color = '#FFFFFF';
        outputContainer.appendChild(Label5);
      
        const Select5 = document.createElement('select');
        Select5.style.width = '100px';
        outputContainer.appendChild(Select5);
      
        // 类型下拉选项
        const options = ['Json输入', '修改', '删除', '查询', '新增'];
        options.forEach(option => {
          const optionElement = document.createElement('option');
          optionElement.value = option;
          optionElement.textContent = option;
          Select5.appendChild(optionElement);
        });
      
        const newLineDiv = document.createElement('div');
        newLineDiv.style.width = '25%'; 
        newLineDiv.style.height = '0'; 
        
      
        // 组(Label + Select1)
        const Label1 = document.createElement('label');
        Label1.textContent = '组';
        Label1.style.flex = '0 0 auto';
        Label1.style.color = '#FFFFFF';
        outputContainer.appendChild(Label1);
      
        const Select1 = document.createElement('select');
        Select1.style.width = '100px';
        outputContainer.appendChild(Select1);
        outputContainer.appendChild(newLineDiv);
        const logicContainer = document.createElement('div');
        logicContainer.className = 'logic-container';
        outputContainer.appendChild(logicContainer);   // ⬅ 逻辑区放在 outputContainer 里
        // ① 不再获取 node.TempOutPuts，而是直接拿 TempColumns
        let nodes = graph.save().nodes;
        let Tempnode = nodes.find(n => n.id == id);
        let TempColumns = Tempnode ? Tempnode.TempColumns : {};
        // ② 用 TempColumns 的键来生成选项
        if (TempColumns) {
          Object.keys(TempColumns).forEach(key => {
            const option = document.createElement('option');
            option.value = key;
            option.text = key;
            Select1.appendChild(option);
          });
        }
      
        // ③ 根据已存的输出配置，设置默认选中的表(组)
        let TempOutput = SearchOutput(id, IdTemp);
        if (TempOutput.selectBox1 != null) {
          Select1.value = TempOutput.selectBox1;
        } else {
          // 若无默认值，就选第一个
          const columnKeys = Object.keys(TempColumns);
          if (columnKeys.length > 0) {
            Select1.value = columnKeys[0];
          }
        }
        CreatCondition(Select1.value);
      
        // 监听“组”选择变动
        Select1.addEventListener('change', function () {
          let data = graph.save();

          data.nodes.forEach((node) => {
            if (node.id == id) {
              node.Outputs.forEach((output, index) => {
                if (output.Id == IdTemp && this.value!='' && this.value!=' ') {
                  output.selectBox1 = this.value;
                  // output.selectBox5 = null; // 如需清空，可保留
                  output.selectKind = null;
                  CreatCondition(this.value);
                }
              });
            }
          });
          ChangeDatas(data);
        });
      
        // 为了确保初始就能更新UI，这里触发一次 change 事件
        setTimeout(function () {
          Select1.dispatchEvent(new Event('change'));
        }, 1000);
        Select1.dispatchEvent(new Event('change'));
      
        // 监听“组”下拉被点击时，检测是否与 TempColumns 的键有差异
        Select1.addEventListener('click', function () {
          if(!TempColumns) return;
          let isDifferent = false;
          const optionValues = Array.from(Select1.options).map(opt => opt.value);
          const columnKeys = Object.keys(TempColumns);
      
          // 如果长度不一致，肯定不同
          if (optionValues.length !== columnKeys.length) {
            isDifferent = true;
          } else {
            // 如果数量一致，则比较排序后是否相同
            optionValues.sort();
            columnKeys.sort();
            for (let i = 0; i < optionValues.length; i++) {
              if (optionValues[i] !== columnKeys[i]) {
                isDifferent = true;
                break;
              }
            }
          }
      
          // 如果不同，则重置下拉选项
          if (isDifferent) {
            Select1.innerHTML = '';
            Object.keys(TempColumns).forEach(key => {
              const option = document.createElement('option');
              option.value = key;
              option.text = key;
              Select1.appendChild(option);
            });
          }
        });
      
        // 包含条件选择的逻辑
        /**
       * 仅保证元素唯一的小工具
       */
        function ensure(parent, tag, id, createFn) {
          // 只在 parent 里找，避免 “不在 document 里就找不到” 的问题
          let el = parent.querySelector(`#${CSS.escape(id)}`);
          if (!el) {
            el      = document.createElement(tag);
            el.id   = id;
            createFn?.(el);
            parent.appendChild(el);
          }
          return el;
        }
        

      function InitSelectBox2(value) {
        // -------- 统一的辅助：把需要的前缀都放这里 ----------
        const prefixes = [
          'SelectedLabel_', 'Select4_', 'ModifyLabel_',
          'Input6_', 'newlineDiv3_', 'newlineDiv4_'
        ];
        const outputTemp   = SearchOutput(id, IdTemp);
        const outputKey    = output.name;  
        // ---------- 清理旧节点 ----------
        prefixes.forEach(p => {
          const node = document.getElementById(p + outputKey);
          node?.parentNode?.removeChild(node);
        });

                            // 方便拼 id
        /* ① 只有在查询/修改/新增时才进入 */
        if (!['查询', '修改', '新增'].includes(outputTemp.selectBox5)) return;

        /* ② --------- 只关心一次性创建的元素 --------- */
        const newline3 = ensure(
          outputContainer,
          'div',
          `newlineDiv3_${outputKey}`,
          el => { el.style.width = '5%'; el.style.height = '0'; }
        );

        /* Label4：查询类别 */
        ensure(
          outputContainer,
          'label',
          `SelectedLabel_${outputKey}`,                // id 统一加下划线
          el => {
            el.textContent = output.selectBox5+'类别';
            el.style.flex  = '0 0 auto';
            el.style.color = '#FFFFFF';
          }
        );
        /* Select4：查询列 */
        const Select4 = ensure(outputContainer, 'select', `Select4_${outputKey}`,
          el => el.style.width = '100px');
      
        console.log('[DEBUG] Select4 id =', Select4.id,
                    outputContainer.querySelectorAll('[id^="Select4_"]').length);                    // 不管是新建还是复用，都回填一次

        /* ③ --------- 修改 / 新增 时要额外的输入框 --------- */
        if (['修改', '新增'].includes(outputTemp.selectBox5)) {
          ensure(
            outputContainer,
            'div',
            `newlineDiv4_${outputKey}`,
            el => { el.style.width = '5%'; el.style.height = '0'; }
          );

          ensure(outputContainer, 'label', `ModifyLabel_${outputKey}`, el => {
            el.textContent = '修改内容';
            el.style.flex  = '0 0 auto';
            el.style.color = '#FFF';
          });

          const Input6 = ensure(
            outputContainer,
            'input',
            `Input6_${outputKey}`,
            el => {
              el.type        = 'text';
              el.style.width = '100px';
              CreatLable(el, 'selectBox6');
            }
          );
          Input6.value = outputTemp.selectBox6 || '';
        }

        /* ④ --------- 重新填充下拉框选项（与旧逻辑一致） --------- */
        const OutputTemp = SearchOutput(id, IdTemp);
        const Table      = OutputTemp.selectBox1;

        // 清空并重建选项
        Select4.innerHTML = '';
        Select4.appendChild(new Option('All', 'All'));

        const nodes       = graph.save().nodes;
        const Tempnode    = nodes.find(n => n.id == id);
        const TempColumns = Tempnode?.TempColumns ?? {};

        if (TempColumns[Table] !== undefined) {
          const added = new Set();
          const pushCols = obj => populateSelectBoxFromObject(added, obj, '', Select4);

          Array.isArray(TempColumns[Table])
            ? TempColumns[Table].flat().forEach(pushCols)
            : pushCols(TempColumns[Table]);
        }

        /* ⑤ --------- 事件：change / click --------- */
        Select4.onchange = () => {
          const data = graph.save();
          data.nodes.forEach(node => {
            if (node.id === id) {
              node.Outputs.forEach(out => {
                if (out.Id === IdTemp) {
                  out.selectKind = 'Str';
                  out.selectBox4 = Select4.value;
                  out.selectNum3 = Select4.value;
                }
              });
            }
          });
          ChangeDatas(data);
        };
        Select4.value = output.selectBox4 || 'All';
        Select4.onclick = () => {
          /* 触发一次刷新即可，逻辑同上，为简洁略 */
        };

        /* ⑥ --------- 更新 selectBox2 等状态 --------- */
        const data = graph.save();
        data.nodes.forEach(node => {
          if (node.id === id) {
            node.Outputs.forEach(out => {
              if (out.Id === IdTemp) {
                out.selectKind = 'Num';
                out.selectBox2 = value;
                out.selectNum2 = value;
              }
            });
          }
        });
        ChangeDatas(data);
      }

      
        // 如果已经存在 selectBox5（即类型），就选中它；否则默认成“查询”
        if (output.selectBox5 != 'null' && output.selectBox5 != '') {
          // 如果是已有值，就选中
          Select5.value = output.selectBox5;
          Select5Function(Select5.value);
        } else {
          // 否则默认给它赋“查询”
          Select5.value = '查询';
          let data = graph.save();
          data.nodes.forEach(node => {
            if (node.id == id) {
              node.Outputs.forEach((output, index) => {
                if (output.Id == IdTemp) {
                  output.selectBox4 = Select5.value;
                }
              });
            }
          });
          Select5Function(Select5.value);
        }
      
        // 这个函数用来根据“类型”去刷新界面
        Select5.addEventListener('change', function () {
          Select5Function(this.value);
        });
      
        function Select5Function(value) {
          let data = graph.save();
          // 清除 outputContainer 中除部分保留元素以外的所有子元素
          let child = outputContainer.lastElementChild;
          while (child) {
            const prev = child.previousElementSibling;
            if (
              child !== outputName &&
              child !== newLineDiv1 &&
              child !== Label5 &&
              child !== Select5 &&
              child.className !== 'column-SubNode' &&
              child !== Select1 &&
              child !== Label1 &&
              child !== newLineDiv
            ) {
              outputContainer.removeChild(child);
            }
            child = prev;
          }
      
          // 在这里更新节点的 selectBox5
          data.nodes.forEach((node) => {
            if (node.id == id) {
              node.Outputs.forEach((output, index) => {
                if (output.Id == IdTemp) {
                  output.selectBox5 = value;
                  CreatCondition(output.selectBox1);
                }
              });
            }
          });
          ChangeDatas(data);
        }
      
        // 根据之前的逻辑，这里还会调用 creatSubNode
        creatSubNode();
        function creatSubNode() {
          let IsBreak = false;
          let data = graph.save();
          data.nodes.forEach((node) => {
            if (node.id == id) {
              node.Outputs.forEach((output, index) => {
                if (output.Id == IdTemp && output.Isnecessary == true) {
                  // 跳过创建
                  IsBreak = true;
                  return;
                }
              });
            }
          });
          if (IsBreak) return;
      
          // 创建一个小的可点击区域来删除此输出
          const SubNode = document.createElement('div');
          SubNode.className = 'column-SubNode';
          SubNode.style.left = '390px';
          SubNode.style.top = '11px';
          outputContainer.appendChild(SubNode);
      
          SubNode.onmousedown = function () {
            let data = graph.save();
            data.nodes.forEach((node) => {
              if (node.id == id) {
                node.Outputs.forEach((output, index) => {
                  if (output.Id == IdTemp) {
                    node.Outputs.splice(index, 1);
                  }
                });
                const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60;
                node.anchorPoints = node.Inputs
                  .map((inp, idx) => {
                    const anchorHeight = 60 + idx * 20;
                    return [0.05, anchorHeight / maxHeight];
                  })
                  .concat(
                    node.Outputs.map((out, idx) => {
                      const anchorHeight = 60 + idx * 20;
                      return [0.95, anchorHeight / maxHeight];
                    })
                  )
                  .concat([[0, 0]]);
                ChangeDatas(data);
                // 移除界面
                outputContainer.parentNode.removeChild(outputContainer);
              }
            });
            RefreshEdge();
          };
        }
        

        function CreatCondition(Table) {
          const Tempdata1 = graph.save();
          let TempColumns;
          // 原先这里会拿到 TempOutPuts，这里删除或注释
          // let TempOutPuts;

          let Tempoutput = SearchOutput(id, IdTemp);

          Tempdata1.nodes.forEach((node) => {
            if (node.id == id) {
              // 只保留对列信息的获取
              TempColumns = node.TempColumns;
            }
          });
          const Select3 = document.createElement('input');

          // 判断是否是 JSON 输入
          if (Tempoutput.selectBox5 == null || (!Tempoutput.selectBox5.includes('Json输入') &&!Tempoutput.selectBox5.includes('新增'))) {
            // 如果不是 Json输入，则显示一个下拉框和一个输入框
            initLogicContainer(outputContainer, Table, TempColumns, Tempoutput);
          } else if (Tempoutput.selectBox5.includes('Json输入')) {
            // 如果是 Json输入，则只留一个内容输入框
            const Label3 = document.createElement('label');
            Label3.textContent = '内容';
            Label3.style.flex = '0 0 auto';
            Label3.style.color = '#FFFFFF';

            Select3.style.width = '100px';
            Select3.value = Tempoutput.selectBox3;
            outputContainer.appendChild(Label3);
            outputContainer.appendChild(Select3);
          }
          else if (Tempoutput.selectBox5.includes('新增')) {
            InitSelectBox2(output.selectBox2);
          }
          function initLogicContainer(outputContainer, table, tempColumns, tempoutput){
            /* 初始化数据字段 */
            if (outputContainer.querySelector('.logic-container')) return;

            tempoutput.DataBaseSubjectArray = tempoutput.DataBaseSubjectArray || [];
            tempoutput.DataBaseContentArray = tempoutput.DataBaseContentArray || [];
            tempoutput.DataBaseLogicKind   = tempoutput.DataBaseLogicKind   || 'And';
            tempoutput.DataBaseIsExactArray = tempoutput.DataBaseIsExactArray || [];
          
            /* ---- DOM ---- */
            const logicContainer = document.createElement('div');
            logicContainer.className = 'logic-container';
          
            /* 左侧全局 And/Or */
            const toggleBtn = document.createElement('div');
            toggleBtn.className = 'logic-toggle';
            toggleBtn.textContent = tempoutput.DataBaseLogicKind;
            toggleBtn.onclick = () => {
              tempoutput.DataBaseLogicKind = tempoutput.DataBaseLogicKind === 'And' ? 'Or' : 'And';
              toggleBtn.textContent = tempoutput.DataBaseLogicKind;
            };
            logicContainer.appendChild(toggleBtn);
          
            /* 右侧主体 */
            const body = document.createElement('div');
            body.className = 'logic-body';
            logicContainer.appendChild(body);
          
            /* 底部新增按钮 */
            const createBtn = document.createElement('button');
            createBtn.className = 'create-logic-row';
            createBtn.textContent = '新增匹配条件';
            createBtn.onclick = () => 
            {
              tempoutput.DataBaseSubjectArray.push('');
              tempoutput.DataBaseContentArray.push('');
              addLogicRow(body, table, tempColumns, tempoutput,tempoutput.DataBaseSubjectArray.length-1);
            }
            body.appendChild(createBtn);
          
            /* 插入到 outputContainer */
            outputContainer.appendChild(logicContainer);
          
            /* 先加一行默认行 */
            for (let i = 0; i < tempoutput.DataBaseSubjectArray.length; i++) {
              addLogicRow(body, table, tempColumns, tempoutput,i);
            }
          }
          
          /* ======= 新增一行 ======= */
          function addLogicRow(body, table, tempColumns, tempoutput,rowIndex){
          
            const row = document.createElement('div');
            row.className = 'logic-row';
          
            /* 匹配类 */
            const subject = document.createElement('select');
            populateSubject(subject, table, tempColumns);
            subject.onchange = () => (tempoutput.DataBaseSubjectArray[rowIndex] = subject.value);
            row.appendChild(subject);
            subject.addEventListener('change', function() {
              InitSelectBox2(subject.value);
            });

            if (tempoutput.DataBaseSubjectArray[rowIndex]!= null) {
              subject.value = tempoutput.DataBaseSubjectArray[rowIndex];
              InitSelectBox2(tempoutput.DataBaseSubjectArray[rowIndex]);
            } else {
              subject.value = 0;
              InitSelectBox2(tempoutput.DataBaseSubjectArray[rowIndex]);
            }
            /* 是否精确 */
            const isExact = document.createElement('select');
            isExact.innerHTML = `
              <option value="true">精确</option>
              <option value="false">模糊</option>
            `;
            if(tempoutput.DataBaseIsExactArray[rowIndex]!= null){
              isExact.value = tempoutput.DataBaseIsExactArray[rowIndex];
            }
            else{
              isExact.value = 'true';
            }
            isExact.onchange = () => (tempoutput.DataBaseIsExactArray[rowIndex] = isExact.value === 'true');
            row.appendChild(isExact);
            /* 匹配内容 */
            const content = document.createElement('input');
            content.type = 'text';
            content.placeholder = '匹配内容';
            if(tempoutput.DataBaseContentArray[rowIndex]!= null){
              content.value = tempoutput.DataBaseContentArray[rowIndex];
            }
            CreatLable(content, "selectBox3");
            content.addEventListener('input', () => {
              tempoutput.DataBaseContentArray[rowIndex] = content.value;
              // 如果还需要做其它「值变了就重算／重渲染」的逻辑，也可以写在这里
            });
            row.appendChild(content);
          
            /* 删除按钮 */
            const remove = document.createElement('button');
            remove.className = 'remove-row';
            remove.textContent = '✖';
            remove.onclick = () => {
              // ① 找到当前 row 在所有 logic-row 里的实时下标
              const rows = Array.from(body.querySelectorAll('.logic-row'));
              const idx  = rows.indexOf(row);
            
              // ② 删除 DOM
              body.removeChild(row);
              content.__destroyQuick && content.__destroyQuick();
            
              // ③ 用 idx 而不是闭包里的 rowIndex 来 splice
              if (idx > -1) {
                tempoutput.DataBaseSubjectArray.splice(idx, 1);
                tempoutput.DataBaseContentArray.splice(idx, 1);
              }
            };
            
            row.appendChild(remove);
          
            /* 插在“新增”按钮之前，保持按钮永远在底部 */
            body.insertBefore(row, body.querySelector('.create-logic-row'));
          }
          
          /* 仅根据 TempColumns 生成 subjectSelect 的选项 */
          function populateSubject(select, table, tempColumns){
            const added = new Set();
            // 默认 All
            const allOpt = document.createElement('option');
            allOpt.value = 'All';
            allOpt.text = 'All';
            select.appendChild(allOpt);

            if (tempColumns && tempColumns[table] !== undefined){
              (Array.isArray(tempColumns[table]) ? tempColumns[table] : [tempColumns[table]])
                .flat(Infinity).forEach(col=>{
                  if(!added.has(col)){
                    added.add(col);
                    const opt = document.createElement('option');
                    opt.value = col;
                    opt.text = col;
                    select.appendChild(opt);
                  }
                });
            }
          }
          //#region 快捷输入栏
          const dropdown = document.createElement('ul');
          dropdown.style.position = 'absolute';
          dropdown.style.display = 'none';
          dropdown.style.listStyle = 'none';
          dropdown.style.margin = '0';
          dropdown.style.padding = '0';
          dropdown.style.border = '1px solid #ccc';
          dropdown.style.backgroundColor = '#fff';
          document.body.appendChild(dropdown);

          let currentIndex = -1; // 当前选中的下拉项
          let itemsList = [];

          function renderDropdown(items) {
            dropdown.innerHTML = '';
            let maxWidth = 0;
            items.forEach((item, index) => {
              const li = document.createElement('li');
              li.textContent = item;
              li.style.padding = '8px';
              li.style.cursor = 'pointer';

              document.body.appendChild(li);
              const itemWidth = li.offsetWidth;
              document.body.removeChild(li);

              if (itemWidth > maxWidth) {
                maxWidth = itemWidth;
              }

              li.addEventListener('mouseenter', function() {
                currentIndex = index;
                highlightItem();
              });
              li.addEventListener('click', function() {
                confirmSelection();
              });
              dropdown.appendChild(li);
            });
            dropdown.style.width = `${maxWidth + 16}px`;
            dropdown.style.display = items.length > 0 ? 'block' : 'none';
          }

          function highlightItem() {
            Array.from(dropdown.children).forEach((li, index) => {
              li.style.backgroundColor = index === currentIndex ? '#ddd' : '#fff';
            });
          }

          function confirmSelection() {
            if (currentIndex >= 0 && currentIndex < itemsList.length) {
              Select3.value = itemsList[currentIndex];
              dropdown.style.display = 'none';
              ChangeAnchorLabel(id, Select3.value, "selectBox3", output.Id, false);
            }
          }

          // 示例：仅基于 inputValue，生成候选项（这里保留之前逻辑，如果只需要列名也可改成列名过滤）
          function generateItems(inputValue) {
            const uniqueItems = new Set();
            // 遍历Inputs从1开始的所有数组
            for (let i = 1; i < Inputs.length; i++) {
              const inputName = `{{${Inputs[i].name}}}`;
              uniqueItems.add(inputName);
            }

            // 如果不是 Json输入，这段本来依赖 TempOutPuts 进行数据过滤
            // 现在无需所有数据，可直接注释或删除
            // if (Tempoutput.selectBox5.includes('Json输入') == false) {
            //   if (TempOutPuts[Table] != undefined) {
            //     TempOutPuts[Table].forEach(item => {
            //       if (output.selectBox2 !== 'All') {
            //         const outputValue = item[output.selectBox2] ? item[output.selectBox2].toString() : '';
            //         if (outputValue.toLowerCase().includes(inputValue)) {
            //           uniqueItems.add(outputValue);
            //         }
            //       } else if (Array.isArray(item)) {
            //         item.forEach(subItem => {
            //           const subItemValue = subItem ? subItem.toString() : '';
            //           if (subItemValue.toLowerCase().includes(inputValue)) {
            //             uniqueItems.add(subItemValue);
            //           }
            //         });
            //       }
            //     });
            //   }
            // }

            return Array.from(uniqueItems);
          }

          Select3.addEventListener('input', function() {
            const inputValue = Select3.value.toLowerCase();
            itemsList = generateItems(inputValue);
            renderDropdown(itemsList);
          });

          Select3.addEventListener('keydown', function(e) {
            if (dropdown.style.display === 'block') {
              if (e.key === 'ArrowDown') {
                currentIndex = (currentIndex + 1) % itemsList.length;
                highlightItem();
                e.preventDefault();
              } else if (e.key === 'ArrowUp') {
                currentIndex = (currentIndex - 1 + itemsList.length) % itemsList.length;
                highlightItem();
                e.preventDefault();
              } else if (e.key === 'Enter' || e.key === ' ') {
                confirmSelection();
                e.preventDefault();
              }
            }
          });

          Select3.addEventListener('blur', function() {
            setTimeout(() => {
              dropdown.style.display = 'none';
            }, 200);
          });

          Select3.addEventListener('focus', function() {
            const rect = Select3.getBoundingClientRect();
            dropdown.style.left = `${rect.left}px`;
            dropdown.style.top = `${rect.bottom}px`;
            dropdown.style.width = `${rect.width}px`;

            if (Select3.value.trim() === '') {
              itemsList = generateItems('');
              renderDropdown(itemsList);
            }
          });
          //#endregion
        }

        Select5.addEventListener('change', function() {
          Select5Function(this.value);
        });
        function Select5Function(value)
        {      
          let data = graph.save();
          //清除outputContainer除Select1与Label1以外的所有的子元素
          let child = outputContainer.lastElementChild;
          while (child) {
              // 在进入下一个循环前保存上一个元素
              const prev = child.previousElementSibling;
              // 检查当前元素是否不是 Select1 和 Label1
              if (child !== outputName && child !== newLineDiv1  &&child !==Label5 &&child !==Select5 && child.className!=='column-SubNode' &&child !== Select1 && child !== Label1&& child !== newLineDiv) {
                  outputContainer.removeChild(child);
              }

              // 更新 child 为之前的元素
              child = prev;
          }
          data.nodes.forEach((node) => {
            if (node.id == id) {
              node.Outputs.forEach((output,index) => {
                if (output.Id == IdTemp) {
                  output.selectBox5 = value;
                  CreatCondition(output.selectBox1)
                }
              }
              );
            }
          }
          );
          ChangeDatas(data);
          
        }
      }
      
      // Add description label


      outputColumn.appendChild(outputContainer);
    }


    // 假设Inputs是已定义的
  Inputs.forEach((input, index) => {
      CreatInputs(input,index,input.Id);
  });
  Outputs.forEach((output, index) => {
    setTimeout(() => {
      CreatOutputs(output,index,output.Id);
    }, 200);
  });
    }
    if(NodeKind.includes('Normal') || (NodeKind.includes('Trigger') && NodeKind!='ArrayTrigger_DataBase'))
    {
      if(InputIsAdd==null || InputIsAdd==false || InputIsAdd=='')
      {
        const inputColumn = document.createElement('div');
        inputColumn.className = 'column';
        const inputLabel = document.createElement('div');
        inputLabel.textContent = 'Input'; // 设置文本
        inputLabel.className = 'column-label'; // 设置样式类
        inputColumn.appendChild(inputLabel);
        vessel.appendChild(inputColumn);
        // 创建输出列并添加标签
        // 添加元素到 DOM

        // 假设Inputs是已定义的
        Inputs.forEach((input, index) => {
          //不包含'FilePath'

          const inputContainer = document.createElement('div');
          inputContainer.className = 'input-container';

          // 创建显示输入名称的输入框
          const inputName = document.createElement('input');
          inputName.value = input.name;
          inputContainer.appendChild(inputName);
          // 创建选择框
          const selectBox = document.createElement('select');
          const optionLink = document.createElement('option');
          optionLink.value = 'link';
          optionLink.text = 'Link';
          const optionLabel = document.createElement('option');
          optionLabel.value = 'Input';
          optionLabel.text = 'Input';
          selectBox.appendChild(optionLink);
          selectBox.appendChild(optionLabel);
          inputContainer.appendChild(selectBox);
          let labelTextarea = document.createElement('textarea'); // 在外部声明变量以便在不同的作用域中访问
          labelTextarea.className = 'normalInput-textarea';
          let pathButton;
          if(input.IsLabel==true)
          {
            selectBox.value = 'Input';
            handleChange('Input');
          }
          // 处理选择框变化
          
          function handleChange(value) {
              // 如果之前添加了文本区域且现在选择是“Link”，则移除文本区域
              if (labelTextarea && value === 'link') {
                  inputContainer.removeChild(labelTextarea);
                  if (pathButton && inputContainer.contains(pathButton)) {
                    inputContainer.removeChild(pathButton);
                  }
                  labelTextarea = null; // 确保引用被清除
                  ChangeAnchorValue(id, '', 'link',input.Id);
              } else if (value === 'Input') {
                  // 如果当前选择是“Input”，则添加文本区域
                  if(input.Kind !='Boolean')
                  {
                    labelTextarea=document.createElement('textarea');

                    if(input.Kind == 'Num')
                    labelTextarea.value = input.Num;
                    else if(input.Kind .includes('String'))
                    labelTextarea.value = input.Context;
                    let uniqueClass = `unique-textarea-${id}-${input.Id}`;
                    labelTextarea.className = 'normalInput-textarea ' + uniqueClass; // 同时设置两个类名
                    labelTextarea.id = uniqueClass;
                    labelTextarea.style.height = '20px';
                    labelTextarea.style.width = '560px'; 
                    labelTextarea.classList.add(uniqueClass); // 为文本区域添加唯一类名
                    adjustHeightBasedOnContent(labelTextarea);
                    function adjustHeightBasedOnContent(textarea) {
                      console.log("Adjusting height...");

                      // 清除之前的高度设置
                      textarea.style.height = 'auto';

                      // 直接使用 textarea 的 scrollHeight 来计算高度
                      const computedHeight = textarea.scrollHeight;
                      console.log(`Computed height: ${computedHeight}px`);

                      // 设置textarea的高度，限制高度在60px到400px之间
                      const newHeight = Math.max(Math.min(computedHeight, 400), 60);
                      textarea.style.height = `${newHeight}px`;
                      console.log(`Textarea height set to: ${newHeight}px`);
                    }
                    labelTextarea.oninput = function() {
                      adjustHeight(this);
                    };
                    labelTextarea.addEventListener('input', function() {
                    let isOk = true; // 假定输入无效
                    if(input.Kind == 'Num') {
                      if(labelTextarea.value.match(/^[0-9]+$/))
                      {
                        isOk = true; // 如果是，将isOk设置为true，表示输入有
                      }
                      else {
                        // 如果上述条件都不满足，则弹出提示窗口告知用户输入格式不正确
                        isOk = false;
                        alert("类型不符，您应该输入数字！");
                      }
                    }
                    if (labelTextarea.value.trim() === '') {
                        isOk = false; // 如果输入为空，则将isOk设置为false，表示输入无效
                        alert("输入不能为空！");
                    }
                      if (isOk) {
                        ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id); // 假定 id 和 ChangeNodeLabel 已定义
                      }

                  });
                    labelTextarea.addEventListener('input', function() {
                      // 重置高度以计算新的高度
                      this.style.height = 'auto';
                    
                      // 设置新的高度
                      this.style.height = `${this.scrollHeight}px`;
                    });
                    inputContainer.appendChild(labelTextarea);
                    if(input.Kind.includes('FilePath'))
                      {
                        pathButton = document.createElement('button');
                        pathButton.textContent = 'Selecte Path';
                        pathButton.addEventListener('click', function() {
                          CreatFilePath(input.Id,id);
                        });
                        inputContainer.appendChild(pathButton);
    
                      }
                  }
                  else
                  {
                    const selectBox = document.createElement('select');
                    const option1 = document.createElement('option');
                    option1.value = 'true';
                    option1.text = 'true';
                    const option2 = document.createElement('option');
                    option2.value = 'false';
                    option2.text = 'false';
                    selectBox.appendChild(option1);
                    selectBox.appendChild(option2);
                    inputContainer.appendChild(selectBox);
                    selectBox.value = input.Boolean;
                    selectBox.addEventListener('change', function() {
                      ChangeAnchorValue(id, selectBox.value, 'Input',input.Id); // 假定 id 和 ChangeNodeLabel 已定义
                    });
                  }
              }
          }
          selectBox.addEventListener('change', function() {
            handleChange(this.value);
          });
          // 为输入框添加 blur 监听器
          inputName.addEventListener('change', function() {
              ChangeAnchorLabel(id, inputName.value, index,input.Id,true); // 假定 id 和 ChangeNodeLabel 已定义
          });

          inputColumn.appendChild(inputContainer);
          
        });
      }
      else
      {
        function CreatInputs(input,index,IdTemp)
        {
          const inputContainer = document.createElement('div');
          inputContainer.className = 'input-container';

          // 创建显示输入名称的输入框
          const inputName = document.createElement('input');
          inputName.value = input.name;
          inputContainer.appendChild(inputName);

          // 创建选择框
          const selectBox = document.createElement('select');
          const optionLink = document.createElement('option');
          optionLink.value = 'link';
          optionLink.text = 'Link';
          const optionLabel = document.createElement('option');
          optionLabel.value = 'Input';
          optionLabel.text = 'Input';
          selectBox.appendChild(optionLink);
          selectBox.appendChild(optionLabel);
          inputContainer.appendChild(selectBox);

          const Select1=document.createElement('select');
          const optionContext = document.createElement('option');
          optionContext.value = 'String';
          optionContext.text = 'String';
          const optionNum = document.createElement('option');
          optionNum.value = 'Num';
          optionNum.text = 'Num';
          const optionBool = document.createElement('option');
          optionBool.value = 'Boolean';
          optionBool.text = 'Boolean';
          const optionFilePath = document.createElement('option');
          optionFilePath.value = 'String_FilePath';
          optionFilePath.text = 'FilePath';

          Select1.appendChild(optionContext);
          Select1.appendChild(optionNum);
          Select1.appendChild(optionBool);
          Select1.appendChild(optionFilePath);
          //Select1选择input.Kind的值匹配
          Select1.selectedIndex = 2;
          inputContainer.appendChild(Select1);
          Select1.addEventListener('change', function() {
            let data = graph.save();
            data.nodes.forEach((node) => {
              if (node.id == id) {
                node.Inputs.forEach((input,index) => {
                  if (input.Id == IdTemp) {
                    input.Kind = this.value;
                  }
                }
                );
              }
            }
            );
            ChangeDatas(data);
          });
          const SubNode = document.createElement('div');
          SubNode.className = 'column-SubNode'; // 使用之前定义的样式类
          SubNode.style.left = '310px'; // 设置与标签之间的间距
          inputContainer.appendChild(SubNode);
          SubNode.onmousedown = function() {//删除这个矛点
            let data=graph.save();
            data.nodes.forEach((node) => {
              if(node.id == id)
              {
                //通过IdTemp删除这个矛点
                node.Inputs.forEach((input,index) => {
                    if(input.Id == IdTemp)
                    {
                      node.Inputs.splice(index,1);
                    }
                  });
                const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
                node.anchorPoints = node.Inputs.map((node, index) => {
                    const anchorHeight = 60 + index * 20;
                    return [0.05, anchorHeight / maxHeight]
                  }).concat(node.Outputs.map((node, index) => {
                    const anchorHeight = 60 + index * 20;
                    return [0.95, anchorHeight / maxHeight]
                  })).concat([[0, 0]]);
                ChangeDatas(data);

                //移除inputContainer
                inputContainer.parentNode.removeChild(inputContainer);
              }
            });
            RefreshEdge();

          }

          Select1.value = input.Kind;
          let labelTextarea = document.createElement('textarea'); // 在外部声明变量以便在不同的作用域中访问
          if(input.IsLabel==true)
          {
            selectBox.value = 'Input';
            handleChange('Input');
          }
          // 处理选择框变化
          function handleChange(value) {
              // 如果之前添加了文本区域且现在选择是“Link”，则移除文本区域
              let data = graph.save();
              data.edges.forEach(edge => {
                if (edge.target==id && edge.targetAnchor==index) {
                  const item = graph.findById(edge.id);
                  const targetNode = graph.findById(edge.target);
                  const targetAnchor = targetNode.getContainer().find(ele => ele.get('anchorPointIdx') === edge.targetAnchor);
                  targetAnchor.set('links', targetAnchor.get('links') + 1);
                  ChangeLink(targetAnchor);
                  graph.remove(item);
                }
              });
              if (labelTextarea && value === 'link') {
                  inputContainer.removeChild(labelTextarea);
                  labelTextarea = null; // 确保引用被清除
                  ChangeAnchorValue(id, '', 'link',input.Id);
              } else if (value === 'Input') {
                  // 如果当前选择是“Input”，则添加文本区域
                  labelTextarea = document.createElement('textarea');
                  if(input.Kind == 'Num')
                  labelTextarea.value = input.Num;
                  else if(input.Kind .includes('String'))
                  labelTextarea.value = input.Context;
                  labelTextarea.style.width = '550px'; // 设置固定宽度
                  labelTextarea.style.height = '20px'; // 初始高度
                  labelTextarea.style.overflow = 'hidden'; // 防止滚动条出现
                  labelTextarea.style.verticalAlign = 'top'; // 输入行字符居上
                  labelTextarea.style.lineHeight = '20px'; // 设置行高以匹配初始高度
                  labelTextarea.style.resize = 'vertical';
                  let uniqueClass = `unique-textarea-${id}-${input.Id}`; // 使用input.Id生成唯一的类名
                  labelTextarea.className = uniqueClass;
                  labelTextarea.id = uniqueClass;
                  
                  labelTextarea.classList.add(uniqueClass); // 为文本区域添加唯一类名
                  //labelTextarea.style.resize = 'none'; // 禁止用户手动调整大小
                  labelTextarea.style.resize = 'vertical';
                  ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id);
                  labelTextarea.addEventListener('input', function() {
                  let isOk = true; // 假定输入无效
                  if(input.Kind == 'Num') {
                    if(labelTextarea.value.match(/^[0-9]+$/))
                    {
                      isOk = true; // 如果是，将isOk设置为true，表示输入有
                    }
                    else {
                      // 如果上述条件都不满足，则弹出提示窗口告知用户输入格式不正确
                      isOk = false;
                      alert("类型不符，您应该输入数字！");
                    }
                  }
                  if (labelTextarea.value.trim() === '') {
                      isOk = false; // 如果输入为空，则将isOk设置为false，表示输入无效
                      alert("输入不能为空！");
                  }
                    if (isOk) {
                      ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id); // 假定 id 和 ChangeNodeLabel 已定义
                    }

                });
                  labelTextarea.addEventListener('input', function() {
                    // 重置高度以计算新的高度
                    this.style.height = 'auto';
                  
                    // 设置新的高度
                    this.style.height = `${this.scrollHeight}px`;
                  });
                  inputContainer.appendChild(labelTextarea);
              }
          }
          selectBox.addEventListener('change', function() {
            handleChange(this.value);
          });
          Select1.addEventListener('change', function() {

          });
          // 为输入框添加 blur 监听器
          inputName.addEventListener('input', function() {
              ChangeAnchorLabel(id, inputName.value, index,input.Id,true); // 假定 id 和 ChangeNodeLabel 已定义
          });

          inputColumn.appendChild(inputContainer);
          RefreshEdge();
        }
        const inputColumn = document.createElement('div');
        inputColumn.className = 'column';
        const inputLabel = document.createElement('div');
        inputLabel.textContent = 'Input'; // 设置文本
        inputLabel.className = 'column-label'; // 设置样式类
        inputColumn.appendChild(inputLabel);
        const addNode = document.createElement('div');
        addNode.className = 'column-AddNode'; // 使用之前定义的样式类
        let IdTemp='';
        inputColumn.appendChild(inputLabel);
        vessel.appendChild(inputColumn);
        Inputs.forEach((input, index) => {
          if(input.Kind.includes('FilePath')==false)
          {
            const inputContainer = document.createElement('div');
            inputContainer.className = 'input-container';

            // 创建显示输入名称的输入框
            const inputName = document.createElement('input');
            inputName.value = input.name;
            inputContainer.appendChild(inputName);

            // 创建选择框
            const selectBox = document.createElement('select');
            const optionLink = document.createElement('option');
            optionLink.value = 'link';
            optionLink.text = 'Link';
            const optionLabel = document.createElement('option');
            optionLabel.value = 'Input';
            optionLabel.text = 'Input';
            selectBox.appendChild(optionLink);
            selectBox.appendChild(optionLabel);
            inputContainer.appendChild(selectBox);
            let labelTextarea = document.createElement('textarea'); // 在外部声明变量以便在不同的作用域中访问
            let uniqueClass = `unique-textarea-${id}-${input.Id}`; // 使用input.Id生成唯一的类名
            
            labelTextarea.className = uniqueClass;
            labelTextarea.id = uniqueClass;
            labelTextarea.classList.add(uniqueClass); // 为文本区域添加唯一类名
            if(input.IsLabel==true)
            {
              selectBox.value = 'Input';
              handleChange('Input');
            }
            // 处理选择框变化
            function handleChange(value) {
                // 如果之前添加了文本区域且现在选择是“Link”，则移除文本区域
                if (labelTextarea && value === 'link') {
                    inputContainer.removeChild(labelTextarea);
                    labelTextarea = null; // 确保引用被清除
                    ChangeAnchorValue(id, '', 'link',input.Id);
                } else if (value === 'Input') {
                    // 如果当前选择是“Input”，则添加文本区域
                    labelTextarea = document.createElement('textarea');
                    if(input.Kind == 'Num')
                    labelTextarea.value = input.Num;
                    else if(input.Kind .includes('String'))
                    labelTextarea.value = input.Context;
                    labelTextarea.style.width = '550px'; // 设置固定宽度
                    labelTextarea.style.height = '20px'; // 初始高度
                    labelTextarea.style.overflow = 'hidden'; // 防止滚动条出现
                    labelTextarea.style.verticalAlign = 'top'; // 输入行字符居上
                    labelTextarea.style.lineHeight = '20px'; // 设置行高以匹配初始高度
                    //labelTextarea.style.resize = 'none'; // 禁止用户手动调整大小
                    labelTextarea.style.resize = 'vertical';
                    adjustHeightBasedOnContent(labelTextarea);
                    labelTextarea.oninput = function() {
                      adjustHeight(this);
                    };
                    labelTextarea.addEventListener('input', function() {
                    let isOk = true; // 假定输入无效
                    if(input.Kind == 'Num') {
                      if(labelTextarea.value.match(/^[0-9]+$/))
                      {
                        isOk = true; // 如果是，将isOk设置为true，表示输入有
                      }
                      else {
                        // 如果上述条件都不满足，则弹出提示窗口告知用户输入格式不正确
                        isOk = false;
                        alert("类型不符，您应该输入数字！");
                      }
                    }
                    if (labelTextarea.value.trim() === '') {
                        isOk = false; // 如果输入为空，则将isOk设置为false，表示输入无效
                        alert("输入不能为空！");
                    }
                      if (isOk) {
                        ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id); // 假定 id 和 ChangeNodeLabel 已定义
                      }

                  });
                    labelTextarea.addEventListener('input', function() {
                      // 重置高度以计算新的高度
                      this.style.height = 'auto';
                    
                      // 设置新的高度
                      this.style.height = `${this.scrollHeight}px`;
                    });
                    inputContainer.appendChild(labelTextarea);
                }
            }
            selectBox.addEventListener('change', function() {
              handleChange(this.value);
            });
            // 为输入框添加 blur 监听器
            inputName.addEventListener('input', function() {
                ChangeAnchorLabel(id, inputName.value, index,input.Id,true); // 假定 id 和 ChangeNodeLabel 已定义
            });

            inputColumn.appendChild(inputContainer);
          }
          else if (input.Kind.includes('FilePath')) {
            const inputContainer = document.createElement('div');
            inputContainer.className = 'input-container';
          
            // 创建显示输入名称的输入框
            const inputName = document.createElement('input');
            inputName.value = input.name;
            inputContainer.appendChild(inputName);
            // 创建选择框
            const selectBox = document.createElement('select');
            const optionLink = document.createElement('option');
            optionLink.value = 'link';
            optionLink.text = 'Link';
            const optionLabel = document.createElement('option');
            optionLabel.value = 'Input';
            optionLabel.text = 'Input';
            selectBox.appendChild(optionLink);
            selectBox.appendChild(optionLabel);
            inputContainer.appendChild(selectBox);
            // 创建路径按钮
            let pathButton ;
          
            // 创建文本区域
            let labelTextarea = document.createElement('textarea'); // 在外部声明变量以便在不同的作用域中访问
            let uniqueClass = `unique-textarea-${id}-${input.Id}`; // 使用input.Id生成唯一的类名
            
            labelTextarea.className = uniqueClass;
            labelTextarea.id = uniqueClass;
            labelTextarea.classList.add(uniqueClass); // 为文本区域添加唯一类名
          
            // 为输入框添加 input 监听器
            inputName.addEventListener('input', function () {
              ChangeAnchorLabel(id, inputName.value, index, input.Id, true); // 假定 id 和 ChangeNodeLabel 已定义
            });
            if(input.IsLabel==true)
              {
                selectBox.value = 'Input';
                handleChange('Input');
              }
              // 处理选择框变化
              function handleChange(value) {
                  // 如果之前添加了文本区域且现在选择是“Link”，则移除文本区域
                  let data = graph.save();
                  data.edges.forEach(edge => {
                    if (edge.target==id && edge.targetAnchor==index) {
                      
                      const item = graph.findById(edge.id);
                      const targetNode = graph.findById(edge.target);
                      const targetAnchor = targetNode.getContainer().find(ele => ele.get('anchorPointIdx') === edge.targetAnchor);
                      targetAnchor.set('links', targetAnchor.get('links') + 1);
                      ChangeLink(targetAnchor);
                      graph.remove(item);
                    }
                  });
                  if (labelTextarea && value === 'link') {
                    if (pathButton && inputContainer.contains(pathButton)) {
                      inputContainer.removeChild(pathButton);
                    }
                    inputContainer.removeChild(labelTextarea);
                    labelTextarea = null; // 确保引用被清除
                    ChangeAnchorValue(id, '', 'link',input.Id);
                  } else if (value === 'Input') {
                      // 如果当前选择是“Input”，则添加文本区域
                      labelTextarea = document.createElement('textarea');
                      if(input.Kind == 'Num')
                      labelTextarea.value = input.Num;
                      else if(input.Kind .includes('String'))
                      labelTextarea.value = input.Context;
                      labelTextarea.style.width = '550px'; // 设置固定宽度
                      labelTextarea.style.height = '20px'; // 初始高度
                      labelTextarea.style.overflow = 'hidden'; // 防止滚动条出现
                      labelTextarea.style.verticalAlign = 'top'; // 输入行字符居上
                      labelTextarea.style.lineHeight = '20px'; // 设置行高以匹配初始高度
                      labelTextarea.style.resize = 'vertical';
                      let uniqueClass = `unique-textarea-${id}-${input.Id}`; // 使用input.Id生成唯一的类名
                      labelTextarea.className = uniqueClass;
                      labelTextarea.id = uniqueClass;
                      adjustHeightBasedOnContent(labelTextarea);
                      labelTextarea.oninput = function() {
                        adjustHeight(this);
                      };
                      labelTextarea.classList.add(uniqueClass); // 为文本区域添加唯一类名
                      //labelTextarea.style.resize = 'none'; // 禁止用户手动调整大小
                      labelTextarea.style.resize = 'vertical';
                      ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id);
                      labelTextarea.addEventListener('input', function() {
                      let isOk = true; // 假定输入无效
                      if(input.Kind == 'Num') {
                        if(labelTextarea.value.match(/^[0-9]+$/))
                        {
                          isOk = true; // 如果是，将isOk设置为true，表示输入有
                        }
                        else {
                          // 如果上述条件都不满足，则弹出提示窗口告知用户输入格式不正确
                          isOk = false;
                          alert("类型不符，您应该输入数字！");
                        }
                      }
                      if (labelTextarea.value.trim() === '') {
                          isOk = false; // 如果输入为空，则将isOk设置为false，表示输入无效
                          alert("输入不能为空！");
                      }
                        if (isOk) {
                          ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id); // 假定 id 和 ChangeNodeLabel 已定义
                        }
    
                    });
                      labelTextarea.addEventListener('input', function() {
                        // 重置高度以计算新的高度
                        this.style.height = 'auto';
                      
                        // 设置新的高度
                        this.style.height = `${this.scrollHeight}px`;
                      });
                      inputContainer.appendChild(labelTextarea);
                      if(input.Kind.includes('FilePath'))
                        {
                          pathButton = document.createElement('button');
                          pathButton.textContent = 'Selecte Path';
                          pathButton.addEventListener('click', function() {
                            CreatFilePath(input.Id,id);
                          });
                          inputContainer.appendChild(pathButton);
      
                        }
                  }
              }
              selectBox.addEventListener('change', function() {
                handleChange(this.value);
              });
            // 为文本区域添加 input 监听器
            labelTextarea.addEventListener('input', function () {
              ChangeAnchorValue(id, labelTextarea.value, 'FilePath', input.Id); // 假定 ChangeAnchorValue 已定义
            });
          
            inputColumn.appendChild(inputContainer);
          }
        });
        addNode.onmousedown = function() {
            let data=graph.save();
            data.nodes.forEach((node) => {
              if(node.id == id)
              {
                IdTemp='Input' + (node.Inputs.length + 1).toString();
                let TempName = 'Input' + (node.Inputs.length + 1).toString();
                let counter = 1; // 新增一个计数器
                // 检查是否重名，如果重名则+1继续检查
                while (node.Inputs.some(input => input.name === TempName)) {
                    TempName = 'Input' + (node.Inputs.length + 1 + counter).toString(); // 使用计数器调整名称
                    counter++; // 每次循环递增计数器
                }
                node.Inputs.push({
                  'Num': null,
                  'Kind': 'String',
                  'Id': IdTemp,
                  'Context': null,
                  'Isnecessary': false,
                  'name': TempName,
                  'Link': 0,
                  'IsLabel': false,
              });
              const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
              node.anchorPoints = node.Inputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.05, anchorHeight / maxHeight]
                }).concat(node.Outputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.95, anchorHeight / maxHeight]
                })).concat([[0, 0]]);
              CreatInputs(node.Inputs[node.Inputs.length - 1],node.Inputs.length - 1,IdTemp);
              ChangeDatas(data);
              }
            });

            RefreshEdge();
          };
        //等比例扩大addNode

        // 确定插入位置并将AddNode插入到inputColumn中
        const nextElement = inputLabel.nextSibling; // 获取inputLabel之后的元素
        if (nextElement) {
            // 如果inputLabel后面有其他元素，则在这个元素之前插入addNode
            inputColumn.insertBefore(addNode, nextElement);
        } else {
            // 如果inputLabel是最后一个元素或inputColumn没有其他子元素，则直接追加
            inputColumn.appendChild(addNode);
        }
      }
      if(OutputsIsAdd==null || OutputsIsAdd==false || OutputsIsAdd=='')
        {
          const outputColumn = document.createElement('div');
          outputColumn.className = 'column';
          const outputLabel = document.createElement('div');
          outputLabel.textContent = 'Output'; // 设置文本
          outputLabel.className = 'column-label'; // 设置样式类
          outputColumn.appendChild(outputLabel);
          // 将输入和输出列添加到节点容器中

          vessel.appendChild(outputColumn);
          Outputs.forEach((output, index) => {
            const outputContainer = document.createElement('div');
            outputContainer.className = 'output-container';
            outputContainer.style.display = 'flex';
            outputContainer.style.alignItems = 'flex-start'; // Content aligned at top
            outputContainer.style.flexWrap = 'wrap'; // Allow child elements to wrap
            outputContainer.style.marginBottom = '10px'; // Increase line spacing
            outputContainer.style.maxHeight = '300px'; // Set maximum height
            outputContainer.style.overflowY = 'auto'; // Add vertical scrollbar when needed

            const outputName = document.createElement('input');
            outputName.value = output.name;
            outputContainer.appendChild(outputName);
            outputName.addEventListener('input', function() {
              ChangeAnchorLabel(id, outputName.value, index,output.Id,false);
            });
            outputColumn.appendChild(outputContainer);
          });
        }
        else
        {
          function CreatOutputs(output, index,IdTemp) {
            const outputContainer = document.createElement('div');
            outputContainer.className = 'output-container';
            outputContainer.style.display = 'flex';
            outputContainer.style.alignItems = 'flex-start'; // Content aligned at top
            outputContainer.style.flexWrap = 'wrap'; // Allow child elements to wrap
            outputContainer.style.marginBottom = '10px'; // Increase line spacing
            outputContainer.style.maxHeight = '300px'; // Set maximum height
            outputContainer.style.overflowY = 'auto'; // Add vertical scrollbar when needed

    
            // Create an input box to display the output name
            const outputName = document.createElement('input');
            outputName.value = output.name;
            outputName.style.width = '100px'; // Allow it to grow
            outputContainer.appendChild(outputName);
    
            // Create type selection box
            const Select1 = document.createElement('select');
            Select1.style.width = '75px'; // Set a fixed width
            const optionContext = document.createElement('option');
            optionContext.value = 'String';
            optionContext.text = 'String';
            const optionNum = document.createElement('option');
            optionNum.value = 'Num';
            optionNum.text = 'Num';
            const optionBool = document.createElement('option');
            optionBool.value = 'Boolean';
            optionBool.text = 'Boolean';
            Select1.appendChild(optionContext);
            Select1.appendChild(optionNum);
            Select1.appendChild(optionBool);
            Select1.value = output.Kind;
            outputContainer.appendChild(Select1);
            Select1.addEventListener('change', function() {
              let data = graph.save();
              data.nodes.forEach((node) => {
                if (node.id == id) {
                  //切断跟它output有关的边
                  node.Outputs.forEach((output,index) => {
                    if (output.Id == IdTemp) {
                      output.Kind = this.value;
                    }
                  }
                  );
                }
              }
              );
              ChangeDatas(data);
            });
            Outputs.forEach((output, index) => {
              const outputContainer = document.createElement('div');
              outputContainer.className = 'output-container';
              outputContainer.style.display = 'flex';
              outputContainer.style.alignItems = 'flex-start'; // Content aligned at top
              outputContainer.style.flexWrap = 'wrap'; // Allow child elements to wrap
              outputContainer.style.marginBottom = '10px'; // Increase line spacing
              outputContainer.style.maxHeight = '300px'; // Set maximum height
              outputContainer.style.overflowY = 'auto'; // Add vertical scrollbar when needed

              const outputName = document.createElement('input');
              outputName.value = output.name;
              outputContainer.appendChild(outputName);
              outputName.addEventListener('input', function() {
                ChangeAnchorLabel(id, outputName.value, index,output.Id,false);
              });
              outputColumn.appendChild(outputContainer);
            });
            // 添加删除按钮
            const SubNode = document.createElement('div');
            SubNode.className = 'column-SubNode'; // 使用之前定义的样式类
            SubNode.style.right = '30px'; // 设置与 Description 之间的间距
            outputContainer.appendChild(SubNode);
            SubNode.onmousedown = function() {//删除这个矛点
              let data=graph.save();
              data.nodes.forEach((node) => {
                if(node.id == id)
                {
                  //通过IdTemp删除这个矛点
                  node.Outputs.forEach((output,index) => {
                      if(output.Id == IdTemp)
                      {
                        node.Outputs.splice(index,1);
                      }
                    }
                  );
                  const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
                  node.anchorPoints = node.Inputs.map((node, index) => {
                      const anchorHeight = 60 + index * 20;
                      return [0.05, anchorHeight / maxHeight]
                    }).concat(node.Outputs.map((node, index) => {
                      const anchorHeight = 60 + index * 20;
                      return [0.95, anchorHeight / maxHeight]
                    })).concat([[0, 0]]);
                  ChangeDatas(data);
                  //移除outputContainer
                  outputContainer.parentNode.removeChild(outputContainer);
                }
              });
              RefreshEdge();
            }
            outputName.addEventListener('input', function() {
              ChangeAnchorLabel(id, outputName.value, index,output.Id,false); // 假定 id 和 ChangeNodeLabel 已定义
          });
            outputColumn.appendChild(outputContainer);
          }
          const outputColumn = document.createElement('div');
          outputColumn.className = 'column';
          const outputLabel = document.createElement('div');
          outputLabel.textContent = 'Output'; // 设置文本
          outputLabel.className = 'column-label'; // 设置样式类
          outputColumn.appendChild(outputLabel);
          // 将输入和输出列添加到节点容器中
          vessel.appendChild(outputColumn);
          Outputs.forEach((output, index) => {
            const outputContainer = document.createElement('div');
            outputContainer.className = 'output-container';
            outputContainer.style.display = 'flex';
            outputContainer.style.alignItems = 'flex-start'; // Content aligned at top
            outputContainer.style.flexWrap = 'wrap'; // Allow child elements to wrap
            outputContainer.style.marginBottom = '10px'; // Increase line spacing
            outputContainer.style.maxHeight = '300px'; // Set maximum height
            outputContainer.style.overflowY = 'auto'; // Add vertical scrollbar when needed

            const outputName = document.createElement('input');
            outputName.value = output.name;
            outputContainer.appendChild(outputName);
            outputName.addEventListener('input', function() {
              ChangeAnchorLabel(id, outputName.value, index,output.Id,false);
            });
            outputColumn.appendChild(outputContainer);
          });
          const addNode1 = document.createElement('div');
          addNode1.className = 'column-AddNode'; // 使用之前定义的样式类
          addNode1.style.marginLeft = '20px'; // 设置与标签之间的间距
          let IdTemp='';
          outputColumn.appendChild(addNode1);
          addNode1.onmousedown = function() {
            let data=graph.save();
            data.nodes.forEach((node) => {
              if(node.id == id)
              {
                IdTemp='Output' + (node.Outputs.length + 1).toString();
                let TempName = 'Output' + (node.Inputs.length + 1).toString();
                let counter = 1; // 新增一个计数器
                // 检查是否重名，如果重名则+1继续检查
                while (node.Outputs.some(output => output.name === TempName)) {
                    TempName = 'Input' + (node.Outputs.length + 1 + counter).toString(); // 使用计数器调整名称
                    counter++; // 每次循环递增计数器
                }
                node.Outputs.push({
                  'Num': 0,
                  'Kind': 'String',
                  'Id': IdTemp,
                  'Context': '',
                  'Boolean': false,
                  'Isnecessary': true,
                  'name': TempName,
                  'Link': 0,
                  'IsLabel': false,
              });
              const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
              node.anchorPoints = node.Inputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.05, anchorHeight / maxHeight]
                }).concat(node.Outputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.95, anchorHeight / maxHeight]
                })).concat([[0, 0]]);
              CreatOutputs(node.Outputs[node.Outputs.length - 1],node.Outputs.length - 1,IdTemp);
              ChangeDatas(data);
              }
            });
    
            RefreshEdge();
          };
        }
    }
    else if(NodeKind.includes('LLm'))
    {
        //#region 基本设置部分
        const LlmSettingColumn = document.createElement('div');
        LlmSettingColumn.className = 'column';

        const llmSettings = document.createElement('div');
        llmSettings.className = 'column';

        
        const basicSettings = document.createElement('div');
        basicSettings.className = 'basic-settings';

        // 去掉 name 变量中的 '.py' 后缀
        const modelName = name.replace('.py', '');

        // 创建 modelSelector 元素并设置内容
        const modelSelector = document.createElement('div');
        modelSelector.className = 'model-selector';
        modelSelector.textContent = 'Model';
        modelSelector.style.color='white'

        // 过滤出 NodeKind 为 'LLm' 的文件，并去掉 '.py' 后缀
        const filteredFiles = fileList
            .filter(file => file.NodeKind.includes('LLm'))
            .map(file => file.filename.replace('.py', ''));

        // 创建选择框并添加过滤后的文件名
        const modelSelect = document.createElement('select');
        modelSelect.id = 'model';

        filteredFiles.forEach(filename => {
            const option = document.createElement('option');
            option.value = filename;
            option.textContent = filename;
            modelSelect.appendChild(option);
        });
        modelSelect.value = modelName; // 设置选择框的默认值

        // 将选择框添加到 modelSelector 元素中
        modelSelector.appendChild(modelSelect);

        // 添加到 basicSettings 中
        basicSettings.appendChild(modelSelector);

        // 温度设置
        const temperatureSetting = document.createElement('div');
        temperatureSetting.className = 'temperature-setting';

        const temperatureLabel = document.createElement('label');
        temperatureLabel.textContent = 'Temperature';
        temperatureLabel.style.color='white'
        temperatureSetting.appendChild(temperatureLabel);

        const temperatureInput = document.createElement('input');
        temperatureInput.type = 'number';
        temperatureInput.id = 'temperature';
        temperatureInput.style.width = '50px';
        temperatureInput.step = '0.1'; // 设置 step 属性为 0.1
        temperatureInput.min = '0';    // 设置最小值为0
        temperatureInput.max = '1';    // 设置最大值为1
        temperatureSetting.appendChild(temperatureInput);

        basicSettings.appendChild(temperatureSetting);

        // 创建快捷设置标签和选择框
        const presetSetting = document.createElement('div');
        presetSetting.className = 'preset-setting';

        const presetLabel = document.createElement('label');
        presetLabel.textContent = '加载预设';
        presetLabel.style.color='white'
        presetLabel.setAttribute('for', 'preset-select');
        presetSetting.appendChild(presetLabel);

        const presetSelect = document.createElement('select');
        presetSelect.id = 'preset-select';

        const presets = [
            { name: '创意', temperature: 0.8, top_p: 0.9, presence_penalty: 0.1, frequency_penalty: 0.1 },
            { name: '平衡', temperature: 0.5, top_p: 0.85, presence_penalty: 0.2, frequency_penalty: 0.3 },
            { name: '精确', temperature: 0.2, top_p: 0.75, presence_penalty: 0.5, frequency_penalty: 0.5 }
        ];

        presets.forEach(preset => {
            const option = document.createElement('option');
            option.value = preset.name;
            option.textContent = preset.name;
            presetSelect.appendChild(option);
        });

        // 设置选择框的默认值为“平衡”
        presetSelect.value = '平衡';

        presetSelect.addEventListener('change', () => {
            const selectedPreset = presets.find(preset => preset.name === presetSelect.value);
            if (selectedPreset) {
                temperatureInput.value = selectedPreset.temperature;
                topPInput.value = selectedPreset.top_p;
                presencePenaltyInput.value = selectedPreset.presence_penalty;
                frequencyPenaltyInput.value = selectedPreset.frequency_penalty;
                const values = [
                    modelSelect.value,
                    parseFloat(temperatureInput.value),
                    parseFloat(topPInput.value),
                    parseFloat(frequencyPenaltyInput.value),
                    parseFloat(presencePenaltyInput.value),
                    parseInt(maxTokensInput.value, 10)
                ];
                ChangeLlmSetting(id, values);  // 替换为实际的节点 ID
            }
        });

        presetSetting.appendChild(presetSelect);

        // 将快捷设置添加到 basicSettings 中
        basicSettings.appendChild(presetSetting);
        // 展开按钮
        const expandButton = document.createElement('button');
        expandButton.id = 'expand-button';
        expandButton.textContent = '↓';
        expandButton.className = 'expand-button';
        basicSettings.appendChild(expandButton);

        llmSettings.appendChild(basicSettings);

        // 高级设置部分
        const advancedSettings = document.createElement('div');
        advancedSettings.id = 'advanced-settings';
        advancedSettings.className = 'advanced-settings';

        // 参数行1
        const parameterRow1 = document.createElement('div');
        parameterRow1.className = 'parameter-row';

        // Top P
        const topPSetting = document.createElement('div');
        topPSetting.className = 'parameter';

        const topPLabel = document.createElement('label');
        topPLabel.textContent = 'Top P';
        topPSetting.appendChild(topPLabel);

        const topPInput = document.createElement('input');
        topPInput.type = 'number';
        topPInput.style.width = '50px';
        topPInput.style.marginLeft = '10px';

        topPInput.id = 'top-p';
        topPSetting.appendChild(topPInput);

        // 创建拖动条
        const topPRange = document.createElement('input');
        topPRange.type = 'range';
        topPRange.id = 'top-p-range';
        topPRange.min = 0;
        topPRange.max = 1;
        topPRange.step = 0.01;
        topPSetting.appendChild(topPRange);

        // 将输入框和拖动条同步
        topPInput.addEventListener('input', function () {
            topPRange.value = topPInput.value;
        });

        topPRange.addEventListener('input', function () {
            topPInput.value = topPRange.value;
        });

        parameterRow1.appendChild(topPSetting);

        // 频率惩罚
        const frequencyPenaltySetting = document.createElement('div');
        frequencyPenaltySetting.className = 'parameter';

        const frequencyPenaltyLabel = document.createElement('label');
        frequencyPenaltyLabel.textContent = '频率惩罚';
        frequencyPenaltySetting.appendChild(frequencyPenaltyLabel);

        const frequencyPenaltyInput = document.createElement('input');
        frequencyPenaltyInput.type = 'number';
        frequencyPenaltyInput.style.width = '50px';
        frequencyPenaltyInput.style.marginLeft = '10px';
        frequencyPenaltyInput.step = 0.1;
        frequencyPenaltyInput.min = 0;
        frequencyPenaltyInput.max = 1;
        frequencyPenaltyInput.id = 'frequency-penalty';
        frequencyPenaltySetting.appendChild(frequencyPenaltyInput);

        // 创建拖动条
        const frequencyPenaltyRange = document.createElement('input');
        frequencyPenaltyRange.type = 'range';
        frequencyPenaltyRange.id = 'frequency-penalty-range';
        frequencyPenaltyRange.min = 0;
        frequencyPenaltyRange.max = 1;
        frequencyPenaltyRange.step = 0.1;
        frequencyPenaltySetting.appendChild(frequencyPenaltyRange);

        // 将输入框和拖动条同步
        frequencyPenaltyInput.addEventListener('input', function () {
            frequencyPenaltyRange.value = frequencyPenaltyInput.value;
        });

        frequencyPenaltyRange.addEventListener('input', function () {
            frequencyPenaltyInput.value = frequencyPenaltyRange.value;
        });

        parameterRow1.appendChild(frequencyPenaltySetting);

        advancedSettings.appendChild(parameterRow1);

        // 参数行2
        const parameterRow2 = document.createElement('div');
        parameterRow2.className = 'parameter-row';

        // 存在惩罚
        const presencePenaltySetting = document.createElement('div');
        presencePenaltySetting.className = 'parameter';

        const presencePenaltyLabel = document.createElement('label');
        presencePenaltyLabel.textContent = '存在惩罚';
        presencePenaltySetting.appendChild(presencePenaltyLabel);

        const presencePenaltyInput = document.createElement('input');
        presencePenaltyInput.type = 'number';
        presencePenaltyInput.style.width = '50px';
        presencePenaltyInput.style.marginLeft = '10px';
        presencePenaltyInput.step = 0.1;
        presencePenaltyInput.min = 0;
        presencePenaltyInput.max = 1;
        presencePenaltyInput.id = 'presence-penalty';
        presencePenaltySetting.appendChild(presencePenaltyInput);

        // 创建拖动条
        const presencePenaltyRange = document.createElement('input');
        presencePenaltyRange.type = 'range';
        presencePenaltyRange.id = 'presence-penalty-range';
        presencePenaltyRange.min = 0;
        presencePenaltyRange.max = 1;
        presencePenaltyRange.step = 0.1;
        presencePenaltySetting.appendChild(presencePenaltyRange);

        // 将输入框和拖动条同步
        presencePenaltyInput.addEventListener('input', function () {
            presencePenaltyRange.value = presencePenaltyInput.value;
        });

        presencePenaltyRange.addEventListener('input', function () {
            presencePenaltyInput.value = presencePenaltyRange.value;
        });

        parameterRow2.appendChild(presencePenaltySetting);

        // 最大标记
        const maxTokensSetting = document.createElement('div');
        maxTokensSetting.className = 'parameter';

        const maxTokensLabel = document.createElement('label');
        maxTokensLabel.textContent = '最大标记';
        maxTokensSetting.appendChild(maxTokensLabel);

        const maxTokensInput = document.createElement('input');
        maxTokensInput.type = 'number';
        maxTokensInput.style.width = '50px';
        maxTokensInput.style.marginLeft = '10px';
        maxTokensInput.id = 'max-tokens';
        maxTokensSetting.appendChild(maxTokensInput);

        // 创建拖动条
        const maxTokensRange = document.createElement('input');
        maxTokensRange.type = 'range';
        maxTokensRange.id = 'max-tokens-range';
        maxTokensRange.min = 1;
        maxTokensRange.max = 16000;
        maxTokensRange.step = 1;
        maxTokensSetting.appendChild(maxTokensRange);

        // 将输入框和拖动条同步
        maxTokensInput.addEventListener('input', function () {
            maxTokensRange.value = maxTokensInput.value;
        });

        maxTokensRange.addEventListener('input', function () {
            maxTokensInput.value = maxTokensRange.value;
        });

        parameterRow2.appendChild(maxTokensSetting);

        advancedSettings.appendChild(parameterRow2);

        llmSettings.appendChild(advancedSettings);

        // 展开按钮的点击事件
        expandButton.addEventListener('click', function () {
            if (advancedSettings.style.display === 'none') {
                advancedSettings.style.display = 'block';
                expandButton.textContent = '↑';
            } else {
                advancedSettings.style.display = 'none';
                expandButton.textContent = '↓';
            }
        });

        // 将所有内容添加到文档中
        llmSettings.appendChild(basicSettings);
        llmSettings.appendChild(advancedSettings);
        LlmSettingColumn.appendChild(llmSettings);

        vessel.appendChild(LlmSettingColumn);

        // 设置默认值
        const defaultValues = {
            temperature: 0.7,
            top_p: 0.75,
            presence_penalty: 0.5,
            frequency_penalty: 0.5,
            max_tokens: 4096
        };

        // 创建一个函数来设置输入框和拖动条的值
        function setInputValue(input, range, value, defaultValue) {
          if (input) {
              if (value !== null && value !== undefined && !isNaN(value)) {
                  input.value = value;
                  if (range) {
                      range.value = value;
                  }
              } else {
                  input.value = defaultValue;
                  if (range) {
                      range.value = defaultValue;
                  }
              }
          }
      }
      
      // 使用这个函数设置输入框的值
        setInputValue(temperatureInput, null, temperature, defaultValues.temperature); // 没有滑动条
        setInputValue(topPInput, topPRange, Top_p, defaultValues.top_p);
        setInputValue(presencePenaltyInput, presencePenaltyRange, presence_penalty, defaultValues.presence_penalty);
        setInputValue(frequencyPenaltyInput, frequencyPenaltyRange, frequency_penalty, defaultValues.frequency_penalty);
        setInputValue(maxTokensInput, maxTokensRange, max_tokens, defaultValues.max_tokens);

        // 添加事件监听器，确保在参数值变化时调用 ChangeLlmSetting 函数
        const inputElements = [
            { input: topPInput, range: topPRange },
            { input: frequencyPenaltyInput, range: frequencyPenaltyRange },
            { input: presencePenaltyInput, range: presencePenaltyRange },
            { input: maxTokensInput, range: maxTokensRange }
        ];
        temperatureInput.addEventListener('input', () => {
          const values = [
              modelSelect.value,
              parseFloat(temperatureInput.value),
              parseFloat(topPInput.value),
              parseFloat(frequencyPenaltyInput.value),
              parseFloat(presencePenaltyInput.value),
              parseInt(maxTokensInput.value, 10)
          ];
          ChangeLlmSetting(id, values);
      });
        inputElements.forEach(item => {
            item.input.addEventListener('input', () => {
                item.range.value = item.input.value;
                const values = [
                    modelSelect.value,
                    parseFloat(temperatureInput.value),
                    parseFloat(topPInput.value),
                    parseFloat(frequencyPenaltyInput.value),
                    parseFloat(presencePenaltyInput.value),
                    parseInt(maxTokensInput.value, 10)
                ];
                ChangeLlmSetting(id, values);
            });

            item.range.addEventListener('input', () => {
                item.input.value = item.range.value;
                const values = [
                    modelSelect.value,
                    parseFloat(temperatureInput.value),
                    parseFloat(topPInput.value),
                    parseFloat(frequencyPenaltyInput.value),
                    parseFloat(presencePenaltyInput.value),
                    parseInt(maxTokensInput.value, 10)
                ];
                ChangeLlmSetting(id, values);
            });
        });

        modelSelect.addEventListener('change', () => {
            const values = [
                modelSelect.value,
                parseFloat(temperatureInput.value),
                parseFloat(topPInput.value),
                parseFloat(frequencyPenaltyInput.value),
                parseFloat(presencePenaltyInput.value),
                parseInt(maxTokensInput.value, 10)
            ];
            ChangeLlmSetting(id, values);
        });
        //#endregion 基本设置部分

        /* ========= 公共工具 ========= */

        // ⬆️ 高度自适应
        
        function adjustHeightBasedOnContent(textarea) {
          console.log("Adjusting height...");

          // 清除之前的高度设置
          textarea.style.height = 'auto';

          // 直接使用 textarea 的 scrollHeight 来计算高度
          const computedHeight = textarea.scrollHeight;
          console.log(`Computed height: ${computedHeight}px`);

          // 设置textarea的高度，限制高度在60px到400px之间
          const newHeight = Math.max(Math.min(computedHeight, 400), 60);
          textarea.style.height = `${newHeight}px`;
          console.log(`Textarea height set to: ${newHeight}px`);
        }

        // ⬆️ 获取光标坐标（用于定位快捷选项框）
        function getCaretCoordinates(element, position) {
          const div = document.createElement('div');
          const span = document.createElement('span');
          const style = window.getComputedStyle(element);
          for (const prop of style) div.style[prop] = style[prop];
          div.style.position = 'absolute';
          div.style.visibility = 'hidden';
          div.style.whiteSpace = 'pre-wrap';
          div.style.wordWrap = 'break-word';
          div.textContent = element.value.substring(0, position);
          span.textContent = element.value.substring(position) || '.';
          div.appendChild(span);
          document.body.appendChild(div);
          const { offsetTop: top, offsetLeft: left } = span;
          document.body.removeChild(div);
          return { top, left };
        }

        // ⬆️ 快捷选项相关
        let selectedOptionIndex = -1;
        let activeTextarea = null;
        let activeFieldKey = '';

        function hideQuickOptions() {
          const quick = document.getElementById('quickOptions');
          if (quick) quick.style.display = 'none';
        }

        function updateOptionHighlight(opts) {
          [...opts].forEach((o, i) => {
            o.style.backgroundColor = i === selectedOptionIndex ? '#b3d4fc' : '';
          });
        }

        function insertSelectedName(name, textarea, fieldKey) {
          const curPos = textarea.selectionStart;
          const lastOpen = textarea.value.lastIndexOf('{{', curPos);
          if (lastOpen === -1) return;

          const newVal =
            textarea.value.slice(0, lastOpen + 2) +
            name +
            '}}' +
            textarea.value.slice(curPos);
          textarea.value = newVal;
          textarea.selectionStart = textarea.selectionEnd = lastOpen + name.length + 4;

          const data = graph.save();
          const idx = data.nodes.findIndex((n) => n.id === id);
          data.nodes[idx][fieldKey] = newVal;
          ChangeDatas(data);

          hideQuickOptions();
          adjustHeight(textarea);
        }

        function showQuickOptions(search, curPos, textarea, fieldKey) {
          let quick = document.getElementById('quickOptions');
          if (!quick) {
            quick = document.createElement('div');
            quick.id = 'quickOptions';
            quick.style.cssText =
              'position:absolute;border:1px solid #ccc;background:#fff;z-index:1000;box-shadow:0 4px 6px rgba(0,0,0,.1);width:200px;';
            document.body.appendChild(quick);
          }

          quick.innerHTML = '';
          selectedOptionIndex = -1;

          Inputs.forEach((inp) => {
            if (!inp.name.includes(search)) return;
            const opt = document.createElement('div');
            opt.textContent = inp.name;
            opt.style.cssText =
              'padding:5px;color:#121212;cursor:pointer;border-bottom:1px solid #eee;';
            opt.onclick = () => insertSelectedName(inp.name, textarea, fieldKey);
            quick.appendChild(opt);
          });

          const rect = textarea.getBoundingClientRect();
          const caret = getCaretCoordinates(textarea, curPos);
          quick.style.left = `${rect.left + caret.left + window.scrollX}px`;
          quick.style.top = `${rect.top + caret.top + window.scrollY + 5 - textarea.scrollTop}px`;
          quick.style.display = 'block';

          activeTextarea = textarea;
          activeFieldKey = fieldKey;
        }

        // 点击空白隐藏
        document.addEventListener('click', (e) => {
          const quick = document.getElementById('quickOptions');
          if (quick && !quick.contains(e.target) && e.target !== activeTextarea) hideQuickOptions();
        });

        /* ========= 通用绑定函数 ========= */

        function attachPromptHandlers(textarea, fieldKey) {
          // 初始化
          adjustHeightBasedOnContent(textarea);

          // 输入监听
          textarea.addEventListener('input', function () {
            const data = graph.save();
            const idx = data.nodes.findIndex((n) => n.id === id);
            data.nodes[idx][fieldKey] = this.value;
            ChangeDatas(data);

            // '{{' 触发快捷选项
            const cur = this.selectionStart;
            if (this.value.slice(cur - 2, cur) === '{{') {
              const kw = this.value.slice(0, cur).split('{{').pop();
              showQuickOptions(kw, cur, this, fieldKey);
            } else hideQuickOptions();

            adjustHeight(this);
          });

          // 上下键 / 选择
          textarea.addEventListener('keydown', function (evt) {
            const quick = document.getElementById('quickOptions');
            if (!(quick && quick.style.display === 'block')) return;

            const opts = quick.children;
            if (evt.key === 'ArrowDown') {
              if (selectedOptionIndex < opts.length - 1) selectedOptionIndex++;
              updateOptionHighlight(opts);
              evt.preventDefault();
            } else if (evt.key === 'ArrowUp') {
              if (selectedOptionIndex > 0) selectedOptionIndex--;
              updateOptionHighlight(opts);
              evt.preventDefault();
            } else if (evt.key === 'Enter' || evt.key === ' ') {
              if (selectedOptionIndex >= 0 && selectedOptionIndex < opts.length) {
                insertSelectedName(opts[selectedOptionIndex].textContent, this, fieldKey);
                evt.preventDefault();
              }
            }
          });
        }

        /* ========= DOM 构建 ========= */

        // Input 列
        const inputColumn = document.createElement('div');
        inputColumn.className = 'column';
        const inputLabel = document.createElement('div');
        inputLabel.textContent = 'Input';
        inputLabel.className = 'column-label';
        inputColumn.appendChild(inputLabel);
        const addNode = document.createElement('div');
        addNode.className = 'column-AddNode';
        vessel.appendChild(inputColumn);

        // SystemPrompt 列
        const promptColumn = document.createElement('div');
        promptColumn.className = 'Promptcolumn';
        promptColumn.innerHTML = `<div class="column-label">SystemPrompt</div><div class="prompt-container"></div>`;
        vessel.appendChild(promptColumn);
        const SystemPromptInput = document.createElement('textarea');
        SystemPromptInput.className = 'prompt-textarea editable-div';
        SystemPromptInput.spellcheck = false;
        SystemPromptInput.textContent = SystemPrompt;
        promptColumn.querySelector('.prompt-container').appendChild(SystemPromptInput);

        // UserPrompt 列
        const userPromptColumn = document.createElement('div');
        userPromptColumn.className = 'Promptcolumn';
        userPromptColumn.innerHTML = `<div class="column-label">UserPrompt</div><div class="prompt-container"></div>`;
        vessel.appendChild(userPromptColumn);
        const UserPromptInput = document.createElement('textarea');
        UserPromptInput.className = 'prompt-textarea editable-div';
        UserPromptInput.spellcheck = false;
        UserPromptInput.textContent = prompt;
        userPromptColumn.querySelector('.prompt-container').appendChild(UserPromptInput);

        // 绑定逻辑
        attachPromptHandlers(SystemPromptInput, 'SystemPrompt');
        attachPromptHandlers(UserPromptInput, 'prompt');


      
        let IdTemp='';
        addNode.onmousedown = function() {
            let data=graph.save();
            data.nodes.forEach((node) => {
              if(node.id == id)
              {
                IdTemp='Input' + (node.Inputs.length + 1).toString();
                let TempName = 'Input' + (node.Inputs.length + 1).toString();
                let counter = 1; // 新增一个计数器
                // 检查是否重名，如果重名则+1继续检查
                while (node.Inputs.some(input => input.name === TempName)) {
                    TempName = 'Input' + (node.Inputs.length + 1 + counter).toString(); // 使用计数器调整名称
                    counter++; // 每次循环递增计数器
                }
                node.Inputs.push({
                  'Num': null,
                  'Kind': 'String',
                  'Id': IdTemp,
                  'Context': null,
                  'Isnecessary': false,
                  'name': TempName,
                  'Link': 0,
                  'IsLabel': false,
              });
              const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
              node.anchorPoints = node.Inputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.05, anchorHeight / maxHeight]
                }).concat(node.Outputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.95, anchorHeight / maxHeight]
                })).concat([[0, 0]]);
              CreatInputs(node.Inputs[node.Inputs.length - 1],node.Inputs.length - 1,IdTemp);
              ChangeDatas(data);
              }
            });

            RefreshEdge();
          };
        //等比例扩大addNode

        // 确定插入位置并将AddNode插入到inputColumn中
        const nextElement = inputLabel.nextSibling; // 获取inputLabel之后的元素
        if (nextElement) {
            // 如果inputLabel后面有其他元素，则在这个元素之前插入addNode
            inputColumn.insertBefore(addNode, nextElement);
        } else {
            // 如果inputLabel是最后一个元素或inputColumn没有其他子元素，则直接追加
            inputColumn.appendChild(addNode);
        }

      
      const outputColumn = document.createElement('div');
      outputColumn.className = 'column';
      const addNode1 = document.createElement('div');
      addNode1.className = 'column-AddNode'; // 使用之前定义的样式类
      addNode1.style.left = '60px'; // 设置左边距
      addNode1.style.marginTop = '-35px'; // 设置上边距
      const JsonColumn = document.createElement('div');
      JsonColumn.className = 'Jsoncolumn';
      const OriginalTextColumn = document.createElement('div');
      OriginalTextColumn.className = 'Jsoncolumn';
      OriginalTextColumn.style.display = 'flex';
      OriginalTextColumn.style.alignItems = 'flex-start'; // 使内容顶部对齐
      OriginalTextColumn.style.flexWrap = 'nowrap'; // 允许子元素换行
      
      JsonColumn.appendChild(addNode1);
      const OutputSelect = document.createElement('select');
      OutputSelect.style.width = '75px'; // 设置固定宽度
      OutputSelect.style.position = 'absolute'; // 设置相对定位
      OutputSelect.style.marginLeft = '-10px'; // 设置左边距
      OutputSelect.style.marginTop = '10px'; // 设置上边距
      
      const optionJson = document.createElement('option');
      optionJson.value = 'Json';
      optionJson.text = 'Json';
      const optionOriginalText = document.createElement('option');
      optionOriginalText.value = 'OriginalText';
      optionOriginalText.text = 'OriginalText';
      OutputSelect.style.left = '100px'; // 设置左边距
      OutputSelect.style.width = '100px'; // 设置固定宽度
      OutputSelect.style.marginTop = '13px'; // 设置上边距
      OutputSelect.appendChild(optionJson);
      OutputSelect.appendChild(optionOriginalText);
      OutputSelect.value = OriginalTextSelector;
      
      const outputLabel = document.createElement('div');
      outputLabel.textContent = 'Output'; // 设置文本
      outputLabel.className = 'column-label'; // 设置样式类
      outputColumn.appendChild(outputLabel);
      outputColumn.appendChild(OutputSelect);
      outputColumn.appendChild(JsonColumn);
      outputColumn.appendChild(OriginalTextColumn);
      OutputSelect.addEventListener('change', function() {
        let data = graph.save();
        data.nodes.forEach((node) => {
          if (node.id == id) {
            // 过滤掉与指定 IdTemp 相关的边
            data.edges = data.edges.filter(edge => edge.source !== id);  
          }
        });
        ChangeDatas(data);
        RefreshEdge();
        data = graph.save();
        data.nodes.forEach((node) => {
          if (node.id == id) {
            // 过滤掉与指定 IdTemp 相关的边
            node.OriginalTextSelector = this.value; 
             
          }
        });
        ChangeDatas(data);
        if(this.value=='OriginalText')
        {
          //JsonColumn隐身
          OriginalTextColumn.style.display = 'block';
          JsonColumn.style.display = 'none';
          let data = graph.save();
          data.nodes.forEach((node) => {
            if (node.id == id) {
              node.TempOutPuts = node.Outputs;
              // OriginalText模式下，Outputs应为1个
              if (!node.OriginalTextArray || node.OriginalTextArray.length !== 1) {
                node.OriginalTextArray = [{
                  'Num': 0,
                  'Kind': 'String',
                  'Id': 'Output1',
                  'Context': '',
                  'Boolean': false,
                  'Isnecessary': true,
                  'name': 'Output1',
                  'Link': 0,
                  'IsLabel': false,
                }];
              }
              node.Outputs = node.OriginalTextArray;
              const maxHeight = Math.max(node.Inputs.length, 1) * 20 + 60
              node.anchorPoints = node.Inputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.05, anchorHeight / maxHeight]
                }).concat(node.Outputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.95, anchorHeight / maxHeight]
                })).concat([[0, 0]]); 
              ChangeDatas(data);
            }
          });
        }
        else
        {
          //JsonColumn显示
          OriginalTextColumn.style.display = 'none';
          JsonColumn.style.display = 'block';
          let data = graph.save();
          data.nodes.forEach((node) => {
            if (node.id == id) {
              node.OriginalTextArray=node.Outputs;
              node.Outputs=node.TempOutPuts;
              const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
              node.anchorPoints = node.Inputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.05, anchorHeight / maxHeight]
                }).concat(node.Outputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.95, anchorHeight / maxHeight]
                })).concat([[0, 0]]); 
              ChangeDatas(data);
            }
          });
        }
      });
      // 将输入和输出列添加到节点容器中
      addNode1.onmousedown = function() {
        let data=graph.save();
        data.nodes.forEach((node) => {
          if(node.id == id)
          {
            IdTemp='Output' + (node.Outputs.length + 1).toString();
            let TempName = 'Output' + (node.Outputs.length + 1).toString();
            let counter = 1; // 新增一个计数器
            // 检查是否重名，如果重名则+1继续检查
            while (node.Outputs.some(output => output.name === TempName)) {
                TempName = 'Output' + (node.Outputs.length + 1 + counter).toString(); // 使用计数器调整名称
                counter++; // 每次循环递增计数器
            }
            node.Outputs.push({
              'Num': 0,
              'Kind': 'String',
              'Id': IdTemp,
              'Context': '',
              'Boolean': false,
              'Isnecessary': true,
              'name': TempName,
              'Link': 0,
              'IsLabel': false,
          });
          const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
          node.anchorPoints = node.Inputs.map((node, index) => {
              const anchorHeight = 60 + index * 20;
              return [0.05, anchorHeight / maxHeight]
            }).concat(node.Outputs.map((node, index) => {
              const anchorHeight = 60 + index * 20;
              return [0.95, anchorHeight / maxHeight]
            })).concat([[0, 0]]);
          CreatOutputs(node.Outputs[node.Outputs.length - 1],node.Outputs.length - 1,IdTemp);
          ChangeDatas(data);
          }
        });

        RefreshEdge();
      };
      vessel.appendChild(outputColumn);
      // 添加元素到 DOM
      //#region 
      //创建OriginalTextColumn有关的输入框
      /******************************************************************
       * 1. 原始容器、名称输入框保持不变
       ******************************************************************/
      const OriginalTextContainer = document.createElement('div');
      OriginalTextContainer.className = 'output-container';
      OriginalTextContainer.style.display = 'flex';
      OriginalTextContainer.style.minHeight = '200px';
      OriginalTextContainer.style.alignItems = 'flex-start';
      OriginalTextContainer.style.flexWrap = 'wrap';

      const OriginalTextNameLabel = document.createElement('input');
      OriginalTextNameLabel.value = OriginalTextName;
      OriginalTextNameLabel.style.width = '100px';
      OriginalTextNameLabel.style.position = 'absolute';
      OriginalTextNameLabel.style.marginLeft = '10px';
      OriginalTextNameLabel.style.marginTop = '0px';

      /******************************************************************
       * 2. 自定义「可收合多选」组件
       ******************************************************************/
      function createMCPMultiSelect(list) {
        /* === 获取当前节点 & 初始化 mcpServers === */
        let TempData = graph.save();
        let node = TempData.nodes.find(node => node.id === id);
        if (!Array.isArray(node.mcpServers)) {
          node.mcpServers = [];
          ChangeDatas(TempData);
        }

        /* === 外层容器 === */
        const wrapper = document.createElement('div');
        Object.assign(wrapper.style, {
          position: 'relative',
          flex: '1',
          marginLeft: '120px',
          marginTop: '0px',
          width: 'calc(100% - 130px)'
        });

        /* === 1. 展开按钮 === */
        const toggle = document.createElement('div');
        toggle.textContent = node.mcpServers.length
          ? node.mcpServers.join(', ')
          : 'MCP Sever…';
        Object.assign(toggle.style, {
          padding: '8px 14px',
          border: '1px solid #ccc',
          borderRadius: '6px',
          cursor: 'pointer',
          userSelect: 'none',
          background: '#fff',
          fontSize: '14px',
          lineHeight: '22px',
          color: '#34495e',
          width: '100%',
          boxSizing: 'border-box',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          overflow: 'hidden',
          textOverflow: 'ellipsis'
        });

        /* === 2. 下拉面板 === */
        const panel = document.createElement('div');
        panel.className = 'mcp-panel';
        Object.assign(panel.style, {
          display: 'none',
          position: 'absolute',
          top: '100%',
          left: '0',
          width: '100%',
          maxHeight: '240px',
          overflowY: 'auto',
          border: '1px solid #ccc',
          borderRadius: '6px',
          background: '#fff',
          boxShadow: '0 3px 8px rgba(0,0,0,0.15)',
          zIndex: '9999'
        });

        /* === 3. 复选项 === */
        list.forEach(name => {
          const row = document.createElement('label');
          row.className = 'mcp-row';
          Object.assign(row.style, {
            display: 'flex',
            alignItems: 'center',
            padding: '6px 10px',
            cursor: 'pointer',
            fontSize: '13px',
            fontWeight: '500'
          });

          const cb = document.createElement('input');
          cb.type = 'checkbox';
          cb.value = name;
          cb.checked = node.mcpServers.includes(name);     /* ← 初始勾选 */
          cb.style.marginRight = '8px';
          cb.style.accentColor = '#ff8c00';

          cb.addEventListener('change', () => {
            const checked = Array.from(panel.querySelectorAll('input:checked'))
                                .map(el => el.value);

            /* 更新按钮文字 */
            toggle.textContent = checked.length ? checked.join(', ') : 'MCP Sever…';

            /* 实时写回节点数据并保存 */
            node.mcpServers = checked;
            ChangeDatas(TempData);
          });

          row.appendChild(cb);
          row.appendChild(document.createTextNode(name));
          panel.appendChild(row);
        });

        /* === 4. 展开 / 收起 === */
        toggle.addEventListener('click', e => {
          e.stopPropagation();
          panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
        });

        /* 面板内部点击不关闭 */
        panel.addEventListener('click', e => e.stopPropagation());

        /* 点击面板外部关闭 */
        document.addEventListener('click', e => {
          if (!wrapper.contains(e.target)) {
            panel.style.display = 'none';
          }
        });

        /* === 5. 装配 === */
        wrapper.appendChild(toggle);
        wrapper.appendChild(panel);

        /* === 6. 全局样式（仅注入一次） === */
        if (!document.getElementById('mcp-style')) {
          const style = document.createElement('style');
          style.id = 'mcp-style';
          style.textContent = `
            .mcp-panel .mcp-row {
              color: #2c3e50 !important;
              font-weight: 500;
            }
            .mcp-panel input[type="checkbox"] {
              accent-color: #ff8c00 !important;
            }
            .mcp-panel .mcp-row:has(input:checked) {
              background: rgba(255, 140, 0, 0.08);
            }
          `;
          document.head.appendChild(style);
        }

        return wrapper;
      }

      // === 工具：把 camelCase → 首字母大写的标题（可选美化）===
      const toTitle = str => str.replace(/(^\w|_\w)/g, s => s.replace('_', '').toUpperCase());

      // === 新函数：从后端获取列表，并创建组件 ==========
      async function initMcpSelect(container) {
        try {
          const res   = await fetch('/api/mcp-servers');
          const names = await res.json();                // ['sequentialThinking', 'tavily', ...]
          const mcpServers = names.map(toTitle);         // ['SequentialThinking', 'Tavily', ...]

          const MCPServerSelect = createMCPMultiSelect(mcpServers);
          container.appendChild(MCPServerSelect);        // 插入到你想放的位置
        } catch (err) {
          console.error('加载 MCP 列表失败：', err);
        }
      }


      /******************************************************************
       * 3. 其余插入关系保持原样
       ******************************************************************/
      const newLineDiv = document.createElement('div');
      newLineDiv.style.width = '100%';
      newLineDiv.style.height = '0px';        // 只是占位，不影响视觉

      OriginalTextContainer.appendChild(OriginalTextNameLabel);
      OriginalTextContainer.appendChild(OriginalTextNameLabel);
      // 原来这里直接 new createMCPMultiSelect，现在换成异步初始化：
      initMcpSelect(OriginalTextContainer);
      OriginalTextColumn.appendChild(OriginalTextContainer);
      OriginalTextColumn.appendChild(newLineDiv);
      outputColumn.appendChild(OriginalTextColumn);

      // 名称输入监听保持不变
      OriginalTextNameLabel.addEventListener('input', () => {
        ChangeAnchorLabel(id, OriginalTextNameLabel.value, 'OriginalText', IdTemp, false);
      });


      if(OriginalTextSelector=='OriginalText')
      {
        OriginalTextColumn.style.display = 'block';
        JsonColumn.style.display = 'none';
        document.querySelectorAll('[id*="outputContainer_s"]').forEach(el => el.style.display = 'none');
        //que
      }
      else
      {
        OriginalTextColumn.style.display = 'none';
        JsonColumn.style.display = 'block';
        document.querySelectorAll('[id*="outputContainer_s"]').forEach(el => el.style.display = 'block');
      }

      function CreatOutputs(output, index,IdTemp) {
        const outputContainer = document.createElement('div');
        outputContainer.className = 'output-container';
        outputContainer.id = `outputContainer_s_${output.name}`;
        outputContainer.style.display = 'flex';
        outputContainer.style.alignItems = 'flex-start'; // Content aligned at top
        outputContainer.style.flexWrap = 'wrap'; // Allow child elements to wrap
        outputContainer.style.marginBottom = '10px'; // Increase line spacing
        outputContainer.style.maxHeight = '300px'; // Set maximum height
        outputContainer.style.overflowY = 'auto'; // Add vertical scrollbar when needed


        // Create an input box to display the output name
        const outputName = document.createElement('input');
        outputName.value = output.name;
        outputName.style.width = '100px'; // Allow it to grow
        outputContainer.appendChild(outputName);

        // Create type selection box
        const Select1 = document.createElement('select');
        Select1.style.width = '75px'; // Set a fixed width
        const optionContext = document.createElement('option');
        optionContext.value = 'String';
        optionContext.text = 'String';
        const optionNum = document.createElement('option');
        optionNum.value = 'Num';
        optionNum.text = 'Num';
        const optionBool = document.createElement('option');
        optionBool.value = 'Boolean';
        optionBool.text = 'Boolean';
        Select1.appendChild(optionContext);
        Select1.appendChild(optionNum);
        Select1.appendChild(optionBool);
        Select1.value = output.Kind;
        outputContainer.appendChild(Select1);
        Select1.addEventListener('change', function() {
          let data = graph.save();
          data.nodes.forEach((node) => {
            if (node.id == id) {
              //切断跟它output有关的边
              node.Outputs.forEach((output,index) => {
                if (output.Id == IdTemp) {
                  output.Kind = this.value;
                }
              }
              );
            }
          }
          );
          ChangeDatas(data);
        });
        // Add description label
        const DescriptionLabel = document.createElement('label');
        DescriptionLabel.textContent = '描述'; // 'Description' in Chinese
        DescriptionLabel.style.flex = '0 0 auto'; // 不允许标签伸缩，保持内容大小
        //字体颜色
        DescriptionLabel.style.color = '#FFFFFF'; // 设置字体颜色以突出显示
        outputContainer.appendChild(DescriptionLabel);

        // 创建描述输入框
        const Description = document.createElement('textarea');
        Description.className = 'Description-textarea'; // Apply the CSS class for styling
        Description.value = output.Description; // Set the value
        

        adjustHeightBasedOnContent(Description);
        Description.oninput = function() {
          adjustHeight(this);
        };
        outputContainer.appendChild(Description);

        // 添加删除按钮
        const SubNode = document.createElement('div');
        SubNode.className = 'column-SubNode'; // 使用之前定义的样式类
        SubNode.style.right = '30px'; // 设置与 Description 之间的间距
        outputContainer.appendChild(SubNode);
        SubNode.onmousedown = function() {//删除这个矛点
          let data=graph.save();
          data.nodes.forEach((node) => {
            if(node.id == id)
            {
              //通过IdTemp删除这个矛点
              node.Outputs.forEach((output,index) => {
                  if(output.Id == IdTemp)
                  {
                    node.Outputs.splice(index,1);
                  }
                }
              );
              const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
              node.anchorPoints = node.Inputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.05, anchorHeight / maxHeight]
                }).concat(node.Outputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.95, anchorHeight / maxHeight]
                })).concat([[0, 0]]);
              ChangeDatas(data);
              //移除outputContainer
              outputContainer.parentNode.removeChild(outputContainer);
            }
          });
          RefreshEdge();
        }
        // Function to resize the textarea according to its content
        Description.addEventListener('input', function() {
          // 重置高度以计算新的高度
          this.style.height = 'auto';
        
          // 设置新的高度
          this.style.height = `${this.scrollHeight}px`;
        });
        outputName.addEventListener('input', function() {
          ChangeAnchorLabel(id, outputName.value, index,output.Id,false); // 假定 id 和 ChangeNodeLabel 已定义
      });

        // suggestions.js
      class SuggestionBox {
        constructor() {
            this.createSuggestionBox();
            this.suggestions = [
                '<@find:"">',
                '<@WordsNum>',
                //'<@match:"">',
                //'<@filter:"">',
                //'<@parse:"">',
                // 添加更多提示选项...
            ];
            this.selectedIndex = -1;
        }

        createSuggestionBox() {
            this.element = document.createElement('div');
            this.element.className = 'suggestion-box';
            document.body.appendChild(this.element);
        }

        show(inputElement, cursorPosition) {
            const rect = inputElement.getBoundingClientRect();
            const coords = this.getCaretCoordinates(inputElement, cursorPosition);
            
            this.element.style.left = `${rect.left + coords.left}px`;
            this.element.style.top = `${rect.top + coords.top + 20}px`;
            this.renderSuggestions();
            this.element.style.display = 'block';
        }

        hide() {
            this.element.style.display = 'none';
            this.selectedIndex = -1;
        }

        renderSuggestions() {
            this.element.innerHTML = this.suggestions
                .map((suggestion, index) => `
                    <div class="suggestion-item ${index === this.selectedIndex ? 'selected' : ''}"
                        data-index="${index}">
                        ${suggestion}
                    </div>
                `).join('');
        }

        attachEvents(inputElement, callback) {
            // 点击选择提示
            this.element.addEventListener('click', (e) => {
                const item = e.target.closest('.suggestion-item');
                if (item) {
                    const suggestion = this.suggestions[item.dataset.index];
                    callback(suggestion);
                    this.hide();
                }
            });

            // 键盘导航
            inputElement.addEventListener('keydown', (e) => {
                if (!this.element.style.display || this.element.style.display === 'none') {
                    return;
                }

                switch(e.key) {
                    case 'ArrowDown':
                        e.preventDefault();
                        this.selectedIndex = Math.min(this.selectedIndex + 1, this.suggestions.length - 1);
                        this.renderSuggestions();
                        break;
                    case 'ArrowUp':
                        e.preventDefault();
                        this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
                        this.renderSuggestions();
                        break;
                    case 'Enter':
                        e.preventDefault();
                        if (this.selectedIndex >= 0) {
                            callback(this.suggestions[this.selectedIndex]);
                            this.hide();
                        }
                        break;
                    case 'Escape':
                        this.hide();
                        break;
                }
            });

            // 点击其他地方关闭提示框
            document.addEventListener('click', (e) => {
                if (!this.element.contains(e.target) && e.target !== inputElement) {
                    this.hide();
                }
            });
        }

        getCaretCoordinates(element, position) {
            const div = document.createElement('div');
            const style = getComputedStyle(element);
            const properties = [
                'direction', 'boxSizing', 'width', 'height', 'overflowX', 'overflowY',
                'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
                'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
                'fontStyle', 'fontVariant', 'fontWeight', 'fontStretch', 'fontSize',
                'fontSizeAdjust', 'lineHeight', 'fontFamily', 'textAlign', 'textTransform',
                'textIndent', 'textDecoration', 'letterSpacing', 'wordSpacing'
            ];

            div.style.position = 'absolute';
            div.style.visibility = 'hidden';
            properties.forEach(prop => div.style[prop] = style[prop]);

            div.textContent = element.value.substring(0, position);
            const span = document.createElement('span');
            span.textContent = element.value.substring(position) || '.';
            div.appendChild(span);
            document.body.appendChild(div);

            const coordinates = {
                top: span.offsetTop,
                left: span.offsetLeft
            };

            document.body.removeChild(div);
            return coordinates;
        }
      }

      // 使用示例
      const suggestionBox = new SuggestionBox();

      Description.addEventListener('input', function(e) {
        const cursorPosition = this.selectionStart;
        const textBeforeCursor = this.value.substring(0, cursorPosition);
        let data = graph.save();
          data.nodes.forEach((node) => {
            if (node.id == id) {
              if(node.name.includes('Contextadd'))
              {
                Description.value
              }
              let Temp='' ;
              Temp+='Please ensure the output is in JSON format\n';
                  Temp+='{\n';
              node.Outputs.forEach((output,index) => {
                  if(output.Id == IdTemp)
                    output.Description = Description.value;
                  let Kind='';
                  if(output.Kind.includes('String'))
                    Kind='String';
                  else if(output.Kind=='Num')
                    Kind='Num';
                  else if(output.Kind=='Boolean')
                    Kind='Boolean';
                  Temp+='"'+output.Id+'"' + ':' + '"'+output.Description+'"' +'(you need output type:'+Kind+')'+ '\n';

              });
             Temp+='}\n';
              node.ExprotAfterPrompt = Temp;
              ChangeDatas(data);
            }
          });
        if (textBeforeCursor.endsWith('<@')) {
            suggestionBox.show(this, cursorPosition);
        } else if (!textBeforeCursor.endsWith('<')) {
            suggestionBox.hide();
        }
      });

      suggestionBox.attachEvents(Description, (selectedSuggestion) => {
        const cursorPosition = Description.selectionStart;
        const newValue = Description.value.substring(0, cursorPosition - 2) + 
                        selectedSuggestion + 
                        Description.value.substring(cursorPosition);
        Description.value = newValue;
        
        // 触发原有的数据处理逻辑
        let data = graph.save();
          data.nodes.forEach((node) => {
            if (node.id == id) {
              if(node.name.includes('Contextadd'))
              {
                Description.value
              }
              let Temp='' ;
              Temp+='Please ensure the output is in JSON format\n';
                  Temp+='{\n';
              node.Outputs.forEach((output,index) => {
                  if(output.Id == IdTemp)
                    output.Description = Description.value;
                  let Kind='';
                  if(output.Kind.includes('String'))
                    Kind='String';
                  else if(output.Kind=='Num')
                    Kind='Num';
                  else if(output.Kind=='Boolean')
                    Kind='Boolean';
                  Temp+='"'+output.Id+'"' + ':' + '"'+output.Description+'"' +'(you need output type:'+Kind+')'+ '\n';

              });
             Temp+='}\n';
              node.ExprotAfterPrompt = Temp;
              ChangeDatas(data);
            }
          });
      });
        JsonColumn.appendChild(outputContainer);
        outputColumn.appendChild(JsonColumn);
      }

      function CreatInputs(input,index,IdTemp)
      {
        const inputContainer = document.createElement('div');
        inputContainer.className = 'input-container';

        // 创建显示输入名称的输入框
        const inputName = document.createElement('input');
        inputName.value = input.name;
        inputContainer.appendChild(inputName);

        // 创建选择框
        const selectBox = document.createElement('select');
        const optionLink = document.createElement('option');
        optionLink.value = 'link';
        optionLink.text = 'Link';
        const optionLabel = document.createElement('option');
        optionLabel.value = 'Input';
        optionLabel.text = 'Input';
        selectBox.appendChild(optionLink);
        selectBox.appendChild(optionLabel);
        inputContainer.appendChild(selectBox);

        const Select1=document.createElement('select');
        const optionContext = document.createElement('option');
        optionContext.value = 'String';
        optionContext.text = 'String';
        const optionNum = document.createElement('option');
        optionNum.value = 'Num';
        optionNum.text = 'Num';
        const optionBool = document.createElement('option');
        optionBool.value = 'Boolean';
        optionBool.text = 'Boolean';
        const optionFilePath = document.createElement('option');
        optionFilePath.value = 'String_FilePath';
        optionFilePath.text = 'FilePath';
        Select1.appendChild(optionContext);
        Select1.appendChild(optionNum);
        Select1.appendChild(optionBool);
        Select1.appendChild(optionFilePath);
        let pathButton;
        //Select1选择input.Kind的值匹配
        Select1.selectedIndex = 2;
        inputContainer.appendChild(Select1);
        Select1.addEventListener('change', function() {
          let data = graph.save();
          data.nodes.forEach((node) => {
            if (node.id == id) {
              node.Inputs.forEach((input,index) => {
                if (input.Id == IdTemp) {
                  input.Kind = this.value;
                  if(this.value=='String_FilePath' && input.IsLabel==true)
                    {
                      // 创建路径按钮
                      pathButton = document.createElement('button');
                      pathButton.textContent = 'Selecte Path';
                      // 文件选择逻辑
                      pathButton.addEventListener('click', function () {
                        CreatFilePath(input.Id,id);

                      });
                      inputContainer.appendChild(pathButton);
                    }
                    else
                    {
                      if (pathButton && inputContainer.contains(pathButton)) {
                        inputContainer.removeChild(pathButton);
                        pathButton = null;
                      }                    
                    }
                }
                
              }
              );
            }
          }
          );
          ChangeDatas(data);
        });
        const SubNode = document.createElement('div');
        SubNode.className = 'column-SubNode'; // 使用之前定义的样式类
        SubNode.style.left = '400px'; // 设置与标签之间的间距
        SubNode.style.marginTop = '-2px'; // 设置上边距
        inputContainer.appendChild(SubNode);
        SubNode.onmousedown = function() {//删除这个矛点
          let data=graph.save();
          data.nodes.forEach((node) => {
            if(node.id == id)
            {
              //通过IdTemp删除这个矛点
              node.Inputs.forEach((input,index) => {
                  if(input.Id == IdTemp)
                  {
                    node.Inputs.splice(index,1);
                  }
                });
              const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
              node.anchorPoints = node.Inputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.05, anchorHeight / maxHeight]
                }).concat(node.Outputs.map((node, index) => {
                  const anchorHeight = 60 + index * 20;
                  return [0.95, anchorHeight / maxHeight]
                })).concat([[0, 0]]);
              ChangeDatas(data);

              //移除inputContainer
              inputContainer.parentNode.removeChild(inputContainer);
            }
          });
          RefreshEdge();

        }

        Select1.value = input.Kind;
        let labelTextarea = document.createElement('textarea'); // Declare variable externally for access in different scope
        // Append the textarea to the desired parent element
        document.body.appendChild(labelTextarea); // You can change the parent element to where you want to append the textarea
        if(input.IsLabel==true)
        {
          selectBox.value = 'Input';
          handleChange('Input');
        }
        // 处理选择框变化
        function handleChange(value) {
            // 如果之前添加了文本区域且现在选择是“Link”，则移除文本区域
            let data = graph.save();
            data.edges.forEach(edge => {
              if (edge.target==id && edge.targetAnchor==index) {
                const item = graph.findById(edge.id);
                const targetNode = graph.findById(edge.target);
                const targetAnchor = targetNode.getContainer().find(ele => ele.get('anchorPointIdx') === edge.targetAnchor);
                targetAnchor.set('links', targetAnchor.get('links') + 1);
                ChangeLink(targetAnchor);
                graph.remove(item);
              }
            });
            if (labelTextarea && value === 'link') {
                inputContainer.removeChild(labelTextarea);
                if (pathButton && inputContainer.contains(pathButton)) {
                  inputContainer.removeChild(pathButton);
                  labelTextarea = null; // 确保引用被清除
                }
                ChangeAnchorValue(id, '', 'link',input.Id);
            } else if (value === 'Input') {
                // 如果当前选择是“Input”，则添加文本区域
                labelTextarea = document.createElement('textarea');
                if(input.Kind == 'Num')
                labelTextarea.value = input.Num;
                else if(input.Kind .includes('String'))
                labelTextarea.value = input.Context;
                if(input.Kind.includes('FilePath'))
                {
                  labelTextarea.style.width = '490px'; // 设置固定宽度
                }
                else
                {
                  labelTextarea.style.width = '550px'; // 设置固定宽度
                }
                labelTextarea.style.height = '50px'; // 初始高度
                let uniqueClass = `unique-textarea-${id}-${input.Id}`;
                labelTextarea.className = 'normalInput-textarea ' + uniqueClass; // 同时设置两个类名
                labelTextarea.id = uniqueClass; // 为文本区域添加唯一的id
                labelTextarea.classList.add(uniqueClass); // Add the unique class name to the textarea
                //labelTextarea.style.resize = 'none'; // 禁止用户手动调整大小
                ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id);
                labelTextarea.addEventListener('input', function() {
                let isOk = true; // 假定输入无效
                if(input.Kind == 'Num') {
                  if(labelTextarea.value.match(/^[0-9]+$/))
                  {
                    isOk = true; // 如果是，将isOk设置为true，表示输入有
                  }
                  else {
                    // 如果上述条件都不满足，则弹出提示窗口告知用户输入格式不正确
                    isOk = false;
                    alert("类型不符，您应该输入数字！");
                  }
                }
                if (labelTextarea.value.trim() === '') {
                    isOk = false; // 如果输入为空，则将isOk设置为false，表示输入无效
                    alert("输入不能为空！");
                }
                  if (isOk) {
                    ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id); // 假定 id 和 ChangeNodeLabel 已定义
                  }

              });
                labelTextarea.addEventListener('input', function() {
                  // 重置高度以计算新的高度
                  this.style.height = 'auto';
                
                  // 设置新的高度
                  this.style.height = `${this.scrollHeight}px`;
                });
                inputContainer.appendChild(labelTextarea);
                if(input.Kind.includes('FilePath'))
                {
                  // 创建路径按钮
                  pathButton = document.createElement('button');
                  pathButton.textContent = 'Selecte Path';
                  // 文件选择逻辑
                  
                  pathButton.addEventListener('click', function () {
                    CreatFilePath(input.Id,id);

                  });
                  inputContainer.appendChild(pathButton);
                }
            }
        }
        selectBox.addEventListener('change', function() {
          handleChange(this.value);
        });
        Select1.addEventListener('change', function() {

        });
        // 为输入框添加 blur 监听器
        inputName.addEventListener('input', function() {
            ChangeAnchorLabel(id, inputName.value, index,input.Id,true); // 假定 id 和 ChangeNodeLabel 已定义
        });

        inputColumn.appendChild(inputContainer);
        RefreshEdge();
      }
      // 假设Inputs是已定义的
    Inputs.forEach((input, index) => {
        CreatInputs(input,index,input.Id);
    });
    Outputs.forEach((output, index) => {
        CreatOutputs(output,index,output.Id);
    });

    }
    else if(NodeKind=='IfNode')
    {
        const inputColumn = document.createElement('div');
          inputColumn.className = 'column';
          const inputLabel = document.createElement('div');
          inputLabel.textContent = 'Input'; // 设置文本
          inputLabel.className = 'column-label'; // 设置样式类
          inputColumn.appendChild(inputLabel);
          const addNode = document.createElement('div');
          addNode.className = 'column-AddNode'; // 使用之前定义的样式类
          vessel.appendChild(inputColumn);
          // 调整textarea高度以适应内容

          // 输入框空格键增长逻辑
          let IdTemp='';
          addNode.onmousedown = function() {
              let data=graph.save();
              data.nodes.forEach((node) => {
                if(node.id == id)
                {
                    IdTemp='Input' + (node.Inputs.length + 1).toString();
                    let TempName = 'Input' + (node.Inputs.length + 1).toString();
                    let counter = 1; // 新增一个计数器
                    // 检查是否重名，如果重名则+1继续检查
                    while (node.Inputs.some(input => input.name === TempName)) {
                        TempName = 'Input' + (node.Inputs.length + 1 + counter).toString(); // 使用计数器调整名称
                        counter++; // 每次循环递增计数器
                    }
                    node.Inputs.push({
                      'Num': null,
                      'Kind': 'String',
                      'Id': IdTemp,
                      'Context': null,
                      'Isnecessary': false,
                      'name': TempName,
                      'Link': 0,
                      'IsLabel': false,
                  });
                  const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
                  node.anchorPoints = node.Inputs.map((node, index) => {
                      const anchorHeight = 60 + index * 20;
                      return [0.05, anchorHeight / maxHeight]
                    }).concat(node.Outputs.map((node, index) => {
                      const anchorHeight = 60 + index * 20;
                      return [0.95, anchorHeight / maxHeight]
                    })).concat([[0, 0]]);
                  CreatInputs(node.Inputs[node.Inputs.length - 1],node.Inputs.length - 1,IdTemp);
                  ChangeDatas(data);
                }
              });

              RefreshEdge();

            };
          //等比例扩大addNode

          // 确定插入位置并将AddNode插入到inputColumn中
          const nextElement = inputLabel.nextSibling; // 获取inputLabel之后的元素
          if (nextElement) {
              // 如果inputLabel后面有其他元素，则在这个元素之前插入addNode
              inputColumn.insertBefore(addNode, nextElement);
          } else {
              // 如果inputLabel是最后一个元素或inputColumn没有其他子元素，则直接追加
              inputColumn.appendChild(addNode);
          }
        const outputColumn = document.createElement('div');
        outputColumn.className = 'column';
        const addNode1 = document.createElement('div');
        addNode1.className = 'column-AddNode'; // 使用之前定义的样式类
        addNode1.style.left = '60px'; // 设置左边距
        outputColumn.appendChild(addNode1);
        const outputLabel = document.createElement('div');
        outputLabel.textContent = 'Output'; // 设置文本
        outputLabel.className = 'column-label'; // 设置样式类
        outputColumn.appendChild(outputLabel);
        // 将输入和输出列添加到节点容器中
        addNode1.onmousedown = function() {
          let data=graph.save();
          data.nodes.forEach((node) => {
            if(node.id == id)
            {
              IdTemp='Output' + (node.Outputs.length + 1).toString();
              let TempName = 'Output' + (node.Outputs.length + 1).toString();
              let counter = 1; // 新增一个计数器
              // 检查是否重名，如果重名则+1继续检查
              while (node.Outputs.some(output => output.name === TempName)) {
                  TempName = 'Output' + (node.Outputs.length + 1 + counter).toString(); // 使用计数器调整名称
                  counter++; // 每次循环递增计数器
              }
              node.Outputs.push({
                'Num': 0,
                'Kind': 'Trigger',
                'Id': IdTemp,
                'Context': '',
                'Boolean': false,
                'Isnecessary': true,
                'name': TempName,
                'Link': 0,
                'IsLabel': false,
            });
            const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
            node.anchorPoints = node.Inputs.map((node, index) => {
                const anchorHeight = 60 + index * 20;
                return [0.05, anchorHeight / maxHeight]
              }).concat(node.Outputs.map((node, index) => {
                const anchorHeight = 60 + index * 20;
                return [0.95, anchorHeight / maxHeight]
              })).concat([[0, 0]]);
            CreatOutputs(node.Outputs[node.Outputs.length - 1],node.Outputs.length - 1,IdTemp);
            ChangeDatas(data);
            }
          });

          RefreshEdge();
        };
        vessel.appendChild(outputColumn);
        // 添加元素到 DOM
        function CreatOutputs(output, index,IdTemp) {
          const outputContainer = document.createElement('div');
          outputContainer.className = 'output-container';
          outputContainer.style.display = 'flex';
          outputContainer.style.alignItems = 'flex-start'; // Content aligned at top
          outputContainer.style.flexWrap = 'wrap'; // Allow child elements to wrap
          outputContainer.style.marginBottom = '10px'; // Increase line spacing
          outputContainer.style.maxHeight = '300px'; // Set maximum height
          outputContainer.style.overflowY = 'auto'; // Add vertical scrollbar when needed


          // Create an input box to display the output name
          const outputName = document.createElement('input');
          outputName.value = output.name;
          outputName.style.width = '100px'; // 设置固定宽度
          outputName.style.marginBottom = '5px'; // 增加10px的下边距，增加行距
          outputContainer.appendChild(outputName);
          outputName.addEventListener('input', function() {
            ChangeAnchorLabel(id, outputName.value, index,IdTemp,false); // 假定 id 和 ChangeNodeLabel 已定义
          })
          // 添加一个宽度为100%的透明div来强制换行
         
          const TriggerKindSelectLabel = document.createElement('label');
          TriggerKindSelectLabel.textContent = '递归逻辑'; // 设置文本
          TriggerKindSelectLabel.style.marginRight = '10px'; // 设置右边距
          //颜色白色加粗
          TriggerKindSelectLabel.style.color = 'white';
          TriggerKindSelectLabel.style.marginBottom = '5px'; // 增加10px的下边距，增加行距
          outputContainer.appendChild(TriggerKindSelectLabel);
          const TriggerKindSelect = document.createElement('select');
          TriggerKindSelect.style.width = '100px'; // 设置宽度为100px
          TriggerKindSelect.style.marginBottom = '5px'; // 增加10px的下边距，增加行距
          const option1 = document.createElement('option');
          option1.value = 'STOP';
          option1.text = 'STOP';
          const option2 = document.createElement('option');
          option2.value = 'SKIP';
          option2.text = 'SKIP';
          TriggerKindSelect.appendChild(option1);
          TriggerKindSelect.appendChild(option2);
          TriggerKindSelect.value = output.TriggerKind || 'STOP';
          if(output.TriggerKind != 'STOP')
          {
            output.TriggerKind = 'STOP';
            let data = graph.save();
            data.nodes.forEach((node) => {
              if (node.id == id) {
                node.Outputs.forEach((output,index) => {
                    if (output.Id == IdTemp) {
                      output.TriggerKind = 'STOP';
                    }
                  }
                );
              }
            })
            ChangeDatas(data);
            RefreshEdge();
          }
          TriggerKindSelect.addEventListener('change', function() {
            let data = graph.save();
            data.nodes.forEach((node) => {
              if (node.id == id) {
                node.Outputs.forEach((output,index) => {
                    if (output.Id == IdTemp) {
                      output.TriggerKind = this.value;
                    }
                  }
                );
              }
            })
            ChangeDatas(data);
            RefreshEdge();
          })
          outputContainer.appendChild(TriggerKindSelect);

          const newLineDiv = document.createElement('div');
          newLineDiv.style.width = '100%'; // 设置宽度为100%
          newLineDiv.style.height = '0'; // 高度设置为0，使其不影响视觉效果
          outputContainer.appendChild(newLineDiv);

          creatSubNode();

          function creatSubNode()
          {
            const SubNode = document.createElement('div');
            SubNode.className = 'column-SubNode'; // 使用之前定义的样式类
            SubNode.style.right = '230px'; // 设置与 Description 之间的间距
            outputContainer.appendChild(SubNode);
            SubNode.onmousedown = function() {//删除这个矛点
              let data=graph.save();
              data.nodes.forEach((node) => {
                if(node.id == id)
                {
                  //通过IdTemp删除这个矛点
                  node.Outputs.forEach((output,index) => {
                      if(output.Id == IdTemp)
                      {
                        node.Outputs.splice(index,1);
                      }
                    }
                  );
                  const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
                  node.anchorPoints = node.Inputs.map((node, index) => {
                      const anchorHeight = 60 + index * 20;
                      return [0.05, anchorHeight / maxHeight]
                    }).concat(node.Outputs.map((node, index) => {
                      const anchorHeight = 60 + index * 20;
                      return [0.95, anchorHeight / maxHeight]
                    })).concat([[0, 0]]);
                  ChangeDatas(data);
                  //移除outputContainer
                  outputContainer.parentNode.removeChild(outputContainer);
                }
              });
              RefreshEdge();
            }
          }
          initLogicContainer(outputContainer, output);
          /* ===================== 初始化 LogicContainer ===================== */
          function initLogicContainer(outputContainer, tempoutput) {
            /* ---------- 初始化数据字段 ---------- */
            if (outputContainer.querySelector('.logic-container')) return;

            tempoutput.IfLogicSubjectArray = tempoutput.IfLogicSubjectArray || [];
            tempoutput.IfLogicContentArray = tempoutput.IfLogicContentArray || [];
            tempoutput.IfLogicKind         = tempoutput.IfLogicKind || 'And';

            /* ---------- DOM ---------- */
            const logicContainer = document.createElement('div');
            logicContainer.className = 'logic-container';

            /* 左侧全局 And / Or 开关 */
            const toggleBtn = document.createElement('div');
            toggleBtn.className = 'logic-toggle';
            toggleBtn.textContent = tempoutput.IfLogicKind;
            toggleBtn.onclick = () => {
              tempoutput.IfLogicKind = tempoutput.IfLogicKind === 'And' ? 'Or' : 'And';
              toggleBtn.textContent  = tempoutput.IfLogicKind;
            };
            logicContainer.appendChild(toggleBtn);

            /* 右侧主体 */
            const body = document.createElement('div');
            body.className = 'logic-body';
            logicContainer.appendChild(body);

            /* 底部新增按钮 */
            const createBtn = document.createElement('button');
            createBtn.className = 'create-logic-row';
            createBtn.textContent = '新增判定条件';
            createBtn.onclick = () => {
              tempoutput.IfLogicSubjectArray.push('');
              tempoutput.IfLogicContentArray.push('');
              addLogicRow(body, tempoutput, tempoutput.IfLogicSubjectArray.length - 1);
            };
            body.appendChild(createBtn);

            /* 插入到 outputContainer */
            outputContainer.appendChild(logicContainer);

            /* 先渲染已存在的行 */
            for (let i = 0; i < tempoutput.IfLogicSubjectArray.length; i++) {
              addLogicRow(body, tempoutput, i);
            }
          }

          /* ===================== 新增一行 ===================== */
          function addLogicRow(body, tempoutput, rowIndex) {
            const row = document.createElement('div');
            row.className = 'logic-row';

            /* ---------- 匹配类 ---------- */
            const subject = document.createElement('select');
            populateSubject(subject, Inputs);

            if (tempoutput.IfLogicSubjectArray[rowIndex] != null) {
              subject.value = tempoutput.IfLogicSubjectArray[rowIndex];
            } else {
              tempoutput.IfLogicSubjectArray[rowIndex] = subject.value;
            }
            row.appendChild(subject);

            /* ---------- 判定条件 ---------- */
            const condition = document.createElement('select');
            populateCondition(condition, Inputs, subject.value);
            // Check if tempoutput and tempoutput.IfLogicConditionArray exist before accessing an index
            if (tempoutput && tempoutput.IfLogicConditionArray && tempoutput.IfLogicConditionArray[rowIndex] != undefined) {
                condition.value = tempoutput.IfLogicConditionArray[rowIndex] || '';
            }
            condition.onchange = () => {
              if (!Array.isArray(tempoutput.IfLogicConditionArray)) {
                tempoutput.IfLogicConditionArray = [];
              }
              tempoutput.IfLogicConditionArray[rowIndex] = condition.value;
              
            };
            row.appendChild(condition);

            /* ---------- 判定内容 ---------- */
            const content = document.createElement('input');
            content.type        = 'text';
            content.placeholder = '判定内容';

            if (tempoutput.IfLogicContentArray[rowIndex] != null) {
              content.value = tempoutput.IfLogicContentArray[rowIndex];
            }

            subject.onchange = () => {
              tempoutput.IfLogicSubjectArray[rowIndex] = subject.value;
              populateCondition(condition, Inputs, subject.value);

              content.style.display =
                condition.value.includes('true') || condition.value.includes('false')
                  ? 'none'
                  : 'block';
            };

            content.addEventListener('input', () => {
              tempoutput.IfLogicContentArray[rowIndex] = content.value;
            });
            row.appendChild(content);

            /* 根据条件类型决定是否显示内容输入框 */
            content.style.display =
              condition.value.includes('true') || condition.value.includes('false')
                ? 'none'
                : 'block';

            /* ---------- 删除按钮 ---------- */
            const remove = document.createElement('button');
            remove.className = 'remove-row';
            remove.textContent = '✖';
            remove.onclick = () => {
              const rows = Array.from(body.querySelectorAll('.logic-row'));
              const idx  = rows.indexOf(row);

              body.removeChild(row);
              content.__destroyQuick && content.__destroyQuick();

              if (idx > -1) {
                tempoutput.IfLogicSubjectArray.splice(idx, 1);
                tempoutput.IfLogicContentArray.splice(idx, 1);
              }
            };
            row.appendChild(remove);

            /* 插在“新增”按钮之前，保持按钮永远在底部 */
            body.insertBefore(row, body.querySelector('.create-logic-row'));
          }

          /* ===================== 工具函数 ===================== */
          function populateSubject(select, Inputs) {
            /* 清空现有选项 */
            select.innerHTML = '';

            /* 遍历 Inputs，把 name 写入下拉框 */
            const added = new Set();
            Inputs.forEach(inp => {
              const col = inp?.name?.trim();
              if (col && !added.has(col)) {
                added.add(col);
                const opt = document.createElement('option');
                opt.value = col;
                opt.textContent = col;
                select.appendChild(opt);
              }
            });
          }

          function populateCondition(select, Inputs, subject) {
            /* 先清空 */
            select.innerHTML = '';
            for (const inp of Inputs) {
              if (inp.name !== subject) continue;

              if (inp.Kind === 'Boolean') {
                ['true', 'false'].forEach(v => {
                  const opt = document.createElement('option');
                  opt.value = v;
                  opt.text  = v;
                  select.appendChild(opt);
                });
              } else if (inp.Kind === 'Num') {
                ['>', '<', '==', '>=', '<=', '!='].forEach(v => {
                  const opt = document.createElement('option');
                  opt.value = v;
                  opt.text  = v;
                  select.appendChild(opt);
                });
              } else if (inp.Kind.includes('String')) {
                ['exclude', 'include', 'empty', 'no empty'].forEach(v => {
                  const opt = document.createElement('option');
                  opt.value = v;
                  opt.text  = v.charAt(0).toUpperCase() + v.slice(1);
                  select.appendChild(opt);
                });
              }
            }
          }

          // Add description label


          outputColumn.appendChild(outputContainer);
        }

        function CreatInputs(input,index,IdTemp)
        {
          const inputContainer = document.createElement('div');
          inputContainer.className = 'input-container';

          // 创建显示输入名称的输入框
          const inputName = document.createElement('input');
          inputName.value = input.name;
          inputContainer.appendChild(inputName);

          // 创建选择框
          const selectBox = document.createElement('select');
          const optionLink = document.createElement('option');
          optionLink.value = 'link';
          optionLink.text = 'Link';
          const optionLabel = document.createElement('option');
          optionLabel.value = 'Input';
          optionLabel.text = 'Input';
          selectBox.appendChild(optionLink);
          selectBox.appendChild(optionLabel);
          inputContainer.appendChild(selectBox);

          const Select1=document.createElement('select');
          const optionContext = document.createElement('option');
          optionContext.value = 'String';
          optionContext.text = 'String';
          const optionNum = document.createElement('option');
          optionNum.value = 'Num';
          optionNum.text = 'Num';
          const optionBool = document.createElement('option');
          optionBool.value = 'Boolean';
          optionBool.text = 'Boolean';
          Select1.appendChild(optionContext);
          Select1.appendChild(optionNum);
          Select1.appendChild(optionBool);
          //Select1选择input.Kind的值匹配
          Select1.selectedIndex = 2;
          inputContainer.appendChild(Select1);
          function RefreshOutput() {
            // 确保outputColumn是已定义的，并且开始清理操作
            if (outputColumn) {
                // 获取所有子元素
                let children = outputColumn.children;
                // 从后往前遍历子元素，以便安全删除元素
                for (let i = children.length - 1; i >= 0; i--) {
                    // 假设我们用className来识别是否是addNode1
                    if (children[i].className !== 'column-AddNode' && children[i].className !== 'column-label') {
                        outputColumn.removeChild(children[i]); // 删除不是addNode1的元素
                    }
                }
            }

            // 这里添加Outputs中的addNode1元素，或其他处理逻辑
            Outputs.forEach((output, index) => {
                // 检查是否是我们需要添加的特定节点addNode1
                  CreatOutputs(output, index, output.Id);
            });
        }


        // 假设Outputs是全局变量，如果不是，需要确保它在这个函数中是可访问的

          Select1.addEventListener('change', function() {
            let data = graph.save();
            data.nodes.forEach((node) => {
              if (node.id == id) {
                node.Inputs.forEach((input,index) => {
                  if (input.Id == IdTemp) {
                    input.Kind = this.value;
                    RefreshOutput();
                  }
                }
                );
              }
            }
            );
            ChangeDatas(data);
          }
          );
          const SubNode = document.createElement('div');
          SubNode.className = 'column-SubNode'; // 使用之前定义的样式类
          SubNode.style.left = '310px'; // 设置与标签之间的间距
          inputContainer.appendChild(SubNode);
          SubNode.onmousedown = function() {//删除这个矛点
            let data=graph.save();
            data.nodes.forEach((node) => {
              if(node.id == id)
              {
                //通过IdTemp删除这个矛点
                node.Inputs.forEach((input,index) => {
                    if(input.Id == IdTemp)
                    {
                      node.Inputs.splice(index,1);
                      RefreshOutput();
                    }
                  }
                );
                const maxHeight = Math.max(node.Inputs.length, node.Outputs.length) * 20 + 60
                node.anchorPoints = node.Inputs.map((node, index) => {
                    const anchorHeight = 60 + index * 20;
                    return [0.05, anchorHeight / maxHeight]
                  }).concat(node.Outputs.map((node, index) => {
                    const anchorHeight = 60 + index * 20;
                    return [0.95, anchorHeight / maxHeight]
                  })).concat([[0, 0]]);
                ChangeDatas(data);
                //移除inputContainer
                inputContainer.parentNode.removeChild(inputContainer);
              }
            });
            RefreshEdge();
          }

          Select1.value = input.Kind;
          let labelTextarea = document.createElement('textarea'); // 在外部声明变量以便在不同的作用域中访问
          labelTextarea.className = 'normalInput-textarea';
          if(input.IsLabel==true)
          {
            selectBox.value = 'Input';
            handleChange('Input');
          }
          // 处理选择框变化
          function handleChange(value) {
              // 如果之前添加了文本区域且现在选择是“Link”，则移除文本区域
              let data = graph.save();
              data.edges.forEach(edge => {
                if (edge.target==id && edge.targetAnchor==index) {
                  const item = graph.findById(edge.id);
                  const targetNode = graph.findById(edge.target);
                  const targetAnchor = targetNode.getContainer().find(ele => ele.get('anchorPointIdx') === anchorIndex);
                  targetAnchor.set('links', targetAnchor.get('links') + 1);
                  ChangeLink(targetAnchor);
                  graph.remove(item);
                }
              });
              if (labelTextarea && value === 'link') {
                  inputContainer.removeChild(labelTextarea);
                  labelTextarea = null; // 确保引用被清除
                  ChangeAnchorValue(id, '', 'link',input.Id);
              } else if (value === 'Input') {
                  // 如果当前选择是“Input”，则添加文本区域
                  labelTextarea = document.createElement('textarea'); // 在外部声明变量以便在不同的作用域中访问
                  labelTextarea.className = 'normalInput-textarea';
                  if(input.Kind == 'Num')
                  labelTextarea.value = input.Num;
                  else if(input.Kind .includes('String'))
                  labelTextarea.value = input.Context;
                  labelTextarea.style.width = '550px'; // 设置固定宽度
                  labelTextarea.style.height = '50px'; // 初始高度
                  let uniqueClass = `unique-textarea-${id}-${input.Id}`;
                  labelTextarea.className = 'normalInput-textarea ' + uniqueClass; // 同时设置两个类名
                  labelTextarea.id = uniqueClass;
                  labelTextarea.classList.add(uniqueClass); // 为文本区域添加唯一类名
                  //labelTextarea.style.resize = 'none'; // 禁止用户手动调整大小
                  labelTextarea.addEventListener('input', function() {
                  let isOk = true; // 假定输入无效
                  if(input.Kind == 'Num') {
                    if(labelTextarea.value.match(/^[0-9]+$/))
                    {
                      isOk = true; // 如果是，将isOk设置为true，表示输入有
                    }
                    else {
                      // 如果上述条件都不满足，则弹出提示窗口告知用户输入格式不正确
                      isOk = false;
                      alert("类型不符，您应该输入数字！");
                    }
                  }
                  if (labelTextarea.value.trim() === '') {
                      isOk = false; // 如果输入为空，则将isOk设置为false，表示输入无效
                      alert("输入不能为空！");
                  }
                    if (isOk) {
                      ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id); // 假定 id 和 ChangeNodeLabel 已定义
                    }

                });
                  labelTextarea.addEventListener('input', function() {
                    // 重置高度以计算新的高度
                    this.style.height = 'auto';
                  
                    // 设置新的高度
                    this.style.height = `${this.scrollHeight}px`;
                  });
                  inputContainer.appendChild(labelTextarea);
              }
          }
          selectBox.addEventListener('change', function() {
            handleChange(this.value);
          });
          Select1.addEventListener('change', function() {

          });
          // 为输入框添加 blur 监听器
          inputName.addEventListener('input', function() {
              ChangeAnchorLabel(id, inputName.value, index,input.Id,true); // 假定 id 和 ChangeNodeLabel 已定义
          });
          RefreshEdge();
          inputColumn.appendChild(inputContainer);
        }
        // 假设Inputs是已定义的
      Inputs.forEach((input, index) => {
          CreatInputs(input,index,input.Id);
      });
      Outputs.forEach((output, index) => {
          CreatOutputs(output,index,output.Id);
      });
    }

    document.getElementById('graph-container').appendChild(domElement);
    domBlocks.push({ id: `dom-${id}`, element: domElement, Item });
  }
  initializeDragAndResize(domElement,300,400);
  // 更新 DOM 元素的内容和位置（不包括已经移除的元素）
  //if (domElement && domElement.parentNode) {
    //domElement.innerHTML += id; // 显示元素的 id，注意不要覆盖 closeButton
    //domElement.style.left = `${x}px`;
    //domElement.style.top = `${y+200}px`;
  //}
  }
  function autoResizeTextarea(textarea) {
    textarea.style.height = 'auto';  // 重置高度，允许它根据内容缩小
    textarea.style.height = textarea.scrollHeight + 'px';  // 设置高度等于滚动高度，以适应所有内容
}
function resizeTextarea(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = textarea.scrollHeight + 'px';
}

function generateIOHtml(items, isInput = true) {
  const title = isInput ? 'Inputs' : 'Outputs';
  let html = `<h3 class="io-title">${title}</h3>`;
  
  items.forEach((item, index) => {
      let value = '';
      if (item.Kind === 'Num') {
          value = item.Num;
      } else if (item.Kind.includes('String')) {
          value = item.Context;
      } else if (item.Kind === 'Boolean' || item.Kind === 'Trigger') {
          value = item[item.Kind] ? 'true' : 'false';
      }
      
      const readOnly = !isInput ? 'readonly' : '';
      const dataAttrs = isInput ? `data-index="${index}" data-kind="${item.Kind}"` : '';
      const className = isInput ? 'input-textarea' : 'output-textarea';
      
      html += `
          <div class="io-container">
              <label class="io-label">${item.name}:</label>
              <textarea 
                  class="${className}"
                  ${readOnly}
                  ${dataAttrs}
                  oninput="resizeTextarea(this)"
              >${value}</textarea>
          </div>`;
  });
  return html;
}

// 全局变量，跟踪全屏状态
let isFullScreen = false;

// 创建侧边窗口函数
function createSideWindow(item, isCheckMode = false) {
  // 获取节点数据
  const node = isCheckMode
      ? TempMessageNode.nodes.find(n => n.id === item.id)
      : graph.save().nodes.find(n => n.id === item.id);

  const tempNode = (!isCheckMode && TempMessageNode?.nodes)
      ? TempMessageNode.nodes.find(n => n.id === item.id)
      : node;

  if (!node) {
      console.error('未找到节点数据');
      return;
  }

  const contentArea = document.getElementById('content-area');
  if (!contentArea) return;
  contentArea.innerHTML = '';

  // 生成 Token 信息（如果有）
  let tokenInfo = '';
  if (tempNode.Outputs?.[0]) {
      const output = tempNode.Outputs[0];
      if (
          typeof output.prompt_tokens !== 'undefined' &&
          typeof output.completion_tokens !== 'undefined' &&
          typeof output.total_tokens !== 'undefined'
      ) {
          tokenInfo = `
              <div class="token-info">
                  <div class="token-item">
                      <span>Prompt Tokens:</span> ${output.prompt_tokens}
                  </div>
                  <div class="token-item">
                      <span>Completion Tokens:</span> ${output.completion_tokens}
                  </div>
                  <div class="token-item">
                      <span>Total Tokens:</span> ${output.total_tokens}
                  </div>
              </div>
          `;
      }
  }

  // 生成输入区域 HTML
  let inputsHtml = `
  <div class="section-container">
      <h3>Inputs</h3>
  `;
  node.Inputs.forEach((input, index) => {
  let value = '';
  if (input.Kind === 'Num') {
      value = input.Num ?? '';
  } else if (input.Kind.includes('String')) {
      value = input.Context ?? '';
  } else if (input.Kind === 'Boolean') {
      value = input.Boolean ? 'true' : 'false';
  }

  inputsHtml += `
      <div class="input-item">
          <label><strong>${input.name}:</strong></label>
          <textarea 
              class="side-window-input-textarea"
              data-index="${index}"
              data-kind="${input.Kind}"
              ${isCheckMode ? 'readonly' : ''}
          >${value}</textarea>
      </div>
  `;
  });
  inputsHtml += '</div>';

  // 生成 Prompt 区域（如果是 LLM 节点）
  let promptHtml = '';
  if (node.NodeKind && node.NodeKind.includes('LLm')) {
      const promptValue = node.prompt ?? '';
      const systemPromptValue = node.SystemPrompt?? '';
      promptHtml = `
      <!-- SystemPrompt 区块 -->
      <div class="section-container">
          <h3>SystemPrompt</h3>
          <div class="prompt-wrapper">
              <textarea
                  id="systemPrompt"
                  class="side-window-textarea"
                  ${isCheckMode ? 'readonly' : ''}
              >${systemPromptValue}</textarea>
          </div>
      </div>

      <!-- UserPrompt 区块 -->
      <div class="section-container">
          <h3>UserPrompt</h3>
          <div class="prompt-wrapper">
              <textarea
                  id="prompt"
                  class="side-window-textarea"
                  ${isCheckMode ? 'readonly' : ''}
              >${promptValue}</textarea>
          </div>
      </div>
    `;

  }

  // 生成输出区域 HTML
  let outputsHtml = `
      <div class="section-container">
          <h3>Outputs</h3>
  `;
  tempNode.Outputs.forEach((output, index) => {
      let value = '';
      if (output.Kind === 'Num') {
          value = output.Num ?? '';
      } else if (output.Kind.includes('String')) {
          value = output.Context ?? '';
      } else if (output.Kind === 'Boolean' || output.Kind === 'Trigger') {
          value = output.Boolean ? 'true' : 'false';
      }

      outputsHtml += `
          <div class="output-item">
              <label><strong>${output.name}:</strong></label>
              <textarea class="side-window-textarea" readonly>${value}</textarea>
          </div>
      `;
  });
  outputsHtml += '</div>';
  //创建一个debug区域
  let debugHtml = `
  <div class="section-container">
      <h3>Debug</h3>
      <div class="debug-wrapper">
          <textarea class="side-window-textarea" readonly>${node.debug}</textarea>
      </div>
  </div>`;  
  // 组合所有 HTML 内容
  contentArea.innerHTML = tokenInfo + inputsHtml + promptHtml + outputsHtml + debugHtml ;

  // 显示侧边窗口
  const sideWindow = document.getElementById('side-window');
  sideWindow.style.display = 'block';

  // 调整所有 textarea 的高度
  document.querySelectorAll('#content-area textarea').forEach(resizeTextarea);

  // 设置按钮和状态显示
  const runButton = document.getElementById('run-button');
  runButton.style.display = isCheckMode ? 'none' : 'block';

  const resultIndicator = document.getElementById('result-indicator');
  const resultMessage = document.getElementById('result-message');

  if (isCheckMode) {
    let Tempnodes =graph.save().nodes;
    let tempNode = Tempnodes.find(n => n.id === item.id);
    const loadingIndicator = document.getElementById('loading-indicator');
    const resultIndicator = document.getElementById('result-indicator');
    if (tempNode.isFinish == false) {
        // 未完成时显示待运行
        
        if(tempNode.IsRunning == true)
        {
          if(tempNode.IsError == false)
          {
            loadingIndicator.style.display = 'block';
            resultIndicator.style.display = 'none';
            resultMessage.textContent = '';
          }
          else
          {
            resultMessage.textContent = tempNode.ErrorContext;
            resultMessage.style.color = 'red';
            resultIndicator.style.display = 'block';
          }
          
        }
        else
        {
          resultMessage.textContent = '待运行';
          resultMessage.style.color = 'orange';
          resultIndicator.style.display = 'block';
          loadingIndicator.style.display = 'none';
        }
        
    } else {
        // 已完成时再判断是否有错误
        const isError = node.IsError;
        resultMessage.textContent = isError ? node.ErrorContext : '已完成';
        resultMessage.style.color = isError ? 'red' : 'green';
        resultIndicator.style.display = 'block';
        loadingIndicator.style.display = 'none';

    }
} else {
    resultIndicator.style.display = 'none';
    setupRunButton(node);
}


  // 设置关闭按钮
  document.getElementById('close-button').onclick = () => {
      sideWindow.style.display = 'none';
      if (!isCheckMode && runButton._clickHandler) {
          runButton.removeEventListener('click', runButton._clickHandler);
      }
  };

 const maximizeButton = document.getElementById('maximize-button');
let isFullScreen = false;

maximizeButton.onclick = () => {
    const sideWindowElement = document.querySelector('.side-window');
    const sideWindowinputElements = document.querySelectorAll('.side-window-input-textarea');
    const sideWindowtextareaElements = document.querySelectorAll('.side-window-textarea');
    
    if (!isFullScreen) {
        sideWindowElement.style.transition = 'all 0.3s ease-in-out';
        sideWindowElement.classList.add('fullscreen');
        isFullScreen = true;
        maximizeButton.textContent = '⛶'; // 切换到缩小图标
    } else {
        sideWindowElement.style.transition = 'all 0.3s ease-in-out';
        sideWindowElement.classList.remove('fullscreen');
        isFullScreen = false;
        maximizeButton.textContent = '⛶'; // 切换到放大图标
    }

    // 等待过渡动画完成后调整所有textarea的高度
    setTimeout(() => {
        // 调整所有textarea的高度
        sideWindowinputElements.forEach(textarea => {
            autoResizeTextarea(textarea);
        });
        
        sideWindowtextareaElements.forEach(textarea => {
            autoResizeTextarea(textarea);
        });
    }, 300);
};

// 添加自动调整高度的函数
function autoResizeTextarea(textarea) {
    // 重置高度以获取正确的scrollHeight
    textarea.style.height = 'auto';
    // 设置新的高度
    textarea.style.height = textarea.scrollHeight + 'px';
}
initializeTextareaListeners()
// 为所有textarea添加输入事件监听器，实时调整高度
function initializeTextareaListeners() {
    const allTextareas = document.querySelectorAll('.side-window-input-textarea, .side-window-textarea');
    
    allTextareas.forEach(textarea => {
        // 初始调整
        autoResizeTextarea(textarea);
        
        // 添加输入事件监听器
        textarea.addEventListener('input', () => {
            autoResizeTextarea(textarea);
        });
    });
}
}

// 设置运行按钮函数
function setupRunButton(node) {
  const runButton = document.getElementById('run-button');

  // 移除先前的事件监听器
  if (runButton._clickHandler) {
      runButton.removeEventListener('click', runButton._clickHandler);
  }

  const handler = async () => {
      try {
          // 显示加载指示器
          const loadingIndicator = document.getElementById('loading-indicator');
          const resultIndicator = document.getElementById('result-indicator');
          const resultMessage = document.getElementById('result-message');
          loadingIndicator.style.display = 'block';
          resultIndicator.style.display = 'none';

          // 收集输入数据并更新 node.Inputs
          document.querySelectorAll('.side-window-input-textarea').forEach(textarea => {
              const index = parseInt(textarea.dataset.index, 10);
              const value = textarea.value.trim();
              const input = node.Inputs[index];

              if (input.Kind === 'Num') {
                  const numValue = parseFloat(value);
                  input.Num = numValue;
              } else if (input.Kind.includes('String')) {
                  input.Context = value;
              } else if (input.Kind === 'Boolean') {
                  input.Boolean = value.toLowerCase() === 'true';
              }
          });

          // 创建 inputs 对象，用于发送到后端
          const inputs = node.Inputs.reduce((acc, input, index) => {
              if (input.Kind === 'Num') {
                  acc[index] = input.Num;
              } else if (input.Kind.includes('String')) {
                  acc[index] = input.Context;
              } else if (input.Kind === 'Boolean') {
                  acc[index] = input.Boolean;
              }
              return acc;
          }, {});

          // 如果是 LLM 节点，处理 prompt
          if (node.NodeKind.includes('LLm')) {
              const promptElement = document.getElementById('prompt');
              if (promptElement) {
                  node.ExportPrompt = promptElement.value;

                  // 处理 prompt，替换占位符
                  const [systemPrompt, exportPrompt,ExprotAfterPrompt] = processLLmPrompt(node);
                  node.SystemPrompt = systemPrompt;
                  node.ExportPrompt = exportPrompt;
                  node.ExprotAfterPrompt = ExprotAfterPrompt;
              }
          }

          // 发送请求到后端
          const response = await fetch('/run-node', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                  name: node.name,
                  node: node,
                  prompt: node.ExportPrompt,
                  inputs: inputs, // 确保这里的 inputs 已经定义
                  outputs: node.Outputs
              })
          });

          // 解析响应数据
          const data = await response.json();
          if (!response.ok) {
              resultMessage.textContent = '后端服务响应错误: ' + (data.trace || '未知错误');
              resultMessage.style.color = 'red';
              resultIndicator.style.display = 'block';
              throw new Error('后端服务响应错误', data);
          }

          // 更新输出显示，包括 Token 信息
          updateOutputs(data.output,data.debug,node.id);

          // 显示成功消息
          resultMessage.textContent = '已完成';
          resultMessage.style.color = 'green';
          resultIndicator.style.display = 'block';

      } catch (error) {
          console.error('运行错误:', error);
          const resultMessage = document.getElementById('result-message');
          resultMessage.textContent = error.message;
          resultMessage.style.color = 'red';
          const resultIndicator = document.getElementById('result-indicator');
          resultIndicator.style.display = 'block';
      } finally {
          // 隐藏加载指示器
          const loadingIndicator = document.getElementById('loading-indicator');
          loadingIndicator.style.display = 'none';
      }
      setTimeout(() => {
        RefreshEdge();
    }, 10);
  };

  // 绑定事件处理器
  runButton._clickHandler = handler;
  runButton.addEventListener('click', handler);
}


// 处理 LLM 节点的 Prompt
function processLLmPrompt(node) {
  // 构建 ExprotAfterPrompt
  let ExprotAfterPrompt = 'Please ensure the output is in JSON format\n{\n';
  node.Outputs.forEach((output) => {
      let outputKind = '';
      if (output.Kind.includes('String')) {
          outputKind = 'String';
      } else if (output.Kind === 'Num') {
          outputKind = 'Num';
      } else if (output.Kind === 'Boolean') {
          outputKind = 'Boolean';
      }
      ExprotAfterPrompt +=
          '"' + output.Id + '": "' + output.Description +
          '" (you need output type:' + outputKind + ')\n';
  });
  ExprotAfterPrompt += '}\n';

  node.ExprotAfterPrompt = ExprotAfterPrompt;

  // 替换 prompt 中的占位符
  const matches = retrieveContentWithinBraces(node.prompt);
  let ExportPrompt = node.prompt;

  matches.forEach(match => {
      node.Inputs.forEach((input) => {
          if (input.name === match) {
              let replacement;
              if (input.Kind === 'Num') {
                  replacement = input.Num;
              } else if (input.Kind.includes('String')) {
                  replacement = input.Context;
              } else if (input.Kind === 'Boolean') {
                  replacement = input.Boolean;
              }
              // 替换占位符，去除花括号
              ExportPrompt = ExportPrompt.replace('{{' + match + '}}', replacement);
          }
      });
  });
  SystemMatches = retrieveContentWithinBraces(node.SystemPrompt);
  let SystemPrompt = node.SystemPrompt;
  SystemMatches.forEach(match => {
      node.Inputs.forEach((input) => {
          if (input.name === match) {
              let replacement;    
              if (input.Kind === 'Num') {
                  replacement = input.Num;
              }
              else if (input.Kind.includes('String')) {
                  replacement = input.Context;
              }
              else if (input.Kind === 'Boolean') {
                  replacement = input.Boolean;
              }
              SystemPrompt = SystemPrompt.replace('{{' + match + '}}', replacement);
          }
        });
      });  
  return [ SystemPrompt, ExportPrompt,ExprotAfterPrompt ];
}

// 从文本中提取花括号内的内容
function retrieveContentWithinBraces(text) {
  const regex = /{{(.*?)}}/g;
  const matches = [];
  let match;
  while ((match = regex.exec(text)) !== null) {
      matches.push(match[1].trim());
  }
  return matches;
}

// 更新输出显示，包括 Token 信息
function updateOutputs(outputs,debug,Id) {
  const outputElements = document.querySelectorAll('.output-item textarea');
  let dataTemp =graph.save();
  let nodeTemp;
  dataTemp.nodes.forEach(node => {
      if(node.id == Id)
      {
        nodeTemp = node;
      }
  });
  outputs.forEach((output, index) => {
      if (index < outputElements.length) {
          const element = outputElements[index];
          let value = '';
          if (output.Kind === 'Num') {
              value = output.Num ?? '';
              nodeTemp.Outputs[index].Num = output.Num;
          } else if (output.Kind.includes('String')) {
              value = output.Context ?? '';
              nodeTemp.Outputs[index].Context = output.Context;
          } else if (output.Kind === 'Boolean') {
              value = output.Boolean ? 'true' : 'false';
              nodeTemp.Outputs[index].Boolean = output.Boolean;
          }
          element.value = value;
      }
  });
  dataTemp.debug = debug;
  const debugelement =document.querySelector('.debug-wrapper textarea');
  if (debugelement) {
    debugelement.value = JSON.stringify(debug, null, 2);
  }
  ChangeDatas(dataTemp);
  // 更新 Token 信息（如果有）
  let tokenInfo = '';
  
  if (outputs[0]) {
      const output = outputs[0];
      if (
          typeof output.prompt_tokens !== 'undefined' &&
          typeof output.completion_tokens !== 'undefined' &&
          typeof output.total_tokens !== 'undefined'
      ) {
          tokenInfo = `
              <div class="token-info">
                  <div class="token-item">
                      <span>Prompt Tokens:</span> ${output.prompt_tokens}
                  </div>
                  <div class="token-item">
                      <span>Completion Tokens:</span> ${output.completion_tokens}
                  </div>
                  <div class="token-item">
                      <span>Total Tokens:</span> ${output.total_tokens}
                  </div>
              </div>
          `;
      }
  }

  // 更新 contentArea 的 token 信息
  const contentArea = document.getElementById('content-area');
  const existingTokenInfo = contentArea.querySelector('.token-info');
  if (existingTokenInfo) {
      existingTokenInfo.outerHTML = tokenInfo; // 更新现有的 token 信息
  } else {
      contentArea.insertAdjacentHTML('afterbegin', tokenInfo); // 插入新的 token 信息
  }
}

// 调整 textarea 高度的函数（假设已经定义）
function resizeTextarea(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = textarea.scrollHeight + 'px';
}

  // 关闭按钮事件监听器

//做一个update函数，定时每过一秒钟console.log('阿斯顿大苏打');
// 更新函数，每隔3秒执行一次
setInterval(() => {
  const { nodes} = graph.save();
  // 更新节点加载状态
  nodes.forEach(node => {
    const n = node.name.split('.py')[0];
    requestNodeInfo(n).then((nodeInfo) => {
      if (node.IsLoadSuccess != nodeInfo.IsLoadSuccess) {
        node.IsLoadSuccess = nodeInfo.IsLoadSuccess;
        ChangeDatas(nodes);
      }
    });
  });
}, 10000);
setInterval(() => {
  const { nodes, edges } = graph.save();

  if (document.getElementById('runButton').textContent === '运行中...' && IsTriggerNode === true) {
    let DataTemp = graph.save();
    let hasPassivityTrigger = DataTemp.nodes.some(node => node.NodeKind.includes('passivityTrigger'));
    let hasArrayTrigger = DataTemp.nodes.some(node => node.NodeKind.includes('ArrayTrigger'));

    // 如果没有正在运行的函数
    if (IsRunningFunction === false ) {
      if (passivityTriggerArray.length > 0 && ArrayTriggerArray.length == 0) {
        IsRunningFunction = true;
        let passivityData = passivityTriggerArray.shift();
        let localDataTemp = structuredClone(graph.save());
        let passivityNode = null;
        if (passivityData.nodeId) {
          passivityNode = localDataTemp.nodes.find(n => n.id === passivityData.nodeId);
        } else {
          passivityNode = localDataTemp.nodes.find(n => n.NodeKind.includes('passivityTrigger'));
        }
        if (passivityNode) {
          let processedData = processNodeConnections(localDataTemp, passivityNode, passivityData.outputData);
          loadArrayTriggerArray(processedData);
        } else {
        }
        processNextArrayTrigger(nodes, edges); 
      }
      else if (hasPassivityTrigger && ArrayTriggerArray.length == 0) {
        // 没有待处理的 passivityTrigger 数据，但存在 passivityTrigger 节点
        runPassivityTriggerNodes();
      } 
      else if (ArrayTriggerArray.length > 0) {
        // 没有 passivityTrigger，直接处理 ArrayTriggerArray
        IsRunningFunction = true;
        processNextArrayTrigger(nodes, edges);
      } else if (hasArrayTrigger && IsFirstRunArrayTrigger === true) {
        // 没有待处理的 ArrayTrigger 数据，但存在 ArrayTrigger 节点
        IsFirstRunArrayTrigger = false;
        
        runArrayTriggerNodes();
        
      } 
    }

    // 更新文件名
    updateFileName(FileName, Callsign);
  }
}, 1000);

// 运行 passivityTrigger 节点
async function runPassivityTriggerNodes() {
  let DataTemp = graph.save();
  let count = 0;
  for (const node of DataTemp.nodes) {
    if (node.NodeKind.includes('passivityTrigger')) {
      try {
        const inputs = getNodeInputs(node);
        const response = await fetch('/run-node', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            name: node.name,
            prompt: node.ExportPrompt,
            node: node,
            count: count,
            inputs: inputs,
            outputs: node.Outputs,
          })
        });
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        } else {
          let jsonResponse = await response.json();
          let result = jsonResponse;
          if (result.output != null) {
            LoadInPassivityTriggerArray(result, node);
          }
        }
      } catch (error) {
        console.error('处理PassivityTrigger节点时出错:', error);
      }
    }
  }
}

// 获取节点输入
function getNodeInputs(node) {
  return node.Inputs.reduce((acc, input, index) => {
    if (input.Kind === 'Num') {
      if (input.Num == null && input.Isnecessary === true) {
        throw new Error(`节点 ${node.label} 的输入点 ${input.Id} 缺失，请检查`);
      }
      acc[index] = input.Num;
    } else if (input.Kind.includes('String')) {
      if (input.Context == null && input.Isnecessary === true) {
        throw new Error(`节点 ${node.label} 的输入点 ${input.Id} 缺失，请检查`);
      }
      acc[index] = input.Context;
    } else if (input.Kind === 'Boolean') {
      if (input.Boolean == null && input.Isnecessary === true) {
        throw new Error(`节点 ${node.label} 的输入点 ${input.Id} 缺失，请检查`);
      }
      acc[index] = input.Boolean;
    }
    return acc;
  }, {});
}
// 使用 WeakMap 作为缓存
const nodeCache = new WeakMap();

// 优化后的节点连接处理函数
function processNodeConnections(DataTemp, triggerNode, outputData) {
  // 生成缓存键
  const cacheKey = `${triggerNode.id}-${JSON.stringify(outputData)}`;
  
  // 检查缓存
  if (nodeCache.has(triggerNode)) {
    const cache = nodeCache.get(triggerNode);
    if (cache[cacheKey]) {
      return structuredClone(cache[cacheKey]); // 返回缓存的深拷贝
    }
  }

  // 更新触发节点的输出
  UpdateNodeOutputs(triggerNode, outputData);

  // 创建节点和边的映射，减少循环查询
  const nodeEdgesMap = new Map();
  DataTemp.edges.forEach(edge => {
    if (edge.source === triggerNode.id) {
      if (!nodeEdgesMap.has(edge.target)) {
        nodeEdgesMap.set(edge.target, []);
      }
      nodeEdgesMap.get(edge.target).push(edge);
    }
  });

  // 优化节点处理
  DataTemp.nodes.forEach(nodez => {
    // 计算标签输入数量
    const labelInputCount = nodez.Inputs.reduce((count, input) => 
      count + (input.IsLabel ? 1 : 0), 0);
    
    // 获取当前节点的相关边
    const relevantEdges = nodeEdgesMap.get(nodez.id) || [];
    
    if (relevantEdges.length > 0) {
      // 处理相关边
      relevantEdges.forEach(edge => {
        const offset = edge.sourceAnchor - triggerNode.Inputs.length;
        const output = triggerNode.Outputs[offset];
        const input = nodez.Inputs[edge.targetAnchor];
        
        // 使用 switch 优化类型判断
        switch(input.Kind) {
          case 'Num':
            input.Num = output.Num;
            break;
          case 'Boolean':
            input.Boolean = output.Boolean;
            break;
          default:
            if (input.Kind.includes('String')) {
              input.Context = output.Context;
            }
        }
      });

      // 判断是否为起始节点
      const totalConnections = labelInputCount + relevantEdges.length;
      if (totalConnections === nodez.Inputs.length) {
        nodez.IsStartNode = true;
      }
    }
  });

  // 存入缓存
  if (!nodeCache.has(triggerNode)) {
    nodeCache.set(triggerNode, {});
  }
  nodeCache.get(triggerNode)[cacheKey] = structuredClone(DataTemp);

  // 添加缓存清理机制
  if (Object.keys(nodeCache.get(triggerNode)).length > 1000) {
    // 如果缓存过大，清理最旧的数据
    const cache = nodeCache.get(triggerNode);
    const keys = Object.keys(cache);
    delete cache[keys[0]];
  }

  return DataTemp;
}

// 添加缓存清理函数
function clearNodeCache() {
  nodeCache.clear();
}


// 重构后的 ArrayTrigger 函数
async function runArrayTriggerNodesInPassivityTriggerArray(DataTemp) { 
  let count = 0;
  // 识别 ArrayTrigger 节点
  let ArrayTriggernodesToProcess = DataTemp.nodes.filter(node => node.NodeKind.includes('ArrayTrigger'));

  // 识别连接到 ArrayTrigger 节点的所有上游节点
  let ConnectArrayTriggernodesToProcessEdges = DataTemp.edges.filter(edge => 
      ArrayTriggernodesToProcess.some(node => node.id === edge.target)
  );
  let ConnectArrayTriggernodesToProcessNodes = ConnectArrayTriggernodesToProcessEdges.map(edge => 
      DataTemp.nodes.find(node => node.id === edge.source)
  );

  // 第一阶段：处理所有连接的上游节点
  for (const node of ConnectArrayTriggernodesToProcessNodes) {
      node.IsRunning = true;
      if (node.ExprotAfterPrompt == '') {
        let Temp = 'Please ensure the output is in JSON format\n{\n';
        node.Outputs.forEach(output => {
          let Kind = output.Kind;
          Temp += `"${output.Id}": "${output.Description}" (you need output type: ${Kind})\n`;
        });
        Temp += '}\n';
        node.ExprotAfterPrompt = Temp;
      }
      const [systemPrompt, exportPrompt] = processLLmPrompt(node);
                  node.SystemPrompt = systemPrompt;
                  node.ExportPrompt = exportPrompt;
      try {
          const inputs = getNodeInputs(node);
          const response = await fetch('/run-node', {
              method: 'POST',
              headers: {
                  'Content-Type': 'application/json'
              },
              body: JSON.stringify({
                  name: node.name,
                  prompt: node.ExportPrompt,
                  node: node,
                  count: count,
                  inputs: inputs,
                  outputs: node.Outputs,
              })
          });

          if (!response.ok) {
              throw new Error(`HTTP error! status: ${response.status}`);
          } else {
              let jsonResponse = await response.json();
              let result = jsonResponse;

              if (result.output != null) {

                  //将result.output往下赋值
                  DataTemp.edges.forEach(edge => {
                    if (edge.source === node.id) {
                      // 使用 filter 查找目标节点，减少嵌套循环
                      const targetNodes = DataTemp.nodes.filter(nodez => nodez.id === edge.target);
                  
                      if (targetNodes.length > 0) {
                        targetNodes.forEach((nodeZ) => {
                          
                          const offset = edge.sourceAnchor - node.Inputs.length;
                          const output = result.output[offset];
                          const input = nodeZ.Inputs[edge.targetAnchor];
                          
                          // 标记输入状态并根据类型赋值
                          input.inputStatus = true;
                          // 使用 switch 优化类型判断
                          if (input.Kind === 'Num') {
                            input.Num = output.Num;
                          } else if (input.Kind === 'Boolean') {
                            input.Boolean = output.Boolean;
                          } else if (input.Kind.includes('String')) {
                            input.Context = output.Context;
                          }
                        });
                        ChangeDatas(DataTemp);
                      }
                    }
                  });
                  
                  
              }
          }
      } catch (error) {
          console.error('处理上游节点时出错:', error);
      }
  }

  ArrayTriggernodesToProcess = DataTemp.nodes.filter(node => node.NodeKind.includes('ArrayTrigger'));

  // 第二阶段：处理 ArrayTrigger 节点
  for (const node of ArrayTriggernodesToProcess) {
      try {
          const inputs = getNodeInputs(node);
          const response = await fetch('/run-node', {
              method: 'POST',
              headers: {
                  'Content-Type': 'application/json'
              },
              body: JSON.stringify({
                  name: node.name,
                  prompt: node.ExportPrompt,
                  node: node,
                  count: count,
                  inputs: inputs,
                  outputs: node.Outputs,
              })
          });

          if (!response.ok) {
              throw new Error(`HTTP error! status: ${response.status}`);
          } else {
              let jsonResponse = await response.json();
              let result = jsonResponse;

              if (result.output != null) {
                  result.output.forEach((outputData) => {
                      // 原逻辑：将完整 processedData 推到 ArrayTriggerArray
                      // 现在只推 outputData
                      
                      ArrayTriggerArray.push({
                        outputData: structuredClone(outputData),
                        nodeId: node.id
                      });
                  });
                console.log('ArrayTriggerArray:', ArrayTriggerArray); 
              }
          }
      } catch (error) {
          console.error('处理ArrayTrigger节点时出错:', error);
      }
  }

  updateFileName(FileName, Callsign);
}

async function runArrayTriggerNodes(){
  let DataTemp = graph.save();
  let count = 0;
  let nodesToProcess = DataTemp.nodes.filter(node => node.NodeKind.includes('ArrayTrigger'));

  for (const node of nodesToProcess) {
      try {
          const inputs = getNodeInputs(node);
          const response = await fetch('/run-node', {
              method: 'POST',
              headers: {
                  'Content-Type': 'application/json'
              },
              body: JSON.stringify({
                  name: node.name,
                  prompt: node.ExportPrompt,
                  node: node,
                  count: count,
                  inputs: inputs,
                  outputs: node.Outputs,
              })
          });

          if (!response.ok) {
              throw new Error(`HTTP error! status: ${response.status}`);
          } else {
              let jsonResponse = await response.json();
              let result = jsonResponse;

              if (result.output != null) {
                  result.output.forEach((outputData) => {
                      // 只存 outputData 以及 node.id
                      ArrayTriggerArray.push({
                        outputData: structuredClone(outputData),
                        nodeId: node.id
                      });
                  });
                  console.log('ArrayTriggerArray:', ArrayTriggerArray); 
              }
          }
      } catch (error) {
          console.error('处理ArrayTrigger节点时出错:', error);
      }
  }
  updateFileName(FileName, Callsign);
}
// 重构后的 LoadInPassivityTrigger 函数
function LoadInPassivityTriggerArray(data, triggerNode) {
  data.output.forEach((outputData) => {
      passivityTriggerArray.push({
        outputData: structuredClone(outputData),
        nodeId: triggerNode.id
      });
  });
  updateFileName(FileName, Callsign);
}
// 使用 passivityData 加载 ArrayTriggerArray
function loadArrayTriggerArray(passivityData) {
  // 克隆数据
  let DataTemp = structuredClone(passivityData);
  let hasArrayTrigger = DataTemp.nodes.some(node => node.NodeKind.includes('ArrayTrigger'));
  if (hasArrayTrigger) {
    runArrayTriggerNodesInPassivityTriggerArray(DataTemp);
  } else {
    ArrayTriggerArray.push(DataTemp);
    updateFileName(FileName, Callsign);
  }
  DataTemp = null;
}
// 更新节点的 Outputs
function UpdateNodeOutputs(node, outputData) {
  node.Outputs.forEach((output, index) => {
    if (output.Kind === 'Num') {
      output.Num = outputData[index].Num;
    } else if (output.Kind.includes('String')) {
      output.Context = outputData[index].Context;
    } else if (output.Kind === 'Boolean') {
      output.Boolean = outputData[index].Boolean;
    }
  });
}
// 更新节点的 Inputs
function UpdateNodeInputs(node, targetAnchor, output) {
  if (node.Inputs[targetAnchor].Kind === 'Num') {
    node.Inputs[targetAnchor].Num = output.Num;
  } else if (node.Inputs[targetAnchor].Kind.includes('String')) {
    node.Inputs[targetAnchor].Context = output.Context;
  } else if (node.Inputs[targetAnchor].Kind === 'Boolean') {
    node.Inputs[targetAnchor].Boolean = output.Boolean;
  }
  //更新ExportPrompt
  
}
// 处理下一个 ArrayTrigger 数据
function processNextArrayTrigger(nodes, edges) {
  if (ArrayTriggerArray.length > 0) {
    let arrayData = ArrayTriggerArray.shift();
    if(arrayData.nodeId == null){
      processNodes(nodes, edges, arrayData);
      return;
    }
    let arrayNode = nodes.find(node => node.id === arrayData.nodeId);
    let localDataTemp = processNodeConnections(structuredClone(graph.save()), arrayNode, arrayData.outputData);
    processNodes(nodes, edges, localDataTemp);
  } else {
    IsRunningFunction = false;
    cleanup();
    updateFileName(FileName, Callsign);
  }
}
function cleanup() {
  // 清理不再需要的数据
  ArrayTriggerArray = [];
}
// 运行节点流程
function processNodes(nodes, edges, data) {
  let DataTemp;
  if (data) {
    data.nodes.forEach(nodez => {
      nodez.IsBlock = true;
      nodez.IsRunning = false;
      nodez.IsError = false;
      nodez.isFinish = false;
      nodez.firstRun =true;
    });
    DataTemp = data;
    ChangeDatas(data);
    TempMessageNode = structuredClone(data);
  }
  else {
    DataTemp = graph.save();
    DataTemp.nodes.forEach(nodez => {
      nodez.IsBlock = true;
      nodez.IsRunning = false;
      nodez.IsError = false;
      nodez.isFinish = false;
    });

    ChangeDatas(DataTemp);
    TempMessageNode = structuredClone(DataTemp);
  }
  
  
  
  // 假设 runAllNodes 是一个异步函数，我们在其完成后将 IsRunningFunction 设置为 false，并继续处理下一个数据
  runAllNodes(DataTemp, nodes, edges).then(() => {
     updateFileName(FileName, Callsign);
  }).catch((error) => {
    console.error('运行节点流程时出错:', error);
    IsRunningFunction = false;
  });
}
// 更新文件名
function updateFileName(FileName, Callsign) {
  FileName = FileName.replace(".json", "");
  FileName = FileName.substring(FileName.lastIndexOf(':') + 1);
  
  if (Callsign != null) {
      FileName = Callsign + ':' + FileName;
  }
  
  // 启动标题动画
  if (!window.titleInterval) {
      window.titleInterval = animateTitle(FileName);
  }
}

function pasteFunction() {
  // 获取鼠标位置
  document.addEventListener('mousemove', function(event) {
      let target = graph.getPointByClient(event.clientX, event.clientY);
      
      // 确保复制的节点存在
      if (CopyNodeTemp) {
          // 获取鼠标位置的 canvas 坐标
          let canvasX = target.x;
          let canvasY = target.y;

          // 粘贴节点到鼠标位置
          copyNode(CopyNodeTemp, canvasX, canvasY);
      } else {
          alert("No node to paste!");
      }
  }, { once: true });
}
function copyFunction() {
  //遍历所有的node找到ishovor==true的node
  let DataTemp=graph.save();
  DataTemp.nodes.forEach(node => {
    if (node.IsHovor) {
      CopyNodeTemp = node;
      console.log('CopyNodeTemp:',CopyNodeTemp);
    }
  });
}
// 优化版本的 ChangeDatas
function ChangeDatas(data) {
  // 限制最大历史记录数量
  const MAX_HISTORY = 20;
  
  let TempData = structuredClone(graph.save());
  
  if (MemoryIndex === -1 || JSON.stringify(TempData) !== JSON.stringify(SaveGraph[MemoryIndex])) {
    if (MemoryIndex < SaveGraph.length - 1) {
      SaveGraph = SaveGraph.slice(0, MemoryIndex + 1);
    }
    
    // 如果历史记录太多，删除较早的记录
    if (SaveGraph.length >= MAX_HISTORY) {
      SaveGraph = SaveGraph.slice(-MAX_HISTORY + 1);
      MemoryIndex = SaveGraph.length - 1;
    }
    
    SaveGraph.push(TempData);
    MemoryIndex++;
  }
  
  graph.changeData(data);
}


document.addEventListener('keydown', function(event) {
  if (event.ctrlKey && event.key === 'z') {
    // 撤销 (Ctrl+Z)
    if (MemoryIndex > 0) {
      MemoryIndex--;
      graph.changeData(SaveGraph[MemoryIndex]);
      //console.log('撤销到:', SaveGraph[MemoryIndex]);
      //console.log('MemoryIndex:', SaveGraph);
    } else if (MemoryIndex === 0) {
      // 确保在撤销到初始状态时正确更新图形
      graph.changeData(SaveGraph[MemoryIndex]);
      //console.log('撤销到初始状态:', SaveGraph[MemoryIndex]);
    }
  } else if (event.ctrlKey && event.key === 'y') {
    // 重做 (Ctrl+Y)
    if (MemoryIndex < SaveGraph.length - 1) {
      MemoryIndex++;
      graph.changeData(SaveGraph[MemoryIndex]);
      //console.log('重做到:', SaveGraph[MemoryIndex]);
      //console.log('MemoryIndex:', SaveGraph);
    }
  }
  else if (event.ctrlKey && event.key === 's') {//抑制浏览器保存
    event.preventDefault();
    saveFunction();
  }
  const isInput = event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA' || event.target.isContentEditable;

  if (!isInput && event.ctrlKey && event.key === 'c') { // 抑制浏览器保存
    event.preventDefault();
    copyFunction();
  } else if (!isInput && event.ctrlKey && event.key === 'v') {
    event.preventDefault();
    pasteFunction();
  }
  else if(event.ctrlKey && event.key === 'r') {
    event.preventDefault();
    runFunction();
  }
  //为运行
  if(document.getElementById('runButton').textContent == '运行')
  {
    //按delete
    if (event.key === 'Delete') {
      let DataTemp=graph.save();
      DataTemp.nodes.forEach(node => {
        if (node.IsHovor) {
          // 删除节点
          const item = graph.findById(node.id);
          removeNode(item);
        }
      });
    }
    
  }
});
function runFunction() {
  if(document.getElementById('runButton').textContent == '运行中...' && IsTriggerNode==true)
  {
    IsTriggerNode=false;
    document.getElementById('runButton').textContent = '运行';
    let DataTemp=graph.save();
    DataTemp.nodes.forEach(nodez => {
      nodez.IsBlock = false;
    })
    ChangeDatas(DataTemp);
    ArrayTriggerArray = [];
    passivityTriggerArray = [];
    updateFileName(FileName, Callsign);
  }
  else if(document.getElementById('runButton').textContent == '运行')
  {
    IsTriggerNode = false;
    TempNodeArray = [];
    IsFirstRunArrayTrigger = true;
    const { nodes, edges } = graph.save();
    TempMessageNode=structuredClone(graph.save());
    // 检查每个节点的每个输入矛点是否都被连接
    let isContinue = true;
    nodes.forEach(node => {
        node.Inputs.forEach((input, index) => {
            if (input.Isnecessary == true &&input.Link==0 && input.IsLabel == false) {
                isContinue = false;
                let DataTemp=graph.save();
                DataTemp.nodes.forEach(nodez => {
                  if(nodez.id == node.id)
                  {
                    nodez.IsError = true;
                    nodez.ErrorContext = '存在未连接的必要输入矛点';
                  }
                })
                ChangeDatas(DataTemp);
            }
        });
        if(node.NodeKind.includes('Trigger'))
        {
          IsTriggerNode = true;
        }
    });

    if (!isContinue) {
        showMessage('存在未连接的必要输入矛点，程序终止','#ff0000');
        return;
    }
    document.getElementById('runButton').textContent = '运行中...';
    let DataTemp=graph.save();
    //console.log('DataTemp:',DataTemp);
    DataTemp.nodes.forEach(nodez => {
      nodez.IsBlock = true;
      nodez.IsRunning = false;
      nodez.IsError = false;
      nodez.isFinish = false;
      nodez.IsStartNode = false;
    })
    if(IsTriggerNode==false)
    {
      IsRunningFunction=true;
      runAllNodes(DataTemp, nodes, edges);
    }
    }
    else if(document.getElementById('runButton').textContent == '返回编辑模式' || document.getElementById('runButton').textContent == '运行中...')
    {
      document.getElementById('runButton').textContent = '运行';
      let DataTemp=graph.save();
      DataTemp.nodes.forEach(nodez => {
        nodez.IsBlock = false;
        let Tempnode=TempMessageNode.nodes.find(node => node.id === nodez.id);
        nodez.Inputs=Tempnode.Inputs;
      })
      ChangeDatas(DataTemp);
      
    }
  setTimeout(() => {
    RefreshEdge();
  }, 10);
}
async function runAllNodes(DataTemp, nodesT, edges) {
  // 运行函数程序初始化
  DataTemp.nodes.forEach(nodez => {
    nodez.IsBlock = true;
    nodez.IsRunning = false;
    nodez.IsError = false;
    nodez.isFinish = false;
  });
  ChangeDatas(DataTemp);
  let nodes=structuredClone(nodesT);//BUg修复！！！！！，nodes无法再函数中更改
  // 为所有节点初始化一个输入状态对象
  nodes.forEach(node => {
    if (node.NodeKind.includes('Trigger')==false) {
      node.inputStatus = node.Inputs.map(() => false);  // 初始时，所有输入状态都设置为 false

      edges.forEach(edge => {
        if (edge.target === node.id) {
          let sourceNodez = nodes.find(nodez => nodez.id === edge.source);
          if (sourceNodez && sourceNodez.NodeKind.includes('Trigger')) {
            node.inputStatus[edge.targetAnchor] = true;
          } else {
            node.inputStatus[edge.targetAnchor] = false;
          }
        }
      });
      node.firstRun = true;
      node.RecursionBehavior ='STOP';
      node.Outputs.forEach(output => {
        output.Boolean = false;  // 初始化输入
        output.Num = 0;  // 初始化输出
        output.Context = '';  // 初始化输出
      });
    }
  });
  // 找到没有输入的节点作为起始节点并执行
  const startNodes = nodes.filter(node =>
    (node.IsStartNode || node.Inputs.length === 0 || node.Inputs.every(input => input.IsLabel == true)) &&
    node.NodeKind.includes('Trigger')==false
  );
  
  let promises = startNodes.map(node => prepareAndExecuteNode(node, DataTemp, nodes, edges));

  // 等待所有的异步操作完成
  Promise.all(promises).then(() => {
    IsRunningFunction = false;
    
    if(document.getElementById('runButton').textContent != '运行中...')
    {
      nodes.forEach(nodez => {
        nodez.IsBlock = false;
        nodez.IsRunning = false;
        nodez.IsError = false;
        nodez.isFinish = false;
        nodez.IsStartNode = false;
      })
      document.getElementById('runButton').textContent = '运行';
    }
    else
    {
      if(IsTriggerNode==false)
      document.getElementById('runButton').textContent = '返回编辑模式';
    }
    
  }).catch(error => {
    console.error('执行节点时出错：', error);
    IsRunningFunction = false;
  });
}

// 工具函数：检查字符串是否可读
function isReadable(str) {
  return typeof str === 'string' && /^[\x20-\x7E]*$/.test(str);
}

// 工具函数：处理执行结果的context
function processContext(context) {
  if (typeof context !== 'string') {
    context = JSON.stringify(context, null, 2);
  }
  
  if (context.includes('Error')) {
    if (!isReadable(context)) {
      context = JSON.stringify(context, null, 2);
    }
    throw new Error(context);
  }
  
  return context;
}

// 工具函数：处理节点输入
function processNodeInputs(node) {
  return node.Inputs.reduce((acc, input, index) => {
    if (input.Isnecessary && input[input.Kind === 'Num' ? 'Num' : input.Kind.includes('String') ? 'Context' : 'Boolean'] == null) {
      throw new Error(`节点 ${node.label} 的输入点 ${input.Id} 输出错误，请重试节点${input}`);
    }
    acc[index] = input[input.Kind === 'Num' ? 'Num' : input.Kind.includes('String') ? 'Context' : 'Boolean'];
    return acc;
  }, {});
}

// 工具函数：更新边的状态
function updateEdgeStates(graph, linkedLines, linkedLines1) {
  linkedLines.forEach(e => {
    const eg = graph.findById(e);
    if (eg) {
      eg.setState('linked', true);
      eg.setState('linkBlue', true);
    }
  });
  
  linkedLines1.forEach(e => {
    const eg = graph.findById(e);
    if (eg) {
      eg.setState('linked', false);
    }
  });
}


// 主要函数：准备并执行节点
function prepareAndExecuteNode(node, DataTemp, nodes, edges) {
  const [systemPrompt, exportPrompt] = processLLmPrompt(node);
  node.SystemPrompt = systemPrompt;
  node.ExportPrompt = exportPrompt;
  
  addHistory('Start');
  
  if (node.TriggerLink==0 || node.RecursionBehavior != 'STOP') {
    return executeNode(node, 0, DataTemp, nodes, edges);
  }
  return Promise.resolve();
}

// 工具函数：获取连接的边
function getLinkedEdges(edges, nodeId) {
  const outgoing = edges.filter(edge => edge.source === nodeId);
  const incoming = edges.filter(edge => edge.target === nodeId);
  return {
    outgoing,
    incoming,
    outgoingIds: outgoing.map(edge => edge.id),
    incomingIds: incoming.map(edge => edge.id)
  };
}

// 工具函数：更新节点状态
function updateNodeStatus(DataTemp, nodeId, status) {
  DataTemp.nodes.forEach(nodez => {
    if (nodez.id === nodeId) {
      Object.assign(nodez, status);
      if (nodez.NodeKind.includes('Trigger')) {
        DataTemp.nodes.forEach(nodezz => {
          nodezz.IsBlock = true;
          nodezz.IsRunning = false;
          nodezz.IsError = false;
        });
      }
    }
  });
}

/**
 * 执行单个节点
 * @param {Object}   node      当前节点（会被克隆，避免副作用）
 * @param {Number}   count     递归计数
 * @param {Object}   DataTemp  全局临时数据（G6 图等）
 * @param {Object[]} nodes     全部节点
 * @param {Object[]} edges     全部连线
 */
async function executeNode(node, count, DataTemp, nodes, edges) {
  count++;

  /* ---------------- 判断是否应该执行 ---------------- */
  const isBtnRunning      = document.getElementById('runButton').textContent === '运行中...';
  const isRunningFunction = IsRunningFunction;                    // 全局开关
  const isTriggerNode     = node.NodeKind?.includes('Trigger');   // 触发器节点不执行
  const isFirstRun        = node.firstRun;
  const isRecursion       = node.RecursionBehavior === 'STOP' && node.TriggerLink > 0;

  const areInputsReady = node.Inputs.every((input, idx) => {
    const ready =
      (!input.Isnecessary && input.Link === 0) ||                 // 非必需未连线
      (node.inputStatus[idx] && input.Link > 0) ||                // 已连线且就绪
      input.IsLabel;                                              // Label 输入
    if (!ready) {
      console.warn(`❌ Input[${idx}] 未就绪`, { input, link: input.Link, status: node.inputStatus[idx] });
    }
    return ready;
  });

  console.table({
    '①按钮文本是“运行中...”' : isBtnRunning,
    '②IsRunningFunction'     : isRunningFunction,
    '③NodeKind含Trigger'     : isTriggerNode,
    '④firstRun'              : isFirstRun,
    '⑤全部输入就绪'          : areInputsReady,
    '⑥isRecursion'           : isRecursion,
    '⑦RecursionBehavior'     : node.RecursionBehavior,
    '⑧TriggerLink'           : node.TriggerLink,
  });

  if (!isBtnRunning || !isRunningFunction || isTriggerNode || !isFirstRun || !areInputsReady || isRecursion) {
    return;     // 不满足执行条件
  }

  console.log('✅ 执行节点：', node.label);

  /* ---------------- 初始化执行环境 ---------------- */
  const { outgoingIds, incomingIds } = getLinkedEdges(edges, node.id);
  updateNodeStatus(DataTemp, node.id, { IsRunning: true });

  // 保存副本，便于后续恢复
  const tempNode = structuredClone(node);
  ChangeDatas(DataTemp);
  node = structuredClone(tempNode);
  graph.refresh();

  // 标记已运行
  node.firstRun = false;
  nodes.forEach(n => { if (n.id === node.id) n.firstRun = false; });

  // 处理输入
  const TempInputs = processNodeInputs(node);

  /* ---------------- 生成并写回 Prompt ----------------
     只有 LLM 节点才需要；其余节点 processLLmPrompt 可直接返回 ['', ''] */
  console.log('处理 LLM 节点的 Prompt...',node.label,node.ExportPrompt);
  if (node.NodeKind?.toLowerCase() === 'llm') {
    const [sysPrompt, expPrompt] = processLLmPrompt(node);
    node.SystemPrompt  = sysPrompt;
    node.ExportPrompt  = expPrompt;     // 推荐字段
  }

  /* ---------------- 执行节点主体 ---------------- */
  let RetryNum = node.ReTryNum ?? 0;
  let success  = false;
  let data     = null;

  do {
    try {
      if (node.TriggerLink > 0 && node.RecursionBehavior === 'SKIP') {
        /* ---------- ① 跳过模式：构造空输出 ---------- */
        data = {
          output: node.Outputs.map(() => ({
            Num: -1, Context: '', Boolean: false,
            prompt_tokens: 0, completion_tokens: 0, total_tokens: 0
          }))
        };
      } else {
        /* ---------- ② 正常模式：调用 /run-node ---------- */
        console.log('执行节点请求：', node.name, node.ExportPrompt, TempInputs);
        const response = await fetch('/run-node', {
          method : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body   : JSON.stringify({
            name   : node.name,
            prompt : node.ExportPrompt,  // 后端若仍用 ExportPrompt 亦能兼容
            node,
            count,
            inputs : TempInputs,
            outputs: node.Outputs,
          })
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || '请求失败');
        }
        data = await response.json();
        console.log('data:',data);
      }

      // 停止按钮被点，直接退出
      if (document.getElementById('runButton').textContent !== '运行中...') return;

      /* ---------- 输出后处理 ---------- */
      data.output.forEach(out => {
        try {
          out.Context = processContext(out.Context);
        } catch (err) {
          console.error('processContext 失败：', err);
          throw err;
        }
      });

      /* ---------- 更新节点状态 ---------- */
      success = true;
      updateNodeStatus(DataTemp, node.id, {
        IsRunning: false,
        isFinish : true,
        ErrorContext: '',
        RecursionBehavior: node.RecursionBehavior,
        IsError: false
      });
      ChangeDatas(DataTemp);
      RefreshEdge();

      /* ---------- 写回输出 ---------- */
      const sourceTempNode = TempMessageNode.nodes.find(n => n.id === node.id);
      sourceTempNode.Outputs.forEach((o, i) => Object.assign(o, data.output[i]));
      //debugto string赋值给sourceTempNode.debug
      sourceTempNode.debug = JSON.stringify(data.debug, null, 2);

      // 第一条输出携带 token 统计
      if (data.output[0]) {
        ['prompt_tokens', 'completion_tokens', 'total_tokens'].forEach(k => {
          sourceTempNode.Outputs[0][k] = data.output[0][k];
        });
      }
      console.log('sourceTempNode.debug:',sourceTempNode.debug);
      addHistory(sourceTempNode);

      /* ---------- 递归处理子节点 ---------- */
      const childPromises = edges
        .filter(e => e.source === node.id)
        .map(async edge => {
          const targetNode = nodes.find(n => n.id === edge.target);
          if (!targetNode || targetNode.NodeKind?.includes('Trigger')) return;

          /* 把当前输出写到目标节点输入 */
          const srcIdx = edge.sourceAnchor - node.Inputs.length;
          const tgtIdx = edge.targetAnchor;
          const outVal = data.output[srcIdx];

          if (targetNode.Inputs.length > tgtIdx) {
            Object.assign(targetNode.Inputs[tgtIdx], {
              Num: outVal.Num, Context: outVal.Context, Boolean: outVal.Boolean
            });
            targetNode.inputStatus[tgtIdx] = true;
            const tTemp = TempMessageNode.nodes.find(n => n.id === targetNode.id);
            Object.assign(tTemp.Inputs[tgtIdx], targetNode.Inputs[tgtIdx]);
          }

          /* 触发器逻辑 */
          if (edge.targetAnchor === targetNode.Inputs.length + targetNode.Outputs.length) {
            targetNode.RecursionBehavior = outVal.Boolean ? 'Run' : outVal.TriggerKind;
          }

          /* 子节点也需要 Prompt */
          if (targetNode.NodeKind?.toLowerCase() === 'llm') {
            const [sys, exp] = processLLmPrompt(targetNode);
            targetNode.SystemPrompt = sys;
            targetNode.ExportPrompt = exp;
          }

          await executeNode(targetNode, count, DataTemp, nodes, edges);
        });

      await Promise.all(childPromises);

    } catch (err) {
      RetryNum--;
      if (RetryNum > 0) {
        console.error(`节点 ${node.name} 执行失败，重试 ${RetryNum} 次：`, err.message);
        showMessage(`节点 ${node.name} 执行失败，重试 ${RetryNum} 次。`, 'orange');
      } else {
        const errMsg = `节点运行有 Bug：\n${err.message}`;
        updateNodeStatus(DataTemp, node.id, { IsError: true, ErrorContext: errMsg });

        TempMessageNode.nodes
          .filter(n => n.id === node.id)
          .forEach(n => { n.IsError = true; n.ErrorContext = errMsg; });

        ChangeDatas(DataTemp);
        //报错行数
        console.error(`节点 ${node.name} 最终失败：`, err, err.stack);
      }
    }
  } while (!success && RetryNum > 0);
}



function RefreshEdge () {
  /* === 1. 取图数据并清零 === */
  const { nodes, edges } = graph.save();

  nodes.forEach(node => {
    node.Inputs.forEach(inp => (inp.Link = 0));
    node.Outputs.forEach(out => (out.Link = 0));
    node.TriggerLink = 0;
  });

  /* === 2. 过滤非法边并补齐锚点 === */
  const validEdges = edges.filter(edge => {
    const src = nodes.find(n => n.id === edge.source);
    const dst = nodes.find(n => n.id === edge.target);
    if (!src || !dst) return false;

    const srcOut = src.Outputs.find(o => o.Id === edge.sourceAnchorID);

    /* ——— IfNode 特殊 ——— */
    if (src.NodeKind === 'IfNode') {
      if (!srcOut) return false;
      dst.TriggerLink = 1;
      srcOut.Link     = 1;
      edge.sourceAnchor = src.Outputs.indexOf(srcOut) + src.Inputs.length;
      edge.targetAnchor = dst.Inputs.length + dst.Outputs.length;
      return true;
    }

    /* ——— 常规节点 ——— */
    const dstInp = dst.Inputs.find(i => i.Id === edge.targetAnchorID);
    if (!srcOut || !dstInp) return false;

    srcOut.Link = 1;
    dstInp.Link = 1;
    edge.sourceAnchor = src.Outputs.indexOf(srcOut) + src.Inputs.length;
    edge.targetAnchor = dst.Inputs.indexOf(dstInp);
    return true;
  });

  /* === 3. 写回图数据 === */
  ChangeDatas({ nodes, edges: validEdges });

  /* === 4. IfNode 边缘着色 === */
  const colored = { orange: [], purple: [] };

  validEdges.forEach(e => {
    const s = nodes.find(n => n.id === e.source);
    if (s?.NodeKind === 'IfNode') {
      const idx = e.sourceAnchor - s.Inputs.length;
      const out = s.Outputs[idx];
      if (out?.TriggerKind === 'STOP') colored.purple.push(e.id);
      else                             colored.orange.push(e.id);
    }
  });

  colored.orange.forEach(id => graph.findById(id)?.setState('linkOrange', true));
  colored.purple.forEach(id => graph.findById(id)?.setState('linkPurple', true));

  /* === 5. 运行态高亮 === */
  if (document.getElementById('runButton').textContent === '运行中...') {
    /* 5‑1. 先全部复位 */
    validEdges.forEach(e => {
      const ed = graph.findById(e.id);
      if (!ed) return;
      ed.setState('linked', false);
      ed.setState('linkBlue',  false);
      ed.setState('linkOrange', false);
      ed.setState('linkPurple', false);

      const s = nodes.find(n => n.id === e.source);
      if (!s) return;
      if (s.NodeKind === 'IfNode') {
        const out = s.Outputs[e.sourceAnchor - s.Inputs.length];
        if (out?.TriggerKind === 'STOP') ed.setState('linkPurple', true);
        else                             ed.setState('linkOrange', true);
      }
    });

    /* 5‑2. 再对运行中节点连线高亮 */
    nodes.forEach(n => {
      if (!n.IsRunning) return;
      validEdges
        .filter(e => e.source === n.id)
        .forEach(e => {
          const ed = graph.findById(e.id);
          if (!ed) return;
          if (n.NodeKind === 'IfNode') {
            const out = n.Outputs[e.sourceAnchor - n.Inputs.length];
            if (out?.TriggerKind === 'STOP') {
              ed.setState('linked', true);
              ed.setState('linkPurple', true);
            } else {
              ed.setState('linked', true);
              ed.setState('linkOrange', true);
            }
          } else {
            ed.setState('linked', true);
            ed.setState('linkBlue', true);
          }
        });
    });
  }
}
function addHistory(data) { // 
  let Temp;
  if(data!='Start')
  {
    // 过滤后的对象只保留 name、Kind，以及根据 Kind 值选择 Context, Boolean 或 Num
    let filteredData = {
      NodeKind: data.NodeKind,
      label: data.label,
      Outputs: data.Outputs.map(item => {
          // 根据 Kind 字段的内容选择性保留 Context, Boolean, 或 Num
          let selectedField;
          if (item.Kind.includes("String")) {
              selectedField = { Context: item.Context };
          } else if (item.Kind.includes("Boolean")) {
              selectedField = { Boolean: item.Boolean };
          } else if (item.Kind.includes("Num")) {
              selectedField = { Num: item.Num };
          }
          
          // 仅保留 name, Kind，以及选择的字段
          return {
              name: item.name,
              Kind: item.Kind,
              ...selectedField
          };
      }),
      Inputs: data.Inputs.map(item => {
          // 根据 Kind 字段的内容选择性保留 Context, Boolean, 或 Num
          let selectedField;
          if (item.Kind.includes("String")) {
              selectedField = { Context: item.Context };
          } else if (item.Kind.includes("Boolean")) {
              selectedField = { Boolean: item.Boolean };
          } else if (item.Kind.includes("Num")) {
              selectedField = { Num: item.Num };
          }

          // 仅保留 name, Kind，以及选择的字段
          return {
              name: item.name,
              Kind: item.Kind,
              ...selectedField
          };
      })
    };

    // 将过滤后的对象转回 JSON 字符串
    Temp = JSON.stringify(filteredData);
    //console.log('过滤后的对象:', filteredData);

    
  }
  else
  {
    //让赋值Temp =['message': 'New conversation started']
    Temp = JSON.stringify({name: 'New started'});
    
  }
  fetch(`/addHistory?ProjectName=${ProjectName}`, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: Temp,
    })
    .then(response => response.json())
    .then(data => {
        console.log('Success:', data);
        loadHistory();
    })
    .catch((error) => {
        console.log('Error:', error);
    });
}
function loadHistory() {
  fetch(`/getHistory?ProjectName=${ProjectName}`)
  .then(response => response.json())
  .then(data => {
      //console.log('Success:', data);
  })
  .catch((error) => {
      //console.log('Error:', error);
  });
}
/* ---------- 工具函数 ---------- */
/** 从对象 o 中挑选 keys 列表里存在的字段 */
function pick(o, keys) {
  const out = {};
  keys.forEach(k => { if (k in o) out[k] = o[k]; });
  return out;
}

/** 根据节点类型返回保留字段列表 */
function slimNode(node) {
  const base = ['id', 'name', 'label', 'x', 'y']; // 所有节点共用
  const kind = (node.NodeKind || node.Kind || '').toLowerCase();

  if (kind.includes('llm')) {
    return pick(node, [
      ...base, 'NodeKind',
      'Inputs', 'Outputs', 'TempOutPuts',
      'SystemPrompt', 'prompt', 'ExportPrompt', 'ExprotAfterPrompt',
      'max_tokens', 'temperature', 'Top_p',
      'OriginalTextSelector',
      'frequency_penalty', 'presence_penalty',
      'ReTryNum', 'mcpServers','ReactNum',
      'IsReact','Tools','Memory'
    ]);
  } else if (kind.includes('arraytrigger')) {
    return pick(node, [
      ...base, 'NodeKind', 'Inputs', 'OriginalTextArray',
      'Outputs', 'RecursionBehavior', 'ReTryNum'
    ]);
  } else if (kind.includes('normal')) {
    return pick(node, [
      ...base, 'NodeKind', 'Inputs', 'Outputs',
      'prompt', 'ReTryNum'
    ]);
  } else if (kind.includes('database')) {
    return pick(node, [
      ...base, 'NodeKind', 'Inputs', 'Outputs',
      'DataBaseSubjectArray', 'DataBaseContentArray',
      'DataBaseLogicKind', 'DataBaseIsExactArray',
      'selectBox1', 'selectNum1',
      'selectBox2', 'selectNum2',
      'selectBox5', 'ReTryNum'
    ]);
  } else if (kind.includes('ifnode')) {
    return pick(node, [
      ...base, 'NodeKind', 'Inputs', 'Outputs',
      'IfLogicSubjectArray', 'IfLogicContentArray',
      'IfLogicKind', 'ReTryNum', 'RecursionBehavior'
    ]);
  } else if (kind.includes('passivitytrigger')) {
    return pick(node, [
      ...base, 'NodeKind', 'Inputs', 'Outputs',
      'RecursionBehavior', 'anchorPoints', 'ReTryNum'
    ]);
  } else {
    return pick(node, base); // 未识别类型：仅保留共通字段
  }
}


/** 精简 edge 结构 */
function slimEdge(edge) {
  return pick(edge, [
    'id',
    'source', 'target',
    'sourceAnchor', 'targetAnchor',
    'targetAnchorID','sourceAnchorID'
  ]);
}

/** 将字符串中的非 ASCII 字符编码为 \uXXXX */
function encodeUnicode(str) {
  return str.split('').map(ch => {
    const code = ch.charCodeAt(0);
    return code > 127 ? "\\u" + ("0000" + code.toString(16)).slice(-4) : ch;
  }).join('');
}

/* ---------- 主函数 ---------- */
function saveFunction() {
  /* === 生成默认文件名 === */
  let defaultFileName = FileName === '' ? 'New WorkFlow' : FileName;
  defaultFileName = defaultFileName.replace(/^.*:/, '');     // 去掉前缀

  /* === 创建对话框 === */
  const saveDialog = document.createElement('div');
  saveDialog.innerHTML = `
    <div style="background:#fff;padding:20px;border-radius:5px;box-shadow:0 2px 10px rgba(0,0,0,.2);">
      <h3 style="color:#000">Save WorkFlow</h3>
      <input  id="saveFileName" value="${defaultFileName}"
              style="width:100%;margin-bottom:10px;padding:5px">
      <button id="confirmSave">Save</button>
      <button id="cancelSave">Cancel</button>
    </div>`;
  saveDialog.style.cssText = `
    position:fixed;inset:0;background:rgba(0,0,0,.5);
    display:flex;align-items:center;justify-content:center;z-index:1000`;
  document.body.appendChild(saveDialog);

  const fileNameInput = document.getElementById('saveFileName');
  const confirmBtn    = document.getElementById('confirmSave');
  const cancelBtn     = document.getElementById('cancelSave');

  /* === 确认保存 === */
  confirmBtn.onclick = function () {
    const saveName = fileNameInput.value.trim();
    if (!saveName) return alert('Please enter a valid file name.');

    /* 1) 取得完整数据并“瘦身” */
    const raw   = graph.save();                 // { nodes: [...], edges: [...] }
    const slimGraph  = {
      nodes: raw.nodes.map(slimNode),
      edges: raw.edges.map(slimEdge)
    };

    /* 2) 对字符串进行 Unicode 编码 */
    const encoded = encodeUnicode(JSON.stringify(slimGraph));

    /* 4) 发送到后端 */
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/save', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = function () {
      if (xhr.readyState === 4 && xhr.status === 200) {
        alert('Saved successfully!');
        FileName = saveName;
        document.title = Callsign + ':' + FileName;
      }
    };


    let safePath = FilePath;          // 原值
    if (!safePath || safePath === '.' || safePath === '/') {
      safePath = 'WorkFlow';          // 空或无效时统一存根目录
    }

    xhr.send(JSON.stringify({
      callsign: Callsign, // 传入 Callsign
      name: saveName,
      data: encoded,   // 字符串！
      path: safePath,        // 一定存在的路径
      host: HostPost, // 传入 HostPost
      callsign: Callsign, // 传入 Callsign
    }));


    document.body.removeChild(saveDialog);      // 关闭弹窗
  };

  /* === 取消保存 === */
  cancelBtn.onclick = () => document.body.removeChild(saveDialog);

  fileNameInput.focus();
}

function AddWorkflowNode(nodes, position) {
    const folder = (nodes && nodes.folder) || 'WorkFlow';

    fetch('/get-project-files', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        json_name: (nodes && nodes.name) ? nodes.name + '.json' : 'default.json',
        json_path: folder 
      })
    })
    .then(resp => resp.json())
    .then(data => {
      const currentData = graph.save();
      const currentNodes = currentData.nodes || [];
      const currentEdges = currentData.edges || [];
      console.log('当前数据:', data.nodes, data.edges);
      // 拿到远端新数据
      // 优先取 data.nodes.nodes，有则用，否则用 data.nodes
      let newNodes = [];
      let newEdges = [];
      if (data.nodes) {
        if (Array.isArray(data.nodes.nodes) && data.nodes.nodes.length > 0) {
          newNodes = data.nodes.nodes;
        } else if (Array.isArray(data.nodes) && data.nodes.length > 0) {
          newNodes = data.nodes;
        }
        if (Array.isArray(data.nodes.edges) && data.nodes.edges.length > 0) {
          newEdges = data.nodes.edges;
        } else if (Array.isArray(data.edges) && data.edges.length > 0) {
          newEdges = data.edges;
        }
      }
      console.log('newNodes:', newNodes, 'newEdges:', newEdges);
      if (!Array.isArray(newNodes) || newNodes.length === 0) {
        console.error("导入的工作流数据中没有节点！");
        return;
      }
      newNodes.forEach((node) => {
        /* ① 复位运行状态 */
        node.IsBlock   = false;
        node.IsRunning = false;
        node.IsError   = false;
        node.isFinish  = false;

        /* ② >>> 立刻给每个节点补 anchorPoints <<< */
        const inLen  = node.Inputs  ? node.Inputs.length  : 0;
        const outLen = node.Outputs ? node.Outputs.length : 0;
        const maxHeight = Math.max(inLen, outLen) * 20 + 60;   // ← 关键修正

        node.anchorPoints = [
          ...Array.from({ length: inLen  }, (_, i) => [0.05, (60 + i * 20) / maxHeight]),
          ...Array.from({ length: outLen }, (_, i) => [0.95, (60 + i * 20) / maxHeight]),
          [0, 0]
        ];

        /* ③ 异步获取额外信息（可选覆盖） */
        const n = node.name.split('.py')[0];
        requestNodeInfo(n).then((info) => {
          if (node.IsLoadSuccess !== info.IsLoadSuccess) node.IsLoadSuccess = info.IsLoadSuccess;
          /* 若想用 info.Inputs / Outputs 覆盖，可在此重新计算 anchorPoints */
        });
      });
      // 现有节点/边 ID
      const existingNodeIds = new Set(currentNodes.map(n => n.id));
      const existingEdgeIds = new Set(currentEdges.map(e => e.id));
      // 现有节点名称
      const existingNames = new Set(currentNodes.map(n => n.name));

      // 计算出目前最大的数字后缀（仅用来做简单递增），也可以完全不用管老数据
      let nodeIndex = existingNodeIds.size; 
      let edgeIndex = existingEdgeIds.size; 

      // 映射：旧节点ID -> 新节点ID
      const idMapping = {};

      // 处理新节点：不解析老 ID，直接统一生成
      const processedNodes = newNodes.filter(n => n).map(node => {
        // 生成一个从1开始累加的 'node' + index
        let newId = `node${++nodeIndex}`;
        // 确保不重复（极端情况下循环检查）
        while (existingNodeIds.has(newId)) {
          newId = `node${++nodeIndex}`;
        }
        existingNodeIds.add(newId);

        // 处理名称重复
        let newName = node.name || newId;
        if (existingNames.has(newName)) {
          let suffix = 1;
          const baseName = newName;
          while (existingNames.has(`${baseName} (${suffix})`)) {
            suffix++;
          }
          newName = `${baseName}`;
        }
        existingNames.add(newName);

        // 记录映射关系
        idMapping[node.id] = newId;

        return {
          ...node,
          id: newId,
          name: newName,
          IsRunning: false,
          IsBlock: false,
          x: (position.x || 0) + (node.x || 0),
          y: (position.y || 0) + (node.y || 0)
        };
      });

      // 处理新边：同理，完全重造 ID，不管老的是什么
      const processedEdges = newEdges.filter(e => e).map(edge => {
        let newEdgeId = `edge${++edgeIndex}`;
        while (existingEdgeIds.has(newEdgeId)) {
          newEdgeId = `edge${++edgeIndex}`;
        }
        existingEdgeIds.add(newEdgeId);

        // source/target 用到刚才节点映射
        const newSource = idMapping[edge.source] || edge.source;
        const newTarget = idMapping[edge.target] || edge.target;

        return {
          ...edge,
          id: newEdgeId,
          source: newSource,
          target: newTarget
        };
      });

      // 合并后写回
      const mergedNodes = [...currentNodes, ...processedNodes];
      const mergedEdges = [...currentEdges, ...processedEdges];

      ChangeDatas({
        nodes: mergedNodes,
        edges: mergedEdges
      });

      console.log('导入完成', { nodeCount: mergedNodes.length, edgeCount: mergedEdges.length });
    })
    .catch(e => console.error("请求工作流数据出错:", e));
}

document.body.addEventListener('dragover', (event) => {
  event.preventDefault(); // 阻止默认行为
});
function adjustHeightBasedOnContent(textarea) {
  console.log("Adjusting height...");

  // 清除之前的高度设置
  textarea.style.height = 'auto';

  // 直接使用 textarea 的 scrollHeight 来计算高度
  const computedHeight = textarea.scrollHeight;
  console.log(`Computed height: ${computedHeight}px`);

  // 设置textarea的高度，限制高度在60px到400px之间
  const newHeight = Math.max(Math.min(computedHeight, 400), 60);
  textarea.style.height = `${newHeight}px`;
  console.log(`Textarea height set to: ${newHeight}px`);
}


function InitFunction() {
  fetch('/get-python-files')
      .then(response => response.json())
      .then(data => {
          data.forEach(function(file_info) {
              fileInfoArray.push({
                  filename: file_info.filename,
              });
          });
      })
      .catch(error => console.error('Error:', error));
}


document.body.addEventListener('drop', (event) => {
  event.preventDefault(); // 阻止默认的拖放事件行为，这是必须的以避免浏览器默认打开文件

  const files = event.dataTransfer.files; // 获取拖放的文件列表
  if (files.length > 0) {
      const file = files[0]; // 取第一个文件
      if (file.type === "application/json") { // 检查文件类型是否为JSON
          // 弹出确认框询问用户是否确认导入新的项目
          if (confirm("你确定要导入新的项目吗？他会清除其他所有的Nodes。")) {
              graph.clear(); // 清除图表中的所有节点

              const reader = new FileReader(); // 创建一个用于读取文件的 FileReader
              reader.onload = (e) => { // 文件读取完成时触发的事件
                let dates = JSON.parse(e.target.result);
                  LoadWorkFlow(dates,file.name,'',''); // 读取文件内容并加载到图表中
              };
              reader.readAsText(file); // 以文本形式读取文件
          }
      } else {
          console.log("Please drop a JSON file."); // 如果文件类型不是JSON，提示用户
      }
  }
});
function extractTempData(dates) {
  let Tempdata;
  if (dates && typeof dates === 'object') {
    // 如果第一层有 nodes 属性
    if ('nodes' in dates) {
      // 如果第二层也有 nodes
      if (dates.nodes && 'nodes' in dates.nodes) {
        Tempdata = dates.nodes;
      }
      // 只有一级 nodes
      else {
        Tempdata = dates
      }
    }
    // 没有 nodes，直接就是数据本身
    else {
      Tempdata = dates;
    }
  } else {
    // 如果 dates 不是对象（比如直接就是数组或其他类型），也直接返回
    Tempdata = dates;
  }

  return Tempdata;
}
function LoadWorkFlow(dates, fileName, HostPost, Callsign) {
  isDropingFile = true;
  Tempdata=extractTempData(dates);
  console.log('导入数据:', Tempdata);

  /* === 先遍历节点，同步生成 anchorPoints === */
  Tempdata.nodes.forEach((node) => {
    /* ① 复位运行状态 */
    node.IsBlock   = false;
    node.IsRunning = false;
    node.IsError   = false;
    node.isFinish  = false;

    /* ② >>> 立刻给每个节点补 anchorPoints <<< */
    const inLen  = node.Inputs  ? node.Inputs.length  : 0;
    const outLen = node.Outputs ? node.Outputs.length : 0;
    const maxHeight = Math.max(inLen, outLen) * 20 + 60;   // ← 关键修正

    node.anchorPoints = [
      ...Array.from({ length: inLen  }, (_, i) => [0.05, (60 + i * 20) / maxHeight]),
      ...Array.from({ length: outLen }, (_, i) => [0.95, (60 + i * 20) / maxHeight]),
      [0, 0]
    ];

    /* ③ 异步获取额外信息（可选覆盖） */
    const n = node.name.split('.py')[0];
    requestNodeInfo(n).then((info) => {
      if (node.IsLoadSuccess !== info.IsLoadSuccess) node.IsLoadSuccess = info.IsLoadSuccess;
      /* 若想用 info.Inputs / Outputs 覆盖，可在此重新计算 anchorPoints */
    });
  });

  /* === 文件名 & Callsign 处理 === */
  FileName = fileName.replace('.json', '');
  FileName = FileName.substring(FileName.lastIndexOf(':') + 1);
  if (Callsign != null) FileName = Callsign + ':' + FileName;
  document.title = FileName;
  console.log('当前文件名:', FileName, 'Callsign:', Callsign, 'HostPost:', HostPost);
  /* === 根据 HostPost / Callsign 给特殊节点赋值 === */
  if (HostPost !== '') {
    Tempdata.nodes.forEach((n) => {
      if (n.NodeKind.includes('passivityTrigger')) {
        n.Inputs[0].Context = HostPost;
        n.Inputs[0].IsLabel = true;
      }
      if (n.NodeKind.includes('TeamWork')) {
        n.Inputs[0].Context = HostPost;
        n.Inputs[0].IsLabel = true;
        n.Inputs[1].Context = Callsign;
        n.Inputs[1].IsLabel = true;
      }
    });
  }
  if (Callsign !== '') {
    Tempdata.nodes.forEach((n) => {
      if (n.NodeKind.includes('passivityTrigger')) {
        n.Inputs[1].Context = Callsign;
        n.Inputs[1].IsLabel = true;
      }
    });
  }

  /* === 统一刷新一次，确保 anchorPoints 已存在 === */
  ChangeDatas(Tempdata);
  data=graph.save();
  isDropingFile = false;
  RefreshEdge();
}

function computeCenter(nodes) {
  if (!nodes || nodes.length === 0) {
    console.warn('节点数组为空或未定义');
    return { x: 0, y: 0 }; // 返回默认值
  }

  let sumX = 0;
  let sumY = 0;

  // 遍历所有节点，累加 x 和 y 坐标
  nodes.forEach((node) => {
    if (typeof node.x === 'number' && typeof node.y === 'number') {
      sumX += node.x;
      sumY += node.y;
    } else {
      console.warn('节点坐标无效:', node);
    }
  });

  // 计算平均值
  const centerX = sumX / nodes.length;
  const centerY = sumY / nodes.length;

  return { x: centerX, y: centerY };
}
function ReCreactNodes(NodeList) {
  const parsedJson = JSON.parse(NodeList);
  //console.log(parsedJson,parsedJson.nodes[0].position.x,parsedJson.nodes[0].position.y);
  // 清除 newArray
  parsedJson.nodes.nodes.forEach(function(newItem) {
    var matchFound = false;
    fileInfoArray.forEach(function(fileInfoItem) {
        addNode(fileInfoItem.filename.replace(".py", ""), newItem.x, newItem.y,fileInfoArray.NodeKind);
        matchFound = true;
    });
  });
  //console.log('解析',graph.save());
  let data = graph.save()
  data.edges = parsedJson.nodes.edges;
  //console.log(parsedJson,parsedJson.nodes[0].position.x,parsedJson.nodes[0].position.y);
  // 清除 newArray
  ChangeDatas(data);
  //Moving(parsedJson.viewCenter.x,parsedJson.viewCenter.y);
}
