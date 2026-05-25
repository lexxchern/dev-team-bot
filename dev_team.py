"""
🤖 AI Dev Team — Команда ИИ-агентов на базе DeepSeek
PM → Architect → Backend Dev → QA → DevOps → (опционально Frontend)

v3 улучшения:
  - agent_frontend интегрирован в пайплайн (ключевое слово "фронтенд"/"frontend" в запросе)
  - Throttle для notify(): не чаще 1 сообщения в секунду (защита от лимита Telegram)
  - Все предыдущие исправления сохранены
"""

import json
import os
import re
import time
import threading
import urllib.request
import urllib.error
from dotenv import load_dotenv
import telebot

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ─────────────────────────────────────────────
# DeepSeek API
# ─────────────────────────────────────────────

def call_deepseek(system: str, user_message: str,
                  model: str = "deepseek-chat", max_tokens: int = 2000) -> str:
    """Универсальный вызов DeepSeek API с retry (3 попытки)."""
    url = "https://api.deepseek.com/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_message}
        ]
    }).encode("utf-8")

    last_error = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "User-Agent": "AIDevTeam/3.0"
                }
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            print(f"   [DeepSeek] Попытка {attempt}/3 не удалась: {e}")
            if attempt < 3:
                time.sleep(3 * attempt)
        except Exception as e:
            raise e

    raise ConnectionError(f"DeepSeek API недоступен после 3 попыток: {last_error}")


def is_qa_ok(report: str) -> bool:
    """OK, OK., OK! — всё считается принятым."""
    return bool(re.match(r'^\s*ok[\s.,!]*$', report.strip(), re.IGNORECASE))


# ─────────────────────────────────────────────
# Throttle для Telegram notify
# ─────────────────────────────────────────────

_last_notify_time = 0.0
_notify_lock = threading.Lock()

def throttled_send(chat_id: int, text: str) -> None:
    """Отправляет сообщение не чаще 1 раза в секунду (лимит Telegram ~30/сек)."""
    global _last_notify_time
    with _notify_lock:
        now = time.time()
        gap = now - _last_notify_time
        if gap < 1.0:
            time.sleep(1.0 - gap)
        try:
            bot.send_message(chat_id, text)
        except Exception as e:
            print(f"   [Telegram] Ошибка отправки: {e}")
        _last_notify_time = time.time()


# ─────────────────────────────────────────────
# Агенты
# ─────────────────────────────────────────────

def agent_pm(user_request: str) -> list:
    """👨‍💼 PM: декомпозиция запроса на 3-5 задач в JSON."""
    system = (
        "Ты опытный Project Manager. "
        "Разбей задачу на 3-5 подзадач. "
        "Ответь ТОЛЬКО валидным JSON-массивом (без markdown, без пояснений): "
        '[{"id":1,"title":"...","description":"..."}]'
    )
    try:
        resp = call_deepseek(system, f"Пользователь хочет: {user_request}",
                             max_tokens=1000)
        # Усиленный парсинг: захватывает весь массив даже с переносами строк
        match = re.search(r'(\[[\s\S]*\])', resp)
        if match:
            return json.loads(match.group(1))
    except Exception as e:
        print(f"   [PM] Ошибка: {e}")
    return [{"id": 1, "title": "Базовая реализация", "description": user_request}]


def agent_architect(task: dict) -> str:
    """📐 Architect: техническая спецификация (макс 60K символов)."""
    system = (
        "Ты System Architect. Напиши детальную техническую спецификацию: "
        "используемые библиотеки и версии, структуру БД (таблицы и поля), "
        "API endpoints, архитектуру модулей, паттерны проектирования. "
        "Пиши чётко, структурированно."
    )
    result = call_deepseek(
        system,
        f"Задача: {task['title']}\nОписание: {task['description']}",
        max_tokens=2000
    )
    return result[:60000]


