"""将 BM25 和语义检索的候选排名按 RRF 融合。"""

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path


def _positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label}必须是正整数。")


def reciprocal_rank_fusion(bm25_results, semantic_results, *, top_k=5, rrf_k=60):
    """按有序列表中的名次计算 Σ 1/(rrf_k + 名次)，不相加原始分数。

    名次从 1 开始；同一路重复分块只计一次，两路按 chunk_id 去重。
    同分按 chunk_id 排序，输入列表及其中的元数据不会被修改。
    """
    _positive_integer(top_k, "返回数量")
    _positive_integer(rrf_k, "RRF 平滑参数")
    merged = {}
    for method, results in (("bm25", bm25_results), ("semantic", semantic_results)):
        seen = set()
        for result in results:
            chunk_id = result["chunk_id"]
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            rank = len(seen)
            if chunk_id not in merged:
                merged[chunk_id] = dict(
                    deepcopy(result), rrf_score=0.0, retrieval_method="hybrid",
                    bm25_rank=None, semantic_rank=None, bm25_score=None,
                    semantic_score=None, matched_terms=[],
                )
            item = merged[chunk_id]
            item[method + "_rank"] = rank
            item[method + "_score"] = result.get(method + "_score")
            item["rrf_score"] += 1.0 / (rrf_k + rank)
            if method == "bm25":
                item["matched_terms"] = list(result.get("matched_terms", []))
    ordered = sorted(merged.values(), key=lambda item: (-item["rrf_score"], item["chunk_id"]))
    return [dict(item, rank=rank) for rank, item in enumerate(ordered[:top_k], 1)]


class HybridRetriever:
    """复用同一份资料快照的两路检索器；任一路异常向调用方报告。"""

    def __init__(self, bm25, semantic):
        self._bm25 = bm25
        self._semantic = semantic

    def search(self, query, *, game_name=None, top_k=5, candidate_k=None,
               rrf_k=60, semantic_min_score=None):
        """两路各召回 candidate_k 条，再融合截取 top_k 条。

        candidate_k 默认 max(10, top_k)。语义阈值仅过滤语义候选，
        不过滤 BM25 命中；空结果可参与融合，但异常不伪装成空结果。
        """
        _positive_integer(top_k, "返回数量")
        _positive_integer(rrf_k, "RRF 平滑参数")
        if candidate_k is None:
            candidate_k = max(10, top_k)
        _positive_integer(candidate_k, "每路候选数量")
        if candidate_k < top_k:
            raise ValueError("每路候选数量不能小于最终返回数量。")
        if semantic_min_score is not None and (
            isinstance(semantic_min_score, bool)
            or not isinstance(semantic_min_score, (int, float))
            or not math.isfinite(semantic_min_score)
            or not -1 <= semantic_min_score <= 1
        ):
            raise ValueError("语义相似度阈值必须位于 -1 到 1 之间。")
        if not query.strip():
            return []
        bm25_results = self._bm25.search(query, game_name=game_name, top_k=candidate_k)
        semantic_results = self._semantic.search(
            query, game_name=game_name, top_k=candidate_k, min_score=semantic_min_score,
        )
        return reciprocal_rank_fusion(bm25_results, semantic_results, top_k=top_k, rrf_k=rrf_k)


def main():
    from app.core.config import PROJECT_ROOT
    from app.knowledge.workflow import KnowledgeBase

    parser = argparse.ArgumentParser(description="使用 BM25、语义检索与 RRF 融合查询游戏资料。")
    parser.add_argument("query", help="关键词或问题")
    parser.add_argument("--game", help="限定游戏名称或已登记别名")
    parser.add_argument("--top-k", type=int, default=5, help="最终返回的分块数")
    parser.add_argument("--candidate-k", type=int, help="每路候选数，默认至少 10 条且不小于返回数")
    parser.add_argument("--rrf-k", type=int, default=60, help="RRF 平滑参数，默认 60")
    parser.add_argument("--semantic-min-score", type=float, help="可选语义相似度下限，仅过滤语义一路")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT / "materials", help="知识库目录")
    args = parser.parse_args()
    try:
        results = KnowledgeBase(args.root).hybrid_search(
            args.query, game_name=args.game, top_k=args.top_k, candidate_k=args.candidate_k,
            rrf_k=args.rrf_k, semantic_min_score=args.semantic_min_score,
        )
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"混合检索失败：{error}\n")
    print(json.dumps({"results": results, "message": "检索完成" if results else "没有匹配的资料"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
