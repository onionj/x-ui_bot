import datetime
import base64
import json
import time
import re

from pprint import pprint
from typing import TypedDict, Optional
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
    uid: str
    inboundId: int
    enable: bool
    up: int
    down: int
    total: int
    port: int


class UserFetch:
    def __init__(self, panel_ip_address: str, panel_username: str, panel_password: str) -> None:
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

    def report_all(self):
        report_datas = {}

        for _, user in self.users_datas.items():
            if report_datas.get(user["port"]):
                if user["enable"]:
                    report_datas[user["port"]]["active_users_count"] += 1
                    report_datas[user["port"]]["active_unlimited_users"] += (
                        1 if user["totalGB"] == 0 else 0
                    )
                    report_datas[user["port"]]["active_users_totalGB"] += user["totalGB"]
                    report_datas[user["port"]]["active_users_totalUsed"] += user["down"] + user["up"]
                else:
                    report_datas[user["port"]]["inactive_users_count"] += 1
                    report_datas[user["port"]]["inactive_unlimited_users"] += (
                        1 if user["totalGB"] == 0 else 0
                    )
                    report_datas[user["port"]]["inactive_users_totalGB"] += user["totalGB"]
                    report_datas[user["port"]]["inactive_users_totalUsed"] += user["down"] + user["up"]

            else:
                report_data = {
                    "active_users_count": 0,
                    "active_unlimited_users": 0,
                    "active_users_totalGB": 0,
                    "active_users_totalUsed": 0,
                    "inactive_users_count": 0,
                    "inactive_unlimited_users": 0,
                    "inactive_users_totalGB": 0,
                    "inactive_users_totalUsed": 0,
                }

                if user["enable"]:
                    report_data.update(
                        {
                            "active_users_count": 1,
                            "active_unlimited_users": 1 if user["totalGB"] == 0 else 0,
                            "active_users_totalGB": user["totalGB"],
                            "active_users_totalUsed": user["down"] + user["up"],
                        }
                    )
                else:
                    report_data.update(
                        {
                            "inactive_users_count": 1,
                            "inactive_unlimited_users": 1 if user["totalGB"] == 0 else 0,
                            "inactive_users_totalGB": user["totalGB"],
                            "inactive_users_totalUsed": user["down"] + user["up"],
                        }
                    )

                report_datas[user["port"]] = report_data

        for key in report_datas.keys():
            report_datas[key]["active_users_totalGB"] = self.sizeof_fmt(report_datas[key]["active_users_totalGB"])
            report_datas[key]["active_users_totalUsed"] = self.sizeof_fmt(report_datas[key]["active_users_totalUsed"])
            report_datas[key]["inactive_users_totalGB"] = self.sizeof_fmt(report_datas[key]["inactive_users_totalGB"])
            report_datas[key]["inactive_users_totalUsed"] = self.sizeof_fmt(
                report_datas[key]["inactive_users_totalUsed"]
            )

        return report_datas

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
                        port = port_user["port"]
                        users = json.loads(port_user["settings"])["clients"]

                        for user in users:
                            new_user_datas[user["email"]] = user
                            new_user_datas[user["email"]].update({"uid": user["id"], "port": port})

                    for port_user in datas["obj"]:
                        for user in port_user["clientStats"]:
                            if new_user_datas.get(user["email"]):
                                new_user_datas[user["email"]].update(**user)

                self.users_datas = new_user_datas
                print("---------------------update data:")
                pprint(self.report_all())
                print("\n")

                time.sleep(20)

            except KeyboardInterrupt:
                return
            except:
                time.sleep(20)

    def sizeof_fmt(self, size):
        if type(size) == int:
            for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]:
                if size < 1024.0 or unit == "PiB":
                    break
                size /= 1024.0
            return f"{size:.{2}f} {unit}"
        return size

    def get_by_id(self, uid) -> Optional[UserDataType]:
        for _, user in self.users_datas.items():
            if user["uid"] == uid:
                return user
        return None

    def get_by_email(self, email) -> Optional[UserDataType]:
        for _, user in self.users_datas.items():
            if user["email"] == email:
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


def extract_vless_hash_id(vless: str) -> Optional[str]:
    data = re.findall(r"vless:\/\/(.*)@", vless)

    hash_id = None
    if len(data) > 0:
        hash_id = data[0]

    return hash_id


def extract_vmess_hash_id(vmess: str) -> Optional[str]:
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

    if not user:
        user = user_fetch.get_by_email(text)

    if user:
        user_total = user.get("down", 0) + user.get("up", 0)

        if user["expiryTime"] == 0:
            expiryTime = "(بدون محدودیت)"
        else:
            seconds = int(str(user["expiryTime"])[:10]) - int(time.time())

            if seconds < 0:
                seconds = 0

            expiryTime = datetime.timedelta(seconds=seconds)

        user_data = f"""
ایمیل: {user['email']}
یونیک ایدی: {user['uid'][:10]}...
چند کاربره:   {user['limitIp'] or '(بدون محدودیت)'}
حجم قابل استفاده: {user_fetch.sizeof_fmt(user['totalGB']) if 0 != user.get('totalGB') else "(بدون محدودیت)" }
حجم کلی استفاده شده: {user_fetch.sizeof_fmt(user_total) if 0 != user_total else 0 }
مقدار اپلود: {user_fetch.sizeof_fmt(user['up']) if 0 != user.get('up') else 0 }
مقدار دانلود: {user_fetch.sizeof_fmt(user['down']) if 0 != user.get('down') else 0 }
وضعیت: {"فعال" if user['enable'] else "غیر فعال"}
زمان باقی مانده:
{expiryTime}
"""

    else:
        user_data = "پیدا نشد"

    await message.reply(user_data)


if __name__ == "__main__":
    # login to panel
    if not user_fetch.login():
        print("login failed")
        exit(2)

    Thread(target=user_fetch.update).start()  # start lop for get update from server

    # print("start telegram bot app")

    # app.run()
    time.sleep(100)
