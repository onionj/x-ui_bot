import base64
import json
import time
import re

from typing import TypedDict
from threading import Thread, main_thread

import requests

from pyrogram import Client, filters
from pyrogram.types import Message

from pydantic import BaseSettings


class Settings(BaseSettings):
    PANEL_ADDRESS: str
    PANEL_USERNAME: str
    PANEL_PASSWORD: str

    API_HASH: str
    API_ID: str
    BOT_TOKEN: str


    class Config:
        env_file = ".env"


settings = Settings()


class UserDataType(TypedDict):
    id: int
    alterId: int
    email: str
    limitIp: int
    totalGB: int
    expiryTime: int
    hashed_id: str
    inboundId: int
    enable: bool
    up: int
    down: int
    total: int


class UserFetch:
    def __init__(
        self, panel_ip_address: str, panel_username: str, panel_password: str
    ) -> None:
        self.panel_ip_address = panel_ip_address.rstrip("/")
        self.panel_username = panel_username
        self.panel_password = panel_password
        self.login_session = ""
        self.requests_session = requests.Session()
        self.users_datas: UserDataType = {}

    def login(self):
        try:
            res = self.requests_session.post(
                f"{self.panel_ip_address}/login/",
                data={"username": self.panel_username, "password": self.panel_password},
                timeout=3,
            )

            if res and (res.json())["success"] == True:
                self.login_session = res.cookies.get("session")
                return True

            return False

        except Exception as e:
            print(e)
            return False

    def update(self):
        """call `/xui/inbound/list` api and save new data"""
        while main_thread().is_alive():
            new_user_datas = {}

            try:
                res = self.requests_session.post(
                    f"{self.panel_ip_address}/xui/inbound/list",
                    cookies={"session": self.login_session},
                    timeout=2,
                )
                if res.ok and res.json()["success"] == True:
                    datas = res.json()

                    for port_user in datas["obj"]:
                        users = json.loads(port_user["settings"])["clients"]

                        for user in users:
                            new_user_datas[user["email"]] = user
                            new_user_datas[user["email"]].update(
                                {"hashed_id": user["id"]}
                            )

                    for port_user in datas["obj"]:

                        for user in port_user["clientStats"]:

                            if new_user_datas.get(user["email"]):
                                new_user_datas[user["email"]].update(**user)

                self.users_datas = new_user_datas
                print(f"update data, {len(new_user_datas) = }")

                time.sleep(10)

            except:
                time.sleep(10)

    def sizeof_fmt(self, size):
        if type(size) == int:
            for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]:
                if size < 1024.0 or unit == "PiB":
                    break
                size /= 1024.0
            return f"{size:.{2}f} {unit}"
        return size

    def get_by_id(self, hashed_id) -> UserDataType | None:
        for _, user in self.users_datas.items():
            if user["hashed_id"] == hashed_id:
                return user
        return None


user_fetch = UserFetch(
    panel_ip_address=settings.PANEL_ADDRESS,
    panel_username=settings.PANEL_USERNAME,
    panel_password=settings.PANEL_PASSWORD,
)


app = Client(
    "X-ui User Reporter Bot",
    api_id=settings.API_ID,
    api_hash=settings.API_HASH,
    bot_token=settings.BOT_TOKEN,
    app_version="0.0.1",
    device_model="PC",
    system_version="Linux",
)


def extract_vless_hash_id(vless: str) -> str | None:
    data = re.findall(r"vless:\/\/(.*)@", vless)

    hash_id = None
    if len(data) > 0:
        hash_id = data[0]

    return hash_id


def extract_vmess_hash_id(vmess: str) -> str | None:
    try:
        data = vmess[8:]
        data = data.encode(encoding="utf8")
        data = base64.b64decode(data)
        data = json.loads(data)
        hash_id = data.get("id")

    except:
        hash_id = None

    finally:
        return hash_id


@app.on_message(filters.text & filters.private)
async def users(client: Client, message: Message):

    text: str = message.text

    if text == "/start":
        await message.reply("اکانت یا ایدی اکانت خود را بفرستید")
        return

    print(f"input: {text}")

    if "vless" in text:
        hash_id = extract_vless_hash_id(text)

    elif "vmess" in text:
        hash_id = extract_vmess_hash_id(text)

    else:
        hash_id = text

    user = user_fetch.get_by_id(hash_id)

    if user:
        user_total = user.get("down", 0) + user.get("up", 0)

        user_data = f"""
ایمیل: {user['email']}
هش ایدی: {user['hashed_id']}
چند کاربره:   {user['limitIp'] or 'بی نهایت'}
حجم قابل استفاده: {user_fetch.sizeof_fmt(user['totalGB']) if 0 != user.get('totalGB') else "بی نهایت" }
حجم کلی استفاده شده: {user_fetch.sizeof_fmt(user_total) if 0 != user_total else 0 }
مقدار اپلود: {user_fetch.sizeof_fmt(user['up']) if 0 != user.get('up') else 0 }
مقدار دانلود: {user_fetch.sizeof_fmt(user['down']) if 0 != user.get('down') else 0 }
وضعیت: {"فعال" if user['enable'] else user['غیر فعال']}
"""

    else:
        user_data = "پیدا نشد"

    await message.reply(user_data)


if __name__ == "__main__":

    # login to panel
    if not user_fetch.login():
        print("login failed")

    Thread(target=user_fetch.update).start()  # start lop for get update from server

    print("start telegram bot app")

    app.run()
