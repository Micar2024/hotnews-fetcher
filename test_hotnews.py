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
                    items = hotnews.get_platform_news("微博", 10)

        self.assertEqual("兜底热点", items[0]["name"])

    def test_platform_news_returns_empty_when_all_levels_fail(self):
        with patch("hotnews_fetcher.get_zhiwei_hotnews", side_effect=RuntimeError("down")):
            with patch("hotnews_fetcher.get_tophub_hotnews", side_effect=RuntimeError("down")):
                with patch(
                    "hotnews_fetcher._get_vvhan_platforms_hotnews",
                    side_effect=RuntimeError("down"),
                ):
                    items = hotnews.get_platform_news("微博", 10)

        self.assertEqual([], items)

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
