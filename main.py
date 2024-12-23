import telebot
import requests
import sqlite3
import uuid
import datetime
import os
import time
import json
from datetime import timedelta
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot 的 Token，请替换为你自己的
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Web 应用 API 的 Host
API_HOST = os.getenv("API_HOST")
# Web 应用 API 的 Token，请替换为你自己的
API_TOKEN = os.getenv("API_TOKEN")
# 数据库文件路径
DATABASE_FILE = "user_data.db"
# 管理员 Telegram ID 列表
ADMIN_IDS = os.getenv("ADMIN_IDS")
ADMIN_IDS = json.loads(ADMIN_IDS)

bot = telebot.TeleBot(BOT_TOKEN)

# 邀请码状态
INVITE_CODE_STATUS_UNUSED = "unused"
INVITE_CODE_STATUS_USED = "used"
INVITE_CODE_STATUS_EXPIRED = "expired"
INVITE_CODE_STATUS_DELETED = "deleted"

# 系统开关状态
SYSTEM_STATUS_ON = "on"
SYSTEM_STATUS_OFF = "off"

# 初始系统状态
SYSTEM_STATUS = SYSTEM_STATUS_ON

# 日志文件配置
#LOG_FILE = "bot.log"
LOG_FILE_SIZE = 10 * 1024 * 1024  # 10MB
LOG_FILE_RETENTION = 10
LOG_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> - <level>{level}</level> - <level>{message}</level>"

# 配置 loguru 日志
#logger.add(format=LOG_FORMAT, rotation=LOG_FILE_SIZE, retention=LOG_FILE_RETENTION, encoding="utf-8")
logger.add(lambda msg: print(msg, end=""), format=LOG_FORMAT, level="DEBUG")


