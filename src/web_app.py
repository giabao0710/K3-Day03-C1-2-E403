import json
import re
import os
import sys
from datetime import date
from uuid import uuid4

from flask import Flask, redirect, render_template, request, session, url_for


sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from prompts import CHATBOT_BASELINE_PROMPT
from providers import get_llm_provider
from tools import check_viewing_slots, create_calendar_event, get_listing_details, search_rentals, send_viewing_request


app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))
app.secret_key = os.getenv("FLASK_SECRET_KEY", "rental-agent-dev-secret")
PROVIDER = get_llm_provider()

SESSION_STORE = {}
DEFAULT_REGION_V2 = 12000
DEFAULT_CATEGORY = 1050
DEFAULT_PROPERTY_TYPES = "u,h"
DEFAULT_LIMIT = 5
PRESERVE_STATE_FLAG = "preserve_state_once"


def _default_state():
    return {
        "messages": [
            {
                "role": "agent",
                "kind": "text",
                "text": "Xin chào! Tôi có thể giúp bạn tìm phòng trọ và gửi yêu cầu đặt lịch xem nhà.",
            }
        ],
        "latest_results": [],
        "selected_listing_id": None,
        "selected_listing_title": "",
        "available_slots": [],
        "selected_viewing_date": "",
    }


def _session_state():
    session_id = session.get("chat_session_id")
    if not isinstance(session_id, str):
        session_id = str(uuid4())
        session["chat_session_id"] = session_id

    state = SESSION_STORE.get(session_id)
    if state is None:
        state = _default_state()
        SESSION_STORE[session_id] = state
    return state


def _reset_session_state():
    session_id = session.get("chat_session_id")
    if isinstance(session_id, str):
        SESSION_STORE.pop(session_id, None)
    new_session_id = str(uuid4())
    session["chat_session_id"] = new_session_id
    SESSION_STORE[new_session_id] = _default_state()
    return SESSION_STORE[new_session_id]


def _redirect_with_state_preserved():
    session[PRESERVE_STATE_FLAG] = True
    return redirect(url_for("index"))


def _append_text(role: str, text: str):
    _session_state()["messages"].append({"role": role, "kind": "text", "text": text})


def _append_listings(results):
    _session_state()["messages"].append({"role": "agent", "kind": "listings", "results": results})


def _append_listing_details(details):
    _session_state()["messages"].append({"role": "agent", "kind": "details", "details": details})


def _append_slots(viewing_date: str, slots):
    _session_state()["messages"].append(
        {
            "role": "agent",
            "kind": "slots",
            "listing_id": _session_state()["selected_listing_id"],
            "listing_title": _session_state()["selected_listing_title"],
            "viewing_date": viewing_date,
            "available_slots": slots,
        }
    )


def _append_request_confirmation(payload):
    _session_state()["messages"].append({"role": "agent", "kind": "request", "payload": payload})


def _append_calendar_confirmation(payload):
    _session_state()["messages"].append({"role": "agent", "kind": "calendar", "payload": payload})


def _provider_text_or_none(prompt: str):
    try:
        response = PROVIDER.generate(prompt, system_prompt=CHATBOT_BASELINE_PROMPT).strip()
    except Exception:
        return None

    if not response or response.startswith("["):
        return None
    return response


def _parse_tool_output(raw_output: str):
    if raw_output.startswith("LỖI:"):
        return None, raw_output

    try:
        return json.loads(raw_output), None
    except json.JSONDecodeError:
        return None, "LỖI: Tool trả về dữ liệu không đọc được."


