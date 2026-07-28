"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
Nơi khai báo tất cả các "món đồ nghề" mà ReAct Agent có thể gọi.
"""

import json
import sqlite3
from datetime import datetime

import requests
from viewing_store import (
    create_event_for_request,
    create_viewing_request,
    get_available_slots,
    get_calendar_event_for_request,
    get_viewing_request,
)


CHOTOT_API_URL = "https://gateway.chotot.com/v1/public/ad-listing"
REQUEST_TIMEOUT_SECONDS = 20
SEARCH_CACHE = {}


def _extract_furnishing(params: list[dict]) -> str:
    for param in params:
        if param.get("id") == "furnishing_rent":
            value = param.get("value")
            if isinstance(value, str):
                return value
    return "Không rõ"


def _build_listing_summary(ad: dict) -> dict:
    list_id = ad.get("list_id")
    street_number = ad.get("street_number", "")
    street_name = ad.get("street_name", "")
    ward_name = ad.get("ward_name_v3") or ad.get("ward_name") or ""
    area_name = ad.get("area_name") or ""
    region_name = ad.get("region_name_v3") or ad.get("region_name") or ""
    address_parts = [part.strip() for part in [street_number, street_name, ward_name, area_name, region_name] if part]
    seller_info = ad.get("seller_info") or {}
    seller_name = seller_info.get("full_name") or ad.get("full_name") or ad.get("account_name") or "Không rõ"

    return {
        "listing_id": list_id,
        "title": ad.get("subject", "Không có tiêu đề"),
        "price_text": ad.get("price_string", "Không rõ"),
        "area_m2": ad.get("size"),
        "address": ", ".join(address_parts) if address_parts else "Không rõ",
        "status": ad.get("status", "Không rõ"),
    }


def _is_valid_listing_id(listing_id: int) -> bool:
    return isinstance(listing_id, int) and listing_id > 0


# def get_weather(location: str) -> str:
#     """
#     Tra cứu thời tiết hiện tại của một thành phố.
    
#     Args:
#         location (str): Tên thành phố (Ví dụ: 'Hà Nội', 'TP.HCM', 'Đà Nẵng')
        
#     Returns:
#         str: Thông tin thời tiết chi tiết
#     """
#     loc_lower = location.lower()
#     if "hà nội" in loc_lower or "ha noi" in loc_lower:
#         return "Thời tiết Hà Nội: 28°C, Nắng nhẹ, Độ ẩm 65%."
#     elif "hồ chí minh" in loc_lower or "tp.hcm" in loc_lower or "hcm" in loc_lower:
#         return "Thời tiết TP.HCM: 33°C, Nắng nóng, Có mây."
#     elif "đà nẵng" in loc_lower or "da nang" in loc_lower:
#         return "Thời tiết Đà Nẵng: 30°C, Gió nhẹ, Mát mẻ."
#     else:
#         return f"LỖI: Không tìm thấy dữ liệu thời tiết cho địa điểm '{location}'."


# def search_flights(origin: str, destination: str) -> str:
#     """
#     Tra cứu chuyến bay giữa hai địa điểm.
    
#     Args:
#         origin (str): Nơi đi (Ví dụ: 'TP.HCM')
#         destination (str): Nơi đến (Ví dụ: 'Hà Nội')
        
#     Returns:
#         str: Danh sách chuyến bay khả dụng và giá vé
#     """
#     return (
#         f"Chuyến bay từ {origin} -> {destination} ngày mai:\n"
#         f"1. VN123 (08:00) - Giá: 1,500,000 VNĐ (Còn vé)\n"
#         f"2. VJ456 (14:30) - Giá: 1,200,000 VNĐ (Còn vé)"
#     )


