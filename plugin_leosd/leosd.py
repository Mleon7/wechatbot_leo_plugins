# encoding:utf-8

import io
import json
import os

import webuiapi
import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from common.log import logger
from plugins import *
from config import conf

from PIL import Image
from datetime import datetime
import logging

import time
from chatgpt_tool_hub.chains.llm import LLMChain
from chatgpt_tool_hub.models import build_model_params
from chatgpt_tool_hub.models.model_factory import ModelFactory
from chatgpt_tool_hub.prompts import PromptTemplate

def get_script_directory():
    """获取当前脚本所在的目录"""
    return os.path.dirname(os.path.abspath(__file__))

STATE_FILE = os.path.join(get_script_directory(), "state.txt")
model_file = os.path.join(get_script_directory(), "model.txt")
# 定义枚举
class State(Enum):
    FREE = '0'
    MODEL_CHANGE = '1'
    DRAWING = '2'

def set_state(state_num):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as file:
            file.write(str(state_num.value))
    except Exception as e:
        print(f"An error occurred while writing to the file: {e}")

def get_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return file.readline().strip()  # 去掉换行符
    except Exception as e:
        print(f"An error occurred while reading from the file: {e}")
        return None  # 或者根据实际情况返回适当的默认值

def set_current_model(model_keyword):
    with open(model_file, "w", encoding="utf-8") as file:
        file.write(model_keyword)

def get_current_model():
    with open(model_file, "r", encoding="utf-8") as file:
        return file.readline()


def save_image_to_folder(result, script_directory, folder_name="img"):
    # 获取当前时间并格式化为字符串
    current_time = datetime.now().strftime("%Y%m%d%H%M%S")

    # 构建保存图像的文件夹路径
    img_folder_path = os.path.join(script_directory, folder_name)

    # 确保文件夹存在，如果不存在则创建
    os.makedirs(img_folder_path, exist_ok=True)

    # 构建完整的文件路径，以当前时间作为文件名
    file_path = os.path.join(img_folder_path, f"{current_time}.png")

    # 将图像保存到文件系统中
    result.image.save(file_path, format="PNG")

    return file_path



log_file_path = os.path.join(get_script_directory(), 'leosd.log')
# logging.basicConfig(filename=log_file_path, level=logging.INFO)
# 创建一个日志记录器
leosd_logger = logging.getLogger(__name__)
# 设置日志级别
leosd_logger.setLevel(logging.DEBUG)

# 创建文件处理器，将日志保存到文件
file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# 创建终端处理器，用于在终端打印日志
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# 创建格式化器，定义日志的输出格式
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 将处理器添加到日志记录器
leosd_logger.addHandler(file_handler)
leosd_logger.addHandler(console_handler)


# TODO: few shot
TRANSLATE2SD_PROMPT = '''
I want you to act as a Stable Diffusion Art Prompt Generator. The formula for a prompt is made of parts, the parts are indicated by brackets. The [Subject] is the person place or thing the image is focused on. [Emotions] is the emotional look the subject or scene might have. [Verb] is What the subject is doing, such as standing, jumping, working and other varied that match the subject. [Adjectives] like beautiful, rendered, realistic, tiny, colorful and other varied that match the subject. 
I will give you a [Subject], you will respond in English with a full prompt. Present the result as one full sentence, no line breaks, no delimiters, and keep it as concise as possible while still conveying a full scene.
Here is a sample of how it should be output: "Beautiful woman, contemplative and reflective, sitting on a bench, cozy sweater, autumn park with colorful leaves"
Additionally, the topic I provide to you may be described in Chinese, but your response should only be in English.
My Input: {input}
'''

prefix = {"get": "查看", "set": "更换"}

