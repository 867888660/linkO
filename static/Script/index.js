

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
let isRecordMode = false;
let recordModeBaseGraph = null;
let recordModeTempMessageBackup = null;
let recordItemsCache = [];
let recordModeCurrentFilename = '';
// 记录面板：避免 annotate 时 O(N^2) 的 DOM 扫描
let recordPanelButtonMap = new Map(); // filename -> button element
// 记录列表后台标注任务：用于取消/防止并发把前后端拖慢
let recordAnnotateController = null;
let recordAnnotateToken = 0;
const RECORD_ANNOTATE_CONCURRENCY = 2;        // 并发过高会把 /history/run 与 UI 都拖慢
const RECORD_ANNOTATE_MAX_ITEMS = 200;        // 记录太多时不做全量标注，避免“越多越卡”
const RECORD_DEEP_SEARCH_MAX_ITEMS = 50;      // 只有少量记录时才构建 Inputs/Outputs 的深度搜索文本
let recordSearchRefilterTimer = null;

function cancelRecordAnnotation(reason = '') {
  // 递增 token 使已排队/延迟启动的任务自动失效
  recordAnnotateToken++;
  try {
    if (recordAnnotateController) {
      recordAnnotateController.abort(reason || 'cancelRecordAnnotation');
    }
  } catch (_) {}
  recordAnnotateController = null;
}

function scheduleRecordSearchIndexBuild(query, refilterFn) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return;
  if (!Array.isArray(recordItemsCache) || !recordItemsCache.length) return;
  // 搜索时优先级最高：取消正在进行的后台标注，避免占用网络/主线程
  cancelRecordAnnotation('search build');
  const token = ++recordAnnotateToken;
  recordAnnotateController = new AbortController();
  // 记录很多时也允许构建搜索索引，但仍然做数量/并发限制
  annotateRecordItemsWithErrorFlag(recordItemsCache, {
    token,
    signal: recordAnnotateController?.signal,
    enableDeepSearch: true,
    // 搜索索引比错误标记更“有用”，这里允许多处理一些（仍然要限流）
    maxItems: Math.max(RECORD_ANNOTATE_MAX_ITEMS, 600),
    onItemUpdated: () => {
      if (typeof refilterFn !== 'function') return;
      try {
        if (recordSearchRefilterTimer) clearTimeout(recordSearchRefilterTimer);
        recordSearchRefilterTimer = setTimeout(() => {
          try { refilterFn(); } catch(_) {}
        }, 120);
      } catch(_) {}
    }
  });
}
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
  // 新一轮节点运行前重置一次性打印标记
  try { window.__RUN_SUMMARY_PRINTED__ = false; window.__RUN_PROGRESS_PRINTED__ = false; } catch(_) {}
  const isCheckMode = document.getElementById('runButton').textContent !== '运行';
  
  // 根据全局静默开关决定是否输出调试日志
  const originalDebugLogAll = window.DEBUG_LOG_ALL;
  window.DEBUG_LOG_ALL = !window.LOG_SILENT;
  
  // 打印与这个组件相关的所有信息
  if (!window.LOG_SILENT) {
    console.log('[RUN:DEBUG] === runNode 调试信息 ===');
    console.log('[RUN:DEBUG] 传入的 item:', item);
    console.log('[RUN:DEBUG] isCheckMode:', isCheckMode);
    try { console.log('[RUN:DEBUG] LOG FLAGS => ALL:', window.DEBUG_LOG_ALL, 'ALLOW_PREFIXES:', window.DEBUG_LOG_ALLOW_PREFIXES); } catch(_) {}
  }
  
  // 查找对应的节点数据
  const nodeData = graph.save().nodes.find(n => n.id === item.id);
  if (!window.LOG_SILENT) console.log('[RUN:DEBUG] graph 中的节点数据:', nodeData);
  
  // 查找 TempMessageNode 中的对应节点
  const tempNode = TempMessageNode?.nodes?.find(n => n.id === item.id);
  if (!window.LOG_SILENT) console.log('[RUN:DEBUG] TempMessageNode 中的节点数据:', tempNode);

  // 查找最近活跃快照中的对应节点
  let latestNode = null;
  try {
    const latestGraph = getLatestActiveGraph();
    latestNode = latestGraph?.nodes?.find(n => n.id === item.id) || null;
    if (!window.LOG_SILENT) console.log('[RUN:DEBUG] latestActiveGraph 节点数据:', latestNode);
  } catch(_) { if (!window.LOG_SILENT) console.log('[RUN:DEBUG] 读取 latestActiveGraph 失败'); }
  
  // 打印节点的关键字段
  if (tempNode) {
    if (!window.LOG_SILENT) {
      console.log('[RUN:DEBUG] 节点关键字段:');
      console.log('[RUN:DEBUG] - NodeKind:', tempNode.NodeKind);
      console.log('[RUN:DEBUG] - label:', tempNode.label);
      console.log('[RUN:DEBUG] - ExportPrompt:', tempNode.ExportPrompt);
      console.log('[RUN:DEBUG] - SystemPrompt:', tempNode.SystemPrompt);
      console.log('[RUN:DEBUG] - status:', tempNode.status);
      console.log('[RUN:DEBUG] - isFinish:', tempNode.isFinish);
      console.log('[RUN:DEBUG] - Inputs 数量:', tempNode.Inputs?.length || 0);
      console.log('[RUN:DEBUG] - Outputs 数量:', tempNode.Outputs?.length || 0);
      console.log('[RUN:DEBUG] - debug 长度:', tempNode.debug?.length || 0);
    }
  }
  if (nodeData) {
    if (!window.LOG_SILENT) {
      console.log('[RUN:DEBUG] graph 节点关键字段:');
      console.log('[RUN:DEBUG] - prompt:', nodeData.prompt);
      console.log('[RUN:DEBUG] - ExportPrompt:', nodeData.ExportPrompt);
      console.log('[RUN:DEBUG] - SystemPrompt:', nodeData.SystemPrompt);
    }
  }
  if (latestNode) {
    if (!window.LOG_SILENT) {
      console.log('[RUN:DEBUG] latestActiveGraph 节点关键字段:');
      console.log('[RUN:DEBUG] - prompt:', latestNode.prompt);
      console.log('[RUN:DEBUG] - ExportPrompt:', latestNode.ExportPrompt);
      console.log('[RUN:DEBUG] - SystemPrompt:', latestNode.SystemPrompt);
    }
  }
  
  // 打印当前工作流状态
  if (!window.LOG_SILENT) {
    console.log('[RUN:DEBUG] 当前工作流状态:');
    console.log('[RUN:DEBUG] - IsRunningFunction:', IsRunningFunction);
    console.log('[RUN:DEBUG] - ProjectName:', ProjectName);
    console.log('[RUN:DEBUG] - TempMessageNode 节点总数:', TempMessageNode?.nodes?.length || 0);
  }
  
  // 如果 TempMessageNode 中该节点仍保留“有意义的数据”，则强制走检查视图（避免按钮文本恢复为“运行”导致看不到结果）
  let hasTempMeaning = false;
  try {
    const tn = TempMessageNode?.nodes?.find(n => n.id === item.id);
    if (tn) {
      const hasOut = Array.isArray(tn.Outputs) && tn.Outputs.some(o => o && (o.Context || o.Num !== null && o.Num !== undefined || o.Boolean === true));
      const hasDbg = typeof tn.debug === 'string' && tn.debug.trim().length > 0;
      const hasPrompt = typeof tn.ExportPrompt === 'string' && tn.ExportPrompt.trim().length > 0;
      hasTempMeaning = !!(hasOut || hasDbg || hasPrompt);
    }
  } catch(_) {}
  // 仅当明确传入检查模式时才进入检查视图，避免历史残留导致按钮消失
  const effectiveCheckMode = !!isCheckMode;

  if (!window.LOG_SILENT) console.log('[RUN:DEBUG] === runNode 调试信息结束 ===');
  
  // 恢复原来的日志设置
  window.DEBUG_LOG_ALL = originalDebugLogAll;
  
  createSideWindow(item, effectiveCheckMode);
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
  const titleText = nodeInfo.filename.replace(/\.py$/, '');

  /* ---------- 创建浮窗（容器 + 标题 + 正文） ---------- */
  const floatingWindow = document.createElement('div');
  floatingWindow.classList.add('node-detail-floating-window');

  // 设置浮窗样式（更易读的配色与排版）
  Object.assign(floatingWindow.style, {
    position: 'fixed',
    backgroundColor: '#1f1f1f',
    border: '1px solid #3a3a3a',
    color: '#eaeaea',
    padding: '14px 16px 12px',
    borderRadius: '10px',
    boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
    transition: 'opacity 0.12s ease-out',
    opacity: '1',
    zIndex: 1000,
    maxWidth: 'min(60vw, 720px)',
    maxHeight: '70vh',
    overflow: 'auto',
    fontFamily: 'ui-sans-serif, -apple-system, Segoe UI, Arial, sans-serif',
    userSelect: 'text',
    WebkitFontSmoothing: 'antialiased'
  });

  // 标题
  const header = document.createElement('div');
  header.textContent = titleText;
  Object.assign(header.style, {
    fontSize: '16px',
    fontWeight: '700',
    letterSpacing: '0.2px',
    marginBottom: '10px',
    color: '#ffffff'
  });

  // 复制按钮（可选）
  const copyBtn = document.createElement('button');
  copyBtn.textContent = '复制';
  Object.assign(copyBtn.style, {
    position: 'absolute',
    top: '8px',
    right: '10px',
    fontSize: '12px',
    padding: '4px 8px',
    color: '#dbe7ff',
    background: '#2b3b7a',
    border: '1px solid #445aa8',
    borderRadius: '6px',
    cursor: 'pointer'
  });
  copyBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const text = `${titleText}\n${introductionText}`;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).catch(() => {});
    } else {
      // 兼容降级
      const ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch(_) {}
      document.body.removeChild(ta);
    }
  });

  // 正文
  const body = document.createElement('div');
  body.textContent = introductionText;
  Object.assign(body.style, {
    whiteSpace: 'pre-wrap',    // 保留换行并自动换行
    overflowWrap: 'anywhere',  // 超长单词也可换行
    wordBreak: 'break-word',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace',
    fontSize: '13.5px',
    lineHeight: '1.7'
  });

  // 装配
  floatingWindow.appendChild(header);
  floatingWindow.appendChild(body);
  floatingWindow.appendChild(copyBtn);


  // 若获取到了点击位置，则在鼠标下方显示
  let initialTop = 150;
  let initialLeft = 150;
  if (event && typeof event.clientX === 'number' && typeof event.clientY === 'number') {
    initialTop = event.clientY + 12;
    initialLeft = event.clientX + 12;
  }
  floatingWindow.style.top = initialTop + 'px';
  floatingWindow.style.left = initialLeft + 'px';

  // 将浮窗添加到页面中
  document.body.appendChild(floatingWindow);

  // 防止超出视口：如果溢出则向内收回
  try {
    const rect = floatingWindow.getBoundingClientRect();
    const pad = 8;
    let top = rect.top;
    let left = rect.left;
    if (rect.right > window.innerWidth - pad) left = Math.max(pad, window.innerWidth - rect.width - pad);
    if (rect.bottom > window.innerHeight - pad) top = Math.max(pad, window.innerHeight - rect.height - pad);
    floatingWindow.style.top = Math.max(pad, top) + 'px';
    floatingWindow.style.left = Math.max(pad, left) + 'px';
  } catch(_) {}

  // 定义淡出并移除浮窗的函数
  function fadeOutAndRemove() {
    floatingWindow.style.opacity = '0';
    setTimeout(() => {
      if (floatingWindow && floatingWindow.parentNode) {
        floatingWindow.parentNode.removeChild(floatingWindow);
      }
    }, 800);
  }

  // 定义一个 hideTimeout 用于控制自动消失
  let hideTimeout = null;

  // 开启 6 秒后自动淡出移除（阅读更从容）
  function startHideTimer() {
    // 如果已有计时器，则先清除
    clearHideTimer();
    hideTimeout = setTimeout(() => {
      fadeOutAndRemove();
    }, 6000);
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
        ParallelLimit:node.ParallelLimit !== undefined ? node.ParallelLimit : 1, // 并行数量限制
        prompt: node.prompt,
        SystemPrompt:node.SystemPrompt,
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
    console.warn('[nodeInfo]', nodeInfo);
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
      ParallelLimit: 1, // 并行数量限制，默认1（仅用于 ArrayTrigger）
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
      const set = (c, w) => shape.attr({ stroke:c, lineWidth:w, shadowBlur:0, opacity:1 });

      if      (s.includes(STATE.RED))    set('#ff4d4f', 6);
      else if (s.includes(STATE.BLUE))   set('#32d7ff', 5);
      else if (s.includes(STATE.GREEN))  set('#30c57b', 4);
      else if (s.includes(STATE.ORANGE)) set('#fa8c16', 4);
      else if (s.includes(STATE.PURPLE)) set('#e205ff', 4);
      else                               set('#000',     3);
    };

    switch (name) {
      /* ——— 高亮 ——— */
      case STATE.RED:
        value ? shape.attr({ stroke:'#ff4d4f', lineWidth:6, shadowColor:'#ff6d6f', shadowBlur:8 }) : back();
        break;
      case STATE.BLUE:
        value ? shape.attr({ stroke:'#32d7ff', lineWidth:5, shadowColor:'#32d7ff', shadowBlur:8 }) : back();
        break;

      /* ——— 常驻底色 ——— */
      case STATE.GREEN:  value ? back() : back(); break;
      case STATE.ORANGE: value ? back() : back(); break;
      case STATE.PURPLE: value ? back() : back(); break;

      /* ——— 流动动画（仅在允许时启动） ——— */
      case STATE.FLOW: {
        // 先统一停一次，避免重复叠加动画
        if (shape.stopAnimate) shape.stopAnimate();

        if (value) {
          // 允许流动的条件：未暂停 且（默认认为在运行，或你自己定义的运行标记为真）
          const paused = document.getElementById('runButton').textContent == '运行'
          // 若你项目有 isWorkflowRunning / currentWorkflowId 等标记，可按需增强条件：
          const running = (window && typeof window.isWorkflowRunning !== 'undefined')
                          ? !!window.isWorkflowRunning
                          : true; // 没有标记时默认允许

          if (!running || paused) {
            // 不允许：立刻复位虚线样式并回到底色
            shape.attr({ lineDash:null, lineDashOffset:0 });
            back();
            break;
          }

          // 允许：开启流动动画（先设定一次虚线，避免启动画前闪烁）
          shape.attr({ lineDash: [12, 6], lineDashOffset: 0 });
          let i = 0;
          shape.animate(() => {
            i = (i + 1) % 12;
            return { lineDash: [12, 6], lineDashOffset: -i };
          }, { repeat:true, duration:3000, easing:'easePolyInOut' });
        } else {
          // 显式关闭：停动画 + 复位
          shape.attr({ lineDash:null, lineDashOffset:0 });
          back();
        }
        break;
      }

      default: break;
    }
  },

  /* ---- 贝塞尔控制点（保持你的逻辑） ---- */
  getControlPoints(cfg) {
    const { startPoint, endPoint } = cfg;
    const midX   = (startPoint.x + endPoint.x - 100) / 2;
    const segLen = 20;
    return [
      { x: midX,                  y: startPoint.y },
      { x: endPoint.x - 100,      y: endPoint.y },
      { x: endPoint.x - segLen/2, y: endPoint.y }
    ];
  },

  /* ---- 默认样式（保持你的样式） ---- */
  options: {
    style: {
      lineWidth : 3,
      stroke    : '#666',
      endArrow  : { path:'M 0,0 L 6,3 L 0,6 Z', d:6, fill:'#666' },
      lineAppendWidth : 8,
      shadowBlur      : 0,
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
     //
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
    maxWidth = maxWidth + 140; // 增加基础宽度：(左右padding 24*2) + (锚点预留 16*2) + (中间间距)
    // 确保有一个最小宽度，避免内容很少时卡片太窄不好看
    maxWidth = Math.max(maxWidth, 200); 
    
    cfg.height = maxHeight * 28;
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
          height: 70 + maxHeight * 24.3,
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
        height: 60 + maxHeight * 24.3,
        stroke: 'rgba(0,0,0,0.08)', // 极细的淡灰边框，更现代
        lineWidth: 1,
        radius: 12, // 增大圆角，更有 iOS 卡片感
        fill: '#ffffff', // 纯白底色，干净
        shadowColor: 'rgba(0, 0, 0, 0.08)', // 柔和的弥散阴影
        shadowBlur: 16,
        shadowOffsetX: 0,
        shadowOffsetY: 4,
      },
      name: 'rect',
    });// 最外层灰色的框
    const shape = group.findById('rect'); // 通过 id 获取矩形图形
    let TitleColor = 'rgb(3,197,136)';
    // 映射苹果风格的颜色 (保持原有色相，但调整饱和度和明度以适应 Apple Design)
    let HeaderFill = '#34C759'; // Default Green (Apple Style)
    
    if (cfg.NodeKind == undefined) {
      cfg.NodeKind = 'Normal';
    }
    if (cfg.IsLoadSuccess == false) {
      TitleColor = '#ff0000'; 
      HeaderFill = '#FF3B30'; // Apple Red
    } else if (cfg.NodeKind.includes('LLm')) {
      TitleColor = '#009fcb';
      HeaderFill = '#007AFF'; // Apple Blue
    } else if (cfg.NodeKind == 'IfNode') {
      TitleColor = '#b300ff';
      HeaderFill = '#AF52DE'; // Apple Purple
    } else if (cfg.NodeKind.includes('passivityTrigger')) {
      TitleColor = '#ff9100';
      HeaderFill = '#FF9500'; // Apple Orange
    } else if (cfg.NodeKind.includes('ArrayTrigger')) {
      TitleColor = '#e75500';
      HeaderFill = '#FF2D55'; // Apple Pink/Red
    } else {
        // Normal / Default
        HeaderFill = '#34C759'; // Apple Green
    }

    group.addShape('rect', {
      attrs: {
        x: 0,
        y: 0,
        width: maxWidth,
        height: 44, // 稍微增加标题栏高度，留出呼吸感
        radius: [12, 12, 0, 0], // 顶部的圆角跟随外框
        fill: HeaderFill, // 使用优化后的颜色
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
        x: 24, // 稍微增加左边距
        y: 22, // 垂直居中 (44/2)
        //text: cfg.name.replace(".py", ""),
        text: cfg.label,
        fill: '#fff',
        textBaseline: 'middle',
        fontWeight: 600, // Semibold
        fontSize: 15, // 稍微调小一点，更精致
        fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif', // 苹果字体栈
        textAlign: 'left',
        shadowColor: 'rgba(0,0,0,0.1)', // 增加一点文字投影，增加层次
        shadowBlur: 2,
        shadowOffsetX: 0,
        shadowOffsetY: 1
      },
      capture: false,
      name: 'nameText',
    }); // 文件名的文字
    cfg.Inputs.map((input, index) => {
      let Temp=''
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
          x: 16, // 左对齐
          y: 58 + index * 24, // 增加行高间距 (20->24)，增加呼吸感
          text: input.name+Temp, // 使用 input.Id 替代 name
          fill: '#1d1d1f', // Apple Dark Gray
          textBaseline: 'top',
          fontWeight: 500, // Medium
          fontSize: 13, // 更加精致的字号
          fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif',
          textAlign: 'left',
        },
        capture: false,
        name: 'nameText',
      });
    }); // Inputs 标题文字

    cfg.Outputs.map((output, index) => {
      group.addShape('text', {
        attrs: {
          x: maxWidth - 16, // 右对齐
          y: 58 + index * 24, // 增加行高间距
          text: output.name,
          fill: '#1d1d1f', // Apple Dark Gray
          textBaseline: 'top',
          fontWeight: 500, // Medium
          fontSize: 13,
          fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif',
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
                        y: 58 + i * 24 + 6, // 精确对齐文本中心：y(58) + 字体大小的一半(13/2≈6.5)
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
                        y: 58 + i * 24 + 6, // 精确对齐文本中心：y(58) + 字体大小的一半(13/2≈6.5)

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
                      y: 58 + i * 24 + 6,

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
              y: (60 + maxHeight * 24.3) * anchorPos[1], // 位置 Y
              fill: '#fff', // 背景颜色
              stroke: '#5F95FF', // 边框颜色
            },
            name: 'num-input-box', // 名称，用于搜索
          });
          group.addShape('text', { // 使用 text 形状在输入框中显示默认值
            attrs: {
              text: '0', // 默认值
              x: 15, // 位置 X，稍微偏移以居中显示
              y: (60 + maxHeight * 24.3) * anchorPos[1] + 15, // 位置 Y，稍微偏移以居中显示
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
                      y: 58 + (i - cfg.Inputs.length) * 24 + 6,
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
      // 精确计算每个点的 y 坐标比例，确保与圆圈绘制位置完全一致
      const yPos = (58 + i * 24 + 6) / (60 + maxHeight * 24.3);

      if(i < cfg.Inputs.length)
      {
        anchorPos[0] = 6/maxWidth;
        // 只有 Inputs 和 Outputs 需要重新计算 y，因为它们是按列表排列的
        anchorPos[1] = (58 + i * 24 + 6) / (60 + maxHeight * 24.3);
      }
      else if(i >= cfg.Inputs.length && i < cfg.Inputs.length + cfg.Outputs.length)
      {
        anchorPos[0] = (maxWidth - 7)/maxWidth;
        // 输出点的索引需要减去输入点的数量才能对应到正确的行
        const outputIndex = i - cfg.Inputs.length;
        anchorPos[1] = (58 + outputIndex * 24 + 6) / (60 + maxHeight * 24.3);
      }
      else if(i == cfg.Inputs.length + cfg.Outputs.length)
      {
        anchorPos[0]= 10/maxWidth;
        anchorPos[1]= 10/(60 + maxHeight * 24.3);
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
                showMessage("Now is Running, Nodes Is Blocking",'#ffffff');
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
      console.warn('[测试】',frontendMode)
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
      /* ---------- ① 预取常量 ---------- */
      const { source, target } = e.edge.getModel();
      const { nodes, edges } = graph.save();          // 少调用一次 graph.save()
      const targetNode = nodes.find(n => n.id === target);
      const sourceNode = nodes.find(n => n.id === source);
    
      console.log('[DBG] 新建边:', e.edge.id, 'source=', source, 'target=', target);
      console.log('[DBG] sourceNode=', sourceNode);
      console.log('[DBG] targetNode=', targetNode);
    
      /* ---------- ② 空值保护 ---------- */
      if (!sourceNode || !targetNode) {
        console.error('[DBG] ❌ 找不到 sourceNode 或 targetNode，直接移除边');
        removeEdge(e.edge);    // 你的 removeEdge 方法
        return;
      }
    
      /* ---------- ③ 计算锚点 & 更新边 ---------- */
      try {
      if (startType !== 'output') {
          let sourceAnchorID = targetNode.Outputs[targetAnchorIdx - targetNode.Inputs.length]?.Id;
          let targetAnchorID = sourceNode.Inputs[sourceAnchorIdx]?.Id;
    
          if (targetNode.NodeKind === 'IfNode') {
            sourceAnchorID = targetNode.Id;
            targetAnchorID = sourceNode.Inputs[sourceAnchorIdx]?.Id;
        }
    
          console.log('[DBG] 非 output 分支 anchorID', { sourceAnchorID, targetAnchorID });
    
        graph.updateItem(e.edge, {
          source: target,
          target: source,
            sourceAnchorID,
            targetAnchorID,
          sourceAnchor: targetAnchorIdx,
          targetAnchor: sourceAnchorIdx,
          });
    
        } else {
          /* ---------- output 分支 ---------- */
          let sourceKind = sourceNode.NodeKind || '';
          console.log('[DBG] output 分支 sourceKind=', sourceKind);
    
          const baseUpdate = {
            sourceAnchor: sourceAnchorIdx,
            targetAnchor: targetAnchorIdx,
          };
    
          if (sourceKind === 'IfNode') {
            graph.updateItem(e.edge, {
              ...baseUpdate,
              sourceAnchorID: sourceNode.Outputs[sourceAnchorIdx - sourceNode.Inputs.length]?.Id,
              targetAnchorID: targetNode.Id,
            });
          } else {
            graph.updateItem(e.edge, {
              ...baseUpdate,
              sourceAnchorID: sourceNode.Outputs[sourceAnchorIdx - sourceNode.Inputs.length]?.Id,
              targetAnchorID: targetNode.Inputs[targetAnchorIdx]?.Id,
            });
          }
        }
      } catch (err) {
        console.error('[DBG] ❌ updateItem 失败:', err);
        removeEdge(e.edge);
        return;
      }
    
      /* ---------- ④ 并行边曲率（保持原样，可按需注释） ---------- */
      graph.getEdges().forEach(edge => {
        graph.updateItem(edge, {
          // curveOffset: 0,
          // curvePosition: 0,
        });
      });
    
      /* ---------- ⑤ 检测环 ---------- */
      const cycleInfo = detectCycles(nodes, edges);
      if (cycleInfo == null) {
        console.log('[DBG] ✅ No cycles detected.');
      } else {
        console.warn('[DBG] 🔄 Cycle detected:', cycleInfo);
        setTimeout(() => {
          removeEdge(graph.findById(e.edge.id));
          alert('连接存在循环');
        }, 1);
      }
    
      /* ---------- ⑥ 刷新显示 ---------- */
      setTimeout(RefreshEdge, 10);
    
      console.log('[DBG] graph.save() ->', graph.save());
    });
    graph.on('aftercreateedge', (e) => {
      /* ---------- ① 预取常量 ---------- */
      const { source, target } = e.edge.getModel();
      const { nodes, edges } = graph.save();          // 少调用一次 graph.save()
      const targetNode = nodes.find(n => n.id === target);
      const sourceNode = nodes.find(n => n.id === source);
    
      console.log('[DBG] 新建边:', e.edge.id, 'source=', source, 'target=', target);
      console.log('[DBG] sourceNode=', sourceNode);
      console.log('[DBG] targetNode=', targetNode);
    
      /* ---------- ② 空值保护 ---------- */
      if (!sourceNode || !targetNode) {
        console.error('[DBG] ❌ 找不到 sourceNode 或 targetNode，直接移除边');
        removeEdge(e.edge);    // 你的 removeEdge 方法
        return;
      }
    
      /* ---------- ③ 计算锚点 & 更新边 ---------- */
      try {
        if (startType !== 'output') {
          let sourceAnchorID = targetNode.Outputs[targetAnchorIdx - targetNode.Inputs.length]?.Id;
          let targetAnchorID = sourceNode.Inputs[sourceAnchorIdx]?.Id;
    
          if (targetNode.NodeKind === 'IfNode') {
            sourceAnchorID = targetNode.Id;
            targetAnchorID = sourceNode.Inputs[sourceAnchorIdx]?.Id;
          }
    
          console.log('[DBG] 非 output 分支 anchorID', { sourceAnchorID, targetAnchorID });
    
          graph.updateItem(e.edge, {
            source: target,
            target: source,
            sourceAnchorID,
            targetAnchorID,
            sourceAnchor: targetAnchorIdx,
            targetAnchor: sourceAnchorIdx,
          });
    
        } else {
          /* ---------- output 分支 ---------- */
          let sourceKind = sourceNode.NodeKind || '';
          console.log('[DBG] output 分支 sourceKind=', sourceKind);
    
          const baseUpdate = {
            sourceAnchor: sourceAnchorIdx,
            targetAnchor: targetAnchorIdx,
          };
    
          if (sourceKind === 'IfNode') {
            graph.updateItem(e.edge, {
              ...baseUpdate,
              sourceAnchorID: sourceNode.Outputs[sourceAnchorIdx - sourceNode.Inputs.length]?.Id,
              targetAnchorID: targetNode.Id,
            });
          } else {
            graph.updateItem(e.edge, {
              ...baseUpdate,
              sourceAnchorID: sourceNode.Outputs[sourceAnchorIdx - sourceNode.Inputs.length]?.Id,
              targetAnchorID: targetNode.Inputs[targetAnchorIdx]?.Id,
            });
          }
        }
      } catch (err) {
        console.error('[DBG] ❌ updateItem 失败:', err);
        removeEdge(e.edge);
        return;
      }
    
      /* ---------- ④ 并行边曲率（保持原样，可按需注释） ---------- */
      graph.getEdges().forEach(edge => {
        graph.updateItem(edge, {
          // curveOffset: 0,
          // curvePosition: 0,
        });
      });
    
      /* ---------- ⑤ 检测环 ---------- */
      const cycleInfo = detectCycles(nodes, edges);
      if (cycleInfo == null) {
        console.log('[DBG] ✅ No cycles detected.');
      } else {
        console.warn('[DBG] 🔄 Cycle detected:', cycleInfo);
        setTimeout(() => {
          removeEdge(graph.findById(e.edge.id));
          alert('连接存在循环');
        }, 1);
      }
    
      /* ---------- ⑥ 刷新显示 ---------- */
      setTimeout(RefreshEdge, 10);
    
      console.log('[DBG] graph.save() ->', graph.save());
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
        showMessage("Now is Running, Nodes Is Blocking",'#ffffff');
      }
    });
    graph.on('node:drag', (e) => {
      updateDomBlock(e.item._cfg);
    });

    graph.on('afterremoveitem', () => {
      console.warn('[图测试]',graph.save());
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
  try {
    const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
    for (const edge of edges) {
      const sourceNode = byId[edge.source];
      const targetNode = byId[edge.target];
      if (!sourceNode || !targetNode) continue;

      const sInputs = (sourceNode.Inputs || []).length;
      const sOutputs = (sourceNode.Outputs || []).length;
      const tInputs = (targetNode.Inputs || []).length;
      const tOutputs = (targetNode.Outputs || []).length;

      const sAnchor = Number(edge.sourceAnchor);
      const tAnchor = Number(edge.targetAnchor);

      // 源端必须来自输出口：位于 Inputs 之后
      const isSourceOutput = sAnchor >= sInputs && sAnchor < sInputs + sOutputs;

      // 目标端必须连到输入口，或 IfNode 的触发锚点（Inputs+Outputs）
      const triggerAnchor = tInputs + tOutputs;
      const isTargetInput = tAnchor >= 0 && tAnchor < tInputs;
      const isTargetTrigger = targetNode.NodeKind === 'IfNode' && tAnchor === triggerAnchor;

      if (!(isSourceOutput && (isTargetInput || isTargetTrigger))) {
        console.warn('Invalid edge detail', {
          edge,
          source: { id: sourceNode.id, inputs: sInputs, outputs: sOutputs },
          target: { id: targetNode.id, inputs: tInputs, outputs: tOutputs, triggerAnchor },
          isSourceOutput, isTargetInput, isTargetTrigger
        });
        throw new Error(`Invalid connection from ${sourceNode.name || sourceNode.id} to ${targetNode.name || targetNode.id}`);
        }
    }
    return { nodes, edges };
  } catch (error) {
    console.error('Connection validation error:', error);
    // 即使验证失败也返回原始数据，避免阻断后续流程
    return { nodes, edges };
  }
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
const recordSelectElement = document.getElementById('recordSelect');
if (recordSelectElement) {
  recordSelectElement.addEventListener('change', (event) => {
    const filename = event.target.value;
    if (!filename) {
      return;
    }
    if (!isRecordMode) {
      event.target.value = '';
      showMessage('请先点击"记录"进入记录模式', '#ff9100');
      return;
    }
    handleRecordSelection(filename);
  });
}

// 工作流选择器
const workflowSelectElement = document.getElementById('workflowSelect');
if (workflowSelectElement) {
  workflowSelectElement.addEventListener('change', (event) => {
    const workflowId = event.target.value;
    console.warn(`[WORKFLOW-SELECTOR] 用户选择工作流: ${workflowId}`);
    if (workflowId) {
      switchToWorkflow(workflowId);
    } else {
      // 如果选择空值，清空观察
      currentObservedWorkflowId = null;
      monitoredWorkflowId = null;
      console.log('[WORKFLOW-SELECTOR] 清空观察的工作流');
    }
  });
  console.log('[WORKFLOW-SELECTOR] 工作流选择器事件监听已绑定');
} else {
  console.warn('[WORKFLOW-SELECTOR] 工作流选择器元素未找到');
}

function hideWorkflowSelector() {
  if (workflowSelectElement) {
    workflowSelectElement.style.display = 'none';
  }
}

function resetWorkflowTracking() {
  currentWorkflowId = null;
  monitoredWorkflowId = null;
  currentObservedWorkflowId = null;
}

// 解锁当前画布节点的 IsBlock，并刷新
function unlockGraphBlocks() {
  try {
    if (typeof graph === 'undefined' || !graph || !graph.save) return;
    const g = graph.save();
    if (!g || !Array.isArray(g.nodes)) return;
    g.nodes.forEach(n => {
      if (n && typeof n === 'object') n.IsBlock = false;
    });
    ChangeDatas(g);
    RefreshEdge?.();
    console.warn('[GRAPH] 已解锁节点 IsBlock');
  } catch (e) {
    console.warn('[GRAPH] 解锁 IsBlock 失败:', e);
  }
}

function resetRunButtonUI(text = '运行') {
  const btn = document.getElementById('runButton');
  if (btn) {
    btn.textContent = text;
    btn.style.backgroundColor = text === '运行完成' ? '#4CAF50' : '#1e1e1e';
  }
  const infoEl = document.getElementById('currentWorkflowInfo');
  if (infoEl && text === '运行') {
    infoEl.textContent = '当前工作流：无';
  }
}

function getQueueValue(data, key) {
  if (!data) return 0;
  const queues = data.queue_lengths || data.queues || {};
  let value = queues[key];
  if ((value === undefined || value === null) && key === 'passivity') {
    value = queues.pending;
  }
  if (typeof value === 'number') return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function formatChildSummaryText(summary) {
  if (!summary || typeof summary !== 'object') return '';
  const total = Number(summary.total) || 0;
  const completed = Number(summary.completed) || 0;
  const active = Number(summary.active) || 0;
  if (!total) return '';
  const runningText = active > 0 ? `，进行中 ${active}` : '';
  return ` · 子任务 ${completed}/${total}${runningText}`;
}

function workflowHasPassivityNodes(data) {
  const nodes = (data && data.graph_data && Array.isArray(data.graph_data.nodes)) ? data.graph_data.nodes : [];
  return nodes.some(node => node && typeof node.NodeKind === 'string' && node.NodeKind.includes('passivityTrigger'));
}

function shouldEnterMonitorCompleted(data) {
  if (!data || data.status !== 'completed') return false;
  const arrayQueue = getQueueValue(data, 'array');
  const passivityQueue = getQueueValue(data, 'passivity');
  const hasPassivity = workflowHasPassivityNodes(data);
  const childActive = Number(data?.childSummary?.active || 0);
  if (childActive > 0) return false;
  return arrayQueue === 0 && (!hasPassivity || passivityQueue === 0);
}

function enterMonitorCompletedMode(statusData, wfId) {
  console.warn('[MODE]🔒  进入 monitor_completed 模式');
  frontendMode = 'monitor_completed';
  prevFrontendMode = 'monitor';
  setWorkflowPollingInterval(0);
  stopAllAnimationsAndPolling();
  resetWorkflowTracking();
  hideWorkflowSelector();
  if (statusData?.graph_data) {
    window.__lastCompletedGraphData = structuredClone(statusData.graph_data);
  }
  window.__lastWorkflowId = wfId || null;
  window.__lastWorkflowStatus = 'completed';
  resetRunButtonUI('运行完成');
}

function handleWorkflowNotFound(wfId) {
  console.warn(`[WORKFLOW] ${wfId || ''} 不存在或已结束，停止前端同步`);
  frontendMode = 'edit';
  stopAllAnimationsAndPolling();
  setWorkflowPollingInterval(0);
  resetWorkflowTracking();
  hideWorkflowSelector();
  resetRunButtonUI('运行');
}

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

          // 统一样式（与 NodeDetail 类似），正文可直接选中复制
          Object.assign(floatingWindow.style, {
            position: 'fixed',
            backgroundColor: '#1f1f1f',
            border: '1px solid #3a3a3a',
            color: '#eaeaea',
            padding: '12px 14px 10px',
            borderRadius: '10px',
            boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
            zIndex: 1000,
            maxWidth: 'min(50vw, 640px)',
            maxHeight: '60vh',
            overflow: 'auto',
            userSelect: 'text' // 允许直接框选复制
          });

          // 解析与构造内容
          let decoded = '';
          if (typeof node.NodeFunction === 'string') {
            decoded = node.NodeFunction
              .replace(/\\\\/g, '\\')
              .replace(/\\n/g, '\n')
              .replace(/\\"/g, '"')
              .replace(/\\</g, '<')
              .replace(/\\>/g, '>');
          } else {
            decoded = 'No introduction available';
          }

          const title = document.createElement('div');
          title.textContent = (node.filename || '').replace(/\.py$/, '');
          Object.assign(title.style, {
            fontSize: '15px',
            fontWeight: '700',
            marginBottom: '8px',
            color: '#ffffff'
          });

          const body = document.createElement('div');
          body.textContent = decoded; // 文本可被直接选择复制
          Object.assign(body.style, {
            whiteSpace: 'pre-wrap',
            overflowWrap: 'anywhere',
            wordBreak: 'break-word',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace',
            fontSize: '13.5px',
            lineHeight: '1.7'
          });

          const copyBtn = document.createElement('button');
          copyBtn.textContent = '复制';
          Object.assign(copyBtn.style, {
            position: 'absolute',
            top: '6px',
            right: '8px',
            fontSize: '12px',
            padding: '3px 8px',
            color: '#dbe7ff',
            background: '#2b3b7a',
            border: '1px solid #445aa8',
            borderRadius: '6px',
            cursor: 'pointer'
          });
          copyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const text = `${title.textContent}\n${decoded}`;
            if (navigator.clipboard) {
              navigator.clipboard.writeText(text).catch(() => {});
            } else {
              const ta = document.createElement('textarea');
              ta.value = text; document.body.appendChild(ta); ta.select();
              try { document.execCommand('copy'); } catch(_) {}
              document.body.removeChild(ta);
            }
          });

          floatingWindow.appendChild(title);
          floatingWindow.appendChild(body);
          floatingWindow.appendChild(copyBtn);

          document.body.appendChild(floatingWindow);

          // 初始位置靠近鼠标
          const place = (x, y) => {
            const pad = 8;
            let left = x + 10;
            let top = y + 10;
            const rect = floatingWindow.getBoundingClientRect();
            if (left + rect.width > window.innerWidth - pad) left = Math.max(pad, window.innerWidth - rect.width - pad);
            if (top + rect.height > window.innerHeight - pad) top = Math.max(pad, window.innerHeight - rect.height - pad);
            floatingWindow.style.left = `${left}px`;
            floatingWindow.style.top = `${top}px`;
          };
          place(event.clientX, event.clientY);

          // 跟随鼠标移动
          const moveHandler = (moveEvent) => {
            place(moveEvent.clientX, moveEvent.clientY);
          };
          event.target.addEventListener('mousemove', moveHandler);

          // 清理
          const leaveHandler = () => {
            event.target.removeEventListener('mousemove', moveHandler);
            event.target.removeEventListener('mouseleave', leaveHandler);
            floatingWindow.remove();
            clearTimeout(hoverTimeout);
          };
          event.target.addEventListener('mouseleave', leaveHandler);
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
      
      const base = window.titleBase || baseTitle;
      // 预热状态：完全静态标题，无动画、无队列数
      if (window.inPreheat) {
          try { console.warn('[WFDBG:TITLE] stop-by-preheat base=', base); } catch(_) {}
          if (window.titleInterval) {
              clearInterval(window.titleInterval);
              window.titleInterval = null;
          }
          document.title = base;
          return;
      }
      const buttonText = document.getElementById('runButton')?.textContent || '';
      const buttonRunning = buttonText === '运行中...' || buttonText === '接收中...';
      // 只要有被监控的工作流存在，就认为有“活动中的工作流”，用于标题动画
      const workflowActive = !!(monitoredWorkflowId || currentWorkflowId);
      const hasRunningNodes = (TempMessageNode?.nodes || []).some(n => n.IsRunning);
      
      // 动画优先级：主要基于按钮状态，确保在"运行中"和"接收中"时持续动画
      const actualRunning = buttonRunning;
      
      // 详细打印按钮状态
      try {
        console.warn('[BUTTON-DEBUG] 按钮状态检测:', {
          buttonText: `"${buttonText}"`,
          isRunningText: buttonText === '运行中...',
          isReceivingText: buttonText === '接收中...',
          buttonRunning,
          actualRunning
        });
      } catch(_) {}
      
      // 调试打印：显示所有状态检测
      try {
        console.warn('[TITLE-DEBUG] 状态检测:', {
          buttonText,
          buttonRunning,
          workflowActive,
          hasRunningNodes,
          actualRunning,
          backendQueueLengths,
          passivityArray: passivityTriggerArray?.length || 0,
          arrayArray: ArrayTriggerArray?.length || 0
        });
      } catch(_) {}
      

      
      if (actualRunning) {
          // 增加执行计数器，确保标题数字在变化
          
          const passLen = (backendQueueLengths && typeof backendQueueLengths.passivity === 'number')
            ? backendQueueLengths.passivity
            : (passivityTriggerArray?.length || 0);
          const arrLen = (backendQueueLengths && typeof backendQueueLengths.array === 'number')
            ? backendQueueLengths.array
            : (ArrayTriggerArray?.length || 0);
          
          // 标题格式：文件名{被动触发}[数组触发]#计数器 动画
          const newTitle = `${base}{${passLen}}[${arrLen}]${animation[index]}`;
          document.title = newTitle;
          index = (index + 1) % animation.length;
          
          // 动画调试信息
          try {
            console.warn('[TITLE-ANIM] 动画运行中:', {
              newTitle,
              animationIndex: index,
              animationChar: animation[index],
              passLen,
              arrLen
            });
          } catch(_) {}
          
          // 记录队列状态变化
          const currentQueueInfo = `{${passLen}}[${arrLen}]`;
          window.lastQueueInfo = currentQueueInfo;
          // 仅在数值变化时打印，避免刷屏
          try {
            if (window.__TITLE_LAST__ !== currentQueueInfo) {
              console.warn('[WFDBG:TITLE] running base=', base, ' P=', passLen, ' A=', arrLen);
              window.__TITLE_LAST__ = currentQueueInfo;
            }
          } catch(_) {}
      } else {
          document.title = base;
          window.lastQueueInfo = null;
          try {
            if (window.__TITLE_LAST__ !== 'idle') {
              console.warn('[WFDBG:TITLE] idle base=', base);
              window.__TITLE_LAST__ = 'idle';
            }
          } catch(_) {}
      }
  }, 300); // 加快动画频率，确保能看到变化
}
// 移除页面上所有的浮窗
function removeFloatingWindows() {
  const floatingWindows = document.querySelectorAll('.LeftSideWindow_floating-window');
  floatingWindows.forEach(window => window.remove());
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

async function recoderFunction() {
  const runBtn = document.getElementById('runButton');
  const btnText = runBtn ? runBtn.textContent : '';
  // 允许在"运行"或"运行完成"状态下进入记录模式
  const canEnterRecord = btnText === '运行' || btnText === '运行完成' || frontendMode === 'monitor_completed';

  if (!isRecordMode && !canEnterRecord) {
    showMessage('仅在"运行"或"运行完成"状态下才能查看记录', '#ff9100');
    return;
  }

  if (isRecordMode) {
    exitRecordMode();
  } else {
    await enterRecordMode();
  }
}

function getProjectHistoryKey() {
  if (!ProjectName) return '';
  const noExt = ProjectName.replace(/\.json$/i, '');
  const parts = noExt.split(':');
  return (parts[parts.length - 1] || '').trim();
}

async function enterRecordMode() {
  try {
    isRecordMode = true;
    window.is_read_history = true;
    document.body.classList.add('record-mode');
    setRecordButtonState(true);
    toggleToolbarSelect(true);
    
    // 🔥 关键修复：在 monitor_completed 模式下，先确保图数据已加载
    if (frontendMode === 'monitor_completed' && window.__lastCompletedGraphData) {
      console.log('[RECORD] monitor_completed 模式：先加载完整图数据');
      const graphDataToLoad = structuredClone(window.__lastCompletedGraphData);
      
      // 🔥 确保 ProjectName 正确设置（从保存的图数据中获取）
      if (graphDataToLoad.ProjectName && !ProjectName) {
        ProjectName = graphDataToLoad.ProjectName;
        console.log('[RECORD] 从图数据中恢复 ProjectName:', ProjectName);
      }
      
      // 确保所有已完成节点的 IsBlock 为 true
      if (graphDataToLoad.nodes) {
        graphDataToLoad.nodes.forEach(node => {
          if (node && (node.isFinish || node.IsError)) {
            node.IsBlock = true;
          }
        });
      }
      ChangeDatas(graphDataToLoad);
      RefreshEdge();
      // 手动触发节点更新
      if (graphDataToLoad.nodes) {
        graphDataToLoad.nodes.forEach(node => {
          const nodeItem = graph.findById(node.id);
          if (nodeItem) {
            graph.updateItem(nodeItem, {
              IsBlock: node.IsBlock,
              IsRunning: node.IsRunning,
              isFinish: node.isFinish,
              IsError: node.IsError
            });
          }
        });
      }
      // 更新 TempMessageNode
      TempMessageNode = structuredClone({ nodes: graphDataToLoad.nodes });
      // 🔥 关键修复：保存当前图数据到记录模式专用变量，供 sidewindow 使用
      window.__recordModeCurrentGraph = structuredClone(graphDataToLoad);
      console.log('[RECORD] 图数据已加载，节点数:', graphDataToLoad.nodes?.length || 0);
    } else {
      // 非 monitor_completed 模式：使用当前图数据
      const currentGraph = graph.save();
      window.__recordModeCurrentGraph = structuredClone(currentGraph);
      console.log('[RECORD] 使用当前图数据初始化 __recordModeCurrentGraph，节点数:', currentGraph?.nodes?.length || 0);
    }
    
    backupGraphForRecordMode();
    disableEditorButtons(true);
    openRecordPanel();
    await loadRecordItems();
    showMessage('已进入记录模式', '#3d8fff');
  } catch (error) {
    console.error('[RECORD] enter error', error);
    showMessage(`进入记录模式失败：${error.message || error}`, 'red');
    exitRecordMode(true);
  }
}

function backupGraphForRecordMode() {
  // 🔥 关键修复：在 monitor_completed 模式下，优先使用保存的完整图数据
  if (frontendMode === 'monitor_completed' && window.__lastCompletedGraphData) {
    recordModeBaseGraph = structuredClone(window.__lastCompletedGraphData);
    console.log('[RECORD] 使用 __lastCompletedGraphData 备份图数据，节点数:', recordModeBaseGraph?.nodes?.length || 0);
    // 同时更新 TempMessageNode
    if (recordModeBaseGraph && recordModeBaseGraph.nodes) {
      recordModeTempMessageBackup = structuredClone({ nodes: recordModeBaseGraph.nodes });
    } else {
      recordModeTempMessageBackup = TempMessageNode ? structuredClone(TempMessageNode) : null;
    }
  } else {
    recordModeBaseGraph = structuredClone(graph.save());
    recordModeTempMessageBackup = TempMessageNode ? structuredClone(TempMessageNode) : null;
    console.log('[RECORD] 使用 graph.save() 备份图数据，节点数:', recordModeBaseGraph?.nodes?.length || 0);
  }
}

async function loadRecordItems() {
  const historyKey = getProjectHistoryKey();
  console.log('[RECORD] 加载记录列表，ProjectName:', ProjectName, 'historyKey:', historyKey);
  setRecordLoadingIndicator(true);
  recordItemsCache = [];
  try {
    const query = historyKey ? `?project_name=${encodeURIComponent(historyKey)}` : '';
    const url = `/history/runs${query}`;
    console.log('[RECORD] 请求URL:', url);
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`无法获取记录列表: ${response.status} ${response.statusText}`);
    }
    const data = await response.json();
    console.log('[RECORD] 后端返回数据:', data);
    recordItemsCache = Array.isArray(data.items) ? data.items : [];
    // 如果后端已经返回了是否出错的标记，则直接复用，避免重复解析
    recordItemsCache.forEach(item => {
      if (item && typeof item.has_error === 'boolean' && typeof item.__hasError === 'undefined') {
        item.__hasError = !!item.has_error;
      }
    });
    console.log('[RECORD] 记录数量:', recordItemsCache.length);
    if (recordItemsCache.length > 0) {
      console.log('[RECORD] 记录列表:', recordItemsCache.map(item => item.filename || item.name || item));
    }
  } catch (error) {
    console.error('[RECORD] load list error', error);
    showMessage(`加载记录列表失败: ${error.message || error}`, 'red');
  } finally {
    renderRecordSelectOptions(recordItemsCache);
    renderRecordPanel(recordItemsCache);
    // 异步标记是否存在错误节点，用于控制记录条目的底色（红/蓝）
    try {
      // 取消上一轮标注任务，避免“记录越多，点一条越慢”
      cancelRecordAnnotation('reload record list');
      const token = ++recordAnnotateToken;
      recordAnnotateController = new AbortController();
      // 让 UI 先完成渲染，再后台慢慢标注（并发/数量都有限制）
      setTimeout(() => {
        annotateRecordItemsWithErrorFlag(recordItemsCache, {
          token,
          signal: recordAnnotateController?.signal,
          // 列表加载阶段只做“错误标记”（轻量）；深度搜索索引按需在用户输入时再构建
          enableDeepSearch: false
        });
      }, 0);
    } catch (e) {
      console.warn('[RECORD] annotate error flag schedule failed', e);
    }
    setRecordLoadingIndicator(false);
  }
}

async function annotateRecordItemsWithErrorFlag(items, opts = {}) {
  if (!Array.isArray(items) || !items.length) return;

  const token = typeof opts.token === 'number' ? opts.token : recordAnnotateToken;
  const signal = opts.signal;
  const onItemUpdated = typeof opts.onItemUpdated === 'function' ? opts.onItemUpdated : null;
  const historyKey = getProjectHistoryKey();
  const projQuery = historyKey ? `&project_name=${encodeURIComponent(historyKey)}` : '';

  const shouldStop = () => (signal && signal.aborted) || token !== recordAnnotateToken;
  const yieldToUI = () => new Promise(r => setTimeout(r, 0));

  // 是否构建深度搜索索引：search 输入时可强制开启
  const forceDeepSearch = opts.enableDeepSearch === true;
  // 只对还未知状态的记录做补充检查，避免重复请求；
  // 同时：当需要构建搜索索引时，也要处理 __searchText 为空的记录（哪怕 __hasError 已经有值）
  const pendingItemsAll = items.filter(item => {
    if (!item || !item.filename) return false;
    if (typeof item.__hasError === 'undefined') return true;
    if (forceDeepSearch && typeof item.__searchText === 'undefined') return true;
    return false;
  });
  if (!pendingItemsAll.length) return;

  // 记录过多时不做全量标注：否则会把 /history/run 与 UI 都拖慢
  const maxItems = Number.isFinite(opts.maxItems) ? Math.max(0, opts.maxItems) : RECORD_ANNOTATE_MAX_ITEMS;
  const pendingItems = pendingItemsAll.slice(0, maxItems);
  if (pendingItemsAll.length > pendingItems.length) {
    console.warn(`[RECORD] 记录过多：仅后台标注前 ${pendingItems.length}/${pendingItemsAll.length} 条，避免卡顿`);
  }

  // 深度搜索文本非常昂贵：默认只在记录数量较少时启用；search 时可强制开启（仍会被 maxItems/并发/截断保护）
  const enableDeepSearch = forceDeepSearch || ((opts.enableDeepSearch !== false) && (pendingItems.length <= RECORD_DEEP_SEARCH_MAX_ITEMS));

  let cursor = 0;
  const concurrency = Math.max(1, Math.min(RECORD_ANNOTATE_CONCURRENCY, pendingItems.length));

  const processOne = async (item) => {
    if (!item || !item.filename) return;
    if (shouldStop()) return;
    try {
      const resp = await fetch(
        `/history/run?filename=${encodeURIComponent(item.filename)}${projQuery}`,
        signal ? { signal } : undefined
      );
      if (!resp.ok) return;
      const payload = await resp.json();
      // payload.nodes 可能是数组，也可能是 { nodes: [...] }
      let nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
      if (!nodes.length && payload && payload.nodes && Array.isArray(payload.nodes.nodes)) {
        nodes = payload.nodes.nodes;
      }

      // 快速判定是否有错误节点（可短路）
      if (typeof item.__hasError === 'undefined') {
        let hasError = false;
        if (Array.isArray(nodes)) {
          for (let i = 0; i < nodes.length; i++) {
            const n = nodes[i];
            if (n && (n.IsError === true || n.isError === true)) {
              hasError = true;
              break;
            }
          }
        }
        item.__hasError = !!hasError;
      }

      // 构建可搜索文本（可选：只在记录少时启用，且做截断，避免卡顿/内存爆炸）
      if (enableDeepSearch && typeof item.__searchText === 'undefined') {
        try {
          const collectFields = [];
          const maxNodesForIndex = 30;
          const maxChars = 12000;
          for (let i = 0; i < (Array.isArray(nodes) ? nodes.length : 0) && i < maxNodesForIndex; i++) {
            const n = nodes[i];
            if (!n || typeof n !== 'object') continue;
            ['label', 'name', 'prompt', 'ExportPrompt', 'SystemPrompt'].forEach(k => {
              if (n[k]) collectFields.push(String(n[k]));
            });
            // Inputs/Outputs：保留 name + 少量 Context/数值（截断），保证“按关键字搜索”可用
            if (Array.isArray(n.Inputs)) {
              n.Inputs.forEach(inp => {
                if (!inp) return;
                if (inp.name) collectFields.push(String(inp.name));
                if (inp.Context) collectFields.push(String(inp.Context).slice(0, 240));
                if (typeof inp.Num !== 'undefined' && inp.Num !== null) collectFields.push(String(inp.Num));
                if (typeof inp.Boolean === 'boolean') collectFields.push(String(inp.Boolean));
              });
            }
            if (Array.isArray(n.Outputs)) {
              n.Outputs.forEach(out => {
                if (!out) return;
                if (out.name) collectFields.push(String(out.name));
                if (out.Context) collectFields.push(String(out.Context).slice(0, 240));
                if (typeof out.Num !== 'undefined' && out.Num !== null) collectFields.push(String(out.Num));
                if (typeof out.Boolean === 'boolean') collectFields.push(String(out.Boolean));
              });
            }
            if (collectFields.join(' ').length > maxChars) break;
          }
          const baseText = `${formatRecordLabel(item)} ${item.time_label || ''}`;
          let st = `${baseText} ${collectFields.join(' ')}`.toLowerCase();
          if (st.length > maxChars) st = st.slice(0, maxChars);
          item.__searchText = st;
        } catch (e) {
          console.warn('[RECORD] build search text failed', e);
        }
      }

      // 根据结果更新对应按钮的样式（O(1)）
      const btn = recordPanelButtonMap && item.filename ? recordPanelButtonMap.get(item.filename) : null;
      if (btn) {
        if (item.__hasError) btn.classList.add('record-panel-item-error');
        else btn.classList.remove('record-panel-item-error');
        if (item.__searchText) btn.dataset.searchText = item.__searchText;
      }
      if (onItemUpdated) {
        try { onItemUpdated(item); } catch (_) {}
      }
    } catch (err) {
      // 取消/中断不算错误，直接忽略
      if (signal && signal.aborted) return;
      console.warn('[RECORD] annotate error flag failed for', item && item.filename, err);
    }
  };

  await Promise.all(
    Array.from({ length: concurrency }).map(async () => {
      while (true) {
        if (shouldStop()) return;
        const idx = cursor++;
        if (idx >= pendingItems.length) return;
        await processOne(pendingItems[idx]);
        // 让出主线程，避免卡 UI（尤其在记录较多时）
        if (idx % 2 === 0) await yieldToUI();
      }
    })
  );
}

function renderRecordSelectOptions(items) {
  if (!recordSelectElement) return;
  recordSelectElement.innerHTML = '';
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = items.length ? '选择记录...' : '暂无记录';
  placeholder.disabled = true;
  placeholder.selected = true;
  recordSelectElement.appendChild(placeholder);
  items.forEach(item => {
    const option = document.createElement('option');
    option.value = item.filename;
    option.textContent = formatRecordLabel(item);
    recordSelectElement.appendChild(option);
  });
}

function renderRecordPanel(items) {
  const container = document.getElementById('LeftSideWindow_KIND-container');
  if (!container) return;
  container.innerHTML = '';
  // 重建 filename -> DOM 的映射，供后台标注 O(1) 更新样式
  try { recordPanelButtonMap = new Map(); } catch (_) { recordPanelButtonMap = new Map(); }

  const header = document.createElement('div');
  header.className = 'record-panel-header';
  header.innerHTML = `
    <div class="record-panel-title">记录列表</div>
    <div class="record-panel-subtitle">${getProjectHistoryKey() || '当前项目'}</div>
  `;
  container.appendChild(header);

  // 关键词搜索（最简实现）
  const searchWrap = document.createElement('div');
  searchWrap.className = 'record-panel-search';
  searchWrap.innerHTML = `
    <input
      id="record-panel-search"
      type="text"
      placeholder="搜索关键字..."
      autocomplete="off"
      style="width:100%;height:28px;line-height:28px;padding:0 8px;border-radius:6px;border:1px solid rgba(255,255,255,.12);background:#0f172a;color:#fff;outline:none;margin:8px 0;"
    />
  `;
  container.appendChild(searchWrap);

  if (items.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'record-panel-empty';
    empty.textContent = '暂无可用记录';
    container.appendChild(empty);
    return;
  }

  const list = document.createElement('div');
  list.className = 'record-panel-list';
  items.forEach(item => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'record-panel-item';
    btn.dataset.filename = item.filename;
    // 预置搜索文本（先用已有信息，后续异步补齐 Inputs/Outputs）
    btn.dataset.searchText = (item.__searchText || formatRecordLabel(item)).toLowerCase();
    // 如果已经提前标记了是否有错误，则在渲染阶段直接加上对应样式
    if (item && item.__hasError) {
      btn.classList.add('record-panel-item-error');
    }
    btn.innerHTML = `
      <span class="record-item-name">${formatRecordLabel(item)}</span>
      <span class="record-item-time">${item.time_label || ''}</span>
    `;
    btn.addEventListener('click', () => {
      if (recordSelectElement) {
        recordSelectElement.value = item.filename;
      }
      handleRecordSelection(item.filename);
    });
    list.appendChild(btn);
    // 记录映射：避免 annotate 时 querySelectorAll + forEach 扫全量
    if (item && item.filename) {
      recordPanelButtonMap.set(item.filename, btn);
    }
  });
  container.appendChild(list);
  updateRecordPanelSelection(recordModeCurrentFilename);

  // 绑定搜索过滤
  const inputEl = document.getElementById('record-panel-search');
  if (inputEl) {
    const doFilter = () => {
      const q = (inputEl.value || '').trim().toLowerCase();
      const itemsEls = list.querySelectorAll('.record-panel-item');
      let hit = 0;
      itemsEls.forEach(el => {
        const text = (el.dataset.searchText || el.textContent || '').toLowerCase();
        const ok = q ? text.includes(q) : true;
        if (ok && q) hit++;
        el.style.display = ok ? '' : 'none';
      });
      // 如果当前索引命中很少/为 0，则后台按需补全深度搜索索引，再自动重跑过滤
      if (q && hit === 0) {
        scheduleRecordSearchIndexBuild(q, doFilter);
      }
    };
    inputEl.addEventListener('input', doFilter);
    inputEl.addEventListener('keydown', e => { if (e.key === 'Enter') doFilter(); });
    try { inputEl.focus(); } catch(_) {}
  }
}

function formatRecordLabel(item) {
  if (!item) return '';
  if (item.label && item.time_label) {
    return `${item.label} (${item.time_label})`;
  }
  return item.filename || '记录';
}

function openRecordPanel() {
  const sideWindow = document.getElementById('LeftSideWindow_side-window');
  if (!sideWindow) return;
  sideWindow.classList.add('visible');
  sideWindowVisible = true;
  const container = document.getElementById('LeftSideWindow_KIND-container');
  if (container) {
    container.innerHTML = '<div class="record-panel-loading">加载中...</div>';
  }
}

function toggleToolbarSelect(visible) {
  if (!recordSelectElement) return;
  recordSelectElement.style.display = visible ? 'inline-flex' : 'none';
  if (!visible) {
    recordSelectElement.value = '';
  }
}

function setRecordButtonState(active) {
  const button = document.getElementById('recoderButton');
  if (!button) return;
  if (active) {
    button.textContent = '退出记录';
    button.classList.add('record-mode-active');
  } else {
    button.textContent = '记录';
    button.classList.remove('record-mode-active');
  }
}

function disableEditorButtons(disabled) {
  ['NodeButton', 'WorkFlowButton', 'saveButton', 'exportButton', 'runButton'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = disabled;
  });
}

function updateRecordPanelSelection(filename) {
  if (recordPanelButtonMap && recordPanelButtonMap.size) {
    for (const [fn, btn] of recordPanelButtonMap.entries()) {
      if (!btn) continue;
      btn.classList.toggle('active', !!filename && fn === filename);
    }
    return;
  }
  document.querySelectorAll('.record-panel-item').forEach(btn => {
    btn.classList.toggle('active', filename && btn.dataset && btn.dataset.filename === filename);
  });
}

async function handleRecordSelection(filename) {
  if (!filename) return;
  // 用户点击记录时，优先保证这一次加载，不要让后台全量标注占满网络/主线程
  cancelRecordAnnotation('user select record');
  recordModeCurrentFilename = filename;
  updateRecordPanelSelection(filename);
  await applyRecordSnapshot(filename);
}

async function applyRecordSnapshot(filename) {
  if (!filename || !recordModeBaseGraph) return;
  setRecordLoadingIndicator(true);
  try {
    const historyKey = getProjectHistoryKey();
    const projQuery = historyKey ? `&project_name=${encodeURIComponent(historyKey)}` : '';
    const response = await fetch(`/history/run?filename=${encodeURIComponent(filename)}${projQuery}`);
    if (!response.ok) {
      throw new Error('记录文件不存在或无法读取');
    }
    const payload = await response.json();
    const nodes = Array.isArray(payload?.nodes) ? payload.nodes : payload?.nodes?.nodes || [];
    if (!nodes || !Array.isArray(nodes)) {
      throw new Error('记录文件缺少节点数据');
    }
    const nextGraph = structuredClone(recordModeBaseGraph);
    const nodeMap = {};
    nextGraph.nodes.forEach(node => {
      nodeMap[node.id] = node;
    });
    nodes.forEach(recordNode => {
      const target = nodeMap[recordNode.id];
      if (target) {
        mergeRecordNode(target, recordNode);
      }
    });
    
    // 🔥 关键修复：确保所有已完成、运行中或错误的节点都有 IsBlock=true，以便显示边框
    nextGraph.nodes.forEach(node => {
      if (node && (node.isFinish || node.IsRunning || node.IsError)) {
        node.IsBlock = true;
      }
    });
    
    ChangeDatas(nextGraph);
    TempMessageNode = structuredClone({ nodes: nextGraph.nodes });
    RefreshEdge();
    
    // 🔥 关键修复：在记录模式下，保存当前加载的记录图数据，供 sidewindow 使用
    // 这样可以避免 sidewindow 被运行时的数据"霸占"
    window.__recordModeCurrentGraph = structuredClone(nextGraph);
    console.log('[RECORD] 已保存记录图数据到 __recordModeCurrentGraph，节点数:', nextGraph.nodes?.length || 0);
    
    // 🔥 自动刷新 sidewindow（如果已打开）
    try {
      const sideWindow = document.getElementById('side-window');
      if (sideWindow && sideWindow.classList.contains('visible') && window.__currentSideWindowNode) {
        console.log('[RECORD] 检测到 sidewindow 已打开，自动刷新节点:', window.__currentSideWindowNode.id);
        // 重新创建 sidewindow，使用当前加载的记录数据
        createSideWindow(window.__currentSideWindowNode, window.__currentSideWindowIsCheckMode || false);
      }
    } catch (e) {
      console.warn('[RECORD] 自动刷新 sidewindow 失败:', e);
    }
    
    // 🔥 手动触发节点更新，确保边框正确显示
    try {
      nextGraph.nodes.forEach(node => {
        const nodeItem = graph.findById(node.id);
        if (nodeItem) {
          graph.updateItem(nodeItem, {
            IsBlock: node.IsBlock,
            IsRunning: node.IsRunning,
            isFinish: node.isFinish,
            IsError: node.IsError
          });
        }
      });
      console.log('[RECORD] 节点边框已更新，节点数:', nextGraph.nodes.length);
    } catch (e) {
      console.warn('[RECORD] 更新节点边框失败:', e);
    }
    
    showMessage('记录载入完成', '#3d8fff');
  } catch (error) {
    console.error('[RECORD] apply error', error);
    showMessage(`载入记录失败：${error.message || error}`, 'red');
  } finally {
    setRecordLoadingIndicator(false);
  }
}

function mergeRecordNode(target, source) {
  const copyFields = [
    'IsBlock', 'IsRunning', 'IsError', 'isFinish', 'ErrorContext',
    'TriggerLink', 'RecursionBehavior', 'firstRun', 'inputStatus',
    'IsStartNode', 'ExportPrompt', 'SystemPrompt', 'ExprotAfterPrompt',
    'messages', 'status', 'debug'
  ];
  copyFields.forEach(key => {
    if (source[key] !== undefined) {
      target[key] = structuredClone(source[key]);
    }
  });
  if (source.Inputs) {
    target.Inputs = structuredClone(source.Inputs);
  }
  if (source.Outputs) {
    target.Outputs = structuredClone(source.Outputs);
  }
  
  // 🔥 关键修复：如果节点已完成、运行中或错误，确保 IsBlock=true（即使记录中没有）
  if (target.isFinish || target.IsRunning || target.IsError) {
    target.IsBlock = true;
  }
}

function setRecordLoadingIndicator(isLoading) {
  if (recordSelectElement) {
    recordSelectElement.disabled = isLoading;
  }
}

function exitRecordMode(isFallback = false) {
  isRecordMode = false;
  cancelRecordAnnotation('exit record mode');
  window.is_read_history = false;
  document.body.classList.remove('record-mode');
  setRecordButtonState(false);
  toggleToolbarSelect(false);
  disableEditorButtons(false);
  recordModeCurrentFilename = '';
  // 🔥 清理记录模式专用的图数据
  window.__recordModeCurrentGraph = null;
  if (recordModeBaseGraph && !isFallback) {
    ChangeDatas(recordModeBaseGraph);
    RefreshEdge();
  }
  if (recordModeTempMessageBackup) {
    TempMessageNode = recordModeTempMessageBackup;
  }
  const sideWindow = document.getElementById('LeftSideWindow_side-window');
  if (sideWindow) {
    sideWindow.classList.remove('visible');
  }
  const container = document.getElementById('LeftSideWindow_KIND-container');
  if (container) {
    container.innerHTML = '';
  }
  sideWindowVisible = false;
  recordModeBaseGraph = null;
  recordModeTempMessageBackup = null;
  if (!isFallback) {
    showMessage('已退出记录模式', '#3d8fff');
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
  console.log('message',message);
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
          data.nodes[nodeIndex].Inputs[anchorIndex].Num = parseFloat(Value);
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
      // 同步 OriginalText 名称到独立字段与 OriginalTextArray[0]
      let updated = false;
      nodes.forEach(node => {
      if(node.id == Nodeid)
      {
        updated = true;
        node.OriginalTextName = name;
        if (!Array.isArray(node.OriginalTextArray) || node.OriginalTextArray.length === 0) {
          node.OriginalTextArray = [{
            'Num': 0,
            'Kind': 'String',
            'Id': 'Output1',
            'Context': '',
            'Boolean': false,
            'Isnecessary': true,
            'name': name || 'Output1',
            'Link': 0,
            'IsLabel': false,
          }];
        } else {
          node.OriginalTextArray[0].name = name;
        }
      }
      });
      if(updated)
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
        left: 30px;
        top: 3px;
        width: 200px;
        height: 26px;
        z-index: 100;
        background: #505050; /* 黑灰色高质感背景 */
        border: 1px solid rgba(255, 255, 255, 0.08); /* 极细微边框 */
        border-left: 3px solid #00d4ff; /* 科技蓝侧边条 */
        border-radius: 2px;
        color: #e0e0e0;
        padding-left: 10px;
        font-family: 'Consolas', 'Monaco', monospace; /* 科技感字体 */
        font-weight: 500;
        font-size: 13px;
        letter-spacing: 0.5px;
        outline: none;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        backdrop-filter: blur(12px); /* 强毛玻璃 */
        
    `;
    NameId.addEventListener('focus', function() {
        this.style.background = '#505050';
        this.style.borderLeftColor = '#fff';
        this.style.color = '#fff';
    });
    NameId.addEventListener('blur', function() {
        this.style.background = '#505050';
        this.style.borderLeftColor = '#00d4ff';
        this.style.color = '#e0e0e0';
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
        background:rgb(238, 238, 238) !important;  /* 灰色背景 */
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

    // 先把 label、input 都塞进 inputContainer
    inputContainer.appendChild(ReTryNumlabel);
    inputContainer.appendChild(input);
    
    // === 并行数量限制（仅 ArrayTrigger 节点显示，放在 ReTryNum 右边）===
    if(NodeKind.includes('ArrayTrigger')) {
      // 从节点数据中获取 ParallelLimit，如果不存在则默认为 1
      let nodeData = graph.save().nodes.find(n => n.id == id);
      let parallelLimit = (nodeData && nodeData.ParallelLimit !== undefined) ? nodeData.ParallelLimit : 1;
      
      const parallelLabel = document.createElement('label');
      parallelLabel.textContent = 'ParallelLimit';
      parallelLabel.style.marginLeft = '30px'; // 与 ReTryNum 保持间距
      parallelLabel.style.marginRight = '15px';
      parallelLabel.style.fontWeight = 'bold';
      
      const parallelInput = document.createElement('input');
      parallelInput.type = 'number';
      parallelInput.id = `ParallelLimit-${id}`;
      parallelInput.value = parallelLimit;
      parallelInput.min = '1';
      
      // 将并行数量控件添加到同一行
      inputContainer.appendChild(parallelLabel);
      inputContainer.appendChild(parallelInput);
      
      parallelInput.addEventListener('change', () => {
        let v = parseInt(parallelInput.value);
        if(v < 1) {
          parallelInput.value = 1;
          v = 1;
        }
        let nd = graph.save().nodes.find(n => n.id == id);
        if(nd) {
          nd.ParallelLimit = v;
          ChangeDatas(graph.save());
        }
      });
    }
    
    // 将整个 inputContainer 挂到 ResetColumn
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
              background: linear-gradient(135deg,rgb(51, 51, 51) 0%,rgb(99, 99, 99) 100%);
              height: 50px; display: flex; align-items: center; justify-content: center;
              user-select: none; position: relative;
              box-shadow: 0 2px 8px rgba(70, 70, 70, 0.3);
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
       // 设置左边距
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
            // 生成唯一 Id，避免删除后复用导致串改
            const baseCount = node.Outputs.length + 1;
            const makeId = () => `Output${baseCount}_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
            IdTemp = makeId();
            while (node.Outputs.some(output => output.Id === IdTemp)) {
              IdTemp = makeId();
            }

            // 生成唯一 name
            let TempName = 'Output' + baseCount.toString();
            let counter = 1; // 新增一个计数器
            // 检查是否重名，如果重名则+1继续检查
            while (node.Outputs.some(output => output.name === TempName)) {
                TempName = 'Output' + (baseCount + counter).toString(); // 使用计数器调整名称
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
            // 如果当前选择是"Input"，则添加输入控件
            if(index!=1)
            {
              if (input.Kind == 'Boolean') {
                // Boolean 使用下拉框 True/False
                labelTextarea = document.createElement('select');
                const optTrue = document.createElement('option');
                optTrue.value = 'true';
                optTrue.text  = 'true';
                const optFalse = document.createElement('option');
                optFalse.value = 'false';
                optFalse.text  = 'false';
                labelTextarea.appendChild(optTrue);
                labelTextarea.appendChild(optFalse);
                let initVal = (typeof input.Boolean === 'boolean')
                              ? (input.Boolean ? 'true' : 'false')
                              : ((input.Context != null) ? String(input.Context).toLowerCase() : 'false');
                labelTextarea.value = initVal;
                labelTextarea.style.width = '120px';
                labelTextarea.addEventListener('change', function () {
                  ChangeAnchorValue(id, labelTextarea.value, 'Input', input.Id);
                });
                ChangeAnchorValue(id, labelTextarea.value, 'Input', input.Id);
                // 让布尔选择器换行显示
                inputContainer.style.flexWrap = 'wrap';
                const br = document.createElement('div');
                br.style.flexBasis = '100%';
                inputContainer.appendChild(br);
                inputContainer.appendChild(labelTextarea);
              } else {
                labelTextarea = document.createElement('textarea');
                // String_Key 类型需要调整宽度，为图标留出空间
                if(input.Kind == 'String_Key') {
                  labelTextarea.style.width = '520px'; // 减小宽度为图标留空间
                } else {
                  labelTextarea.style.width = '550px'; // 设置固定宽度
                }
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
                    if (labelTextarea.value.match(/^-?[0-9]+(\.[0-9]+)?$/)) {
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
                      if (pathButton) pathButton.classList.add('path-button');
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
                              console.warn('[DB] success: received columns', {
                                type: typeof data.columns,
                                keys: data && data.columns ? Object.keys(data.columns) : []
                              }, 'nodeId=', id);
                              let dataTemp=graph.save();
                              dataTemp.nodes.forEach((node) => {
                                if(node.id == id)
                                {
                                  node.TempColumns= data.columns;
                                  console.warn('[DB] success: node.TempColumns assigned for node', id, {
                                    keys: node && node.TempColumns ? Object.keys(node.TempColumns) : []
                                  });
                                }
                              });
                              ChangeDatas(dataTemp);
                              console.warn('[DB] success: ChangeDatas called');
                              console.log('Data:', dataTemp);

                              // 数据库列加载成功后，立即刷新该节点的所有 Outputs 下拉（与另一处逻辑保持一致）
                              try {
                                setTimeout(() => {
                                  try {
                                    if (!window.__DBColumnsLoadedListenerInstalled) {
                                      document.addEventListener('DatabaseColumnsLoaded', function(ev) {
                                        try {
                                          const detail   = ev && ev.detail ? ev.detail : {};
                                          const nodeId   = detail.nodeId;
                                          console.warn('[DB] DatabaseColumnsLoaded fired', {
                                            rawDetail: detail,
                                            nodeId,
                                          });
                                          if (nodeId == null) {
                                            console.warn('[DB] skip: nodeId is null/undefined');
                                            return;
                                          }
                                          const data     = graph.save();
                                          const tempNode = (data.nodes || []).find(n => n.id == nodeId);
                                          console.warn('[DB] tempNode found?', !!tempNode, tempNode);
                                          if (!tempNode) return;
                                          const CurrentCols      = (tempNode && typeof tempNode.TempColumns === 'object') ? tempNode.TempColumns : {};
                                          const defaultTableKey  = tempNode?.Inputs?.[1]?.Context || null; // 仅对 ArrayTrigger_DataBase 有意义
                                          const nodeKind         = tempNode.NodeKind || '';
                                          const selector    = 'select.db-output-group-select[data-node-id="' + nodeId + '"]';
                                          const selects     = document.querySelectorAll(selector);
                                          console.warn('[DB] handler context', {
                                            defaultTableKey,
                                            nodeKind,
                                            TempColumnsKeys: CurrentCols ? Object.keys(CurrentCols) : null,
                                            selector,
                                            selectsLength: selects.length,
                                          });
                                          selects.forEach((selectEl, idx) => {
                                            // 先根据 output 配置计算当前下拉应绑定的“表名”(DataBase) 或使用旧逻辑(ArrayTrigger_DataBase)
                                            const outIdAttr = selectEl.getAttribute('data-output-id');
                                            let outputConfig = null;
                                            if (Array.isArray(tempNode.Outputs)) {
                                              outputConfig = tempNode.Outputs.find(out => out && out.Id == outIdAttr) || null;
                                            }
                                            let tableKey = null;
                                            if (nodeKind === 'ArrayTrigger_DataBase') {
                                              // 旧节点依然从 Inputs[1].Context 读取 sheet 名
                                              tableKey = defaultTableKey;
                                            } else if (nodeKind === 'DataBase') {
                                              // 新 DataBase 节点：selectBox1 存的是 sheet / 表名
                                              tableKey = outputConfig && outputConfig.selectBox1 ? outputConfig.selectBox1 : null;
                                            }
                                            console.warn('[DB] updating select', {
                                              index: idx,
                                              element: selectEl,
                                              beforeValue: selectEl.value,
                                              tableKey,
                                              outId: outIdAttr,
                                            });
                                            const prevValue = selectEl.value;
                                            // 清空并重建选项
                                            selectEl.innerHTML = '';
                                            const optAll = document.createElement('option');
                                            optAll.value = 'All';
                                            optAll.text  = 'All';
                                            selectEl.appendChild(optAll);
                                            const addedKeys = new Set();
                                            if (tableKey && CurrentCols && CurrentCols[tableKey]) {
                                              const arr = CurrentCols[tableKey];
                                              if (Array.isArray(arr)) {
                                                arr.forEach(item => {
                                                  if (Array.isArray(item)) {
                                                    item.forEach(subItem => populateSelectBoxFromObject(addedKeys, subItem, "", selectEl));
                                                  } else {
                                                    populateSelectBoxFromObject(addedKeys, item, "", selectEl);
                                                  }
                                                });
                                              }
                                            }
                                            console.warn('[DB] options before rebuild', {
                                              tableKey,
                                              CurrentCols,
                                            });
                                            // 再插入列的 key
                                            if (CurrentCols) {
                                              Object.keys(CurrentCols).forEach(k => {
                                                const o = document.createElement('option');
                                                o.value = k;
                                                o.text  = k;
                                                selectEl.appendChild(o);
                                              });
                                            }
                                            // 恢复之前保存或当前选择
                                            const savedVal = outputConfig && outputConfig.selectBox1 != null
                                              ? outputConfig.selectBox1
                                              : null;
                                            const values = Array.from(selectEl.options).map(o => o.value);
                                            if (savedVal && values.includes(savedVal)) {
                                              console.warn('[DB] apply savedVal to select', { savedVal });
                                              selectEl.value = savedVal;
                                            } else if (values.includes(prevValue)) {
                                              console.warn('[DB] keep previous value for select', { prevValue });
                                              selectEl.value = prevValue;
                                            } else {
                                              console.warn('[DB] fallback to first option', {
                                                options: values,
                                              });
                                            }
                                            // 触发一次 change，保证下游依赖更新
                                            selectEl.dispatchEvent(new Event('change'));
                                          });
                                        } catch (errHandler) {
                                          console.warn('DatabaseColumnsLoaded handler error:', errHandler);
                                        }
                                      });
                                      window.__DBColumnsLoadedListenerInstalled = true;
                                    }
                                  } catch (_) {}
                                  // 仅在成功时广播当前节点的刷新事件
                                  document.dispatchEvent(new CustomEvent('DatabaseColumnsLoaded', { detail: { nodeId: id, columns: data.columns } }));
                                }, 0);
                              } catch (e) {
                                console.warn('Outputs refresh skipped:', e);
                              }

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

              // 安全获取 TempColumns，避免未加载时报错
              const getTempColumns = (node) => {
                return (node && node.TempColumns && typeof node.TempColumns === 'object')
                  ? node.TempColumns
                  : {};
              };
              // 添加占位选项，防止误选旧值
              const appendPlaceholder = (selectEl, text, disabledFlag) => {
                const opt = document.createElement('option');
                opt.value = '';
                opt.text = text;
                opt.disabled = !!disabledFlag;
                opt.selected = true;
                selectEl.appendChild(opt);
              };
              // 用最新列信息重建下拉
              const rebuildOptions = (selectEl, columns) => {
                while (selectEl.firstChild) {
                  selectEl.removeChild(selectEl.firstChild);
                }
                const keys = Object.keys(columns || {});
                if (!keys.length) {
                  appendPlaceholder(selectEl, '未加载', true);
                  return keys;
                }
                appendPlaceholder(selectEl, '请选择', true);
                keys.forEach((key) => {
                  const option = document.createElement('option');
                  option.value = key;
                  option.text = key;
                  selectEl.appendChild(option);
                });
                return keys;
              };

              let database = graph.save();
              // 假设 labelTextarea 是一个 <select> 或 <textarea> 元素
              for (let i = 0; i < database.nodes.length; i++) {
                if (database.nodes[i].id == id) {
                  const TempColumns = getTempColumns(database.nodes[i]);
                  rebuildOptions(labelTextarea, TempColumns);
                  break;
                }
              }

              labelTextarea.addEventListener('click', function () {
                let database = graph.save();

                for (let i = 0; i < database.nodes.length; i++) {
                  if (database.nodes[i].id == id) {
                    let isDifferent = false;

                    const TempColumns1 = getTempColumns(database.nodes[i]);
                    const keys1 = Object.keys(TempColumns1);

                    // 如果尚未加载列数据，保持占位并退出，避免加载错误值
                    if (!keys1.length) {
                      rebuildOptions(labelTextarea, TempColumns1);
                      labelTextarea.value = '';
                      return;
                    }

                    // 从第 1 个选项开始检查(第 0 个是占位)
                    for (let j = 1; j < labelTextarea.options.length; j++) {
                      let currentValue = labelTextarea.options[j].value;
                      isDifferent = true; // 默认先认为不匹配

                      // 遍历 TempColumns1 的所有 key
                      for (let key of keys1) {
                        if (currentValue === key) {
                          isDifferent = false; // 找到相同键，说明没变
                          break;
                        }
                      }
                      // 如果真有不同，这里不一定需要立即 break，看你后面逻辑需要
                    }

                    // 如果元素数量也不一致，则视为不同
                    if (labelTextarea.options.length !== keys1.length + 1) {
                      isDifferent = true;
                    }

                    // 如果检测到不一致，则先清空所有选项
                    if (isDifferent) {
                      rebuildOptions(labelTextarea, TempColumns1);
                    }
                  }
                }

                // 只在当前列存在时回填 Context，避免加载错误的值
                const nodeForValue = graph.save().nodes.find(n => n.id == id);
                const validKeys = getTempColumns(nodeForValue);
                if (input.Context && Object.prototype.hasOwnProperty.call(validKeys, input.Context)) {
                  labelTextarea.value = input.Context;
                } else {
                  labelTextarea.value = '';
                }
              });

              labelTextarea.addEventListener('change', function () {
                ChangeAnchorValue(id, labelTextarea.value, 'Input', input.Id);
              });
              if (input.Context && labelTextarea.querySelector(`option[value="${input.Context}"]`)) {
                labelTextarea.value = input.Context;
              } else {
                labelTextarea.value = '';
              }
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
  pathButton.classList.add('path-button');

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
            
            // 如果是 String_Key 类型，添加密钥选择图标
            if (input.Kind == 'String_Key') {
              const keyIcon = document.createElement('button');
              keyIcon.innerHTML = '<i class="fas fa-key"></i>';
              keyIcon.style.cssText = 'width: 24px; height: 24px; border: none; background: rgba(0, 212, 255, 0.2); color: #00d4ff; cursor: pointer; border-radius: 4px; display: flex; align-items: center; justify-content: center; margin-left: 4px;';
              keyIcon.title = '选择密钥';
              
              let secretMenu = null;
              keyIcon.addEventListener('click', function(e) {
                e.stopPropagation();
                // 如果菜单已存在，则移除
                if(secretMenu && secretMenu.parentNode) {
                  secretMenu.parentNode.removeChild(secretMenu);
                  secretMenu = null;
                  return;
                }
                
                // 创建菜单
                secretMenu = document.createElement('div');
                secretMenu.style.cssText = 'position: absolute; background: rgba(30, 30, 40, 0.95); border: 1px solid rgba(0, 212, 255, 0.3); border-radius: 8px; padding: 8px 0; min-width: 200px; max-height: 300px; overflow-y: auto; z-index: 10000; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);';
                
                // 获取密钥列表
                fetch('/api/secrets/get-config')
                  .then(res => res.json())
                  .then(data => {
                    const secrets = data.secrets || [];
                    if(secrets.length === 0) {
                      const emptyItem = document.createElement('div');
                      emptyItem.textContent = '暂无密钥';
                      emptyItem.style.cssText = 'padding: 8px 16px; color: #888; font-size: 12px;';
                      secretMenu.appendChild(emptyItem);
                    } else {
                      secrets.forEach(secret => {
                        if(secret.name) {
                          const menuItem = document.createElement('div');
                          menuItem.textContent = secret.name;
                          menuItem.style.cssText = 'padding: 8px 16px; color: #fff; cursor: pointer; font-size: 13px; transition: background 0.2s;';
                          menuItem.addEventListener('mouseenter', function() {
                            this.style.background = 'rgba(0, 212, 255, 0.2)';
                          });
                          menuItem.addEventListener('mouseleave', function() {
                            this.style.background = 'transparent';
                          });
                          menuItem.addEventListener('click', function() {
                            labelTextarea.value = secret.name;
                            ChangeAnchorValue(id, secret.name, 'Input', input.Id);
                            if(secretMenu && secretMenu.parentNode) {
                              secretMenu.parentNode.removeChild(secretMenu);
                              secretMenu = null;
                            }
                          });
                          secretMenu.appendChild(menuItem);
                        }
                      });
                    }
                    
                    // 定位菜单
                    const rect = keyIcon.getBoundingClientRect();
                    secretMenu.style.left = (rect.left + rect.width) + 'px';
                    secretMenu.style.top = rect.top + 'px';
                    document.body.appendChild(secretMenu);
                  })
                  .catch(err => {
                    console.error('获取密钥列表失败:', err);
                    const errorItem = document.createElement('div');
                    errorItem.textContent = '加载失败';
                    errorItem.style.cssText = 'padding: 8px 16px; color: #dc3545; font-size: 12px;';
                    secretMenu.appendChild(errorItem);
                    const rect = keyIcon.getBoundingClientRect();
                    secretMenu.style.left = (rect.left + rect.width) + 'px';
                    secretMenu.style.top = rect.top + 'px';
                    document.body.appendChild(secretMenu);
                  });
              });
              
              // 点击其他地方关闭菜单
              document.addEventListener('click', function closeMenu(e) {
                if(secretMenu && !secretMenu.contains(e.target) && e.target !== keyIcon) {
                  if(secretMenu.parentNode) {
                    secretMenu.parentNode.removeChild(secretMenu);
                  }
                  secretMenu = null;
                  document.removeEventListener('click', closeMenu);
                }
              });
              
              inputContainer.appendChild(keyIcon);
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
      const realId = IdTemp || output.Id;
      const outputContainer = document.createElement('div');
      outputContainer.className = 'output-container';
      outputContainer.style.display = 'flex';
      outputContainer.style.alignItems = 'center'; // 同行居中
      outputContainer.style.flexWrap = 'wrap'; // Allow child elements to wrap
      outputContainer.style.marginBottom = '10px'; // Increase line spacing
      outputContainer.style.maxHeight = '320px'; // Set maximum height
      outputContainer.style.overflowY = 'auto'; // Add vertical scrollbar when needed
    
      // 创建一个 input 来显示/编辑 output name
      const outputName = document.createElement('input');
      outputName.value = output.name;
      outputName.style.width = '100px';
      outputName.style.marginBottom = '5px';
      outputContainer.appendChild(outputName);
      outputName.addEventListener('input', function() {
        ChangeAnchorLabel(id, outputName.value, index, realId, false);
      });
    
      // 分隔用的小空div
      const newLineDiv = document.createElement('div');
      newLineDiv.style.width = '5%';
      newLineDiv.style.height = '0';
      outputContainer.appendChild(newLineDiv);
    
      // Label1 + Select1：“组”下拉
      const Label1 = document.createElement('label');
      Label1.textContent = '组';
      Label1.classList.add('output-group-label');
      outputContainer.appendChild(Label1);
    
      const Select1 = document.createElement('select');
      Select1.style.width = '100px';
      outputContainer.appendChild(Select1);
      try {
        Select1.classList.add('db-output-group-select');
        Select1.setAttribute('data-node-id', id);
        Select1.setAttribute('data-output-id', realId);
        console.warn('[DB] CreatOutputs: Select1 created', { nodeId: id, outId: realId });
      } catch(_) {}
    
      // 获取当前节点的 TempColumns（原本是 TempOutPuts）
const database = graph.save();
      let TempColumns;
      for (let i = 0; i < database.nodes.length; i++) {
        if (database.nodes[i].id == id) {
          // 优先使用最新的 TempColumns；若未加载则回退到 TempOutPuts；两者应为对象
          const maybeColumns = database.nodes[i].TempColumns;
          const maybeLegacy  = database.nodes[i].TempOutPuts;
          TempColumns = (maybeColumns && typeof maybeColumns === 'object')
            ? maybeColumns
            : ((maybeLegacy && typeof maybeLegacy === 'object') ? maybeLegacy : {});
          try {
            const tableKeyDbg = (typeof Inputs !== 'undefined' && Inputs[1]) ? Inputs[1].Context : null;
            console.warn('[DB] CreatOutputs: TempColumns resolved', {
              nodeId: id,
              keys: TempColumns ? Object.keys(TempColumns) : [],
              tableKey: tableKeyDbg
            });
          } catch(_) {}
        }
      }

      // 工具：占位 & 回填
      const ensurePlaceholder = () => {
        const existing = Select1.querySelector('option[value=""]');
        if (!existing) {
          const opt = document.createElement('option');
          opt.value = '';
          opt.text = '请选择';
          opt.disabled = true;
          opt.selected = true;
          Select1.insertBefore(opt, Select1.firstChild);
        } else {
          existing.disabled = true;
        }
      };
      const restoreSavedValue = () => {
        const tempOutput = SearchOutput(id, realId);
        const saved = tempOutput && tempOutput.selectBox1;
        if (saved && Select1.querySelector(`option[value="${saved}"]`)) {
          Select1.value = saved;
        } else {
          Select1.value = '';
        }
      };
    
      // 如果需要根据某个 key(如 Inputs[1].Context) 去定位 TempColumns 的“表”或“列数据”，则如下写:
      // 注意：只有在 TempColumns[Inputs[1].Context] 是数组或可遍历的结构时，这些操作才有意义
      const addedKeys = new Set();
      if (TempColumns && TempColumns[Inputs[1].Context]) {
        // 若这里确实存储的是多列/多对象，也可继续用 forEach
        if (Array.isArray(TempColumns[Inputs[1].Context])) {
          TempColumns[Inputs[1].Context].forEach(item => {
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
                  if (out.Id == realId && out.selectBox4 != null) {
                    Select1.value = out.selectBox4;
                  }
                });
              }
            });
          });
        }
      }
    
      // 增加占位与 "All" 选项（All 不默认选中）
      ensurePlaceholder();
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
      restoreSavedValue();
    
      // 当 Select1 改变时，清除多余元素并更新输出配置
      Select1.addEventListener('change', function() {
        if (Select1.value === '') return; // 占位不写回
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
              if (out.Id == realId) {
                out.selectBox1 = Select1.value;
                // out.selectBox5 = null; // 若需要可保留
                out.selectKind = null;
              }
            });
          }
        });
        ChangeDatas(data);
      });
    
      // 为了让它在初始化时也执行一次 change（仅当有有效值）
      const triggerChange = () => {
        if (Select1.value !== '') {
          Select1.dispatchEvent(new Event('change'));
        }
      };
      setTimeout(triggerChange, 1000);
      triggerChange();
    
      // 点击 Select1 时，检测与 TempColumns.keys() 是否一致
      Select1.addEventListener('click', function() {
        let isDifferent = false;
        let data = graph.save();
        let Tempnode = data.nodes.filter(n => n.id == id);
        let CurrentCols = Tempnode[0].TempColumns || {}; // 原先用 TempOutPuts
    
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
          ensurePlaceholder();
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
                      if (out2.Id == realId && out2.selectBox4 != null) {
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

          // 回填之前选中的值（不存在则留在占位）
          restoreSavedValue();
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
              if (out.Id == realId && out.Isnecessary == true) {
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
        SubNode.style.left = '440px';
        outputContainer.appendChild(SubNode);
    
        SubNode.onmousedown = function() {
          let data = graph.save();
          data.nodes.forEach((node) => {
            if (node.id == id) {
              // 通过 IdTemp 删除此 Output
              node.Outputs.forEach((out, idx) => {
                if (out.Id == realId) {
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
                // 生成唯一的 Id 和不重复的 name
                let baseCount = node.Inputs.length + 1;
                // 先为 name 计算一个不重复的序号
                let TempName = 'Input' + baseCount.toString();
                let counter = 1; // 新增一个计数器
                // 检查是否重名，如果重名则+1继续检查
                while (node.Inputs.some(input => input.name === TempName)) {
                    TempName = 'Input' + (baseCount + counter).toString(); // 使用计数器调整名称
                    counter++; // 每次循环递增计数器
                }
                // 基于当前时间戳确保 Id 唯一；如存在重复再追加随机数
                let IdTemp = 'Input' + baseCount.toString() + '_' + Date.now();
                while (node.Inputs.some(input => input.Id === IdTemp)) {
                  IdTemp = 'Input' + baseCount.toString() + '_' + Date.now() + '_' + Math.floor(Math.random()*1000);
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
     // 设置左边距
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
          let TempName = 'Output' + baseCount;
          // 确保 name 不重复
          let counter = 1;
          while (node.Outputs.some(o => o.name === TempName)) {
            TempName = 'Output' + (baseCount + counter);
            counter++;
          }

          // 确保 Id 全局唯一，避免后续操作串改其它输出
          const makeId = () => `Output${baseCount}_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
          let IdTemp = makeId();
          while (node.Outputs.some(o => o.Id === IdTemp)) {
            IdTemp = makeId();
          }
          // 保证 name 不重复
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
        SubNode.style.left = '410px'; // 设置与标签之间的间距
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
            // 如果当前选择是"Input"，则添加输入控件
            if (input.Kind == 'Boolean') {
                // Boolean 使用下拉框 True/False
                labelTextarea = document.createElement('select');
                const optTrue = document.createElement('option');
                optTrue.value = 'true';
                optTrue.text  = 'true';
                const optFalse = document.createElement('option');
                optFalse.value = 'false';
                optFalse.text  = 'false';
                labelTextarea.appendChild(optTrue);
                labelTextarea.appendChild(optFalse);
                let initVal = (typeof input.Boolean === 'boolean')
                              ? (input.Boolean ? 'true' : 'false')
                              : ((input.Context != null) ? String(input.Context).toLowerCase() : 'false');
                labelTextarea.value = initVal;
                let uniqueClass = `unique-textarea-${id}-${input.Id}`; // 使用 input.Id 生成唯一的类名
                labelTextarea.className = uniqueClass;
                labelTextarea.id = uniqueClass;
                labelTextarea.classList.add(uniqueClass);
                labelTextarea.style.width = '120px';
                labelTextarea.addEventListener('change', function () {
                    ChangeAnchorValue(id, labelTextarea.value, 'Input', input.Id);
                });
                ChangeAnchorValue(id, labelTextarea.value, 'Input', input.Id);
                // 让布尔选择器换行显示
                inputContainer.style.flexWrap = 'wrap';
                const br = document.createElement('div');
                br.style.flexBasis = '100%';
                inputContainer.appendChild(br);
                inputContainer.appendChild(labelTextarea);
            } else {
                // 文本/数字/文件路径用文本域
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
            
            // 如果是 String_Key 类型，添加密钥选择图标
            if (input.Kind == 'String_Key') {
              const keyIcon = document.createElement('button');
              keyIcon.innerHTML = '<i class="fas fa-key"></i>';
              keyIcon.style.cssText = 'width: 24px; height: 24px; border: none; background: rgba(0, 212, 255, 0.2); color: #00d4ff; cursor: pointer; border-radius: 4px; display: flex; align-items: center; justify-content: center; margin-left: 4px;';
              keyIcon.title = '选择密钥';
              
              let secretMenu = null;
              keyIcon.addEventListener('click', function(e) {
                e.stopPropagation();
                // 如果菜单已存在，则移除
                if(secretMenu && secretMenu.parentNode) {
                  secretMenu.parentNode.removeChild(secretMenu);
                  secretMenu = null;
                  return;
                }
                
                // 创建菜单
                secretMenu = document.createElement('div');
                secretMenu.style.cssText = 'position: absolute; background: rgba(30, 30, 40, 0.95); border: 1px solid rgba(0, 212, 255, 0.3); border-radius: 8px; padding: 8px 0; min-width: 200px; max-height: 300px; overflow-y: auto; z-index: 10000; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);';
                
                // 获取密钥列表
                fetch('/api/secrets/get-config')
                  .then(res => res.json())
                  .then(data => {
                    const secrets = data.secrets || [];
                    if(secrets.length === 0) {
                      const emptyItem = document.createElement('div');
                      emptyItem.textContent = '暂无密钥';
                      emptyItem.style.cssText = 'padding: 8px 16px; color: #888; font-size: 12px;';
                      secretMenu.appendChild(emptyItem);
                    } else {
                      secrets.forEach(secret => {
                        if(secret.name) {
                          const menuItem = document.createElement('div');
                          menuItem.textContent = secret.name;
                          menuItem.style.cssText = 'padding: 8px 16px; color: #fff; cursor: pointer; font-size: 13px; transition: background 0.2s;';
                          menuItem.addEventListener('mouseenter', function() {
                            this.style.background = 'rgba(0, 212, 255, 0.2)';
                          });
                          menuItem.addEventListener('mouseleave', function() {
                            this.style.background = 'transparent';
                          });
                          menuItem.addEventListener('click', function() {
                            labelTextarea.value = secret.name;
                            ChangeAnchorValue(id, secret.name, 'Input', input.Id);
                            if(secretMenu && secretMenu.parentNode) {
                              secretMenu.parentNode.removeChild(secretMenu);
                              secretMenu = null;
                            }
                          });
                          secretMenu.appendChild(menuItem);
                        }
                      });
                    }
                    
                    // 定位菜单
                    const rect = keyIcon.getBoundingClientRect();
                    secretMenu.style.left = (rect.left + rect.width) + 'px';
                    secretMenu.style.top = rect.top + 'px';
                    document.body.appendChild(secretMenu);
                  })
                  .catch(err => {
                    console.error('获取密钥列表失败:', err);
                    const errorItem = document.createElement('div');
                    errorItem.textContent = '加载失败';
                    errorItem.style.cssText = 'padding: 8px 16px; color: #dc3545; font-size: 12px;';
                    secretMenu.appendChild(errorItem);
                    const rect = keyIcon.getBoundingClientRect();
                    secretMenu.style.left = (rect.left + rect.width) + 'px';
                    secretMenu.style.top = rect.top + 'px';
                    document.body.appendChild(secretMenu);
                  });
              });
              
              // 点击其他地方关闭菜单
              document.addEventListener('click', function closeMenu(e) {
                if(secretMenu && !secretMenu.contains(e.target) && e.target !== keyIcon) {
                  if(secretMenu.parentNode) {
                    secretMenu.parentNode.removeChild(secretMenu);
                  }
                  secretMenu = null;
                  document.removeEventListener('click', closeMenu);
                }
              });
              
              inputContainer.appendChild(keyIcon);
            }
            
            labelTextarea.className = uniqueClass;
            labelTextarea.id = uniqueClass;
            labelTextarea.classList.add(uniqueClass); // 为文本区域添加唯一类名
    
            labelTextarea.addEventListener('input', function () {
                let isOk = true; // 假定输入有效
                if (input.Kind == 'Num') {
                    if (labelTextarea.value.match(/^-?[0-9]+(\.[0-9]+)?$/)) {
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
                      if (pathButton) {
                        pathButton.classList.add('path-button');
                        pathButton.innerHTML = 'Select Path <span class="circle-loader"></span>';
                      }
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
                              if (pathButton) {
                                pathButton.innerHTML = 'Select Path <span style="color: green;">(Load Success)</span>';
                              }
                              let dataTemp=graph.save();
                              dataTemp.nodes.forEach((node) => {
                                if(node.id == id)
                                {
                                  node.TempColumns= data.columns;
                                }
                              });
                              ChangeDatas(dataTemp);
                              // 数据库列加载成功后，立即刷新该节点的所有 Outputs 下拉
                              try{
                                setTimeout(() => {
                                  // 安装一次性的全局监听器（若未安装），用于统一刷新 Outputs 的“组”下拉
                                  try {
                                    if (!window.__DBColumnsLoadedListenerInstalled) {
                                      document.addEventListener('DatabaseColumnsLoaded', function(ev) {
                                        try {
                                          const detail   = ev && ev.detail ? ev.detail : {};
                                          const nodeId   = detail.nodeId;
                                          console.warn('[DB] DatabaseColumnsLoaded fired', {
                                            rawDetail: detail,
                                            nodeId,
                                          });
                                          if (nodeId == null) {
                                            console.warn('[DB] skip: nodeId is null/undefined');
                                            return;
                                          }
                                          const data     = graph.save();
                                          const tempNode = (data.nodes || []).find(n => n.id == nodeId);
                                          console.warn('[DB] tempNode found?', !!tempNode, tempNode);
                                          if (!tempNode) return;
                                          const CurrentCols      = (tempNode && typeof tempNode.TempColumns === 'object') ? tempNode.TempColumns : {};
                                          const defaultTableKey  = tempNode?.Inputs?.[1]?.Context || null; // 仅对 ArrayTrigger_DataBase 有意义
                                          const nodeKind         = tempNode.NodeKind || '';
                                          const selector    = 'select.db-output-group-select[data-node-id=\"' + nodeId + '\"]';
                                          const selects     = document.querySelectorAll(selector);
                                          console.warn('[DB] handler context', {
                                            defaultTableKey,
                                            nodeKind,
                                            TempColumnsKeys: CurrentCols ? Object.keys(CurrentCols) : null,
                                            selector,
                                            selectsLength: selects.length,
                                          });
                                          selects.forEach((selectEl, idx) => {
                                            // 先根据 output 配置计算当前下拉应绑定的“表名”(DataBase) 或使用旧逻辑(ArrayTrigger_DataBase)
                                            const outIdAttr = selectEl.getAttribute('data-output-id');
                                            let outputConfig = null;
                                            if (Array.isArray(tempNode.Outputs)) {
                                              outputConfig = tempNode.Outputs.find(out => out && out.Id == outIdAttr) || null;
                                            }
                                            let tableKey = null;
                                            if (nodeKind === 'ArrayTrigger_DataBase') {
                                              // 旧节点依然从 Inputs[1].Context 读取 sheet 名
                                              tableKey = defaultTableKey;
                                            } else if (nodeKind === 'DataBase') {
                                              // 新 DataBase 节点：selectBox1 存的是 sheet / 表名
                                              tableKey = outputConfig && outputConfig.selectBox1 ? outputConfig.selectBox1 : null;
                                            }
                                            console.warn('[DB] updating select', {
                                              index: idx,
                                              element: selectEl,
                                              beforeValue: selectEl.value,
                                              tableKey,
                                              outId: outIdAttr,
                                            });
                                            const prevValue = selectEl.value;
                                            // 清空并重建选项
                                            selectEl.innerHTML = '';
                                            const optAll = document.createElement('option');
                                            optAll.value = 'All';
                                            optAll.text  = 'All';
                                            selectEl.appendChild(optAll);
                                            const addedKeys = new Set();
                                            if (tableKey && CurrentCols && CurrentCols[tableKey]) {
                                              const arr = CurrentCols[tableKey];
                                              if (Array.isArray(arr)) {
                                                arr.forEach(item => {
                                                  if (Array.isArray(item)) {
                                                    item.forEach(subItem => populateSelectBoxFromObject(addedKeys, subItem, "", selectEl));
                                                  } else {
                                                    populateSelectBoxFromObject(addedKeys, item, "", selectEl);
                                                  }
                                                });
                                              }
                                            }
                                            console.warn('[DB] options before rebuild', {
                                              tableKey,
                                              CurrentCols,
                                            });
                                            // 再插入列的 key
                                            if (CurrentCols) {
                                              Object.keys(CurrentCols).forEach(k => {
                                                const o = document.createElement('option');
                                                o.value = k;
                                                o.text  = k;
                                                selectEl.appendChild(o);
                                              });
                                            }
                                            // 记录重建后的所有选项
                                            console.warn('[DB] options after rebuild', {
                                              nodeId,
                                              index: idx,
                                              options: Array.from(selectEl.options).map(o => ({
                                                value: o.value,
                                                text : o.text,
                                              })),
                                            });
                                            // 恢复之前保存或当前选择
                                            const savedVal = outputConfig && outputConfig.selectBox1 != null
                                              ? outputConfig.selectBox1
                                              : null;
                                            const values = Array.from(selectEl.options).map(o => o.value);
                                            if (savedVal && values.includes(savedVal)) {
                                              console.warn('[DB] apply savedVal to select', { savedVal });
                                              selectEl.value = savedVal;
                                            } else if (values.includes(prevValue)) {
                                              console.warn('[DB] keep previous value for select', { prevValue });
                                              selectEl.value = prevValue;
                                            } else {
                                              console.warn('[DB] fallback to first option', {
                                                options: values,
                                              });
                                            }
                                            // 触发一次 change，保证下游依赖更新
                                            selectEl.dispatchEvent(new Event('change'));
                                          });
                                        } catch (errHandler) {
                                          console.warn('DatabaseColumnsLoaded handler error:', errHandler);
                                        }
                                      });
                                      window.__DBColumnsLoadedListenerInstalled = true;
                                    }
                                  } catch (_) {}
                                  // 仅在成功时广播当前节点的刷新事件
                                  document.dispatchEvent(new CustomEvent('DatabaseColumnsLoaded', { detail: { nodeId: id, columns: data.columns } }));
                                }, 0);
                              }catch(e){
                                console.warn('Outputs refresh skipped:', e);
                              }         
                          } else {
                              console.error('Error:', data.message,data);
                              if (pathButton) {
                                pathButton.innerHTML = 'Select Path <span style="color: red;">(Load Fail)</span>';
                              }
                          }
                      })
                      .catch(error => {
                          console.error('Error:', error,data);
                          if (pathButton) {
                            pathButton.innerHTML = 'Select Path <span style="color: red;">(Load Fail)</span>';
                          }
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
      // 确保输出标识存在，避免 realId 未定义报错
      const realId = IdTemp || output.Id;
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
      outputContainer.style.marginBottom = '8px'; // 收紧行距
      outputContainer.style.maxHeight = 'none'; // 不再限制高度
      outputContainer.style.overflowY = 'visible'; // 不强制滚动
      // Create an input box to display the output name
      const outputName = document.createElement('input');
      outputName.value = output.name;
      outputName.style.width = '150px'; // 统一宽度，保持对齐
      outputName.style.marginBottom = '6px';
      outputContainer.appendChild(outputName);
      outputName.addEventListener('input', function() {
        ChangeAnchorLabel(id, outputName.value, index, IdTemp, false);
      })
      
      if (index != 0) {
        const newLineDiv = document.createElement('div');
        newLineDiv.style.width = '100%';
        newLineDiv.style.height = '0';
        outputContainer.appendChild(newLineDiv);
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
      
        // 组(Label + Select1)
        const Label1 = document.createElement('label');
        Label1.textContent = '组';
        Label1.style.flex = '0 0 auto';
        Label1.style.color = '#FFFFFF';
        outputContainer.appendChild(Label1);
      
        const Select1 = document.createElement('select');
        Select1.style.width = '120px';
        outputContainer.appendChild(Select1);
        // 标记以便全局事件处理器能精准找到并刷新
        try {
          Select1.classList.add('db-output-group-select');
          Select1.setAttribute('data-node-id', id);
          Select1.setAttribute('data-output-id', IdTemp);
        } catch (_) {}
        
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
        const outputTemp   = SearchOutput(id, realId);
        const outputKey    = realId;
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
        const OutputTemp = SearchOutput(id, realId);
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
                if (out.Id === realId) {
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
              if (out.Id === realId) {
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
          SubNode.style.left = '500px';
          SubNode.style.top = '20px';
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
            /* 初始化数据字段（无论新建还是刷新，都要保证数组存在） */
            tempoutput.DataBaseSubjectArray = tempoutput.DataBaseSubjectArray || [];
            tempoutput.DataBaseContentArray = tempoutput.DataBaseContentArray || [];
            tempoutput.DataBaseLogicKind   = tempoutput.DataBaseLogicKind   || 'And';
            tempoutput.DataBaseIsExactArray = tempoutput.DataBaseIsExactArray || [];

            let logicContainer = outputContainer.querySelector('.logic-container');

            /* ====== 场景一：首次创建逻辑区域 ====== */
            if (!logicContainer) {
              /* ---- DOM ---- */
              logicContainer = document.createElement('div');
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
              return;
            }

            /* ====== 场景二：TempColumns / 表名 发生变化时的“刷新” ====== */
            const body = logicContainer.querySelector('.logic-body');
            if (!body) return;

            /* 确保“新增匹配条件”按钮后续新增的行也使用最新的列信息 */
            const createBtn = body.querySelector('.create-logic-row');
            if (createBtn) {
              createBtn.onclick = () => {
                // 使用当前最新的 TempColumns / table 来生成新行
                tempoutput.DataBaseSubjectArray.push('');
                tempoutput.DataBaseContentArray.push('');
                addLogicRow(body, table, tempColumns, tempoutput, tempoutput.DataBaseSubjectArray.length - 1);
              };
            }

            const rows = Array.from(body.querySelectorAll('.logic-row'));
            rows.forEach((row, idx) => {
              const subjectSelect = row.querySelector('select');
              if (!subjectSelect) return;

              const prevVal = subjectSelect.value;
              // 清空并用最新的列信息重建 subject 选项
              subjectSelect.innerHTML = '';
              populateSubject(subjectSelect, table, tempColumns);

              const savedVal = Array.isArray(tempoutput.DataBaseSubjectArray)
                ? tempoutput.DataBaseSubjectArray[idx] || prevVal
                : prevVal;
              const optionsValues = Array.from(subjectSelect.options).map(o => o.value);
              if (savedVal && optionsValues.includes(savedVal)) {
                subjectSelect.value = savedVal;
              } else if (optionsValues.length > 0) {
                subjectSelect.value = optionsValues[0];
              }

              // 列发生变化后，同步刷新右侧依赖于列选择的其他下拉（如字段选择）
              try {
                InitSelectBox2(subjectSelect.value);
              } catch(_) {}
            });
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
              ChangeAnchorLabel(id, Select3.value, "selectBox3", realId, false);
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
              if (child !== outputName  &&child !==Label5 &&child !==Select5 && child.className!=='column-SubNode' &&child !== Select1 && child !== Label1&& child !== newLineDiv) {
                  outputContainer.removeChild(child);
              }

              // 更新 child 为之前的元素
              child = prev;
          }
          data.nodes.forEach((node) => {
            if (node.id == id) {
              node.Outputs.forEach((output,index) => {
                if (output.Id == realId) {
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
                    // String_Key 类型需要调整宽度，为图标留出空间
                    if(input.Kind == 'String_Key') {
                      labelTextarea.style.width = '530px'; // 减小宽度为图标留空间
                    } else {
                      labelTextarea.style.width = '560px'; 
                    }
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
                      if (labelTextarea.value.match(/^-?[0-9]+(\.[0-9]+)?$/)) 
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
                    // 如果是 String_Key 类型，添加密钥选择图标
                    if(input.Kind == 'String_Key') {
                      const keyIcon = document.createElement('button');
                      keyIcon.innerHTML = '<i class="fas fa-key"></i>';
                      keyIcon.style.cssText = 'width: 24px; height: 24px; border: none; background: rgba(0, 212, 255, 0.2); color: #00d4ff; cursor: pointer; border-radius: 4px; display: flex; align-items: center; justify-content: center; margin-left: 4px;';
                      keyIcon.title = '选择密钥';
                      
                      let secretMenu = null;
                      keyIcon.addEventListener('click', function(e) {
                        e.stopPropagation();
                        // 如果菜单已存在，则移除
                        if(secretMenu && secretMenu.parentNode) {
                          secretMenu.parentNode.removeChild(secretMenu);
                          secretMenu = null;
                          return;
                        }
                        
                        // 创建菜单
                        secretMenu = document.createElement('div');
                        secretMenu.style.cssText = 'position: absolute; background: rgba(30, 30, 40, 0.95); border: 1px solid rgba(0, 212, 255, 0.3); border-radius: 8px; padding: 8px 0; min-width: 200px; max-height: 300px; overflow-y: auto; z-index: 10000; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);';
                        
                        // 获取密钥列表
                        fetch('/api/secrets/get-config')
                          .then(res => res.json())
                          .then(data => {
                            const secrets = data.secrets || [];
                            if(secrets.length === 0) {
                              const emptyItem = document.createElement('div');
                              emptyItem.textContent = '暂无密钥';
                              emptyItem.style.cssText = 'padding: 8px 16px; color: #888; font-size: 12px;';
                              secretMenu.appendChild(emptyItem);
                            } else {
                              secrets.forEach(secret => {
                                if(secret.name) {
                                  const menuItem = document.createElement('div');
                                  menuItem.textContent = secret.name;
                                  menuItem.style.cssText = 'padding: 8px 16px; color: #fff; cursor: pointer; font-size: 13px; transition: background 0.2s;';
                                  menuItem.addEventListener('mouseenter', function() {
                                    this.style.background = 'rgba(0, 212, 255, 0.2)';
                                  });
                                  menuItem.addEventListener('mouseleave', function() {
                                    this.style.background = 'transparent';
                                  });
                                  menuItem.addEventListener('click', function() {
                                    labelTextarea.value = secret.name;
                                    ChangeAnchorValue(id, secret.name, 'Input', input.Id);
                                    if(secretMenu && secretMenu.parentNode) {
                                      secretMenu.parentNode.removeChild(secretMenu);
                                      secretMenu = null;
                                    }
                                  });
                                  secretMenu.appendChild(menuItem);
                                }
                              });
                            }
                            
                            // 定位菜单
                            const rect = keyIcon.getBoundingClientRect();
                            secretMenu.style.left = (rect.left + rect.width) + 'px';
                            secretMenu.style.top = rect.top + 'px';
                            document.body.appendChild(secretMenu);
                          })
                          .catch(err => {
                            console.error('获取密钥列表失败:', err);
                            const errorItem = document.createElement('div');
                            errorItem.textContent = '加载失败';
                            errorItem.style.cssText = 'padding: 8px 16px; color: #dc3545; font-size: 12px;';
                            secretMenu.appendChild(errorItem);
                            const rect = keyIcon.getBoundingClientRect();
                            secretMenu.style.left = (rect.left + rect.width) + 'px';
                            secretMenu.style.top = rect.top + 'px';
                            document.body.appendChild(secretMenu);
                          });
                      });
                      
                      // 点击其他地方关闭菜单
                      document.addEventListener('click', function closeMenu(e) {
                        if(secretMenu && !secretMenu.contains(e.target) && e.target !== keyIcon) {
                          if(secretMenu.parentNode) {
                            secretMenu.parentNode.removeChild(secretMenu);
                          }
                          secretMenu = null;
                          document.removeEventListener('click', closeMenu);
                        }
                      });
                      
                      inputContainer.appendChild(keyIcon);
                    }
                  }
                  else
                  {
                    // Boolean 使用下拉框
                    labelTextarea = document.createElement('select');
                    const optTrue = document.createElement('option');
                    optTrue.value = 'true';
                    optTrue.text = 'true';
                    const optFalse = document.createElement('option');
                    optFalse.value = 'false';
                    optFalse.text = 'false';
                    labelTextarea.appendChild(optTrue);
                    labelTextarea.appendChild(optFalse);
                    let initVal = (typeof input.Boolean === 'boolean')
                                  ? (input.Boolean ? 'true' : 'false')
                                  : ((input.Context != null) ? String(input.Context).toLowerCase() : 'false');
                    labelTextarea.value = initVal;
                    let uniqueClass = `unique-textarea-${id}-${input.Id}`;
                    labelTextarea.className = uniqueClass;
                    labelTextarea.id = uniqueClass;
                    labelTextarea.classList.add(uniqueClass);
                    labelTextarea.style.width = '120px';
                    labelTextarea.addEventListener('change', function() {
                      ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id);
                    });
                    // 让布尔选择器换行显示
                    inputContainer.style.flexWrap = 'wrap';
                    const br = document.createElement('div');
                    br.style.flexBasis = '100%';
                    inputContainer.appendChild(br);
                    inputContainer.appendChild(labelTextarea);
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
          const optionKey = document.createElement('option');
          optionKey.value = 'String_Key';
          optionKey.text = 'Key';

          Select1.appendChild(optionContext);
          Select1.appendChild(optionNum);
          Select1.appendChild(optionBool);
          Select1.appendChild(optionFilePath);
          Select1.appendChild(optionKey);
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
                    // 如果是 String_Key 类型且 selectBox 是 Input，需要重新渲染以显示图标
                    if(this.value == 'String_Key' && selectBox.value == 'Input' && labelTextarea) {
                      // 触发 handleChange 重新渲染
                      handleChange('Input');
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
          SubNode.style.left = '410px'; // 设置与标签之间的间距
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
                    if (labelTextarea.value.match(/^-?[0-9]+(\.[0-9]+)?$/)) 
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
                      if (labelTextarea.value.match(/^-?[0-9]+(\.[0-9]+)?$/)) 
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
                        if (labelTextarea.value.match(/^-?[0-9]+(\.[0-9]+)?$/)) 
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
                const baseCount = node.Inputs.length + 1;
                let TempName = 'Input' + baseCount.toString();
                let counter = 1; // 新增一个计数器
                // 检查是否重名，如果重名则+1继续检查
                while (node.Inputs.some(input => input.name === TempName)) {
                    TempName = 'Input' + (baseCount + counter).toString(); // 使用计数器调整名称
                    counter++; // 每次循环递增计数器
                }
                // 生成唯一 Id
                let IdTemp = 'Input' + baseCount.toString() + '_' + Date.now();
                while (node.Inputs.some(input => input.Id === IdTemp)) {
                  IdTemp = 'Input' + baseCount.toString() + '_' + Date.now() + '_' + Math.floor(Math.random()*1000);
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
          ChangeAnchorLabel(id, outputName.value, 'selectBox'+'name',output.Id,false);
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
                // 唯一 Id，避免删除后复用
                const baseCount = node.Outputs.length + 1;
                const makeId = () => `Output${baseCount}_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
                IdTemp = makeId();
                while (node.Outputs.some(output => output.Id === IdTemp)) {
                  IdTemp = makeId();
                }

                // 唯一 name
                let TempName = 'Output' + baseCount.toString();
                let counter = 1; // 新增一个计数器
                // 检查是否重名，如果重名则+1继续检查
                while (node.Outputs.some(output => output.name === TempName)) {
                    TempName = 'Output' + (baseCount + counter).toString(); // 使用计数器调整名称
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
        modelSelector.style.color='Black'

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
            // 运行中不把 SystemPrompt/prompt 写回图数据
            const runBtn = document.getElementById('runButton');
            const isRunning = runBtn && runBtn.textContent === '运行中...';
            if (isRunning && (fieldKey === 'SystemPrompt' || fieldKey === 'prompt')) {
              return;
            }
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
                const baseCount = node.Inputs.length + 1;
                let TempName = 'Input' + baseCount.toString();
                let counter = 1; // 新增一个计数器
                // 检查是否重名，如果重名则+1继续检查
                while (node.Inputs.some(input => input.name === TempName)) {
                    TempName = 'Input' + (baseCount + counter).toString(); // 使用计数器调整名称
                    counter++; // 每次循环递增计数器
                }
                // 生成唯一 Id
                let IdTemp = 'Input' + baseCount.toString() + '_' + Date.now();
                while (node.Inputs.some(input => input.Id === IdTemp)) {
                  IdTemp = 'Input' + baseCount.toString() + '_' + Date.now() + '_' + Math.floor(Math.random()*1000);
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
      addNode1.className = 'column-AddNode'; // 使用之前定义的样式类（定位由 CSS 统一控制）
      const JsonColumn = document.createElement('div');
      JsonColumn.className = 'Jsoncolumn';
      const OriginalTextColumn = document.createElement('div');
      OriginalTextColumn.className = 'Jsoncolumn';
      OriginalTextColumn.style.display = 'flex';
      OriginalTextColumn.style.alignItems = 'flex-start'; // 使内容顶部对齐
      OriginalTextColumn.style.flexWrap = 'nowrap'; // 允许子元素换行
      
      // 加号回到 Output 整体列的头部，与 Output 标题同一层级（始终可用）
      outputColumn.appendChild(addNode1);
      const OutputSelect = document.createElement('select');
      OutputSelect.style.width = '75px'; // 设置固定宽度
      OutputSelect.style.position = 'absolute'; // 设置相对定位
      OutputSelect.style.left = '88px'; // 略向左移
      OutputSelect.style.top = '6px';   // 略向上移
      OutputSelect.style.height = '34px';
      OutputSelect.style.padding = '6px 28px 6px 12px';
      
      const optionJson = document.createElement('option');
      optionJson.style.top='0px';
      optionJson.value = 'Json';
      optionJson.text = 'Json';
      const optionOriginalText = document.createElement('option');
      optionOriginalText.value = 'OriginalText';
      optionOriginalText.text = 'OriginalText';
      OutputSelect.style.width = '100px'; // 设置固定宽度
      OutputSelect.appendChild(optionJson);
      OutputSelect.appendChild(optionOriginalText);
      OutputSelect.value = OriginalTextSelector;

      // 根据初始模式决定是否显示加号（OriginalText 隐藏，Json 显示）
      if (OriginalTextSelector === 'OriginalText') {
        addNode1.style.display = 'none';
      } else {
        addNode1.style.display = 'block';
      }
      const outputLabel = document.createElement('div');
      outputLabel.textContent = 'Output'; // 设置文本
      outputLabel.className = 'column-label'; // 设置样式类
      outputColumn.appendChild(outputLabel);
      outputColumn.appendChild(OutputSelect);
      outputColumn.appendChild(JsonColumn);
      outputColumn.appendChild(OriginalTextColumn);
      OutputSelect.addEventListener('change', function() {
        let data = graph.save();
        // 记录切换前模式
        let prevMode = null;
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
            // 记录之前的模式
            prevMode = node.OriginalTextSelector;
            // 设置新模式
            node.OriginalTextSelector = this.value; 
             
          }
        });
        ChangeDatas(data);
        // 调试：记录切换初始状态
        try {
          const cur = graph.save().nodes.find(n=>n.id==id) || {};
          console.warn('[OutputSelect.change] node=', id, 'to=', this.value,
            'hasJsonOutputs=', Array.isArray(cur.JsonOutputs),
            'jsonCount=', (cur.JsonOutputs||[]).length,
            'outputsCount(before)=', (cur.Outputs||[]).length,
            'hasTemplate=', !!(cur.ExprotAfterPrompt && cur.ExprotAfterPrompt.length>0)
          );
        } catch(_) {}
        if(this.value=='OriginalText')
        {
          // OriginalText 模式下隐藏新增输出加号
          addNode1.style.display = 'none';
          //JsonColumn隐身
          OriginalTextColumn.style.display = 'block';
          JsonColumn.style.display = 'none';
          let data = graph.save();
          data.nodes.forEach((node) => {
            if (node.id == id) {
              // 仅当从 Json -> OriginalText 时，才缓存 JsonOutputs
              if (prevMode === 'Json' && Array.isArray(node.Outputs)) {
                try {
                  node.JsonOutputs = (typeof structuredClone === 'function')
                    ? structuredClone(node.Outputs)
                    : JSON.parse(JSON.stringify(node.Outputs));
                } catch (_) {
                  node.JsonOutputs = JSON.parse(JSON.stringify(node.Outputs));
                }
              }
              // OriginalText模式下，Outputs应为1个
              if (!node.OriginalTextArray || node.OriginalTextArray.length !== 1) {
                node.OriginalTextArray = [{
                  'Num': 0,
                  'Kind': 'String',
                  'Id': 'Output1',
                  'Context': '',
                  'Boolean': false,
                  'Isnecessary': true,
                  'name': (node.OriginalTextName || 'Output1'),
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
          // 清理并重建输出 UI（移除旧 Json 容器）
          try {
            const containers = Array.from(outputColumn.querySelectorAll('[id^="outputContainer_s_"]'));
            containers.forEach(el => { try { el.parentNode.removeChild(el); } catch(_) {} });
            console.warn('[OutputSelect.change] switched to OriginalText, removed json containers=', containers.length);
          } catch(e) { console.warn('cleanup json containers error', e); }
        }
        else
        {
          // Json 模式下显示新增输出加号
          addNode1.style.display = 'block';
          //JsonColumn显示
          OriginalTextColumn.style.display = 'none';
          JsonColumn.style.display = 'block';
          let data = graph.save();
          data.nodes.forEach((node) => {
            if (node.id == id) {
              // 保存当前 OriginalText 的输出到 OriginalTextArray
              node.OriginalTextArray=node.Outputs;
              // 用持久化的 JsonOutputs 恢复（深拷贝防止联动）
              if(Array.isArray(node.JsonOutputs)){
                try {
                  node.Outputs = (typeof structuredClone === 'function')
                    ? structuredClone(node.JsonOutputs)
                    : JSON.parse(JSON.stringify(node.JsonOutputs));
                } catch (_) {
                  node.Outputs = JSON.parse(JSON.stringify(node.JsonOutputs));
                }
              } else {
                // Fallback：从 ExprotAfterPrompt 模板解析 键名/描述/类型 生成默认 Json 输出
                try {
                  const tpl = (node.ExprotAfterPrompt || '').toString();
                  const braceStart = tpl.indexOf('{');
                  const braceEnd   = tpl.lastIndexOf('}');
                  const body = (braceStart !== -1 && braceEnd !== -1 && braceEnd > braceStart)
                    ? tpl.slice(braceStart + 1, braceEnd)
                    : tpl;

                  // 1) 优先解析出 key/desc/type
                  const parsed = [];
                  body.split('\n').forEach((lineRaw) => {
                    const line = (lineRaw || '').trim();
                    if (!line) return;
                    const mKV = line.match(/"([^"\n]+)"\s*:\s*"([^"\n]*)"/);
                    if (mKV) {
                      const key = (mKV[1] || '').trim();
                      const desc = (mKV[2] || '').trim();
                      let kind = 'String';
                      const mType = line.match(/output\s*type\s*:\s*([A-Za-z]+)/i);
                      if (mType) {
                        const t = (mType[1] || '').toLowerCase();
                        if (t.includes('bool')) kind = 'Boolean';
                        else if (t.includes('num') || t === 'int' || t === 'float') kind = 'Num';
                        else kind = 'String';
                      }
                      if (key) parsed.push({ key, desc, kind });
                    }
                  });

                  let built;
                  if (parsed.length) {
                    built = parsed.map((p, idx) => ({
                      'Num': 0,
                      'Kind': p.kind,
                      'Id': p.key,
                      'Context': '',
                      'Boolean': false,
                      'Isnecessary': true,
                      'name': p.key,
                      'Description': p.desc,
                      'Link': 0,
                      'IsLabel': false,
                    }));
                  } else {
                    // 2) 退化：仅解析键名
                    const keyRegex = /"([^"\n]+)"\s*:/g;
                    const keys = [];
                    let m;
                    while ((m = keyRegex.exec(body)) !== null) {
                      const k = (m[1] || '').trim();
                      if (k && !keys.includes(k)) keys.push(k);
                    }
                    built = (keys.length ? keys : ['Output1']).map((k, idx) => ({
                      'Num': 0,
                      'Kind': 'String',
                      'Id': k || ('Output' + (idx + 1)),
                      'Context': '',
                      'Boolean': false,
                      'Isnecessary': true,
                      'name': k || ('Output' + (idx + 1)),
                      'Description': '',
                      'Link': 0,
                      'IsLabel': false,
                    }));
                  }
                  node.Outputs = built;
                  // 同步持久化，避免再次切换丢失
                  node.JsonOutputs = built;
                  console.warn('[OutputSelect.change] built from template outputs=', built.map(o=>({Id:o.Id,name:o.name,Kind:o.Kind}))); 
                } catch (e) {
                  // 兜底：至少提供一个默认输出
                  node.Outputs = [{
                    'Num': 0,
                    'Kind': 'String',
                    'Id': 'Output1',
                    'Context': '',
                    'Boolean': false,
                    'Isnecessary': true,
                    'name': 'Output1',
                    'Description': '',
                    'Link': 0,
                    'IsLabel': false,
                  }];
                  node.JsonOutputs = node.Outputs;
                  console.warn('[OutputSelect.change] fallback default outputs for node=', id);
                }
              }
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
          
          // 先强制清理并根据当前 Outputs 全量重建一次（避免存在但内容不对的容器）
          try {
            const cur0 = graph.save().nodes.find(n=>n.id==id);
            const outs0 = (cur0 && Array.isArray(cur0.Outputs)) ? cur0.Outputs : [];
            const containers0 = Array.from(outputColumn.querySelectorAll('[id^="outputContainer_s_"]'));
            containers0.forEach(el => { try { el.parentNode.removeChild(el); } catch(_) {} });
            outs0.forEach((op, idx) => { try { CreatOutputs(op, idx, op.Id); } catch(e) { console.warn('CreatOutputs (force) error', e); } });
            console.warn('[OutputSelect.change] force rebuilt json outputs once, outs=', outs0.length);
          } catch(e) { console.warn('force rebuild error', e); }

          // 若未渲染出 Json 输出 UI，重试渲染（最多 20 次，每次 50ms）
          (function ensureOutputsRendered(attempt){
            try {
              const cur = graph.save().nodes.find(n=>n.id==id);
              const outs = (cur && Array.isArray(cur.Outputs)) ? cur.Outputs : [];
              const containers = Array.from(outputColumn.querySelectorAll('[id^="outputContainer_s_"]'));
              const needRebuild = containers.length !== outs.length || containers.length === 0;
              console.warn('[OutputSelect.change][retry]', attempt, 'containers=', containers.length, 'outputs=', outs.length, 'needRebuild=', needRebuild);
              if (!needRebuild) return; // 已匹配
              // 清理并重建
              containers.forEach(el => { try { el.parentNode.removeChild(el); } catch(_) {} });
              outs.forEach((op, idx) => {
                try { CreatOutputs(op, idx, op.Id); } catch(e) { console.warn('CreatOutputs error', e); }
              });
            } catch(e) { console.warn('ensureOutputsRendered error', e); }
            if (attempt < 20) setTimeout(() => ensureOutputsRendered(attempt + 1), 50);
          })(1);
        }
      });
      // 将输入和输出列添加到节点容器中
      addNode1.onmousedown = function() {
        let data=graph.save();
        data.nodes.forEach((node) => {
          if(node.id == id)
          {
            // 唯一 Id，避免删除后复用
            const baseCount = node.Outputs.length + 1;
            const makeId = () => `Output${baseCount}_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
            IdTemp = makeId();
            while (node.Outputs.some(output => output.Id === IdTemp)) {
              IdTemp = makeId();
            }

            // 唯一 name
            let TempName = 'Output' + baseCount.toString();
            let counter = 1; // 新增一个计数器
            // 检查是否重名，如果重名则+1继续检查
            while (node.Outputs.some(output => output.name === TempName)) {
                TempName = 'Output' + (baseCount + counter).toString(); // 使用计数器调整名称
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
      let __otNameDefault = (OriginalTextName && OriginalTextName !== 'undefined') ? OriginalTextName : (function(){
        try{
          let data = graph.save();
          let node = data.nodes.find(n=>n.id==id);
          if(node && Array.isArray(node.OriginalTextArray) && node.OriginalTextArray.length>0 && node.OriginalTextArray[0].name){
            return node.OriginalTextArray[0].name;
          }
        }catch(e){}
        return 'Output1';
      })();
      OriginalTextNameLabel.value = __otNameDefault;
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
        // 首次面板构建时的基线日志（非 change 事件路径）
        try {
          const cur = graph.save().nodes.find(n=>n.id==id) || {};
          const containers = Array.from(outputColumn.querySelectorAll('[id^="outputContainer_s_"]'));
          console.warn('[InitialJsonRender] containers=', containers.length, 'outputs=', (cur.Outputs||[]).length);
          // 如果是首次进入且尚未渲染容器，但已有 Outputs，则立即渲染一次
          if (containers.length === 0 && Array.isArray(cur.Outputs) && cur.Outputs.length > 0) {
            (cur.Outputs||[]).forEach((op, idx) => {
              try { CreatOutputs(op, idx, op.Id); } catch(e) { console.warn('Initial CreatOutputs error', e); }
            });
          }
        } catch(_) {}
      }

      function CreatOutputs(output, index,IdTemp) {
        const realId = IdTemp || output.Id;
        // 去重：若已存在相同 Id 的容器，先移除再创建，防止重复渲染
        try {
          const containerId = `outputContainer_s_${realId}`;
          const existed = outputColumn.querySelector(`#${CSS.escape(containerId)}`);
          if (existed && existed.parentNode) {
            existed.parentNode.removeChild(existed);
            console.warn('[CreatOutputs] removed duplicated container for', realId);
          }
        } catch(_) {}
        const outputContainer = document.createElement('div');
        outputContainer.className = 'output-container';
        outputContainer.id = `outputContainer_s_${realId}`;
        outputContainer.style.display = 'flex';
        outputContainer.style.alignItems = 'flex-start'; // Content aligned at top
        outputContainer.style.flexWrap = 'wrap'; // Allow child elements to wrap
        outputContainer.style.marginBottom = '10px'; // Increase line spacing
        outputContainer.style.maxHeight = '300px'; // Set maximum height
        outputContainer.style.overflowY = 'auto'; // Add vertical scrollbar when needed


        // Create an input box to display the output name
        const outputName = document.createElement('input');
        outputName.value = output.name;
        outputName.style.width = '160px'; // 更宽，便于看清
        outputContainer.appendChild(outputName);

        // Create type selection box
        const Select1 = document.createElement('select');
        Select1.style.width = '120px'; // 稍宽
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
                if (output.Id == realId) {
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
        // Set the value (avoid "undefined" showing in textarea)
        Description.value = (output && output.Description != null) ? output.Description : '';
        

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
                  if(output.Id == realId)
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
          ChangeAnchorLabel(id, outputName.value, index,realId,false); // 假定 id 和 ChangeNodeLabel 已定义
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
              let Temp='' ;
              Temp+='Please ensure the output is in JSON format\n';
                  Temp+='{\n';
              // 关键修复：面板渲染读取的是 node.Outputs，但切换模式时可能存在 node.JsonOutputs；
              // 为了“再次点击仍然是修改后的值”，这里同步写入 Outputs 和 JsonOutputs（如果存在）。
              const newDesc = Description.value;
              const outputsMain = Array.isArray(node.Outputs) ? node.Outputs : [];
              const outputsJson = Array.isArray(node.JsonOutputs) ? node.JsonOutputs : null;

              const syncDesc = (arr) => {
                arr.forEach((out) => {
                  if (out && out.Id == realId) out.Description = newDesc;
                });
              };
              syncDesc(outputsMain);
              if (outputsJson) syncDesc(outputsJson);

              // Prompt 内容优先使用 Outputs（因为 UI / 执行侧通常以它为准）
              outputsMain.forEach((output,index) => {
                  let Kind='';
                  const k = (output && output.Kind != null) ? String(output.Kind) : '';
                  if(k.includes('String'))
                    Kind='String';
                  else if(k=='Num')
                    Kind='Num';
                  else if(k=='Boolean')
                    Kind='Boolean';
                  Temp+='"'+output.Id+'"' + ':' + '"'+(output.Description ?? '')+'"' +'(you need output type:'+Kind+')'+ '\n';

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
              let Temp='' ;
              Temp+='Please ensure the output is in JSON format\n';
                  Temp+='{\n';
              const newDesc = Description.value;
              const outputsMain = Array.isArray(node.Outputs) ? node.Outputs : [];
              const outputsJson = Array.isArray(node.JsonOutputs) ? node.JsonOutputs : null;

              const syncDesc = (arr) => {
                arr.forEach((out) => {
                  if (out && out.Id == realId) out.Description = newDesc;
                });
              };
              syncDesc(outputsMain);
              if (outputsJson) syncDesc(outputsJson);

              outputsMain.forEach((output,index) => {
                  let Kind='';
                  const k = (output && output.Kind != null) ? String(output.Kind) : '';
                  if(k.includes('String'))
                    Kind='String';
                  else if(k=='Num')
                    Kind='Num';
                  else if(k=='Boolean')
                    Kind='Boolean';
                  Temp+='"'+output.Id+'"' + ':' + '"'+(output.Description ?? '')+'"' +'(you need output type:'+Kind+')'+ '\n';

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
                  // 移除之前的按钮和图标
                  const existingButton = inputContainer.querySelector('button');
                  if (existingButton && inputContainer.contains(existingButton)) {
                    inputContainer.removeChild(existingButton);
                  }
                  
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
                  // 如果是 String_Key 类型且 selectBox 是 Input，需要重新渲染以显示图标
                  if(this.value == 'String_Key' && selectBox.value == 'Input' && labelTextarea) {
                    // 触发 handleChange 重新渲染
                    handleChange('Input');
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
        SubNode.style.left = '470px'; // 设置与标签之间的间距
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
                  // 如果当前选择是"Input"，根据类型渲染控件
                  if (input.Kind == 'Boolean') {
                    labelTextarea = document.createElement('select');
                    const optTrue = document.createElement('option');
                    optTrue.value = 'true';
                    optTrue.text  = 'true';
                    const optFalse = document.createElement('option');
                    optFalse.value = 'false';
                    optFalse.text  = 'false';
                    labelTextarea.appendChild(optTrue);
                    labelTextarea.appendChild(optFalse);
                    let initVal = (typeof input.Boolean === 'boolean')
                                  ? (input.Boolean ? 'true' : 'false')
                                  : ((input.Context != null) ? String(input.Context).toLowerCase() : 'false');
                    labelTextarea.value = initVal;
                    let uniqueClass = `unique-textarea-${id}-${input.Id}`;
                    labelTextarea.className = uniqueClass;
                    labelTextarea.id = uniqueClass;
                    labelTextarea.classList.add(uniqueClass);
                    labelTextarea.style.width = '120px';
                    ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id);
                    labelTextarea.addEventListener('change', function () {
                      ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id);
                    });
                    // 让布尔选择器换行显示
                    inputContainer.style.flexWrap = 'wrap';
                    const br = document.createElement('div');
                    br.style.flexBasis = '100%';
                    inputContainer.appendChild(br);
                    inputContainer.appendChild(labelTextarea);
                  } else {
                    // 非 Boolean 维持原先的文本域逻辑
                    labelTextarea = document.createElement('textarea');
                    if(input.Kind == 'Num')
                    labelTextarea.value = input.Num;
                    else if(input.Kind .includes('String'))
                    labelTextarea.value = input.Context;
                    // String_Key 类型需要调整宽度，为图标留出空间
                    if(input.Kind == 'String_Key') {
                      labelTextarea.style.width = '520px'; // 减小宽度为图标留空间
                    } else if(input.Kind.includes('FilePath')) {
                      labelTextarea.style.width = '490px'; // 设置固定宽度
                    } else {
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
                  if (labelTextarea.value.match(/^-?[0-9]+(\.[0-9]+)?$/)) 
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
                // 如果是 String_Key 类型，添加密钥选择图标
                if(input.Kind == 'String_Key') {
                  const keyIcon = document.createElement('button');
                  keyIcon.innerHTML = '<i class="fas fa-key"></i>';
                  keyIcon.style.cssText = 'width: 24px; height: 24px; border: none; background: rgba(0, 212, 255, 0.2); color: #00d4ff; cursor: pointer; border-radius: 4px; display: flex; align-items: center; justify-content: center; margin-left: 4px;';
                  keyIcon.title = '选择密钥';
                  
                  let secretMenu = null;
                  keyIcon.addEventListener('click', function(e) {
                    e.stopPropagation();
                    // 如果菜单已存在，则移除
                    if(secretMenu && secretMenu.parentNode) {
                      secretMenu.parentNode.removeChild(secretMenu);
                      secretMenu = null;
                      return;
                    }
                    
                    // 创建菜单
                    secretMenu = document.createElement('div');
                    secretMenu.style.cssText = 'position: absolute; background: rgba(30, 30, 40, 0.95); border: 1px solid rgba(0, 212, 255, 0.3); border-radius: 8px; padding: 8px 0; min-width: 200px; max-height: 300px; overflow-y: auto; z-index: 10000; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);';
                    
                    // 获取密钥列表
                    fetch('/api/secrets/get-config')
                      .then(res => res.json())
                      .then(data => {
                        const secrets = data.secrets || [];
                        if(secrets.length === 0) {
                          const emptyItem = document.createElement('div');
                          emptyItem.textContent = '暂无密钥';
                          emptyItem.style.cssText = 'padding: 8px 16px; color: #888; font-size: 12px;';
                          secretMenu.appendChild(emptyItem);
                        } else {
                          secrets.forEach(secret => {
                            if(secret.name) {
                              const menuItem = document.createElement('div');
                              menuItem.textContent = secret.name;
                              menuItem.style.cssText = 'padding: 8px 16px; color: #fff; cursor: pointer; font-size: 13px; transition: background 0.2s;';
                              menuItem.addEventListener('mouseenter', function() {
                                this.style.background = 'rgba(0, 212, 255, 0.2)';
                              });
                              menuItem.addEventListener('mouseleave', function() {
                                this.style.background = 'transparent';
                              });
                              menuItem.addEventListener('click', function() {
                                labelTextarea.value = secret.name;
                                ChangeAnchorValue(id, secret.name, 'Input', input.Id);
                                if(secretMenu && secretMenu.parentNode) {
                                  secretMenu.parentNode.removeChild(secretMenu);
                                  secretMenu = null;
                                }
                              });
                              secretMenu.appendChild(menuItem);
                            }
                          });
                        }
                        
                        // 定位菜单
                        const rect = keyIcon.getBoundingClientRect();
                        secretMenu.style.left = (rect.left + rect.width) + 'px';
                        secretMenu.style.top = rect.top + 'px';
                        document.body.appendChild(secretMenu);
                      })
                      .catch(err => {
                        console.error('获取密钥列表失败:', err);
                        const errorItem = document.createElement('div');
                        errorItem.textContent = '加载失败';
                        errorItem.style.cssText = 'padding: 8px 16px; color: #dc3545; font-size: 12px;';
                        secretMenu.appendChild(errorItem);
                        const rect = keyIcon.getBoundingClientRect();
                        secretMenu.style.left = (rect.left + rect.width) + 'px';
                        secretMenu.style.top = rect.top + 'px';
                        document.body.appendChild(secretMenu);
                      });
                  });
                  
                  // 点击其他地方关闭菜单
                  document.addEventListener('click', function closeMenu(e) {
                    if(secretMenu && !secretMenu.contains(e.target) && e.target !== keyIcon) {
                      if(secretMenu.parentNode) {
                        secretMenu.parentNode.removeChild(secretMenu);
                      }
                      secretMenu = null;
                      document.removeEventListener('click', closeMenu);
                    }
                  });
                  
                  inputContainer.appendChild(keyIcon);
                }
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
                    const baseCount = node.Inputs.length + 1;
                    let TempName = 'Input' + baseCount.toString();
                    let counter = 1; // 新增一个计数器
                    // 检查是否重名，如果重名则+1继续检查
                    while (node.Inputs.some(input => input.name === TempName)) {
                        TempName = 'Input' + (baseCount + counter).toString(); // 使用计数器调整名称
                        counter++; // 每次循环递增计数器
                    }
                    // 生成唯一 Id
                    let IdTemp = 'Input' + baseCount.toString() + '_' + Date.now();
                    while (node.Inputs.some(input => input.Id === IdTemp)) {
                      IdTemp = 'Input' + baseCount.toString() + '_' + Date.now() + '_' + Math.floor(Math.random()*1000);
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
         // 设置左边距
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
              // 唯一 Id，避免删除后复用
              const baseCount = node.Outputs.length + 1;
              const makeId = () => `Output${baseCount}_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
              IdTemp = makeId();
              while (node.Outputs.some(output => output.Id === IdTemp)) {
                IdTemp = makeId();
              }

              // 唯一 name
              let TempName = 'Output' + baseCount.toString();
              let counter = 1; // 新增一个计数器
              // 检查是否重名，如果重名则+1继续检查
              while (node.Outputs.some(output => output.name === TempName)) {
                  TempName = 'Output' + (baseCount + counter).toString(); // 使用计数器调整名称
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
          const realId = IdTemp || output.Id;
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
            ChangeAnchorLabel(id, outputName.value, index,realId,false); // 假定 id 和 ChangeNodeLabel 已定义
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
          if(output.TriggerKind != 'STOP' && output.TriggerKind != 'SKIP')
          {
            output.TriggerKind = 'STOP';
            let data = graph.save();
            data.nodes.forEach((node) => {
              if (node.id == id) {
                node.Outputs.forEach((output,index) => {
                    if (output.Id == realId) {
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
                    if (output.Id == realId) {
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
            SubNode.style.right = '90px'; // 设置与 Description 之间的间距
            outputContainer.appendChild(SubNode);
            SubNode.onmousedown = function() {//删除这个矛点
              let data=graph.save();
              data.nodes.forEach((node) => {
                if(node.id == id)
                {
                  //通过IdTemp删除这个矛点
                  node.Outputs.forEach((output,index) => {
                      if(output.Id == realId)
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
            if (!Array.isArray(tempoutput.IfLogicConditionArray)) {
              tempoutput.IfLogicConditionArray = [];
            }
            if (tempoutput && tempoutput.IfLogicConditionArray && tempoutput.IfLogicConditionArray[rowIndex] != undefined) {
                // 兼容历史拼写：no empty -> not empty
                const v = tempoutput.IfLogicConditionArray[rowIndex];
                condition.value = (v === 'no empty') ? 'not empty' : (v || '');
            } else {
                // 关键修复：即使用户不点下拉框，也要把默认值写回配置
                tempoutput.IfLogicConditionArray[rowIndex] = condition.value;
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
              // 同步保存当前默认/选中条件，避免 IfLogicConditionArray 缺失导致后端走默认 include
              if (!Array.isArray(tempoutput.IfLogicConditionArray)) {
                tempoutput.IfLogicConditionArray = [];
              }
              tempoutput.IfLogicConditionArray[rowIndex] = condition.value;

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
                if (Array.isArray(tempoutput.IfLogicConditionArray)) {
                  tempoutput.IfLogicConditionArray.splice(idx, 1);
                }
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
                // 使用 not empty；同时后端也会兼容 no empty（历史拼写）
                ['exclude', 'include', 'empty', 'not empty'].forEach(v => {
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
        const optionKey = document.createElement('option');
        optionKey.value = 'String_Key';
        optionKey.text = 'Key';
        Select1.appendChild(optionContext);
        Select1.appendChild(optionNum);
        Select1.appendChild(optionBool);
        Select1.appendChild(optionKey);
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
                    // 如果是 String_Key 类型且 selectBox 是 Input，需要重新渲染以显示图标
                    if(this.value == 'String_Key' && selectBox.value == 'Input' && labelTextarea) {
                      // 触发 handleChange 重新渲染
                      handleChange('Input');
                    }
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
          SubNode.style.left = '440px'; // 设置与标签之间的间距
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
                  // 如果当前选择是"Input"，根据类型渲染控件
                  if (input.Kind == 'Boolean') {
                    labelTextarea = document.createElement('select'); // 使用下拉框 True/False
                    const optTrue = document.createElement('option');
                    optTrue.value = 'true';
                    optTrue.text  = 'true';
                    const optFalse = document.createElement('option');
                    optFalse.value = 'false';
                    optFalse.text  = 'false';
                    labelTextarea.appendChild(optTrue);
                    labelTextarea.appendChild(optFalse);
                    let initVal = (typeof input.Boolean === 'boolean')
                                  ? (input.Boolean ? 'true' : 'false')
                                  : ((input.Context != null) ? String(input.Context).toLowerCase() : 'false');
                    labelTextarea.value = initVal;
                    let uniqueClass = `unique-textarea-${id}-${input.Id}`;
                    labelTextarea.className = uniqueClass;
                    labelTextarea.id = uniqueClass;
                    labelTextarea.classList.add(uniqueClass);
                    labelTextarea.style.width = '120px';
                    labelTextarea.addEventListener('change', function() {
                      ChangeAnchorValue(id, labelTextarea.value, 'Input',input.Id);
                    });
                    // 让布尔选择器换行显示
                    inputContainer.style.flexWrap = 'wrap';
                    const br = document.createElement('div');
                    br.style.flexBasis = '100%';
                    inputContainer.appendChild(br);
                    inputContainer.appendChild(labelTextarea);
                  } else {
                    // 其余类型保持文本域
                    labelTextarea = document.createElement('textarea'); // 在外部声明变量以便在不同的作用域中访问
                    labelTextarea.className = 'normalInput-textarea';
                    if(input.Kind == 'Num')
                    labelTextarea.value = input.Num;
                    else if(input.Kind .includes('String'))
                    labelTextarea.value = input.Context;
                    
                    // String_Key 类型需要调整宽度，为图标留出空间
                    if(input.Kind == 'String_Key') {
                      labelTextarea.style.width = '520px'; // 减小宽度为图标留空间
                    } else {
                      labelTextarea.style.width = '550px'; // 设置固定宽度
                    }
                    labelTextarea.style.height = '50px'; // 初始高度
                  let uniqueClass = `unique-textarea-${id}-${input.Id}`;
                  labelTextarea.className = 'normalInput-textarea ' + uniqueClass; // 同时设置两个类名
                  labelTextarea.id = uniqueClass;
                  labelTextarea.classList.add(uniqueClass); // 为文本区域添加唯一类名
                  //labelTextarea.style.resize = 'none'; // 禁止用户手动调整大小
                  labelTextarea.addEventListener('input', function() {
                  let isOk = true; // 假定输入无效
                  if(input.Kind == 'Num') {
                    if (labelTextarea.value.match(/^-?[0-9]+(\.[0-9]+)?$/)) 
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
                  
                  // 如果是 String_Key 类型，添加密钥选择图标
                  if(input.Kind == 'String_Key') {
                    const keyIcon = document.createElement('button');
                    keyIcon.innerHTML = '<i class="fas fa-key"></i>';
                    keyIcon.style.cssText = 'width: 24px; height: 24px; border: none; background: rgba(0, 212, 255, 0.2); color: #00d4ff; cursor: pointer; border-radius: 4px; display: flex; align-items: center; justify-content: center; margin-left: 4px;';
                    keyIcon.title = '选择密钥';
                    
                    let secretMenu = null;
                    keyIcon.addEventListener('click', function(e) {
                      e.stopPropagation();
                      // 如果菜单已存在，则移除
                      if(secretMenu && secretMenu.parentNode) {
                        secretMenu.parentNode.removeChild(secretMenu);
                        secretMenu = null;
                        return;
                      }
                      
                      // 创建菜单
                      secretMenu = document.createElement('div');
                      secretMenu.style.cssText = 'position: absolute; background: rgba(30, 30, 40, 0.95); border: 1px solid rgba(0, 212, 255, 0.3); border-radius: 8px; padding: 8px 0; min-width: 200px; max-height: 300px; overflow-y: auto; z-index: 10000; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);';
                      
                      // 获取密钥列表
                      fetch('/api/secrets/get-config')
                        .then(res => res.json())
                        .then(data => {
                          const secrets = data.secrets || [];
                          if(secrets.length === 0) {
                            const emptyItem = document.createElement('div');
                            emptyItem.textContent = '暂无密钥';
                            emptyItem.style.cssText = 'padding: 8px 16px; color: #888; font-size: 12px;';
                            secretMenu.appendChild(emptyItem);
                          } else {
                            secrets.forEach(secret => {
                              if(secret.name) {
                                const menuItem = document.createElement('div');
                                menuItem.textContent = secret.name;
                                menuItem.style.cssText = 'padding: 8px 16px; color: #fff; cursor: pointer; font-size: 13px; transition: background 0.2s;';
                                menuItem.addEventListener('mouseenter', function() {
                                  this.style.background = 'rgba(0, 212, 255, 0.2)';
                                });
                                menuItem.addEventListener('mouseleave', function() {
                                  this.style.background = 'transparent';
                                });
                                menuItem.addEventListener('click', function() {
                                  labelTextarea.value = secret.name;
                                  ChangeAnchorValue(id, secret.name, 'Input', input.Id);
                                  if(secretMenu && secretMenu.parentNode) {
                                    secretMenu.parentNode.removeChild(secretMenu);
                                    secretMenu = null;
                                  }
                                });
                                secretMenu.appendChild(menuItem);
                              }
                            });
                          }
                          
                          // 定位菜单
                          const rect = keyIcon.getBoundingClientRect();
                          secretMenu.style.left = (rect.left + rect.width) + 'px';
                          secretMenu.style.top = rect.top + 'px';
                          document.body.appendChild(secretMenu);
                        })
                        .catch(err => {
                          console.error('获取密钥列表失败:', err);
                          const errorItem = document.createElement('div');
                          errorItem.textContent = '加载失败';
                          errorItem.style.cssText = 'padding: 8px 16px; color: #dc3545; font-size: 12px;';
                          secretMenu.appendChild(errorItem);
                          const rect = keyIcon.getBoundingClientRect();
                          secretMenu.style.left = (rect.left + rect.width) + 'px';
                          secretMenu.style.top = rect.top + 'px';
                          document.body.appendChild(secretMenu);
                        });
                    });
                    
                    // 点击其他地方关闭菜单
                    document.addEventListener('click', function closeMenu(e) {
                      if(secretMenu && !secretMenu.contains(e.target) && e.target !== keyIcon) {
                        if(secretMenu.parentNode) {
                          secretMenu.parentNode.removeChild(secretMenu);
                        }
                        secretMenu = null;
                        document.removeEventListener('click', closeMenu);
                      }
                    });
                    
                    inputContainer.appendChild(keyIcon);
                  }
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

// 日志过滤：默认屏蔽 console.log，但允许特定前缀通过；保留 warn/error
;(function(){
  try {
    if (!console.__origLog) {
      console.__origLog = Function.prototype.bind.call(console.log, console);
    }
    // 配置项：
    // window.DEBUG_LOG_ALL = true  => 全量放行
    // window.DEBUG_LOG_ALLOW_PREFIXES = ['[SIDEWIN:', '🧪[WFDBG:'] => 仅放行以这些前缀开头的日志
    if (typeof window.DEBUG_LOG_ALL === 'undefined') window.DEBUG_LOG_ALL = false;
    if (!Array.isArray(window.DEBUG_LOG_ALLOW_PREFIXES)) window.DEBUG_LOG_ALLOW_PREFIXES = [];
    // 默认允许的日志前缀 - 仅允许运行完成摘要
    try {
      const defaults = ['[RUN:SUMMARY]', '[MERGE]', '[SIDEWIN:', 'executeNode:'];
      defaults.forEach(p => {
        if (window.DEBUG_LOG_ALLOW_PREFIXES.indexOf(p) === -1) {
          window.DEBUG_LOG_ALLOW_PREFIXES.push(p);
        }
      });
    } catch(_) {}

    const orig = console.__origLog;
    window.DEBUG_LOG_ALL = false;
    
    console.log = function(){
      try {
        if (window.DEBUG_LOG_ALL === true) {
          return orig.apply(console, arguments);
        }
        const allow = window.DEBUG_LOG_ALLOW_PREFIXES;
        if (Array.isArray(allow) && allow.length > 0) {
          // 只要任一参数是字符串且以任一允许前缀开头，则放行
          outer: for (let i = 0; i < arguments.length; i++) {
            const a = arguments[i];
            if (typeof a === 'string') {
              for (let j = 0; j < allow.length; j++) {
                const p = allow[j];
                if (p && a.startsWith(p)) {
                  return orig.apply(console, arguments);
                }
              }
            }
          }
          return; // 未匹配到前缀，丢弃
        }
        // 无前缀配置且未开启全量，默认丢弃
        return;
      } catch (_) {
        try { return orig.apply(console, arguments); } catch(e){}
      }
    };
  } catch(_) {}
})();

// —— 前端白名单日志面板（可输入逗号分隔前缀，直接在页面展示匹配日志）——
(function(){
  try {
    if (typeof window === 'undefined' || typeof document === 'undefined') return;

    // 简易工具
    function whitelistMatch(msg){
      try {
        const list = Array.isArray(window.LOG_ALLOW_PREFIXES) ? window.LOG_ALLOW_PREFIXES : [];
        if (!list.length) return false;
        if (typeof msg !== 'string') return false;
        for (let i=0;i<list.length;i++) {
          const p = String(list[i]||'').trim();
          if (!p) continue;
          if (msg.startsWith(p)) return true;
        }
      } catch(_) {}
      return false;
    }
    function toText(args){
      try {
        return Array.from(args).map(x => {
          if (typeof x === 'string') return x;
          try { return JSON.stringify(x); } catch(_) { return String(x); }
        }).join(' ');
      } catch(_) { return ''+args; }
    }

    // 面板 UI
    function installWhitelistPanel(){
      if (document.getElementById('log-wl-panel')) return;
      const panel = document.createElement('div');
      panel.id = 'log-wl-panel';
      panel.style.position = 'fixed';
      panel.style.right = '10px';
      panel.style.bottom = '10px';
      panel.style.width = '360px';
      panel.style.height = '220px';
      panel.style.background = 'rgba(0,0,0,0.75)';
      panel.style.color = '#d9d9d9';
      panel.style.font = '12px/1.4 monospace';
      panel.style.zIndex = '2147483647';
      panel.style.border = '1px solid #444';
      panel.style.borderRadius = '6px';
      panel.style.display = 'flex';
      panel.style.flexDirection = 'column';

      const head = document.createElement('div');
      head.style.padding = '6px';
      head.style.display = 'flex';
      head.style.gap = '6px';
      head.style.alignItems = 'center';

      const label = document.createElement('span');
      label.textContent = 'Whitelist:';
      label.style.color = '#9ad';

      const input = document.createElement('input');
      input.type = 'text';
      input.id = 'log-wl-input';
      input.placeholder = '[RING, 🌀 [RING, [SNAPSHOT], 🔍 [RING';
      input.style.flex = '1';
      input.style.minWidth = '0';

      const btnClear = document.createElement('button');
      btnClear.textContent = '清空';
      btnClear.style.cursor = 'pointer';
      btnClear.onclick = () => { body.textContent = ''; window.__WL_LOGS__ = []; };

      const btnHide = document.createElement('button');
      btnHide.textContent = '隐藏';
      btnHide.style.cursor = 'pointer';
      btnHide.onclick = () => { panel.style.display = 'none'; };

      head.appendChild(label); head.appendChild(input); head.appendChild(btnClear); head.appendChild(btnHide);

      const body = document.createElement('pre');
      body.id = 'log-wl-body';
      body.style.flex = '1';
      body.style.margin = '0';
      body.style.padding = '6px';
      body.style.whiteSpace = 'pre-wrap';
      body.style.overflow = 'auto';
      body.style.background = 'rgba(0,0,0,0.2)';

      panel.appendChild(head);
      panel.appendChild(body);
      document.body.appendChild(panel);

      // 初始化内容
      try {
        const saved = localStorage.getItem('log_wl_prefixes') || '';
        input.value = saved || '[RING, 🌀 [RING, [SNAPSHOT], 🔍 [RING';
        window.LOG_ALLOW_PREFIXES = input.value.split(',').map(s=>s.trim()).filter(Boolean);
      } catch(_) {}

      input.addEventListener('change', () => {
        window.LOG_ALLOW_PREFIXES = input.value.split(',').map(s=>s.trim()).filter(Boolean);
        try { localStorage.setItem('log_wl_prefixes', input.value); } catch(_) {}
      });

      // 提供全局追加接口
      window.__WL_LOGS__ = window.__WL_LOGS__ || [];
      window.__WL_APPEND__ = function(){
        try {
          const line = toText(arguments);
          window.__WL_LOGS__.push(line);
          if (window.__WL_LOGS__.length > 200) window.__WL_LOGS__.splice(0, window.__WL_LOGS__.length - 200);
          body.textContent = window.__WL_LOGS__.join('\n');
          body.scrollTop = body.scrollHeight;
        } catch(_) {}
      };
    }

    // 升级 console 包装：静默时，命中白名单的日志写入面板（并根据允许前缀决定是否放行到控制台）
    (function upgradeConsole(){
      if (!window.__ORIG_CONSOLE__) return; // 未安装静默器
      const c = window.__ORIG_CONSOLE__;
      const wrapForPanel = (orig) => function(){
        try {
          const first = arguments[0];
          const match = (typeof first === 'string') && whitelistMatch(first);
          if (match) {
            if (typeof window.__WL_APPEND__ === 'function') window.__WL_APPEND__.apply(null, arguments);
            // 命中白名单时：即使静默也允许输出到控制台，便于调试
            return orig.apply(console, arguments);
          }
          // 非静默：原样输出
          if (!window.LOG_SILENT) return orig.apply(console, arguments);
        } catch(_) {}
        return undefined;
      };
      console.log  = wrapForPanel(c.log);
      console.info = wrapForPanel(c.info);
      console.debug= wrapForPanel(c.debug);
      console.warn = wrapForPanel(c.warn);
    })();

    const ready = () => installWhitelistPanel();
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready);
    else ready();
  } catch(_) {}
})();

// 创建侧边窗口函数
function createSideWindow(item, isCheckMode = false) {
  // [FIX] 始终从 graph.save() 取最新节点
  function getLiveNodeById(id) {
    const g = graph.save();

    const xs = Array.isArray(g?.nodes) ? g.nodes : [];
    return xs.find(n => n.id === id) || null;
  }
  console.warn('[MODE]🔍  createSideWindow',item);
  // 🔍 函数入口调试信息
  try {
    if (window.__snapshotRing && Array.isArray(window.__snapshotRing.items)) {
      console.warn('🌀 [RING:DUMP] 当前全部快照环内容:', window.__snapshotRing.items);
    } else {
      console.warn('🌀 [RING:DUMP] snapshotRing 不存在或格式错误');
    }
  } catch (err) {
    console.error('🌀 [RING:DUMP] 读取 snapshotRing 失败:', err);
  }  
  const { nodes, edges } = graph.save();
  // 获取节点数据（优先最近活跃快照）
  const latestGraph = getLatestActiveGraph();
  // 侧窗历史选择：为每个节点记忆用户选择的快照
  window.__sidewinSelectedGraphs = window.__sidewinSelectedGraphs || {};
  // 首次打开：检查模式默认使用最近活跃快照；非检查模式默认使用“最新”（null）
  if (typeof window.__sidewinSelectedGraphs[item.id] === 'undefined') {
    window.__sidewinSelectedGraphs[item.id] = isCheckMode ? (latestGraph || null) : null;
  }
  const selectedGraphForNode = (window.__sidewinSelectedGraphs[item.id] || null);
  // 优先使用用户选择的快照，否则使用最近活跃快照（所有模式均可用）
  // 若记忆选择存在但不是“finalish”，则回退到最近一条 finalish 快照；否则使用记忆/最新
  let activeGraph = selectedGraphForNode || latestGraph || null;
  try {
    const isFinal = activeGraph && Array.isArray(activeGraph.nodes) && activeGraph.nodes.some(isNodeFinalish);
    if (!isFinal) {
      const ring = (window.__snapshotRing && Array.isArray(window.__snapshotRing.items)) ? window.__snapshotRing.items : [];
      const findFinal = ring.find(g => g && Array.isArray(g.nodes) && g.nodes.some(isNodeFinalish));
      if (findFinal) {
        activeGraph = findFinal;
        console.warn('[WFDBG:SIDEWIN] fallback to nearest finalish snapshot');
      }
    }
  } catch(_) {}

  // 数据源优先级：
  // - 记录模式：优先使用 window.__recordModeCurrentGraph（当前加载的记录数据），避免被运行时数据"霸占"
  // - monitor_completed 模式：优先使用 window.__lastCompletedGraphData（包含完整的 Outputs）
  // - 其他模式：activeGraph → TempMessageNode → graph.save（与"历史/最新"选择保持一致）
  function findNodeFromSources(nodeId) {
    // 🔥 关键修复：在记录模式下，优先使用当前加载的记录图数据，避免被运行时的数据"霸占"
    if (isRecordMode && window.__recordModeCurrentGraph) {
      const recordArr = (window.__recordModeCurrentGraph && window.__recordModeCurrentGraph.nodes) || [];
      const fromRecord = Array.isArray(recordArr) ? recordArr.find(n => n && n.id === nodeId) : null;
      if (fromRecord) {
        console.warn('[SIDEWIN:SOURCE] use __recordModeCurrentGraph (record mode)');
        // 打印节点的 Outputs 信息，用于调试
        if (fromRecord.Outputs && Array.isArray(fromRecord.Outputs)) {
          console.log(`[SIDEWIN:OUTPUTS] 节点 ${fromRecord.label || fromRecord.id} 的 Outputs:`, fromRecord.Outputs.map(o => ({
            name: o.name,
            Context: o.Context ? (o.Context.length > 50 ? o.Context.substring(0, 50) + '...' : o.Context) : '',
            Num: o.Num,
            Boolean: o.Boolean
          })));
        }
        return fromRecord;
      }
    }
    
    // 🔥 关键修复：在 monitor_completed 模式下，优先使用保存的完整图数据（但不在记录模式下）
    if (!isRecordMode && frontendMode === 'monitor_completed' && window.__lastCompletedGraphData) {
      const completedArr = (window.__lastCompletedGraphData && window.__lastCompletedGraphData.nodes) || [];
      const fromCompleted = Array.isArray(completedArr) ? completedArr.find(n => n && n.id === nodeId) : null;
      if (fromCompleted) {
        console.warn('[SIDEWIN:SOURCE] use __lastCompletedGraphData (monitor_completed mode)');
        // 打印节点的 Outputs 信息，用于调试
        if (fromCompleted.Outputs && Array.isArray(fromCompleted.Outputs)) {
          console.log(`[SIDEWIN:OUTPUTS] 节点 ${fromCompleted.label || fromCompleted.id} 的 Outputs:`, fromCompleted.Outputs.map(o => ({
            name: o.name,
            Context: o.Context ? (o.Context.length > 50 ? o.Context.substring(0, 50) + '...' : o.Context) : '',
            Num: o.Num,
            Boolean: o.Boolean
          })));
        }
        return fromCompleted;
      }
    }
    
    // 在记录模式下，跳过 activeGraph（可能包含运行时的数据），直接使用 TempMessageNode 和 graph.save()
    // 因为它们已经被 applyRecordSnapshot 更新为记录数据
    if (isRecordMode) {
      const liveArr   = (TempMessageNode && TempMessageNode.nodes) || [];
      const graphArr  = (graph.save() && graph.save().nodes) || [];
      const fromLive = Array.isArray(liveArr) ? liveArr.find(n => n && n.id === nodeId) : null;
      if (fromLive) { console.warn('[SIDEWIN:SOURCE] use TempMessageNode (record mode)'); return fromLive; }
      const fromGraph = Array.isArray(graphArr) ? graphArr.find(n => n && n.id === nodeId) : null;
      if (fromGraph) { console.warn('[SIDEWIN:SOURCE] use graph.save() (record mode)'); return fromGraph; }
      return null;
    }
    
    // 非记录模式的正常流程
    const liveArr   = (TempMessageNode && TempMessageNode.nodes) || [];
    const activeArr = (activeGraph && activeGraph.nodes) || [];
    const graphArr  = (graph.save() && graph.save().nodes) || [];
    const fromActive = Array.isArray(activeArr) ? activeArr.find(n => n && n.id === nodeId) : null;
    if (fromActive) { console.warn('[SIDEWIN:SOURCE] use activeGraph'); return fromActive; }
    const fromLive = Array.isArray(liveArr) ? liveArr.find(n => n && n.id === nodeId) : null;
    if (fromLive) { console.warn('[SIDEWIN:SOURCE] use TempMessageNode'); return fromLive; }
    const fromGraph = Array.isArray(graphArr) ? graphArr.find(n => n && n.id === nodeId) : null;
    if (fromGraph) { console.warn('[SIDEWIN:SOURCE] use graph.save()'); return fromGraph; }
    return null;
  }

  const node = findNodeFromSources(item.id);
  const tempNode = node;
      
  // 🔍 数据源调试信息
  console.log('[SIDEWIN:ENTRY] 数据源状态:');
  console.log('  - frontendMode:', frontendMode);
  console.log('  - __lastCompletedGraphData 存在:', !!window.__lastCompletedGraphData);
  console.log('  - __lastCompletedGraphData.nodes 数量:', window.__lastCompletedGraphData?.nodes?.length || 0);
  console.log('  - latestGraph 存在:', !!latestGraph);
  console.log('  - latestGraph.nodes 数量:', latestGraph?.nodes?.length || 0);
  const ringItems = (window.__snapshotRing && Array.isArray(window.__snapshotRing.items)) ? window.__snapshotRing.items : [];
  console.log('  - snapshotRing.size:', ringItems.length);
  try { console.log('  - snapshotRing.indexes:', ringItems.map((_,i)=>i)); } catch(_) {}
  console.log('  - activeGraph 使用来源:', selectedGraphForNode ? 'userSelectedSnapshot' : (latestGraph ? 'latestActiveSnapshot':'none'));
  console.log('  - activeGraph.nodes 数量:', activeGraph?.nodes?.length || 0);
  console.log('  - TempMessageNode 存在:', !!TempMessageNode);
  console.log('  - TempMessageNode.nodes 数量:', TempMessageNode?.nodes?.length || 0);
  console.log('  - graph.save().nodes 数量:', graph.save().nodes?.length || 0);
  console.log('  - node 存在:', !!node);
  console.log('  - tempNode 存在:', !!tempNode);
  
  // 🔍 详细数据内容调试
  console.log('[SIDEWIN:ENTRY] 详细数据内容:');
  console.log('  - item.id:', item.id);
  console.log('  - node 详情:', node);
  console.log('  - tempNode 详情:', tempNode);
  
  if (latestGraph?.nodes) {
    console.log('  - latestGraph.nodes 中的节点ID:', latestGraph.nodes.map(n => n.id));
    const foundInLatest = latestGraph.nodes.find(n => n.id === item.id);
    console.log('  - 在 latestGraph 中找到的节点:', foundInLatest);
  }
  if (activeGraph?.nodes) {
    console.log('  - activeGraph.nodes 中的节点ID:', activeGraph.nodes.map(n => n.id));
    const foundInActive = activeGraph.nodes.find(n => n.id === item.id);
    console.log('  - 在 activeGraph 中找到的节点:', foundInActive);
  }
  
  if (TempMessageNode?.nodes) {
    console.log('  - TempMessageNode.nodes 中的节点ID:', TempMessageNode.nodes.map(n => n.id));
    const foundInTemp = TempMessageNode.nodes.find(n => n.id === item.id);
    console.log('  - 在 TempMessageNode 中找到的节点:', foundInTemp);
  }
  
  if (graph.save().nodes) {
    console.log('  - graph.save().nodes 中的节点ID:', graph.save().nodes.map(n => n.id));
    const foundInGraph = graph.save().nodes.find(n => n.id === item.id);
    console.log('  - 在 graph.save 中找到的节点:', foundInGraph);
  }
  
  try {
    console.log(`🧪[WFDBG:SIDEWIN] id=${item.id} isCheckMode=${!!isCheckMode} source=${(isCheckMode && (selectedGraphForNode||latestGraph))? 'snapshot':'live'} hasNode=${!!node} hasTempNode=${!!tempNode}`);
    const ca0 = document.getElementById('content-area');
    const sw0 = document.getElementById('side-window');
    console.log(`[SIDEWIN:DOM] content-area=${!!ca0} side-window=${!!sw0}`);
  } catch(_) {}

  if (!node) {
      console.error('未找到节点数据');
      return;
  }

  const contentArea = document.getElementById('content-area');
  if (!contentArea) { console.warn('[SIDEWIN:DOM] 缺少 #content-area，放弃渲染'); return; }
  contentArea.innerHTML = '';

  // 生成 Token 信息（如果有）
  let tokenInfo = '';
  if (tempNode && tempNode.Outputs?.[0]) {
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

  // 🔍 数据传递到HTML生成的调试
  console.log('[SIDEWIN:HTML] ===== HTML生成数据调试 =====');
  console.log('[SIDEWIN:HTML] node 用于输入和提示词:');
  console.log('  - node.Inputs 数量:', node?.Inputs?.length || 0);
  console.log('  - node.NodeKind:', node?.NodeKind);
  console.log('  - node.prompt:', node?.prompt);
  console.log('  - node.SystemPrompt:', node?.SystemPrompt);
  console.log('[SIDEWIN:HTML] tempNode 用于输出:');
  console.log('  - tempNode.Outputs 数量:', tempNode?.Outputs?.length || 0);
  console.log('  - tempNode.Outputs 详情:', tempNode?.Outputs);

  // 生成输入区域 HTML
  let inputsHtml = `
  <div class="section-container">
      <h3>Inputs</h3>
  `;
  if (node?.Inputs && Array.isArray(node.Inputs)) {
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
  } else {
    console.warn('[SIDEWIN:HTML] node.Inputs 不存在或不是数组:', node?.Inputs);
  }
  inputsHtml += '</div>';

  // 生成 Prompt 区域（如果是 LLM 节点）
  let promptHtml = '';
  const liveNode = getLiveNodeById(item.id);
  if ((liveNode?.NodeKind || '').includes('LLm')) {
      const promptValue = liveNode.prompt ?? '';
      const systemPromptValue = liveNode.SystemPrompt ?? '';
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
  if (tempNode?.Outputs && Array.isArray(tempNode.Outputs)) {
  tempNode.Outputs.forEach((output, index) => {
      let value = '';
      if (output.Kind === 'Num') {
          value = output.Num ?? '';
      } else if (output.Kind?.includes('String')) {
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
  } else {
    console.warn('[SIDEWIN:HTML] tempNode.Outputs 不存在或不是数组:', tempNode?.Outputs);
  }
  outputsHtml += '</div>';

  // Error / Debug 文本需要进入 textarea innerHTML，必须做转义（避免 </textarea> 破坏 DOM）
  function escapeForTextarea(val) {
    const s = (val === null || val === undefined) ? '' : String(val);
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/<\/textarea/gi, '&lt;/textarea');
  }

  //创建一个debug区域（优先使用快照中的 debug；若为空则回退到 tempNode.debug）
  let debugTextRaw = '';
  try {
    const snapNode = (activeGraph?.nodes || []).find(n => n.id === item.id);
    debugTextRaw = (snapNode && typeof snapNode.debug === 'string' && snapNode.debug.trim().length)
      ? snapNode.debug
      : ((typeof tempNode?.debug === 'string' && tempNode.debug.trim().length) ? tempNode.debug : (node.debug || ''));
  } catch(_) {
    debugTextRaw = (typeof tempNode?.debug === 'string' && tempNode.debug.trim().length) ? tempNode.debug : (node.debug || '');
  }
  // 🔧 兜底：如果快照/TempMessageNode 没有同步到 debug（例如 ring 未写入导致 activeGraph 还是旧快照），
  // 则回退到实时图（graph.save）里的节点 debug，确保侧窗能看到本次运行的后端 debug。
  try {
    const liveDbg = (typeof liveNode?.debug === 'string') ? liveNode.debug : '';
    if ((!debugTextRaw || !String(debugTextRaw).trim().length) && liveDbg && String(liveDbg).trim().length) {
      debugTextRaw = liveDbg;
      console.warn('[SIDEWIN:DEBUG] fallback to liveNode.debug (graph.save)');
    }
  } catch(_) {}

  // 若节点报错：把 ErrorContext + 最近一次后端错误明细拼进 Debug，方便直接查看
  try {
    const lastErr = window.__nodeLastBackendError && window.__nodeLastBackendError[item.id];
    const ctx = (tempNode && tempNode.ErrorContext) || (node && node.ErrorContext) || '';
    const detail = (lastErr && lastErr.detail) || '';
    if ((tempNode && tempNode.IsError) || (node && node.IsError) || ctx || detail) {
      const parts = [];
      if (ctx) parts.push(String(ctx));
      if (detail && detail !== ctx) parts.push(String(detail));
      const merged = parts.join('\n\n---\n\n');
      debugTextRaw = merged || debugTextRaw;
    }
  } catch (_) {}

  const debugText = (debugTextRaw || '').replace(/\\n/g, '\n');
  const debugTextSafe = escapeForTextarea(debugText);

  let debugHtml = `
    <div class="section-container">
        <h3>Debug</h3>
        <div class="debug-wrapper">
            <textarea class="side-window-textarea" style="white-space:pre-wrap;" readonly>${debugTextSafe}</textarea>
        </div>
    </div>`;
  // 历史快照选择框（所有模式显示，置顶）
  let historyHtml = '';
  {
    // === SideWindow 渲染 ===
    const allRings = ensureSnapshotRing();
    const nodeRings = pickRingsForNode(allRings, item.id); // ← 你的当前组件 id
    
    // 若无任何历史记录，清理此前的选择，保证"最新"有效
    try {
      window.__sidewinSelectedGraphs = window.__sidewinSelectedGraphs || {};
      if (!Array.isArray(nodeRings) || nodeRings.length === 0) {
        window.__sidewinSelectedGraphs[item.id] = null;
      }
    } catch(_) {}
    const selectedGraphForNode = (window.__sidewinSelectedGraphs && window.__sidewinSelectedGraphs[item.id]) || null;
    const options = [];
    // “最新”永远代表当前已选择的记录（若无则回退到实时图）
    options.push(`<option value="-1" selected>最新(graph.save)</option>`);
    // 历史记录保持不变 - 只显示与当前组件相关的记录
    nodeRings.forEach((g, idx) => {
      try {
        const sel = (selectedGraphForNode===g) ? 'selected' : '';
        options.push(`<option value="${idx}" ${sel}>记录${idx+1}</option>`);
      } catch(_) {}
    });
    historyHtml = `
      <div class="section-container">
        <h3>History</h3>
        <div class="prompt-wrapper">
          <select id="history-select-${item.id}" class="side-window-select">
            ${options.join('')}
          </select>
        </div>
      </div>
    `;
  }

  // 组合所有 HTML 内容（历史选择框置顶）并加上固定容器，便于局部刷新
  const tokenSection   = `<div id="token-section">${tokenInfo}</div>`;
  const inputsSection  = `<div id="inputs-section">${inputsHtml}</div>`;
  const promptSection  = `<div id="prompt-section">${promptHtml}</div>`;
  const outputsSection = `<div id="outputs-section">${outputsHtml}</div>`;
  const debugSection   = `<div id="debug-section">${debugHtml}</div>`;
  contentArea.innerHTML = historyHtml + tokenSection + inputsSection + promptSection + outputsSection + debugSection ;
  // 侧窗渲染完后，若允许编辑则绑定写回（Prompt）
  try {
    if (!isCheckMode) {
      const sysTa0 = document.getElementById('systemPrompt');
      const usrTa0 = document.getElementById('prompt');
      if (sysTa0) attachPromptHandlers(sysTa0, 'SystemPrompt');
      if (usrTa0) attachPromptHandlers(usrTa0, 'prompt');
    }
  } catch(_) {}
  try {
    const inputsCount  = Array.isArray(node && node.Inputs) ? node.Inputs.length : 0;
    const outputsCount = Array.isArray(tempNode && tempNode.Outputs) ? tempNode.Outputs.length : 0;
    console.log(`[SIDEWIN:DATA] inputs=${inputsCount} outputs=${outputsCount} debugLen=${debugText.length}`);
  } catch(_) {}

  // 🔥 保存当前打开的节点信息，用于记录模式下的自动刷新
  window.__currentSideWindowNode = item;
  window.__currentSideWindowIsCheckMode = isCheckMode;

  // 显示侧边窗口 (Apple Style Animation)
  const sideWindow = document.getElementById('side-window');
  sideWindow.style.display = 'flex'; // Ensure it's in the DOM for transition
  // Use requestAnimationFrame to ensure the browser registers the display change before adding the class
  requestAnimationFrame(() => {
      sideWindow.classList.add('visible');
  });
  try { console.log(`[SIDEWIN:DOM] show side-window display=${sideWindow && sideWindow.style && sideWindow.style.display}`); } catch(_) {}
  // 确保关闭按钮始终可见
  try { const closeBtn = document.getElementById('close-button'); if (closeBtn) closeBtn.style.display = 'block'; } catch(_) {}

  // 历史选择事件绑定（所有模式）并打印快照环
  try {
    const ring = (window.__snapshotRing && Array.isArray(window.__snapshotRing.items)) ? window.__snapshotRing.items : [];
    console.log('[SIDEWIN:HISTORY] 快照环数量:', ring.length);
    try { console.log('[SIDEWIN:HISTORY] 快照索引:', ring.map((_,i)=>i)); } catch(_) {}
    const sel = document.getElementById(`history-select-${item.id}`);
    if (sel) {
      sel.onchange = (e) => {
        const val = String(e.target.value);
        if (val === '-1') {
          // “最新”使用用户已选择的记录（若无选择则回退到最近活跃/实时）
          window.__sidewinSelectedGraphs = window.__sidewinSelectedGraphs || {};
          console.log('[SIDEWIN:HISTORY] 选择: 最新(使用已选记录/回退最新)');
        } else {
          const idx = parseInt(val, 10);
          window.__sidewinSelectedGraphs = window.__sidewinSelectedGraphs || {};
          // 选择具体历史记录时，写回对应的快照对象为“已选记录”
          window.__sidewinSelectedGraphs[item.id] = ring[idx] || null;
          console.log('[SIDEWIN:HISTORY] 选择: 记录', idx+1);
        }
        // 仅更新 Inputs/Outputs/Token/Prompt/Debug，不重建整体UI
        try {
          let pickNode = null;
          if (val === '-1') {
            // 最新 → 优先用“已选记录”，否则最近活跃快照，否则退回实时图
            const saved = (window.__sidewinSelectedGraphs && window.__sidewinSelectedGraphs[item.id]) || null;
            const sourceGraph = saved || getLatestActiveGraph() || graph.save();
            const latestNode = (sourceGraph && Array.isArray(sourceGraph.nodes)) ? sourceGraph.nodes.find(n => n.id === item.id) : null;
            const liveNode = graph.save().nodes.find(n => n.id === item.id) || {};
            // 使用快照中的数据，但保留实时 Prompt，避免覆盖侧栏编辑
            pickNode = latestNode ? { ...latestNode, prompt: liveNode.prompt, SystemPrompt: liveNode.SystemPrompt } : (liveNode || null);
          } else {
            // 历史 → 用 ring 的数据 + graph.save() 的 prompt，并把该记录记为“最新”
            const idx = parseInt(val, 10);
            const snap = ring[idx];
            const ringNode = (snap?.nodes || []).find(n => n.id === item.id);
            const liveNode = graph.save().nodes.find(n => n.id === item.id);
            pickNode = {...ringNode, prompt: liveNode?.prompt, SystemPrompt: liveNode?.SystemPrompt};
            // 将选择固化到“最新”
            try { sel.value = '-1'; } catch(_) {}
          }
          const tokenEl   = document.getElementById('token-section');
          const inputsEl  = document.getElementById('inputs-section');
          const promptEl  = document.getElementById('prompt-section');
          const outputsEl = document.getElementById('outputs-section');
          const debugEl   = document.getElementById('debug-section');

          // 安全防空
          if (!pickNode) {
            console.warn('[SIDEWIN:HISTORY] 选中的快照未找到该节点');
            return;
          }

          // 重新构建 token html（若有 tokens）
          let tokenHtml = '';
          try {
            const out0 = (pickNode.Outputs && pickNode.Outputs[0]) || null;
            if (out0 && out0.total_tokens !== undefined && out0.prompt_tokens !== undefined && out0.completion_tokens !== undefined) {
              tokenHtml = `
                <div class="token-info">
                  <div class="token-item"><span>Prompt Tokens:</span> ${out0.prompt_tokens}</div>
                  <div class="token-item"><span>Completion Tokens:</span> ${out0.completion_tokens}</div>
                  <div class="token-item"><span>Total Tokens:</span> ${out0.total_tokens}</div>
                </div>`;
            }
          } catch(_) {}
          if (tokenEl) tokenEl.innerHTML = tokenHtml;

          // 重新构建 inputs html
          let inputsHtml2 = `
            <div class="section-container">
              <h3>Inputs</h3>`;
          try {
            (pickNode.Inputs||[]).forEach((input, idx2) => {
              let val = '';
              if (input.Kind === 'Num') val = input.Num ?? '';
              else if ((input.Kind||'').includes('String')) val = input.Context ?? '';
              else if (input.Kind === 'Boolean') val = input.Boolean ? 'true' : 'false';
              inputsHtml2 += `
                <div class="input-item">
                  <label><strong>${input.name}:</strong></label>
                  <textarea class="side-window-input-textarea" data-index="${idx2}" data-kind="${input.Kind}">${val}</textarea>
                </div>`;
            });
          } catch(_) {}
          inputsHtml2 += '</div>';
          if (inputsEl) inputsEl.innerHTML = inputsHtml2;

          // 重新构建 prompt html（仅对 LLM）
          let promptHtml2 = '';
          try {
            const liveNode2 = getLiveNodeById(item.id);
            if ((liveNode2?.NodeKind || '').includes('LLm')) {
              const systemPromptValue = liveNode2.SystemPrompt ?? '';
              const promptValue = liveNode2.prompt ?? '';
              promptHtml2 = `
                <div class="section-container">
                  <h3>SystemPrompt</h3>
                  <div class="prompt-wrapper"><textarea id="systemPrompt" class="side-window-textarea">${systemPromptValue}</textarea></div>
                </div>
                <div class="section-container">
                  <h3>UserPrompt</h3>
                  <div class="prompt-wrapper"><textarea id="prompt" class="side-window-textarea">${promptValue}</textarea></div>
                </div>`;
            }
          } catch(_) {}
          if (promptEl) {
            promptEl.innerHTML = promptHtml2;
            try {
              const sysTa = document.getElementById('systemPrompt');
              const usrTa = document.getElementById('prompt');
              if (sysTa) attachPromptHandlers(sysTa, 'SystemPrompt');
              if (usrTa) attachPromptHandlers(usrTa, 'prompt');
            } catch(_) {}
          }

          // 重新构建 outputs html
          let outputsHtml2 = `
            <div class="section-container">
              <h3>Outputs</h3>`;
          try {
            (pickNode.Outputs||[]).forEach((output) => {
              let v = '';
              if (output.Kind === 'Num') v = output.Num ?? '';
              else if ((output.Kind||'').includes('String')) v = output.Context ?? '';
              else if (output.Kind === 'Boolean' || output.Kind==='Trigger') v = output.Boolean ? 'true' : 'false';
              outputsHtml2 += `
                <div class="output-item">
                  <label><strong>${output.name}:</strong></label>
                  <textarea class="side-window-textarea" readonly>${v}</textarea>
                </div>`;
            });
          } catch(_) {}
          outputsHtml2 += '</div>';
          if (outputsEl) outputsEl.innerHTML = outputsHtml2;

          // 重新构建 Debug 文本（若报错，把错误拼进 Debug）
          let debugText2 = '';
          try {
            // 根据当前选择推断“对应快照”用于 Debug/Error（避免 active 未定义导致不刷新）
            let chosenGraph = null;
            if (val === '-1') {
              const saved = (window.__sidewinSelectedGraphs && window.__sidewinSelectedGraphs[item.id]) || null;
              chosenGraph = saved || getLatestActiveGraph() || graph.save();
            } else {
              const idx2 = parseInt(val, 10);
              chosenGraph = ring[idx2] || null;
            }
            const chosenNode = (chosenGraph && Array.isArray(chosenGraph.nodes)) ? chosenGraph.nodes.find(n => n && n.id === item.id) : null;
            const rawDbg = (chosenNode && typeof chosenNode.debug === 'string') ? chosenNode.debug : (pickNode.debug || '');
            debugText2 = (rawDbg || '').replace(/\\n/g, '\n');

            // 🔧 兜底：历史/快照数据可能没有同步到 debug（例如 ring 未写入/仍是旧快照），
            // 回退到实时图节点 debug，避免 onchange 把 Debug 覆盖成空。
            try {
              const liveN = getLiveNodeById(item.id);
              const liveDbg = (typeof liveN?.debug === 'string') ? liveN.debug : '';
              if ((!debugText2 || !String(debugText2).trim().length) && liveDbg && String(liveDbg).trim().length) {
                debugText2 = String(liveDbg).replace(/\\n/g, '\n');
                console.warn('[SIDEWIN:HISTORY:DEBUG] fallback to liveNode.debug (graph.save)');
              }
              const snapLen = (chosenNode && typeof chosenNode.debug === 'string') ? chosenNode.debug.length : 0;
              const pickLen = (typeof pickNode?.debug === 'string') ? pickNode.debug.length : 0;
              const liveLen = (typeof liveDbg === 'string') ? liveDbg.length : 0;
              const finalLen = (typeof debugText2 === 'string') ? debugText2.length : 0;
              console.warn('[SIDEWIN:HISTORY:DEBUGPICK]', { val, snapLen, pickLen, liveLen, finalLen });
            } catch(_) {}

            const lastErr2 = window.__nodeLastBackendError && window.__nodeLastBackendError[item.id];
            const ctx2 = pickNode.ErrorContext || (chosenNode && chosenNode.ErrorContext) || '';
            const det2 = (lastErr2 && lastErr2.detail) || '';
            if ((pickNode.IsError === true) || ctx2 || det2) {
              const parts2 = [];
              if (ctx2) parts2.push(String(ctx2));
              if (det2 && det2 !== ctx2) parts2.push(String(det2));
              const merged2 = parts2.join('\n\n---\n\n');
              debugText2 = merged2 || debugText2;
            }
          } catch(_) {}

          if (debugEl) debugEl.innerHTML = `
            <div class="section-container">
              <h3>Debug</h3>
              <div class="debug-wrapper">
                <textarea class="side-window-textarea" style="white-space:pre-wrap;" readonly>${escapeForTextarea(debugText2)}</textarea>
              </div>
            </div>`;

          // 高度自适应
          document.querySelectorAll('#content-area textarea').forEach(resizeTextarea);

          console.log('[SIDEWIN:HISTORY] 已更新 Inputs/Outputs/Token/Prompt/Debug');
        } catch(err) {
          console.error('[SIDEWIN:HISTORY] 更新数据块失败:', err);
        }
      };
    }
  } catch(_) {}

  // 调整所有 textarea 的高度
  document.querySelectorAll('#content-area textarea').forEach(resizeTextarea);

  // 设置按钮和状态显示
  const runButton = document.getElementById('run-button');
  runButton.style.display = isCheckMode ? 'none' : 'block';
  const statusArea = document.querySelector('.status-area');
  if (statusArea) statusArea.style.display = 'none';

  const resultIndicator = document.getElementById('result-indicator');
  const resultMessage = document.getElementById('result-message');

  if (isCheckMode) {
    let Tempnodes =graph.save().nodes;
    let tempNodeForCheck = Tempnodes.find(n => n.id === item.id);
    
    // 🔍 详细调试信息 - 检查数据传递
    console.warn('[SIDEWIN:DEBUG] ===== 检查模式数据调试 =====');
    console.warn('[SIDEWIN:DEBUG] item.id:', item.id);
    console.warn('[SIDEWIN:DEBUG] Tempnodes 总数:', Tempnodes ? Tempnodes.length : 'undefined');
    console.warn('[SIDEWIN:DEBUG] tempNodeForCheck 是否存在:', !!tempNodeForCheck);
    console.warn('[SIDEWIN:DEBUG] 原始 tempNode 状态:');
    console.warn('  - isFinish:', tempNode?.isFinish);
    console.warn('  - IsRunning:', tempNode?.IsRunning);
    console.warn('  - IsError:', tempNode?.IsError);
    console.warn('  - ErrorContext:', tempNode?.ErrorContext);
    
    if (tempNodeForCheck) {
      console.warn('[SIDEWIN:DEBUG] tempNodeForCheck 关键状态:');
      console.warn('  - isFinish:', tempNodeForCheck.isFinish);
      console.warn('  - IsRunning:', tempNodeForCheck.IsRunning);
      console.warn('  - IsError:', tempNodeForCheck.IsError);
      console.warn('  - ErrorContext:', tempNodeForCheck.ErrorContext);
      console.warn('  - 节点类型:', tempNodeForCheck.NodeKind || tempNodeForCheck.Kind);
      console.warn('  - 节点标签:', tempNodeForCheck.label || tempNodeForCheck.name);
    } else {
      console.error('[SIDEWIN:ERROR] 未找到 tempNodeForCheck，item.id:', item.id);
      console.warn('[SIDEWIN:DEBUG] 可用的节点ID列表:', Tempnodes.map(n => n.id));
    }
    
    const statusArea = document.querySelector('.status-area');
    const loadingIndicator = document.getElementById('loading-indicator');
    const resultIndicator = document.getElementById('result-indicator');
    if (statusArea) statusArea.style.display = 'flex';
    
    console.warn('[SIDEWIN:DEBUG] DOM 元素状态:');
    console.warn('  - loadingIndicator:', !!loadingIndicator);
    console.warn('  - resultIndicator:', !!resultIndicator);
    console.warn('  - resultMessage:', !!resultMessage);
    
    // 🔍 修改后的逻辑：始终显示状态信息，但数据始终可见
    console.warn('[SIDEWIN:DEBUG] ===== 状态显示逻辑 =====');
    
    if (tempNodeForCheck) {
        // 根据节点状态显示不同的状态信息
        if (tempNodeForCheck.isFinish == false) {
            // 未完成状态
            console.warn('[SIDEWIN:DEBUG] 节点未完成');
            
            if (tempNodeForCheck.IsRunning == true) {
                // 正在运行
                console.warn('[SIDEWIN:DEBUG] 节点正在运行中');
                if (tempNodeForCheck.IsError == false) {
                    console.warn('[SIDEWIN:DEBUG] 运行中无错误，显示加载指示器');
            loadingIndicator.style.display = 'block';
            resultIndicator.style.display = 'none';
            resultMessage.textContent = '';
                } else {
                    console.warn('[SIDEWIN:DEBUG] 运行中有错误，显示错误信息');
                    loadingIndicator.style.display = 'none';
                    resultMessage.textContent = `运行错误: ${tempNodeForCheck.ErrorContext || '未知错误'}`;
            resultMessage.style.color = 'red';
            resultIndicator.style.display = 'block';
          }
            } else {
                // 待运行
                console.warn('[SIDEWIN:DEBUG] 节点待运行');
                loadingIndicator.style.display = 'none';
          resultMessage.textContent = '待运行';
          resultMessage.style.color = 'orange';
          resultIndicator.style.display = 'block';
        }
        } else {
            // 已完成状态
            console.warn('[SIDEWIN:DEBUG] 节点已完成');
            loadingIndicator.style.display = 'none';
        
            if (tempNodeForCheck.IsError) {
                console.warn('[SIDEWIN:DEBUG] 完成但有错误');
                resultMessage.textContent = `完成但有错误: ${tempNodeForCheck.ErrorContext || '未知错误'}`;
                resultMessage.style.color = 'red';
    } else {
                console.warn('[SIDEWIN:DEBUG] 正常完成');
                resultMessage.textContent = '已完成';
                resultMessage.style.color = 'green';
            }
        resultIndicator.style.display = 'block';
        }
    } else {
        // 节点未找到
        console.warn('[SIDEWIN:DEBUG] 节点未找到，显示默认状态');
        loadingIndicator.style.display = 'none';
        resultMessage.textContent = '节点数据未找到';
        resultMessage.style.color = 'gray';
        resultIndicator.style.display = 'block';
    }
    
    console.warn('[SIDEWIN:DEBUG] ===== 数据始终可见，状态仅作提示 =====');
} else {
    resultIndicator.style.display = 'none';
    setupRunButton(liveNode || node);
}


  // 设置关闭按钮
  document.getElementById('close-button').onclick = () => {
      // Apple Style Animation: Remove visible class first
      sideWindow.classList.remove('visible');
      // Wait for transition (0.5s) then hide
      setTimeout(() => {
        sideWindow.style.display = 'none';
      }, 500);
      
      // 🔥 清理当前打开的节点信息
      window.__currentSideWindowNode = null;
      window.__currentSideWindowIsCheckMode = false;
      
      if (!isCheckMode && runButton._clickHandler) {
          runButton.removeEventListener('click', runButton._clickHandler);
      }
      const statusArea = document.querySelector('.status-area');
      const loadingIndicator = document.getElementById('loading-indicator');
      const resultIndicator = document.getElementById('result-indicator');
      if (statusArea) statusArea.style.display = 'none';
      if (loadingIndicator) loadingIndicator.style.display = 'none';
      if (resultIndicator) resultIndicator.style.display = 'none';
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
          // 单节点运行前重置一次性打印标记，保证本次也会生成汇总/快照
          try { window.__RUN_SUMMARY_PRINTED__ = false; window.__RUN_PROGRESS_PRINTED__ = false; } catch(_) {}
          // 显示加载指示器
          const statusArea = document.querySelector('.status-area');
          const loadingIndicator = document.getElementById('loading-indicator');
          const resultIndicator = document.getElementById('result-indicator');
          const resultMessage = document.getElementById('result-message');
          if (statusArea) statusArea.style.display = 'flex';
          loadingIndicator.style.display = 'block';
          resultIndicator.style.display = 'none';

          // 0) 工具
          const getLiveNodeById = (id) => {
            const g = graph.save();
            return (Array.isArray(g?.nodes) ? g.nodes : []).find(n => n.id === id) || null;
          };

          // 1) 先把侧窗 DOM 写回 graph（以 graph 为准）
          let live1 = getLiveNodeById(node.id);
          if (!live1) throw new Error('[RUN] 找不到实时节点');
          const sysTa = document.getElementById('systemPrompt');
          const usrTa = document.getElementById('prompt');
          if ((live1.NodeKind||'').includes('LLm')) {
            // 运行中不把侧栏改动写回图数据，仅用于本次发送的临时节点
          }
          document.querySelectorAll('.side-window-input-textarea').forEach(t => {
            const idx  = parseInt(t.dataset.index, 10);
            const kind = t.dataset.kind || '';
            if (!live1.Inputs || !live1.Inputs[idx]) return;
            if (kind === 'Num') live1.Inputs[idx].Num = (t.value.trim()==='') ? null : Number(t.value);
            else if (kind.includes('String')) live1.Inputs[idx].Context = t.value;
            else if (kind === 'Boolean') live1.Inputs[idx].Boolean = String(t.value).toLowerCase() === 'true';
          });

          // 2) 立刻从 graph 再取一次最新节点（确保刚写回的数据生效）
          const g2 = graph.save();
          const sendNode = (Array.isArray(g2?.nodes) ? g2.nodes : []).find(n => n.id === node.id);
          if (!sendNode) throw new Error('[RUN] 刷新后仍找不到节点');

          // 3) 接下来所有 payload 都用 sendNode（你原来的组装 + fetch 保持不变）
          // 收集输入数据并更新 sendNode.Inputs
          document.querySelectorAll('.side-window-input-textarea').forEach(textarea => {
              const index = parseInt(textarea.dataset.index, 10);
              const value = textarea.value.trim();
              const input = sendNode.Inputs[index];

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
          const inputs = sendNode.Inputs.reduce((acc, input, index) => {
              if (input.Kind === 'Num') {
                  acc[index] = Number.isFinite(input.Num) ? input.Num : 0;        // 默认 0
              } else if (input.Kind?.includes('String')) {
                  acc[index] = (input.Context ?? '').toString();                  // 默认空串
              } else if (input.Kind === 'Boolean') {
                  acc[index] = (input.Boolean === true);                          // 默认 false
              } else {
                  acc[index] = null;                                              // 兜底，避免被丢
              }
              return acc;
          }, {});
          // 在不修改图数据的前提下，将侧栏的 SystemPrompt/prompt 应用到本次发送节点
          if ((sendNode.NodeKind||'').includes('LLm')) {
            const sysTaRef = document.getElementById('systemPrompt');
            const usrTaRef = document.getElementById('prompt');
            if (sysTaRef && typeof sysTaRef.value === 'string') {
              sendNode.SystemPrompt = sysTaRef.value;
            }
            if (usrTaRef && typeof usrTaRef.value === 'string') {
              sendNode.prompt = usrTaRef.value;
            }
          }
          // 如果是 LLM 节点，处理 prompt
          if (sendNode.NodeKind.includes('LLm')) {
              // 保留原始占位符，不替换；导出使用图中的 sendNode.prompt
              const [systemPrompt, exportPrompt,ExprotAfterPrompt] = processLLmPrompt(sendNode);
              sendNode.SystemPrompt = systemPrompt;
              sendNode.ExportPrompt = sendNode.prompt;
              sendNode.ExprotAfterPrompt = ExprotAfterPrompt;
          }
          console.warn('测试sendNode',sendNode,inputs);
          // 发送请求到后端
          const response = await fetch('/run-node-single', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                  name: sendNode.name,
                  node: sendNode,
                  prompt: sendNode.ExportPrompt,
                  inputs: inputs, // 确保这里的 inputs 已经定义
                  outputs: sendNode.Outputs
              })
          });

          // 解析响应数据（兼容非 JSON 错误体，尽量展示“具体错误内容”）
          const rawText = await response.text();
          let data = null;
          try { data = rawText ? JSON.parse(rawText) : null; } catch (_) { data = null; }
          if (!response.ok) {
              const traceLike =
                (data && (data.trace || data.detail || data.message || data.error)) ||
                (typeof rawText === 'string' ? rawText : '');
              const summary = `后端服务响应错误: HTTP ${response.status} ${response.statusText || ''}`.trim();
              const detail = (data ? JSON.stringify(data, null, 2) : String(traceLike || '未知错误')).trim();
              const short = String(traceLike || '').replace(/\s+/g, ' ').slice(0, 200);

              resultMessage.textContent = summary + (short ? ` - ${short}` : '');
              resultMessage.style.color = 'red';
              resultIndicator.style.display = 'block';

              // 将错误信息写回到节点，确保侧窗可查看完整错误
              try {
                window.__nodeLastBackendError = window.__nodeLastBackendError || {};
                window.__nodeLastBackendError[sendNode.id] = { ts: Date.now(), summary, detail };
              } catch (_) {}
              try {
                const nodeItem = graph.findById(sendNode.id);
                if (nodeItem) {
                  graph.updateItem(nodeItem, {
                    IsError: true,
                    IsRunning: false,
                    isFinish: true,
                    ErrorContext: summary,
                    debug: detail
                  });
                }
              } catch (_) {}
              try {
                const tn = TempMessageNode?.nodes?.find(n => n && n.id === sendNode.id);
                if (tn) {
                  tn.IsError = true;
                  tn.IsRunning = false;
                  tn.isFinish = true;
                  tn.ErrorContext = summary;
                  tn.debug = detail;
                }
              } catch (_) {}

              // 若侧窗已打开，立即刷新 Debug textarea（避免残留上一次内容）
              try {
                const dbgTa =
                  document.querySelector('#debug-section .debug-wrapper textarea') ||
                  document.querySelector('#debug-section textarea');
                if (dbgTa) dbgTa.value = detail || summary;
              } catch (_) {}

              throw new Error(summary);
          }
          if (!data) {
              throw new Error('后端返回的响应不是有效 JSON（请查看侧窗 Error/Debug）');
          }

          // 成功：清理上一次错误痕迹（否则会“保留 error/debug 之前的运行结果”）
          // 同时：将 debug 同步为“本次结果”（无 debug 则清空，避免旧错误残留）
          try {
            if (window.__nodeLastBackendError && window.__nodeLastBackendError[sendNode.id]) {
              delete window.__nodeLastBackendError[sendNode.id];
            }
          } catch (_) {}
          // 后端 /run-node-single 返回字段是 debug_text；旧逻辑读 data.debug 会导致 debug 被清空
          let dbgStr = '';
          try {
            const d = (data && data.debug !== undefined) ? data.debug : (data ? data.debug_text : undefined);
            dbgStr = (d === undefined || d === null || d === '') ? '' : ((typeof d === 'string') ? d : JSON.stringify(d, null, 2));
          } catch (_) { dbgStr = ''; }
          try {
            const nodeItem = graph.findById(sendNode.id);
            if (nodeItem) {
              graph.updateItem(nodeItem, { IsError: false, ErrorContext: '', debug: dbgStr });
            }
          } catch (_) {}
          try {
            const tn = TempMessageNode?.nodes?.find(n => n && n.id === sendNode.id);
            if (tn) { tn.IsError = false; tn.ErrorContext = ''; tn.debug = dbgStr; }
          } catch (_) {}

          // 更新输出显示，包括 Token 信息
          // 兼容 debug/debug_text 两种字段名
          updateOutputs(data.output, ((data && data.debug !== undefined) ? data.debug : (data ? data.debug_text : '')) ?? '', sendNode.id);

          // 运行完成后：同步到 ring
          try {
            // 1) 拿到“真正的环引用”
            const ringObj = (window.__snapshotRing = window.__snapshotRing || { items: [] });
            const ring = ringObj.items;

            // 2) 用深拷贝把当前图推到最前面（避免后续 graph 变化污染历史）
            const nowGraph = graph.save();
            const snap = (typeof structuredClone === 'function')
              ? structuredClone(nowGraph)
              : JSON.parse(JSON.stringify(nowGraph));

            // 将本次单节点运行的真实输出合并进快照中的对应节点（不会改动真实图）
            try {
              const nodeSnap = (Array.isArray(snap?.nodes) ? snap.nodes : []).find(n => n && n.id === sendNode.id);
              if (nodeSnap && Array.isArray(nodeSnap.Outputs) && Array.isArray(data.output)) {
                data.output.forEach((o, i) => {
                  if (!o || !nodeSnap.Outputs[i]) return;
                  if ('Context' in nodeSnap.Outputs[i]) nodeSnap.Outputs[i].Context = o.Context;
                  if ('Num' in nodeSnap.Outputs[i]) nodeSnap.Outputs[i].Num = o.Num;
                  if ('Boolean' in nodeSnap.Outputs[i]) nodeSnap.Outputs[i].Boolean = (o.Boolean === true);
                  // token 字段
                  ['prompt_tokens','completion_tokens','total_tokens'].forEach(k=>{
                    if (o[k] !== undefined) nodeSnap.Outputs[i][k] = o[k];
                  });
                });
                // 标记该节点为完成，便于 finalish 判定
                nodeSnap.isFinish = true;
                nodeSnap.IsError = false;
                nodeSnap.IsRunning = false;
                const dd = (data && data.debug !== undefined) ? data.debug : (data ? data.debug_text : undefined);
                if (typeof dd === 'object' || typeof dd === 'string') {
                  try { nodeSnap.debug = (typeof dd === 'string') ? dd : JSON.stringify(dd); } catch(_) {}
                }
              }
            } catch(_) {}

            // 判定是否应写入ring：finalish 或 本次有"有效输出"
            const finalsNodes = (snap && Array.isArray(snap.nodes)) ? snap.nodes.filter(isNodeFinalish) : [];
            const finals = finalsNodes.map(n=>n && (n.label||n.id));
            const hasUsefulOutput = Array.isArray(data.output) && data.output.some(o=> o && ((o.Context && String(o.Context).length) || (o.Num!==null && o.Num!==undefined) || o.Boolean === true));
            
            if (finalsNodes.length > 0 || hasUsefulOutput) {
              // 构造快照并获取指纹
              const payload = snap;
              const fp = getRingFingerprint({ graph_data: snap }); // 单节点运行可能没有后端指纹
              payload.__fingerprint = fp || null;
              payload.__ts = Date.now();

              // 没有指纹也先写入“临时指纹”的记录，并标记为 __isProvisional
              let useFp = fp;
              if (!useFp) {
                const dg = computeGraphDigest(snap); // 轻量摘要作为临时指纹
                useFp = window.__RING_PROV_FP__ = `prov:${dg || Date.now()}`;
                payload.__isProvisional = true;
              }

              upsertRingByFingerprint(window.__snapshotRing, payload, useFp, window.__snapshotRing?.max || 20);
              console.warn('   - 新增/覆盖节点:', finals);
              console.warn('   - 环大小:', window.__snapshotRing.items.length);
            } else {
              try { if (window.LOG && window.LOG.ring) console.warn('[WFDBG:RING] RUN-BTN skip (no new finalish & no useful output)'); } catch(_) {}
            }
            console.log('🌀 [RING:SYNC] 新快照已插入为记录1，当前总数=', ring.length);

            // 3) 重建对应节点的下拉选项，并强制切到“最新”
            const sel = document.getElementById(`history-select-${sendNode.id}`);
            if (sel) {
              const opts = ['<option value="-1" selected>最新(graph.save)</option>']
                .concat(ring.map((_, i) => `<option value="${i}">记录${i + 1}</option>`));
              sel.innerHTML = opts.join('');

              sel.value = '-1';
              sel.dispatchEvent(new Event('change'));
            }

            // 4) 取消任何“历史选中”记忆，保持“最新”
            window.__sidewinSelectedGraphs = window.__sidewinSelectedGraphs || {};
            window.__sidewinSelectedGraphs[sendNode.id] = null;

          } catch (e) {
            console.warn('🌀 [RING:SYNC] 写入历史环失败:', e);
          }

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

  // 不进行占位符替换，直接返回原始 Prompt
  return [ node.SystemPrompt, node.prompt, ExprotAfterPrompt ];
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
  try { console.warn('[WFDBG:UI:updateOutputs] id=', Id, 'outs=', Array.isArray(outputs)?outputs.map((o,i)=>({i,Kind:o?.Kind,Num:o?.Num,Context:typeof o?.Context==='string'?o.Context.slice(0,40):o?.Context,Boolean:o?.Boolean})):'?'); } catch(_) {}
  // 前端仅更新面板展示，避免直接写入 graph.save() 造成与轮询回写竞态
  outputs.forEach((output, index) => {
      if (index < outputElements.length) {
          const element = outputElements[index];
          let value = '';
          if (output.Kind === 'Num') {
              value = output.Num ?? '';
          } else if (output.Kind?.includes('String')) {
              value = output.Context ?? '';
          } else if (output.Kind === 'Boolean') {
              value = output.Boolean ? 'true' : 'false';
          }
          element.value = value;
      }
  });
  // ⚠️ SideWindow 里可能有多个 wrapper（例如 Error/Debug），这里必须精确指向 Debug 区块
  const debugelement =
    document.querySelector('#debug-section .debug-wrapper textarea') ||
    document.querySelector('#debug-section textarea');
  if (debugelement) {
    // debug 可能为 ''/null/undefined：此时应清空，而不是保留上一次内容
    if (debug === undefined || debug === null || debug === '') {
      debugelement.value = '';
    } else {
      debugelement.value = (typeof debug === 'string') ? debug : JSON.stringify(debug, null, 2);
    }
  }
  // 不再触碰全图数据，等待轮询把后端 graph_data 写回
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
// 添加工作流相关变量
// currentWorkflowId：由本页面“发起并拥有”的工作流（负责 stop/cleanup）
// monitoredWorkflowId：当前正在监控的工作流（可来自本页启动或 /workflow/status/current）
let currentWorkflowId = null;
let monitoredWorkflowId = null;
let workflowStatusInterval = null;
let workflowStatusIntervalMs = 0;
let backendQueueLengths = null;
// 当前观察的工作流ID（用于工作流选择器）
let currentObservedWorkflowId = null;
// 前端模式：'edit' | 'monitor'
// - edit：本页面启动并“拥有”工作流，关闭页面时会尝试停止
// - monitor：仅监控后端已有工作流（例如从 Control Room 打开），不擅自停止
let frontendMode = 'edit';
let prevFrontendMode = 'edit'; // 跟踪之前的模式，用于检测模式切换

// 统一设置工作流状态轮询间隔
function setWorkflowPollingInterval(ms) {
  console.warn('[WFDBG:POLL:SET]', { ms, existing: !!workflowStatusInterval, currentMs: workflowStatusIntervalMs });
  // ms <= 0 表示关闭轮询
  if (!ms || ms <= 0) {
    if (workflowStatusInterval) {
      clearInterval(workflowStatusInterval);
      workflowStatusInterval = null;
    }
    workflowStatusIntervalMs = 0;
    return;
  }

  // 与当前间隔一致则不重复创建
  if (workflowStatusInterval && workflowStatusIntervalMs === ms) {
    console.warn('[WFDBG:POLL:SET] skip (same interval)');
    return;
  }

  if (workflowStatusInterval) {
    clearInterval(workflowStatusInterval);
  }
  workflowStatusIntervalMs = ms;
  workflowStatusInterval = setInterval(pollWorkflowStatus, ms);
  console.warn('[WFDBG:POLL:SET] started interval', { ms, id: workflowStatusInterval });
}

// 统一清理所有动画和轮询的函数
function stopAllAnimationsAndPolling() {
  console.warn('[WFDBG:STOP] 清理所有动画和轮询');
  
  // 清理工作流状态轮询
  setWorkflowPollingInterval(0);
  console.log('[DEBUG] 清理了 workflowStatusInterval');
  
  // 清理快速动画间隔
  if (window.fastAnimationInterval) {
    clearInterval(window.fastAnimationInterval);
    window.fastAnimationInterval = null;
    console.log('[DEBUG] 清理了 fastAnimationInterval');
  }
  
  // 清理标题动画
  if (window.titleInterval) {
    clearInterval(window.titleInterval);
    window.titleInterval = null;
    console.log('[DEBUG] 清理了 titleInterval');
  }
  
  // 重置标题为基础标题
  const baseTitle = FileName || 'LinkO';
  document.title = baseTitle;
  
  // 重置相关状态
  backendQueueLengths = null;
  window.lastQueueInfo = null;
  // 安全兜底：停止时一律退出预热
  try { window.inPreheat = false; } catch(_) {}
  // 停止监控当前工作流（不改变 currentWorkflowId 所代表的“所有权”）
  monitoredWorkflowId = null;
}

// 页面卸载时清理所有资源
window.addEventListener('beforeunload', () => {
  console.log('[DEBUG] 页面卸载，清理所有资源');
  stopAllAnimationsAndPolling();

  // ★ 只有在 edit 模式下主动启动的工作流，页面关闭时才停止
  // 监控模式下（从 Control Room 打开），关闭页面不应该影响后端工作流
  if (currentWorkflowId && frontendMode === 'edit') {
    console.log(`[DEBUG] Edit 模式页面关闭，停止工作流 ${currentWorkflowId}`);
    //fetch(`/workflow/stop/${currentWorkflowId}`, {
      //method: 'POST',
      //keepalive: true
    //});
  } else if (currentWorkflowId && frontendMode === 'monitor') {
    console.log(`[DEBUG] Monitor 模式页面关闭，保留后端工作流 ${currentWorkflowId}`);
  }
});

// 简单冗余关闭钩子：部分浏览器更可靠触发 pagehide
window.addEventListener('pagehide', () => {
  if (!currentWorkflowId || frontendMode !== 'edit') return;
  try {
    console.log(`[DEBUG:pagehide] Edit 模式停止工作流 ${currentWorkflowId}`);
    if (navigator.sendBeacon) {
      const blob = new Blob([], { type: 'application/json' });
      //navigator.sendBeacon(`/workflow/stop/${currentWorkflowId}`, blob);
    } else {
      //fetch(`/workflow/stop/${currentWorkflowId}`, { method: 'POST', keepalive: true });
    }
  } catch (_) {}
});

// 维护最近活跃快照的环（最多保存20份），用于“接收中/完成后”侧栏查看
// 快照环：统一初始化与访问（最多 20 条，最新在最前）
function ensureSnapshotRing(max = 20) {
  if (!window.__snapshotRing || !Array.isArray(window.__snapshotRing.items)) {
    window.__snapshotRing = { items: [], max };
  }
  if (typeof window.__snapshotRing.max !== 'number') {
    window.__snapshotRing.max = max;
  }
  return window.__snapshotRing.items;
}

// 全局日志屏蔽开关（单一总开关，默认屏蔽所有非 error 日志）
// 用法:
//   setLogSilence(false)  // 开启日志
//   setLogSilence(true)   // 关闭日志（默认）
//屏蔽打印
(function(){
  try {
    if (typeof window === 'undefined') return;
    if (!window.__ORIG_CONSOLE__) {
      window.__ORIG_CONSOLE__ = {
        log: console.log.bind(console),
        info: console.info.bind(console),
        debug: console.debug.bind(console),
        warn: console.warn.bind(console)
      };
    }
    window.LOG_SILENT = true;  // 默认静默
    window.LOG_ALLOW_PREFIXES = window.LOG_ALLOW_PREFIXES || [];
    function apply() {
      const c = window.__ORIG_CONSOLE__;
      const wrap = (orig) => function(){
        try {
          if (!window.LOG_SILENT) return orig.apply(console, arguments);
          const first = arguments[0];
          if (typeof first === 'string' && Array.isArray(window.LOG_ALLOW_PREFIXES) && window.LOG_ALLOW_PREFIXES.length) {
            for (let i=0;i<window.LOG_ALLOW_PREFIXES.length;i++) {
              const p = window.LOG_ALLOW_PREFIXES[i];
              if (first.startsWith(p)) return orig.apply(console, arguments);
            }
          }
        } catch(_) {}
        return undefined;
      };
      console.log  = wrap(c.log);
      console.info = wrap(c.info);
      console.debug= wrap(c.debug);
      console.warn = wrap(c.warn);
    }
    window.setLogSilence = function(v, opts){
      window.LOG_SILENT = !!v;
      if (opts && Array.isArray(opts.allowPrefixes)) window.LOG_ALLOW_PREFIXES = opts.allowPrefixes.slice();
      apply();
      return window.LOG_SILENT;
    };
    window.enableRingLogsOnly = function(){
      return window.setLogSilence(true, { allowPrefixes: ['[RING', '🌀 [RING', '[SNAPSHOT]'] });
    };
    apply();
  } catch(_) {}
})();

// 生成用于去重的轻量摘要：仅包含节点状态与Outputs的核心值
function computeGraphDigest(g) {
  try {
    const nodes = (g && Array.isArray(g.nodes)) ? g.nodes : [];
    const brief = nodes.map(n => {
      if (!n) return null;
      const st = n.IsError ? 'E' : (n.isFinish ? 'F' : (n.IsRunning ? 'R' : 'I'));
      const outs = Array.isArray(n.Outputs) ? n.Outputs.map(o => ({
        C: (o && typeof o.Context === 'string') ? o.Context : (o ? o.Context : undefined),
        N: o ? o.Num : undefined,
        B: o ? o.Boolean : undefined
      })) : [];
      return { id: n.id, st, outsLen: outs.length, outs };
    });
    return JSON.stringify(brief);
  } catch (_) {
    return '';
  }
}

// 判断节点是否有“有效数据”（完成/报错），用于入环
function nodeIsEffective(n) {
  return !!(n && (n.isFinish === true || n.IsError === true));
}

// === [顶部/工具区] 新增: 统一指纹获取 + 覆盖工具 ===
// ★ 最小工具函数：拿当前快照的指纹（后端字段名以你的为准）
function getRingFingerprint(data) {
  const fpFromBackend = data?.ringFingerprint || data?.graph_data?.fingerprint || null;
  if (fpFromBackend) return fpFromBackend;

  // 兜底：本地基于轻量摘要做一个廉价 hash，避免"第一条没指纹就被跳过"
  try {
    const s = computeGraphDigest(data?.graph_data); // 你已有的轻量摘要函数
    if (!s) return null;
    let h = 0;
    for (let i = 0; i < s.length; i++) { h = ((h << 5) - h) + s.charCodeAt(i); h |= 0; }
    return 'h' + (h >>> 0).toString(16);
  } catch(_) { return null; }
}

// ★ 覆盖或插入：保证"同指纹只保留最新"
function upsertRingByFingerprint(ring, payload, fp, RING_MAX = 100) {
  if (!Array.isArray(ring.items)) ring.items = [];
  if (fp) {
    payload.__fingerprint = fp;          // 关键：让记录本身带上 fp
  }

  // 先在环里找相同指纹
  const i = fp ? ring.items.findIndex(it => it?.__fingerprint === fp) : -1;

  if (i === 0) {
    // 环首就是同指纹 → 直接覆盖（最省变动）
    ring.items[0] = payload;
    console.log('🌀 [RING:OVERWRITE] 覆盖环首 (相同指纹)');
  } else if (i > 0) {
    // 环内存在同指纹，移除旧的，再把新的放到首位
    ring.items.splice(i, 1);
    ring.items.unshift(payload);
    console.log('🌀 [RING:OVERWRITE] 覆盖环内旧记录 (相同指纹) → 移到环首');
        } else {
    // 没找到同指纹 → 正常追加到首位
    ring.items.unshift(payload);
    // 控制上限
    if (ring.items.length > RING_MAX) ring.items.pop();
    console.log('✅ [RING:PUSH] 新增记录到环 (新指纹)');
  }
}

// === [SideWindow 渲染前的过滤] 新增/替换 ===
function isNodeFinalish(node) {
  // 你的状态字段名按实情改：常见的是 node.isFinish / node.IsError
  return node?.isFinish === true || node?.isError === true || node?.IsError === true;
}

function pickRingsForNode(ringItems, activeNodeId) {
  if (!activeNodeId) return ringItems || [];

  return (ringItems || []).filter(item => {
    // ① 取出该环的节点列表（按你 payload 的结构来——下面做了宽松兼容）
    const nodes = item?.nodes
      || item?.graph?.nodes
      || item?.graph_data?.nodes
      || [];

    // ② 找到目标节点
    const hit = nodes.find(n =>
      n?.id === activeNodeId
      || n?.name === activeNodeId
      || n?.nodeId === activeNodeId
    );

    // ③ 命中且处于 finalish，才保留
    return !!(hit && isNodeFinalish(hit));
  });
}

// 将 TempMessageNode 中的"有效节点"入环（最新在最前，超过上限弹出最后一个）
function snapshotTempMessageNodes(targetNodeId = null) {
  if (!TempMessageNode || !Array.isArray(TempMessageNode.nodes)) return;
  const nodesToSave = targetNodeId
    ? TempMessageNode.nodes.filter(n => n && n.id === targetNodeId && nodeIsEffective(n))
    : TempMessageNode.nodes.filter(n => nodeIsEffective(n));
  if (!nodesToSave.length) {
    try {
      const origWarn = window.__ORIG_CONSOLE__?.warn || console.warn;
      origWarn('🔍 [RING:SNAPSHOT] 无有效节点可入环');
    } catch(_) {}
    return;
  }

  const payload = {
    type: 'TempMessageNode',
    ts: Date.now(),
    nodes: (typeof structuredClone === 'function')
      ? structuredClone(nodesToSave)
      : JSON.parse(JSON.stringify(nodesToSave))
  };
  // 详细打印入环内容 - 绕过静默机制
  try {
    const origWarn = window.__ORIG_CONSOLE__?.warn || console.warn;
    origWarn('🔍 [RING:SNAPSHOT] 入环详情:');
    origWarn('  - 目标节点ID:', targetNodeId);
    origWarn('  - 入环节点数:', nodesToSave.length);
    origWarn('  - 节点详情:', nodesToSave.map(n => ({
      id: n.id,
      label: n.label,
      isFinish: n.isFinish,
      IsError: n.IsError,
      hasOutputs: n.Outputs && n.Outputs.length > 0
    })));
  } catch(_) {}
  
  try {
    if (window.LOG && window.LOG.ring) {
      const names = payload.nodes.map(n => n && (n.label || n.id));
      const first = names[0];
      console.warn('🌀 [RING:SNAPSHOT] 入环 TempMessageNode 节点数=', names.length, ' 首个=', first, ' 全部=', names);
    }
  } catch(_) {}
  // 临时快照不再写入主环，避免第三来源重复
  // 只打印调试信息，不入环
  try {
    const origWarn = window.__ORIG_CONSOLE__?.warn || console.warn;
    origWarn('🔍 [TEMP:SNAPSHOT] 临时快照不入环（避免重复）');
    origWarn('  - 目标节点ID:', targetNodeId);
    origWarn('  - 入环节点数:', nodesToSave.length);
    origWarn('  - 节点详情:', nodesToSave.map(n => ({
      id: n.id,
      label: n.label,
      isFinish: n.isFinish,
      IsError: n.IsError
    })));
  } catch(_) {}
}

// 兼容旧代码：提供 latest() 便于取最近一条
if (!window.__snapshotRing) { ensureSnapshotRing(20); }
if (typeof window.__snapshotRing.latest !== 'function') {
  window.__snapshotRing.latest = function latest() {
    const items = ensureSnapshotRing();
    return items.length ? items[0] : null; // 最新在最前
  };
}

// 兼容旧代码：提供 push(graph) 并写入为“最新在最前”，按 max 截断
if (typeof window.__snapshotRing.push !== 'function') {
  window.__snapshotRing.push = function push(graph) {
    const items = ensureSnapshotRing(20);
    const data = (typeof structuredClone === 'function')
      ? structuredClone(graph)
      : JSON.parse(JSON.stringify(graph));
    items.unshift(data);
    while (items.length > window.__snapshotRing.max) items.pop();
    return items.length;
  };
}

function getLatestActiveGraph() {
  const ringLatest = (window.__snapshotRing && typeof window.__snapshotRing.latest === 'function')
    ? window.__snapshotRing.latest()
    : null;
  // 仅当 latest 为“完整图结构”（含 nodes 与 edges）时才采用；否则回退到 lastActiveSnapshot
  const hasFullGraphShape = ringLatest && Array.isArray(ringLatest.nodes) && Array.isArray(ringLatest.edges);
  return (hasFullGraphShape ? ringLatest : null) || (window.lastActiveSnapshot || null);
}

// 判定图是否包含“有意义”的运行数据（避免用空结构覆盖本地记录）
function isNodeFinalish(n){
  return !!(n && (n.isFinish === true || n.IsError === true));
}

// 仅当图中存在 finalish 节点时，才认为“有意义”
function hasMeaningfulDataGraph(g) {
  try {
    const nodes = (g && Array.isArray(g.nodes)) ? g.nodes : [];
    if (!nodes.length) return false;
    return nodes.some(isNodeFinalish);
  } catch(_) {}
  return false;
}

// 记录：每个节点最后一次被“finalish 推入 ring”时的摘要，用于去重
window.__nodeFinalDigest = window.__nodeFinalDigest || {};
function computeNodeDigest(n) {
  try {
    const outs = Array.isArray(n?.Outputs) ? n.Outputs.map(o=>({C:o?.Context,N:o?.Num,B:o?.Boolean})) : [];
    const dbg  = typeof n?.debug === 'string' ? n.debug.length : 0;
    return JSON.stringify({ st: n?.IsError? 'E' : (n?.isFinish? 'F':'?'), outs, dbg });
  } catch(_) { return ''; }
}

// 合并：优先采用服务端结构，但保留本地已有的运行记录（Outputs/Debug/状态）
function mergeGraphPreservingData(oldGraph, newGraph) {
  try {
    if (!oldGraph) return structuredClone(newGraph);
    if (!newGraph) return structuredClone(oldGraph);
    const result = structuredClone(newGraph);
    const oldNodes = (oldGraph.nodes||[]);
    const resNodes = (result.nodes||[]);
    resNodes.forEach(rn => {
      const on = oldNodes.find(x => x && rn && x.id === rn.id);
      if (!on) return;
      // 保留 Outputs 内容（当新数据为空或缺省时）
      if (Array.isArray(rn.Outputs) && Array.isArray(on.Outputs)) {
        rn.Outputs = rn.Outputs.map((o, idx) => {
          const oo = on.Outputs[idx];
          if (!o && oo) return structuredClone(oo);
          if (!o || !oo) return o || oo || o;
          const merged = structuredClone(o);
          const ctxEmpty = !(merged.Context && String(merged.Context).length) && merged.Num === null && merged.Num === undefined && merged.Boolean !== true;
          if (ctxEmpty) {
            merged.Context = oo.Context;
            merged.Num = (merged.Num===null||merged.Num===undefined) ? oo.Num : merged.Num;
            if (merged.Boolean !== true) merged.Boolean = oo.Boolean;
          }
          // token 字段
          ['prompt_tokens','completion_tokens','total_tokens'].forEach(k=>{
            if (merged[k] === undefined && oo[k] !== undefined) merged[k] = oo[k];
          });
          return merged;
        });
      }
      // 保留 debug
      {
        const rnDbgEmpty = (typeof rn.debug !== 'string' || rn.debug.trim()==='');
        const onDbgNonEmpty = (typeof on.debug === 'string' && on.debug.trim()!=='');
        const oldWasError = (on?.IsError === true) || (typeof on?.ErrorContext === 'string' && on.ErrorContext.trim() !== '');
        const newIsSuccessFinal = (rn?.isFinish === true) && (rn?.IsError === false);
        // 若从“错误→成功”且新 debug 为空：不要保留旧错误 debug，直接清空
        if (rnDbgEmpty && oldWasError && newIsSuccessFinal) {
          rn.debug = '';
        } else if (rnDbgEmpty && onDbgNonEmpty) {
          rn.debug = on.debug;
        }
      }
      // 保留状态位（仅在新数据缺省时）
      ['IsRunning','isFinish','IsError','ErrorContext'].forEach(k=>{
        if (rn[k] === undefined && on[k] !== undefined) rn[k] = on[k];
      });
    });
    return result;
  } catch(_) {
    return structuredClone(newGraph || oldGraph);
  }
}

// 基于节点状态的合并：
// - 始终同步状态位（IsRunning / isFinish / IsError / ErrorContext）
// - 仅当目标节点 isFinish 或 IsError 为 true，或新输出/调试“有内容”时，才覆盖运行期数据（Outputs / debug / Prompt）
function mergeGraphStateAware(oldGraph, newGraph) {
  try {
    if (!oldGraph) return structuredClone(newGraph);
    if (!newGraph) return structuredClone(oldGraph);
    const result = structuredClone(newGraph);
    const oldNodes = Array.isArray(oldGraph.nodes) ? oldGraph.nodes : [];
    const resNodes = Array.isArray(result.nodes) ? result.nodes : [];
    try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] begin', { oldCount: oldNodes.length, newCount: resNodes.length }); } catch(_) {}
    resNodes.forEach(rn => {
      const on = oldNodes.find(x => x && rn && x.id === rn.id);
      if (!on) return;
      // 1) 状态位始终同步
      ['IsRunning','isFinish','IsError','ErrorContext'].forEach(k=>{
        rn[k] = (rn[k] !== undefined) ? rn[k] : on[k];
      });
      const finalish = rn.IsError === true || rn.isFinish === true;

      // 2) 合并 Outputs（仅在最终态或新输出有“内容”时才覆盖，否则保留旧值）
      const newOuts = Array.isArray(rn.Outputs) ? rn.Outputs : [];
      const oldOuts = Array.isArray(on.Outputs) ? on.Outputs : [];
      const hasNewUsefulOut = newOuts.some(o => o && ((o.Context && String(o.Context).length)
        || (o.Num !== null && o.Num !== undefined) || o.Boolean === true));
      const hasOldUsefulOut = oldOuts.some(o => o && ((o.Context && String(o.Context).length)
        || (o.Num !== null && o.Num !== undefined) || o.Boolean === true));
      if (!finalish) {
        // 非最终态完全禁止覆盖
        try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] deny overwrite (not final)', { id: rn.id, label: rn.label, isFinish: rn.isFinish, IsError: rn.IsError, hasNewUsefulOut, hadOld: hasOldUsefulOut }); } catch(_) {}
        rn.Outputs = structuredClone(oldOuts);
      } else if (finalish && hasNewUsefulOut && newOuts.length) {
        try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] overwrite Outputs (finalish)', { id: rn.id, label: rn.label, isFinish: rn.isFinish, IsError: rn.IsError }); } catch(_) {}
        rn.Outputs = newOuts.map((o, idx) => {
          const oo = oldOuts[idx];
          if (!o && oo) return structuredClone(oo);
          if (!o || !oo) return o || oo || o;
          const merged = structuredClone(o);
          const ctxEmpty = !(merged.Context && String(merged.Context).length) && merged.Num === null && merged.Num === undefined && merged.Boolean !== true;
          if (ctxEmpty) {
            merged.Context = oo.Context;
            merged.Num = (merged.Num===null||merged.Num===undefined) ? oo.Num : merged.Num;
            if (merged.Boolean !== true) merged.Boolean = oo.Boolean;
          }
          ['prompt_tokens','completion_tokens','total_tokens'].forEach(k=>{
            if (merged[k] === undefined && oo[k] !== undefined) merged[k] = oo[k];
          });
          return merged;
        });
      } else {
        // 最终态但新数据没有有效输出 -> 仍保留旧值
        try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] keep old Outputs (final but new empty)', { id: rn.id, label: rn.label, isFinish: rn.isFinish, IsError: rn.IsError }); } catch(_) {}
        rn.Outputs = structuredClone(oldOuts);
      }

      // 3) 合并 debug（仅在最终态或新 debug 非空时覆盖）
      const newDbg = (typeof rn.debug === 'string') ? rn.debug.trim() : '';
      const oldDbg = (typeof on.debug === 'string') ? on.debug : '';
      const oldWasError = (on?.IsError === true) || (typeof on?.ErrorContext === 'string' && on.ErrorContext.trim() !== '');
      const newIsSuccessFinal = (rn?.isFinish === true) && (rn?.IsError === false);
      if (!finalish) {
        if (oldDbg) { try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] keep old debug (not final)', { id: rn.id, label: rn.label, isFinish: rn.isFinish, IsError: rn.IsError }); } catch(_) {} }
        rn.debug = oldDbg;
      } else if (finalish && newDbg !== '') {
        try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] overwrite debug (finalish)', { id: rn.id, label: rn.label, isFinish: rn.isFinish, IsError: rn.IsError }); } catch(_) {}
      } else {
        // 若从“错误→成功”且新 debug 为空：清空旧错误 debug
        if (oldWasError && newIsSuccessFinal) {
          rn.debug = '';
        } else {
          if (oldDbg) { try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] keep old debug (final but new empty)', { id: rn.id, label: rn.label, isFinish: rn.isFinish, IsError: rn.IsError }); } catch(_) {} }
          rn.debug = oldDbg;
        }
      }

      // 4) Prompt 类字段（仅在最终态或新字段非空时覆盖）
      const newEP = (typeof rn.ExportPrompt === 'string') ? rn.ExportPrompt.trim() : '';
      const oldEP = (typeof on.ExportPrompt === 'string') ? on.ExportPrompt : '';
      if (!finalish) {
        if (oldEP) { try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] keep old ExportPrompt (not final)', { id: rn.id, label: rn.label, isFinish: rn.isFinish, IsError: rn.IsError }); } catch(_) {} }
        rn.ExportPrompt = oldEP;
      } else if (finalish && newEP !== '') {
        try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] overwrite ExportPrompt (finalish)', { id: rn.id, label: rn.label, isFinish: rn.isFinish, IsError: rn.IsError }); } catch(_) {}
      } else {
        if (oldEP) { try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] keep old ExportPrompt (final but new empty)', { id: rn.id, label: rn.label, isFinish: rn.isFinish, IsError: rn.IsError }); } catch(_) {} }
        rn.ExportPrompt = oldEP;
      }

      const newSP = (typeof rn.SystemPrompt === 'string') ? rn.SystemPrompt.trim() : '';
      const oldSP = (typeof on.SystemPrompt === 'string') ? on.SystemPrompt : '';
      if (!finalish) {
        if (oldSP) { try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] keep old SystemPrompt (not final)', { id: rn.id, label: rn.label, isFinish: rn.isFinish, IsError: rn.IsError }); } catch(_) {} }
        rn.SystemPrompt = oldSP;
      } else if (finalish && newSP !== '') {
        try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] overwrite SystemPrompt (finalish)', { id: rn.id, label: rn.label, isFinish: rn.isFinish, IsError: rn.IsError }); } catch(_) {}
      } else {
        if (oldSP) { try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE] keep old SystemPrompt (final but new empty)', { id: rn.id, label: rn.label, isFinish: rn.isFinish, IsError: rn.IsError }); } catch(_) {} }
        rn.SystemPrompt = oldSP;
      }
    });
    return result;
  } catch (_) {
    return structuredClone(newGraph || oldGraph);
  }
}

function applyTitleNow(baseTitle, backendQueueLengths, inPreheat) {
  try {
    // 如果有动画在运行，不覆盖标题
    if (window.titleInterval) {
      console.warn('[WFDBG:APPLY] 跳过标题设置，动画正在运行');
      return;
    }
    
    const passLen = (backendQueueLengths && typeof backendQueueLengths.passivity === 'number') ? backendQueueLengths.passivity : 0;
    const arrLen  = (backendQueueLengths && typeof backendQueueLengths.array === 'number') ? backendQueueLengths.array : 0;
    document.title = inPreheat ? (baseTitle || '') : `${baseTitle || ''}{${passLen}}[${arrLen}]`;
    try {
      const key = `${baseTitle}|${inPreheat?'pre':''}|${passLen}|${arrLen}`;
      if (window.__TITLE_NOW_LAST__ !== key) {
        console.warn('[WFDBG:APPLY] base=', baseTitle, ' preheat=', !!inPreheat, ' P=', passLen, ' A=', arrLen, ' title=', document.title);
        window.__TITLE_NOW_LAST__ = key;
      }
    } catch(_) {}
  } catch (_) {}
}

// 精简列摘要：仅打印包含 passivityTrigger / ArrayTrigger 的列，以及这些列内的所有节点（按 y 排序）
// function printTriggerColumnsSummary(graphData) {
//   try {
//     const nodes = (graphData && Array.isArray(graphData.nodes)) ? graphData.nodes : [];
//     if (!nodes.length) return;

//     const colWidth = 200;
//     const getCol = n => Math.round(((typeof n.x === 'number' ? n.x : 0)) / colWidth);
//     const kindAbbr = k => {
//       const s = (k || '').toLowerCase();
//       if (s.includes('passivitytrigger')) return 'P';
//       if (s.includes('arraytrigger'))     return 'A';
//       if (s.includes('llm'))              return 'L';
//       if (s.includes('ifnode'))           return 'IF';
//       if (s.includes('database'))         return 'DB';
//       if (s.includes('normal'))           return 'N';
//       return (k || '').slice(0, 2);
//     };

//     const cols = new Map();
//     const pCols = new Set();
//     const aCols = new Set();
//     nodes.forEach(n => {
//       const c = getCol(n);
//       if (!cols.has(c)) cols.set(c, []);
//       cols.get(c).push(n);
//       const k = (n.NodeKind || '').toLowerCase();
//       if (k.includes('passivitytrigger')) pCols.add(c);
//       if (k.includes('arraytrigger')) aCols.add(c);
//     });

//     const targetCols = Array.from(new Set([...pCols, ...aCols])).sort((a,b)=>a-b);
//     if (!targetCols.length) return;

//     const lines = [];
//     lines.push(`[COLS] P=${Array.from(pCols).sort((a,b)=>a-b).join(',')} A=${Array.from(aCols).sort((a,b)=>a-b).join(',')} total=${cols.size}`);
//     targetCols.forEach(ci => {
//       const list = (cols.get(ci) || []).slice().sort((a,b)=> (a.y||0)-(b.y||0));
//       const row = list.map(n => {
//         const status = n.IsError ? 'ERR' : (n.IsRunning ? 'RUN' : (n.isFinish ? 'FIN' : 'IDLE'));
//         return `${n.label || n.id}(${kindAbbr(n.NodeKind)}/${status})`;
//       }).join(' · ');
//       lines.push(`C${ci} | ${row}`);
//     });

//     const out = lines.join('\n');
//     if (window.__COLS_LAST__ !== out) {
//       window.__COLS_LAST__ = out;
//       console.warn(out);
//     }
//   } catch (_) {}
// }

// 后端状态 → 统一更新运行按钮和“当前工作流”显示
function updateUIFromBackendStatus(statusData) {
  try {
    const btn = document.getElementById('runButton');
    const infoEl = document.getElementById('currentWorkflowInfo');
    if (!btn) return;

    const status   = statusData?.status || 'idle';
    const wfId     = statusData?.workflow_id || monitoredWorkflowId || currentWorkflowId || null;
    const projName = statusData?.graph_project_name || statusData?.project_name || '';
    const childSummaryText = formatChildSummaryText(statusData?.childSummary);
    
    // 记录最后的状态和项目名称，用于错误恢复
    if (status && status !== 'idle') {
      window.__lastWorkflowStatus = status;
    }
    if (projName) {
      window.__lastWorkflowProjectName = projName;
    }
    if (wfId) {
      window.__lastWorkflowId = wfId;
    }
    
    // 如果状态是 completed，标记需要保存图数据（但不在此时保存，等 ChangeDatas 后再保存）
    // 这样可以确保保存的是前端实际显示的完整图数据，而不是后端返回的可能不完整的数据
    if (status === 'completed' && statusData?.graph_data) {
      const nodes = statusData.graph_data.nodes || [];
      const hasRunningNodes = nodes.some(n => n && n.IsRunning === true);
      const allNodesFinished = nodes.every(n => !n || n.isFinish === true || n.IsError === true || String(n.NodeKind || '').toLowerCase().endsWith('trigger'));
      
      // 标记需要保存图数据（在 ChangeDatas 之后保存）
      if (!hasRunningNodes && allNodesFinished) {
        window.__shouldSaveCompletedGraph = true;
        console.log('[MODE]💾  标记需要保存完成时的图数据，节点数:', nodes.length, '已完成节点:', nodes.filter(n => n && (n.isFinish || n.IsError)).length);
      } else {
        console.warn('[MODE]⚠️  工作流状态为 completed，但仍有节点运行中，暂不标记保存图数据');
      }
    }
    
    // 根据当前状态推断并更新 frontendMode（必须在检测切换之前更新）
    console.warn('[test13]0',isRecordMode, currentWorkflowId, wfId, status);
    // 如果状态是 completed 且有 wfId，切换到 monitor_completed 模式并锁定
    const canEnterMonitor = shouldEnterMonitorCompleted(statusData);
    if (wfId && status === 'completed' && canEnterMonitor) {
      frontendMode = 'monitor_completed';
      // 停止轮询，因为已完成状态需要锁定
      setWorkflowPollingInterval(0);
      console.warn('[MODE]1 后端返回的节点数:', statusData?.graph_data?.nodes);
      
      // 🔥 关键修复：立即加载后端返回的图数据到前端
      if (statusData?.graph_data) {
        try {
          const graphDataToLoad = structuredClone(statusData.graph_data);
          // 确保所有已完成节点的 IsBlock 为 true，以便正确显示颜色
          if (graphDataToLoad.nodes) {
            graphDataToLoad.nodes.forEach(node => {
              if (node && node.IsRunning === true) {
                // 修复运行中的节点状态
                node.IsRunning = false;
                if (!node.isFinish && !node.IsError) {
                  node.isFinish = true;
                }
              }
              // 确保所有已完成节点的 IsBlock 为 true
              if (node && (node.isFinish || node.IsError)) {
                node.IsBlock = true;
              }
            });
          }
          // 加载图数据到前端
          ChangeDatas(graphDataToLoad);
          RefreshEdge();
          console.log('[MODE]✅  monitor_completed 模式：已加载后端图数据，节点数:', graphDataToLoad.nodes?.length || 0);
          
          // 手动触发节点更新，确保颜色正确显示
          if (graphDataToLoad.nodes) {
            graphDataToLoad.nodes.forEach(node => {
              const nodeItem = graph.findById(node.id);
              if (nodeItem) {
                graph.updateItem(nodeItem, {
                  IsBlock: node.IsBlock,
                  IsRunning: node.IsRunning,
                  isFinish: node.isFinish,
                  IsError: node.IsError
                });
              }
            });
          }
        } catch (e) {
          console.warn('[MODE]⚠️  加载图数据失败:', e);
        }
      }
      
      // 注意：此时后端返回的 graph_data 可能不完整，真正的完整图数据会在 ChangeDatas 之后从前端获取
    } else if (wfId && status === 'completed' && !canEnterMonitor) {
      frontendMode = 'edit';
    } else if (frontendMode === 'monitor_completed') {
      // 如果已经是 monitor_completed 模式，保持该模式（除非用户主动退出）
      // 不在这里改变模式，保持锁定状态
    } else if (wfId && status !== 'stopped') {
      frontendMode = (currentWorkflowId && currentWorkflowId === wfId) ?  'monitor':'edit' ;
    } else {
      if(isRecordMode===true){
        frontendMode = 'monitor';
      }else{
        frontendMode = 'edit';
      }
    }
    
    console.warn('[test13]1', status, wfId, projName, 'mode=', frontendMode);

    // 根据前端模式决定"当前工作流"显示：
    // - edit 模式：始终显示"当前工作流：无"
    // - monitor 模式：显示实际工作流名称 + 状态
    if (infoEl) {
      const mode = (typeof frontendMode === 'string') ? frontendMode : 'edit';
      console.warn('[test13]2',prevFrontendMode,frontendMode,mode,wfId,status)
      
      // 检测从monitor或monitor_completed变为edit的切换，首次切换时设置所有组件的IsBlock=false
      if ((prevFrontendMode === 'monitor' || prevFrontendMode === 'monitor_completed') && mode === 'edit') {
        if (typeof graph !== 'undefined' && graph) {
          try {
            const graphData = graph.save();
            if (graphData && graphData.nodes) {
              graphData.nodes.forEach(nodez => {
                nodez.IsBlock = false;
              });
              ChangeDatas(graphData); 
              console.warn('[test13]3',graphData);
            }
          } catch (e) {
            console.warn('设置IsBlock失败:', e);
          }
        }
      }
      
      // 更新prevFrontendMode
      prevFrontendMode = mode;
      
      if (mode === 'edit') {
        infoEl.textContent = '当前工作流：无';
      } else if (mode === 'monitor_completed') {
        // monitor_completed 模式：显示已完成状态
        if (!wfId) {
          infoEl.textContent = '当前工作流：无';
        } else {
          const name = projName || wfId;
          infoEl.textContent = `当前工作流：${name}（已完成）${childSummaryText}`;
        }
      } else {
        if (!wfId || status === 'idle') {
          infoEl.textContent = '当前工作流：无';
        } else {
          let statusLabel = '未知';
          if (status === 'running')  statusLabel = '运行中';
          else if (status === 'paused')    statusLabel = '已暂停';
          else if (status === 'completed') statusLabel = '已完成';
          else if (status === 'error')     statusLabel = '错误';
          else if (status === 'stopped')   statusLabel = '已停止';
          const name = projName || wfId;
          infoEl.textContent = `当前工作流：${name}（${statusLabel}）${childSummaryText}`;
        }
      }
    }

    // 运行按钮文本/颜色完全跟随后端状态 + 本地预热标记
    if (status === 'running') {
      // 预热阶段优先显示“接收中...”
      if (window.inPreheat) {
        btn.textContent = '接收中...';
        btn.style.backgroundColor = '#ff9100';
      } else {
        btn.textContent = '运行中...';
        btn.style.backgroundColor = '#3d8fff';
      }
    } else if (status === 'paused') {
      btn.textContent = '已暂停';
      btn.style.backgroundColor = '#ff9100';
    } else if (status === 'completed') {
      // 运行完成时仍然用绿色提示一次成功
      btn.textContent = '运行完成';
      btn.style.backgroundColor = '#4CAF50';
    } else {
      // idle / stopped / error / 其他未知状态 → 视为“编辑模式”
      btn.textContent = '运行';
      // ★ 编辑模式统一使用黑色按钮
      btn.style.backgroundColor = '#1e1e1e';
    }

    // 统一维护 IsTriggerNode：仅在运行/暂停时视为 true
    if (typeof IsTriggerNode !== 'undefined') {
      IsTriggerNode = (status === 'running' || status === 'paused');
    }

    // 根据是否有活跃工作流调整轮询频率：
    // - monitor_completed 模式 → 停止轮询（已锁定）
    // - 有工作流（running/paused） → 高频 300ms
    // - 其它情况 → 低频 2000ms，用于探测新工作流
    if (frontendMode === 'monitor_completed') {
      setWorkflowPollingInterval(0); // 停止轮询
    } else if (wfId && (status === 'running' || status === 'paused')) {
      setWorkflowPollingInterval(300);
    } else {
      setWorkflowPollingInterval(2000);
    }
  } catch (_) {}
}

// 使用async/await重构轮询函数（唯一的状态同步入口）
async function pollWorkflowStatus() {
  try {
    console.warn('[WFDBG:SELECT]', {
      currentObservedWorkflowId,
      monitoredWorkflowId,
      currentWorkflowId,
      frontendMode,
      inPreheat: !!window.inPreheat
    });
    // 如果处于 monitor_completed 模式，停止轮询（已完成状态已锁定）
    if (frontendMode === 'monitor_completed') {
      return;
    }
    
    // 更新工作流选择器
    await updateWorkflowSelector();
    
    // 优先使用当前观察的工作流ID；其次使用当前监控的 workflowId；最后询问 /workflow/status/current
    let wfId = currentObservedWorkflowId || monitoredWorkflowId || currentWorkflowId || null;

    if (!wfId) {
      const currentRes = await fetch('/workflow/status/current');
      if (!currentRes.ok) {
        console.warn('[WFDBG:STATUS:current] /workflow/status/current not ok', currentRes.status);
        return;
      }
      const currentData = await currentRes.json();
      // 先用当前状态更新一次 UI（即使是 idle 也可以刷新"当前工作流：无"）
      updateUIFromBackendStatus(currentData);

      if (currentData.status !== 'idle' && currentData.workflow_id) {
        wfId = currentData.workflow_id;
        monitoredWorkflowId = wfId;
        currentObservedWorkflowId = wfId;
        console.warn('[WFDBG:STATUS:current] adopt current workflow', wfId);
      } else {
        // 后端也没有活跃工作流，本轮无需再查具体状态
        console.warn('[WFDBG:STATUS:current] idle, no active workflow');
        return;
      }
    }

    // 获取指定工作流的详细状态（包含 graph_data / 队列等）
    console.warn(`[WORKFLOW-SELECTOR] 轮询工作流状态: ${wfId}`);
    const response = await fetch(`/workflow/status/${wfId}`);
    
    // 检查响应是否成功
    if (!response.ok) {
      console.warn('[WFDBG:STATUS] response not ok', response.status, 'wfId=', wfId);
      // 如果工作流不存在，可能是已完成或被清理，尝试更新选择器
      if (response.status === 404 && currentObservedWorkflowId === wfId) {
        console.warn(`[WORKFLOW-SELECTOR] 工作流 ${wfId} 不存在，更新选择器`);
        await updateWorkflowSelector();
        // 如果还有其他工作流，自动切换
        const listRes = await fetch('/workflow/list');
        if (listRes.ok) {
          const listData = await listRes.json();
          const runningWorkflows = (listData.workflows || []).filter(wf => wf.status === 'running');
          if (runningWorkflows.length > 0) {
            switchToWorkflow(runningWorkflows[0].id);
            return;
          }
        }
        currentObservedWorkflowId = null;
      }
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    // 解析JSON响应
    let data = await response.json();
    const status = data.status || 'idle';
    console.warn('[WFDBG:RESP]', { wfId, status, hasGraph: !!data.graph_data, queues: data.queues, queue_lengths: data.queue_lengths });
    try {
      const nodesRaw = data?.graph_data?.nodes || [];
      const running = nodesRaw.filter(n => n && n.IsRunning === true).map(n => n.label || n.id);
      const finished = nodesRaw.filter(n => n && n.isFinish === true).map(n => n.label || n.id);
      const errored = nodesRaw.filter(n => n && n.IsError === true).map(n => n.label || n.id);
      console.warn('[WFDBG:RESP:NODES]', {
        wfId,
        total: nodesRaw.length,
        runningCount: running.length,
        finishedCount: finished.length,
        errorCount: errored.length,
        sampleRunning: running.slice(0, 5),
        sampleFinished: finished.slice(0, 5),
        sampleError: errored.slice(0, 5)
      });
    } catch (_) {}

    // 若当前观测的工作流已停止/完成/出错，自动切到其他 running 的工作流
    if (status === 'stopped' || status === 'completed' || status === 'error') {
      try {
        const listRes = await fetch('/workflow/list');
        if (listRes.ok) {
          const listData = await listRes.json();
          const runningList = (listData.workflows || []).filter(w => w.status === 'running' && w.id !== wfId);
          if (runningList.length > 0) {
            const nextWf = runningList[0];
            console.warn('[WFDBG:SWITCH] current non-running, switch to', nextWf.id);
            currentWorkflowId = nextWf.id; // 将当前工作流也切到新的运行实例，便于动画和按钮同步
            switchToWorkflow(nextWf.id);
            return; // 等下一轮轮询按新ID取状态
          } else {
            console.warn('[WFDBG:SWITCH] no other running workflow to switch');
          }
        } else {
          console.warn('[WFDBG:SWITCH] /workflow/list not ok', listRes.status);
        }
      } catch (e) {
        console.warn('[WFDBG:SWITCH] list error', e);
      }
    }
    
    // 确保使用的工作流ID与当前观察的一致
    if (currentObservedWorkflowId && currentObservedWorkflowId !== wfId) {
      console.warn(`[WORKFLOW-SELECTOR] 检测到工作流ID不一致，当前观察: ${currentObservedWorkflowId}, 轮询: ${wfId}，重新获取正确的工作流状态`);
      // 如果当前观察的工作流已改变，重新轮询正确的工作流
      wfId = currentObservedWorkflowId;
      const newResponse = await fetch(`/workflow/status/${wfId}`);
      if (newResponse.ok) {
        data = await newResponse.json();
        console.warn(`[WORKFLOW-SELECTOR] 已获取正确的工作流 ${wfId} 的状态`);
      } else {
        console.warn(`[WORKFLOW-SELECTOR] 无法获取工作流 ${wfId} 的状态`);
        return;
      }
    }
    
    // === 调试：集中打印关键信息 ===
    window.__WF_DEBUG__ = window.__WF_DEBUG__ || { seq: 0 };
    const seq = ++window.__WF_DEBUG__.seq;
    const pLenDbg = data.queue_lengths?.passivity ?? null;
    const aLenDbg = data.queue_lengths?.array ?? null;
    // 如后端提供指纹，打印一次，便于排查入环重复
    try {
      if (data.ringFingerprint && window.__LAST_FP__ !== data.ringFingerprint) {
        window.__LAST_FP__ = data.ringFingerprint;
        console.warn('[RING:FP] recv', data.ringFingerprint);
      }
    } catch(_) {}
    // 收到真实指纹后：如存在最近的临时项，则重绑为真实指纹并通过 upsert 覆盖
    if (data.ringFingerprint) {
      const realFp = data.ringFingerprint;
      try {
        const ringObj = (window.__snapshotRing = window.__snapshotRing || { items: [] });
        const ring = ringObj.items;
        if (Array.isArray(ring)) {
          const j = ring.findIndex(it => it && it.__isProvisional);
          if (j >= 0) {
            const item = ring.splice(j, 1)[0];
            item.__fingerprint = realFp;
            delete item.__isProvisional;
            upsertRingByFingerprint(ringObj, item, realFp, ringObj?.max || 20);
          }
        }
      } catch (_) {}
    }
    // 精简日志：仅保留标题与侧栏相关

    
    if (data.error) {
      console.warn('[WF-STATUS] 接口返回错误:', data.error);
      if (data.status === 'completed') {
        updateUIFromBackendStatus(data);
        if (shouldEnterMonitorCompleted(data)) {
          enterMonitorCompletedMode(data, wfId);
        } else {
          handleWorkflowNotFound(wfId);
        }
        return;
      }
      if (String(data.error).includes('Workflow not found')) {
        handleWorkflowNotFound(wfId);
        return;
      }
      console.error(`❌ [ERROR] ${data.error}`);
      if (data.traceback) {
        console.error('🔍 [TRACEBACK]\n' + data.traceback);
      }
      showMessage(`获取工作流状态失败: ${data.error}`, 'orange');
      return;
    }

    if (status === 'completed') {
      updateUIFromBackendStatus(data);
      if (shouldEnterMonitorCompleted(data)) {
        enterMonitorCompletedMode(data, wfId);
      } else {
        handleWorkflowNotFound(wfId);
      }
      return;
    }

    if (status === 'stopped' || status === 'error') {
      updateUIFromBackendStatus(data);
      handleWorkflowNotFound(wfId);
      return;
    }

  // 预热阶段检测和处理
  // 规则：仅当“存在 passivityTrigger 且 正在运行 且 两队列为0 且 当前响应无运行节点”时视为预热
  const hasP = window.currentHasPassivityTrigger === true;
  const isRunning = data.status === 'running';
  const pLen = (data.queue_lengths && typeof data.queue_lengths.passivity === 'number') ? data.queue_lengths.passivity : 0;
  const aLen = (data.queue_lengths && typeof data.queue_lengths.array === 'number') ? data.queue_lengths.array : 0;
  const anyRunningInResp = ((data.graph_data && Array.isArray(data.graph_data.nodes)) ? data.graph_data.nodes : []).some(n => n && n.IsRunning === true);
    
    // 更新后端队列长度（优先读取固定字段 queues，其次回退到 queue_lengths）
    (function(){
      try {
        // 优先读取 queue_lengths（后端真源），若无再回退 queues
        const qsrc = (data && typeof data === 'object') ? (data.queue_lengths || data.queues || null) : null;
        const q = qsrc;
        if (q) {
          // 记录原始字段与类型，便于定位后端返回是否为字符串
          try { if (window.LOG && window.LOG.wf) console.warn('[WFDBG:QUEUE:RAW]', { q, types: { passivity: typeof q.passivity, pending: typeof q.pending, array: typeof q.array } }); } catch(_) {}
          // 统一数值化，兼容字符串数字
          const rawPass = (q.passivity !== undefined ? q.passivity : q.pending);
          const passNum = Number(rawPass);
          const arrNum  = Number(q.array);
          let pass = Number.isFinite(passNum) ? passNum : 0;
          let arr  = Number.isFinite(arrNum)  ? arrNum  : 0;
          // 兜底：若服务端为0但本地数组队列存在，临时用本地长度显示，避免标题不变
          if ((pass === 0 || !Number.isFinite(pass)) && Array.isArray(window.passivityTriggerArray)) pass = Math.max(pass, window.passivityTriggerArray.length|0);
          if ((arr === 0 || !Number.isFinite(arr)) && Array.isArray(window.ArrayTriggerArray))     arr  = Math.max(arr,  window.ArrayTriggerArray.length|0);
          backendQueueLengths = { passivity: pass, array: arr };
          try { console.warn('[WFDBG:QUEUE] set from status', { pass, arr, wfId }); } catch(_) {}
        } else {
          console.warn('[WFDBG:QUEUE] no q in status', { wfId });
        }
      } catch(err) {
        try { if (window.LOG && window.LOG.wf) console.warn('[WFDBG:QUEUE] parse error:', err); } catch(_) {}
      }
    })();
    
  // 仅当满足上述规则才进入预热
  const shouldBeInPreheat = hasP && isRunning && pLen === 0 && aLen === 0 && !anyRunningInResp;
    
  if (shouldBeInPreheat && !window.inPreheat) {
    // 进入预热状态（按钮文案交给 updateUIFromBackendStatus 统一处理）
    window.inPreheat = true;
    // 在预热状态下也更新一次标题，确保动画就绪
    updateFileName(FileName, Callsign);
    // 关闭边动画刷新，预热时不需要任何动画
    if (window.fastAnimationInterval) {
      clearInterval(window.fastAnimationInterval);
      window.fastAnimationInterval = null;
    }
    // 预热时仅关闭动画，但仍继续下面的数据应用（ChangeDatas/RefreshEdge）
  } else if (!shouldBeInPreheat && window.inPreheat) {
    // 退出预热状态（任意非 running 最终态/或检测到非预热条件时）
    window.inPreheat = false;
    // 恢复边动画刷新（由轮询驱动图数据变更后再刷新一次，不再额外100ms循环）
    if (window.fastAnimationInterval) {
      clearInterval(window.fastAnimationInterval);
      window.fastAnimationInterval = null;
    }
  } else if (!shouldBeInPreheat && !isRunning && window.inPreheat) {
    // 若工作流不处于 running，强制退出预热
    window.inPreheat = false;
  }

    // 预热状态更新完成后，根据最新后端状态统一刷新按钮/当前工作流信息
    updateUIFromBackendStatus(data);
    
    // 记录最后的状态和项目名称，用于错误恢复
    if (data.status) {
      window.__lastWorkflowStatus = data.status;
    }
    if (data.graph_project_name || data.project_name) {
      window.__lastWorkflowProjectName = data.graph_project_name || data.project_name;
    }
    
    // 如果状态是 completed，标记需要保存图数据（但不在此时保存，等 ChangeDatas 后再保存）
    if (data.status === 'completed' && data.graph_data) {
      const nodes = data.graph_data.nodes || [];
      const hasRunningNodes = nodes.some(n => n && n.IsRunning === true);
      const allNodesFinished = nodes.every(n => !n || n.isFinish === true || n.IsError === true || String(n.NodeKind || '').toLowerCase().endsWith('trigger'));
      
      // 标记需要保存图数据（在 ChangeDatas 之后保存）
      if (!hasRunningNodes && allNodesFinished) {
        window.__shouldSaveCompletedGraph = true;
        console.log('[MODE]💾  标记需要保存完成时的图数据，节点数:', nodes.length, '已完成节点:', nodes.filter(n => n && (n.isFinish || n.IsError)).length);
      } else {
        console.warn('[MODE]⚠️  工作流状态为 completed，但仍有节点运行中，暂不标记保存图数据');
      }
    }

    // === 工作流结束后的自动切换逻辑 ===
    // 如果当前观察的工作流已完成，自动切换到下一个运行中的工作流
    try {
      const finished = (data.status === 'completed' || data.status === 'stopped' || data.status === 'error');
      if (finished && currentObservedWorkflowId && currentObservedWorkflowId === wfId) {
        // 获取所有运行中的工作流
        const listRes = await fetch('/workflow/list');
        if (listRes.ok) {
          const listData = await listRes.json();
          const runningWorkflows = (listData.workflows || []).filter(wf => 
            wf.status === 'running' && wf.id !== currentObservedWorkflowId
          );
          if (runningWorkflows.length > 0) {
            // 切换到第一个运行中的工作流
            console.warn(`[WORKFLOW-SELECTOR] 当前工作流已完成，自动切换到: ${runningWorkflows[0].id}`);
            switchToWorkflow(runningWorkflows[0].id);
            // 更新选择器后继续轮询新工作流
            return;
          } else {
            // 没有其他运行中的工作流，清空观察
            console.log('[WORKFLOW-SELECTOR] 当前工作流已完成，且无其他运行中的工作流');
            currentObservedWorkflowId = null;
          }
        }
      }
    } catch (e) {
      console.warn('[WORKFLOW-SELECTOR] 自动切换失败:', e);
    }
    
    // === 工作流结束后的 ID 释放策略 ===
    // 目的：无论是 index 还是 Control Room 启动的 workflow，只要结束/停止/出错，
    // 前端都不要再"死盯着旧的 workflowId"，而是允许后续通过 /workflow/status/current 发现新的 workflow。
    try {
      const finished = (data.status === 'completed' || data.status === 'stopped' || data.status === 'error');
      if (finished) {
        if (!currentWorkflowId) {
          // 纯监控模式：释放 monitoredWorkflowId，下一轮从 /workflow/status/current 重新发现
          console.warn('[WFDBG] release monitoredWorkflowId (monitor mode) because workflow finished:', wfId, 'status=', data.status);
          monitoredWorkflowId = null;
        } else if (currentWorkflowId && frontendMode === 'edit') {
          // 本页发起的 workflow：运行结束后也释放 ID，避免后续 Control Room 新起的 workflow 被旧 ID 卡住
          console.warn('[WFDBG] clear currentWorkflowId/monitoredWorkflowId (edit mode) because workflow finished:', currentWorkflowId, 'status=', data.status);
          currentWorkflowId = null;
          monitoredWorkflowId = null;
        }
      }
    } catch(_) {}
    
    // 若进入 running，重置本轮完成打印标志
    try {
      if (data.status === 'running') {
        if (window.__RUN_STATE__ !== 'running') {
          window.__RUN_STATE__ = 'running';
          window.__RUN_SUMMARY_PRINTED__ = false;
          window.__RUN_PROGRESS_PRINTED__ = false;
          try { if (window.LOG && window.LOG.wf) console.warn('[WFDBG:STATE] enter running, preheat=', !!window.inPreheat); } catch(_) {}
        }
      }
    } catch(_) {}
    
    // 更新图形数据
    // 在 monitor_completed 模式下，不更新图数据（保持完成时的状态）
    // 但如果状态刚变为 completed，需要最后一次更新并修复运行中的节点
    if (data.graph_data && data.status!='stopped') {
      // 如果刚进入 monitor_completed 模式，需要最后一次更新图数据并修复状态
      if (frontendMode === 'monitor_completed' && data.status === 'completed') {
        // 修复运行中的节点状态
        const fixedGraphData = structuredClone(data.graph_data);
        if (fixedGraphData.nodes) {
          let fixedCount = 0;
          fixedGraphData.nodes.forEach(node => {
            if (node && node.IsRunning === true) {
              node.IsRunning = false;
              if (!node.isFinish && !node.IsError) {
                node.isFinish = true;
              }
              fixedCount++;
            }
          });
          if (fixedCount > 0) {
            console.warn(`[MODE]🔧  修复了 ${fixedCount} 个运行中的节点状态`);
            ChangeDatas(fixedGraphData);
            RefreshEdge();
            // 在 ChangeDatas 之后，使用前端实际显示的图数据保存
            try {
              const currentGraphData = graph.save();
              if (currentGraphData && currentGraphData.nodes) {
                window.__lastCompletedGraphData = structuredClone(currentGraphData);
                // 确保所有已完成节点的 IsBlock 为 true，以便正确显示颜色
                window.__lastCompletedGraphData.nodes.forEach(node => {
                  if (node && (node.isFinish || node.IsError)) {
                    node.IsBlock = true;
                  }
                });
                console.log('[MODE]💾  保存修复后的前端图数据，节点数:', currentGraphData.nodes.length);
              }
            } catch (e) {
              console.warn('保存修复后的图数据失败:', e);
              // 兜底：使用修复后的数据
              window.__lastCompletedGraphData = fixedGraphData;
            }
          } else {
            // 即使没有修复，也要保存当前前端显示的图数据
            try {
              const currentGraphData = graph.save();
              if (currentGraphData && currentGraphData.nodes) {
                window.__lastCompletedGraphData = structuredClone(currentGraphData);
                // 确保所有已完成节点的 IsBlock 为 true
                window.__lastCompletedGraphData.nodes.forEach(node => {
                  if (node && (node.isFinish || node.IsError)) {
                    node.IsBlock = true;
                  }
                });
                console.log('[MODE]💾  保存当前前端图数据，节点数:', currentGraphData.nodes.length);
              }
            } catch (e) {
              console.warn('保存当前图数据失败:', e);
            }
          }
        }
        // 不再继续后续的图数据更新
        return;
      }
      
      // 非 monitor_completed 模式的正常更新
      if (frontendMode !== 'monitor_completed') {
        try {
          const q = (data && typeof data === 'object') ? (data.queue_lengths || data.queues || null) : null;
        const pass = q ? ((typeof q.passivity === 'number') ? q.passivity : (typeof q.pending === 'number' ? q.pending : 0)) : 0;
        const arr  = q ? ((typeof q.array === 'number') ? q.array : 0) : 0;
        const nodes = (data.graph_data && Array.isArray(data.graph_data.nodes)) ? data.graph_data.nodes : [];
        const snapshotSize = (window.__snapshotRing && Array.isArray(window.__snapshotRing.items)) ? window.__snapshotRing.items.length : 0;
        const nodeBrief = nodes.slice(0, 20).map(n=>{
          if(!n) return 'null';
          const st = n.IsError ? 'ERR' : (n.isFinish ? 'FIN' : (n.IsRunning ? 'RUN' : 'IDLE'));
          const outLen = Array.isArray(n.Outputs) ? n.Outputs.length : 0;
          return `${n.label||n.id}(${String(n.NodeKind||'?').slice(0,3)})=${st}/out${outLen}`;
        }).join(' · ');
        console.warn('[WFDBG:RESP]', { status: data.status, passivity: pass, array: arr, snapshotSize });
        console.warn('[WFDBG:NODES]', nodeBrief);
      } catch(_) {}
      // 基于状态的合并，避免在最终态之后被“空结构”回写清空
      const incoming = structuredClone(data.graph_data);
      const before = TempMessageNode;
      TempMessageNode = mergeGraphStateAware(TempMessageNode, incoming);
      try {
        if (window.MERGE_DEBUG !== false) {
          const changedIds = [];
          const afterNodes = (TempMessageNode && Array.isArray(TempMessageNode.nodes)) ? TempMessageNode.nodes : [];
          const beforeNodes = (before && Array.isArray(before.nodes)) ? before.nodes : [];
          afterNodes.forEach(an => {
            const bn = beforeNodes.find(n => n && an && n.id === an.id);
            if (!bn) return;
            const beforeKey = JSON.stringify({
              s: { run: bn.IsRunning, fin: bn.isFinish, err: bn.IsError },
              ep: bn.ExportPrompt || '', sp: bn.SystemPrompt || '',
              out: (Array.isArray(bn.Outputs) ? bn.Outputs.map(o=>({C:o?.Context, N:o?.Num, B:o?.Boolean})) : []),
              dbg: typeof bn.debug === 'string' ? bn.debug.length : 0
            });
            const afterKey = JSON.stringify({
              s: { run: an.IsRunning, fin: an.isFinish, err: an.IsError },
              ep: an.ExportPrompt || '', sp: an.SystemPrompt || '',
              out: (Array.isArray(an.Outputs) ? an.Outputs.map(o=>({C:o?.Context, N:o?.Num, B:o?.Boolean})) : []),
              dbg: typeof an.debug === 'string' ? an.debug.length : 0
            });
            if (beforeKey !== afterKey) changedIds.push({ id: an.id, label: an.label });
          });
          if (changedIds.length) console.warn('[MERGE] applied changes on nodes:', changedIds);
        }
      } catch(_) {}
      // 精简：不打印图数据概览
      try {} catch(_){}
      
      // 直接采用后端图（全量覆盖），避免局部合并造成状态不同步
      // 注意：后端返回的 graph_data 可能不完整，所以 ChangeDatas 后需要从前端获取完整数据
      console.warn('[MODE]📥 后端返回的节点数:', data.graph_data?.nodes?.length || 0);
      ChangeDatas(structuredClone(data.graph_data));
      
      // 在 ChangeDatas 之后，如果标记了需要保存完成时的图数据，优先使用后端返回的最新数据（包含最新的 Outputs）
      if (window.__shouldSaveCompletedGraph && data.status === 'completed') {
        // 🔥 关键修复：优先使用后端返回的 graph_data，因为它包含最新的 Outputs
        try {
          const backendNodes = data.graph_data?.nodes || [];
          const currentGraphData = graph.save();
          const frontendNodes = currentGraphData?.nodes || [];
          
          console.warn('[MODE]📊 前端实际节点数:', frontendNodes.length, '后端返回节点数:', backendNodes.length);
          
          // 优先使用后端数据（包含最新的 Outputs），如果后端数据不完整，则合并前端数据
          let finalGraphData = null;
          
          if (backendNodes.length > 0) {
            // 使用后端数据作为基础（包含最新的 Outputs）
            finalGraphData = structuredClone(data.graph_data);
            console.log('[MODE]✅  使用后端返回的图数据（包含最新 Outputs）');
            
            // 如果前端节点数更多，说明后端数据可能不完整，需要合并前端数据
            if (frontendNodes.length > backendNodes.length) {
              console.warn('[MODE]⚠️  后端数据不完整，合并前端完整数据');
              // 以后端数据为主，补充前端中后端没有的节点
              const backendNodeIds = new Set(backendNodes.map(n => n?.id).filter(Boolean));
              frontendNodes.forEach(fn => {
                if (fn && fn.id && !backendNodeIds.has(fn.id)) {
                  finalGraphData.nodes.push(structuredClone(fn));
                }
              });
            }
            
            // 合并后端最新的 Outputs 到最终数据中
            backendNodes.forEach(backendNode => {
              if (!backendNode || !backendNode.id) return;
              const finalNode = finalGraphData.nodes.find(n => n && n.id === backendNode.id);
              if (finalNode && Array.isArray(backendNode.Outputs) && backendNode.Outputs.length > 0) {
                // 使用后端的最新 Outputs（包含完整的 Context, Num, Boolean 等）
                finalNode.Outputs = structuredClone(backendNode.Outputs);
                // 同时更新其他状态
                if (backendNode.isFinish !== undefined) finalNode.isFinish = backendNode.isFinish;
                if (backendNode.IsError !== undefined) finalNode.IsError = backendNode.IsError;
                if (backendNode.IsRunning !== undefined) finalNode.IsRunning = backendNode.IsRunning;
                if (backendNode.debug !== undefined) finalNode.debug = backendNode.debug;
                console.log(`[MODE]🔄  更新节点 ${finalNode.label || finalNode.id} 的 Outputs，数量: ${finalNode.Outputs.length}`);
              }
            });
          } else {
            // 如果后端没有数据，使用前端数据
            finalGraphData = structuredClone(currentGraphData);
            console.warn('[MODE]⚠️  后端无数据，使用前端数据');
          }
          
          if (finalGraphData && finalGraphData.nodes) {
            const nodes = finalGraphData.nodes || [];
            // 检查所有节点是否都完成
            const hasRunningNodes = nodes.some(n => n && n.IsRunning === true);
            const allNodesFinished = nodes.every(n => !n || n.isFinish === true || n.IsError === true || String(n.NodeKind || '').toLowerCase().endsWith('trigger'));
            
            if (!hasRunningNodes && allNodesFinished) {
              // 确保所有已完成节点的 IsBlock 为 true，以便正确显示颜色
              finalGraphData.nodes.forEach(node => {
                if (node && (node.isFinish || node.IsError)) {
                  node.IsBlock = true;
                }
              });
              
              // 🔥 确保保存 ProjectName，以便记录模式能正确加载记录
              if (!finalGraphData.ProjectName && ProjectName) {
                finalGraphData.ProjectName = ProjectName;
              }
              
              window.__lastCompletedGraphData = structuredClone(finalGraphData);
              console.log('[MODE]💾  保存完成图数据，节点数:', nodes.length, '已完成节点:', nodes.filter(n => n && (n.isFinish || n.IsError)).length, 'ProjectName:', finalGraphData.ProjectName || ProjectName);
              
              // 打印每个节点的 Outputs 信息，用于调试
              nodes.forEach(node => {
                if (node && Array.isArray(node.Outputs) && node.Outputs.length > 0) {
                  const outputsInfo = node.Outputs.map(o => ({
                    name: o.name,
                    Context: o.Context ? (o.Context.length > 50 ? o.Context.substring(0, 50) + '...' : o.Context) : '',
                    Num: o.Num,
                    Boolean: o.Boolean
                  }));
                  console.log(`[MODE]📦  节点 ${node.label || node.id} 的 Outputs:`, outputsInfo);
                }
              });
              
              // 同时更新前端当前显示的图，确保 IsBlock 正确
              try {
                finalGraphData.nodes.forEach(node => {
                  if (node && (node.isFinish || node.IsError)) {
                    node.IsBlock = true;
                    const nodeItem = graph.findById(node.id);
                    if (nodeItem) {
                      graph.updateItem(nodeItem, {
                        IsBlock: true,
                        IsRunning: false,
                        isFinish: node.isFinish,
                        IsError: node.IsError
                      });
                    }
                  }
                });
                // 重新应用图数据，确保所有节点状态和 Outputs 正确
                ChangeDatas(finalGraphData);
              } catch (e) {
                console.warn('更新前端节点失败:', e);
              }
              
              // 清除标记
              window.__shouldSaveCompletedGraph = false;
            } else {
              // 如果还有节点未完成，延迟再试一次
              console.warn('[MODE]⚠️  图数据仍有节点未完成，延迟100ms后重试。运行中:', nodes.filter(n => n && n.IsRunning).length, '未完成:', nodes.filter(n => n && !n.isFinish && !n.IsError && !String(n.NodeKind || '').toLowerCase().endsWith('trigger')).length);
              setTimeout(() => {
                try {
                  // 延迟重试时，再次获取后端数据
                  const retryBackendData = data.graph_data;
                  const retryFrontendData = graph.save();
                  let retryFinalData = null;
                  
                  if (retryBackendData && retryBackendData.nodes && retryBackendData.nodes.length > 0) {
                    retryFinalData = structuredClone(retryBackendData);
                    // 合并最新的 Outputs
                    retryBackendData.nodes.forEach(backendNode => {
                      if (!backendNode || !backendNode.id) return;
                      const finalNode = retryFinalData.nodes.find(n => n && n.id === backendNode.id);
                      if (finalNode && Array.isArray(backendNode.Outputs) && backendNode.Outputs.length > 0) {
                        finalNode.Outputs = structuredClone(backendNode.Outputs);
                      }
                    });
                  } else {
                    retryFinalData = structuredClone(retryFrontendData);
                  }
                  
                  if (retryFinalData && retryFinalData.nodes) {
                    const retryNodes = retryFinalData.nodes || [];
                    const retryHasRunning = retryNodes.some(n => n && n.IsRunning === true);
                    const retryAllFinished = retryNodes.every(n => !n || n.isFinish === true || n.IsError === true || String(n.NodeKind || '').toLowerCase().endsWith('trigger'));
                    
                    if (!retryHasRunning && retryAllFinished) {
                      retryFinalData.nodes.forEach(node => {
                        if (node && (node.isFinish || node.IsError)) {
                          node.IsBlock = true;
                        }
                      });
                      window.__lastCompletedGraphData = structuredClone(retryFinalData);
                      console.log('[MODE]💾  延迟保存完整图数据，节点数:', retryNodes.length);
                    }
                  }
                  window.__shouldSaveCompletedGraph = false;
                } catch (e) {
                  console.warn('延迟保存失败:', e);
                  window.__shouldSaveCompletedGraph = false;
                }
              }, 100);
            }
          } else {
            window.__shouldSaveCompletedGraph = false;
          }
        } catch (e) {
          console.warn('保存完成图数据失败:', e);
          window.__shouldSaveCompletedGraph = false;
        }
      }
      
      // 精简：不打印快照环大小
      try {} catch(_) {}
      // 维护最近活跃快照（运行中或已有完成/错误节点）
      try {
        const nodesNow = (data.graph_data && data.graph_data.nodes) || [];
        // 入环标准：IsError=true 或 (isFinish=true 且 至少一个输出有效)
        const hasUsefulOut = (n) => Array.isArray(n?.Outputs) && n.Outputs.some(o => o && ((o.Context && String(o.Context).length) || (o.Num !== null && o.Num !== undefined) || o.Boolean === true));
        const finalsNodes = (nodesNow||[]).filter(n => (n && (n.IsError === true || (n.isFinish === true && hasUsefulOut(n)))));
        const finals = finalsNodes.map(n=>n && (n.label||n.id));
        try { if (window.LOG && window.LOG.ring) console.warn('[RING:GATE] cause=poll finals=', finals); } catch(_) {}
        // === [轮询写环处] 替换写入逻辑 ===
        if (finalsNodes.length > 0) {
          const payload = structuredClone(data.graph_data || data);
          const fp = getRingFingerprint(data);
          payload.__fingerprint = fp || null;
          payload.__ts = Date.now();

          // ⭐ 指纹未到，先跳过，避免把"同一轮"的多条临时快照塞满环
          if (!fp) {
            console.warn('[RING:SKIP] 指纹未就绪，暂不入环（等待后端提供 ringFingerprint）');
          } else {
            upsertRingByFingerprint(window.__snapshotRing, payload, fp, window.__snapshotRing?.max || 20);
            const names = finalsNodes.map(n => n.name || n.id);
            console.warn('   - 新增/覆盖节点:', names);
            console.warn('   - 环大小:', window.__snapshotRing.items.length);
          }
        }
          // 记录参与的节点摘要供后续去重参考
          try { finalsNodes.forEach(n => { window.__nodeFinalDigest[n.id] = computeNodeDigest(n); }); } catch(_) {}
          window.lastActiveSnapshot = structuredClone(payload);
      } catch (_) {}
      // 精简：不打印 ChangeDatas 后概览
      try {} catch(_){}
      
      // 刷新边状态以反映节点运行状态
      RefreshEdge();
      try {
        const btnText = document.getElementById('runButton')?.textContent;
        const nodesRef = (TempMessageNode?.nodes) || (data.graph_data?.nodes) || [];
        const runningNodes = (nodesRef || []).filter(n => n && n.IsRunning).map(n => n.label || n.id);
        const isWorkflowRunning = (btnText === '运行中...' || btnText === '接收中...' || !!currentWorkflowId || runningNodes.length > 0);
        console.warn('[WFDBG:ANIM]', {
          wfId,
          btnText,
          runningNodes,
          backendQueueLengths,
          isWorkflowRunning
        });
        // 前端当前画布的运行节点（用于确认图是否切到子workflow）
        try {
          const gNodes = (graph && graph.save && graph.save().nodes) ? graph.save().nodes : [];
          const gRunning = gNodes.filter(n => n && n.IsRunning).map(n => n.label || n.id);
          console.warn('[WFDBG:ANIM:GRAPH]', { runningInGraph: gRunning, totalGraphNodes: gNodes.length });
        } catch(_) {}
      } catch(_) {}

      // 同步后端队列长度（用于标题动画，优先 queues 回退 queue_lengths）
      (function(){
        try {
          const q = (data && typeof data === 'object') ? (data.queues || data.queue_lengths || null) : null;
          if (q) {
          // 同步一次并进行数值化
          const rawPass2 = (q.passivity !== undefined ? q.passivity : q.pending);
          const passNum2 = Number(rawPass2);
          const arrNum2  = Number(q.array);
          let pass2 = Number.isFinite(passNum2) ? passNum2 : 0;
          let arr2  = Number.isFinite(arrNum2)  ? arrNum2  : 0;
          if ((pass2 === 0 || !Number.isFinite(pass2)) && Array.isArray(window.passivityTriggerArray)) pass2 = Math.max(pass2, window.passivityTriggerArray.length|0);
          if ((arr2 === 0 || !Number.isFinite(arr2)) && Array.isArray(window.ArrayTriggerArray))     arr2  = Math.max(arr2,  window.ArrayTriggerArray.length|0);
          backendQueueLengths = { passivity: pass2, array: arr2 };
          try { console.warn('[WFDBG:QUEUE] sync after graph: P=', pass2, ' A=', arr2); } catch(_) {}
          }
        } catch(_) {}
      })();
      }
    }

    // 进度一次性打印：首次检测到“非触发器节点已完成”时，打印一次（用于确认轮询与数据写回链路正常）
    try {
      const nodesNow = (data.graph_data && Array.isArray(data.graph_data.nodes)) ? data.graph_data.nodes : [];
      const finishedNonTriggerNames = (nodesNow||[])
        .filter(n => n && n.isFinish === true && !(String(n.NodeKind||'').toLowerCase().endsWith('trigger')))
        .map(n => n.label || n.id);
      if (finishedNonTriggerNames.length && window.__RUN_PROGRESS_PRINTED__ !== true) {
        console.warn('[RUN:PROGRESS]', { status: data.status, finished: finishedNonTriggerNames });
        window.__RUN_PROGRESS_PRINTED__ = true;
      }
    } catch(_) {}

    // 状态变更打印：仅在 status 或 非触发器完成数 变化时打印一次
    try {
      const nodesNow = (data.graph_data && Array.isArray(data.graph_data.nodes)) ? data.graph_data.nodes : [];
      const finishedCount = (nodesNow||[]).filter(n => n && n.isFinish === true && !(String(n.NodeKind||'').toLowerCase().endsWith('trigger'))).length;
      const snap = { s: data.status, f: finishedCount };
      const last = window.__RUN_STATE_LAST__ || {};
      if (snap.s !== last.s || snap.f !== last.f) {
        console.warn('[RUN:STATE]', snap);
        window.__RUN_STATE_LAST__ = snap;
      }
    } catch(_) {}

    // 前端打印服务端事件（帮助在 @index.html 直接看到后端流程）
    // try {
    //   if (Array.isArray(data?.events) && data.events.length) {
    //     const recentEvents = data.events.slice(-50);
    //     recentEvents.forEach(ev => console.log('[SIDEWIN:WF]', ev));
    //   }
    // } catch (_) {}

    // 打印触发器相关列的摘要，便于一眼看清一张图上关键列
    // try { printTriggerColumnsSummary(data.graph_data); } catch (_) {}
    
    // 检查工作流终止状态（完成 / 出错 / 停止）
    // 注意：按钮文案与轮询频率已经在 updateUIFromBackendStatus 中统一处理，这里只负责提示和摘要打印
    if (data.status === 'completed' || data.status === 'error' || data.status === 'stopped') {
      // 退出预热标记（按钮文案交给 updateUIFromBackendStatus）
      window.inPreheat = false;
      
      // 显示完成/错误/停止消息
      const runButton = document.getElementById('runButton');
      if (data.status === 'completed') {
        showMessage('工作流执行完成', 'green');

        // 仅在运行完成后，打印一次本轮“所有节点存入的数据”摘要，便于检查
        try {
          if (data.graph_data && Array.isArray(data.graph_data.nodes)) {
            const nodes = data.graph_data.nodes || [];
            const colWidth = 200;
            const getCol = n => Math.round(((typeof n.x === 'number' ? n.x : 0)) / colWidth);
            const statusOf = n => (n.IsError ? 'ERR' : (n.IsRunning ? 'RUN' : (n.isFinish ? 'FIN' : 'IDLE')));
            const pickIO = io => {
              const picked = { name: io?.name, Kind: io?.Kind };
              if (Object.prototype.hasOwnProperty.call(io || {}, 'Context')) picked.Context = io.Context;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'Num')) picked.Num = io.Num;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'Boolean')) picked.Boolean = io.Boolean;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'prompt_tokens')) picked.prompt_tokens = io.prompt_tokens;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'completion_tokens')) picked.completion_tokens = io.completion_tokens;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'total_tokens')) picked.total_tokens = io.total_tokens;
              return picked;
            };
            const summary = {
              totalNodes: nodes.length,
              columnWidth: colWidth,
              nodes: nodes
                .slice()
                .sort((a,b)=> (getCol(a)-getCol(b)) || ((a.y||0)-(b.y||0)))
                .map(n => ({
                  id: n.id,
                  label: n.label,
                  NodeKind: n.NodeKind,
                  status: statusOf(n),
                  col: getCol(n),
                  SystemPrompt: n.SystemPrompt,
                  ExportPrompt: n.ExportPrompt,
                  Inputs: Array.isArray(n.Inputs) ? n.Inputs.map(pickIO) : [],
                  Outputs: Array.isArray(n.Outputs) ? n.Outputs.map(pickIO) : [],
                  debugLen: Array.isArray(n.debug) ? n.debug.length : (n.debug ? 1 : 0),
                  ErrorContext: n.ErrorContext || ''
                }))
            };
            if (window.LOG && window.LOG.summary) console.warn('[RUN:SUMMARY]', summary);
          }
        } catch (_) {}
      } else if (data.status === 'error') {
        showMessage(`工作流执行出错: ${data.error || '未知错误'}`, 'red');
        // 出错时也打印一次，便于定位
        try {
          if (data.graph_data && Array.isArray(data.graph_data.nodes)) {
            const nodes = data.graph_data.nodes || [];
            const colWidth = 200;
            const getCol = n => Math.round(((typeof n.x === 'number' ? n.x : 0)) / colWidth);
            const statusOf = n => (n.IsError ? 'ERR' : (n.IsRunning ? 'RUN' : (n.isFinish ? 'FIN' : 'IDLE')));
            const pickIO = io => {
              const picked = { name: io?.name, Kind: io?.Kind };
              if (Object.prototype.hasOwnProperty.call(io || {}, 'Context')) picked.Context = io.Context;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'Num')) picked.Num = io.Num;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'Boolean')) picked.Boolean = io.Boolean;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'prompt_tokens')) picked.prompt_tokens = io.prompt_tokens;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'completion_tokens')) picked.completion_tokens = io.completion_tokens;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'total_tokens')) picked.total_tokens = io.total_tokens;
              return picked;
            };
            const summary = {
              status: 'error',
              totalNodes: nodes.length,
              columnWidth: colWidth,
              nodes: nodes
                .slice()
                .sort((a,b)=> (getCol(a)-getCol(b)) || ((a.y||0)-(b.y||0)))
                .map(n => ({
                  id: n.id,
                  label: n.label,
                  NodeKind: n.NodeKind,
                  status: statusOf(n),
                  col: getCol(n),
                  SystemPrompt: n.SystemPrompt,
                  ExportPrompt: n.ExportPrompt,
                  Inputs: Array.isArray(n.Inputs) ? n.Inputs.map(pickIO) : [],
                  Outputs: Array.isArray(n.Outputs) ? n.Outputs.map(pickIO) : [],
                  debugLen: Array.isArray(n.debug) ? n.debug.length : (n.debug ? 1 : 0),
                  ErrorContext: n.ErrorContext || ''
                }))
            };
            if (window.LOG && window.LOG.summary) console.warn('[RUN:SUMMARY]', summary);
          }
        } catch (_) {}
      } else if (data.status === 'stopped') {
        // 主动停止时也打印一次，便于检查停止前的数据
        try {
          if (data.graph_data && Array.isArray(data.graph_data.nodes)) {
            const nodes = data.graph_data.nodes || [];
            const colWidth = 200;
            const getCol = n => Math.round(((typeof n.x === 'number' ? n.x : 0)) / colWidth);
            const statusOf = n => (n.IsError ? 'ERR' : (n.IsRunning ? 'RUN' : (n.isFinish ? 'FIN' : 'IDLE')));
            const pickIO = io => {
              const picked = { name: io?.name, Kind: io?.Kind };
              if (Object.prototype.hasOwnProperty.call(io || {}, 'Context')) picked.Context = io.Context;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'Num')) picked.Num = io.Num;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'Boolean')) picked.Boolean = io.Boolean;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'prompt_tokens')) picked.prompt_tokens = io.prompt_tokens;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'completion_tokens')) picked.completion_tokens = io.completion_tokens;
              if (Object.prototype.hasOwnProperty.call(io || {}, 'total_tokens')) picked.total_tokens = io.total_tokens;
              return picked;
            };
            const summary = {
              status: 'stopped',
              totalNodes: nodes.length,
              columnWidth: colWidth,
              nodes: nodes
                .slice()
                .sort((a,b)=> (getCol(a)-getCol(b)) || ((a.y||0)-(b.y||0)))
                .map(n => ({
                  id: n.id,
                  label: n.label,
                  NodeKind: n.NodeKind,
                  status: statusOf(n),
                  col: getCol(n),
                  SystemPrompt: n.SystemPrompt,
                  ExportPrompt: n.ExportPrompt,
                  Inputs: Array.isArray(n.Inputs) ? n.Inputs.map(pickIO) : [],
                  Outputs: Array.isArray(n.Outputs) ? n.Outputs.map(pickIO) : [],
                  debugLen: Array.isArray(n.debug) ? n.debug.length : (n.debug ? 1 : 0),
                  ErrorContext: n.ErrorContext || ''
                }))
            };
            if (window.LOG && window.LOG.summary) console.warn('[RUN:SUMMARY]', summary);
          }
        } catch (_) {}
      }
      
      // 清理工作流资源
      await fetch(`/workflow/cleanup/${currentWorkflowId}`, {
        method: 'POST'
      });
      
      currentWorkflowId = null;
      window.__RUN_STATE__ = 'idle';
      window.__RUN_SUMMARY_PRINTED__ = true;
    }

    // 兜底：如果没有运行中的节点、队列为0，且有意义数据，且存在至少一个“非触发器节点”已完成，
    // 但后端未显式返回完成/错误/停止，则打印一次摘要（仅一次，避免过早打印运行前数据）
    try {
      const nodesNow = (data.graph_data && Array.isArray(data.graph_data.nodes)) ? data.graph_data.nodes : [];
      const anyRunning = nodesNow.some(n => n && n.IsRunning === true);
      const queuesZero = (pLen === 0 && aLen === 0);
      const meaningful = hasMeaningfulDataGraph({ nodes: nodesNow });
      const hasFinishedNonTrigger = nodesNow.some(n => n && n.isFinish === true && !(String(n.NodeKind||'').toLowerCase().endsWith('trigger')));
      const serverSaysDone = (data.status === 'completed' || data.status === 'error' || data.status === 'stopped');
      if (!serverSaysDone && !anyRunning && queuesZero && meaningful && hasFinishedNonTrigger && window.__RUN_SUMMARY_PRINTED__ !== true) {
        // 生成并打印一次摘要
        const colWidth = 200;
        const getCol = n => Math.round(((typeof n.x === 'number' ? n.x : 0)) / colWidth);
        const statusOf = n => (n.IsError ? 'ERR' : (n.IsRunning ? 'RUN' : (n.isFinish ? 'FIN' : 'IDLE')));
        const pickIO = io => {
          const picked = { name: io?.name, Kind: io?.Kind };
          if (Object.prototype.hasOwnProperty.call(io || {}, 'Context')) picked.Context = io.Context;
          if (Object.prototype.hasOwnProperty.call(io || {}, 'Num')) picked.Num = io.Num;
          if (Object.prototype.hasOwnProperty.call(io || {}, 'Boolean')) picked.Boolean = io.Boolean;
          if (Object.prototype.hasOwnProperty.call(io || {}, 'prompt_tokens')) picked.prompt_tokens = io.prompt_tokens;
          if (Object.prototype.hasOwnProperty.call(io || {}, 'completion_tokens')) picked.completion_tokens = io.completion_tokens;
          if (Object.prototype.hasOwnProperty.call(io || {}, 'total_tokens')) picked.total_tokens = io.total_tokens;
          return picked;
        };
        const summary = {
          status: data.status || 'unknown',
          totalNodes: nodesNow.length,
          columnWidth: colWidth,
          nodes: nodesNow
            .slice()
            .sort((a,b)=> (getCol(a)-getCol(b)) || ((a.y||0)-(b.y||0)))
            .map(n => ({
              id: n.id,
              label: n.label,
              NodeKind: n.NodeKind,
              status: statusOf(n),
              col: getCol(n),
              SystemPrompt: n.SystemPrompt,
              ExportPrompt: n.ExportPrompt,
              Inputs: Array.isArray(n.Inputs) ? n.Inputs.map(pickIO) : [],
              Outputs: Array.isArray(n.Outputs) ? n.Outputs.map(pickIO) : [],
              debugLen: Array.isArray(n.debug) ? n.debug.length : (n.debug ? 1 : 0),
              ErrorContext: n.ErrorContext || ''
            }))
        };
        console.warn('[RUN:SUMMARY]', summary);
        // 关闭 summary 的额外快照，避免重复 push
        try { /* no-op snapshot on summary */ } catch(_) {}
        window.__RUN_SUMMARY_PRINTED__ = true;
      }
    } catch(_) {}

    // 更新文件名（不重启动画，仅更新基础标题）
    updateFileName(FileName, Callsign);
    // 立即应用一次标题，避免等待动画定时器
    applyTitleNow(window.titleBase, backendQueueLengths, window.inPreheat);
    // —— 精简汇总日志：仅在关键状态改变时打印一行 ——
    try {
      const nodesRef = (typeof TempMessageNode === 'object' && TempMessageNode && Array.isArray(TempMessageNode.nodes)) ? TempMessageNode.nodes : ((data.graph_data && Array.isArray(data.graph_data.nodes)) ? data.graph_data.nodes : []);
      const runningNames = (nodesRef||[]).filter(n => n && n.IsRunning === true).map(n => n.label || n.id);
      const finishedCount = (nodesRef||[]).filter(n => n && n.isFinish === true).length;
      const summary = {
        status: data.status,
        preheat: !!window.inPreheat,
        P: (backendQueueLengths && typeof backendQueueLengths.passivity === 'number') ? backendQueueLengths.passivity : 0,
        A: (backendQueueLengths && typeof backendQueueLengths.array === 'number') ? backendQueueLengths.array : 0,
        running: runningNames.join(','),
        finishedCount,
        title: document.title || ''
      };
      const last = window.__WF_SUMMARY_LAST || {};
      const changed = (
        summary.status !== last.status ||
        summary.preheat !== last.preheat ||
        summary.P !== last.P ||
        summary.A !== last.A ||
        summary.running !== last.running ||
        summary.finishedCount !== last.finishedCount ||
        summary.title !== last.title
      );
      if (changed) {
        // console.log(`WFSTAT status=${summary.status} preheat=${summary.preheat} P=${summary.P} A=${summary.A} running=[${summary.running}] finished=${summary.finishedCount} title='${summary.title}'`);
        window.__WF_SUMMARY_LAST = summary;
      }
    } catch(_) {}
  } catch (error) {
    console.error('轮询工作流状态失败:', error);
    showMessage(`轮询工作流状态失败: ${error.message}`, 'red');
    
    // 如果出现错误，停止轮询并重置UI
    stopAllAnimationsAndPolling();
    
    const runButton = document.getElementById('runButton');
    runButton.textContent = '运行';
    runButton.style.backgroundColor = '#4CAF50';
    currentWorkflowId = null;
  }
}

// 移除额外的标题更新定时器，避免与轮询重复重启动画

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
      acc[index] = Number.isFinite(input.Num) ? input.Num : 0;        // 默认 0
    } else if (input.Kind?.includes('String')) {
      if (input.Context == null && input.Isnecessary === true) {
        throw new Error(`节点 ${node.label} 的输入点 ${input.Id} 缺失，请检查`);
      }
      acc[index] = (input.Context ?? '').toString();                  // 默认空串
    } else if (input.Kind === 'Boolean') {
      if (input.Boolean == null && input.Isnecessary === true) {
        throw new Error(`节点 ${node.label} 的输入点 ${input.Id} 缺失，请检查`);
      }
      acc[index] = (input.Boolean === true);                          // 默认 false
    } else {
      acc[index] = null;                                              // 兜底，避免被丢
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
  // WeakMap 没有 clear 方法
  // 由于 nodeCache 是 const，我们不能重新赋值
  // 我们可以简单地不做任何事情，因为 WeakMap 会自动垃圾回收
  // 或者我们可以遍历所有已知的键并删除它们
  console.log('Node cache cleared');
}




// 重构后的 ArrayTrigger 函数
async function runArrayTriggerNodesInPassivityTriggerArray(DataTemp) { 
  let count = 0;
  console.warn('[ARRAY-DEBUG] 开始处理 ArrayTrigger 在 Passivity 中');
  
  // 识别 ArrayTrigger 节点
  let ArrayTriggernodesToProcess = DataTemp.nodes.filter(node => node.NodeKind.includes('ArrayTrigger'));
  console.warn('[ARRAY-DEBUG] 找到 ArrayTrigger 节点数量:', ArrayTriggernodesToProcess.length);
  ArrayTriggernodesToProcess.forEach((node, i) => {
    console.warn(`[ARRAY-DEBUG] ArrayTrigger[${i}]:`, node.label || node.id, 'kind=', node.NodeKind);
  });

  // 识别连接到 ArrayTrigger 节点的所有上游节点
  let ConnectArrayTriggernodesToProcessEdges = DataTemp.edges.filter(edge => 
      ArrayTriggernodesToProcess.some(node => node.id === edge.target)
  );
  let ConnectArrayTriggernodesToProcessNodes = ConnectArrayTriggernodesToProcessEdges.map(edge => 
      DataTemp.nodes.find(node => node.id === edge.source)
  );
  console.warn('[ARRAY-DEBUG] 上游节点数量:', ConnectArrayTriggernodesToProcessNodes.length);
  ConnectArrayTriggernodesToProcessNodes.forEach((node, i) => {
    console.warn(`[ARRAY-DEBUG] 上游[${i}]:`, node?.label || node?.id, 'outputs=', Array.isArray(node?.Outputs) ? node.Outputs.length : 0);
  });

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
                  // 运行中不写回 SystemPrompt，保持图上静态值
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
                  console.warn('[ARRAY-DEBUG] ArrayTrigger 节点输出数量:', result.output.length);
                  result.output.forEach((outputData, idx) => {
                      console.warn(`[ARRAY-DEBUG] 输出[${idx}]:`, outputData);
                      // 原逻辑：将完整 processedData 推到 ArrayTriggerArray
                      // 现在只推 outputData
                      
                      ArrayTriggerArray.push({
                        outputData: structuredClone(outputData),
                        nodeId: node.id
                      });
                  });
                console.warn('[ARRAY-DEBUG] ArrayTriggerArray 当前长度:', ArrayTriggerArray.length); 
              } else {
                console.warn('[ARRAY-DEBUG] ArrayTrigger 节点无输出');
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
  console.warn('[PASSIVITY-DEBUG] LoadInPassivityTriggerArray 被调用，输出数量:', data.output.length);
  
  data.output.forEach((outputData, idx) => {
    console.warn(`[PASSIVITY-DEBUG] 输出[${idx}]:`, outputData);
    
    // 将数据推入 passivityTriggerArray
      passivityTriggerArray.push({
        outputData: structuredClone(outputData),
        nodeId: triggerNode.id
      });
  });
  
  console.warn('[PASSIVITY-DEBUG] passivityTriggerArray 当前长度:', passivityTriggerArray.length);
  
  // 检查是否有 ArrayTrigger 节点，如果有则调用 loadArrayTriggerArray
  const hasArrayTrigger = graph.save().nodes.some(node => node.NodeKind.includes('ArrayTrigger'));
  if (hasArrayTrigger) {
    console.warn('[PASSIVITY-DEBUG] 发现 ArrayTrigger 节点，调用 loadArrayTriggerArray');
    loadArrayTriggerArray(data);
  }
  
  updateFileName(FileName, Callsign);
}
// 使用 passivityData 加载 ArrayTriggerArray
function loadArrayTriggerArray(passivityData) {
  // 克隆数据
  let DataTemp = structuredClone(passivityData);
  let hasArrayTrigger = DataTemp.nodes.some(node => node.NodeKind?.includes('ArrayTrigger'));
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
    } else if (output.Kind?.includes('String')) {
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
  } else if (node.Inputs[targetAnchor].Kind?.includes('String')) {
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
    // 初始化 TempMessageNode：使用合并策略，避免清空已有运行记录
    TempMessageNode = mergeGraphPreservingData(TempMessageNode, data);
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
    // 初始化 TempMessageNode：使用合并策略，避免清空已有运行记录
    TempMessageNode = mergeGraphPreservingData(TempMessageNode, DataTemp);
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
  
  // 先清理现有的标题动画
  if (window.titleInterval) {
      clearInterval(window.titleInterval);
      window.titleInterval = null;
  }
  
  // 设置基础标题
  window.titleBase = FileName;
  // 调试：记录基础标题更新
  try{ console.log(`[WFDBG] set titleBase='${window.titleBase}' inPreheat=${!!window.inPreheat}`); }catch(_){}
  
  // 直接启动动画，优先级最高
  const animation = ['🌑', '🌒', '🌓', '🌔', '🌕', '🌖', '🌗', '🌘'];
  // 动画速度设置（毫秒）- 可以调整这个值来控制快慢
  const animationSpeed = 200; // 200ms = 快，500ms = 中等，1000ms = 慢
  // 使用全局变量避免每次调用时重置
  if (typeof window.animationIndex === 'undefined') {
    window.animationIndex = 0;
  }
  
  window.titleInterval = setInterval(() => {
    const base = window.titleBase || FileName;
    const buttonText = document.getElementById('runButton')?.textContent || '';
    const buttonRunning = buttonText === '运行中...' || buttonText === '接收中...';
    
    // 详细测试打印
    console.warn('[ANIM-DEBUG] 动画检测:', {
      buttonText: `"${buttonText}"`,
      buttonRunning,
      base,
      hasTitleInterval: !!window.titleInterval,
      currentTitle: document.title
    });
    if (buttonRunning) {
      console.warn('[ANIM-DEBUG] 进入动画分支!');
      // 获取队列长度用于显示
      const passLen = (backendQueueLengths && typeof backendQueueLengths.passivity === 'number')
        ? backendQueueLengths.passivity
        : (passivityTriggerArray?.length || 0);
      const arrLen = (backendQueueLengths && typeof backendQueueLengths.array === 'number')
        ? backendQueueLengths.array
        : (ArrayTriggerArray?.length || 0);
      
      // 标题格式：文件名{被动触发}[数组触发]动画
      const newTitle = `${base}{${passLen}}[${arrLen}]${animation[window.animationIndex]}`;
      console.warn('[ANIM-DEBUG] 设置新标题:', newTitle);
      document.title = newTitle;
      window.animationIndex = (window.animationIndex + 1) % animation.length;
      
      try {
        console.warn('[TITLE-ANIM] 直接动画运行:', {
          newTitle,
          buttonText,
          animationIndex: window.animationIndex,
          animationChar: animation[window.animationIndex]
        });
      } catch(_) {}
    } else {
      document.title = base;
    }
  }, animationSpeed);
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
  
  if (MemoryIndex < 0 || JSON.stringify(TempData) !== JSON.stringify(SaveGraph[MemoryIndex])) {
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
  // 调试：将关键节点的输入输出打印出来，便于阅读
  try {
    const keyNodes = (data.nodes||[]).slice(0, 10);
    keyNodes.forEach(n=>{
      const ins = (n.Inputs||[]).map(i=>({name:i.name,Kind:i.Kind,Link:i.Link,Context:i.Context,Num:i.Num,Boolean:i.Boolean}));
      const outs= (n.Outputs||[]).map(o=>({name:o.name,Kind:o.Kind,Link:o.Link,Context:o.Context,Num:o.Num,Boolean:o.Boolean}));
      console.log(`[WFDBG:NODE] ${n.label||n.id} kind=${n.NodeKind} running=${!!n.IsRunning} finish=${!!n.isFinish}`);
      console.log('  Inputs:', ins);
      console.log('  Outputs:', outs);
    });
  } catch(_){}
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
  const btn = document.getElementById('runButton');
  if (!btn) return;

  const currentText = btn.textContent;

  // === 停止：按钮显示“运行中...”或“接收中...”时，仅向后端发送 stop 指令，UI 交给轮询更新 ===
  if ((currentText === '运行中...' || currentText === '接收中...') && (currentWorkflowId || monitoredWorkflowId)) {
    const wfId = currentWorkflowId || monitoredWorkflowId;
    console.log('🛑 [STOP] 用户点击停止按钮，workflowId =', wfId);

    stopWorkflowAndChildren(wfId)
      .then(() => showMessage('工作流已停止并清理', '#00d4ff'))
      .catch(error => showMessage(`停止/清理工作流失败: ${error.message}`, 'red'))
      .finally(() => {
        stopAllAnimationsAndPolling();
        currentWorkflowId = null;
        monitoredWorkflowId = null;
        currentObservedWorkflowId = null;
        // 停止后仍保持选择器可见，便于切换监控其他工作流
        setWorkflowPollingInterval(0);
        // 解锁前端节点，恢复可编辑
        unlockGraphBlocks();
        updateWorkflowSelector();
        const runBtn = document.getElementById('runButton');
        if (runBtn) {
          runBtn.textContent = '运行';
          runBtn.style.backgroundColor = '#1e1e1e';
        }
      });
    return;
  }

  // === 恢复：预留“已暂停”状态时的恢复逻辑 ===
  if (currentText === '已暂停') {
    const wfId = currentWorkflowId || monitoredWorkflowId;
    if (!wfId) {
      showMessage('没有可恢复的工作流', '#ff9100');
      return;
    }
    console.log('▶️ [RESUME] 用户点击恢复按钮，workflowId =', wfId);
    fetch(`/workflow/resume/${wfId}`, { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          showMessage(`恢复工作流失败: ${data.error}`, 'orange');
        } else {
          showMessage('工作流已恢复', 'green');
        }
      })
      .catch(error => {
        showMessage(`恢复工作流失败: ${error.message}`, 'red');
      });
    return;
  }

  // === 退出 monitor_completed 模式：当处于完成状态时，点击按钮退出到编辑模式 ===
  if (frontendMode === 'monitor_completed' && currentText === '运行完成') {
    console.log('[MODE]🔄  退出 monitor_completed 模式，返回 edit 模式');
    frontendMode = 'edit';
    prevFrontendMode = 'monitor_completed';
    
    // 清理工作流ID和记录的状态
    if (currentWorkflowId) {
      fetch(`/workflow/cleanup/${currentWorkflowId}`, { method: 'POST' })
        .catch(error => console.warn('清理工作流失败:', error));
      currentWorkflowId = null;
    }
    monitoredWorkflowId = null;
    
    // 清理记录的状态
    if (window.__lastWorkflowStatus) {
      delete window.__lastWorkflowStatus;
    }
    if (window.__lastWorkflowProjectName) {
      delete window.__lastWorkflowProjectName;
    }
    if (window.__lastWorkflowId) {
      delete window.__lastWorkflowId;
    }
    if (window.__lastCompletedGraphData) {
      delete window.__lastCompletedGraphData;
    }
    
    // 恢复编辑模式：设置所有组件的IsBlock=false
    if (typeof graph !== 'undefined' && graph) {
      try {
        const graphData = graph.save();
        if (graphData && graphData.nodes) {
          graphData.nodes.forEach(nodez => {
            nodez.IsBlock = false;
          });
          ChangeDatas(graphData);
        }
      } catch (e) {
        console.warn('设置IsBlock失败:', e);
      }
    }
    
    // 更新按钮和UI
    const btn = document.getElementById('runButton');
    const infoEl = document.getElementById('currentWorkflowInfo');
    if (btn) {
      btn.textContent = '运行';
      btn.style.backgroundColor = '#1e1e1e';
    }
    if (infoEl) {
      infoEl.textContent = '当前工作流：无';
    }
    
    // 停止所有轮询和动画
    stopAllAnimationsAndPolling();
    resetWorkflowTracking();
    hideWorkflowSelector();
    return;
  }

  // === 启动：按钮显示"运行"时，进行校验并向后端发送 start 指令 ===
  if (currentText === '运行')
  {
    // 新一轮运行前重置一次性打印标记，确保每次都能触发汇总/快照
    try {
      window.__RUN_SUMMARY_PRINTED__ = false;
      window.__RUN_PROGRESS_PRINTED__ = false;
    } catch(_) {}
    // —— DEBUG：跑新一轮前打印一下旧队列长度 —— 
    console.warn('[DEBUG] 运行前 passivityTriggerArray 长度：', passivityTriggerArray.length);
    console.warn('[DEBUG] 运行前 ArrayTriggerArray 长度：', ArrayTriggerArray.length);

    // —— 清空上一轮残留的触发队列 —— 
    passivityTriggerArray = [];
    ArrayTriggerArray     = [];

    // —— DEBUG：清空后确认 —— 
    console.warn('[DEBUG] 运行后 passivityTriggerArray 长度：', passivityTriggerArray.length);
    console.warn('[DEBUG] 运行后 ArrayTriggerArray 长度：', ArrayTriggerArray.length);

    IsTriggerNode = false;
    TempNodeArray = [];
    IsFirstRunArrayTrigger = true;
    const { nodes, edges } = graph.save();
    try { if (window.MERGE_DEBUG !== false) console.warn('[MERGE:INIT] seed TempMessageNode with graph.save() (merge, not overwrite)'); } catch(_) {}
    TempMessageNode = mergeGraphStateAware(TempMessageNode, graph.save());
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
    // 记录当前图是否包含被动触发节点（预热检测用，具体文案交给轮询处理）
    window.currentHasPassivityTrigger = nodes.some(n => n.NodeKind?.includes('passivityTrigger'));
    
    let DataTemp=graph.save();
    DataTemp.nodes.forEach(nodez => {
      nodez.IsBlock = true;
      nodez.IsRunning = false;
      nodez.IsError = false;
      nodez.isFinish = false;
      nodez.IsStartNode = false;
      nodez.firstRun = true;
      nodez.inputStatus = Array(nodez.Inputs?.length || 0).fill(false);
      // 清空旧的输出/调试，避免历史输出混入新一轮全局运行
      if (Array.isArray(nodez.Outputs)) {
        nodez.Outputs.forEach(o => {
          if (!o) return;
          if ('Context' in o) o.Context = '';
          if ('Num' in o) o.Num = null;
          if ('Boolean' in o) o.Boolean = false;
          ['prompt_tokens','completion_tokens','total_tokens'].forEach(k => { if (k in o) delete o[k]; });
        });
      }
      if ('debug' in nodez) nodez.debug = '';
    });
    
    // 验证连接
    const { nodes: validNodes, edges: validEdges } = validateConnections(nodes, graph.save().edges);
    
    // 检查循环
    const cycleInfo = detectCycles(validNodes, validEdges);
    if (cycleInfo!=null) {
      showMessage('检测到循环依赖，请检查连接。', 'red');
      document.getElementById('runButton').textContent = '运行';
      document.getElementById('runButton').style.backgroundColor = '#1e1e1e';
      return;
    }
    
    // 清理缓存
    clearNodeCache();
    
    // 使用后端工作流引擎
    if (IsTriggerNode || true) { // 总是使用后端工作流引擎
      
      // ★ 修复：在启动新工作流前，确保清理任何已存在的工作流状态
      stopAllAnimationsAndPolling();
      if (window._wfEventsPrinted) window._wfEventsPrinted = {};
      const cleanupPromise = currentWorkflowId ? 
        fetch(`/workflow/cleanup/${currentWorkflowId}`, { method: 'POST' })
          .then(() => console.log(`[测试】已清理工作流: ${currentWorkflowId}`))
          .catch(error => console.warn('[测试】清理旧工作流失败:', error)) :
        Promise.resolve();
      
      // ★ 修复：停止任何正在运行的轮询
      if (workflowStatusInterval) {
        clearInterval(workflowStatusInterval);
        workflowStatusInterval = null;
      }
      
      cleanupPromise.then(() => {
        currentWorkflowId = null;
        monitoredWorkflowId = null;
        // 启动前：若存在 passivityTrigger 且暂时无队列，进入预热，否则保持 false
        window.inPreheat = !!window.currentHasPassivityTrigger && (passivityTriggerArray.length === 0) && (ArrayTriggerArray.length === 0);
        
        // ★ 修复：生成唯一且可预测的workflow_id（基于时间戳 + 随机）
        const newWorkflowId = `workflow_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        console.log(`[DEBUG] Generated new workflow ID: ${newWorkflowId}`);
        console.log(`[DEBUG] passivityTriggerArray:`, passivityTriggerArray);
        console.log(`[DEBUG] ArrayTriggerArray:`, ArrayTriggerArray);
        console.log(`[DEBUG] DataTemp nodes count:`, DataTemp.nodes.length);
        
        // 启动工作流
        return fetch('/workflow/start', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            workflow_id: newWorkflowId,  // ★ 修复：明确传递 workflow_id
            graph_data: DataTemp,
            passivity_trigger_array: passivityTriggerArray,
            array_trigger_array: ArrayTriggerArray
          })
        });
      })
      .then(response => {
        console.log(`[DEBUG] Start workflow response status: ${response.status}`);
        return response.json();
      })
      .then(data => {
        if (data.error) {
          showMessage(`启动工作流失败: ${data.error}`, 'red');
          document.getElementById('runButton').textContent = '运行';
          document.getElementById('runButton').style.backgroundColor = '#1e1e1e';
          return;
        }
        
        currentWorkflowId = data.workflow_id;
        monitoredWorkflowId = data.workflow_id;
        currentObservedWorkflowId = data.workflow_id; // 设置当前观察的工作流
        frontendMode = 'edit'; // 本页启动的工作流，视为 edit 模式
        console.log(`🚀 [FRONTEND] 工作流已启动: ${currentWorkflowId}`);
        
        // ★ 立即同步一次 workflow 状态 UI（显示当前运行的工作流名称）
        syncRunButtonWithBackend();
        
        // 开始高频轮询工作流状态（300ms）
        setWorkflowPollingInterval(300);
            
            // 额外的快速动画刷新，确保即使后端运行很快也能看到动画
            const fastAnimationInterval = setInterval(() => {
                if (!currentWorkflowId) {
                    clearInterval(fastAnimationInterval);
                    return;
                }
                RefreshEdge(); // 每100ms强制刷新一次边动画
            }, 100);
            
            // 保存interval ID以便清理
            window.fastAnimationInterval = fastAnimationInterval;
        
        // 触发运行
        IsTriggerNode = true;
        IsRunningFunction = false; // 前端不再负责运行
      })
      .catch(error => {
        showMessage(`启动工作流失败: ${error.message}`, 'red');
        const btn = document.getElementById('runButton');
        if (btn) {
          btn.textContent = '运行';
          btn.style.backgroundColor = '#1e1e1e';
        }
      });
    } else {
      // 保留原有逻辑作为备选，但实际不会执行到这里
      IsRunningFunction=true;
      runAllNodes(DataTemp, nodes, edges);
    }
    }
  else if(document.getElementById('runButton').textContent == '返回编辑模式' || document.getElementById('runButton').textContent == '运行中...'|| document.getElementById('runButton').textContent == '运行完成' || document.getElementById('runButton').textContent == '接收中...')
    {
      document.getElementById('runButton').textContent = '运行';
    document.getElementById('runButton').style.backgroundColor = '#1e1e1e';
    
      let DataTemp=graph.save();
      DataTemp.nodes.forEach(nodez => {
        nodez.IsBlock = false;
        let Tempnode=TempMessageNode.nodes.find(node => node.id === nodez.id);
        nodez.Inputs=Tempnode.Inputs;
      })
      ChangeDatas(DataTemp);
      
    // 如果有活跃的工作流，清理它
    if (currentWorkflowId) {
      fetch(`/workflow/cleanup/${currentWorkflowId}`, {
        method: 'POST'
      });
      
      currentWorkflowId = null;
    }
    
    // 统一清理所有动画和轮询
    stopAllAnimationsAndPolling();
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
  // 运行前从图数据获取 node 的最新 Prompt（保留占位符）
  try {
    const g = graph.save();
    const nn = (g && Array.isArray(g.nodes)) ? g.nodes.find(n => n.id === node.id) : null;
    if (nn) {
      node.SystemPrompt = nn.SystemPrompt || '';
      node.prompt = nn.prompt || '';
    }
  } catch(_) {}
  const [systemPrompt, exportPrompt] = processLLmPrompt(node);
  // 运行中不写回 SystemPrompt，保持图上静态值
  // TempMessageNode/导出都使用原始 prompt（用于侧窗即时查看）
  node.ExportPrompt = (typeof node.prompt === 'string' ? node.prompt : exportPrompt);
  
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
  console.log('[SIDEWIN:TEMP] executeNode start:', node.id);
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
    // TempMessageNode 预写：ExportPrompt 用原始 prompt
    node.ExportPrompt  = (typeof node.prompt === 'string' ? node.prompt : expPrompt);
  }

  /* ---------------- 执行前：写入 TempMessageNode（Inputs/Prompt/状态/清空上一轮输出） ---------------- */
  try {
    const preT = TempMessageNode.nodes.find(n => n.id === node.id);
    try {
      console.log('executeNode: pre-run BEFORE', node.id, {
        inputs: preT?.Inputs?.length,
        outputs: preT?.Outputs?.length,
        debugLen: typeof preT?.debug === 'string' ? preT.debug.length : 0,
        sysPromptLen: (node.SystemPrompt||'').length,
        promptLen: (node.ExportPrompt||'').length
      });
    } catch(_) {}
    if (preT) {
      // 覆盖 Inputs（以当前 node.Inputs 为准）
      preT.Inputs = structuredClone(node.Inputs || []);
      // Prompt 信息（包含 SystemPrompt 与 UserPrompt/ExportPrompt）
      if (typeof node.SystemPrompt !== 'undefined') preT.SystemPrompt = node.SystemPrompt;
      if (typeof node.prompt === 'string') preT.ExportPrompt = node.prompt; else if (typeof node.ExportPrompt !== 'undefined') preT.ExportPrompt = node.ExportPrompt;
      if (typeof node.ExprotAfterPrompt !== 'undefined') preT.ExprotAfterPrompt = node.ExprotAfterPrompt;
      // 状态位：准备运行
      preT.IsRunning = true;
      preT.isFinish  = false;
      preT.IsError   = false;
      preT.ErrorContext = '';
      // 清空上一轮输出与 token
      if (Array.isArray(preT.Outputs)) {
        preT.Outputs.forEach(o => {
          if (!o) return;
          if ('Context' in o) o.Context = '';
          if ('Num' in o) o.Num = null;
          if ('Boolean' in o) o.Boolean = false;
          if ('prompt_tokens' in o) o.prompt_tokens = undefined;
          if ('completion_tokens' in o) o.completion_tokens = undefined;
          if ('total_tokens' in o) o.total_tokens = undefined;
        });
      }
      try {
        console.log('executeNode: pre-run AFTER', node.id, {
          inputs: preT?.Inputs?.length,
          outputs: preT?.Outputs?.length,
          sysPromptLen: (preT.SystemPrompt||'').length,
          promptLen: (preT.ExportPrompt||'').length
        });
      } catch(_) {}
    }
    // 移除预运行快照入环，避免污染历史（仅在完成/报错时入环）
  } catch(err) { console.warn('预写 TempMessageNode 失败:', err); }

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
        try {
          const t0 = data && data.output && data.output[0];
          console.log('executeNode: run-node OK', node.id, {
            outputs: Array.isArray(data?.output) ? data.output.length : 0,
            t0Preview: t0 && typeof t0.Context === 'string' ? t0.Context.slice(0, 80) : undefined
          });
        } catch(_) {}
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
      // debug：本次无 debug 则清空（避免残留上一次错误）
      try {
        // 兼容 debug/debug_text 两种字段名
        const d = (data && data.debug !== undefined) ? data.debug : (data ? data.debug_text : undefined);
        sourceTempNode.debug = (d === undefined || d === null || d === '') ? '' : ((typeof d === 'string') ? d : JSON.stringify(d, null, 2));
      } catch (_) {
        sourceTempNode.debug = '';
      }
      // 成功时清理错误上下文
      sourceTempNode.ErrorContext = '';
      sourceTempNode.IsError = false;

      // 第一条输出携带 token 统计
      if (data.output[0]) {
        ['prompt_tokens', 'completion_tokens', 'total_tokens'].forEach(k => {
          sourceTempNode.Outputs[0][k] = data.output[0][k];
        });
      }
      try {
        const tok = sourceTempNode?.Outputs && sourceTempNode.Outputs[0];
        console.log('executeNode: post-run WRITE', node.id, {
          outputs: Array.isArray(sourceTempNode?.Outputs) ? sourceTempNode.Outputs.length : 0,
          debugLen: typeof sourceTempNode?.debug === 'string' ? sourceTempNode.debug.length : 0,
          tokens: tok ? {
            prompt_tokens: tok.prompt_tokens,
            completion_tokens: tok.completion_tokens,
            total_tokens: tok.total_tokens
          } : undefined
        });
        // 标记完成态，供快照环筛选
        sourceTempNode.isFinish = true;
        sourceTempNode.IsError = false;
        sourceTempNode.IsRunning = false;
      } catch(_) {}
      addHistory(sourceTempNode);
      // 执行后：依据有效输出/调试信息入快照环
      try { 
        const origWarn = window.__ORIG_CONSOLE__?.warn || console.warn;
        origWarn('🔍 [RING:SINGLE] 单节点运行入环:', node.id, node.label);
        snapshotTempMessageNodes(node.id); 
      } catch(_) {}

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
            // 为下游 LLM，从图数据取最新 prompt（保留占位符）
            try {
              const g2 = graph.save();
              const nn2 = (g2 && Array.isArray(g2.nodes)) ? g2.nodes.find(n => n.id === targetNode.id) : null;
              if (nn2) {
                targetNode.SystemPrompt = nn2.SystemPrompt || '';
                targetNode.prompt = nn2.prompt || '';
              }
            } catch(_) {}
            const [sys, exp] = processLLmPrompt(targetNode);
            targetNode.SystemPrompt = sys;
            targetNode.ExportPrompt = (typeof targetNode.prompt === 'string' ? targetNode.prompt : exp);
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
  // 预热阶段：仅当仍满足预热规则时才跳过刷新
  const stillPreheat = !!window.inPreheat && !!window.currentHasPassivityTrigger && !!currentWorkflowId;
  console.warn('RefreshEdge: window.inPreheat', window.inPreheat, 'stillPreheat', stillPreheat);
  if (stillPreheat) {
    return;
  }
  (graph.getEdges?.() || []).forEach((e, i) => {
    const sh  = e.getKeyShape?.();
    const off = sh?.attr ? sh.attr('lineDashOffset') : undefined;
    const st  = e.getStates ? e.getStates() : [];
    console.warn('[EDGE123]', i, e.getID?.(), 'type=', e.getModel()?.type, 'states=', st, 'lineDashOffset=', off);
  });
  /* === 1. 取图数据并清零 === */
  const { nodes, edges } = graph.save();
  console.warn('RefreshEdge: nodes', nodes);
  console.warn('RefreshEdge: edges', edges);
  // 运行状态统计
  const runningCount = (TempMessageNode?.nodes || nodes).filter(n => n.IsRunning).length;

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
  const buttonRunning = document.getElementById('runButton').textContent === '运行中...';
  const workflowActive = !!currentWorkflowId;
  const nodesRunning = (TempMessageNode?.nodes || nodes).some(n => n.IsRunning);
  
  // 更全面的运行状态检测
  const isWorkflowRunning = buttonRunning || workflowActive || nodesRunning;
  
  if (isWorkflowRunning) {
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

    /* 5‑2. 再对运行中节点连线高亮 - 使用最新的状态数据 */
    // 优先使用 TempMessageNode 的实时状态数据（如果存在）
    const realTimeNodes = TempMessageNode?.nodes || nodes;
    
    let hasRunningNodes = false;
    
    realTimeNodes.forEach(n => {
      if (!n.IsRunning) return;
      hasRunningNodes = true;
      
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
    
    // 记录运行状态变化
    window.lastHasRunningNodes = hasRunningNodes;
    
    // 如果没有运行中的节点但工作流仍在进行，添加全局脉冲效果
    if (!hasRunningNodes && isWorkflowRunning) {
      // 对所有边添加微弱的脉冲效果表示系统活跃
      validEdges.forEach(e => {
        const ed = graph.findById(e.id);
        if (!ed) return;
        
        // 随机选择一些边进行轻微高亮，模拟数据流动
        if (Math.random() < 0.3) { // 30%的边会高亮
          ed.setState('linked', true);
          ed.setState('linkBlue', true);
          
          // 200ms后取消高亮，形成闪烁效果
          setTimeout(() => {
            if (ed && ed.setState) {
              ed.setState('linked', false);
              ed.setState('linkBlue', false);
            }
          }, 200);
        }
      });
    }
  }
}

// ==================== 工作流选择器相关函数 ====================
async function updateWorkflowSelector() {
  // 更新工作流选择器选项
  try {
    const res = await fetch('/workflow/list');
    if (!res.ok) return;
    
    const data = await res.json();
    // 优先将父工作流排在前面（is_child=false），避免自动选到子工作流
    const workflows = (data.workflows || []).slice().sort((a, b) => {
      const pa = a?.is_child ? 1 : 0;
      const pb = b?.is_child ? 1 : 0;
      if (pa !== pb) return pa - pb; // 父优先
      return 0;
    });
    
    if (!workflowSelectElement) return;
    
    // 清空现有选项
    workflowSelectElement.innerHTML = '';
    
    // 添加占位符
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = workflows.length ? '选择工作流...' : '暂无运行中的工作流';
    placeholder.disabled = true;
    if (!currentObservedWorkflowId) {
      placeholder.selected = true;
    }
    workflowSelectElement.appendChild(placeholder);
    
    // 添加工作流选项
    workflows.forEach(wf => {
      const option = document.createElement('option');
      option.value = wf.id;
      const rawName = wf.project_name || wf.id;
      const displayName = rawName.replace(/\.json$/i, '');
      // 状态显示优化
      let statusText = wf.status;
      if (statusText === 'running') statusText = '运行中';
      else if (statusText === 'paused') statusText = '已暂停';
      else if (statusText === 'completed') statusText = '已完成';
      else if (statusText === 'error') statusText = '错误';
      else if (statusText === 'stopped') statusText = '已停止';

      // 子工作流使用简化的三态文案与颜色
      const childStatusInfo = (() => {
        if (!wf.is_child) return null;
        const st = (wf.status || '').toLowerCase();
        if (st === 'running') return { text: '运行中', color: '#1e90ff', prefix: '🔵', suffix: '🔄' };
        if (st === 'completed') return { text: '运行完成', color: '#16a34a', prefix: '✅' };
        return { text: '待运行', color: '#f97316', prefix: '🟠' };
      })();

      const childText = formatChildSummaryText(wf.child_summary);
      const childMark = wf.is_child ? ' [子工作流]' : '';
      if (childStatusInfo) {
        const prefix = childStatusInfo.prefix ? `${childStatusInfo.prefix} ` : '';
        const suffix = childStatusInfo.suffix ? ` ${childStatusInfo.suffix}` : '';
        option.textContent = `${prefix}${displayName}${childMark} (${childStatusInfo.text})${childText}${suffix}`;
        option.style.color = childStatusInfo.color;
      } else {
        option.textContent = `${displayName}${childMark} (${statusText})${childText}`;
      }
      if (wf.id === currentObservedWorkflowId) {
        option.selected = true;
      }
      workflowSelectElement.appendChild(option);
    });
    
    // 显示/隐藏选择器 —— 只要有工作流就显示，方便随时切换
    const shouldShowSelector = workflows.length > 0;
    if (shouldShowSelector) {
      // 强制显示选择器
      workflowSelectElement.style.display = 'inline-flex';
      workflowSelectElement.style.visibility = 'visible';
      workflowSelectElement.style.opacity = '1';
      workflowSelectElement.removeAttribute('hidden');
      console.warn(`[WORKFLOW-SELECTOR] 显示选择器，共 ${workflows.length} 个工作流:`, workflows.map(w => `${w.id}(${w.status})`));
      console.warn(`[WORKFLOW-SELECTOR] 选择器元素:`, workflowSelectElement);
      console.warn(`[WORKFLOW-SELECTOR] 选择器样式:`, window.getComputedStyle(workflowSelectElement).display);
    } else {
      hideWorkflowSelector();
      console.log('[WORKFLOW-SELECTOR] 隐藏选择器（非监控模式或无工作流）');
    }
    
    // 如果有工作流但没有选中，默认选中“父”工作流优先（仅监控模式）
    if (workflows.length > 0 && !currentObservedWorkflowId && shouldShowSelector) {
      const runningParents = workflows.filter(wf => wf.status === 'running' && !wf.is_child);
      const runningAny = workflows.filter(wf => wf.status === 'running');
      const candidate =
        (runningParents.length && runningParents[0]) ||
        (runningAny.length && runningAny[0]) ||
        workflows[0];
      if (candidate) {
        currentObservedWorkflowId = candidate.id;
        monitoredWorkflowId = candidate.id;
        workflowSelectElement.value = candidate.id;
        console.warn(`[WORKFLOW-SELECTOR] 自动选中工作流: ${candidate.id}（父优先）`);
      }
    }
    
    // 确保当前选中的工作流在选择器中正确显示
    if (currentObservedWorkflowId && workflowSelectElement.value !== currentObservedWorkflowId) {
      workflowSelectElement.value = currentObservedWorkflowId;
      console.warn(`[WORKFLOW-SELECTOR] 同步选择器值为当前观察的工作流: ${currentObservedWorkflowId}`);
    }
  } catch (e) {
    console.warn('[WORKFLOW-SELECTOR] 更新工作流列表失败:', e);
  }
}

function switchToWorkflow(workflowId) {
  // 切换到指定工作流
  if (!workflowId) {
    console.warn('[WORKFLOW-SELECTOR] 切换失败：workflowId 为空');
    return;
  }
  
  console.warn(`[WORKFLOW-SELECTOR] 开始切换到工作流: ${workflowId}`);
  
  // 更新观察的工作流ID
  const oldWfId = currentObservedWorkflowId;
  currentObservedWorkflowId = workflowId;
  monitoredWorkflowId = workflowId;
  
  // 更新选择器显示
  if (workflowSelectElement) {
    workflowSelectElement.value = workflowId;
    console.warn(`[WORKFLOW-SELECTOR] 选择器值已更新为: ${workflowId}`);
  } else {
    console.warn('[WORKFLOW-SELECTOR] 选择器元素不存在');
  }
  
  // 如果切换了工作流，清空之前的图数据，避免显示错误的数据
  if (oldWfId && oldWfId !== workflowId) {
    console.warn(`[WORKFLOW-SELECTOR] 切换工作流，清空之前的图数据`);
    // 不立即清空，让轮询获取新数据后再更新
    try {
      // 切换时重置侧窗/快照相关缓存，避免显示上一条 workflow 的快照
      window.__snapshotRing = { items: [], max: (window.__snapshotRing && window.__snapshotRing.max) || 20 };
      window.lastActiveSnapshot = null;
      window.__nodeFinalDigest = {};
      window.__lastCompletedGraphData = null;
      window.__shouldSaveCompletedGraph = false;
      window.__sidewinSelectedGraphs = {};
      window.__currentSideWindowNode = null;
      window.__currentSideWindowIsCheckMode = false;
      console.warn('[WORKFLOW-SELECTOR] 已重置本地快照/侧窗缓存');
    } catch (_) {}
  }
  
  // 立即触发一次状态轮询，使用新的工作流ID
  console.warn(`[WORKFLOW-SELECTOR] 触发状态轮询，观察工作流: ${workflowId}`);
  // 使用 setTimeout 确保选择器值已更新
  setTimeout(() => {
    pollWorkflowStatus();
  }, 100);
}

// 停止指定工作流及其子工作流
async function stopWorkflowAndChildren(targetWorkflowId) {
  try {
    const listRes = await fetch('/workflow/list');
    if (!listRes.ok) throw new Error(`list http ${listRes.status}`);
    const listData = await listRes.json();
    const workflows = listData.workflows || [];
    const targets = workflows
      .filter(wf => wf.status === 'running' && (wf.id === targetWorkflowId || wf.parent_id === targetWorkflowId))
      .map(wf => wf.id);
    if (!targets.includes(targetWorkflowId)) targets.push(targetWorkflowId);
    console.warn('[STOP] 计划停止工作流集合:', targets);
    for (const wid of targets) {
      try { await fetch(`/workflow/stop/${wid}`, { method: 'POST' }); } catch (e) { console.warn('[STOP] stop failed', wid, e); }
      try { await fetch(`/workflow/cleanup/${wid}`, { method: 'POST' }); } catch (e) { console.warn('[STOP] cleanup failed', wid, e); }
    }
  } catch (err) {
    console.warn('[STOP] stopWorkflowAndChildren error:', err);
  }
}

// ==================== 与后端 Workflow 状态同步运行按钮 + 当前工作流信息 ====================
async function syncRunButtonWithBackend() {
  try {
    // 先更新工作流选择器
    await updateWorkflowSelector();
    
    const res = await fetch('/workflow/status/current');
    if (!res.ok) return;

    const data = await res.json();
    console.log('[SYNC] /workflow/status/current =>', data);

    const status   = data.status || 'idle';
    const wfId     = data.workflow_id || null;

    // 如果当前观察的工作流已完成，自动切换到下一个运行中的工作流
    if (currentObservedWorkflowId && (status === 'completed' || status === 'stopped' || status === 'error')) {
      // 获取所有运行中的工作流
      const listRes = await fetch('/workflow/list');
      if (listRes.ok) {
        const listData = await listRes.json();
        const runningWorkflows = (listData.workflows || []).filter(wf => 
          wf.status === 'running' && wf.id !== currentObservedWorkflowId
        );
        if (runningWorkflows.length > 0) {
          // 切换到第一个运行中的工作流
          switchToWorkflow(runningWorkflows[0].id);
          return;
        }
      }
      // 没有其他运行中的工作流，清空观察
      currentObservedWorkflowId = null;
    }
    
    // 如果没有当前观察的工作流，使用后端返回的工作流
    if (!currentObservedWorkflowId && wfId) {
      currentObservedWorkflowId = wfId;
    }

    // 更新当前监控的 workflowId（优先使用观察的工作流）
    monitoredWorkflowId = currentObservedWorkflowId || wfId || null;

    // 根据后端状态统一更新 UI（按钮 + 当前工作流信息 + 轮询频率）
    updateUIFromBackendStatus({
      status,
      workflow_id: monitoredWorkflowId,
      project_name: data.project_name,
      graph_project_name: data.graph_project_name
    });

    // 根据当前工作流归属更新前端模式
    if (monitoredWorkflowId && status!='stopped') {
      frontendMode = (currentWorkflowId && currentWorkflowId === monitoredWorkflowId) ? 'edit' : 'monitor';
    } else {
      frontendMode = 'edit';
    }
  } catch (e) {
    console.warn('[SYNC] 获取 /workflow/status/current 失败:', e);
  }
}

// 页面初始化后，同步一次按钮状态，并启动低频轮询（发现后端已有工作流时会自动切到高频）
try {
  syncRunButtonWithBackend();
  // 初始情况下先以低频方式轮询，以便发现由其他页面/Control Room 启动的工作流
  setWorkflowPollingInterval(2000);
} catch (_) {}
function addHistory(data) { // 
  let Temp;
  if(data!='Start')
  {
    // 过滤后的对象只保留 name、Kind，以及根据 Kind 值选择 Context, Boolean 或 Num
    let filteredData = {
      NodeKind: data.NodeKind,
      label: data.label,
      // 添加重要的运行数据到历史记录
      ExportPrompt: data.ExportPrompt || '',
      SystemPrompt: data.SystemPrompt || '',
      ExprotAfterPrompt: data.ExprotAfterPrompt || '',
      debug: data.debug || '',
      status: data.status || '',
      isFinish: data.isFinish || false,
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
      'Inputs', 'Outputs', 'JsonOutputs',
      'SystemPrompt', 'prompt', 'ExportPrompt', 'ExprotAfterPrompt',
      'max_tokens', 'temperature', 'Top_p',
      'OriginalTextSelector','OriginalTextArray','OriginalTextName',
      'frequency_penalty', 'presence_penalty',
      'ReTryNum', 'mcpServers','ReactNum',
      'IsReact','Tools','Memory'
    ]);
  } else if (kind.includes('arraytrigger')) {
    return pick(node, [
      ...base, 'NodeKind', 'Inputs', 'OriginalTextArray',
      'Outputs', 'RecursionBehavior', 'ReTryNum', 'ParallelLimit'
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

    /* ①.5 为 ArrayTrigger 节点设置默认的 ParallelLimit */
    if (node.NodeKind && node.NodeKind.includes('ArrayTrigger')) {
      if (node.ParallelLimit === undefined || node.ParallelLimit === null) {
        node.ParallelLimit = 1;
      }
    }

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

// ==================== 设置菜单功能 ====================
let secretsConfigWorkflow = { secrets: [], llmMappings: {} };
let llmNodesWorkflow = [];
let selectedSecretIndexWorkflow = -1;
let settingsTabsInitializedWorkflow = false;

document.addEventListener('DOMContentLoaded', () => {
  const settingsBtn = document.getElementById('settingsBtnWorkflow');
  if (settingsBtn) {
    settingsBtn.addEventListener('click', () => {
      initSettingsMenuWorkflow();
    });
  }
});

function initSettingsMenuWorkflow() {
  // 创建模态框
  let modal = document.getElementById('settingsModalWorkflow');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'settingsModalWorkflow';
    modal.className = 'settings-modal';
    modal.innerHTML = `
      <div class="settings-modal-content">
        <div class="settings-header">
          <div class="settings-header-left">
            <button class="settings-btn-add" id="settingsAddBtnWorkflow" title="添加">
              <i class="fas fa-plus"></i>
            </button>
            <button class="settings-btn-delete" id="settingsDeleteBtnWorkflow" title="删除">
              <i class="fas fa-minus"></i>
            </button>
          </div>
          <button class="settings-btn-close" id="settingsCloseBtnWorkflow">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="settings-body">
          <div class="settings-sidebar">
            <div class="settings-menu-item active" data-section="secrets">
              <i class="fas fa-key"></i>
              <span>密钥</span>
            </div>
            <div class="settings-menu-item" data-section="llm-key">
              <i class="fas fa-code-branch"></i>
              <span>LLM Key</span>
            </div>
          </div>
          <div class="settings-content">
            <div id="secretsSectionWorkflow" class="settings-section">
              <h3>密钥管理</h3>
              <div id="secretsListWorkflow" class="secrets-list">
                <!-- 密钥列表将动态插入这里 -->
              </div>
            </div>
            <div id="llmKeySectionWorkflow" class="settings-section" style="display:none;">
              <h3>LLM 密钥分配</h3>
              <div class="llm-key-list" id="llmKeyListWorkflow">
                <!-- LLM 分配列表 -->
              </div>
            </div>
          </div>
        </div>
        <div class="settings-footer">
          <button class="btn btn-apply" id="settingsApplyBtnWorkflow">应用</button>
          <button class="btn btn-cancel" id="settingsCancelBtnWorkflow">取消</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    
    // 添加样式
    if (!document.getElementById('settingsModalStyle')) {
      const style = document.createElement('style');
      style.id = 'settingsModalStyle';
      style.textContent = `
        .settings-modal {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.7);
          backdrop-filter: blur(10px);
          z-index: 10000;
          display: flex;
          align-items: center;
          justify-content: center;
          animation: fadeIn 0.3s ease;
          overflow: hidden;
        }
        body.modal-open {
          overflow: hidden;
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        .settings-modal-content {
          width: 90%;
          max-width: 1000px;
          max-height: 85vh;
          background: rgba(30, 30, 40, 0.95);
          backdrop-filter: blur(20px);
          border-radius: 20px;
          border: 1px solid rgba(0, 212, 255, 0.3);
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.8);
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .settings-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 20px 30px;
          border-bottom: 1px solid rgba(0, 212, 255, 0.2);
          background: rgba(0, 0, 0, 0.3);
        }
        .settings-header-left {
          display: flex;
          gap: 10px;
        }
        .settings-btn-add,
        .settings-btn-delete,
        .settings-btn-close {
          width: 36px;
          height: 36px;
          border: none;
          border-radius: 8px;
          background: rgba(0, 212, 255, 0.2);
          color: #00d4ff;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.3s ease;
        }
        .settings-btn-add:hover {
          background: rgba(0, 212, 255, 0.4);
          transform: scale(1.1);
        }
        .settings-btn-delete:hover {
          background: rgba(220, 53, 69, 0.4);
          color: #dc3545;
          transform: scale(1.1);
        }
        .settings-btn-close:hover {
          background: rgba(220, 53, 69, 0.4);
          color: #dc3545;
          transform: scale(1.1);
        }
        .settings-body {
          display: flex;
          flex: 1;
          overflow: hidden;
        }
        .settings-sidebar {
          width: 200px;
          background: rgba(0, 0, 0, 0.2);
          border-right: 1px solid rgba(0, 212, 255, 0.2);
          padding: 20px 0;
          overflow-y: auto;
        }
        .settings-menu-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 15px 25px;
          color: #888;
          cursor: pointer;
          transition: all 0.3s ease;
          border-left: 3px solid transparent;
        }
        .settings-menu-item:hover {
          background: rgba(0, 212, 255, 0.1);
          color: #00d4ff;
        }
        .settings-menu-item.active {
          background: rgba(0, 212, 255, 0.15);
          color: #00d4ff;
          border-left-color: #00d4ff;
        }
        .settings-menu-item i {
          font-size: 18px;
          width: 20px;
        }
        .settings-content {
          flex: 1;
          padding: 30px;
          overflow-y: auto;
          padding-right: 6px;
        }
        .settings-section h3 {
          font-size: 24px;
          color: #fff;
          margin-bottom: 25px;
          padding-bottom: 15px;
          border-bottom: 2px solid rgba(0, 212, 255, 0.2);
        }
        .secrets-list {
          display: flex;
          flex-direction: column;
          gap: 20px;
          padding-right: 6px;
          max-height: calc(70vh - 140px);
          overflow-y: auto;
        }
        .secret-item {
          background: rgba(20, 20, 30, 0.7);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 12px;
          padding: 20px;
          transition: all 0.3s ease;
        }
        .secret-item:hover {
          border-color: rgba(0, 212, 255, 0.3);
          box-shadow: 0 4px 20px rgba(0, 212, 255, 0.1);
        }
        .secret-item-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 15px;
        }
        .secret-item-title {
          font-size: 18px;
          font-weight: 600;
          color: #fff;
        }
        .secret-item-delete {
          width: 32px;
          height: 32px;
          border: none;
          border-radius: 6px;
          background: rgba(220, 53, 69, 0.2);
          color: #dc3545;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.3s ease;
        }
        .secret-item-delete:hover {
          background: rgba(220, 53, 69, 0.4);
          transform: scale(1.1);
        }
        .secret-form-group {
          margin-bottom: 20px;
        }
        .secret-form-group label {
          display: block;
          font-size: 14px;
          color: #aaa;
          margin-bottom: 8px;
        }
        .secret-form-group input,
        .secret-form-group select {
          width: 100%;
          padding: 12px 15px;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          color: #fff;
          font-size: 14px;
          transition: all 0.3s ease;
        }
        .secret-form-group input:focus,
        .secret-form-group select:focus {
          outline: none;
          border-color: #00d4ff;
          box-shadow: 0 0 0 3px rgba(0, 212, 255, 0.1);
        }
        .secret-form-group input[type="password"] {
          font-family: 'Courier New', monospace;
        }
        .secret-visibility-toggle {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-top: 10px;
        }
        .secret-visibility-toggle input[type="checkbox"] {
          width: auto;
          margin: 0;
        }
        .settings-footer {
          display: flex;
          justify-content: flex-end;
          gap: 15px;
          padding: 20px 30px;
          border-top: 1px solid rgba(0, 212, 255, 0.2);
          background: rgba(0, 0, 0, 0.3);
        }
        .btn-apply {
          background: linear-gradient(135deg, #00c6ff 0%, #0072ff 100%);
          color: white;
          padding: 12px 30px;
          border: none;
          border-radius: 8px;
          font-size: 15px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.3s ease;
        }
        .btn-apply:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 15px rgba(0, 198, 255, 0.4);
        }
        .btn-cancel {
          background: rgba(108, 117, 125, 0.3);
          color: #fff;
          padding: 12px 30px;
          border: 1px solid rgba(255, 255, 255, 0.2);
          border-radius: 8px;
          font-size: 15px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.3s ease;
        }
        .btn-cancel:hover {
          background: rgba(108, 117, 125, 0.5);
          transform: translateY(-2px);
        }
        .settings-content::-webkit-scrollbar,
        .secrets-list::-webkit-scrollbar {
          width: 6px;
        }
        .settings-content::-webkit-scrollbar-track,
        .secrets-list::-webkit-scrollbar-track {
          background: rgba(255, 255, 255, 0.05);
          border-radius: 10px;
        }
        .settings-content::-webkit-scrollbar-thumb,
        .secrets-list::-webkit-scrollbar-thumb {
          background: linear-gradient(180deg, rgba(0, 212, 255, 0.6), rgba(123, 47, 247, 0.6));
          border-radius: 10px;
          border: 1px solid rgba(0, 0, 0, 0.2);
        }
        .settings-content::-webkit-scrollbar-thumb:hover,
        .secrets-list::-webkit-scrollbar-thumb:hover {
          background: linear-gradient(180deg, rgba(0, 212, 255, 0.9), rgba(123, 47, 247, 0.9));
        }
        .llm-key-list {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
          gap: 16px;
          padding: 8px 4px;
          max-height: calc(70vh - 140px);
          overflow-y: auto;
        }
        .llm-key-item {
          background: linear-gradient(135deg, rgba(25, 25, 35, 0.95) 0%, rgba(20, 20, 30, 0.95) 100%);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 14px;
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 16px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          position: relative;
          overflow: hidden;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        }
        .llm-key-item::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 3px;
          background: linear-gradient(90deg, rgba(0, 212, 255, 0) 0%, rgba(0, 212, 255, 0.5) 50%, rgba(0, 212, 255, 0) 100%);
          opacity: 0;
          transition: opacity 0.3s ease;
        }
        .llm-key-item:hover {
          border-color: rgba(0, 212, 255, 0.4);
          box-shadow: 0 8px 24px rgba(0, 212, 255, 0.15), 0 0 0 1px rgba(0, 212, 255, 0.1);
          transform: translateY(-2px);
        }
        .llm-key-item:hover::before {
          opacity: 1;
        }
        .llm-key-info {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .llm-key-name {
          font-size: 15px;
          font-weight: 600;
          color: #fff;
          letter-spacing: 0.3px;
          line-height: 1.4;
          font-family: 'Segoe UI', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, sans-serif;
        }
        .llm-key-desc {
          font-size: 12px;
          color: rgba(255, 255, 255, 0.5);
          line-height: 1.5;
          font-weight: 400;
        }
        .llm-key-select {
          width: 100%;
          padding: 10px 14px;
          background: rgba(0, 0, 0, 0.4);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 8px;
          color: #fff;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.3s ease;
          appearance: none;
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23ffffff' d='M6 9L1 4h10z'/%3E%3C/svg%3E");
          background-repeat: no-repeat;
          background-position: right 12px center;
          padding-right: 36px;
        }
        .llm-key-select:hover {
          border-color: rgba(0, 212, 255, 0.4);
          background-color: rgba(0, 0, 0, 0.5);
        }
        .llm-key-select:focus {
          outline: none;
          border-color: rgba(0, 212, 255, 0.6);
          box-shadow: 0 0 0 3px rgba(0, 212, 255, 0.15);
          background-color: rgba(0, 0, 0, 0.6);
        }
        .llm-key-select option {
          background: #1a1a2e;
          color: #fff;
          padding: 8px;
        }
        .llm-key-list::-webkit-scrollbar {
          width: 6px;
        }
        .llm-key-list::-webkit-scrollbar-track {
          background: rgba(255, 255, 255, 0.05);
          border-radius: 10px;
        }
        .llm-key-list::-webkit-scrollbar-thumb {
          background: linear-gradient(180deg, rgba(0, 212, 255, 0.6), rgba(123, 47, 247, 0.6));
          border-radius: 10px;
          border: 1px solid rgba(0, 0, 0, 0.2);
        }
        .llm-key-list::-webkit-scrollbar-thumb:hover {
          background: linear-gradient(180deg, rgba(0, 212, 255, 0.9), rgba(123, 47, 247, 0.9));
        }
      `;
      document.head.appendChild(style);
    }
    
    // 绑定事件
    document.getElementById('settingsCloseBtnWorkflow').addEventListener('click', () => {
      modal.style.display = 'none';
      document.body.classList.remove('modal-open');
    });
    
    document.getElementById('settingsCancelBtnWorkflow').addEventListener('click', () => {
      modal.style.display = 'none';
      document.body.classList.remove('modal-open');
    });
    
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.style.display = 'none';
        document.body.classList.remove('modal-open');
      }
    });
    
    document.getElementById('settingsAddBtnWorkflow').addEventListener('click', () => {
      addSecretItemWorkflow();
    });
    
    document.getElementById('settingsDeleteBtnWorkflow').addEventListener('click', () => {
      if (selectedSecretIndexWorkflow >= 0) {
        deleteSecretItemWorkflow(selectedSecretIndexWorkflow);
      }
    });
    
    document.getElementById('settingsApplyBtnWorkflow').addEventListener('click', async () => {
      await saveSecretsConfigWorkflow();
      modal.style.display = 'none';
      document.body.classList.remove('modal-open');
    });
    initSettingsTabsWorkflow();
  }
  
  modal.style.display = 'flex';
  document.body.classList.add('modal-open');
  loadSecretsConfigWorkflow();
}

async function loadSecretsConfigWorkflow() {
  try {
    const res = await fetch('/api/secrets/get-config');
    const data = await res.json();
    secretsConfigWorkflow = {
      secrets: data.secrets || [],
      llmMappings: data.llmMappings || {}
    };
    
    const llmRes = await fetch('/api/secrets/get-llm-nodes');
    const llmData = await llmRes.json();
    llmNodesWorkflow = llmData.nodes || [];
    
    renderSecretsListWorkflow();
    renderLlmKeyListWorkflow();
  } catch (error) {
    console.error('加载配置失败:', error);
    secretsConfigWorkflow = { secrets: [], llmMappings: {} };
    llmNodesWorkflow = [];
    renderSecretsListWorkflow();
    renderLlmKeyListWorkflow();
  }
}

function renderSecretsListWorkflow() {
  const secretsList = document.getElementById('secretsListWorkflow');
  if (!secretsList) return;
  
  secretsList.innerHTML = '';
  
  if (secretsConfigWorkflow.secrets.length === 0) {
    secretsList.innerHTML = '<div style="text-align: center; color: #888; padding: 40px;">暂无密钥，点击左上角"+"添加</div>';
    return;
  }
  
  secretsConfigWorkflow.secrets.forEach((secret, index) => {
    const secretItem = document.createElement('div');
    secretItem.className = 'secret-item';
    secretItem.innerHTML = `
      <div class="secret-item-header">
        <div class="secret-item-title">${secret.name || '未命名密钥'}</div>
        <button class="secret-item-delete" onclick="deleteSecretItemWorkflow(${index})">
          <i class="fas fa-trash"></i>
        </button>
      </div>
      <div class="secret-form-group">
        <label>密钥名称</label>
        <input type="text" class="secret-name-input" value="${secret.name || ''}" 
               data-old-name="${secret.name || ''}"
               onchange="updateSecretNameWorkflow(${index}, this)">
      </div>
      <div class="secret-form-group">
        <label>密钥项目</label>
        <input type="${secret.visible ? 'text' : 'password'}" class="secret-value-input" 
               value="${secret.value || ''}" 
               onchange="updateSecretWorkflow(${index}, 'value', this.value)">
      </div>
      <div class="secret-form-group">
        <label>是否可见</label>
        <div class="secret-visibility-toggle">
          <input type="checkbox" class="secret-visible-checkbox" 
                 ${secret.visible ? 'checked' : ''} 
                 onchange="toggleSecretVisibilityWorkflow(${index}, this.checked)">
          <span>显示密钥内容</span>
        </div>
      </div>
    `;
    secretsList.appendChild(secretItem);
  });
}

function addSecretItemWorkflow() {
  if (!secretsConfigWorkflow.secrets) {
    secretsConfigWorkflow.secrets = [];
  }
  secretsConfigWorkflow.secrets.push({
    name: '',
    value: '',
    visible: false
  });
  selectedSecretIndexWorkflow = secretsConfigWorkflow.secrets.length - 1;
  renderSecretsListWorkflow();
  renderLlmKeyListWorkflow();
}

function deleteSecretItemWorkflow(index) {
  if (confirm('确定要删除这个密钥吗？')) {
    secretsConfigWorkflow.secrets.splice(index, 1);
    if (secretsConfigWorkflow.llmMappings) {
      Object.keys(secretsConfigWorkflow.llmMappings).forEach(node => {
        const secretName = secretsConfigWorkflow.llmMappings[node];
        const exists = secretsConfigWorkflow.secrets.some(sec => sec.name === secretName);
        if (!exists) {
          delete secretsConfigWorkflow.llmMappings[node];
        }
      });
    }
    selectedSecretIndexWorkflow = -1;
    renderSecretsListWorkflow();
    renderLlmKeyListWorkflow();
  }
}

function updateSecretWorkflow(index, field, value) {
  if (secretsConfigWorkflow.secrets[index]) {
    secretsConfigWorkflow.secrets[index][field] = value;
  }
}

function updateSecretNameWorkflow(index, input) {
  const oldName = input.dataset.oldName || '';
  const newName = input.value;
  if (secretsConfigWorkflow.secrets[index]) {
    secretsConfigWorkflow.secrets[index].name = newName;
    if (oldName !== newName) {
      if (!secretsConfigWorkflow.llmMappings) {
        secretsConfigWorkflow.llmMappings = {};
      }
      Object.keys(secretsConfigWorkflow.llmMappings).forEach(node => {
        if (secretsConfigWorkflow.llmMappings[node] === oldName) {
          secretsConfigWorkflow.llmMappings[node] = newName;
        }
      });
      input.dataset.oldName = newName;
    renderSecretsListWorkflow();
      renderLlmKeyListWorkflow();
    }
  }
}

function toggleSecretVisibilityWorkflow(index, visible) {
  if (secretsConfigWorkflow.secrets[index]) {
    secretsConfigWorkflow.secrets[index].visible = visible;
    const valueInput = document.querySelectorAll('.secret-value-input')[index];
    if (valueInput) {
      valueInput.type = visible ? 'text' : 'password';
    }
  }
}

async function saveSecretsConfigWorkflow() {
  try {
    const res = await fetch('/api/secrets/save-config', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(secretsConfigWorkflow)
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

function initSettingsTabsWorkflow() {
  if (settingsTabsInitializedWorkflow) return;
  const menuItems = document.querySelectorAll('.settings-menu-item');
  const sections = {
    secrets: document.getElementById('secretsSectionWorkflow'),
    'llm-key': document.getElementById('llmKeySectionWorkflow')
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
  settingsTabsInitializedWorkflow = true;
}

function renderLlmKeyListWorkflow() {
  const llmKeyList = document.getElementById('llmKeyListWorkflow');
  if (!llmKeyList) return;

  llmKeyList.innerHTML = '';

  if (!llmNodesWorkflow.length) {
    llmKeyList.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">未检测到 LLM 组件</div>';
    return;
  }

  const secretOptions = secretsConfigWorkflow.secrets || [];

  llmNodesWorkflow.forEach(node => {
    const item = document.createElement('div');
    item.className = 'llm-key-item';
    const currentSecret = secretsConfigWorkflow.llmMappings?.[node] || '';

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
    select.addEventListener('change', () => updateLlmMappingWorkflow(node, select.value));

    item.appendChild(info);
    item.appendChild(select);
    llmKeyList.appendChild(item);
  });
}

function updateLlmMappingWorkflow(node, secretName) {
  if (!secretsConfigWorkflow.llmMappings) {
    secretsConfigWorkflow.llmMappings = {};
  }
  if (!secretName) {
    delete secretsConfigWorkflow.llmMappings[node];
  } else {
    secretsConfigWorkflow.llmMappings[node] = secretName;
  }
}