# 创建数据库连接和游标
def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# 创建邀请码表
def create_invite_code_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invite_codes (
            code TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            create_time INTEGER NOT NULL,
            expire_time INTEGER NOT NULL,
            creator INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    logger.info("邀请码表创建成功")

create_invite_code_table()

# 创建用户表
def create_user_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            telegram_id INTEGER NOT NULL UNIQUE,
            invite_code TEXT
        )
    """)
    conn.commit()
    conn.close()
    logger.info("用户表创建成功")
create_user_table()

# 向 Web 应用注册用户
def register_user_to_web(username, email, password):
    url = f"{API_HOST}/api/user"
    headers = {
        "x-nd-authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "isAdmin": False,
        "userName": username,
        "name": username,
        "email": email,
        "password": password
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status() # 如果状态码不是 2xx，抛出异常
        logger.debug(f"向 Web 应用注册用户成功，返回信息：{response.json()}")
        return response.json().get("id")
    except requests.exceptions.RequestException as e:
        logger.error(f"向 Web 应用注册用户失败：{str(e)}")
        return response.json()

# 从 Web 应用删除用户
def delete_user_from_web(user_id):
     url = f"{API_HOST}/api/user/{user_id}"
     headers = {"x-nd-authorization": f"Bearer {API_TOKEN}"}
     try:
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        logger.debug(f"向 Web 应用删除用户成功，返回信息：{response.json()}")
        return True
     except requests.exceptions.RequestException as e:
         logger.error(f"向 Web 应用删除用户失败：{str(e)}")
         return None


# 生成邀请码
def generate_invite_code():
    return str(uuid.uuid4())

# 获取邀请码信息
def get_invite_code_info(code):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invite_codes WHERE code = ?", (code,))
    invite_code = cursor.fetchone()
    conn.close()
    return invite_code

# 更新邀请码状态
def update_invite_code_status(code, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE invite_codes SET status = ? WHERE code = ?", (status, code))
    conn.commit()
    conn.close()
    logger.debug(f"邀请码 {code} 状态更新为 {status}")

# 添加邀请码
def add_invite_code(code, creator):
    conn = get_db_connection()
    cursor = conn.cursor()
    create_time = int(time.time())
    expire_time = int((datetime.datetime.now() + timedelta(days=7)).timestamp())
    cursor.execute("INSERT INTO invite_codes (code, status, create_time, expire_time, creator) VALUES (?, ?, ?, ?, ?)",
                   (code, INVITE_CODE_STATUS_UNUSED, create_time, expire_time, creator))
    conn.commit()
    conn.close()
    logger.info(f"邀请码 {code} 创建成功")

# 删除邀请码
def delete_invite_code(code):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE invite_codes SET status = ? WHERE code = ?", (INVITE_CODE_STATUS_DELETED, code))
    conn.commit()
    conn.close()
    logger.info(f"邀请码 {code} 删除成功")


# 获取所有邀请码
def get_all_invite_codes():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invite_codes")
    invite_codes = cursor.fetchall()
    conn.close()
    return invite_codes

# 获取用户
def get_user(telegram_id):
     conn = get_db_connection()
     cursor = conn.cursor()
     cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
     user = cursor.fetchone()
     conn.close()
     return user

# 检查是否是管理员
def is_admin(user_id):
    return user_id in ADMIN_IDS

# 切换系统状态
def switch_system_status():
    global SYSTEM_STATUS
    if SYSTEM_STATUS == SYSTEM_STATUS_ON:
        SYSTEM_STATUS = SYSTEM_STATUS_OFF
    else:
        SYSTEM_STATUS = SYSTEM_STATUS_ON
    logger.info(f"系统状态切换为：{SYSTEM_STATUS}")
    return SYSTEM_STATUS

# 处理 /start 命令
@bot.message_handler(commands=["start"])
def start_command(message):
    if SYSTEM_STATUS == SYSTEM_STATUS_ON:
        bot.send_message(message.chat.id, "欢迎使用注册系统。\n"
                         "请使用邀请码进行注册。")
    else:
        bot.send_message(message.chat.id, "欢迎使用注册系统。\n"
                         "请使用用户名和密码进行注册。")
    logger.info(f"用户 {message.from_user.id} 执行 /start 命令")

# 处理 /newinvite 命令
@bot.message_handler(commands=["newinvite"])
def new_invite_code_command(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "您不是管理员，无权执行此操作。")
        logger.warning(f"用户 {message.from_user.id} 尝试执行 /newinvite 命令，但不是管理员")
        return
    if SYSTEM_STATUS == SYSTEM_STATUS_OFF:
        bot.send_message(message.chat.id, "系统已关闭，请先开启系统。")
        logger.warning(f"用户 {message.from_user.id} 尝试在系统关闭时执行 /newinvite 命令")
        return
    
    invite_code = generate_invite_code()
    add_invite_code(invite_code, message.from_user.id)
    bot.send_message(message.chat.id, f"新的邀请码已生成：{invite_code}")
    logger.info(f"管理员 {message.from_user.id} 生成邀请码 {invite_code}")

# 处理 /listinvite 命令
@bot.message_handler(commands=["listinvite"])
def list_invite_code_command(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "您不是管理员，无权执行此操作。")
        logger.warning(f"用户 {message.from_user.id} 尝试执行 /listinvite 命令，但不是管理员")
        return
    if SYSTEM_STATUS == SYSTEM_STATUS_OFF:
          bot.send_message(message.chat.id, "系统已关闭，请先开启系统。")
          logger.warning(f"用户 {message.from_user.id} 尝试在系统关闭时执行 /listinvite 命令")
          return
    invite_codes = get_all_invite_codes()
    if not invite_codes:
        bot.send_message(message.chat.id, "暂无邀请码。")
        logger.info(f"管理员 {message.from_user.id} 查询邀请码列表，结果为空")
        return
    
    response = "邀请码列表:\n"
    for code in invite_codes:
        create_time = datetime.datetime.fromtimestamp(code["create_time"]).strftime("%Y-%m-%d %H:%M:%S")
        expire_time = datetime.datetime.fromtimestamp(code["expire_time"]).strftime("%Y-%m-%d %H:%M:%S")
        response += (
            f"邀请码: {code['code']}\n"
            f"状态: {code['status']}\n"
            f"创建时间: {create_time}\n"
            f"过期时间: {expire_time}\n"
            f"创建人ID: {code['creator']}\n"
            f"---\n"
            )
    bot.send_message(message.chat.id, response)
    logger.info(f"管理员 {message.from_user.id} 查询邀请码列表")

# 处理 /deleteinvite 命令
@bot.message_handler(commands=["deleteinvite"])
def delete_invite_code_command(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "您不是管理员，无权执行此操作。")
        logger.warning(f"用户 {message.from_user.id} 尝试执行 /deleteinvite 命令，但不是管理员")
        return
    if SYSTEM_STATUS == SYSTEM_STATUS_OFF:
          bot.send_message(message.chat.id, "系统已关闭，请先开启系统。")
          logger.warning(f"用户 {message.from_user.id} 尝试在系统关闭时执行 /deleteinvite 命令")
          return
    try:
        code = message.text.split(" ")[1]
        invite_code = get_invite_code_info(code)
        if not invite_code:
            bot.send_message(message.chat.id, "邀请码不存在")
            logger.warning(f"管理员 {message.from_user.id} 尝试删除不存在的邀请码 {code}")
            return
        
        if invite_code["creator"] != message.from_user.id:
            bot.send_message(message.chat.id, "您不是此邀请码的创建人，无法删除。")
            logger.warning(f"管理员 {message.from_user.id} 尝试删除非自己创建的邀请码 {code}")
            return
        
        if invite_code["status"] == INVITE_CODE_STATUS_DELETED:
             bot.send_message(message.chat.id, "邀请码已删除，请勿重复操作。")
             logger.warning(f"管理员 {message.from_user.id} 尝试删除已删除的邀请码 {code}")
             return
    
        delete_invite_code(code)
        bot.send_message(message.chat.id, f"邀请码 {code} 已删除。")
        logger.info(f"管理员 {message.from_user.id} 删除邀请码 {code}")
    except IndexError:
         bot.send_message(message.chat.id, "请指定需要删除的邀请码，如：/deleteinvite 邀请码")
         logger.warning(f"管理员 {message.from_user.id} 执行 /deleteinvite 命令，但没有指定邀请码")
    except Exception as e:
          bot.send_message(message.chat.id, f"删除邀请码过程中发生错误：{str(e)}")
          logger.error(f"删除邀请码过程中发生错误：{str(e)}")

# 处理 /deleteuser 命令
@bot.message_handler(commands=["deleteuser"])
def delete_user_command(message):
    try:
        if not is_admin(message.from_user.id):
            user = get_user(message.from_user.id)
            if user:
                user_id = user["id"]
                if delete_user_from_web(user_id):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM users WHERE telegram_id = ?", (message.from_user.id,))
                    conn.commit()
                    conn.close()
                    bot.send_message(message.chat.id, f"用户 {message.chat.id} 已成功删除！")
                    logger.info(f"用户 {message.from_user.id} 删除用户成功")
                else:
                    bot.send_message(message.chat.id, "删除用户失败")
                    logger.error(f"用户 {message.from_user.id} 删除用户失败")
            else:
                bot.send_message(message.chat.id, "你尚未注册")
                logger.warning(f"用户 {message.from_user.id} 尝试删除用户，但尚未注册")
            return

        target = message.text[len("/deleteuser"):].strip()
        if not target:
            bot.send_message(message.chat.id, "请指定需要删除的用户的 Telegram ID 或用户名，如：/deleteuser TelegramID 或 /deleteuser 用户名")
            logger.warning(f"管理员 {message.from_user.id} 尝试删除用户，但未指定用户 Telegram ID 或用户名")
            return

        try:
            # 尝试将目标解析为 Telegram ID
            telegram_id = int(target)
            user = get_user(telegram_id)
            if not user:
                bot.send_message(message.chat.id, "该 Telegram ID 的用户不存在")
                logger.warning(f"管理员 {message.from_user.id} 尝试删除不存在的用户 {telegram_id} (Telegram ID)")
                return
            user_id = user["id"]
            if delete_user_from_web(user_id):
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
                conn.commit()
                conn.close()
                bot.send_message(message.chat.id, f"用户 {user_id} (Telegram ID: {telegram_id}) 已成功删除！")
                logger.info(f"管理员 {message.from_user.id} 删除用户 {telegram_id} (Telegram ID) 成功")
            else:
                bot.send_message(message.chat.id, "删除用户失败")
                logger.error(f"管理员 {message.from_user.id} 删除用户 {telegram_id} (Telegram ID) 失败")

        except ValueError:
            # 如果解析为 Telegram ID 失败，则尝试解析为用户名
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (target,))
            user = cursor.fetchone()
            conn.close()
            if not user:
                bot.send_message(message.chat.id, "该用户不存在")
                logger.warning(f"管理员 {message.from_user.id} 尝试删除不存在的用户 {target} (用户名)")
                return
            user_id = user["id"]
            telegram_id = user["telegram_id"]
            if delete_user_from_web(user_id):
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
                conn.commit()
                conn.close()
                bot.send_message(message.chat.id, f"用户 {user_id} (用户名: {target}) 已成功删除！")
                logger.info(f"管理员 {message.from_user.id} 删除用户 {target} (用户名) 成功")
            else:
                bot.send_message(message.chat.id, "删除用户失败")
                logger.error(f"管理员 {message.from_user.id} 删除用户 {target} (用户名) 失败")

    except Exception as e:
        bot.send_message(message.chat.id, f"删除用户过程中发生错误：{str(e)}")
        logger.error(f"删除用户过程中发生错误：{str(e)}")


# 处理 /switch 命令
@bot.message_handler(commands=["switch"])
def switch_system_command(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "您不是管理员，无权执行此操作。")
        logger.warning(f"用户 {message.from_user.id} 尝试执行 /switch 命令，但不是管理员")
        return
    
    new_status = switch_system_status()
    bot.send_message(message.chat.id, f"系统已切换为：{new_status}")
    logger.info(f"管理员 {message.from_user.id} 切换系统状态为 {new_status}")

# 处理 /adminregister 命令
@bot.message_handler(commands=["adminreg"])
def admin_register_command(message):
    if not is_admin(message.from_user.id):
       bot.send_message(message.chat.id, "您不是管理员，无权执行此操作。")
       logger.warning(f"用户 {message.from_user.id} 尝试执行 /adminreg 命令，但不是管理员")
       return
    try:
        parts = message.text.lstrip("/adminreg ").split(",")
        if len(parts) < 2:
            bot.send_message(message.chat.id, "请按格式输入/adminreg 用户名,密码")
            logger.warning(f"管理员 {message.from_user.id} 尝试执行 /adminreg 命令，但缺少参数")
            return
        username = parts[0].strip()
        password = parts[1].strip()
        
        web_user_id = register_user_to_web(username, None, password)
        if "errors" in web_user_id:
            bot.send_message(message.chat.id, "该用户名已被使用，请选择其他用户名。")
            logger.warning(f"用户 {message.from_user.id} 尝试注册，但用户名 {username} 已存在")
            return
        
        bot.send_message(message.chat.id, f"管理员注册用户成功！用户名为：{username}。")
        logger.info(f"管理员 {message.from_user.id} 通过 /adminreg 命令注册用户 {username} 成功")
    except Exception as e:
        bot.send_message(message.chat.id, f"管理员注册过程中发生错误：{str(e)}")
        logger.error(f"管理员 {message.from_user.id} 通过 /adminreg 命令注册用户发生错误：{str(e)}")

# 处理注册信息
# @bot.message_handler(func=lambda message: True)
@bot.message_handler(commands=["reg"])
def register_handler(message):
    # if message.text.startswith("/"):
    #     return
    try:
        # 检查用户是否已注册
        user = get_user(message.from_user.id)
        if user:
            bot.send_message(message.chat.id, "您已注册，请勿重复注册。")
            logger.warning(f"用户 {message.from_user.id} 尝试重复注册")
            return

        if SYSTEM_STATUS == SYSTEM_STATUS_ON:
            if "," not in message.text:
                bot.send_message(message.chat.id, "请按格式输入/reg 邀请码,用户名,邮箱(可选),密码")
                logger.warning(f"用户 {message.from_user.id} 尝试注册，但输入格式错误（邀请码模式）")
                return
            parts = message.text.lstrip("/reg ").split(",")
            invite_code = parts[0].strip()
            username = parts[1].strip()
            email = parts[2].strip() if len(parts) > 3 else None
            password = parts[-1].strip()
            if not (invite_code and username and password):
                bot.send_message(message.chat.id, "邀请码、用户名和密码不能为空")
                logger.warning(f"用户 {message.from_user.id} 尝试注册，但缺少必要的信息（邀请码模式）")
                return
            
            invite_code_info = get_invite_code_info(invite_code)
            if not invite_code_info:
                bot.send_message(message.chat.id, "无效的邀请码")
                logger.warning(f"用户 {message.from_user.id} 尝试注册，但邀请码无效（邀请码模式）")
                return

            if invite_code_info["status"] != INVITE_CODE_STATUS_UNUSED:
                bot.send_message(message.chat.id, "邀请码已被使用或已过期")
                logger.warning(f"用户 {message.from_user.id} 尝试注册，但邀请码已使用或过期（邀请码模式）")
                return
            
            if invite_code_info["expire_time"] <= int(time.time()):
                update_invite_code_status(invite_code, INVITE_CODE_STATUS_EXPIRED)
                bot.send_message(message.chat.id, "邀请码已过期")
                logger.warning(f"用户 {message.from_user.id} 尝试注册，但邀请码已过期（邀请码模式）")
                return
            
            web_user_id = register_user_to_web(username, email, password)
            if "errors" in web_user_id:
                bot.send_message(message.chat.id, "该用户名已被使用，请选择其他用户名。")
                logger.warning(f"用户 {message.from_user.id} 尝试注册，但用户名 {username} 已存在（邀请码模式）")
                return
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (id, telegram_id, invite_code) VALUES (?, ?, ?)",(web_user_id, message.from_user.id, invite_code))
            conn.commit()
            conn.close()
            update_invite_code_status(invite_code, INVITE_CODE_STATUS_USED)
            bot.send_message(message.chat.id, f"注册成功！你的用户名为：{username}。")
            logger.info(f"用户 {message.from_user.id} 使用邀请码 {invite_code} 注册成功")
        else:
            if "," not in message.text:
                bot.send_message(message.chat.id, "请按格式输入/reg 用户名,邮箱(可选),密码")
                logger.warning(f"用户 {message.from_user.id} 尝试注册，但输入格式错误（无邀请码模式）")
                return
            parts = message.text.lstrip("/reg ").split(",")
            username = parts[0].strip()
            email = parts[1].strip() if len(parts) > 2 else None
            password = parts[-1].strip()

            if not (username and password):
                bot.send_message(message.chat.id, "用户名和密码不能为空")
                logger.warning(f"用户 {message.from_user.id} 尝试注册，但缺少必要的信息（无邀请码模式）")
                return
            
            web_user_id = register_user_to_web(username, email, password)
            if "errors" in web_user_id:
                bot.send_message(message.chat.id, "该用户名已被使用，请选择其他用户名。")
                logger.warning(f"用户 {message.from_user.id} 尝试注册，但用户名 {username} 已存在（无邀请码模式）")
                return
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (id, telegram_id, invite_code) VALUES (?, ?, ?)",(web_user_id, message.from_user.id, None))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, f"注册成功！你的用户ID为：{username}。")
            logger.info(f"用户 {message.from_user.id} 无邀请码注册成功")
    except ValueError:
        bot.send_message(message.chat.id, "输入格式错误，请使用正确的格式：/reg 邀请码,用户名,邮箱(可选),密码 或 用户名,邮箱(可选),密码")
        logger.warning(f"用户 {message.from_user.id} 尝试注册，但输入格式错误")
    except Exception as e:
        bot.send_message(message.chat.id, f"注册过程中发生错误：{str(e)}")
        logger.error(f"注册过程中发生错误：{str(e)}")


# 启动 bot
if __name__ == "__main__":
    bot.polling(none_stop=True)