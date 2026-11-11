
import os
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# ==================================================
# USER CONTEXT
# ==================================================

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


# ==================================================
# TOOL REGISTRY
# ==================================================

class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, name, allowed_roles, handler):
        if name in self.tools:
            raise ValueError(f"Tool already registered: {name}")

        self.tools[name] = Tool(
            name=name,
            allowed_roles=allowed_roles,
            handler=handler,
        )

    def execute(self, call: ToolCall, context: UserContext):
        tool = self.tools.get(call.name)

        if tool is None:
            raise PermissionError("Tool is not registered.")

        if context.role not in tool.allowed_roles:
            raise PermissionError("User role is not authorized.")

        result = tool.handler(context, call.arguments)

        if not isinstance(result, dict):
            raise TypeError("Tool must return a dictionary.")

        if result.get("campus_id") != context.campus_id:
            raise PermissionError("Campus isolation check failed.")

        return result


# ==================================================
# FAKE STOCK DATA
# ==================================================

def get_stock_status(context, arguments):
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

    item_name = str(
        arguments.get("item_name", "")
    ).strip().lower()

    for record in records:
        if (
            record["campus_id"] == context.campus_id
            and record["item_name"].lower() == item_name
        ):
            return record.copy()

    return {
        "campus_id": context.campus_id,
        "message": "No matching stock record found.",
    }


def build_registry():
    registry = ToolRegistry()

    registry.register(
        "get_stock_status",
        ("ADMIN", "KITCHEN_MANAGER", "STORE_KEEPER"),
        get_stock_status,
    )

    return registry


# ==================================================
# FAKE LLM
# No API key or internet required
# ==================================================

class FakeLLM:
    def choose_tool(self, prompt: str) -> ToolCall:
        return ToolCall(
            name="get_stock_status",
            arguments={"item_name": "Rice"},
        )


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


# ==================================================
# GEMINI RETRY HANDLING
# ==================================================

def generate_with_retry(client, **kwargs):
    """
    Call Gemini with retry handling.

    Retryable HTTP errors:
    - 429: Rate limit exceeded
    - 500: Internal server error
    - 502: Bad gateway
    - 503: Service unavailable
    - 504: Gateway timeout

    Maximum attempts: 3.
    """

    max_attempts = 3
    base_delay = 2
    max_delay = 30

    retryable_statuses = {
        429,
        500,
        502,
        503,
        504,
    }

    for attempt in range(max_attempts):
        try:
            return client.models.generate_content(
                **kwargs
            )

        except Exception as exc:
            status_code = (
                getattr(exc, "code", None)
                or getattr(exc, "status_code", None)
            )

            if status_code not in retryable_statuses:
                raise

            if attempt == max_attempts - 1:
                raise

            delay = min(
                base_delay * (2 ** attempt),
                max_delay,
            )

            delay += random.uniform(0, 1)

            print(
                f"Gemini HTTP {status_code}. "
                f"Retry attempt {attempt + 2}/{max_attempts} "
                f"in {delay:.1f} seconds."
            )

            time.sleep(delay)


# ==================================================
# REAL GEMINI LLM
# ==================================================

class GeminiLLM:

    def __init__(self, api_key=None, model=None):
        from google import genai
        from google.genai import types  # type: ignore

        self.api_key = api_key or os.getenv(
            "GEMINI_API_KEY"
        )

        self.model = model or os.getenv(
            "GEMINI_MODEL",
            "gemini-3.1-flash-lite",
        )

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured."
            )

        self.client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(
                timeout=30000,
            ),
        )

    # --------------------------------------------------
    # GEMINI TOOL CALL
    # --------------------------------------------------

    def call_tool(self, prompt: str):
        from google.genai import types  # type: ignore

        function_declaration = types.FunctionDeclaration(
            name="get_stock_status",
            description=(
                "Get the stock quantity of an item "
                "for the authenticated user's campus."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "item_name": types.Schema(
                        type=types.Type.STRING,
                        description="Name of the stock item.",
                    ),
                },
                required=["item_name"],
            ),
        )

        tool = types.Tool(
            function_declarations=[
                function_declaration
            ],
        )

        config = types.GenerateContentConfig(
            tools=[tool],
        )

        response = generate_with_retry(
            self.client,
            model=self.model,
            contents=prompt,
            config=config,
        )

        function_calls = response.function_calls

        if not function_calls:
            return {
                "tool": None,
                "arguments": {},
                "result": None,
                "answer": response.text,
            }

        function_call = function_calls[0]

        return (
            ToolCall(
                name=function_call.name,
                arguments=dict(function_call.args or {}),
            ),
            response,
            config,
        )

    # --------------------------------------------------
    # SEND TOOL RESULT BACK TO GEMINI
    # --------------------------------------------------

    def generate_tool_response(
        self,
        prompt,
        original_response,
        tool_call,
        result,
        config,
    ):
        from google.genai import types  # type: ignore

        function_response = types.Part.from_function_response(
            name=tool_call.name,
            response=result,
        )

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=prompt)
                ],
            ),
            original_response.candidates[0].content,
            types.Content(
                role="user",
                parts=[function_response],
            ),
        ]

        return generate_with_retry(
            self.client,
            model=self.model,
            contents=contents,
            config=config,
        )


# ==================================================
# GEMINI TOOL-CALLING EXECUTION
# ==================================================

def run_gemini_tool_call(prompt, context):
    llm = GeminiLLM()
    registry = build_registry()

    call_result = llm.call_tool(prompt)

    # Gemini may answer directly without requesting a tool.
    if isinstance(call_result, dict):
        return call_result

    call, original_response, config = call_result

    # Python validates permissions and campus isolation.
    result = registry.execute(
        call,
        context,
    )

    # Send Python's result back to Gemini.
    final_response = llm.generate_tool_response(
        prompt,
        original_response,
        call,
        result,
        config,
    )

    return {
        "tool": call.name,
        "arguments": call.arguments,
        "result": result,
        "answer": final_response.text,
    }


# ==================================================
# RUN OFFLINE TEST
# ==================================================

if __name__ == "__main__":

    user = UserContext(
        user_id="demo-user-1",
        campus_id="KC-DEMO-NORTH",
        role="STORE_KEEPER",
    )

    print("Testing FakeLLM (offline):")

    print(
        run_tool_call(
            "How much rice is available?",
            user,
        )
    )