@plugins.register(
    name="leosd",
    desire_priority=1,
    desc="leo: stable-diffusion webui画图",
    version="0.1",
    author="leo",
)
class LeoSD(Plugin):
    def __init__(self):
        super().__init__()
        curdir = os.path.dirname(__file__)
        config_path = os.path.join(curdir, "config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self.rules = config["rules"]
                defaults = config["defaults"]
                self.default_params = defaults["params"]
                self.default_options = defaults["options"]
                self.start_args = config["start"]
                self.api = webuiapi.WebUIApi(**self.start_args)
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            logger.info("[LeoSD] inited")
        except Exception as e:
            if isinstance(e, FileNotFoundError):
                logger.warn(f"[LeoSD] init failed, {config_path} not found, ignore")
            else:
                logger.warn("[LeoSD] init failed, ignore")
            raise e

    def _get_available_models_text(self):
        help_text = "目前可用模型：\n"
        for rule in self.rules:
            keywords = [f"[{keyword}]" for keyword in rule['keywords']]
            help_text += f"{','.join(keywords)}\n"
        return help_text.rstrip("\n")

    def _translate2sd(self, text):
        llm = ModelFactory().create_llm_model(**build_model_params({
            "openai_api_key": conf().get("open_ai_api_key", ""),
            "proxy": conf().get("proxy", ""),
        }))

        prompt = PromptTemplate(
            input_variables=["input"],
            template=TRANSLATE2SD_PROMPT,
        )
        bot = LLMChain(llm=llm, prompt=prompt)
        content = bot.run(text)
        return content

    def on_handle_context(self, e_context: EventAction):
        script_directory = get_script_directory()

        if e_context['context'].type != ContextType.IMAGE_CREATE:
            return
        channel = e_context['channel']
        if ReplyType.IMAGE in channel.NOT_SUPPORT_REPLYTYPE:
            return

        logger.debug("[LeoSD] on_handle_context. content: %s" %e_context['context'].content)

        logger.info("[LeoSD] image_query={}".format(e_context['context'].content))
        reply = Reply()
        try:
            is_test = True
            current_state = State(get_state())

            if current_state == State.MODEL_CHANGE:
                reply.type = ReplyType.INFO
                reply.content = "正在换模型中，等换完后再来吧"
                e_context.action = EventAction.BREAK_PASS

            elif current_state == State.DRAWING:
                reply.type = ReplyType.INFO
                reply.content = "正在跑图中，等跑完图后再来吧"
                e_context.action = EventAction.BREAK_PASS

            else:
                content = e_context["context"].content
                leosd_logger.info("[LeoSD] content: %s" % content)

                if content.strip().startswith(prefix["get"]):
                    reply.type = ReplyType.INFO
                    help_text = f"当前模型是: [{get_current_model()}]\n\n"
                    help_text += self._get_available_models_text()
                    reply.content = help_text
                    e_context.action = EventAction.BREAK_PASS

                elif content.strip().startswith(prefix["set"]):
                    keyword = content[len(prefix["set"]):].strip()

                    rule_options = {}
                    matched = False
                    for rule in self.rules:
                        if keyword in rule["keywords"]:
                            if "options" in rule:
                                for key in rule["options"]:
                                    rule_options[key] = rule["options"][key]
                            matched = True

                    if matched:
                        set_state(State.MODEL_CHANGE)
                        options = {**self.default_options, **rule_options}
                        if len(options) > 0:
                            logger.info("[LeoSD] cover options={}".format(options))
                            leosd_logger.info("[LeoSD] cover options={}".format(options))
                        self.api.set_options(options) if not is_test else None
                        reply.type = ReplyType.INFO
                        reply.content = f"更换{keyword}模型成功！"
                        set_current_model(keyword)
                        set_state(State.FREE)
                        e_context.action = EventAction.BREAK_PASS
                    else:
                        logger.info("[LeoSD] keyword not matched: %s" % keyword)
                        leosd_logger.info("[LeoSD] keyword not matched: %s" % keyword)
                        reply.type = ReplyType.INFO
                        reply.content = "输入的模型不正确，请检查"
                        e_context.action = EventAction.BREAK_PASS


                else: # sdprompt
                    set_state(State.DRAWING)
                    keyword = get_current_model()
                    user_prompt = content
                    rule_params = {}
                    matched = False
                    for rule in self.rules:
                        if keyword in rule["keywords"]:
                            for key in rule["params"]:
                                rule_params[key] = rule["params"][key]
                            matched = True
                    if not matched:
                        logger.info("[LeoSD] current_model not matched: %s" % keyword)
                        leosd_logger.info("[LeoSD] current_model not matched: %s" % keyword)

                    params = {**self.default_params, **rule_params}
                    params["prompt"] = params.get("prompt", "")

                    try:
                        sdprompt = self._translate2sd(user_prompt)
                        # TODO 将其它符号都换成 ","
                    except Exception as e:
                        logger.info("[LeoSD] translate failed: {}".format(e))
                        logger.info("[LeoSD] translated sdprompt={}".format(sdprompt))
                    # TODO 让sdprompt 在最前面
                    params["prompt"] += f", {sdprompt}"


                    logger.info("[LeoSD] params={}".format(params))
                    leosd_logger.info("[LeoSD] params={}".format(params))

                    # TODO: 能先发文字提示，再发图片吗
                    if is_test:
                        reply.type = ReplyType.INFO
                        reply.content = sdprompt
                        set_state(State.FREE)
                        e_context.action = EventAction.BREAK_PASS
                    else:
                        result = self.api.txt2img(
                            **params
                        )
                        leosd_logger.info("[LeoSD] Done")
                        save_image_to_folder(result, script_directory)

                        reply.type = ReplyType.IMAGE
                        b_img = io.BytesIO()
                        result.image.save(b_img, format="PNG")
                        reply.content = b_img
                        set_state(State.FREE)
                        e_context.action = EventAction.BREAK_PASS

        except Exception as e:
            reply.type = ReplyType.ERROR
            reply.content = "[LeoSD] "+str(e)
            logger.error("[LeoSD] exception: %s" % e)
            e_context.action = EventAction.CONTINUE  # 事件继续，交付给下个插件或默认逻辑

        finally:
            e_context['reply'] = reply
    
    def get_help_text(self, **kwargs):
        if not conf().get('image_create_prefix'):
            return "画图功能未启用"
        else:
            trigger = conf()['image_create_prefix'][0] # TODO 获取全部，如 画 draw
        help_text = "利用leo:stable-diffusion来画图。\n"

        help_text += f"一、触发方式\n1.画图: \"{trigger} 场景\"，例如\"{trigger} 一只猫\"\n2.更换画图模型: \"{trigger} 更换 模型名称\", 例如\"{trigger} 更换 二次元\"\n3.查看当前模型: \"{trigger} 查看\"\n"
        help_text += "目前可用模型：\n"
        for rule in self.rules:
            keywords = [f"[{keyword}]" for keyword in rule['keywords']]
            help_text += f"{','.join(keywords)}"
            help_text += "\n"
            # if "desc" in rule:
            #     help_text += f"-{rule['desc']}\n"
            # else:
            #     help_text += "\n"

        help_text += """
注意！
1. 网络非法外之地，不合适的词可能会导致微信被封掉。
2. 用的是我的电脑，不能保证什么时候会崩掉
3. 生成一张图大概要2分钟
4. 更换模型大概要1分钟"""
        return help_text