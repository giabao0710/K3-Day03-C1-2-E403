"""
🔌 MULTI-PROVIDER LLM ADAPTER (OpenAI, Gemini, Anthropic, DeepSeek, OpenRouter & Offline Mock)
Hỗ trợ chuyển đổi linh hoạt giữa các nhà cung cấp AI chỉ bằng cách đổi biến môi trường LLM_PROVIDER.
"""

import os
import sys
import re
import requests
from dotenv import load_dotenv

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

class BaseLLMProvider:
    """Interface cơ sở cho tất cả các LLM Provider"""
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"
        
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env!"
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = client.models.generate_content(
                model=self.model_name,
                contents=contents
            )
            return response.text
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (GPT-4o, GPT-3.5-turbo, etc.)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            return "[OpenAI Error]: Chưa cấu hình OPENAI_API_KEY trong file .env!"
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[OpenAI Exception]: {str(e)}"


class DeepSeekProvider(BaseLLMProvider):
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "deepseek-v4-flash"
        
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_deepseek_api_key_here":
            return "[DeepSeek Error]: Chưa cấu hình DEEPSEEK_API_KEY trong file .env!"
        try:
            import openai
            client = openai.OpenAI(
                api_key=self.api_key,
                base_url="https://api.deepseek.com"
            )
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[DeepSeek Exception]: {str(e)}"


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude Provider (Claude 3.5 Sonnet, Claude 3 Haiku)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "claude-3-haiku-20240307"
        
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_anthropic_api_key_here":
            return "[Anthropic Error]: Chưa cấu hình ANTHROPIC_API_KEY trong file .env!"
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            kwargs = {
                "model": self.model_name,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            }
            if system_prompt:
                kwargs["system"] = system_prompt
                
            response = client.messages.create(**kwargs)
            return response.content[0].text
        except Exception as e:
            return f"[Anthropic Exception]: {str(e)}"


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter Provider (Hỗ trợ gọi mọi model qua OpenRouter API)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "google/gemini-2.5-flash"
        
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_openrouter_api_key_here":
            return "[OpenRouter Error]: Chưa cấu hình OPENROUTER_API_KEY trong file .env!"
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.model_name,
                "messages": messages
            }
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                return data["choices"][0]["message"]["content"]
            else:
                return f"[OpenRouter API Error {res.status_code}]: {res.text}"
        except Exception as e:
            return f"[OpenRouter Exception]: {str(e)}"