def _build_listing_detail_view(raw_listing):
    params = raw_listing.get("params") or []
    furnishing = "Không rõ"
    for param in params:
        if param.get("id") == "furnishing_rent" and isinstance(param.get("value"), str):
            furnishing = param["value"]
            break

    seller_info = raw_listing.get("seller_info") or {}
    return {
        "listing_id": raw_listing.get("list_id"),
        "title": raw_listing.get("subject", "Không có tiêu đề"),
        "price_text": raw_listing.get("price_string", "Không rõ"),
        "area_m2": raw_listing.get("size"),
        "address": ", ".join(
            [
                part.strip()
                for part in [
                    raw_listing.get("street_number", ""),
                    raw_listing.get("street_name", ""),
                    raw_listing.get("ward_name_v3") or raw_listing.get("ward_name") or "",
                    raw_listing.get("area_name", ""),
                    raw_listing.get("region_name_v3") or raw_listing.get("region_name") or "",
                ]
                if part
            ]
        )
        or "Không rõ",
        "status": raw_listing.get("status", "Không rõ"),
        "furnishing": furnishing,
        "description": (raw_listing.get("body") or "").strip(),
        "contact_name": seller_info.get("full_name") or raw_listing.get("full_name") or raw_listing.get("account_name") or "Không rõ",
        "rating": raw_listing.get("average_rating"),
        "rating_count": raw_listing.get("total_rating"),
        "seller_rating": raw_listing.get("average_rating_for_seller"),
        "seller_rating_count": raw_listing.get("total_rating_for_seller"),
    }


def _extract_budget_bounds(message: str):
    matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*triệu", message.lower())
    if not matches:
        return None

    values = []
    for item in matches[:2]:
        normalized = item.replace(",", ".")
        try:
            values.append(int(float(normalized) * 1_000_000))
        except ValueError:
            return None

    if len(values) == 1:
        return values[0], values[0]
    return min(values), max(values)


def _extract_listing_id(message: str):
    matches = re.findall(r"(?:tin|mã tin|listing)\s*#?\s*(\d+)", message.lower())
    if not matches:
        fallback = re.findall(r"#(\d+)", message)
        if not fallback:
            return None
        matches = fallback

    try:
        return int(matches[-1])
    except ValueError:
        return None


def _extract_request_id(message: str):
    matches = re.findall(r"(?:request|yêu cầu)\s*#?\s*(\d+)", message.lower())
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def _extract_date(message: str):
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", message)
    if not match:
        return None
    return match.group(1)


def _extract_slot(message: str):
    match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", message)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    return f"{hour:02d}:{minute:02d}"