def agent_backend(spec: str) -> str:
    """💻 Backend Developer: рабочий Python-код."""
    system = (
        "Ты Senior Backend Developer. "
        "Напиши полный рабочий код на Python по спецификации ниже. "
        "Используй FastAPI или библиотеки из спецификации. "
        "Добавь docstring и inline-комментарии. "
        "Верни ТОЛЬКО код, без пояснений и markdown-обёрток."
    )
    return call_deepseek(system, f"Спецификация:\n{spec[:55000]}", max_tokens=4000)


def agent_frontend(spec: str) -> str:
    """🎨 Frontend Developer: HTML/CSS/JS или Telegram-клавиатуры."""
    system = (
        "Ты Senior Frontend Developer. "
        "Напиши полный готовый к запуску HTML/CSS/JS интерфейс "
        "или Telegram inline-клавиатуры по спецификации. "
        "Верни ТОЛЬКО код."
    )
    return call_deepseek(system, f"Спецификация:\n{spec[:55000]}", max_tokens=3000)


def agent_qa(code: str, task_title: str) -> str:
    """🔍 QA Engineer: анализ кода → 'OK' или список проблем."""
    system = (
        "Ты Senior QA Engineer. "
        "Проверь код на: синтаксические ошибки, логические баги, "
        "уязвимости безопасности, несоответствие задаче, отсутствие обработки ошибок. "
        "Если всё хорошо — ответь ТОЛЬКО словом 'OK'. "
        "Если есть проблемы — перечисли нумерованным списком с предложениями по исправлению."
    )
    return call_deepseek(system,
                         f"Задача: {task_title}\n\nКод:\n{code[:55000]}",
                         max_tokens=1000)


def agent_devops(code: str, task_title: str) -> str:
    """🐳 DevOps Engineer: Dockerfile, docker-compose, инструкция."""
    system = (
        "Ты DevOps Engineer. "
        "Напиши: Dockerfile, docker-compose.yml и инструкцию по запуску "
        "для этого Python-кода. Используй многоэтапную сборку где уместно. "
        "Верни ТОЛЬКО конфиги и инструкцию."
    )
    return call_deepseek(system,
                         f"Задача: {task_title}\n\nКод:\n{code[:55000]}",
                         max_tokens=2000)


# ─────────────────────────────────────────────
# Оркестратор
# ─────────────────────────────────────────────

def needs_frontend(user_request: str) -> bool:
    """Определяет нужен ли фронтенд по ключевым словам в запросе."""
    keywords = ["фронтенд", "frontend", "интерфейс", "html", "ui", "веб", "web",
                "сайт", "страниц", "форм", "кнопк", "клавиатур"]
    req_lower = user_request.lower()
    return any(kw in req_lower for kw in keywords)


