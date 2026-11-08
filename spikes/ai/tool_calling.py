from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class UserContext:
    user_id: str
    campus_id: str
    role: str


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class Tool:
    name: str
    allowed_roles: tuple[str, ...]
    handler: Callable


class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, name, allowed_roles, handler):
        if name in self.tools:
            raise ValueError(f"Tool already registered: {name}")

        self.tools[name] = Tool(name, allowed_roles, handler)

    def execute(self, call: ToolCall, context: UserContext):
        tool = self.tools.get(call.name)

        if tool is None:
            raise PermissionError("Tool is not registered.")

        if context.role not in tool.allowed_roles:
            raise PermissionError("User role is not authorized.")

        result = tool.handler(context, call.arguments)

        if result.get("campus_id") != context.campus_id:
            raise PermissionError("Campus isolation check failed.")

        return result


class FakeLLM:
    def choose_tool(self, prompt: str) -> ToolCall:
        return ToolCall(
            name="get_stock_summary",
            arguments={"item_name": "Rice"},
        )


def get_stock_summary(context, arguments):
    records = [
        {
            "campus_id": "KC-DEMO-NORTH",
            "item_name": "Rice",
            "quantity": 125,
            "unit": "kg",
        },
        {
            "campus_id": "KC-DEMO-SOUTH",
            "item_name": "Rice",
            "quantity": 80,
            "unit": "kg",
        },
    ]

    for record in records:
        if (
            record["campus_id"] == context.campus_id
            and record["item_name"].lower()
            == str(arguments.get("item_name", "")).lower()
        ):
            return record.copy()

    return {
        "campus_id": context.campus_id,
        "message": "No matching stock record found.",
    }


def build_registry():
    registry = ToolRegistry()

    registry.register(
        "get_stock_summary",
        ("ADMIN", "KITCHEN_MANAGER", "STORE_KEEPER"),
        get_stock_summary,
    )

    return registry


def run_tool_call(prompt, context):
    llm = FakeLLM()
    registry = build_registry()

    call = llm.choose_tool(prompt)
    result = registry.execute(call, context)

    return {
        "tool": call.name,
        "arguments": call.arguments,
        "result": result,
    }


if __name__ == "__main__":
    user = UserContext(
        user_id="demo-user-1",
        campus_id="KC-DEMO-NORTH",
        role="STORE_KEEPER",
    )

    print(run_tool_call("How much rice is available?", user))