def _extract_name(message: str):
    match = re.search(r"(?:tên|name)\s*[:\-]?\s*([^,;\n]+)", message, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def _extract_phone(message: str):
    match = re.search(r"(0\d{8,10})", message)
    if not match:
        return None
    return match.group(1)


def _run_search_flow(min_price: int, max_price: int, limit: int, user_text: str):
    state = _session_state()
    _append_text("user", user_text)

    raw_output = search_rentals(
        region_v2=DEFAULT_REGION_V2,
        category=DEFAULT_CATEGORY,
        min_price=min_price,
        max_price=max_price,
        property_types=DEFAULT_PROPERTY_TYPES,
        limit=limit,
    )
    payload, error = _parse_tool_output(raw_output)
    state["latest_results"] = []
    state["selected_listing_id"] = None
    state["selected_listing_title"] = ""
    state["available_slots"] = []
    state["selected_viewing_date"] = ""

    if error is not None:
        _append_text("agent", error)
        return

    results = payload.get("results", [])
    state["latest_results"] = results
    if not results:
        _append_text("agent", "Không tìm thấy phòng phù hợp với yêu cầu này.")
        return

    summary_prompt = (
        "Bạn là trợ lý tìm nhà trọ. Hãy trả lời ngắn gọn bằng tiếng Việt trong 2 câu. "
        "Tóm tắt kết quả tìm kiếm sau và gợi ý người dùng chọn một tin để xem chi tiết.\n"
        f"Kết quả: {json.dumps(results[:3], ensure_ascii=False)}"
    )
    summary_text = _provider_text_or_none(summary_prompt)
    _append_text(
        "agent",
        summary_text or f"Tôi tìm thấy {payload.get('total_found', len(results))} tin phù hợp. Bạn có thể bấm vào một tin để xem chi tiết.",
    )
    _append_listings(results)


def _run_details_flow(listing_id: int):
    state = _session_state()
    title = next((item.get("title", "") for item in state["latest_results"] if item.get("listing_id") == listing_id), "")
    raw_output = get_listing_details(listing_id)
    payload, error = _parse_tool_output(raw_output)
    if error is not None:
        _append_text("agent", error)
        return

    details_view = _build_listing_detail_view(payload)
    state["selected_listing_id"] = listing_id
    state["selected_listing_title"] = title or details_view["title"]
    state["available_slots"] = []
    state["selected_viewing_date"] = ""
    detail_prompt = (
        "Bạn là trợ lý thuê nhà. Hãy mô tả ngắn gọn listing sau bằng tiếng Việt trong tối đa 3 câu, "
        "nêu giá, khu vực, điểm nổi bật và gợi ý kiểm tra lịch nếu người dùng muốn xem nhà.\n"
        f"Listing: {json.dumps(details_view, ensure_ascii=False)}"
    )
    detail_text = _provider_text_or_none(detail_prompt)
    if detail_text is not None:
        _append_text("agent", detail_text)
    _append_listing_details(details_view)


def _run_slots_flow(listing_id: int, viewing_date: str):
    state = _session_state()
    raw_output = check_viewing_slots(listing_id, viewing_date)
    payload, error = _parse_tool_output(raw_output)
    if error is not None:
        _append_text("agent", error)
        return

    available_slots = payload.get("available_slots", [])
    state["selected_listing_id"] = listing_id
    state["available_slots"] = available_slots
    state["selected_viewing_date"] = viewing_date
    slots_prompt = (
        "Bạn là trợ lý đặt lịch xem nhà. Hãy trả lời ngắn gọn bằng tiếng Việt về các khung giờ trống "
        f"ngày {viewing_date} cho listing {listing_id}, rồi mời người dùng đặt lịch nếu phù hợp.\n"
        f"Khung giờ trống: {json.dumps(available_slots, ensure_ascii=False)}"
    )
    slots_text = _provider_text_or_none(slots_prompt)
    if slots_text is not None:
        _append_text("agent", slots_text)
    _append_slots(viewing_date, available_slots)


def _run_request_flow(listing_id: int, viewing_date: str, slot: str, customer_name: str, customer_phone: str):
    raw_output = send_viewing_request(
        listing_id=listing_id,
        viewing_date=viewing_date,
        slot=slot,
        customer_name=customer_name,
        customer_phone=customer_phone,
    )
    payload, error = _parse_tool_output(raw_output)
    if error is not None:
        _append_text("agent", error)
        return None

    request_prompt = (
        "Bạn là trợ lý đặt lịch xem nhà. Hãy xác nhận ngắn gọn bằng tiếng Việt rằng yêu cầu đã được tạo, "
        "nhắc lại ngày giờ và nói rằng trạng thái hiện tại là pending.\n"
        f"Yêu cầu: {json.dumps(payload, ensure_ascii=False)}"
    )
    request_text = _provider_text_or_none(request_prompt)
    if request_text is not None:
        _append_text("agent", request_text)
    _append_request_confirmation(payload)
    return payload


def _run_calendar_flow(request_id: int):
    raw_output = create_calendar_event(request_id)
    payload, error = _parse_tool_output(raw_output)
    if error is not None:
        _append_text("agent", error)
        return
    calendar_prompt = (
        "Bạn là trợ lý đặt lịch xem nhà. Hãy xác nhận ngắn gọn bằng tiếng Việt rằng calendar event đã được tạo "
        "để theo dõi booking, và nhắc lại thời gian sự kiện.\n"
        f"Sự kiện: {json.dumps(payload, ensure_ascii=False)}"
    )
    calendar_text = _provider_text_or_none(calendar_prompt)
    if calendar_text is not None:
        _append_text("agent", calendar_text)
    _append_calendar_confirmation(payload)


@app.get("/")
def index():
    should_preserve = bool(session.pop(PRESERVE_STATE_FLAG, False))
    state = _session_state() if should_preserve else _reset_session_state()
    return render_template(
        "chat.html",
        messages=state["messages"],
        selected_listing_id=state["selected_listing_id"],
        selected_listing_title=state["selected_listing_title"],
        available_slots=state["available_slots"],
        selected_viewing_date=state["selected_viewing_date"],
        min_viewing_date=date.today().isoformat(),
        defaults={
            "min_price": 1_000_000,
            "max_price": 2_000_000,
            "limit": DEFAULT_LIMIT,
        },
    )


@app.post("/search")
def search():
    min_price_raw = request.form.get("min_price", "1000000").strip()
    max_price_raw = request.form.get("max_price", "2000000").strip()
    limit_raw = request.form.get("limit", str(DEFAULT_LIMIT)).strip()

    try:
        min_price = int(min_price_raw)
        max_price = int(max_price_raw)
        limit = int(limit_raw)
    except ValueError:
        _append_text("agent", "LỖI: min_price, max_price và limit phải là số nguyên.")
        return _redirect_with_state_preserved()

    _run_search_flow(
        min_price=min_price,
        max_price=max_price,
        limit=limit,
        user_text=f"Tìm phòng trong khoảng {min_price_raw} - {max_price_raw} VND, tối đa {limit_raw} kết quả.",
    )
    return _redirect_with_state_preserved()


@app.post("/chat")
def chat():
    message = request.form.get("message", "").strip()
    if not message:
        _append_text("agent", "LỖI: Bạn cần nhập nội dung trước khi gửi.")
        return _redirect_with_state_preserved()

    budget_bounds = _extract_budget_bounds(message)
    lowered_message = message.lower()
    if ("tìm" in lowered_message or "phòng" in lowered_message or "trọ" in lowered_message) and budget_bounds is not None:
        min_price, max_price = budget_bounds
        _run_search_flow(
            min_price=min_price,
            max_price=max_price,
            limit=DEFAULT_LIMIT,
            user_text=message,
        )
        return _redirect_with_state_preserved()

    _append_text("user", message)
    state = _session_state()
    listing_id = _extract_listing_id(message) or state["selected_listing_id"]
    request_id = _extract_request_id(message)
    viewing_date = _extract_date(message)
    slot = _extract_slot(message)
    customer_name = _extract_name(message)
    customer_phone = _extract_phone(message)

    if ("chi tiết" in lowered_message or "xem tin" in lowered_message) and listing_id is not None:
        _run_details_flow(listing_id)
        return redirect(url_for("index"))

    if ("lịch trống" in lowered_message or "khung giờ" in lowered_message or "slot" in lowered_message) and listing_id is not None and viewing_date is not None:
        _run_slots_flow(listing_id, viewing_date)
        return redirect(url_for("index"))

    if ("đặt lịch" in lowered_message or "book" in lowered_message or "gửi yêu cầu" in lowered_message) and listing_id is not None:
        if viewing_date is None or slot is None or customer_name is None or customer_phone is None:
            _append_text(
                "agent",
                "Để đặt lịch bằng chat, hãy nhắn theo mẫu: 'Đặt lịch tin 123 vào 2026-07-30 lúc 14:00, tên Nguyễn Văn A, 0900000000'.",
            )
            return _redirect_with_state_preserved()

        request_payload = _run_request_flow(
            listing_id=listing_id,
            viewing_date=viewing_date,
            slot=slot,
            customer_name=customer_name,
            customer_phone=customer_phone,
        )
        if request_payload is not None and ("tạo lịch" in lowered_message or "calendar" in lowered_message):
            _run_calendar_flow(request_payload["request_id"])
        return _redirect_with_state_preserved()

    if ("tạo lịch" in lowered_message or "calendar" in lowered_message) and request_id is not None:
        _run_calendar_flow(request_id)
        return _redirect_with_state_preserved()

    if state["selected_listing_id"] is None:
        fallback_prompt = (
            "Bạn là trợ lý tìm nhà trọ. Người dùng vừa nhắn: "
            f"'{message}'. Hãy trả lời ngắn gọn bằng tiếng Việt, tự nhiên, và hướng người dùng đến việc "
            "tìm phòng hoặc xem chi tiết tin. Nếu cần ví dụ, dùng các mẫu: "
            "'Tìm phòng 1.5 đến 2 triệu', 'Xem chi tiết tin 133431083', "
            "'Kiểm tra lịch trống tin 133431083 vào 2026-07-30'."
        )
        _append_text(
            "agent",
            _provider_text_or_none(fallback_prompt)
            or "Bạn có thể nhắn như: 'Tìm phòng 1.5 đến 2 triệu', 'Xem chi tiết tin 133431083', hoặc 'Kiểm tra lịch trống tin 133431083 vào 2026-07-30'.",
        )
        return _redirect_with_state_preserved()

    if state["available_slots"]:
        booking_help_prompt = (
            "Bạn là trợ lý đặt lịch xem nhà. Hãy trả lời ngắn gọn bằng tiếng Việt cho người dùng vừa nhắn: "
            f"'{message}'. Hiện đã có khung giờ trống, nên hãy hướng họ đặt lịch bằng chat với mẫu: "
            "'Đặt lịch tin 133431083 vào 2026-07-30 lúc 14:00, tên Nguyễn Văn A, 0900000000'."
        )
        _append_text(
            "agent",
            _provider_text_or_none(booking_help_prompt)
            or "Bạn có thể đặt lịch ngay trong chat, ví dụ: 'Đặt lịch tin 133431083 vào 2026-07-30 lúc 14:00, tên Nguyễn Văn A, 0900000000'.",
        )
        return _redirect_with_state_preserved()

    selected_help_prompt = (
        "Bạn là trợ lý thuê nhà. Hãy trả lời ngắn gọn bằng tiếng Việt cho người dùng vừa nhắn: "
        f"'{message}'. Hiện họ đã chọn được một tin, nên hãy hướng họ kiểm tra lịch trống bằng chat với mẫu: "
        "'Kiểm tra lịch trống vào 2026-07-30'."
    )
    _append_text(
        "agent",
        _provider_text_or_none(selected_help_prompt)
        or "Bạn đã chọn được một tin. Bạn có thể nhắn: 'Kiểm tra lịch trống vào 2026-07-30' hoặc dùng nút ngay trong khung chat.",
    )
    return _redirect_with_state_preserved()


@app.post("/details")
def details():
    state = _session_state()
    listing_id_raw = request.form.get("listing_id", "").strip()

    try:
        listing_id = int(listing_id_raw)
    except ValueError:
        _append_text("agent", "LỖI: listing_id không hợp lệ.")
        return _redirect_with_state_preserved()

    title = next((item.get("title", "") for item in state["latest_results"] if item.get("listing_id") == listing_id), "")
    _append_text("user", f"Cho tôi xem chi tiết tin #{listing_id}.")

    _run_details_flow(listing_id)
    return _redirect_with_state_preserved()


@app.post("/slots")
def slots():
    state = _session_state()
    listing_id_raw = request.form.get("listing_id", "").strip()
    viewing_date = request.form.get("viewing_date", "").strip()

    try:
        listing_id = int(listing_id_raw)
    except ValueError:
        _append_text("agent", "LỖI: listing_id không hợp lệ.")
        return _redirect_with_state_preserved()

    _append_text("user", f"Kiểm tra lịch trống cho tin #{listing_id} vào ngày {viewing_date}.")
    _run_slots_flow(listing_id, viewing_date)
    return _redirect_with_state_preserved()


@app.post("/request")
def create_request():
    state = _session_state()
    listing_id_raw = request.form.get("listing_id", "").strip()
    viewing_date = request.form.get("viewing_date", "").strip()
    slot = request.form.get("slot", "").strip()
    customer_name = request.form.get("customer_name", "").strip()
    customer_phone = request.form.get("customer_phone", "").strip()

    try:
        listing_id = int(listing_id_raw)
    except ValueError:
        _append_text("agent", "LỖI: listing_id không hợp lệ.")
        return _redirect_with_state_preserved()

    _append_text(
        "user",
        f"Gửi yêu cầu xem nhà cho tin #{listing_id} vào {viewing_date} lúc {slot}.",
    )
    _run_request_flow(
        listing_id=listing_id,
        viewing_date=viewing_date,
        slot=slot,
        customer_name=customer_name,
        customer_phone=customer_phone,
    )
    return _redirect_with_state_preserved()


if __name__ == "__main__":
    app.run(debug=True)
