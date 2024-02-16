import plugins
import requests
import re
import pandas as pd
from urllib.parse import urlparse
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel import channel
from common.log import logger
from plugins import *
from datetime import datetime, timedelta

BASE_URL_AMAP = "https://restapi.amap.com/v3/"
AMAP_KEY = "xxxxx" # 换成自己高德的api

@plugins.register(
    name="Leoapi",
    desire_priority=90,
    hidden=False,
    desc="A plugin to handle specific keywords",
    version="0.1",
    author="leo",
)
class Leoapi(Plugin):
    def __init__(self):
        super().__init__()
        self.condition_2_and_3_cities = None  # 天气查询，存储重复城市信息，Initially set to None
        self.amap_key = AMAP_KEY
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        logger.info("[Leoapi] inited")
    
    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type not in [
            ContextType.TEXT
        ]:
            return
        content = e_context["context"].content.strip()
        logger.debug("[Leoapi] on_handle_context. content: %s" % content)
        
        #TODO 新闻

        live_weather_match = re.match(r'^现在(?:(.{2,7}?)(?:市|县|区|镇)?|(\d{7,9}))(?:的)?天气$', content)
        if live_weather_match:
            # 如果匹配成功，提取第一个捕获组
            city_or_id = live_weather_match.group(1) or live_weather_match.group(2)
            if not self.amap_key:
                self.handle_error("amap_key not configured", "天气请求失败")
                reply = self.create_reply(ReplyType.TEXT, "请先配置高德的key")
            else:
                result = f"\n" + self.get_live_weather(self.amap_key, city_or_id)
                reply = self.create_reply(ReplyType.TEXT, result)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        weather_match = re.match(r'^(?:(.{2,7}?)(?:市|县|区|镇)?|(\d{7,9}))(?:的)?天气$', content)
        if weather_match:
            # 如果匹配成功，提取第一个捕获组
            city_or_id = weather_match.group(1) or weather_match.group(2)
            if not self.amap_key:
                self.handle_error("amap_key not configured", "天气请求失败")
                reply = self.create_reply(ReplyType.TEXT, "请先配置高德的key")
            else:
                result = f"\n" + self.get_weather(self.amap_key, city_or_id)
                reply = self.create_reply(ReplyType.TEXT, result)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

    def get_help_text(self, verbose=False, **kwargs):
        short_help_text = " 发送特定指令以获取天气信息"
        
        if not verbose:
            return short_help_text
        
        help_text = "📚 发送关键词获取特定信息！\n"

        # 查询类
        help_text += "\n🔍 查询工具：\n"
        help_text += "  🌦️ 当前天气: 发送“现在+城市+天气”查天气，如“现在潮阳区天气”。\n"
        help_text += "  🌦️ 天气: 发送“城市+天气”查天气，如“潮阳区天气”。\n"

        return help_text

    def get_live_weather(self, amap_key, city_or_id: str):
        url = BASE_URL_AMAP + "weather/weatherInfo?"

        if city_or_id.isnumeric():
            city_id = city_or_id
        else:
            city_id = self.get_city_id(city_or_id)
            if city_id is None:
                return f"{city_or_id}不存在"
        
        base_params = {
            'city': city_id,
            'key': amap_key,
            'extensions': 'base',
            'output': 'json',
        }

        try:
            # 当前天气
            weather_base_data = self.make_request(url, "GET", params=base_params)
            if isinstance(weather_base_data, dict) and weather_base_data.get('status') == "1":
                lives = weather_base_data.get("lives")[0]

                formatted_output = []
                weather_info = (
                    f"地区: {lives['province']} {lives['city']}\n"
                    f"当前天气: {lives['weather']}\n"
                    f"当前温度: {lives['temperature']} ℃\n"
                    f"发布时间: {lives['reporttime']}\n"
                )
                formatted_output.append(weather_info)

                return "\n".join(formatted_output)
            else:
                return self.handle_error(weather_base_data, "获取失败，请查看服务器log")
        except Exception as e:
            return self.handle_error(e, "获取天气信息失败")

    def get_weather(self, amap_key, city_or_id: str):
        url = BASE_URL_AMAP + "weather/weatherInfo?"

        if city_or_id.isnumeric():
            city_id = city_or_id
        else:
            city_id = self.get_city_id(city_or_id)
            if city_id is None:
                return f"{city_or_id}不存在"

        all_params = {
            'city': city_id,
            'key': amap_key,
            'extensions': 'all',
            'output': 'json',
        }

        try:
            # 未来天气
            weather_all_data = self.make_request(url, "GET", params=all_params)
            if isinstance(weather_all_data, dict) and weather_all_data.get('status') == "1":
                forecasts = weather_all_data.get("forecasts")[0].get("casts")

                formatted_output = []
                for forecast in forecasts:
                    weather_info = (
                        f"日期    : {forecast['date']}\n"
                        f"星期    : {forecast['week']}\n"
                        f"白天天气: {forecast['dayweather']}\n"
                        f"夜晚天气: {forecast['nightweather']}\n"
                        f"白天温度: {forecast['daytemp']} ℃\n"
                        f"夜晚温度: {forecast['nighttemp']} ℃\n"
                    )
                    formatted_output.append(weather_info)

                return "\n".join(formatted_output)
            else:
                return self.handle_error(weather_all_data, "获取失败，请查看服务器log")

        except Exception as e:
            return self.handle_error(e, "获取天气信息失败")

    def make_request(self, url, method="GET", headers=None, params=None, data=None, json_data=None):
        try:
            if method.upper() == "GET":
                response = requests.request(method, url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = requests.request(method, url, headers=headers, data=data, json=json_data)
            else:
                return {"success": False, "message": "Unsupported HTTP method"}

            return response.json()
        except Exception as e:
            return e

    def create_reply(self, reply_type, content):
        reply = Reply()
        reply.type = reply_type
        reply.content = content
        return reply

    def handle_error(self, error, message):
        logger.error(f"{message}，错误信息：{error}")
        return message

    def is_valid_url(self, url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def is_valid_image_url(self, url):
        try:
            response = requests.head(url)  # Using HEAD request to check the URL header
            # If the response status code is 200, the URL exists and is reachable.
            return response.status_code == 200
        except requests.RequestException as e:
            # If there's an exception such as a timeout, connection error, etc., the URL is not valid.
            return False

    def get_city_id(self, city_name):
        try:
            excel_file_path = os.path.join(os.path.dirname(__file__), 'AMap_adcode_citycode.xlsx')
            df = pd.read_excel(excel_file_path)
            # 忽略excel中第一列每个单元格的最后一个字
            # df['部分中文名'] = df['中文名'].apply(lambda x: x[:-1] if pd.notna(x) else x)
            # 使用str.contains进行模糊匹配
            matching_row = df[df['中文名'].str.contains(city_name, na=False)]
            
            # 获取匹配到的第一个结果的adcode值
            adcode = matching_row['adcode'].iloc[0] if not matching_row.empty else None
            
            return adcode

        except Exception as e:
            return e
    
