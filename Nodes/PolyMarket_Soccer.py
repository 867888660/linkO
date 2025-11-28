import json
import logging
import os
import re
import math

# **Function definition**

# **Define the number of outputs and inputs**输入节点与输出节点的数量
OutPutNum = 3
InPutNum = 17
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs  = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}',  'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly**

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# ---------- 严格按照你的模板撰写 ----------
FunctionIntroduction = '组件功能（简述代码整体功能）\\n这是一个基础的节点模板程序，用于计算单个独立期权选项的综合评分与建议买入股数。节点读取规则清晰度、若赢年化、1¢ 深度及若干权重等输入，输出 Score（0–100）、SuggestedQty，以及 RightNow 买入信号。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n程序定义了一个标准的节点结构模板，包含输入输出节点的初始化、属性配置和基础的运行框架。核心处理逻辑在 run_node 函数中实现：将 APR_win 归一化得到 S_apr；由 depth_ask_1c_usd 归一得到 S_liq；结合模型-市场错价 S_edge 与权重合成 Score（若 Isclear=0 则 Score=0）；若 IsSubject 或 IsMatching 为真则一票否决 Score=0；按 beta×1¢ 深度股数或用(1¢ 金额/卖一价)估算股数得到 SuggestedQty；最后比较 Score 与 Rightnow_buy_Score 输出 Is_RightNow_Buy。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: Isclear\\n    type: boolean\\n    required: true\\n    description: 规则是否清晰，一票否决（0 时 Score=0）\\n  - name: APR_win\\n    type: number\\n    required: true\\n    description: 若赢年化收益（主指标）\\n  - name: l1_spread_c\\n    type: number\\n    required: false\\n    description: 一级点差（美分），仅入日志不参与打分\\n  - name: depth_ask_1c_usd\\n    type: number\\n    required: false\\n    description: 1¢ 带宽可成交金额（USD），用于小加分与控仓估算\\n  - name: depth_ask_1c_qty\\n    type: number\\n    required: false\\n    description: 1¢ 带宽可成交股数，若提供则优先用于控仓\\n  - name: ask_price\\n    type: number\\n    required: false\\n    description: 卖一价；无股数时用 USD/ask 估算股数\\n  - name: S_llm\\n    type: number\\n    required: false\\n    description: LLM 解释分（0–1）\\n  - name: w_main\\n    type: number\\n    required: false\\n    description: 收益主导权重，默认 0.90\\n  - name: w_liq\\n    type: number\\n    required: false\\n    description: 流动性小加分权重，默认 0.05\\n  - name: w_llm\\n    type: number\\n    required: false\\n    description: 解释分权重，默认 0.05\\n  - name: A_ref\\n    type: number\\n    required: false\\n    description: 年化标尺，默认 0.30\\n  - name: D_ref\\n    type: number\\n    required: false\\n    description: 深度标尺（USD），默认 3000\\n  - name: beta\\n    type: number\\n    required: false\\n    description: 控仓系数，默认 0.30\\n  - name: top_concentration_ask_1c\\n    type: number\\n    required: false\\n    description: 1¢ 深度是否单笔集中（=1.0 则仅日志提示）\\n  - name: IsSubject\\n    type: boolean\\n    required: false\\n    description: 是否属于主观题（为真时一票否决 Score=0）\\n  - name: IsMatching\\n    type: boolean\\n    required: false\\n    description: 是否处于匹配/冲突状态（为真时与 IsSubject 相同，一票否决 Score=0）\\n  - name: Rightnow_buy_Score\\n    type: number\\n    required: false\\n    description: 触发 RightNow 买入的分数阈值，默认 85.0\\noutputs:\\n  - name: Score\\n    type: number\\n    description: 最终推荐分（0–100）\\n  - name: SuggestedQty\\n    type: number\\n    description: 建议买入股数（按 1¢ 深度与 beta 控仓）\\n  - name: Is_RightNow_Buy\\n    type: boolean\\n    description: 若 Score > Rightnow_buy_Score 则为 true，否则为 false\\n```\\n\\n运行逻辑（用 - 列表描写详细流程）\\n- 初始化输入输出数组，分配基础属性（ID、名称、类型）\\n- 读取输入，进行容错解析与安全下限处理\\n- 计算 S_apr、S_edge（含反向惩罚）、S_liq 与 S_time，并按权重合成得分\\n- 若 Isclear=0 或 IsSubject/IsMatching=1，则 Score=0（前两者为一票否决）\\n- 依据 1¢ 深度股数或用(1¢ 金额/卖一价)估算股数，乘以 beta 得到 SuggestedQty；若 e<0 再按 P 缩仓\\n- 将 Score 与 SuggestedQty 写入输出；比较 Score 与 Rightnow_buy_Score 得出 Is_RightNow_Buy 并输出'

