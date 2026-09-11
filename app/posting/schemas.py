"""发帖输入与输出约定，供 Agent、菜单和文件保存共同使用。"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 发帖输入
class PostingRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    current_game: str = Field(min_length=1) # 当前游戏名称 必填
    tone: str = Field(default="自然", min_length=1) # 发帖语气
    length: str = Field(default="简洁", min_length=1) # 发帖长度
    focus: str = Field(min_length=1) # 主要关注点 必填

# 发帖输出
class PostingDraft(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(description="商品标题；需要先追问时为空")
    body: str = Field(description="商品正文；需要先追问时为空")
    missing_information: list[str] = Field(description="尚未确认的信息，不能变成宣传承诺")
    questions: list[str] = Field(description="阻碍本次生成的关键问题；可生成时为空")

    @model_validator(mode="after")
    def check_result(self):
        # 追问和可用草稿互斥，界面不会误把待确认内容当成可发布正文。
        if any(not item.strip() for item in self.missing_information + self.questions):
            raise ValueError("待补充信息和问题不能为空白问题。")
        if self.questions:
            if self.title or self.body:
                raise ValueError("需要追问时不能同时生成草稿。")
        elif not self.title or not self.body:
            raise ValueError("草稿必须同时包含标题和正文。")
        return self
