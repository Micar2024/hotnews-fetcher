import random
import unittest
from unittest.mock import patch

import hotnews_fetcher as hotnews


class FakeResponse:
    def __init__(self, data=None, text="", status_code=200):
        self._data = data
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


class HotnewsFetcherTests(unittest.TestCase):
    def setUp(self):
        cache_clear = getattr(hotnews._get_vvhan_platforms_hotnews, "cache_clear", None)
        if cache_clear:
            cache_clear()

    def assert_news_item(self, item):
        self.assertEqual({"name", "rank", "lastCount", "url"}, set(item))
        self.assertIsInstance(item["name"], str)
        self.assertIsInstance(item["rank"], int)

    def test_zhiwei_returns_normalized_list(self):
        payload = {
            "data": {
                "list": [
                    {
                        "keyword": "热点一",
                        "rank": 3,
                        "hotValue": 1234,
                        "url": "https://example.com/a",
                    }
                ]
            }
        }
        with patch("hotnews_fetcher.requests.get", return_value=FakeResponse(payload)):
            items = hotnews.get_zhiwei_hotnews("微博")

        self.assertEqual(1, len(items))
        self.assert_news_item(items[0])
        self.assertEqual("热点一", items[0]["name"])
        self.assertEqual(3, items[0]["rank"])
        self.assertEqual(1234, items[0]["lastCount"])
        self.assertEqual("https://example.com/a", items[0]["url"])

    def test_tophub_returns_normalized_list(self):
        html = """
        <html><body>
          <div class="cc-cd">
            <div class="cc-cd-is"><span>微博</span></div>
            <a href="/n/KqndgxeLl9">微博热搜</a>
          </div>
          <table>
            <tr><td class="al"><a href="https://weibo.com/search">热点二</a></td><td>88万</td></tr>
          </table>
        </body></html>
        """
        with patch("hotnews_fetcher.requests.get", return_value=FakeResponse(text=html)):
            items = hotnews.get_tophub_hotnews("微博", 1)

        self.assertEqual(1, len(items))
        self.assert_news_item(items[0])
        self.assertEqual("热点二", items[0]["name"])
        self.assertEqual(1, items[0]["rank"])
        self.assertEqual("88万", items[0]["lastCount"])
        self.assertEqual("https://weibo.com/search", items[0]["url"])

    def test_vvhan_returns_normalized_list(self):
        payload = {
            "data": {
                "weibo": [
                    {
                        "title": "热点三",
                        "hot": "456",
                        "url": "https://example.com/c",
                    }
                ]
            }
        }
        with patch("hotnews_fetcher.requests.get", return_value=FakeResponse(payload)):
            items = hotnews.get_vvhan_hotnews()

        self.assertEqual(1, len(items))
        self.assert_news_item(items[0])
        self.assertEqual("热点三", items[0]["name"])

    def test_platform_news_falls_back_when_upper_level_fails(self):
        with patch("hotnews_fetcher.get_zhiwei_hotnews", side_effect=RuntimeError("down")):
            with patch("hotnews_fetcher.get_tophub_hotnews", return_value=[]):
                with patch(
                    "hotnews_fetcher._get_vvhan_platforms_hotnews",
                    return_value={
                        "微博": [
                            {
                                "name": "兜底热点",
                                "rank": 1,
                                "lastCount": "1万",
                                "url": "https://example.com/fallback",
                            }
                        ]
                    },
                ):
                    with self.assertLogs("hotnews_fetcher", level="WARNING") as logs:
                        items = hotnews.get_platform_news("微博", 10)

        self.assertEqual("兜底热点", items[0]["name"])
        self.assertIn("微博", "\n".join(logs.output))

    def test_platform_news_rejects_unsupported_platform(self):
        with self.assertRaises(ValueError):
            hotnews.get_platform_news("不存在的平台", 10)

    def test_platform_news_logs_fallback_failures(self):
        with patch("hotnews_fetcher.get_zhiwei_hotnews", side_effect=RuntimeError("zhiwei down")):
            with patch("hotnews_fetcher.get_tophub_hotnews", side_effect=RuntimeError("tophub down")):
                with patch(
                    "hotnews_fetcher._get_vvhan_platforms_hotnews",
                    side_effect=RuntimeError("vvhan down"),
                ):
                    with self.assertLogs("hotnews_fetcher", level="WARNING") as logs:
                        items = hotnews.get_platform_news("微博", 10)

        self.assertEqual([], items)
        output = "\n".join(logs.output)
        self.assertIn("微博", output)
        self.assertIn("zhiwei down", output)
        self.assertIn("tophub down", output)
        self.assertIn("vvhan down", output)

    def test_platform_news_returns_empty_when_all_levels_fail(self):
        with patch("hotnews_fetcher.get_zhiwei_hotnews", side_effect=RuntimeError("down")):
            with patch("hotnews_fetcher.get_tophub_hotnews", side_effect=RuntimeError("down")):
                with patch(
                    "hotnews_fetcher._get_vvhan_platforms_hotnews",
                    side_effect=RuntimeError("down"),
                ):
                    with self.assertLogs("hotnews_fetcher", level="WARNING"):
                        items = hotnews.get_platform_news("微博", 10)

        self.assertEqual([], items)

    def test_get_all_platforms_news_reuses_vvhan_fallback_response(self):
        payload = {"data": {"weibo": [{"title": "缓存热点", "url": "https://example.com/cache"}]}}
        with patch("hotnews_fetcher.get_zhiwei_hotnews", return_value=[]):
            with patch("hotnews_fetcher.get_tophub_hotnews", return_value=[]):
                with patch("hotnews_fetcher.requests.get", return_value=FakeResponse(payload)) as request_get:
                    data = hotnews.get_all_platforms_news(1)

        self.assertEqual("缓存热点", data["微博"][0]["name"])
        self.assertEqual(1, request_get.call_count)

    def test_tophub_returns_empty_when_platform_card_missing(self):
        html = """
        <html><body>
          <table>
            <tr><td class="al"><a href="https://example.com/fake">不属于目标平台的全页热点</a></td></tr>
          </table>
        </body></html>
        """
        with patch("hotnews_fetcher.requests.get", return_value=FakeResponse(text=html)):
            items = hotnews.get_tophub_hotnews("微博", 10)

        self.assertEqual([], items)

    def test_select_platform_topic_rejects_empty_list(self):
        with patch("hotnews_fetcher.get_platform_news", return_value=[]):
            with self.assertRaises(RuntimeError):
                hotnews.select_platform_topic("微博", 10)

    def test_normalize_count_handles_boundaries(self):
        self.assertEqual(1, hotnews._normalize_count(0))
        self.assertEqual(1, hotnews._normalize_count(-3))
        self.assertEqual(10, hotnews._normalize_count(None))
        self.assertEqual(10, hotnews._normalize_count("abc"))
        self.assertEqual(7, hotnews._normalize_count("7"))

    def test_safe_int_handles_empty_and_non_numeric_values(self):
        self.assertEqual(5, hotnews._safe_int(None, 5))
        self.assertEqual(5, hotnews._safe_int("不是数字", 5))
        self.assertEqual(5, hotnews._safe_int("", 5))

    def test_normalize_news_item_filters_unsafe_url_protocols(self):
        item = hotnews._normalize_news_item(
            {"title": "危险链接", "url": "javascript:alert(1)"},
            0,
        )

        self.assertEqual("", item["url"])

    def test_weighted_random_prefers_higher_rank_with_deterministic_choice(self):
        items = [
            {"name": "第一", "rank": 1, "lastCount": "10", "url": "u1"},
            {"name": "第二", "rank": 2, "lastCount": "9", "url": "u2"},
            {"name": "第三", "rank": 3, "lastCount": "8", "url": "u3"},
        ]
        with patch("hotnews_fetcher.get_platform_news", return_value=items):
            with patch.object(random, "choices", wraps=random.choices) as choices:
                selected = hotnews.select_platform_topic("微博", 3)

        weights = choices.call_args.kwargs["weights"]
        self.assertEqual([1.0, 0.25, 1 / 9], weights)
        self.assertIn(selected, items)


if __name__ == "__main__":
    unittest.main()