# **Assign properties to Inputs**
# —— 严格使用你给的设置风格（逐行赋值）——
Inputs[0]['Kind'] = 'String'
Inputs[0]['name'] = 'Isclear'
Inputs[0]['Isnecessary'] = True
Inputs[0]['IsLabel'] = False

Inputs[1]['Kind'] = 'String'
Inputs[1]['name'] = 'APR_win'
Inputs[1]['Isnecessary'] = True
Inputs[1]['IsLabel'] = False

Inputs[2]['Kind'] = 'String'
Inputs[2]['name'] = 'l1_spread_c'
Inputs[2]['Isnecessary'] = True
Inputs[2]['IsLabel'] = False

Inputs[3]['Kind'] = 'String'
Inputs[3]['name'] = 'depth_ask_1c_usd'
Inputs[3]['Isnecessary'] = True
Inputs[3]['IsLabel'] = False

Inputs[4]['Kind'] = 'String'
Inputs[4]['name'] = 'depth_ask_1c_qty'
Inputs[4]['Isnecessary'] = True
Inputs[4]['IsLabel'] = False

Inputs[5]['Kind'] = 'String'
Inputs[5]['name'] = 'ask_price'
Inputs[5]['Isnecessary'] = True
Inputs[5]['IsLabel'] = False

Inputs[6]['Kind'] = 'String'
Inputs[6]['name'] = 'S_llm'
Inputs[6]['Isnecessary'] = True
Inputs[6]['IsLabel'] = False

Inputs[7]['Kind'] = 'Num'
Inputs[7]['name'] = 'w_main'
Inputs[7]['Isnecessary'] = True
Inputs[7]['IsLabel'] = True
Inputs[7]['Num'] = 0.45

Inputs[8]['Kind'] = 'Num'
Inputs[8]['name'] = 'w_liq'
Inputs[8]['Isnecessary'] = True
Inputs[8]['IsLabel'] = True
Inputs[8]['Num'] = 0.15

Inputs[9]['Kind'] = 'Num'
Inputs[9]['name'] = 'w_llm'
Inputs[9]['Isnecessary'] = True
Inputs[9]['IsLabel'] = True
Inputs[9]['Num'] = 0.30

Inputs[10]['Kind'] = 'Num'
Inputs[10]['name'] = 'A_ref'
Inputs[10]['Isnecessary'] = True
Inputs[10]['IsLabel'] = True
Inputs[10]['Num'] = 0.30

Inputs[11]['Kind'] = 'Num'
Inputs[11]['name'] = 'D_ref'
Inputs[11]['Isnecessary'] = True
Inputs[11]['IsLabel'] = True
Inputs[11]['Num'] = 3000

Inputs[12]['Kind'] = 'Num'
Inputs[12]['name'] = 'beta'
Inputs[12]['Isnecessary'] = True
Inputs[12]['IsLabel'] = True
Inputs[12]['Num'] = 0.30

Inputs[13]['Kind'] = 'String'
Inputs[13]['name'] = 'top_concentration_ask_1c'
Inputs[13]['Isnecessary'] = True
Inputs[13]['IsLabel'] = False

Inputs[14]['Kind'] = 'String'
Inputs[14]['name'] = 'IsSubject'
Inputs[14]['Isnecessary'] = True
Inputs[14]['IsLabel'] = False

