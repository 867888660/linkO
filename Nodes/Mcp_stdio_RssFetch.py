import asyncio, os, platform, re, json, html, time, logging
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, parse_qs, unquote

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

# ==========================
# 节点元数据与 IO 槽定义
# ==========================
OutPutNum = 1
InPutNum = 8

Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}',
            'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None,
           'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

FunctionIntroduction='''
这是一个基于 MCP 的 RSS 检索与清洗工具，仅访问白名单源（Google News RSS、Bing News RSS、固定 RSS 池）。

注意：所有字符串输入禁止包含 http/https（除 fixed_rss 的内部映射外）。

```yaml
inputs:
  - name: provider
    type: string
    required: true
    enum: [google_news, bing_news, fixed_rss]
    allow_multi: true  # 逗号分隔，如 "google_news,bing_news"
    description: 选择数据源，支持多源并发抓取、合并去重。

  - name: query
    type: string
    required: false
    default: ""
    applies_to: [google_news, bing_news]
    description: 搜索关键词（不含 URL），支持 OR（如：OpenAI OR Anthropic）。空字符串用于 Google 热点。

  - name: time_window
    type: string
    required: false
    default: "7d"
    enum: ["1h", "24h", "7d", "all"]
    description: 时间窗；中文源常缺发布时间，缺失时视作在窗内；排序用当前时间兜底。

  - name: locale
    type: string
    required: false
    default: "US:en"
    examples: ["US:en", "CN:zh-Hans", "JP:ja"]
    description: 区域与语言。Google 用 hl/gl/ceid；Bing 自动映射 setlang（CN:zh-Hans -> zh-CN）。

  - name: fixed_source
    type: string
    required: false
    applies_to: [fixed_rss]
    enum: [ap, bbc, bbc_world, cnn, guardian, nytimes, aljazeera, toi, jpost, state, whitehouse, unpress, unwebtv]
    description: 固定 RSS 源标识，仅当 provider=fixed_rss 时生效。

  - name: top_k
    type: integer
    required: false
    default: 8
    min: 1
    description: 返回条数上限（全局 Top-K）。

  - name: max_summary_len
    type: integer
    required: false
    default: 180
    description: 文本清洗后摘要的最大字符数。

  - name: strict_xml_only
    type: boolean
    required: false
    default: true
    description: 严格仅接受 XML/RSS；false 时启用原生 HTTP 回退并放宽 Content-Type。

outputs:
  - name: Hits
    type: string
    description: JSON 字符串（数组）。元素字段：title, source_domain, published_at(UTC ISO8601), summary, link(可选)。
```

行为摘要：白名单构造 URL/固定源映射；fetcher-mcp 抓取，非 XML 时原生 HTTP 回退；解析 RSS/Atom 并清洗；
多源并发抓取合并，按时间倒序去重，输出全局 Top-K 紧凑 JSON。'''

# 简易日志工具（控制台与 logging 双输出）
def _log(msg):
    try:
        s = f"[MCP_RSS] {msg}"
        print(s)
        logging.info(s)
    except Exception:
        try:
            print(msg)
        except Exception:
            pass

# 若宿主未配置日志处理器，兜底为 INFO 级别
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

# —— 明确每个输入槽 ——（逐行赋值，与你习惯对齐）
for o in Outputs: o['Kind'] = 'String'

for i in Inputs:  i['Kind'] = 'String'
for i in Inputs:  i['IsLabel'] = False
Inputs[0]['name'] = 'provider'          # String: "google_news" | "bing_news" | "fixed_rss"
Inputs[1]['name'] = 'query'             # String: 关键词（禁止含 http/https）
Inputs[2]['name'] = 'time_window'       # String: "1h"|"24h"|"7d"
Inputs[3]['name'] = 'locale'            # String: "US:en" / "CN:zh-Hans"
Inputs[4]['name'] = 'fixed_source'      # String: 固定 RSS 源标识
Inputs[5]['name'] = 'top_k'             # String: 数值字符串，内部转 int
Inputs[6]['name'] = 'max_summary_len'   # String: 数值字符串，内部转 int
Inputs[7]['Kind'] = 'Boolean'
Inputs[7]['name'] = 'strict_xml_only'   # String: "true"/"false"（不填=默认 true）
Inputs[7]['Boolean'] = True


