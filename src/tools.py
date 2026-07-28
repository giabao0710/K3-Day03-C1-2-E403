"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
Nơi khai báo tất cả các "món đồ nghề" mà ReAct Agent có thể gọi.
"""

import json

import requests


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
        "price_vnd": ad.get("price"),
        "price_text": ad.get("price_string", "Không rõ"),
        "area_m2": ad.get("size"),
        "address": ", ".join(address_parts) if address_parts else "Không rõ",
        "district": area_name or "Không rõ",
        "ward": ward_name or "Không rõ",
        "furnishing": _extract_furnishing(ad.get("params") or []),
        "contact_name": seller_name,
        "status": ad.get("status", "Không rõ"),
        "posted_time": ad.get("date", "Không rõ"),
        "summary": ad.get("body", "").strip().replace("\n", " ")[:280],
        "image_count": ad.get("number_of_images", 0),
        "thumbnail": ad.get("thumbnail_image") or ad.get("image"),
    }


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

    summaries = []
    for ad in ads:
        if not isinstance(ad, dict):
            continue

        listing_id = ad.get("list_id")
        if isinstance(listing_id, int):
            SEARCH_CACHE[listing_id] = ad
        summaries.append(_build_listing_summary(ad))

    normalized_response = {
        "tool": "search_rentals",
        "total_found": total if isinstance(total, int) else len(summaries),
        "results": summaries,
    }
    return json.dumps(normalized_response, ensure_ascii=False, indent=2)


def get_listing_details(listing_id: int) -> str:
    """
    Lấy thông tin chi tiết của một tin đăng theo listing_id.

    Args:
        listing_id (int): Mã tin đăng Chợ Tốt.

    Returns:
        str: JSON string chứa thông tin đầy đủ của listing.
    """
    listing = SEARCH_CACHE.get(listing_id)
    if listing is None:
        return (
            f"LỖI: Không tìm thấy listing_id={listing_id}. "
            "Hãy gọi search_rentals trước."
        )
    return json.dumps(listing, ensure_ascii=False, indent=2)


# Danh sách các tool được đăng ký để Agent sử dụng
AVAILABLE_TOOLS = {
    # "get_weather": get_weather,
    # "search_flights": search_flights,
    "search_rentals": search_rentals,
    "get_listing_details": get_listing_details,
}



# print(search_rentals())
