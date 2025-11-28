let graph;
let isInput=0;
// 请求所有节点信息 todo：如果需要更新的，建议发通知更新或者定时拉取
const requestNodeList = async () => {
  const res = await fetch('/get-python-files');
  return await res.json()
}
const fileList = await requestNodeList();
// 请求节点详细信息
const requestNodeInfo = async (nodeName) => {
  const res = await fetch(`/get-node-details/${nodeName}`)
  return await res.json()
}
//删除节点
const removeNode = (item) => {
  graph.remove(item);
};
// 删除边
const removeEdge = (item) => {
  graph.remove(item);
};
// 手动添加节点
const addNode = (name, x, y,hash,id) => {
  const n = name.split('.py')[0];
  requestNodeInfo(n).then((nodeInfo) => {
    // 总高度
    const maxHeight = Math.max(nodeInfo.InPutName.length, nodeInfo.OutPutName.length) * 20 + 60
    const anchorPoints = nodeInfo.InPutName.map((node, index) => {
      const anchorHeight = 60 + index * 20;
      return [0.02, anchorHeight / maxHeight]
    }).concat(nodeInfo.OutPutName.map((node, index) => {
      const anchorHeight = 60 + index * 20;
      return [0.98, anchorHeight / maxHeight]
    }))
    let Ids='';
    if(id=='')
    {
      Ids=name + Date.now();
    }
    else
    {
      Ids=id;
    }
    const node = {
      // 可以添加随机数或时间戳来达到重复导入的效果
      id: Ids,
      name,
      hash:hash,
      x,
      y,
      anchorPoints,
      ...nodeInfo
    };
    graph.addItem('node', node);
  });
}
// 右键点击菜单实现
const contextMenu = new G6.Menu({
  getContent(evt) {
    let menu = '';
    if (evt.target && evt.target.isCanvas && evt.target.isCanvas()) {
      menu = `<div class="title">添加节点</div>`
      menu += fileList.map((file) => {
        return `<div class="menu-item" data-behavior="addNode" data-hash="${file.hash}" data-canvasx="${evt.canvasX}" data-canvasy="${evt.canvasY}">${file.filename}</div>`
      }).join('');      
    } else if (evt.item) {
      const itemType = evt.item.getType();
      if (itemType === 'node') {
        menu = `
          <div class="menu-item" data-behavior="removeNode">删除节点</div>
          <div class="menu-item" data-behavior="copyNode" data-canvasx="${evt.canvasX}" data-canvasy="${evt.canvasY}">复制节点</div>
        `
      } else {
        menu = `
          <div class="menu-item" data-behavior="removeEdge">删除连线</div>
        `
      }
    }
    return `<div class="new-context-menu">
${menu}
</div>`;
  },
  handleMenuClick: (target, item) => {
    const targetText = target.dataset.behavior;
    console.log('阿松大',target.innerText, target.dataset.canvasx, target.dataset.canvasy,target.dataset.hash,'');
    switch (targetText) {
      case 'addNode':
        addNode(target.innerText, target.dataset.canvasx, target.dataset.canvasy,target.dataset.hash,'');
        break;
      case 'removeNode':
        removeNode(item);
        break;
      case 'copyNode':
        addNode(item.getModel().name, target.dataset.canvasx, target.dataset.canvasy,target.dataset.hash,'');
        break;
      case 'removeEdge':
        removeEdge(item);
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
G6.registerNode('fileNode', {
  draw(cfg, group) {
    const maxHeight = Math.max(cfg.InPutName.length, cfg.OutPutName.length)
    const container = group.addShape('rect', {
      attrs: {
        x: 0,
        y: 0,
        width: 450,
        height: 60 + maxHeight * 20,
        stroke: 'black',
        radius: [8, 8],
        fill: 'rgb(238,241,243)', // todo 节点背景框颜色
      },
      name: 'rect',
    });// 最外层灰色的框
    group.addShape('rect', {
      attrs: {
        x: 0,
        y: 0,
        width: 450,
        height: 40,
        radius: [8, 8, 0, 0],
        fill: 'rgb(3,197,136)', // todo 节点标题栏颜色
      },
      capture: false,
      name: 'rect',
    }); // 标题绿色的栏
    group.addShape('text', {
      attrs: {
        x: 25,
        y: 20,
        text: cfg.name.replace(".py", ""),
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
    cfg.InPutName.map((name, index) => {
      group.addShape('text', {
        attrs: {
          x: 25,
          y: 60 + index * 20,
          text: name,
          fill: '#000000',
          textBaseline: 'middle',
          fontWeight: 600,
          fontSize: 14,
          fontFamily: 'Microsoft YaHei',
          textAlign: 'left',
        },
        capture: false,
        name: 'nameText',
      });
    }); // InPutName标题文字
    cfg.OutPutName.map((name, index) => {
      group.addShape('text', {
        attrs: {
          x: 425,
          y: 60 + index * 20,
          text: name,
          fill: '#000000',
          textBaseline: 'middle',
          fontWeight: 600,
          fontSize: 14,
          fontFamily: 'Microsoft YaHei',
          textAlign: 'right',
        },
        name: 'nameText',
      });
    }); // OutPutName标题文字
    const anchorPoints = this.getAnchorPoints(cfg)
    anchorPoints.forEach((anchorPos, i) => {
      let Kind=''
      if(i<cfg.InPutName.length)
      {
        Kind='input'
      }
      else if(i>=cfg.InPutName.length && i<cfg.InPutName.length+cfg.OutPutName.length)
      {
        Kind='output'
      }
      group.addShape('circle', {
        attrs: {
          r: 5,
          x: 450 * anchorPos[0],
          y: (60 + maxHeight * 20) * anchorPos[1],
          fill: '#fff',
          stroke: '#5F95FF'
        },
        // must be assigned in G6 3.3 and later versions. it can be any string you want, but should be unique in a custom item type
        name: `anchor-point`, // the name, for searching by group.find(ele => ele.get('name') === 'anchor-point')
        anchorPointIdx: i, // flag the idx of the anchor-point circle
        links: 0, // cache the number of edges connected to this shape
        visible: true, // invisible by default, shows up when links > 1 or the node is in showAnchors state
        draggable: true,
        Kind:Kind
      })
    }) // 圆圈锚点
    return container;
  },
  getAnchorPoints(cfg) {
    return cfg.anchorPoints;
  },
  setState(name, value, item) {
  },
  afterDraw(cfg, group) {
  }
});
// 记录锚点
let sourceAnchorIdx, targetAnchorIdx, sourceAnchor;
// 处理平行和不同锚点的边
const processParallelEdgesOnAnchorPoint = (
  edges,
  offsetDiff = 15,
  multiEdgeType = 'cubic-horizontal',
  singleEdgeType = 'cubic-horizontal',
  loopEdgeType = 'cubic-horizontal'
) => {
  const len = edges.length;
  const cod = offsetDiff * 2;
  const loopPosition = [
    'top',
    'top-right',
    'right',
    'bottom-right',
    'bottom',
    'bottom-left',
    'left',
    'top-left',
  ];
  const edgeMap = {};
  const tags = [];
  const reverses = {};
  for (let i = 0; i < len; i++) {
    const edge = edges[i];
    const {source, target, sourceAnchor, targetAnchor} = edge;
    const sourceTarget = `${source}|${sourceAnchor}-${target}|${targetAnchor}`;

    if (tags[i]) continue;
    if (!edgeMap[sourceTarget]) {
      edgeMap[sourceTarget] = [];
    }
    tags[i] = true;
    edgeMap[sourceTarget].push(edge);
    for (let j = 0; j < len; j++) {
      if (i === j) continue;
      const sedge = edges[j];
      const {source: src, target: dst, sourceAnchor: srcAnchor, targetAnchor: dstAnchor} = sedge;

      // 两个节点之间共同的边
      // 第一条的source = 第二条的target
      // 第一条的target = 第二条的source
      if (!tags[j]) {
        if (source === dst && sourceAnchor === dstAnchor
          && target === src && targetAnchor === srcAnchor) {
          edgeMap[sourceTarget].push(sedge);
          tags[j] = true;
          reverses[`${src}|${srcAnchor}|${dst}|${dstAnchor}|${edgeMap[sourceTarget].length - 1}`] = true;
        } else if (source === src && sourceAnchor === srcAnchor
          && target === dst && targetAnchor === dstAnchor) {
          edgeMap[sourceTarget].push(sedge);
          tags[j] = true;
        }
      }
    }
  }

  for (const key in edgeMap) {
    const arcEdges = edgeMap[key];
    const {length} = arcEdges;
    for (let k = 0; k < length; k++) {
      const current = arcEdges[k];
      if (current.source === current.target) {
        if (loopEdgeType) current.type = loopEdgeType;
        // 超过8条自环边，则需要重新处理
        current.loopCfg = {
          position: loopPosition[k % 8],
          dist: Math.floor(k / 8) * 20 + 50,
        };
        continue;
      }
      if (length === 1 && singleEdgeType && (current.source !== current.target || current.sourceAnchor !== current.targetAnchor)) {
        current.type = singleEdgeType;
        continue;
      }
      current.type = multiEdgeType;
      const sign =
        (k % 2 === 0 ? 1 : -1) * (reverses[`${current.source}|${current.sourceAnchor}|${current.target}|${current.targetAnchor}|${k}`] ? -1 : 1);
      if (length % 2 === 1) {
        current.curveOffset = sign * Math.ceil(k / 2) * cod;
      } else {
        current.curveOffset = sign * (Math.floor(k / 2) * cod + offsetDiff);
      }
    }
  }
  return edges;
};
// 初始化图
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
          'zoom-canvas',
          {
            type: 'drag-node',
            shouldBegin: e => {
              if (e.target.get('name') === 'anchor-point') return false;
              return true;
            }
          },
          {
            type: 'create-edge',
            trigger: 'drag', // set the trigger to be drag to make the create-edge triggered by drag
            shouldBegin: e => {
              // avoid beginning at other shapes on the node
              if (e.target && e.target.get('name') !== 'anchor-point') return false;
              sourceAnchorIdx = e.target.get('anchorPointIdx');
              e.target.attr('fill', '#78bbe5');
              sourceAnchor = e.target;
              return true;
            },
            shouldEnd: e => {
              // avoid ending at other shapes on the node
              //if(e.target&&e.target.get('Kind')!=sourceAnchor.get('Kind')) return false;
              const sourceKind=sourceAnchor.get('Kind');
              const targetKind=e.target.get('Kind');
              const sourceLinks=sourceAnchor.get('links');
              const targetLinks=e.target.get('links');
              if (e.target && e.target.get('name') !== 'anchor-point') return false;
              if(sourceKind==targetKind) return false;
              if(sourceLinks>=1 && sourceKind=='input') return false;
              if(targetLinks>=1 && targetKind=='input') return false;
              if (e.target) {
                targetAnchorIdx = e.target.get('anchorPointIdx');
                e.target.set('links', e.target.get('links') + 1);  // cache the number of edge connected to this anchor-point circle
                sourceAnchor.set('links', sourceAnchor.get('links') + 1); // cache the number of edge connected to this anchor-point circle
                e.target.attr('fill', '#78bbe5')
                if(sourceKind=='input')
                {
                  isInput=1;
                }
                else
                {
                  isInput=-1;
                }
                return true;
              }
              sourceAnchor.attr('fill', '#fff')
              targetAnchorIdx = undefined;
              return true;
            },
          }
          // {
          //   type: 'create-edge',
          //   trigger: 'drag',
          //   shouldBegin: e => {
          //     // avoid beginning at other shapes on the node
          //     if (e.target && e.target.get('name') !== 'anchor-point') return false;
          //     sourceAnchorIdx = e.target.get('anchorPointIdx');
          //     e.target.set('links', e.target.get('links') + 1); // cache the number of edge connected to this anchor-point circle
          //     e.target.attr('fill', '#78bbe5');
          //     sourceAnchor = e.target;
          //     return true;
          //   },
          //   shouldEnd: e => {
          //     // avoid ending at other shapes on the node
          //     if (e.target && e.target.get('name') !== 'anchor-point') return false;
          //     if (e.target) {
          //       targetAnchorIdx = e.target.get('anchorPointIdx');
          //       e.target.set('links', e.target.get('links') + 1);  // cache the number of edge connected to this anchor-point circle
          //       e.target.attr('fill', '#78bbe5')
          //       return true;
          //     }
          //     targetAnchorIdx = undefined;
          //     sourceAnchor.attr('fill', '#fff')
          //     sourceAnchor = undefined;
          //     return false;
          //   },
          // }
        ], // 允许拖拽画布、放缩画布、拖拽节点
      },
      animate: true, // Boolean，切换布局时是否使用动画过度，默认为 false
      animateCfg: {
        duration: 500, // Number，一次动画的时长
        easing: 'easeLinear', // String，动画函数
      },
      defaultNode: {
        type: 'fileNode',
      },
      defaultEdge: {
        type: 'cubic-horizontal',
        style: {
          lineWidth: 4,
          stroke: '#000', // 线的颜色
         
        },
       
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
    backgroundImag.toBack();

    // 添加边后更新锚点
    graph.on('aftercreateedge', (e) => {
      // update the sourceAnchor and targetAnchor for the newly added edge
      graph.updateItem(e.edge, {
        sourceAnchor: sourceAnchorIdx,
        targetAnchor: targetAnchorIdx
      })

      // update the curveOffset for parallel edges
      const edges = graph.save().edges;
      processParallelEdgesOnAnchorPoint(edges);
      graph.getEdges().forEach((edge, i) => {
        graph.updateItem(edge, {
          curveOffset: edges[i].curveOffset,
          curvePosition: edges[i].curvePosition,
        });
      });
    });

    graph.on('afteradditem', e => {
      //if (e.item && e.item.getType() === 'edge') {
       // graph.updateItem(e.item, {
          
        //  sourceAnchor: sourceAnchorIdx
       // });
        //let data = graph.save()


        if(isInput==1)
        {
          data.edges[data.edges.length-1].style.endArrow = true;
          data.edges[data.edges.length-1].style.endArrow=
          {
            path: G6.Arrow.triangle(10, 20, 25), // 使用内置箭头路径函数，参数为箭头的 宽度、长度、偏移量（默认为 0，与 d 对应）
            d: 25
          }
        }
        else if(isInput==-1)
        {
          data.edges[data.edges.length-1].style.startArrow = true;
          data.edges[data.edges.length-1].style.startArrow=
          {
            path: G6.Arrow.triangle(-10, 20, 25), // 使用内置箭头路径函数，参数为箭头的 宽度、长度、偏移量（默认为 0，与 d 对应）
            d: 15
          }
        }
        isInput=0;
        console.log('测试asdasd',e);
      
    })

    graph.on('beforeremoveitem', (e) => {
      if (e && e.type === 'edge') {
        const edge = graph.findById(e.item.id)
        const sourceNode = edge.getSource();
        const targetNode = edge.getTarget();
        console.log('测试1',edge,e.item.id);
        const sourceAnchor = sourceNode.getContainer().find(ele => ele.get('anchorPointIdx') === e.item.sourceAnchor);
        if(sourceAnchor.get('links')==0) {
          sourceAnchor && sourceAnchor.attr('fill', '#fff');
        }
        //const targetNode = edge.getTarget();
        //const targetAnchor = targetNode.getContainer()?.find(ele => ele.get('anchorPointIdx') === e.item.targetAnchor);
        //targetAnchor && targetAnchor.attr('fill', '#fff');
      }
    });
    graph.on('mousedown', (e) => {
      // e.originEvent 鼠标原生事件
      // e.item // 事件触发的物体 e.target.get('name') !== 'anchor-point'
      
    })
    graph.on('afterremoveitem', () => {
      // todo 在更改元素的时候保存下来
      //   由graph.save()获取到数据
    });
    graph.on('edge:mouseup', (e) => {
      if(e.target.get('name') === 'anchor-point') {
        console.log('点击了锚点', e.target.get('anchorPointIdx'));
      }
    });
    graph.on('afteradditem', () => {
      console.log(graph.save());
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


initGraph();


let fileInfoArray = [];
InitFunction()
//按键编辑
document.getElementById('saveButton').addEventListener('click', saveFunction);
function saveFunction() {
  // 弹出确认框询问用户是否保存
  if (confirm("Do you want to save?")) {
      // 弹出输入框让用户输入保存的名称
      var saveName = prompt("Enter the name for the save:");
      if (saveName) {
          //ViewCenter = calculateVisualCenter(newArray);
          // 创建一个包含所有需要保存数据的对象
          var dataToSave = {
              nodes: graph.save(),
              //viewCenter: ViewCenter,
              //nodeCount: NodeNums,
              //scale: {x: scaleX, y: scaleY},
              //prev: {x: prevX, y: prevY}
          };
          // 将数据对象转换为 JSON 字符串
          console.log('存储',dataToSave);
          var jsonDataToSave = JSON.stringify(dataToSave);
          // 使用 AJAX 向后端发送保存请求
          var xhr = new XMLHttpRequest();
          xhr.open("POST", "/save", true);
          xhr.setRequestHeader("Content-Type", "application/json");
          xhr.onreadystatechange = function () {
              if (this.readyState == 4 && this.status == 200) {
                  alert("Saved successfully!");
              }
          };
          // 发送请求，包括保存的名称和数据
          xhr.send(JSON.stringify({name: saveName, data: jsonDataToSave}));
      }
  }
}
document.body.addEventListener('dragover', (event) => {
  event.preventDefault(); // 阻止默认行为
});
function InitFunction() {
  fetch('/get-python-files')
      .then(response => response.json())
      .then(data => { 
          data.forEach(function(file_info) {
              fileInfoArray.push({
                  filename: file_info.filename,
                  hash: file_info.hash
              });
          });
      })
      .catch(error => console.error('Error:', error));
}


document.body.addEventListener('drop', (event) => {
  event.preventDefault(); // 阻止默认行为
  graph.clear();
  const files = event.dataTransfer.files;
  if (files.length > 0) {
      const file = files[0];
      if (file.type === "application/json") {
          // 弹出确认框询问用户是否确认导入新的项目
          if (confirm("你确定要导入新的项目吗？他会清楚其他所有的Nodes。")) {
              // 清除所有 Nodes
              // 读取文件内容（后续步骤将在这里进行）
              const reader = new FileReader();
              reader.onload = (e) => {
                  // 处理文件内容         
                  //ReCreactNodes(e.target.result);
                  const data = JSON.parse(e.target.result);
                  graph.changeData(data.nodes);
                  //console.log('测试',JSON.parse(e.target.result)); // 打印文件内容
                 // const edgesdate = data.nodes.edges;
                 
              };
              reader.readAsText(file);
          }
      } else {
          console.log("Please drop a JSON file.");
      }
  }
});
function ReCreactNodes1(NodeList) {
  
  console.log('解析',NodeList);
  //console.log(parsedJson,parsedJson.nodes[0].position.x,parsedJson.nodes[0].position.y);
  // 清除 newArray
  //console.log('测试',data);
  graph.changeData(NodeList.nodes);
  //Moving(parsedJson.viewCenter.x,parsedJson.viewCenter.y);
}
function ReCreactNodes(NodeList) {
  const parsedJson = JSON.parse(NodeList);
  //console.log(parsedJson,parsedJson.nodes[0].position.x,parsedJson.nodes[0].position.y);
  // 清除 newArray
  parsedJson.nodes.nodes.forEach(function(newItem) {
    var matchFound = false;
    fileInfoArray.forEach(function(fileInfoItem) {
        if (newItem.hash === fileInfoItem.hash) {
            addNode(fileInfoItem.filename.replace(".py", ""), newItem.x, newItem.y, newItem.hash,newItem.id);
            matchFound = true;
        }
    });
    if (!matchFound) {
        console.log('No match found for hash:', newItem.hash);
    }
  });
  console.log('解析',graph.save());
  let data = graph.save()
  data.edges = parsedJson.nodes.edges;
  //console.log(parsedJson,parsedJson.nodes[0].position.x,parsedJson.nodes[0].position.y);
  // 清除 newArray
  console.log('测试',data);
  graph.changeData(data);
  //Moving(parsedJson.viewCenter.x,parsedJson.viewCenter.y);
}
