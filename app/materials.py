"""本地资料文件读取，不依赖模型和命令行入口。"""

from pathlib import Path


def load_material(path: Path) -> str:
    """读取资料；文件缺失或为空时停止，避免模型在没有依据时继续回答。"""
    try:
        # utf-8-sig 同时兼容普通 UTF-8 文件和带 BOM 的 UTF-8 文件。
        material = path.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        raise ValueError("无法读取商品资料，请确认文件存在、可读取且为 UTF-8 编码。") from None
    if not material:
        raise ValueError("商品资料为空，请先补充资料内容。")
    return material
