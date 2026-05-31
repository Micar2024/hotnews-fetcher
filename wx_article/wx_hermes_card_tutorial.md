# Hermes Agent 飞书卡片自定义：从纯文本到交互式状态卡片

> 这是「AI Agent 飞书卡片自定义」系列的第一篇。系列基于 OpenClaw、Hermes、GenericAgent 三个 Agent 的真实踩坑经验，讲怎么把 AI Agent 的飞书消息从默认纯文本改造成带状态、颜色、emoji、多卡拆分的交互式卡片。

## 你的 Agent 现在长什么样

如果你刚装好 Hermes Agent，接上了飞书，跑了一个任务，你会收到一条纯文本消息。

大概是这样：

```
搜索完成。找到了 5 个结果，已整理如下：
1. xxx
2. xxx
...
```

能用。但有几个问题：

- 看不出任务是成功了还是失败了
- 看不出用了多长时间、调了几次 API
- 长回答会被截断，或者变成一大坨文字
- 多个任务同时跑的时候，分不清哪条消息对应哪个任务

飞书支持 Interactive Card（交互式卡片），可以做到带颜色的状态头、结构化的正文、底部元信息。Hermes 默认没有这个功能，需要自己接。

## 整体思路

Hermes 有一个 hook 机制：每次 Agent 完成任务后，会触发一个 `agent:end` 事件。我们可以注册一个 hook，监听这个事件，在回调里构建卡片 JSON，然后通过飞书 API 发出去。

整个链路是这样的：

```
用户发消息 → Hermes 处理 → agent:end 触发 → hook 回调 → 构建卡片 JSON → 飞书 API 发送
```

我们需要写的东西只有一个 Python 脚本 + 一个 hook 配置文件。

## 第一步：创建 hook 配置

在 `~/.hermes/hooks/feishu-card/` 目录下创建 `HOOK.yaml`：

```yaml
name: feishu-card
description: "Send Feishu interactive message cards for final agent responses."
events:
  - agent:end
```

这就注册了一个 hook。Hermes 每次跑完任务，都会调用这个目录下的脚本。

## 第二步：理解飞书卡片的 JSON 结构

飞书 Interactive Card 的核心结构长这样：

```json
{
  "config": {"wide_screen_mode": true},
  "header": {
    "template": "indigo",
    "title": {"tag": "plain_text", "content": "🔍 已完成｜搜索结果"}
  },
  "elements": [
    {"tag": "markdown", "content": "正文内容"},
    {"tag": "hr"},
    {"tag": "div", "text": {"tag": "lark_md", "content": "⏱ 3s · gpt-5.5 · 调用API 1 次"}}
  ]
}
```

几个关键字段：

- `header.template`：卡片头部颜色。支持 blue、wathet、turquoise、green、yellow、orange、red、carmine、violet、purple、indigo、grey、default
- `header.title.content`：标题文字
- `elements`：卡片正文，支持 markdown、分割线、div 等元素

## 第三步：状态颜色映射

最基础的定制是根据任务状态显示不同颜色：

```python
def _status_template(status: str) -> str:
    return {
        "已完成": "indigo",
        "需确认": "yellow",
        "失败": "red"
    }.get(status, "indigo")
```

我们选了 indigo 作为默认色。这个选择经过了四轮测试：

1. 第一版用 green —— 太像成功提示，视觉上没有区分度
2. 改成 wathet —— 太淡，手机上几乎看不清
3. 改成 turquoise —— 还行，但跟飞书默认的链接色撞了
4. 最终定 indigo —— 稳重、有辨识度、不刺眼

状态判断逻辑也很简单：

```python
def _determine_card_status(response, agent_failed, error_text=""):
    if agent_failed:
        return "失败"
    if error_text:
        for kw in ["工具调用", "调用失败", "报错", "异常", "timeout", "超时"]:
            if kw in error_text.lower():
                return "失败"
    for kw in ["不确定", "请确认", "无法确定", "需要你"]:
        if kw in response:
            return "需确认"
    return "已完成"
```

关键词命中就切换状态。不需要复杂的 NLP，简单的字符串匹配就够用。

## 第四步：标题提取

卡片标题不能直接截断用户原文。用户说「帮我查一下最近的 AI 新闻，要包含 OpenAI 和 Anthropic 的」，标题不应该把这句话原封不动塞进去。

我们需要从用户输入里提取一个短标签：

