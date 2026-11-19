import time
import threading
import mysql.connector
from mysql.connector import pooling
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

VK_TOKEN = "vk1.a.Ad6Y0O2e6U13y8bb7As9J_EB5TUf_oHXiY_y_0byLQULQz7VONqmONDeYkm4TgVKowhMP8fIjQabiKoOwLB_KhLXLao6DZibdZFuOBRiO5UsQ1UAAugQWTohKLBDISf7NMnT-SKUcIHJfTVO6JLXpbQ-rbuZbRZ-_Cq5rRBzJ1SGGLa2PtU2hXjawtIj6q-cYo_pLf_eu9kFxtnAqb4AWg"
SERVER_NAME = "TEST SERVER"

DB_CONFIG = {
    "host": "80.242.59.112",
    "user": "gs330867",
    "password": "HeZ5icJZQtXW",
    "database": "gs330867",
    "autocommit": True
}

db_pool = pooling.MySQLConnectionPool(pool_name="samp_pool", pool_size=5, **DB_CONFIG)

vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)

user_states = {}

def get_main_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Привязать аккаунт", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Привязанные аккаунты", color=VkKeyboardColor.PRIMARY)
    return keyboard.get_keyboard()

def send_msg(user_id, text, keyboard=None):
    params = {
        "user_id": user_id,
        "message": text,
        "random_id": vk_api.utils.get_random_id()
    }
    if keyboard is not None:
        params["keyboard"] = keyboard
    vk.messages.send(**params)

def check_expired_codes():
    while True:
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            query = """
                UPDATE `accounts` 
                SET `vk_reg_code` = 0, `vk_get` = 0, `vk_time` = 0 
                WHERE `vk_get` = 1 AND (UNIX_TIMESTAMP() - `vk_time`) >= 60
            """
            cursor.execute(query)
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[Ошибка фоновой проверки]: {e}")
        time.sleep(5)

threading.Thread(target=check_expired_codes, daemon=True).start()

print("ВК Бот успешно запущен...")

for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        user_id = event.user_id
        text = event.text.strip()
        text_lower = text.lower()

        if text_lower in ["начать", "start", "меню"]:
            user_states[user_id] = None
            send_msg(
                user_id,
                "Привет, для начала работы выберите действие в меню:",
                keyboard=get_main_keyboard()
            )

        elif text_lower == "привязать аккаунт":
            user_states[user_id] = "WAITING_CODE"
            send_msg(
                user_id,
                "Введите код привязки, полученный в игре.",
                keyboard=get_main_keyboard()
            )

        elif text_lower == "привязанные аккаунты":
            user_states[user_id] = None
            try:
                conn = db_pool.get_connection()
                cursor = conn.cursor(dictionary=True)

                cursor.execute("SELECT `name` FROM `accounts` WHERE `vk_id` = %s", (user_id,))
                accounts = cursor.fetchall()

                if accounts:
                    lines = ["Привязанные аккаунты:"]
                    for acc in accounts:
                        lines.append(f"Никнейм: {acc['name']} | Сервер: {SERVER_NAME}")
                    send_msg(user_id, "\n".join(lines), keyboard=get_main_keyboard())
                else:
                    send_msg(user_id, "У вас нет привязанных аккаунтов.", keyboard=get_main_keyboard())

                cursor.close()
                conn.close()
            except Exception as e:
                print(f"[Ошибка БД при получении списка]: {e}")
                send_msg(user_id, "Ошибка при получении списка аккаунтов.", keyboard=get_main_keyboard())

        elif text.isdigit() and len(text) == 6:
            code = int(text)
            try:
                conn = db_pool.get_connection()
                cursor = conn.cursor(dictionary=True)

                cursor.execute(
                    "SELECT `name`, `vk_id`, `vk_time` FROM `accounts` WHERE `vk_reg_code` = %s AND `vk_get` = 1 LIMIT 1",
                    (code,)
                )
                account = cursor.fetchone()

                if account:
                    if int(time.time()) - account['vk_time'] >= 60:
                        cursor.execute(
                            "UPDATE `accounts` SET `vk_reg_code` = 0, `vk_get` = 0, `vk_time` = 0 WHERE `name` = %s",
                            (account['name'],)
                        )
                        send_msg(user_id, "Время действия кода истекло (прошла 1 минута). Сгенерируйте новый код в игре.", keyboard=get_main_keyboard())
                    
                    elif account['vk_id'] != 0:
                        send_msg(user_id, "К этому аккаунту уже привязан ВКонтакте.", keyboard=get_main_keyboard())
                    
                    else:
                        nickname = account['name']
                        cursor.execute(
                            "UPDATE `accounts` SET `vk_id` = %s, `vk_reg_code` = 0, `vk_get` = 0, `vk_time` = 0 WHERE `name` = %s LIMIT 1",
                            (user_id, nickname)
                        )
                        user_states[user_id] = None
                        send_msg(
                            user_id,
                            f"Аккаунт успешно привязан!\nНикнейм: {nickname} | Сервер: {SERVER_NAME}",
                            keyboard=get_main_keyboard()
                        )
                else:
                    send_msg(user_id, "Неверный код привязки или его срок действия уже истек.", keyboard=get_main_keyboard())

                cursor.close()
                conn.close()
            except Exception as e:
                print(f"[Ошибка БД при привязке]: {e}")
                send_msg(user_id, "Произошла техническая ошибка. Попробуйте позже.", keyboard=get_main_keyboard())

        else:
            if user_states.get(user_id) == "WAITING_CODE":
                send_msg(user_id, "Код должен состоять из 6 цифр. Введите код привязки, полученный в игре:", keyboard=get_main_keyboard())
            else:
                send_msg(user_id, "Выберите действие в меню:", keyboard=get_main_keyboard())