Outputs[0]['name'] = 'Hits'
Outputs[0]['Kind'] = 'String'

# ==========================
# 工具层：MCP & 抓取
# ==========================
def make_server_params() -> StdioServerParameters:
    env = os.environ.copy()
    is_win = platform.system() == "Windows"
    return StdioServerParameters(
        command="cmd" if is_win else "npx",
        args=["/c", "npx", "-y", "fetcher-mcp"] if is_win else ["-y", "fetcher-mcp"],
        env=env, timeout=20000,
    )

async def mcp_fetch(url: str):
    _log(f"fetch.start url={url}")
    async with stdio_client(make_server_params()) as (r, w):
        async with ClientSession(r, w) as sess:
            await sess.initialize()
            out = await sess.call_tool("fetch_url", arguments={"url": url, "extractContent": False})
            # 兼容不同返回：优先 content / mime / text
            meta = getattr(out, "metadata", {}) or {}
            mime = (meta.get("content_type") or meta.get("mime") or "").lower()
            raw = getattr(out, "content", None)
            if isinstance(raw, (bytes, bytearray)):
                body = raw.decode("utf-8", errors="replace")
            elif isinstance(raw, list):
                body = "".join(str(x) for x in raw)
            else:
                body = str(raw) if raw is not None else ""
            head = body[:120].replace("\n", " ") if body else ""
            _log(f"fetch.done mime={mime} len={len(body)} head={head}")
            return mime, body

# ==========================
# 构造 URL（仅白名单）
# ==========================
def _locale_to_hl_gl_ceid(locale: str):
    # "US:en" -> hl=en, gl=US, ceid=US:en
    if not locale or ":" not in locale:
        return "en", "US", "US:en"
    country, lang = locale.split(":", 1)
    return lang, country, f"{country}:{lang}"

# --- add: locale -> bing setlang 映射 ---
def _bing_lang_from_locale(locale: str) -> str:
    if not locale:
        return "en-US"
    try:
        country, lang = locale.split(":", 1)
    except ValueError:
        country, lang = "US", locale
    lang = lang.lower(); country = country.upper()
    if lang in ("zh-hans", "zh-cn", "zh"):
        return "zh-CN"
    if lang in ("zh-hant", "zh-tw"):
        return "zh-TW"
    if lang.startswith("en"):
        return "en-US" if country == "US" else "en-GB"
    if lang.startswith("ja"): return "ja-JP"
    if lang.startswith("ko"): return "ko-KR"
    if lang.startswith("fr"): return "fr-FR"
    if lang.startswith("de"): return "de-DE"
    if lang.startswith("es"): return "es-ES"
    return f"{lang}-{country}"

def build_rss_url(provider: str, query: str, time_window: str, locale: str, fixed_source: str):
    provider = (provider or "").strip().lower()
    tw = (time_window or "7d").strip().lower()
    q = (query or "").strip()
    if re.search(r'https?://', q, flags=re.I):
        raise ValueError("query 不得包含 URL（http/https）")

    if provider == "google_news":
        hl, gl, ceid = _locale_to_hl_gl_ceid(locale or "US:en")
        q_enc = quote_plus(q.replace(" ", "+"))
        if not q_enc:
            # 顶部热点
            return f"https://news.google.com/rss?hl={hl}&gl={gl}&ceid={ceid}"
        else:
            win = tw if tw in ("1h", "24h", "7d") else "7d"
            return f"https://news.google.com/rss/search?q={q_enc}+when:{win}&hl={hl}&gl={gl}&ceid={ceid}"

    if provider == "bing_news":
        lang = _bing_lang_from_locale(locale or "US:en")
        q_enc = quote_plus(q.replace(" ", "+"))
        if not q_enc:
            raise ValueError("bing_news 需要提供 query")
        return f"https://www.bing.com/news/search?q={q_enc}&setlang={lang}&format=rss"

    if provider == "fixed_rss":
        src = (fixed_source or "").strip().lower()
        fixed_map = {
            "ap":         "https://apnews.com/index.rss",
            "bbc":        "http://feeds.bbci.co.uk/news/rss.xml",
            "bbc_world":  "http://feeds.bbci.co.uk/news/world/rss.xml",
            "cnn":        "http://rss.cnn.com/rss/edition.rss",
            "guardian":   "https://www.theguardian.com/world/rss",
            "nytimes":    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
            "aljazeera":  "https://www.aljazeera.com/xml/rss/all.xml",
            "toi":        "https://www.timesofisrael.com/feed/",
            "jpost":      "https://www.jpost.com/rss",
            "state":      "https://www.state.gov/rss-feeds",
            "whitehouse": "https://www.whitehouse.gov/news/",
            "unpress":    "https://press.un.org/en/content/security-council",
            "unwebtv":    "https://www.un.org/webcast/rss/",
        }
        url = fixed_map.get(src)
        if not url:
            raise ValueError("fixed_rss 需要合法 fixed_source（ap|bbc|bbc_world|...）")
        return url

    raise ValueError("provider 仅支持 google_news|bing_news|fixed_rss")