def run_team(user_request: str, chat_id: int = None) -> None:
    """
    Главный пайплайн:
    PM → Architect → Backend (QA-цикл до 3 раз) → DevOps
                  ↘ Frontend (если нужен, параллельно)
    Сохраняет: .py, _frontend.html, _spec.txt, _qa_report.txt, _deploy.txt
    """

    def notify(text: str) -> None:
        print(text)
        if chat_id:
            throttled_send(chat_id, text)

    with_frontend = needs_frontend(user_request)

    notify("👨‍💼 PM анализирует запрос и декомпозирует задачи...")
    tasks = agent_pm(user_request)
    notify(f"✅ PM: разбито на {len(tasks)} задач:\n" +
           "\n".join(f"  {t['id']}. {t['title']}" for t in tasks))

    if with_frontend:
        notify("🎨 Обнаружен запрос на фронтенд — Frontend агент будет подключён.")

    for task in tasks:
        notify(f"\n📐 Архитектор проектирует: «{task['title']}»...")
        try:
            spec = agent_architect(task)
        except Exception as e:
            notify(f"❌ Architect: ошибка — {e}")
            continue
        notify(f"✅ Architect: спецификация готова ({len(spec)} символов)")

        filename_base = re.sub(r'[^\w]', '_', task['title'])

        # Сохраняем спецификацию
        with open(f"{filename_base}_spec.txt", "w", encoding="utf-8") as f:
            f.write(spec)

        # Frontend — параллельный поток (если нужен)
        frontend_thread = None
        if with_frontend:
            def run_frontend(s=spec, fb=filename_base):
                try:
                    notify("🎨 Frontend пишет интерфейс...")
                    html = agent_frontend(s)
                    with open(f"{fb}_frontend.html", "w", encoding="utf-8") as fh:
                        fh.write(html)
                    notify(f"✅ Frontend: сохранён {fb}_frontend.html ({len(html)} символов)")
                except Exception as e:
                    notify(f"❌ Frontend: ошибка — {e}")
            frontend_thread = threading.Thread(target=run_frontend, daemon=True)
            frontend_thread.start()

        # Backend + QA цикл
        code = ""
        qa_report = ""
        qa_passed = False

        for iteration in range(1, 4):
            notify(f"💻 Backend пишет код (попытка {iteration}/3)...")
            try:
                code = agent_backend(spec)
            except Exception as e:
                notify(f"❌ Backend: ошибка — {e}")
                break
            notify(f"✅ Backend: код получен ({len(code)} символов)")

            notify("🔍 QA проверяет код...")
            try:
                qa_report = agent_qa(code, task['title'])
            except Exception as e:
                notify(f"❌ QA: ошибка — {e}")
                break

            if is_qa_ok(qa_report):
                notify("✅ QA: код принят!")
                qa_passed = True
                break
            else:
                notify(f"❌ QA нашёл замечания:\n{qa_report[:600]}")
                spec = (f"{spec}\n\n--- Замечания QA (итерация {iteration}) ---\n"
                        f"{qa_report}\nИсправь все проблемы.")

        if not qa_passed:
            notify("⚠️ QA: не удалось пройти за 3 попытки. Сохраняю лучший вариант.")

        # Сохраняем код и QA-отчёт
        with open(f"{filename_base}.py", "w", encoding="utf-8") as f:
            f.write(f"# Задача: {task['title']}\n# Описание: {task['description']}\n\n")
            f.write(code)
        notify(f"💾 Код сохранён: {filename_base}.py")

        with open(f"{filename_base}_qa_report.txt", "w", encoding="utf-8") as f:
            f.write(qa_report)

        # DevOps
        notify("🐳 DevOps готовит конфигурацию развёртывания...")
        try:
            devops_result = agent_devops(code, task['title'])
            with open(f"{filename_base}_deploy.txt", "w", encoding="utf-8") as f:
                f.write(devops_result)
            notify(f"✅ DevOps: сохранён {filename_base}_deploy.txt")
        except Exception as e:
            notify(f"❌ DevOps: ошибка — {e}")

        # Ждём завершения frontend если он запускался
        if frontend_thread:
            frontend_thread.join(timeout=120)

        if task != tasks[-1]:
            time.sleep(2)

    notify("\n🎉 Все задачи выполнены командой ИИ!\n"
           "Файлы сохранены в текущую директорию.")


# ─────────────────────────────────────────────
# Анализ загруженного .py файла
# ─────────────────────────────────────────────

def analyze_file(code: str, mode: str, chat_id: int) -> None:
    """
    Три режима анализа загруженного .py файла:
      qa       — QA проверка багов и уязвимостей
      improve  — Architect предлагает улучшения архитектуры
      devops   — DevOps генерирует Dockerfile и docker-compose
    """
    def notify(text: str) -> None:
        print(text)
        throttled_send(chat_id, text)

    try:
        if mode == "qa":
            notify("🔍 QA анализирует ваш код...")
            report = agent_qa(code, "Загруженный файл")
            if is_qa_ok(report):
                notify("✅ QA: код чистый, багов не найдено!")
            else:
                notify(f"📋 Отчёт QA:\n\n{report}")

        elif mode == "improve":
            notify("📐 Architect анализирует архитектуру...")
            system = (
                "Ты Senior Software Architect. "
                "Проанализируй код и предложи конкретные улучшения: "
                "архитектура, паттерны, читаемость, производительность, безопасность. "
                "Пиши по-русски, структурированно, с примерами кода где уместно."
            )
            result = call_deepseek(system, f"Код:\n{code[:55000]}", max_tokens=2000)
            notify(f"💡 Рекомендации Architect:\n\n{result}")

        elif mode == "devops":
            notify("🐳 DevOps готовит конфигурацию для вашего кода...")
            result = agent_devops(code, "Загруженный файл")
            notify(f"📦 Docker конфигурация:\n\n{result}")

        notify("✅ Анализ завершён.")

    except Exception as e:
        notify(f"❌ Ошибка при анализе файла: {e}")


