"""本地中文向量检索；向量缓存可重建，不修改原始知识库。"""

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata


MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def _normalize(vector, dimension):
    try:
        values = [float(value) for value in vector]
    except (TypeError, ValueError, OverflowError):
        raise ValueError("向量包含无效数值。") from None
    if len(values) != dimension or not all(math.isfinite(value) for value in values):
        raise ValueError("向量维度不一致或包含非有限数值。")
    length = math.hypot(*values)
    if not length or not math.isfinite(length):
        raise ValueError("向量长度无效。")
    return [value / length for value in values]


class LocalEmbedder:
    """按需加载中文模型；分段编码后均值池化，保留长资料尾部信息。"""

    dimension = 512
    fingerprint = {"model": MODEL_NAME, "runtime": "fastembed-0.8.0",
                   "recipe": "windows-160-mean-v1", "dimension": 512}

    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir)
        self._model = None

    def embed(self, texts, *, query=False):
        if not texts:
            return []
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(self.cache_dir),
                                        threads=4, providers=["CPUExecutionProvider"])
        results = []
        for text in texts:
            if not text.strip():
                raise ValueError("不能为纯空白内容生成向量。")
            # 编码窗口只用于计算向量，返回给调用方的原始分块保持完整。
            windows = [text[start:start + 160] for start in range(0, len(text), 160)]
            if query:
                windows = ["为这个句子生成表示以用于检索相关文章：" + window for window in windows]
            total = [0.0] * self.dimension
            count = 0
            for vector in self._model.embed(windows, batch_size=16):
                values = _normalize(vector, self.dimension)
                total = [left + right for left, right in zip(total, values)]
                count += 1
            if count != len(windows):
                raise ValueError("模型返回的向量数量不完整。")
            results.append(_normalize(total, self.dimension))
        return results


def _name_key(name):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", name).casefold())


def _text(chunk):
    return "\n".join([chunk.get("search_text") or "\n".join([
        chunk["game_name"], chunk.get("section", ""), chunk["content"],
    ]), *chunk.get("aliases", [])])


class SemanticRetriever:
    """使用当前分块与可复用向量缓存进行余弦相似度检索。

    embedder 提供 fingerprint、dimension 和 embed(texts, query=False)。
    资料变化后重新创建实例；缓存只包含文本哈希和向量，元数据取自当前分块。
    """

    def __init__(self, chunks, embedder, index_file):
        self._chunks = deepcopy(list(chunks))
        ids = [chunk["chunk_id"] for chunk in self._chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("分块编号重复，请重新生成分块。")
        self._embedder = embedder
        self._index_file = Path(index_file)
        self._texts = {}
        self._keys = []
        for chunk in self._chunks:
            text = _text(chunk)
            key = hashlib.sha256(text.encode("utf-8")).hexdigest()
            self._keys.append(key)
            self._texts[key] = text
        self._vectors = None

    def build(self):
        """只生成新增或变更文本向量；成功后原子替换缓存，移除删除项。"""
        from app.knowledge.workflow import KnowledgeBase

        old = {}
        if self._index_file.exists():
            try:
                old = json.loads(self._index_file.read_text(encoding="utf-8"))
                if not isinstance(old, dict):
                    raise ValueError()
            except (ValueError, UnicodeError):
                raise ValueError("向量缓存格式无效，请移走缓存后重新生成。") from None
        vectors = {}
        if old.get("schema_version") == 1 and old.get("embedding") == self._embedder.fingerprint:
            cached = old.get("vectors")
            if not isinstance(cached, dict):
                raise ValueError("向量缓存格式无效，请移走缓存后重新生成。")
            vectors = {key: _normalize(cached[key], self._embedder.dimension)
                       for key in self._texts if key in cached}
        missing = [key for key in self._texts if key not in vectors]
        reused = len(vectors)
        for start in range(0, len(missing), 16):
            keys = missing[start:start + 16]
            generated = list(self._embedder.embed([self._texts[key] for key in keys]))
            if len(generated) != len(keys):
                raise ValueError("模型返回的向量数量不完整。")
            for key, vector in zip(keys, generated):
                vectors[key] = _normalize(vector, self._embedder.dimension)
        payload = {"schema_version": 1, "embedding": self._embedder.fingerprint, "vectors": vectors}
        # 模型或编码规则变化时完整重建；失败时保留上一次的缓存。
        if (missing or old.get("schema_version") != 1
                or old.get("embedding") != self._embedder.fingerprint
                or set(old.get("vectors", {})) != set(vectors)):
            self._index_file.parent.mkdir(parents=True, exist_ok=True)
            KnowledgeBase._write(self._index_file, payload)
        self._vectors = vectors
        return {"chunks": len(self._chunks), "generated": len(missing), "reused": reused,
                "index_file": str(self._index_file)}

    def search(self, query, *, game_name=None, top_k=5, min_score=None):
        """返回相似分块；默认不设未经评测的阈值，分数不代表答案可信度。"""
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("返回数量必须是正整数。")
        if min_score is not None and (not isinstance(min_score, (int, float))
                                     or isinstance(min_score, bool) or not math.isfinite(min_score)
                                     or not -1 <= min_score <= 1):
            raise ValueError("相似度阈值必须位于 -1 到 1 之间。")
        if not query.strip():
            return []
        candidates = list(range(len(self._chunks)))
        if game_name is not None:
            matches = {chunk["game_name"] for chunk in self._chunks
                       if _name_key(game_name) in {_name_key(name) for name in
                           [chunk["game_name"], *chunk.get("aliases", [])]}}
            if len(matches) > 1:
                raise ValueError("游戏名称或别名存在歧义，请使用明确的游戏名称。")
            candidates = [i for i in candidates if self._chunks[i]["game_name"] in matches]
        if not candidates:
            return []
        if self._vectors is None:
            self.build()
        generated = list(self._embedder.embed([query], query=True))
        if len(generated) != 1:
            raise ValueError("模型返回的查询向量数量无效。")
        query_vector = _normalize(generated[0], self._embedder.dimension)
        scores = []
        for index in candidates:
            score = sum(a * b for a, b in zip(query_vector, self._vectors[self._keys[index]]))
            score = max(-1.0, min(1.0, score))
            if min_score is None or score >= min_score:
                scores.append((index, score))
        scores.sort(key=lambda pair: (-pair[1], self._chunks[pair[0]]["chunk_id"]))
        return [dict(deepcopy(self._chunks[index]), semantic_score=score, rank=rank,
                     retrieval_method="semantic")
                for rank, (index, score) in enumerate(scores[:top_k], 1)]


def main():
    from app.core.config import PROJECT_ROOT
    from app.knowledge.workflow import KnowledgeBase

    parser = argparse.ArgumentParser(description="生成本地中文向量或执行语义检索。")
    parser.add_argument("query", nargs="?", help="待检索的问题")
    parser.add_argument("--build", action="store_true", help="仅生成或更新向量缓存")
    parser.add_argument("--game", help="限定游戏名称或已登记别名")
    parser.add_argument("--top-k", type=int, default=5, help="最多返回的分块数")
    parser.add_argument("--min-score", type=float, help="可选余弦相似度下限，需自行评测")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT / "materials", help="知识库目录")
    args = parser.parse_args()
    if args.build == (args.query is not None):
        parser.error("请提供查询问题，或单独使用 --build。")
    try:
        kb = KnowledgeBase(args.root)
        retriever = kb.semantic_retriever()
        result = retriever.build() if args.build else {"results": retriever.search(
            args.query, game_name=args.game, top_k=args.top_k, min_score=args.min_score)}
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"语义检索失败：{error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
