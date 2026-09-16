"""项目启动入口：在项目根目录执行 python main.py。"""

from app.customer.cli import main as run_customer_chat
from app.posting.cli import main as run_posting
from app.knowledge.main import main as run_knowledge


def main():
    """显示菜单，根据用户的选择执行对应操作。"""
    print("欢迎使用 Agent 学习项目！")

    # 循环显示菜单，直到用户选择退出。
    while True:
        print("\n1. 智能客服")
        print("2. 发帖生成")
        print("3. 知识库维护")
        print("0. 退出")
        try:
            choice = input("请输入选择：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n程序已退出。")
            return

        if choice == "1":
            # 客服里的 /exit 返回菜单；菜单里的 0 退出整个程序。
            print("进入智能客服，输入 /exit 返回主菜单。")
            run_customer_chat()
            print("已返回主菜单。")
        elif choice == "2":
            run_posting()
            print("已返回主菜单。")
        elif choice == "3":
            run_knowledge()
            print("已返回主菜单。")
        elif choice == "0":
            print("程序已退出，再见！")
            break
        else:
            print("输入无效，请输入 1、2、3 或 0。")


# 直接运行此文件时，从 main() 开始执行。
if __name__ == "__main__":
    main()