```python
# 动词 + 关键词提取
_ACTION_VERB_RE = re.compile(
    r"^(搜索|查一下|查|查找|分析|处理|生成|创建|写|修改|翻译|总结|整理|部署|安装|配置)"
)

def _extract_title_from_query(user_query: str) -> str:
    # 1. 去掉状态前缀（已完成｜...）
    cleaned = strip_status_prefix(user_query)
    
    # 2. 去掉礼貌前缀
    for prefix in ["帮我", "给我", "请你", "麻烦你", "请问"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    
    # 3. 提取动词 + 第一个关键词
    match = _ACTION_VERB_RE.match(cleaned)
    if match:
        action = match.group(1)
        remainder = cleaned[match.end():].strip()
        keyword = remainder.split("，")[0][:8]  # 取逗号前 8 个字
        return f"{action}{keyword}"
    
    return "处理结果"  # 兜底
```

最终效果：

| 用户输入 | 卡片标题 |
|---|---|
| 帮我查一下最近的 AI 新闻 | 搜索最近的 AI 新闻 |
| 分析一下这个项目的代码质量 | 分析这个项目的代码 |
| 好的 | 处理结果 |
| 修一下那个 bug | 修复那个 bug |

## 第五步：任务类型 emoji

标题前面加一个 emoji，一眼看出这是什么类型的任务：

```python
_TYPE_EMOJI_RULES = [
    (["搜索", "查找", "查一下", "search"], "🔍"),
    (["数据", "分析", "统计", "图表"], "📊"),
    (["写", "文章", "文案", "翻译", "总结"], "✍️"),
    (["调试", "debug", "排查", "修复", "fix"], "🔧"),
    (["安装", "配置", "部署", "deploy"], "📦"),
    (["网络", "api", "http", "代理"], "🌐"),
    (["文件", "读取", "写入", "目录"], "📁"),
    (["模型", "llm", "gpt", "训练"], "🤖"),
    ([], "📋"),  # 兜底
]
```

匹配规则是数命中关键词数量，选最多的那个 emoji。没有命中就用 📋。

最终标题格式：`{emoji} {状态}｜{短任务名}`

例如：`🔍 已完成｜搜索AI新闻`、`🔧 失败｜修复登录bug`

## 第六步：底部元信息

卡片底部显示运行元信息：耗时、模型、API 调用次数、上下文占用。

```python
def _build_footer(payload):
    model = payload.get("model", "unknown")
    elapsed = format_seconds(payload.get("response_time_seconds"))
    api_calls = payload.get("api_calls", 0)
    
    footer = f"⏱ {elapsed} · {model} · 调用API {api_calls} 次"
    
    # 上下文占用进度条
    used = payload.get("last_prompt_tokens", 0)
    total = resolve_context_window(payload)
    if used > 0 and total > 0:
        pct = used / total * 100
        filled = round(pct / 10)
        bar = "█" * filled + "░" * (10 - filled)
        footer += f" · 上下文 {used//1000:.1f}k/{total//1000:.1f}k [{bar}] {pct:.1f}%"
    
    return footer
```

效果：`⏱ 3s · gpt-5.5 · 调用API 1 次 · 上下文 2.1k/128k [█░░░░░░░░░] 1.6%`

这个进度条是纯文本拼的，用 `<text_tag>` 包一下可以加颜色：

```python
f"<text_tag color='{pct_color(pct)}'>[{bar}] {pct_str}</text_tag>"
```

低于 35% 绿色，35-60% 黄色，60-80% 橙色，80% 以上红色。

## 第七步：多卡拆分

飞书单张卡片有 30KB 的 payload 上限。长回答需要拆成多张卡片。

```python
MAX_MARKDOWN_CHARS_PER_CARD = 5200
MAX_CARD_COUNT = 6

def split_markdown(text, max_chars):
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    current = []
    current_len = 0
    
    for block in re.split(r"\n\s*\n", text):
        if current_len + len(block) > max_chars:
            chunks.append("\n\n".join(current))
            current = [block]
            current_len = len(block)
        else:
            current.append(block)
            current_len += len(block)
    
    if current:
        chunks.append("\n\n".join(current))
    
    return chunks
```

拆分规则：

- 按空行分段，不在段落中间切
- 每张卡片最多 5200 字符
- 最多 6 张卡片，超出部分截断并提示
- 第一张卡片带工具摘要，后续卡片不带（省空间）
- 标题带编号：`搜索结果 (1/3)`、`搜索结果 (2/3)`

## 第八步：组装完整卡片

把上面所有组件拼起来：