def search_rentals(
    region_v2: int = 12000,
    category: int = 1050,
    min_price: int = 1_000_000,
    max_price: int = 2_000_000,
    property_types: str = "u,h",
    limit: int = 10,
) -> str:
    """
    Tìm danh sách phòng trọ / căn hộ cho thuê từ API public của Chợ Tốt.

    Hàm này lưu toàn bộ payload theo `listing_id` trong SEARCH_CACHE để các tool
    khác có thể dùng lại, nhưng chỉ trả về dữ liệu tóm tắt cho Agent.

    Args:
        region_v2 (int): Mã khu vực Chợ Tốt. Mặc định 12000 = Hà Nội.
        category (int): Mã category. Mặc định 1050 = Phòng trọ.
        min_price (int): Giá tối thiểu theo VND.
        max_price (int): Giá tối đa theo VND.
        property_types (str): Loại tin đăng, ví dụ "u,h".
        limit (int): Số lượng kết quả tối đa cần lấy.

    Returns:
        str: JSON string chứa shortlist kết quả phù hợp cho ReAct Agent.
    """
    if not all(isinstance(value, int) for value in (region_v2, category, min_price, max_price, limit)):
        return "LỖI: region_v2, category, min_price, max_price và limit phải là số nguyên."
    if min_price < 0 or max_price < 0:
        return "LỖI: min_price và max_price không được âm."
    if min_price > max_price:
        return "LỖI: min_price không được lớn hơn max_price."
    if limit <= 0:
        return "LỖI: limit phải lớn hơn 0."
    if not isinstance(property_types, str) or not property_types.strip():
        return "LỖI: property_types phải là chuỗi hợp lệ."

    params = {
        "region_v2": region_v2,
        "cg": category,
        "price": f"{min_price}-{max_price}",
        "st": property_types,
        "limit": limit,
        "w": 1,
        "include_expired_ads": "true",
        "key_param_included": "true",
        "video_count_included": "true",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    try:
        response = requests.get(
            CHOTOT_API_URL,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        return f"LỖI: API Chợ Tốt trả về mã {exc.response.status_code if exc.response else 'không rõ'}."
    except requests.RequestException as exc:
        return f"LỖI: Không thể kết nối API Chợ Tốt. Chi tiết: {exc}"

    try:
        payload = response.json()
    except ValueError:
        return "LỖI: API Chợ Tốt trả về dữ liệu không phải JSON hợp lệ."

    ads = payload.get("ads")
    total = payload.get("total")
    if not isinstance(ads, list):
        return "LỖI: API Chợ Tốt không trả về danh sách tin đăng hợp lệ."

    try:
        summaries = []
        for ad in ads:
            if not isinstance(ad, dict):
                continue

            listing_id = ad.get("list_id")
            if _is_valid_listing_id(listing_id):
                SEARCH_CACHE[listing_id] = ad
            summaries.append(_build_listing_summary(ad))

        normalized_response = {
            "tool": "search_rentals",
            "total_found": total if isinstance(total, int) else len(summaries),
            "results": summaries,
        }
        return json.dumps(normalized_response, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as exc:
        return f"LỖI: Không thể chuẩn hóa dữ liệu tin đăng. Chi tiết: {exc}"


def get_listing_details(listing_id: int) -> str:
    """
    Lấy thông tin chi tiết của một tin đăng theo listing_id.

    Args:
        listing_id (int): Mã tin đăng Chợ Tốt.

    Returns:
        str: JSON string chứa thông tin đầy đủ của listing.
    """
    if not _is_valid_listing_id(listing_id):
        return "LỖI: listing_id phải là số nguyên dương."

    listing = SEARCH_CACHE.get(listing_id)
    if listing is None:
        return (
            f"LỖI: Không tìm thấy listing_id={listing_id}. "
            "Hãy gọi search_rentals trước."
        )
    try:
        return json.dumps(listing, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as exc:
        return f"LỖI: Không thể đọc chi tiết tin đăng {listing_id}. Chi tiết: {exc}"


def check_viewing_slots(listing_id: int, viewing_date: str) -> str:
    """
    Kiểm tra các khung giờ còn trống để xem nhà cho một tin đăng.

    Args:
        listing_id (int): Mã tin đăng cần xem nhà.
        viewing_date (str): Ngày xem nhà theo định dạng YYYY-MM-DD.

    Returns:
        str: JSON string chứa các khung giờ còn trống.
    """
    if not _is_valid_listing_id(listing_id):
        return "LỖI: listing_id phải là số nguyên dương."
    if not isinstance(viewing_date, str) or not viewing_date.strip():
        return "LỖI: viewing_date phải là chuỗi theo định dạng YYYY-MM-DD."

    try:
        datetime.strptime(viewing_date, "%Y-%m-%d")
    except ValueError:
        return "LỖI: viewing_date phải theo định dạng YYYY-MM-DD."

    try:
        available_slots = get_available_slots(listing_id, viewing_date)
        payload = {
            "tool": "check_viewing_slots",
            "listing_id": listing_id,
            "viewing_date": viewing_date,
            "available_slots": available_slots,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except sqlite3.Error as exc:
        return f"LỖI: Không thể kiểm tra lịch xem nhà. Chi tiết: {exc}"


def send_viewing_request(
    listing_id: int,
    viewing_date: str,
    slot: str,
    customer_name: str,
    customer_phone: str,
) -> str:
    """
    Gửi yêu cầu đặt lịch xem nhà và lưu trạng thái pending vào SQLite.

    Args:
        listing_id (int): Mã tin đăng cần xem nhà.
        viewing_date (str): Ngày xem nhà theo định dạng YYYY-MM-DD.
        slot (str): Khung giờ xem nhà, ví dụ 14:00.
        customer_name (str): Tên khách cần đặt lịch.
        customer_phone (str): Số điện thoại liên hệ của khách.

    Returns:
        str: JSON string chứa request_id và trạng thái yêu cầu.
    """
    if not _is_valid_listing_id(listing_id):
        return "LỖI: listing_id phải là số nguyên dương."
    if not isinstance(viewing_date, str) or not viewing_date.strip():
        return "LỖI: viewing_date phải là chuỗi theo định dạng YYYY-MM-DD."
    if not isinstance(slot, str) or not slot.strip():
        return "LỖI: slot phải là chuỗi hợp lệ."
    if not isinstance(customer_name, str) or not customer_name.strip():
        return "LỖI: customer_name không được để trống."
    if not isinstance(customer_phone, str) or not customer_phone.strip():
        return "LỖI: customer_phone không được để trống."

    try:
        datetime.strptime(viewing_date, "%Y-%m-%d")
    except ValueError:
        return "LỖI: viewing_date phải theo định dạng YYYY-MM-DD."

    try:
        available_slots = get_available_slots(listing_id, viewing_date)
        if slot not in available_slots:
            return f"LỖI: Khung giờ {slot} không còn trống cho ngày {viewing_date}."

        request_id = create_viewing_request(
            listing_id=listing_id,
            viewing_date=viewing_date,
            slot=slot,
            customer_name=customer_name.strip(),
            customer_phone=customer_phone.strip(),
        )
        payload = {
            "tool": "send_viewing_request",
            "request_id": request_id,
            "listing_id": listing_id,
            "viewing_date": viewing_date,
            "slot": slot,
            "status": "pending",
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except sqlite3.Error as exc:
        return f"LỖI: Không thể lưu yêu cầu xem nhà. Chi tiết: {exc}"


def create_calendar_event(request_id: int) -> str:
    """
    Tạo một calendar event nội bộ từ viewing request đã lưu trong SQLite.

    Args:
        request_id (int): Mã yêu cầu đặt lịch xem nhà.

    Returns:
        str: JSON string chứa thông tin event đã tạo.
    """
    if not isinstance(request_id, int) or request_id <= 0:
        return "LỖI: request_id phải là số nguyên dương."

    try:
        request_row = get_viewing_request(request_id)
        if request_row is None:
            return f"LỖI: Không tìm thấy request_id={request_id}."

        existing_event = get_calendar_event_for_request(request_id)
        if existing_event is not None:
            payload = {
                "tool": "create_calendar_event",
                "event_id": existing_event["event_id"],
                "request_id": request_id,
                "start_at": existing_event["start_at"],
                "event_status": existing_event["event_status"],
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)

        start_at = f"{request_row['viewing_date']}T{request_row['slot']}:00"
        event_status = "tentative" if request_row["status"] == "pending" else "confirmed"
        event_id = create_event_for_request(
            request_id=request_id,
            title=f"Xem nhà listing {request_row['listing_id']}",
            start_at=start_at,
            event_status=event_status,
        )
        payload = {
            "tool": "create_calendar_event",
            "event_id": event_id,
            "request_id": request_id,
            "start_at": start_at,
            "event_status": event_status,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except sqlite3.Error as exc:
        return f"LỖI: Không thể tạo calendar event. Chi tiết: {exc}"


# Danh sách các tool được đăng ký để Agent sử dụng
AVAILABLE_TOOLS = {
    # "get_weather": get_weather,
    # "search_flights": search_flights,
    "search_rentals": search_rentals,
    "get_listing_details": get_listing_details,
    "check_viewing_slots": check_viewing_slots,
    "send_viewing_request": send_viewing_request,
    "create_calendar_event": create_calendar_event,
}
