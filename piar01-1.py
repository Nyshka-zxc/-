import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import random
import time
import threading
import os
import json
import sys
from datetime import datetime
from collections import defaultdict

TOKEN = 'тут токен' #тут токен от группы вставь его в кавычках
GROUP_ID = 0000000000 #тут айди группы, просто замени
OWNER_IDS = [ ] #тут вставь свой айди от вк цифрами, это типо как создатель, котррому доступны все функции

#далее снизу ниче не трогай, это на хосте или сервере создаются файлы с базой данных
CHATS_FILE = "chats.txt"
STATS_FILE = "stats.json"
LOG_FILE = "bot_log.txt"
ACCESS_FILE = "access_users.json"
BACKUP_FILE = "backup_data.json"

spam_attachment = ""
spam_text = ""
spam_keyboard = None
spam_button_link = ""
spam_button_text = ""
is_spamming = False
spam_interval = 300
messages_sent = 0
failed_messages = 0
start_time = time.time()
last_run_time = 0
current_progress = {"current": 0, "total": 0}
chat_stats = defaultdict(lambda: {"sent": 0, "failed": 0, "last_time": None, "name": ""})
current_campaign_stats = defaultdict(lambda: {"sent": 0, "failed": 0})

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

def create_keyboard(link, button_text="Перейти"):
    if not link.startswith("http"):
        link = "https://" + link
    
    keyboard = {
        "inline": True,
        "buttons": [
            [
                {
                    "action": {
                        "type": "open_link",
                        "link": link,
                        "label": button_text[:40]
                    }
                }
            ]
        ]
    }
    return json.dumps(keyboard, ensure_ascii=False)

def save_backup():
    backup = {
        "spam_text": spam_text,
        "spam_attachment": spam_attachment,
        "spam_button_link": spam_button_link,
        "spam_button_text": spam_button_text,
        "is_spamming": is_spamming,
        "spam_interval": spam_interval,
        "messages_sent": messages_sent,
        "failed_messages": failed_messages,
        "last_run_time": last_run_time,
        "current_progress": current_progress,
        "chat_stats": dict(chat_stats),
        "timestamp": datetime.now().isoformat()
    }
    with open(BACKUP_FILE, "w") as f:
        json.dump(backup, f, indent=2)
    print("💾 Данные сохранены")

def load_backup():
    global spam_text, spam_attachment, spam_keyboard, spam_button_link, spam_button_text
    global is_spamming, spam_interval, messages_sent, failed_messages
    global last_run_time, current_progress
    
    if os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, "r") as f:
            backup = json.load(f)
        
        spam_text = backup.get("spam_text", "")
        spam_attachment = backup.get("spam_attachment", "")
        spam_button_link = backup.get("spam_button_link", "")
        spam_button_text = backup.get("spam_button_text", "")
        spam_interval = backup.get("spam_interval", 300)
        messages_sent = backup.get("messages_sent", 0)
        failed_messages = backup.get("failed_messages", 0)
        last_run_time = backup.get("last_run_time", 0)
        current_progress = backup.get("current_progress", {"current": 0, "total": 0})
        
        if spam_button_link:
            spam_keyboard = create_keyboard(spam_button_link, spam_button_text)
        
        saved_stats = backup.get("chat_stats", {})
        for chat_id, data in saved_stats.items():
            chat_stats[int(chat_id)] = data
        
        is_spamming = False
        print("📥 Данные восстановлены из бекапа")
        return True
    return False

def load_access_users():
    if not os.path.exists(ACCESS_FILE):
        default_users = {"allowed_users": [], "blacklist": []}
        save_access_users(default_users)
        return default_users
    with open(ACCESS_FILE, "r") as f:
        return json.load(f)