```python
def build_card(content, title, status, footer, index, total, type_emoji, tool_summary=""):
    display_title = title if total == 1 else f"{title} ({index}/{total})"
    header_text = f"{type_emoji} {status}｜{display_title}"
    template = status_template(status)
    
    elements = [{"tag": "markdown", "content": content}]
    
    if tool_summary:
        elements.append({"tag": "markdown", "content": tool_summary})
        elements.append({"tag": "hr"})
    
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": footer}
    })
    
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": header_text}
        },
        "elements": elements
    }
```

## 踩过的坑

### 坑 1：shell_hooks 误判

Hermes 的 hook 系统会扫描 `~/.hermes/hooks/` 目录下的配置文件。但它的 `shell_hooks` 模块会把 `feishu-card` 的 HOOK.yaml 误判为 shell hook 配置，导致报警 `unknown hook event`。

修复方式：在 shell_hooks 解析器里加一个判断，遇到 `{enabled: true, path: ...}` 结构的配置块就跳过。

```python
def _looks_like_gateway_hook_config(block):
    """判断这是 gateway hook 配置还是 shell hook 配置"""
    return "enabled" in block and "path" in block
```

### 坑 2：自愈巡检的过度设计

一开始写了一个 cron job，每隔几小时检查 `feishu_card_send.py` 的 patch 是否还在，丢了就自动修复。

后来发现这完全是过度设计。hook 机制本身就是持久的，不需要额外巡检。把 cron job 关了，代码清净了。

### 坑 3：颜色选型

前面说过，indigo 是第四版。每一版都有问题：

- green：太普通，飞书默认绿色太多
- wathet：太淡，手机上几乎看不见
- turquoise：跟飞书链接色撞车
- indigo：最终版，稳重有辨识度

建议：直接在飞书里发几张不同颜色的卡片，用手机看一遍再定。

### 坑 4：敏感信息泄露

卡片 footer 会显示模型名和 API 调用信息。如果工具调用的参数里有 API key、token、密码，需要在构建卡片前脱敏：

```python
_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s'\"]+"),
    re.compile(r"(?i)(sk|xox[baprs]|gh[pousr])-[A-Za-z0-9_\-]{8,}"),
]

def redact_preview(text):
    for pattern in _SENSITIVE_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text
```

## 最终效果

一张完整卡片长这样：

```
┌─────────────────────────────────────┐
│ 🔍 已完成｜搜索AI新闻              │ ← indigo 色头部
├─────────────────────────────────────┤
│                                     │
│ 找到 5 条相关新闻，已整理如下：     │ ← 正文 markdown
│ 1. OpenAI 发布 GPT-5...            │
│ 2. Anthropic 宣布 Claude 4...      │
│                                     │
├────────────────────────────────────┤
│ **工具摘要**                        │ ← 工具调用摘要
│ - `web_search` · 完成 · 2.1s       │
│ - `web_extract` · 完成 · 1.8s      │
├────────────────────────────────────┤
│ ⏱ 4s · gpt-5.5 · 调用API 2 次    │ ← footer 元信息
│ · 上下文 3.2k/128k [█░░░░░░░░░] 2.5% │
└────────────────────────────────────┘
```

## 完整代码

完整脚本约 600 行，包含：

- 标题提取（动词+关键词、意图分类、兜底策略）
- 状态判断（失败/需确认/已完成）
- emoji 映射（11 种任务类型 + 默认）
- footer 构建（耗时、模型、API 次数、上下文进度条）
- 多卡拆分（按空行分段、字数预算、截断提示）
- 敏感信息脱敏

代码在 `~/.hermes/scripts/feishu_card_send.py`，hook 配置在 `~/.hermes/hooks/feishu-card/HOOK.yaml`。

## 你可以定制的部分

1. **颜色**：改 `_status_template()` 的映射字典
2. **emoji**：改 `_TYPE_EMOJI_RULES` 的关键词列表
3. **标题**：改 `_extract_title_from_query()` 的提取规则
4. **footer**：改 `_build_footer()` 的格式和字段
5. **拆分阈值**：改 `MAX_MARKDOWN_CHARS_PER_CARD`（默认 5200）
6. **最大卡片数**：改 `MAX_CARD_COUNT`（默认 6）

每个参数都是独立的，改一个不影响其他。

## 下一篇

第二篇讲 OpenClaw/宁姚的卡片定制。OpenClaw 用 Node.js 的 CardKit 实现流式更新（typewriter effect），架构完全不同，但核心问题一样：怎么让 AI Agent 的飞书消息看起来不像机器人发的。
