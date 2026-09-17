"""本地分块的 BM25 关键词检索，不调用模型或远程接口。"""

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import unicodedata

import jieba


_STOP_WORDS = frozenset("的 了 呢 吗 啊 请问 我 想 知道 怎么 如何 这个 一下".split())
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[._+-][a-z0-9]+)*|[\u3400-\u9fff]+")


def _name_key(name):
    # 不去掉版本、作品编号或副标题，避免把不同商品混在一起。
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", name).casefold())


class BM25Retriever:
    """从分块建立只读内存索引；资料更新后重新创建实例。

    文档与查询使用相同分词规则；采用正值 IDF 的 BM25，k1=1.2、b=0.75。
    统计量基于整个索引，游戏过滤在取前 top_k 之前完成。
    """

    def __init__(self, chunks):
        self._chunks = deepcopy(list(chunks))
        self._tokenizer = jieba.Tokenizer()
        self._postings = defaultdict(dict)
        self._names = defaultdict(set)
        self._lengths = []
        ids = set()
        for index, chunk in enumerate(self._chunks):
            if chunk["chunk_id"] in ids:
                raise ValueError("分块编号重复，请重新生成分块。")
            ids.add(chunk["chunk_id"])
            for name in [chunk["game_name"], *chunk.get("aliases", [])]:
                self._names[_name_key(name)].add(chunk["game_name"])
            text = "\n".join([
                chunk.get("search_text") or "\n".join([
                    chunk["game_name"], chunk.get("section", ""), chunk["content"],
                ]),
                *chunk.get("aliases", []),
            ])
            frequencies = Counter(self._tokens(text))
            self._lengths.append(sum(frequencies.values()))
            for token, frequency in frequencies.items():
                self._postings[token][index] = frequency
        self._average_length = sum(self._lengths) / len(self._chunks) if self._chunks else 0

    def _tokens(self, text):
        normalized = unicodedata.normalize("NFKC", text).casefold()
        tokens = []
        for part in _TOKEN_PATTERN.findall(normalized):
            # 英文、版本号和错误码保留完整形式，中文使用搜索模式分词。
            pieces = self._tokenizer.cut_for_search(part, HMM=False) if ord(part[0]) >= 0x3400 else [part]
            tokens.extend(piece for piece in pieces if piece not in _STOP_WORDS)
        return tokens

    def search(self, query, *, game_name=None, top_k=5):
        """返回按分数排序的分块及命中词；空查询或无词命中返回空列表。

        游戏按名称或别名匹配；未知名称不回退全库，歧义名称抛出 ValueError。
        分数只表示关键词相关程度，不能作为事实可信度或可回答性的判断。
        """
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("返回数量必须是正整数。")
        selected = None
        if game_name is not None:
            matches = self._names.get(_name_key(game_name), set())
            if not matches:
                return []
            if len(matches) > 1:
                raise ValueError("游戏名称或别名存在歧义，请使用明确的游戏名称。")
            selected = next(iter(matches))
        terms = sorted(set(self._tokens(query)))
        scores, matched = defaultdict(float), defaultdict(list)
        count = len(self._chunks)
        for term in terms:
            postings = self._postings.get(term, {})
            if not postings:
                continue
            # 正值 IDF 让仅一条资料或全体都命中的词仍可参与排序。
            idf = math.log1p((count - len(postings) + 0.5) / (len(postings) + 0.5))
            for index, frequency in postings.items():
                if selected is not None and self._chunks[index]["game_name"] != selected:
                    continue
                norm = 1.2 * (0.25 + 0.75 * self._lengths[index] / self._average_length)
                scores[index] += idf * frequency * 2.2 / (frequency + norm)
                matched[index].append(term)
        ordered = sorted(scores, key=lambda index: (-scores[index], self._chunks[index]["chunk_id"]))[:top_k]
        return [dict(deepcopy(self._chunks[index]), bm25_score=scores[index],
                     matched_terms=matched[index], rank=rank, retrieval_method="bm25")
                for rank, index in enumerate(ordered, 1)]


def main():
    from app.core.config import PROJECT_ROOT
    from app.knowledge.workflow import KnowledgeBase

    parser = argparse.ArgumentParser(description="使用 BM25 检索本地游戏资料。")
    parser.add_argument("query", help="关键词或问题")
    parser.add_argument("--game", help="限定游戏名称或已登记别名")
    parser.add_argument("--top-k", type=int, default=5, help="最多返回多少个分块")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT / "materials", help="知识库目录")
    args = parser.parse_args()
    try:
        results = KnowledgeBase(args.root).search(args.query, game_name=args.game, top_k=args.top_k)
    except (OSError, ValueError) as error:
        parser.exit(1, f"检索失败：{error}\n")
    print(json.dumps({"results": results, "message": "检索完成" if results else "没有匹配的资料"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
