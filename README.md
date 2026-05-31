# Hot Topic Fetcher

热搜三级回退抓取工具，用于公众号自动化选题。

## 三级回退机制

1. **知微数据 API** — 主数据源
2. **tophub.today** — HTML 爬虫备用
3. **vvhan API** — 兜底

## 支持平台

微博、抖音、B站、今日头条、百度热点、小红书、知乎热榜

## 使用

```bash
python hotnews_fetcher.py --platform 微博 --count 10
python hotnews_fetcher.py --all
python hotnews_fetcher.py --platform 微博 --select
```

## 测试

```bash
python -m unittest test_hotnews.py -v
```
