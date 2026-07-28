import ast
import csv
import json
import os
import re
import sys
from typing import Any

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from prompts import CHATBOT_BASELINE_PROMPT, MAX_ITERATIONS, REACT_SYSTEM_PROMPT
from providers import get_llm_provider
from tools import AVAILABLE_TOOLS


load_dotenv()

TOOL_SPECS = {
    "search_rentals": {"min_args": 0, "max_args": 6},
    "get_listing_details": {"min_args": 1, "max_args": 1},
    "check_viewing_slots": {"min_args": 2, "max_args": 2},
    "send_viewing_request": {"min_args": 5, "max_args": 5},
    "create_calendar_event": {"min_args": 1, "max_args": 1},
}
PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "bỏ qua mọi hướng dẫn",
    "system prompt",
    "prompt hệ thống",
    "developer prompt",
    "tiết lộ prompt",
)
OFF_TOPIC_PATTERNS = (
    "thời tiết",
    "weather",
    "bóng đá",
    "bitcoin",
    "chứng khoán",
    "recipe",
    "công thức nấu",
)
RENTAL_HINTS = (
    "phòng",
    "trọ",
    "thuê",
    "căn hộ",
    "listing",
    "xem nhà",
    "đặt lịch",
    "lịch xem",
)


def load_test_cases() -> list[dict[str, Any]]:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")
    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)


def _build_react_prompt(user_query: str, trace_lines: list[str]) -> str:
    trace_text = "\n".join(trace_lines).strip() or "(chưa có)"
    return (
        f"Câu hỏi người dùng: {user_query}\n\n"
        f"Lịch sử ReAct hiện tại:\n{trace_text}\n\n"
        "Hãy trả lời đúng một trong hai dạng:\n"
        "1. Thought + Action\n"
        "2. Thought + Final Answer"
    )