# ==========================
# 解析与清洗
# ==========================
URL_RE = re.compile(r'https?://\S+', flags=re.I)
TAG_RE = re.compile(r'<[^>]+>')
WS_RE  = re.compile(r'\s+')

def clean_text(s: str, max_len_cn: int = 180):
    if not s:
        return ""
    s = TAG_RE.sub(" ", s)
    s = html.unescape(s)
    s = URL_RE.sub("[URL]", s)
    s = WS_RE.sub(" ", s).strip()
    # 简单按字符截断（中文/英文通吃），更细可按宽度
    if len(s) > max_len_cn:
        s = s[:max_len_cn].rstrip() + "…"
    return s

def extract_domain(link: str, fallback: str = ""):
    m = re.match(r'https?://([^/]+)', link or "", flags=re.I)
    if m:
        return m.group(1).lower()
    return (fallback or "").lower()

# --- add: 解析 bing/google 的外链包装，取真实 URL ---
def _unwrap_redirect(link: str) -> str:
    if not link:
        return link
    try:
        u = urlparse(link)
        host = (u.netloc or "").lower()
        if "bing.com" in host:
            qs = parse_qs(u.query or "")
            for k in ("url", "u"):
                if k in qs and qs[k]:
                    return unquote(qs[k][0])
        if "news.google" in host or "google.com" in host:
            qs = parse_qs(u.query or "")
            if "url" in qs and qs["url"]:
                return unquote(qs["url"][0])
        return link
    except Exception:
        return link

def parse_datetime(dt_str: str):
    if not dt_str:
        return None
    try:
        return parsedate_to_datetime(dt_str).astimezone(timezone.utc)
    except Exception:
        # 尝试 ISO
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return None

def within_window(dt: datetime, window: str, accept_nodate: bool = True):
    if dt is None:
        # 无时间戳：若接收，则视作在当前窗内（all/any 本就放行）
        return True if accept_nodate or str(window).lower() in ("all", "any") else False
    now = datetime.now(timezone.utc)
    if str(window).lower() in ("all", "any"):
        return True
    if window == "1h":
        return (now - dt) <= timedelta(hours=1)
    if window == "24h":
        return (now - dt) <= timedelta(days=1)
    # 默认 7d
    return (now - dt) <= timedelta(days=7)

