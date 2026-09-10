"""根据一份本地商品资料回答，保存多轮对话。"""

from pathlib import Path

from model_call import main


if __name__ == "__main__":
    # 按脚本所在位置找资料，换终端工作目录也能找到。
    # materials 已被 Git 忽略；复制项目时需要单独准备本地资料。
    material_path = Path(__file__).resolve().parent / "materials" / "sultans-game.md"
    # 复用模型调用、输入输出和错误处理，只额外提供资料文件位置。
    main(material_path=material_path)