class MockProvider(BaseLLMProvider):
    """Offline Mock Provider (Cho bài test không cần kết nối API)"""
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if "Bạn là một ReAct Agent" in system_prompt:
            return self._generate_react_response(prompt)
        text = prompt.lower()
        if any(keyword in text for keyword in ["nhà trọ", "căn hộ dịch vụ", "thuê lần đầu"]):
            return (
                "Nhà trọ thường rẻ hơn, diện tích gọn và ít dịch vụ đi kèm; căn hộ dịch vụ thường có nội thất đầy đủ, "
                "vệ sinh hoặc bảo vệ và chi phí cao hơn. Khi thuê lần đầu, bạn nên kiểm tra hợp đồng, tiền cọc, điện nước, "
                "quy định ra vào và tình trạng phòng trước khi chốt."
            )
        return "Mình là mock provider offline và hiện chỉ mô phỏng các tình huống trong bài lab."

    def _generate_react_response(self, prompt: str) -> str:
        user_query_match = re.search(r"Câu hỏi người dùng:\s*(.+)", prompt)
        user_query = user_query_match.group(1).strip() if user_query_match else prompt.strip()
        normalized = user_query.lower()

        if "case_guardrail_loop" in normalized:
            return "Thought: Tôi sẽ thử một action không hợp lệ.\nAction: unknown_tool[]"

        observations = re.findall(
            r"Observation:\s*([\s\S]*?)(?=\nThought:|\n\nHãy trả lời|\Z)",
            prompt,
        )
        actions = re.findall(r"Action:\s*([A-Za-z_][A-Za-z0-9_]*)\[", prompt)
        last_observation = observations[-1].strip() if observations else ""
        last_tool = actions[-1] if actions else ""

        listing_id_match = re.search(r"(?:listing_id|tin|mã)\D*(\d{4,})", user_query, flags=re.IGNORECASE)
        listing_id = listing_id_match.group(1) if listing_id_match else "123456789"
        observed_listing_match = re.search(r'"listing_id":\s*(\d+)', last_observation)
        if last_tool == "search_rentals" and observed_listing_match:
            listing_id = observed_listing_match.group(1)
        request_id_match = re.search(r"(?:request_id|request|yêu cầu)\D*(\d+)", user_query, flags=re.IGNORECASE)
        request_id = request_id_match.group(1) if request_id_match else "1"
        date_match = re.search(r"(20\d{2}-\d{2}-\d{2})", user_query)
        viewing_date = date_match.group(1) if date_match else "2026-08-03"
        slot_match = re.search(r"(\d{2}:\d{2})", user_query)
        slot = slot_match.group(1) if slot_match else "09:00"
        phone_match = re.search(r"(0\d{8,10})", user_query)
        customer_phone = phone_match.group(1) if phone_match else "0901234567"
        customer_name = "Nguyen Van A"
        if "tran thi b" in normalized:
            customer_name = "Tran Thi B"
        elif "nguyen van a" in normalized:
            customer_name = "Nguyen Van A"

        if not last_observation:
            if "sự khác nhau" in normalized or "thuê nhà trọ lần đầu" in normalized:
                return (
                    "Thought: Đây là câu hỏi kiến thức chung nên không cần gọi tool.\n"
                    "Final Answer: Nhà trọ thường có chi phí thấp và ít dịch vụ hơn căn hộ dịch vụ. "
                    "Khi thuê lần đầu, bạn nên kiểm tra hợp đồng, tiền cọc, điện nước, an ninh và hiện trạng phòng."
                )
            if "calendar" in normalized or "tạo lịch" in normalized:
                return (
                    "Thought: Tôi đã có request_id nên cần tạo calendar event.\n"
                    f"Action: create_calendar_event[{request_id}]"
                )
            if "đặt lịch" in normalized:
                return (
                    "Thought: Tôi cần kiểm tra slot trước khi gửi yêu cầu đặt lịch.\n"
                    f"Action: check_viewing_slots[{listing_id}, \"{viewing_date}\"]"
                )
            if "lịch trống" in normalized or "khung giờ" in normalized:
                return (
                    "Thought: Tôi cần kiểm tra các slot còn trống cho listing đã chọn.\n"
                    f"Action: check_viewing_slots[{listing_id}, \"{viewing_date}\"]"
                )
            if "tìm" in normalized:
                return (
                    "Thought: Tôi cần tìm các tin cho thuê phù hợp với ngân sách của khách.\n"
                    "Action: search_rentals[12000, 1050, 1000000, 2000000, \"u,h\", 5]"
                )
            if "chi tiết" in normalized or "xem tin" in normalized:
                return (
                    "Thought: Tôi đã có listing_id nên cần lấy chi tiết tin đăng.\n"
                    f"Action: get_listing_details[{listing_id}]"
                )
            return (
                "Thought: Tôi cần tìm các tin cho thuê phù hợp với ngân sách của khách.\n"
                "Action: search_rentals[12000, 1050, 1000000, 2000000, \"u,h\", 5]"
            )

        if "LỖI:" in last_observation:
            return (
                "Thought: Tool vừa báo lỗi nên tôi cần dừng và giải thích rõ ràng cho người dùng.\n"
                f"Final Answer: {last_observation}"
            )

        if last_tool == "search_rentals":
            if "chi tiết" in normalized or "xem tin" in normalized:
                return (
                    "Thought: Tôi đã tìm được listing phù hợp và cần lấy chi tiết tin đầu tiên.\n"
                    f"Action: get_listing_details[{listing_id}]"
                )
            return (
                "Thought: Tôi đã có danh sách tin phù hợp để tóm tắt cho người dùng.\n"
                "Final Answer: Mình đã tìm được một số tin phù hợp trong tầm giá 1-2 triệu. "
                "Bạn có thể chọn một listing_id từ kết quả để mình xem chi tiết hoặc kiểm tra lịch trống."
            )

        if last_tool == "get_listing_details":
            return (
                "Thought: Tôi đã có đủ chi tiết của tin đăng để tóm tắt cho người dùng.\n"
                f"Final Answer: Tin {listing_id} đã có chi tiết đầy đủ về giá, diện tích, mô tả và thông tin người đăng. "
                "Nếu bạn muốn, mình có thể kiểm tra lịch trống để đặt lịch xem nhà tiếp."
            )

        if last_tool == "check_viewing_slots":
            if slot not in last_observation:
                available_slot_match = re.search(r'"available_slots":\s*\[\s*"([^"]+)"', last_observation)
                slot = available_slot_match.group(1) if available_slot_match else "09:00"
            if "đặt lịch" in normalized:
                return (
                    "Thought: Slot còn trống nên tôi có thể gửi yêu cầu xem nhà ngay.\n"
                    f"Action: send_viewing_request[{listing_id}, \"{viewing_date}\", \"{slot}\", "
                    f"\"{customer_name}\", \"{customer_phone}\"]"
                )
            return (
                "Thought: Tôi đã có danh sách lịch trống để phản hồi cho người dùng.\n"
                f"Final Answer: Tin {listing_id} còn trống các khung giờ trong ngày {viewing_date}. "
                "Nếu bạn muốn chốt một giờ cụ thể, mình có thể gửi yêu cầu đặt lịch ngay."
            )

        if last_tool == "send_viewing_request":
            request_id_match = re.search(r'"request_id":\s*(\d+)', last_observation)
            request_id = request_id_match.group(1) if request_id_match else "1"
            return (
                "Thought: Yêu cầu đã được tạo, tôi cần tạo luôn calendar event nội bộ.\n"
                f"Action: create_calendar_event[{request_id}]"
            )

        if last_tool == "create_calendar_event":
            return (
                "Thought: Tôi đã có đủ thông tin để xác nhận lịch xem nhà.\n"
                "Final Answer: Đã tạo yêu cầu xem nhà thành công, trạng thái hiện là pending và sự kiện lịch nội bộ cũng đã được tạo."
            )

        return "Thought: Tôi đã có đủ thông tin để trả lời.\nFinal Answer: Mình đã hoàn tất yêu cầu."


def get_llm_provider(provider_name: str = None) -> BaseLLMProvider:
    """Factory function tự chọn Provider từ biến môi trường LLM_PROVIDER"""
    name = (provider_name or os.getenv("LLM_PROVIDER") or "mock").lower().strip()
    
    if name == "gemini":
        return GeminiProvider()
    elif name == "openai":
        return OpenAIProvider()
    elif name == "deepseek":
        return DeepSeekProvider()
    elif name == "anthropic":
        return AnthropicProvider()
    elif name == "openrouter":
        return OpenRouterProvider()
    else:
        return MockProvider()


if __name__ == "__main__":
    print("=== TEST MULTI-PROVIDER LLM ADAPTER ===")
    provider = get_llm_provider()
    print(f"✅ Provider đang dùng: {provider.__class__.__name__}")
    print(f"🤖 User Query: Hello")
    print(f"💬 Response  : {provider.generate('Hello')}")