def parse_rss_xml(xml_text: str, time_window: str, top_k: int, max_summary_len: int):
    # RSS 或 Atom 都用 ElementTree 粗解析
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        raise ValueError("返回内容不是合法 XML/RSS，已拒绝解析。")

    items = []
    rss_cnt_before = 0
    # RSS: channel/item
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link  = (it.findtext("link") or "").strip()
        real_link = _unwrap_redirect(link)
        source_tag = it.find("source")
        src_url = (source_tag.get("url") if source_tag is not None else "") or ""
        pub = (it.findtext("pubDate") or "").strip() or (it.findtext("{http://purl.org/dc/elements/1.1/}date") or "").strip()
        desc = it.findtext("description") or ""
        dt = parse_datetime(pub)
        if not within_window(dt, time_window, accept_nodate=True):
            continue
        domain = extract_domain(real_link, extract_domain(src_url))
        summ = clean_text(desc or title, max_len_cn=max_summary_len)
        items.append({
            "source_domain": domain or "unknown",
            "title": clean_text(title, max_len_cn=200),
            "published_at": (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "summary": summ
            # ,"link": real_link
        })

    # Atom: feed/entry
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        atom_cnt_before = len(items)
        for it in root.findall(".//atom:entry", ns):
            title = (it.findtext("atom:title", default="", namespaces=ns) or "").strip()
            link_el = it.find("atom:link", ns)
            link = link_el.get("href") if link_el is not None else ""
            real_link = _unwrap_redirect(link)
            updated = (it.findtext("atom:updated", default="", namespaces=ns) or "").strip()
            summary = it.findtext("atom:summary", default="", namespaces=ns) or it.findtext("atom:content", default="", namespaces=ns) or ""
            dt = parse_datetime(updated)
            if not within_window(dt, time_window, accept_nodate=True):
                continue
            domain = extract_domain(real_link, "")
            summ = clean_text(summary or title, max_len_cn=max_summary_len)
            items.append({
                "source_domain": domain or "unknown",
                "title": clean_text(title, max_len_cn=200),
                "published_at": (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "summary": summ
                # ,"link": real_link
            })
        atom_cnt = len(items) - atom_cnt_before
    else:
        atom_cnt = 0

    # 去重（title+domain+date）
    seen = set()
    uniq = []
    for x in items:
        key = (x["title"].lower(), x["source_domain"], x["published_at"][:10])
        if key in seen: 
            continue
        seen.add(key)
        uniq.append(x)

    # 按时间倒序
    uniq.sort(key=lambda x: x["published_at"], reverse=True)
    # Top-K
    _log(f"parse.stats rss={rss_cnt_before and len(items) - rss_cnt_before or len(items)} atom={atom_cnt} after_dedupe={len(uniq)} window={time_window} top_k={top_k}")
    return uniq[:max(1, top_k)]

# ==========================
# 节点主逻辑
# ==========================
def _to_int(x, default):
    try:
        return int(float(x))
    except Exception:
        return default

def _to_bool(x, default=True):
    if x is None: return default
    s = str(x).strip().lower()
    if s in ("1","true","yes","y","t"): return True
    if s in ("0","false","no","n","f"): return False
    return default

def _safe_get_input(node, idx, default=None):
    try:
        inputs = (node or {}).get('Inputs') or []
        if not isinstance(inputs, list) or idx < 0 or idx >= len(inputs):
            return default
        entry = inputs[idx]
        if isinstance(entry, dict):
            val = entry.get('Context')
            # 若为布尔型槽且 Context 为空，尝试读取 Boolean 字段
            if val is None and str(entry.get('Kind', '')).lower() == 'boolean':
                val = entry.get('Boolean')
        else:
            val = None
        if val is None:
            return default
        s = str(val)
        return s if len(s) > 0 else default
    except Exception:
        return default

async def _fetch_and_parse(url, strict_xml_only, time_window, top_k, max_summary_len):
    mime, body = await mcp_fetch(url)

    def _is_xml_like(m, b):
        try:
            if (m or "").lower().find("xml") >= 0:
                return True
            head = (b or "")[:200].lower()
            return head.startswith("<?xml") or "<rss" in head or "<feed" in head
        except Exception:
            return False

    # 首次判断
    is_xml = _is_xml_like(mime, body)

    # MCP 有时返回提取后的纯文本，这里尝试原生 HTTP 回退抓取
    if not is_xml:
        _log(f"fallback.raw_http because non-xml from mcp mime={mime}")
        try:
            # 使用标准库 urllib，避免额外依赖
            import urllib.request
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MCP-RSS/1.0",
                "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                mime2 = (resp.headers.get_content_type() or "").lower() if hasattr(resp.headers, 'get_content_type') else (resp.headers.get('Content-Type','')).split(';')[0].lower()
                body2 = resp.read().decode("utf-8", errors="replace")
            _log(f"fallback.raw_http.done mime={mime2} len={len(body2)}")
            if _is_xml_like(mime2, body2):
                mime, body = mime2, body2
                is_xml = True
        except Exception as fe:
            _log(f"fallback.raw_http.error {fe}")

    # 严格只接收 XML/RSS（常见三种）
    if strict_xml_only and not is_xml:
        raise ValueError(f"非 XML/RSS 内容（mime={mime}），已拒绝。")

    parsed = parse_rss_xml(body, time_window, top_k, max_summary_len)
    _log(f"fetch.parse items={len(parsed)} window={time_window}")
    return parsed

async def _fetch_many(urls, strict_xml_only, time_window, top_k, max_summary_len):
    # 为了全局 Top-K，单源适当放大提取数量
    per_feed_k = max(20, int(top_k) if isinstance(top_k, int) else 20)
    _log(f"fetch.batch size={len(urls)} window={time_window} strict={strict_xml_only} per_feed_k={per_feed_k}")
    tasks = [ _fetch_and_parse(u, strict_xml_only, time_window, per_feed_k, max_summary_len) for u in urls ]
    results_all = []
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for res in results:
        if isinstance(res, Exception):
            continue
        results_all.extend(res)
    _log(f"fetch.batch.done merged_items={len(results_all)}")
    return results_all

def _dedupe_and_sort(items):
    seen = set()
    uniq = []
    for x in items or []:
        try:
            key = (str(x.get("title","")) .lower(), str(x.get("source_domain","")), str(x.get("published_at",""))[:10])
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        uniq.append(x)
    uniq.sort(key=lambda x: x.get("published_at",""), reverse=True)
    return uniq

def run_node(node):
    # 读取 Inputs
    provider_raw  = _safe_get_input(node, 0, "google_news")
    query         = _safe_get_input(node, 1, "")
    time_window   = _safe_get_input(node, 2, "7d")
    locale        = _safe_get_input(node, 3, "US:en")
    fixed_source  = _safe_get_input(node, 4, "")
    top_k         = _to_int(_safe_get_input(node, 5, 8), 8)
    max_sum_len   = _to_int(_safe_get_input(node, 6, 180), 180)
    strict_xml    = _to_bool(_safe_get_input(node, 7, None), True)
    _log(f"inputs provider={provider_raw} query={query} window={time_window} locale={locale} fixed_source={fixed_source} top_k={top_k} max_sum_len={max_sum_len} strict={strict_xml}")

    # 支持多源 provider，逗号分隔
    providers = [p.strip().lower() for p in str(provider_raw or "").split(",") if p.strip()]
    if not providers:
        providers = ["google_news"]

    urls = []
    build_errors = []
    for p in providers:
        try:
            url = build_rss_url(p, query, time_window, locale, fixed_source)
            urls.append(url)
        except Exception as e:
            build_errors.append({"provider": p, "error": str(e)})
    _log(f"build urls_count={len(urls)} providers={providers} errors={build_errors}")

    if not urls:
        Outputs[0]['Context'] = json.dumps({"error": "无可用RSS源", "details": build_errors}, ensure_ascii=False)
        return Outputs

    # 抓取并解析
    try:
        win = time_window if time_window in ("1h","24h","7d") else "7d"
        merged = asyncio.run(_fetch_many(urls, strict_xml, win, top_k, max_sum_len))
        _log(f"merge.first items={len(merged)} window={win}")
        final_items = _dedupe_and_sort(merged)[:max(1, top_k)]
        _log(f"dedupe.first items={len(final_items)}")
        # 若按时间窗为空，自动放宽为全部时间再尝试一次
        if not final_items:
            _log("fallback.window=all triggered")
            merged_all = asyncio.run(_fetch_many(urls, strict_xml, "all", max(top_k, 20), max_sum_len))
            _log(f"merge.all items={len(merged_all)}")
            final_items = _dedupe_and_sort(merged_all)[:max(1, top_k)]
            _log(f"dedupe.all items={len(final_items)}")
        Outputs[0]['Context'] = json.dumps(final_items, ensure_ascii=False)
        _log(f"output.size={len(final_items)}")
    except Exception as e:
        payload = {"error": f"抓取/解析失败：{str(e)}"}
        if build_errors:
            payload["build_errors"] = build_errors
        Outputs[0]['Context'] = json.dumps(payload, ensure_ascii=False)

    return Outputs
