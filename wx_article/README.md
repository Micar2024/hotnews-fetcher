# 公众号文章生成工作流 v1

## 流程概览

```
飞书文档/素材 → 火灵儿写稿 → 多轮反馈迭代 → Mdnice 排版 → 公众号发布
```

## 文件说明

| 文件 | 用途 |
|---|---|
| `wx_article_draft.md` | 文章 Markdown 终稿（纯内容，无排版） |
| `wx_article_mdnice.md` | Mdnice 排版版（引用块做卡片，可直接粘贴到 Mdnice） |
| `wx_article.html` | 公众号内联 CSS HTML 版（备用，不推荐直接粘贴） |

## 排版方案：Mdnice（推荐）

公众号后台会过滤 `section`/`table` 的 `background` 样式，直接粘贴 HTML 会丢失卡片效果。

**正确做法：**

1. 打开 [Mdnice](https://editor.mdnice.com/)
2. 粘贴 `wx_article_mdnice.md` 内容到左侧编辑器
3. 选主题（推荐「默认」或「科技蓝」）
4. 点「复制到公众号」
5. 粘贴到公众号后台编辑器
6. 替换图片链接（先上传到公众号素材库）

### Mdnice 排版约定

- 卡片用引用块 `>` + 加粗标题
- 核心判断单独一行引用块
- 清单用有序列表嵌套在引用块里
- 图片用标准 Markdown `![alt](url)`
- 不用 HTML 标签（公众号会过滤）

## 配图规范

公众号正文配图建议：**900×500px 横图**

第一篇文章用了 3 张流程图：
1. **错误链路图** — 任务 → AI 执行 → AI 自审 → 合入 → Bug
2. **正确链路图** — Issue → Codex → Claude → ChatGPT → 人 → GitHub
3. **最小闭环图** — Issue → PR → Review → Merge

图片生成工具待定（xAI API key 未配置），可手动画或用 Canva。

## 写作纪律

- 参考卡兹克风格：口语化、无套话、不用表格、去装饰性元素
- 先结论后原因，先动作后解释
- 段落间距适中，适合手机阅读
- 标题 6-12 字，从内容提炼
- 正文 15px，行高 1.75-2.0
- 卡片突出核心判断，不堆砌信息

## 迭代记录

- v1.0：初稿，多 Agent 协作角度
- v1.1：重心转到「不要 AI 自己审自己 + GitHub 事实源 + ChatGPT 独立 PM Review」
- v1.2：卡兹克风格改造，口语化，加私人视角
- v1.3：排版 HTML 版（section 卡片），公众号后台过滤样式
- v1.4：转 Mdnice Markdown 版，引用块做卡片，成功发布

## 系列文章：AI Agent 飞书卡片自定义

| 篇目 | 文件 | Agent | 技术栈 | 状态 |
|---|---|---|---|---|
| 第 1 篇 | `wx_hermes_card_tutorial.md` | Hermes/火灵儿 | Python + hook | 初稿完成 |
| 第 2 篇 | 待写 | OpenClaw/宁姚 | Node.js + CardKit | 待定 |
| 第 3 篇 | 待写 | GenericAgent/云曦 | Python + _TaskCard | 待定 |
