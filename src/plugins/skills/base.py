"""Agentic 技能 (Skill) 与大模型函数调用 (Function Calling) 抽象基类与装饰器。
支持插件向大模型注册结构化工具能力，大模型可自主感知、决策并调用具体技能。
"""

from abc import ABC, abstractmethod
import inspect
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class BaseSkill(ABC):
    """技能工具抽象基类。"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters_schema: Dict[str, Any],
        admin_only: bool = False,
    ):
        self.name = name.strip()
        self.description = description.strip()
        self.parameters_schema = parameters_schema
        self.admin_only = admin_only

    def to_openai_tool(self) -> Dict[str, Any]:
        """转换为 OpenAI 兼容标准的 Function Calling tools 定义结构。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema or {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }

    @abstractmethod
    async def execute(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """
        执行具体技能逻辑。
        :param params: 大模型生成的 JSON 参数字典
        :param context: 执行上下文 (包含 session_type, target_id, user_id, user_name, platform 等)
        :return: 文本结果（将被回传给大模型作为 tool 响应）
        """
        pass


class FunctionalSkill(BaseSkill):
    """由普通异步函数包装而成的技能实例。"""

    def __init__(
        self,
        fn: Callable,
        name: str,
        description: str,
        parameters_schema: Dict[str, Any],
        admin_only: bool = False,
    ):
        super().__init__(name, description, parameters_schema, admin_only)
        self.fn = fn

    async def execute(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        sig = inspect.signature(self.fn)
        if "context" in sig.parameters:
            if inspect.iscoroutinefunction(self.fn):
                res = await self.fn(params, context=context)
            else:
                res = self.fn(params, context=context)
        else:
            if inspect.iscoroutinefunction(self.fn):
                res = await self.fn(params)
            else:
                res = self.fn(params)
        return str(res)


def skill(
    name: str,
    description: str,
    parameters_schema: Dict[str, Any],
    admin_only: bool = False,
):
    """快捷装饰器，可直接将一个异步函数声明为插件技能。"""
    def decorator(fn: Callable):
        return FunctionalSkill(
            fn=fn,
            name=name,
            description=description,
            parameters_schema=parameters_schema,
            admin_only=admin_only,
        )
    return decorator