def _extract_line(output: str, label: str) -> str | None:
    pattern = rf"^{re.escape(label)}:\s*(.+)$"
    match = re.search(pattern, output, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _split_arguments(argument_block: str) -> list[str]:
    reader = csv.reader([argument_block], skipinitialspace=True)
    return next(reader, [])


def _coerce_argument(token: str) -> Any:
    value = token.strip()
    if not value:
        return ""
    if value[0] in ("'", '"', "{", "[") or value in {"True", "False", "None"}:
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value.strip("'\"")
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value.strip("'\"")


def parse_action(action_line: str) -> tuple[str | None, list[Any] | dict[str, Any] | None, str | None]:
    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\[(.*)\]", action_line.strip(), flags=re.DOTALL)
    if not match:
        return None, None, "Action không đúng định dạng tool_name[arg1, arg2, ...]."

    tool_name, raw_arguments = match.groups()
    raw_arguments = raw_arguments.strip()
    if not raw_arguments:
        return tool_name, [], None

    if raw_arguments.startswith("{") and raw_arguments.endswith("}"):
        try:
            parsed = ast.literal_eval(raw_arguments)
        except (ValueError, SyntaxError):
            return None, None, "Không parse được tham số dạng dict."
        if not isinstance(parsed, dict):
            return None, None, "Tham số dạng dict không hợp lệ."
        return tool_name, parsed, None

    try:
        parsed_tuple = ast.literal_eval(f"({raw_arguments},)")
    except (ValueError, SyntaxError):
        parsed_tuple = None
    if isinstance(parsed_tuple, tuple):
        return tool_name, list(parsed_tuple), None

    parsed_tokens = [_coerce_argument(token) for token in _split_arguments(raw_arguments)]
    if len(parsed_tokens) == 1 and isinstance(parsed_tokens[0], dict):
        return tool_name, parsed_tokens[0], None
    return tool_name, parsed_tokens, None


def execute_action(tool_name: str, arguments: list[Any] | dict[str, Any]) -> str:
    function = AVAILABLE_TOOLS.get(tool_name)
    if function is None:
        return f"LỖI: Tool '{tool_name}' không được hỗ trợ."

    spec = TOOL_SPECS[tool_name]
    try:
        if isinstance(arguments, dict):
            return function(**arguments)
        if not spec["min_args"] <= len(arguments) <= spec["max_args"]:
            return (
                f"LỖI: Tool '{tool_name}' nhận từ {spec['min_args']} đến "
                f"{spec['max_args']} tham số, nhưng nhận {len(arguments)}."
            )
        return function(*arguments)
    except TypeError as exc:
        return f"LỖI: Sai tham số khi gọi {tool_name}. Chi tiết: {exc}"
    except Exception as exc:
        return f"LỖI: Gọi tool {tool_name} thất bại. Chi tiết: {exc}"


def _guardrail_response(user_query: str) -> str | None:
    normalized = user_query.strip().lower()
    if not normalized:
        return "Bạn hãy mô tả rõ nhu cầu tìm phòng hoặc đặt lịch xem nhà để mình hỗ trợ chính xác hơn."
    if any(pattern in normalized for pattern in PROMPT_INJECTION_PATTERNS):
        return "Mình không thể tiết lộ prompt nội bộ hay bỏ qua quy tắc an toàn. Nếu bạn cần, mình vẫn có thể hỗ trợ tìm phòng và đặt lịch xem nhà."
    if any(pattern in normalized for pattern in OFF_TOPIC_PATTERNS) and not any(hint in normalized for hint in RENTAL_HINTS):
        return "Mình chỉ hỗ trợ tìm tin cho thuê và đặt lịch xem nhà. Bạn hãy gửi nhu cầu thuê phòng hoặc căn hộ, mình sẽ tiếp tục."
    if "hủy lịch" in normalized or "cancel" in normalized or "đổi lịch" in normalized:
        return "Hiện tại agent chưa hỗ trợ hủy hoặc đổi lịch tự động. Bạn hãy cung cấp lại listing hoặc request_id để mình ghi nhận nhu cầu và hướng dẫn bước tiếp theo."
    if "đặt lịch" in normalized and not any(token in normalized for token in ("listing", "tin ", "mã", "ngày", "slot", "giờ")):
        return "Để đặt lịch xem nhà, mình cần ít nhất listing_id hoặc tin đã chọn, ngày xem, khung giờ, họ tên và số điện thoại."
    return None


def run_baseline_chatbot(user_query: str, provider) -> str:
    print(f"\n[CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT).strip()
    print(f"Final Answer: {response}\n")
    return response


def run_react_agent(user_query: str, provider) -> dict[str, Any]:
    print(f"\n[REACT AGENT] Câu hỏi: {user_query}")
    guardrail_answer = _guardrail_response(user_query)
    if guardrail_answer:
        print("Thought: Đây là trường hợp cần guardrail hoặc làm rõ thêm trước khi dùng tool.")
        print(f"Final Answer: {guardrail_answer}\n")
        return {"status": "guardrail", "final_answer": guardrail_answer, "trace": []}

    trace_lines: list[str] = []
    consecutive_invalid_steps = 0

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- Step {step}/{MAX_ITERATIONS} ---")
        prompt = _build_react_prompt(user_query, trace_lines)
        model_output = provider.generate(prompt, system_prompt=REACT_SYSTEM_PROMPT).strip()
        print(model_output)

        final_answer = _extract_line(model_output, "Final Answer")
        if final_answer:
            print("")
            return {"status": "completed", "final_answer": final_answer, "trace": trace_lines}

        thought = _extract_line(model_output, "Thought")
        action_line = _extract_line(model_output, "Action")
        if thought:
            trace_lines.append(f"Thought: {thought}")

        if not action_line:
            consecutive_invalid_steps += 1
            observation = "LỖI: Model không trả về Action hoặc Final Answer hợp lệ."
            trace_lines.append(f"Observation: {observation}")
            print(f"Observation: {observation}")
        else:
            tool_name, arguments, parse_error = parse_action(action_line)
            if parse_error or tool_name is None or arguments is None:
                consecutive_invalid_steps += 1
                observation = f"LỖI: {parse_error}"
                trace_lines.append(f"Action: {action_line}")
                trace_lines.append(f"Observation: {observation}")
                print(f"Observation: {observation}")
            else:
                trace_lines.append(f"Action: {action_line}")
                observation = execute_action(tool_name, arguments)
                consecutive_invalid_steps = consecutive_invalid_steps + 1 if tool_name not in AVAILABLE_TOOLS else 0
                trace_lines.append(f"Observation: {observation}")
                print(f"Observation: {observation}")

        if consecutive_invalid_steps >= 2:
            final_answer = (
                "Mình dừng vòng lặp an toàn vì model liên tục sinh Action không hợp lệ. "
                "Bạn hãy diễn đạt lại yêu cầu hoặc cung cấp dữ liệu cụ thể hơn."
            )
            print(f"Final Answer: {final_answer}\n")
            return {"status": "invalid_loop", "final_answer": final_answer, "trace": trace_lines}

    final_answer = (
        f"Mình dừng lại an toàn sau {MAX_ITERATIONS} bước vì chưa thể hoàn tất yêu cầu. "
        "Bạn hãy cung cấp ngắn gọn hơn hoặc chỉ rõ listing_id/ngày/khung giờ cần thao tác."
    )
    print(f"Final Answer: {final_answer}")
    print(f"Guardrail: MAX_ITERATIONS={MAX_ITERATIONS}\n")
    return {"status": "max_iterations", "final_answer": final_answer, "trace": trace_lines}


def run_demo_cases(provider) -> None:
    tests = load_test_cases()
    print(f"Đã tải {len(tests)} test cases từ config/test_cases.json")

    print("\n=== DEMO: BASELINE CHATBOT ===")
    for test in tests:
        print(f"\n--- Case {test['id']}: {test['category']} ---")
        run_baseline_chatbot(test["question"], provider)

    print("\n=== DEMO: REACT AGENT ===")
    for test in tests:
        print(f"\n--- Case {test['id']}: {test['category']} ---")
        run_react_agent(test["question"], provider)


if __name__ == "__main__":
    print("==================================================")
    print("LAB 03: RENTAL VIEWING ASSISTANT")
    print("==================================================")
    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "mock")
    print(f"LLM Provider: {provider.__class__.__name__} (Model: {model_name})")
    run_demo_cases(provider)