def download_file_content(file_id: str) -> str:
    """Скачивает файл из Telegram и возвращает содержимое как строку."""
    file_info = bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
    req = urllib.request.Request(file_url, headers={"User-Agent": "AIDevTeam/3.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ─────────────────────────────────────────────
# Telegram бот
# ─────────────────────────────────────────────

@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    text = (
        "👥 *AI Dev Team на базе DeepSeek* v3\n\n"
        "Команда агентов разработает ваш проект:\n"
        "👨‍💼 PM → 📐 Architect → 💻 Backend → 🔍 QA → 🐳 DevOps\n"
        "🎨 Frontend — подключается автоматически если нужен\n\n"
        "📎 *Прикрепите .py файл* для анализа:\n"
        "• Без подписи — QA проверит баги\n"
        "• Подпись `улучши` — Architect предложит улучшения\n"
        "• Подпись `devops` — DevOps создаст Dockerfile\n\n"
        "_Пример: «Создай веб-сайт с формой обратной связи»_\n"
        "_Пример: «Создай Telegram бота для заметок с SQLite»_"
    )
    bot.reply_to(message, text, parse_mode="Markdown")


@bot.message_handler(content_types=["document"])
def handle_document(message):
    doc = message.document

    if not doc.file_name.endswith(".py"):
        bot.reply_to(message, "⚠️ Поддерживаются только файлы `.py`",
                     parse_mode="Markdown")
        return

    if doc.file_size > 500_000:
        bot.reply_to(message, "⚠️ Файл слишком большой. Максимум 500 КБ.")
        return

    caption = (message.caption or "").strip().lower()
    if "улучши" in caption or "improve" in caption:
        mode, mode_label = "improve", "улучшение архитектуры"
    elif "devops" in caption or "docker" in caption:
        mode, mode_label = "devops", "генерация Docker конфигурации"
    else:
        mode, mode_label = "qa", "QA проверка"

    bot.reply_to(
        message,
        f"📎 Файл `{doc.file_name}` получен.\n"
        f"🔄 Режим: *{mode_label}*\nНачинаю анализ...",
        parse_mode="Markdown"
    )

    try:
        code = download_file_content(doc.file_id)
        threading.Thread(
            target=analyze_file,
            args=(code, mode, message.chat.id),
            daemon=True
        ).start()
    except Exception as e:
        bot.reply_to(message, f"❌ Не удалось скачать файл: {e}")


@bot.message_handler(func=lambda m: True)
def handle_message(message):
    bot.send_chat_action(message.chat.id, "typing")
    bot.reply_to(
        message,
        "🚀 Команда ИИ начала работу! Буду отправлять статусы по мере выполнения...",
        parse_mode="Markdown"
    )
    threading.Thread(
        target=run_team,
        args=(message.text, message.chat.id),
        daemon=True
    ).start()


# ─────────────────────────────────────────────
# Точка входа
# ─────────────────────────────────────────────

if __name__ == "__main__":
    if not DEEPSEEK_API_KEY:
        print("❌ Ошибка: DEEPSEEK_API_KEY не задан в .env")
        exit(1)

    if TELEGRAM_TOKEN:
        print("🤖 AI Dev Team v3 запущен.")
        print("   Модель: deepseek-chat | Frontend: авто по ключевым словам")
        bot.infinity_polling()
    else:
        print("🤖 Режим CLI. Введите описание проекта:")
        user_input = input("> ").strip()
        if user_input:
            run_team(user_input)
        else:
            print("❌ Пустой запрос.")
