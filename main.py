"""项目启动入口：在项目根目录执行 python main.py。"""

from app.chat_cli import main as run_customer_chat


def main():
    """显示菜单，根据用户的选择执行对应操作。"""
    print("欢迎使用 Agent 学习项目！")

    # 循环显示菜单，直到用户选择退出。
    while True:
        print("\n1. 智能客服")
        print("2. 发帖生成")
        print("0. 退出")
        try:
            choice = input("请输入选择：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n程序已退出。")
            return

        if choice == "1":
            # 客服里的 /exit 返回菜单；菜单里的 0 退出整个程序。
            run_customer_chat()
        elif choice == "2":
            print("你选择了发帖生成，后续将在这里接入文案生成。")
        elif choice == "0":
            print("程序已退出，再见！")
            break
        else:
            print("输入无效，请输入 1、2 或 0。")


# 直接运行此文件时，从 main() 开始执行。
if __name__ == "__main__":
    main()