Inputs[15]['Kind'] = 'String'
Inputs[15]['name'] = 'IsMatching'
Inputs[15]['Isnecessary'] = True
Inputs[15]['IsLabel'] = False

Inputs[16]['Kind'] = 'Num'
Inputs[16]['name'] = 'Rightnow_buy_Score'
Inputs[16]['Isnecessary'] = True
Inputs[16]['IsLabel'] = True
Inputs[16]['Num'] = 85.0

# **Assign properties to Outputs**
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Score'

Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'SuggestedQty'

Outputs[2]['Kind'] = 'Boolean'
Outputs[2]['name'] = 'Is_RightNow_Buy'

# **Assign properties to Inputs**

# **Function definition**

def _to_float(x, default=0.0):
    try:
        if x is None:
            return float(default)
        if isinstance(x, str) and x.strip()=='':
            return float(default)
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return float(default)
        return v
    except Exception:
        return float(default)

def _to_bool01(x):
    if isinstance(x, str):
        v = x.strip().lower()
        if v in ('1','true','yes','y','t'): return 1
        if v in ('0','false','no','n','f'): return 0
    return 1 if bool(x) else 0

def _clip01(v):
    return max(0.0, min(1.0, float(v)))

def run_node(node):
    # 读取 Inputs
    Isclear           = _to_bool01(node['Inputs'][0]['Context'])
    APR_win           = _to_float(node['Inputs'][1]['Context'], 0.0)
    l1_spread_c       = _to_float(node['Inputs'][2]['Context'], 0.0)  # 仅日志
    depth_usd         = _to_float(node['Inputs'][3]['Context'], 0.0)
    depth_qty_raw     = node['Inputs'][4]['Context']
    depth_qty         = None if depth_qty_raw in (None, '') else _to_float(depth_qty_raw, 0.0)
    ask_price_raw     = _to_float(node['Inputs'][5]['Context'], 0.0)
    S_llm_in_raw      = _to_float(node['Inputs'][6]['Context'], 0.0)
    w_main            = _to_float(node['Inputs'][7]['Context'], 0.90)
    w_liq             = _to_float(node['Inputs'][8]['Context'], 0.05)
    w_llm             = _to_float(node['Inputs'][9]['Context'], 0.05)
    A_ref             = _to_float(node['Inputs'][10]['Context'], 0.30)
    D_ref             = _to_float(node['Inputs'][11]['Context'], 3000.0)
    beta              = _to_float(node['Inputs'][12]['Context'], 0.30)
    top_concentration = _to_float(node['Inputs'][13]['Context'], -1.0)
    IsSubject         = _to_bool01(node['Inputs'][14]['Context'])
    IsMatching        = _to_bool01(node['Inputs'][15]['Context'])
    rightnow_buy_score = _to_float(node['Inputs'][16]['Context'], 85.0)

    # 由前端传入，不预归一（允许和≠1；先截断到非负）
    w_main = max(0.0, w_main)   # 年化权重
    w_llm  = max(0.0, w_llm)    # 错价权重（用在 S_edge）
    w_liq  = max(0.0, w_liq)    # 流动性权重

    # ============ 常量（按需调整） ============
    TAU_STRONG_AGAINST = 0.25   # 强烈反向哨兵阈值
    BASE_FRICTION      = 0.06   # ★比原来小一点，增强错价灵敏度（原 0.08）
    MIN_ASK_EPS        = 1e-6   # 防止除以零
    CONTRAST           = 0.85   # ★分数拉伸指数(<1 提升区分度与整体水平)
    W_PENALTY          = 0.30   # ★总分惩罚权重，匹配 w_edge

    # 规范化概率与价格（概率视角）
    p_model  = _clip01(S_llm_in_raw)        # 约定：S_llm_in 为“该 side 的模型概率”
    p_mkt    = _clip01(ask_price_raw)       # 约定：ask_price ≈ 该 side 的市场概率
    fee_prob = max(0.0, min(0.5, l1_spread_c / 100.0))

    # ---- 哨兵（强反向）：市场显著高于模型且超过费用 -> 直接-1分并清仓 ----
    if (p_mkt - p_model - fee_prob) >= TAU_STRONG_AGAINST:
        Outputs[0]['Context'] = "-1"
        Outputs[1]['Context'] = "0"
        Outputs[2]['Boolean'] = False
        return Outputs

    # 1) 年化收益子分（饱和）：S_apr ∈ (0,1)
    A_ref_safe = max(1e-9, A_ref)
    APR_win_safe = max(0.0, APR_win)
    S_apr = APR_win_safe / (APR_win_safe + A_ref_safe)

    # 2) 错价子分：正向奖励 × 反向惩罚
    #    e>=0: G>0,P=1     e<0: G=0,P<1
    e = (p_model - p_mkt) - fee_prob
    pos = max(0.0, e)
    neg = max(0.0, -e)
    G = pos / (pos + BASE_FRICTION)             # 正向奖励（保持原分式）
    P = 1.0 - (neg / (neg + BASE_FRICTION))     # 新增反向惩罚（平滑从 1 降至 ~0）
    S_edge = G * P                               # ★唯一替换点

    # 3) 流动性子分（饱和）：S_liq ∈ (0,1)
    D_ref_safe = max(1e-9, D_ref)
    depth_usd_safe = max(0.0, depth_usd)
    S_liq = depth_usd_safe / (depth_usd_safe + D_ref_safe)

    # 4) 时间子分：暂无 days_to_end，固定 1.0
    S_time = 1.0

    # === 用前端三权重驱动四项权重（剩余给 time），再统一归一化 ===
    w_time_raw = max(0.0, 1.0 - (w_main + w_llm + w_liq))  # 你也可以把这行换成固定 0.10
    _wa, _we, _wl, _wt = w_main, w_llm, w_liq, w_time_raw
    totw = max(1e-9, (_wa + _we + _wl + _wt))
    w_apr, w_edge, w_liq2, w_time = _wa/totw, _we/totw, _wl/totw, _wt/totw
    EPS = 1e-9
    S_agg = ((max(EPS, S_apr))**w_apr) * ((max(EPS, S_edge))**w_edge) * ((max(EPS, S_liq))**w_liq2) * ((max(EPS, S_time))**w_time)

    # ★总分增加一个“全局惩罚”以确保 e<0 时也能压低分（即使 S_edge=0）
    S_agg *= (max(EPS, P) ** W_PENALTY)

    # ★分数拉伸：把 0.12~0.19 的窄区间拉开，同时整体抬高
    S_agg = max(EPS, S_agg) ** CONTRAST

    # 最终评分（Isclear 一票否决）
    Score = 100.0 * (1 if Isclear else 0) * S_agg
    Score = round(Score, 2)
    # 最终评分（IsSubject / IsMatching 一票否决）
    if (IsSubject == 1) or (IsMatching == 1):
        Score = 0
    Score = round(Score, 2)

    # 建议买入股数（保守控仓）
    beta_safe = max(0.0, beta)
    ask_safe = max(MIN_ASK_EPS, ask_price_raw)  # 防止除零
    if depth_qty is not None:
        suggested_qty_raw = depth_qty * beta_safe
    elif depth_usd_safe > 0 and ask_safe > 0:
        estimated_qty = depth_usd_safe / ask_safe
        suggested_qty_raw = estimated_qty * beta_safe
    else:
        suggested_qty_raw = 0.0

    # ★当 e<0 时按 P 缩仓；e>=0 时 P≈1 不影响
    suggested_qty = suggested_qty_raw * max(0.0, P)

    # 单笔集中时提示（不影响数值）
    if top_concentration == 1.0:
        logging.warning("1¢ 深度高度集中（top_concentration_ask_1c=1.0），建议 beta 保守一些（≈0.3）。")

    # 写入输出
    # RightNow 买入信号：分数阈值限定在 [0,100]
    rightnow_threshold = max(0.0, min(100.0, rightnow_buy_score))
    is_rightnow_buy = (Score > rightnow_threshold)
    Outputs[0]['Context'] = f"{Score:.2f}"
    Outputs[1]['Context'] = str(int(round(suggested_qty)))
    Outputs[2]['Boolean'] = bool(is_rightnow_buy)

    return Outputs

# **Function definition**
