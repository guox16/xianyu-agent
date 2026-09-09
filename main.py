def main():
    """显示菜单，根据用户的选择执行对应操作。"""
    print("欢迎使用 Agent 学习项目！")

    # 循环显示菜单，直到用户选择退出。
    while True:
        print("\n1. 智能客服")
        print("2. 发帖生成")
        print("0. 退出")
        choice = input("请输入选择：").strip()

        if choice == "1":
            print("你选择了智能客服，后续将在这里接入 AI 对话。")
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