def save_access_users(data):
    with open(ACCESS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def has_access(user_id):
    access_data = load_access_users()
    if user_id in access_data.get("blacklist", []):
        return False
    if user_id in OWNER_IDS or user_id in access_data.get("allowed_users", []):
        return True
    return False

def grant_access(user_id):
    access_data = load_access_users()
    if user_id in access_data.get("blacklist", []):
        access_data["blacklist"].remove(user_id)
    if user_id not in access_data["allowed_users"] and user_id not in OWNER_IDS:
        access_data["allowed_users"].append(user_id)
        save_access_users(access_data)
        return True
    return False

def revoke_access(user_id):
    access_data = load_access_users()
    if user_id in access_data["allowed_users"] and user_id not in OWNER_IDS:
        access_data["allowed_users"].remove(user_id)
        if user_id not in access_data["blacklist"]:
            access_data["blacklist"].append(user_id)
        save_access_users(access_data)
        return True
    return False

def extract_user_id(text):
    if "vk.com/" in text:
        parts = text.split("vk.com/")
        if len(parts) > 1:
            user_part = parts[1].split()[0].strip("/")
            if user_part.startswith("id"):
                try:
                    return int(user_part[2:])
                except:
                    pass
            else:
                try:
                    response = vk.users.get(user_ids=user_part, v='5.131')
                    if response:
                        return response[0]['id']
                except:
                    pass
    else:
        for word in text.split():
            if word.isdigit():
                user_id = int(word)
                if user_id > 0:
                    return user_id
    return None

def get_user_name(user_id):
    try:
        response = vk.users.get(user_ids=user_id, v='5.131')
        if response:
            user = response[0]
            return f"{user['first_name']} {user['last_name']}"
    except:
        pass
    return f"ID:{user_id}"

def get_chat_name(peer_id):
    try:
        chat_id = peer_id - 2000000000
        if chat_id > 0:
            chat = vk.messages.getChat(chat_id=chat_id, v='5.131')
            if chat and 'title' in chat:
                return chat['title']
        return f"Чат {peer_id}"
    except:
        return f"Чат {peer_id}"

def get_saved_chats():
    if not os.path.exists(CHATS_FILE):
        return set()
    with open(CHATS_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def save_chat(peer_id):
    chats = get_saved_chats()
    if str(peer_id) not in chats:
        with open(CHATS_FILE, "a") as f:
            f.write(f"{peer_id}\n")
        print(f"💾 Чат {peer_id} добавлен")
        return True
    return False

def remove_chat(peer_id):
    chats = get_saved_chats()
    if str(peer_id) in chats:
        chats.remove(str(peer_id))
        with open(CHATS_FILE, "w") as f:
            for chat in sorted(chats, key=lambda x: int(x)):
                f.write(f"{chat}\n")
        print(f"🗑 Чат {peer_id} удален")
        return True
    return False

def test_chat_access(peer_id):
    try:
        vk.messages.getConversationsById(peer_ids=peer_id, v='5.131')
        return True
    except:
        return False

def clean_inactive_chats():
    chats = get_saved_chats()
    removed = 0
    for chat_id in list(chats):
        if not test_chat_access(int(chat_id)):
            remove_chat(int(chat_id))
            removed += 1
            time.sleep(0.3)
    return removed

def load_stats():
    if not os.path.exists(STATS_FILE):
        return {"total_sent": 0, "total_failed": 0, "campaigns": []}
    with open(STATS_FILE, "r") as f:
        return json.load(f)

def save_stats():
    stats = load_stats()
    stats["total_sent"] += messages_sent
    stats["total_failed"] += failed_messages
    if messages_sent > 0:
        stats["campaigns"].append({
            "date": datetime.now().isoformat(),
            "sent": messages_sent,
            "failed": failed_messages,
            "chats_count": len(get_saved_chats())
        })
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)

def send_msg(p_id, text, attachment="", keyboard=None):
    global messages_sent, failed_messages
    
    try:
        params = {
            "peer_id": p_id,
            "message": text,
            "attachment": attachment,
            "random_id": random.randint(1, 2147483647),
            "v": "5.131"
        }
        
        if keyboard:
            params["keyboard"] = keyboard
        
        vk.messages.send(**params)
        messages_sent += 1
        chat_stats[p_id]["sent"] += 1
        chat_stats[p_id]["last_time"] = time.time()
        current_campaign_stats[p_id]["sent"] += 1
        print(f"✅ OK {p_id}")
        return True
    except Exception as e:
        failed_messages += 1
        chat_stats[p_id]["failed"] += 1
        current_campaign_stats[p_id]["failed"] += 1
        error_msg = str(e)
        print(f"❌ ERR {p_id}: {error_msg[:100]}")
        if "902" in error_msg or "917" in error_msg or "901" in error_msg:
            remove_chat(p_id)
        return False

def spam_worker():
    global is_spamming, spam_text, spam_attachment, spam_keyboard, spam_interval, last_run_time
    global current_progress, current_campaign_stats, messages_sent, failed_messages
    
    while True:
        if is_spamming and spam_text:
            chats = list(get_saved_chats())
            if chats:
                current_campaign_stats.clear()
                
                for chat_id in chats:
                    try:
                        if not chat_stats[int(chat_id)]["name"]:
                            chat_stats[int(chat_id)]["name"] = get_chat_name(int(chat_id))
                    except:
                        pass
                
                total = len(chats)
                current_progress = {"current": 0, "total": total}
                print(f"🚀 Рассылка в {total} чатов")
                
                for i, p_id in enumerate(chats, 1):
                    if not is_spamming:
                        print(f"⏹ Остановлено на {i}")
                        break
                    
                    current_progress["current"] = i
                    send_msg(int(p_id), spam_text, attachment=spam_attachment, keyboard=spam_keyboard)
                    
                    if i % 25 == 0:
                        print(f"📊 Прогресс: {i}/{total}")
                        for owner_id in OWNER_IDS:
                            try:
                                vk.messages.send(
                                    peer_id=owner_id,
                                    message=f"📊 Прогресс: {i}/{total} чатов",
                                    random_id=random.randint(1, 2147483647),
                                    v='5.131'
                                )
                            except:
                                pass
                    
                    if i % 20 == 0:
                        time.sleep(random.randint(10, 20))
                    else:
                        time.sleep(random.uniform(1.5, 4.0))
                
                print(f"✅ Цикл завершен")
                last_run_time = time.time()
                
                if is_spamming:
                    for owner_id in OWNER_IDS:
                        try:
                            vk.messages.send(
                                peer_id=owner_id,
                                message=f"✅ Цикл завершен!\n📊 Чатов: {total}\n✅ OK: {messages_sent}\n❌ ERR: {failed_messages}\n⏳ Следующий через {spam_interval}с",
                                random_id=random.randint(1, 2147483647),
                                v='5.131'
                            )
                        except:
                            pass
                    
                    time.sleep(spam_interval)
            else:
                is_spamming = False
                for owner_id in OWNER_IDS:
                    try:
                        vk.messages.send(
                            peer_id=owner_id,
                            message="⚠️ Рассылка остановлена: нет чатов в базе",
                            random_id=random.randint(1, 2147483647),
                            v='5.131'
                        )
                    except:
                        pass
        else:
            time.sleep(5)

def log_action(action, status, details=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {status} {action}: {details}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)
    print(log_entry.strip())

def format_number(num):
    if num >= 1000:
        return f"{num:,}".replace(",", " ")
    return str(num)

def get_uptime():
    upt = int(time.time() - start_time)
    h, m, s = upt // 3600, (upt % 3600) // 60, upt % 60
    return f"{h}ч {m}м {s}с"

if load_backup():
    print("📥 Восстановлены предыдущие данные")

threading.Thread(target=spam_worker, daemon=True).start()
print("🚀 Бот запущен! Пиши 'хелп' в ЛС группы")
log_action("bot_start", "✅", "Бот запущен")

try:
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            full_text = event.obj.message['text']
            msg = full_text.lower().strip()
            sender_id = event.obj.message['from_id']
            peer_id = event.obj.message['peer_id']
            
            print(f"📩 Сообщение от {sender_id}: {msg[:50]}")
            
            if peer_id > 2000000000:
                save_chat(peer_id)
            
            if has_access(sender_id):
                
                if msg == "хелп":
                    help_text = (
                        f"📚 КОМАНДЫ БОТА\n"
                        f"══════════════\n\n"
                        f"📢 РАССЫЛКА:\n"
                        f"• рассылка [текст] — запустить\n"
                        f"• рестарт — перезапуск с тем же текстом\n"
                        f"• стоп — остановить\n"
                        f"• интервал [сек] — пауза между циклами\n"
                        f"• вложение [ссылка] — добавить медиа\n"
                        f"• убрать вложение — удалить медиа\n"
                        f"• кнопка [ссылка|текст] — добавить кнопку\n"
                        f"• убрать кнопку — удалить кнопку\n\n"
                        f"💾 ЧАТЫ:\n"
                        f"• адд — добавить чат в БД\n"
                        f"• дел — удалить чат из БД\n"
                        f"• очистка — удалить неактивные\n"
                        f"• список — показать чаты\n"
                        f"• импорт — импорт из пересланного\n\n"
                        f"📊 СТАТИСТИКА:\n"
                        f"• стат — статистика сессии\n"
                        f"• стат чаты — статистика по чатам\n"
                        f"• ошибки — топ чатов с ошибками\n"
                        f"• полный стат — общая статистика\n"
                        f"• сброс — сбросить счетчики\n"
                        f"• лог — последние 20 записей\n\n"
                        f"👥 ДОСТУП (только владельцы):\n"
                        f"• доступ [ссылка] — выдать доступ\n"
                        f"• -доступ [ссылка] — забрать доступ\n"
                        f"• пользователи — список с доступом\n\n"
                        f"🛠 ДРУГОЕ:\n"
                        f"• тест [id] — проверить чат\n"
                        f"• проверка [id] — доступность чата\n"
                        f"• пинг — проверить бота\n"
                        f"• инфо — информация о чате\n"
                        f"• спам-лист — очередь рассылки\n"
                        f"• рестарт бота — полный перезапуск\n\n"
                        f"ℹ️ ОБЩЕЕ:\n"
                        f"• Чатов в базе: {format_number(len(get_saved_chats()))}\n"
                        f"• Интервал: {spam_interval}с\n"
                        f"• Отправлено: {format_number(messages_sent)}\n"
                        f"• Кнопка: {'🔘 есть' if spam_keyboard else '❌ нет'}\n"
                        f"════════════════════════"
                    )
                    send_msg(peer_id, help_text)
                
                elif msg == "пинг":
                    send_msg(peer_id, "🏓 Понг! Бот работает!")
                
                elif msg == "стат":
                    upt = int(time.time() - start_time)
                    h, m = upt // 3600, (upt % 3600) // 60
                    
                    progress_text = ""
                    if current_progress["total"] > 0:
                        percent = (current_progress["current"] / current_progress["total"]) * 100
                        progress_text = f"📈 Прогресс: {current_progress['current']}/{current_progress['total']} ({percent:.1f}%)\n"
                    
                    success_rate = 0
                    if (messages_sent + failed_messages) > 0:
                        success_rate = (messages_sent / (messages_sent + failed_messages)) * 100
                    
                    if is_spamming:
                        next_run = last_run_time + spam_interval
                        diff = int(next_run - time.time())
                        if diff <= 0:
                            timer_str = "🔄 Выполняется..."
                        else:
                            timer_str = f"⏳ Через {diff // 60}м {diff % 60}с"
                    else:
                        timer_str = "💤 Не активна"
                    
                    stat_msg = (
                        f"📊 СТАТИСТИКА\n"
                        f"══════════════\n"
                        f"• Статус: {'✅ АКТИВНА' if is_spamming else '💤 ПАУЗА'}\n"
                        f"{progress_text}"
                        f"• Чатов в базе: {format_number(len(get_saved_chats()))}\n"
                        f"• Отправлено: {format_number(messages_sent)}\n"
                        f"• Ошибок: {format_number(failed_messages)}\n"
                        f"• Успешность: {success_rate:.1f}%\n"
                        f"• Аптайм: {h}ч {m}мин\n"
                        f"• След. цикл: {timer_str}\n"
                        f"• Интервал: {spam_interval}с\n"
                        f"• Вложение: {'📎 есть' if spam_attachment else '❌ нет'}\n"
                        f"• Кнопка: {'🔘 есть' if spam_keyboard else '❌ нет'}"
                    )
                    
                    if current_campaign_stats:
                        stat_msg += "\n\n📈 ТОП-5 ЧАТОВ:\n"
                        sorted_chats = sorted(current_campaign_stats.items(), key=lambda x: x[1]["sent"], reverse=True)[:5]
                        for i, (chat_id, data) in enumerate(sorted_chats, 1):
                            name = chat_stats[chat_id]["name"] or get_chat_name(chat_id)
                            stat_msg += f"{i}. {name}: ✅{data['sent']}\n"
                    
                    send_msg(peer_id, stat_msg)
                
                elif msg == "стат чаты":
                    if chat_stats:
                        sorted_chats = sorted(chat_stats.items(), key=lambda x: x[1]["sent"], reverse=True)
                        stats_text = "📊 СТАТИСТИКА ПО ЧАТАМ\n══════════════\n"
                        
                        for i, (chat_id, data) in enumerate(sorted_chats[:30], 1):
                            name = get_chat_name(int(chat_id))
                            if len(name) > 35:
                                name = name[:32] + "..."
                            
                            last_time = ""
                            if data["last_time"]:
                                last_time = datetime.fromtimestamp(data["last_time"]).strftime("%d.%m %H:%M")
                                last_time = f" | 🕐 {last_time}"
                            
                            stats_text += f"{i}. {name}\n"
                            stats_text += f"   🆔 ID:{chat_id} | ✅{data['sent']} ❌{data['failed']}{last_time}\n"
                        
                        if len(sorted_chats) > 30:
                            stats_text += f"\n... и еще {len(sorted_chats) - 30} чатов"
                        
                        send_msg(peer_id, stats_text)
                    else:
                        send_msg(peer_id, "📭 Нет данных о рассылках")
                
                elif msg == "ошибки":
                    error_types = {}
                    for chat_id, stats in chat_stats.items():
                        if stats["failed"] > 0:
                            name = get_chat_name(int(chat_id))
                            in_base = "✅" if str(chat_id) in get_saved_chats() else "🗑"
                            error_types[f"{name} {in_base}"] = stats["failed"]
                    
                    if error_types:
                        sorted_errors = sorted(error_types.items(), key=lambda x: x[1], reverse=True)
                        error_msg = "❌ ЧАТЫ С ОШИБКАМИ\n══════════════\n"
                        for i, (name, count) in enumerate(sorted_errors[:15], 1):
                            error_msg += f"{i}. {name}: {count} ошибок\n"
                        error_msg += "\n💡 Используй 'очистка'"
                        send_msg(peer_id, error_msg)
                    else:
                        send_msg(peer_id, "✅ Нет чатов с ошибками!")
                
                elif msg == "полный стат":
                    stats = load_stats()
                    campaigns_count = len(stats["campaigns"])
                    
                    full_stat = (
                        f"📈 ПОЛНАЯ СТАТИСТИКА\n"
                        f"══════════════\n"
                        f"• Всего отправлено: {format_number(stats['total_sent'])}\n"
                        f"• Всего ошибок: {format_number(stats['total_failed'])}\n"
                        f"• Всего кампаний: {campaigns_count}\n"
                        f"• За сессию: {format_number(messages_sent)}\n"
                        f"• Аптайм: {get_uptime()}"
                    )
                    
                    if campaigns_count > 0:
                        last_campaign = stats["campaigns"][-1]
                        full_stat += f"\n\nПоследняя кампания:\n• Дата: {last_campaign['date'][:10]}\n• Чатов: {last_campaign['chats_count']}"
                    
                    send_msg(peer_id, full_stat)
                
                elif msg.startswith("рассылка "):
                    txt = full_text[9:].strip()
                    if txt:
                        spam_text = txt
                        is_spamming = True
                        current_campaign_stats.clear()
                        chat_count = len(get_saved_chats())
                        send_msg(peer_id, f"✅ Рассылка запущена!\n📝 Текст: {txt[:100]}{'...' if len(txt) > 100 else ''}\n📊 Чатов: {chat_count}\n🔄 Интервал: {spam_interval}с\n📎 Вложение: {'есть' if spam_attachment else 'нет'}\n🔘 Кнопка: {'есть' if spam_keyboard else 'нет'}\n💡 Работает пока не напишешь 'стоп'")
                    else:
                        send_msg(peer_id, "⚠️ Укажи текст рассылки!")
                
                elif msg == "рестарт":
                    if spam_text:
                        is_spamming = True
                        current_campaign_stats.clear()
                        send_msg(peer_id, f"🔄 Рассылка перезапущена!\n📝 Текст: {spam_text[:100]}\n📎 Вложение: {'есть' if spam_attachment else 'нет'}\n🔘 Кнопка: {'есть' if spam_keyboard else 'нет'}")
                    else:
                        send_msg(peer_id, "⚠️ Нет сохраненного текста! Используй 'рассылка [текст]'")
                
                elif msg == "стоп":
                    if is_spamming:
                        is_spamming = False
                        save_stats()
                        send_msg(peer_id, f"🛑 Рассылка остановлена!\n📊 Отправлено: {format_number(messages_sent)}\n💡 Текст, вложения и кнопка сохранены")
                    else:
                        send_msg(peer_id, "ℹ️ Рассылка уже остановлена")
                
                elif msg.startswith("вложение "):
                    attachment = full_text[9:].strip()
                    if attachment:
                        spam_attachment = attachment
                        send_msg(peer_id, "📎 Вложение установлено!")
                    else:
                        send_msg(peer_id, "⚠️ Укажи ссылку на вложение!")
                
                elif msg == "убрать вложение":
                    spam_attachment = ""
                    send_msg(peer_id, "🗑 Вложение удалено")
                
                elif msg.startswith("кнопка "):
                    parts = full_text[7:].strip().split("|")
                    if len(parts) >= 1:
                        link = parts[0].strip()
                        button_text = parts[1].strip() if len(parts) > 1 else "Перейти"
                        
                        if link:
                            spam_button_link = link
                            spam_button_text = button_text
                            spam_keyboard = create_keyboard(link, button_text)
                            send_msg(peer_id, f"🔘 Кнопка установлена!\n🔗 Ссылка: {link}\n📝 Текст кнопки: {button_text}", keyboard=spam_keyboard)
                        else:
                            send_msg(peer_id, "⚠️ Укажи ссылку!")
                    else:
                        send_msg(peer_id, "⚠️ Формат: кнопка ссылка|текст кнопки\nПример: кнопка https://vk.com|Группа ВК")
                
                elif msg == "убрать кнопку":
                    spam_keyboard = None
                    spam_button_link = ""
                    spam_button_text = ""
                    send_msg(peer_id, "🗑 Кнопка удалена!")
                
                elif msg.startswith("интервал "):
                    try:
                        new_interval = int(msg.split()[1])
                        if 1 <= new_interval <= 3600:
                            spam_interval = new_interval
                            send_msg(peer_id, f"⏱ Интервал: {new_interval}с ({new_interval//60}м {new_interval%60}с)")
                    except:
                        send_msg(peer_id, "⚠️ Пример: интервал 300")
                
                elif msg == "адд":
                    if peer_id > 2000000000:
                        if save_chat(peer_id):
                            name = get_chat_name(peer_id)
                            send_msg(peer_id, f"✅ Чат '{name}' добавлен в базу!")
                        else:
                            send_msg(peer_id, "ℹ️ Этот чат уже в базе")
                    else:
                        send_msg(peer_id, "⚠️ Эту команду нужно писать в беседе!")
                
                elif msg == "дел":
                    if peer_id > 2000000000:
                        if remove_chat(peer_id):
                            send_msg(peer_id, "🗑 Чат удален из базы!")
                        else:
                            send_msg(peer_id, "ℹ️ Чат не найден в базе")
                    else:
                        send_msg(peer_id, "⚠️ Эту команду нужно писать в беседе!")
                
                elif msg == "очистка":
                    send_msg(peer_id, "🔄 Проверяю чаты... Это может занять время")
                    removed = clean_inactive_chats()
                    send_msg(peer_id, f"🧹 Очистка завершена!\n🗑 Удалено неактивных: {removed}\n📊 Осталось в базе: {len(get_saved_chats())}")
                
                elif msg == "список":
                    chats = sorted(get_saved_chats(), key=lambda x: int(x))
                    if chats:
                        chat_list = "📋 ЧАТЫ В БАЗЕ\n══════════════\n"
                        for i, chat_id in enumerate(chats[:30], 1):
                            name = get_chat_name(int(chat_id))
                            status = "✅" if test_chat_access(int(chat_id)) else "❌"
                            chat_list += f"{i}. {name} {status}\n"
                        if len(chats) > 30:
                            chat_list += f"\n... и еще {len(chats) - 30} чатов"
                        send_msg(peer_id, chat_list)
                    else:
                        send_msg(peer_id, "📭 База чатов пуста!")
                
                elif msg == "сброс":
                    old_sent = messages_sent
                    messages_sent = 0
                    failed_messages = 0
                    current_progress["current"] = 0
                    current_progress["total"] = 0
                    current_campaign_stats.clear()
                    send_msg(peer_id, f"🔄 Счетчики сброшены! (было {format_number(old_sent)} сообщений)")
                
                elif msg.startswith("тест "):
                    try:
                        target = int(msg.split()[1])
                        if send_msg(target, "🧪 Тестовое сообщение от бота!", keyboard=spam_keyboard):
                            send_msg(peer_id, f"✅ Тест успешно отправлен в чат {target}")
                        else:
                            send_msg(peer_id, f"❌ Ошибка отправки в чат {target}")
                    except:
                        send_msg(peer_id, "⚠️ Пример: тест 2000000001")
                
                elif msg.startswith("проверка "):
                    try:
                        target = int(msg.split()[1])
                        if test_chat_access(target):
                            send_msg(peer_id, f"✅ Чат {target} доступен")
                        else:
                            send_msg(peer_id, f"❌ Чат {target} недоступен")
                    except:
                        send_msg(peer_id, "⚠️ Укажи ID чата")
                
                elif msg == "лог":
                    if os.path.exists(LOG_FILE):
                        with open(LOG_FILE, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                            last = lines[-20:] if len(lines) > 20 else lines
                            log_text = "📋 ПОСЛЕДНИЕ ЗАПИСИ ЛОГА\n══════════════\n" + "".join(last)
                            if len(log_text) > 4000:
                                log_text = log_text[-3900:]
                            send_msg(peer_id, log_text)
                    else:
                        send_msg(peer_id, "📭 Лог пуст")
                
                elif msg == "инфо":
                    if peer_id > 2000000000:
                        name = get_chat_name(peer_id)
                        in_base = "✅ Да" if str(peer_id) in get_saved_chats() else "❌ Нет"
                        stats = chat_stats.get(peer_id, {})
                        info = (
                            f"ℹ️ ИНФОРМАЦИЯ О ЧАТЕ\n"
                            f"══════════════\n"
                            f"• Название: {name}\n"
                            f"• ID: {peer_id}\n"
                            f"• В базе: {in_base}\n"
                            f"• Отправлено: {stats.get('sent', 0)}\n"
                            f"• Ошибок: {stats.get('failed', 0)}"
                        )
                        send_msg(peer_id, info)
                    else:
                        send_msg(peer_id, "⚠️ Команда только для бесед!")
                
                elif msg == "спам-лист":
                    if is_spamming and current_progress["total"] > 0:
                        chats = list(get_saved_chats())
                        current = current_progress["current"]
                        remaining = len(chats) - current
                        
                        queue_msg = (
                            f"📋 ОЧЕРЕДЬ РАССЫЛКИ\n"
                            f"══════════════\n"
                            f"• Всего чатов: {len(chats)}\n"
                            f"• Отправлено: {current}\n"
                            f"• Осталось: {remaining}"
                        )
                        
                        if 0 < remaining <= 10:
                            queue_msg += "\n\n⏳ Ближайшие чаты:\n"
                            for chat_id in chats[current:current+10]:
                                name = chat_stats[int(chat_id)]["name"] or get_chat_name(int(chat_id))
                                queue_msg += f"• {name}\n"
                        
                        send_msg(peer_id, queue_msg)
                    else:
                        send_msg(peer_id, "ℹ️ Рассылка не активна")
                
                elif msg.startswith("импорт"):
                    if "fwd_messages" in event.obj.message:
                        fwd = event.obj.message['fwd_messages'][0]['text']
                        imported = 0
                        for word in fwd.split():
                            try:
                                if word.strip().isdigit() and int(word.strip()) > 2000000000:
                                    if save_chat(int(word.strip())):
                                        imported += 1
                            except:
                                pass
                        send_msg(peer_id, f"📥 Импортировано чатов: {imported}")
                    else:
                        send_msg(peer_id, "⚠️ Перешли сообщение с ID чатов!")
                
                elif msg == "рестарт бота":
                    send_msg(peer_id, "🔄 Выполняю полный перезапуск бота...\n💾 Данные сохранены\n⏳ Бот вернется через несколько секунд")
                    save_backup()
                    save_stats()
                    time.sleep(2)
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                
                elif sender_id in OWNER_IDS:
                    if msg.startswith("доступ ") and not msg.startswith("-доступ "):
                        user_id = extract_user_id(full_text[7:].strip())
                        if user_id and grant_access(user_id):
                            name = get_user_name(user_id)
                            send_msg(peer_id, f"🔓 Доступ выдан пользователю {name}")
                            try:
                                vk.messages.send(
                                    peer_id=user_id,
                                    message="🔓 Вам выдан доступ к боту рассылки!\nНапишите 'хелп' для списка команд.",
                                    random_id=random.randint(1, 2147483647),
                                    v='5.131'
                                )
                            except:
                                pass
                        else:
                            send_msg(peer_id, "⚠️ Укажи ссылку или ID: доступ vk.com/id123")
                    
                    elif msg.startswith("-доступ "):
                        user_id = extract_user_id(full_text[8:].strip())
                        if user_id and revoke_access(user_id):
                            name = get_user_name(user_id)
                            send_msg(peer_id, f"🔒 Доступ забран у {name}")
                        else:
                            send_msg(peer_id, "ℹ️ У этого пользователя нет доступа")
                    
                    elif msg == "пользователи":
                        access_data = load_access_users()
                        users_list = "👥 ПОЛЬЗОВАТЕЛИ С ДОСТУПОМ\n══════════════\n👑 Владельцы:\n"
                        for owner_id in OWNER_IDS:
                            users_list += f"• {get_user_name(owner_id)}\n"
                        
                        if access_data["allowed_users"]:
                            users_list += "\n✅ Разрешенные:\n"
                            for user_id in access_data["allowed_users"]:
                                if user_id not in OWNER_IDS:
                                    users_list += f"• {get_user_name(user_id)}\n"
                        
                        if access_data.get("blacklist"):
                            users_list += "\n🚫 Черный список:\n"
                            for user_id in access_data["blacklist"][:10]:
                                users_list += f"• {get_user_name(user_id)}\n"
                        
                        users_list += f"\nВсего: {len(access_data['allowed_users'])}"
                        send_msg(peer_id, users_list)
            
            else:
                if msg.startswith(("хелп", "стат", "рассылка", "стоп", "адд", "дел", "очистка", "список", "сброс", "тест", "проверка", "лог", "импорт", "пинг", "инфо", "интервал", "вложение", "пользователи", "доступ", "спам-лист", "ошибки", "рестарт", "кнопка")):
                    send_msg(peer_id, "⛔ У вас нет доступа к боту!")

except KeyboardInterrupt:
    print("\n👋 Бот остановлен!")
    save_backup()
    save_stats()
    log_action("bot_stop", "⏹", "Бот остановлен")
    
except Exception as e:
    print(f"❗ Критическая ошибка: {e}")
    log_action("critical_error", "❌", str(e))
    save_backup()
    
#если че в коде уже можешь сам менять что нужно, удачи b.y: karp1k