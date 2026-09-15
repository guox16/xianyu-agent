import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.knowledge.quark import QuarkClient, QuarkError, import_catalog, parse_share, scan
from app.knowledge.workflow import KnowledgeBase


def folder(fid, name):
    return dict(fid=fid, file_name=name, dir=True)


class QuarkTests(unittest.TestCase):
    def test_validates_share_host_and_reads_code(self):
        self.assertEqual(parse_share("https://pan.quark.cn/s/abc?pwd=1234"), ("abc", "1234"))
        for url in ["https://evil.test/s/abc", "https://pan.quark.cn@evil.test/s/abc", "file:///s/abc"]:
            with self.assertRaises(QuarkError):
                parse_share(url)

    def test_pagination_uses_total_even_for_short_page(self):
        client = QuarkClient("https://pan.quark.cn/s/abc")
        responses = [dict(data=dict(stoken="secret")),
                     dict(data=dict(list=[folder("1", "甲")] ), metadata=dict(_total=2)),
                     dict(data=dict(list=[folder("2", "乙")] ), metadata=dict(_total=2))]
        with patch.object(client, "_request", side_effect=responses) as request:
            self.assertEqual(len(client.list_folder()), 2)
            self.assertEqual(request.call_args.kwargs["params"]["_page"], 2)

    def test_repeated_or_incomplete_page_fails(self):
        for batch in [[folder("1", "甲")], []]:
            client = QuarkClient("https://pan.quark.cn/s/abc")
            client.token = "secret"
            with patch.object(client, "_request", side_effect=[
                dict(data=dict(list=[folder("1", "甲")]), metadata=dict(_total=2)),
                dict(data=dict(list=batch), metadata=dict(_total=2)),
            ]):
                with self.assertRaises(QuarkError):
                    client.list_folder()

    def test_scans_categories_not_game_contents_and_preserves_existing(self):
        client = QuarkClient("https://pan.quark.cn/s/abc")
        tree = {"0": [folder("a", "游戏合集")],
                "a": [folder("b", "ABCD  "), folder("skip", "游戏模拟器及其它软件")],
                "b": [folder("g1", "《游戏甲》v1"), folder("g2", "《游戏甲》v2"),
                      folder("g3", "名称不清楚"), dict(fid="txt", file_name="FAQ.txt", dir=False)]}
        with patch.object(client, "list_folder", side_effect=lambda fid: tree[fid]):
            report = scan(client)
        self.assertEqual(len(report["games"]), 3)
        self.assertEqual(len(report["skipped"]), 2)
        self.assertEqual(report["games"][-1]["status"], "补充失败")
        with TemporaryDirectory() as directory:
            kb = KnowledgeBase(Path(directory))
            kb.register(["游戏甲"])
            entries = kb.entries()
            entries[0].update(status="已补充", material_file="existing.md")
            (kb.root / "existing.md").write_text("已有资料", encoding="utf-8")
            kb._write(kb.catalog_file, entries)
            self.assertEqual(import_catalog(kb, report), 1)
            self.assertEqual(import_catalog(kb, report), 0)
            self.assertEqual(kb.lookup("游戏甲")["content"], "已有资料")
            self.assertIsNone(kb.entries()[1]["last_attempt_at"])

    def test_scan_failure_does_not_change_catalog(self):
        with TemporaryDirectory() as directory:
            kb = KnowledgeBase(Path(directory))
            kb.register(["原游戏"])
            original = kb.catalog_file.read_bytes()
            client = QuarkClient("https://pan.quark.cn/s/abc")
            with patch.object(client, "list_folder", side_effect=[
                [folder("a", "ABCD"), folder("g", "《游戏》")], QuarkError("连接失败"),
            ]):
                with self.assertRaises(QuarkError):
                    import_catalog(kb, scan(client))
            self.assertEqual(kb.catalog_file.read_bytes(), original)
