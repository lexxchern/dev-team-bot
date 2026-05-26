"""
🤖 AI Dev Team — Команда ИИ-агентов на базе DeepSeek
PM → Architect → Designer → Frontend → Backend Dev → QA → DevOps

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
# Папка для результатов
# ─────────────────────────────────────────────

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def rp(filename: str) -> str:
    """Полный путь файла внутри results/"""
    return os.path.join(RESULTS_DIR, filename)


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



def agent_designer(task: dict, spec: str) -> str:
    """🎨 UI/UX Designer: дизайн-концепция и ТЗ для Frontend."""
    system = (
        "Ты Senior UI/UX Designer. "
        "На основе задачи и технической спецификации создай детальную дизайн-концепцию: "
        "1. Цветовая палитра (HEX коды) "
        "2. Типографика (шрифты, размеры, веса) "
        "3. Компоненты UI (кнопки, карточки, формы, иконки) "
        "4. Макет страниц/экранов (описание layout) "
        "5. UX-flow (как пользователь взаимодействует с интерфейсом) "
        "6. Готовые CSS-переменные для реализации. "
        "Пиши чётко, с конкретными значениями — это ТЗ для Frontend разработчика."
    )
    return call_deepseek(
        system,
        f"Задача: {task['title']}\nОписание: {task['description']}\n\nСпецификация:\n{spec[:30000]}",
        max_tokens=2000
    )

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
                "сайт", "страниц", "форм", "кнопк", "клавиатур", "дизайн", "design"]
    req_lower = user_request.lower()
    return any(kw in req_lower for kw in keywords)




def agent_summary(task_title: str, spec: str, qa_report: str, iterations: int) -> str:
    """
    📝 Summary: человеческое описание что было сделано и исправлено.
    """
    system = (
        "Ты технический писатель. Напиши краткий отчёт на русском языке (10-20 строк): "
        "1. Что было сделано (главные функции и решения) "
        "2. Какие проблемы нашёл QA и что было исправлено "
        "3. Как запустить код (зависимости, команда запуска) "
        "Пиши просто и понятно, без технического жаргона."
    )
    qa_info = qa_report if qa_report and qa_report.strip().upper() != "OK" else "Замечаний не было."
    prompt = (
        f"Задача: {task_title}\n"
        f"Итераций QA: {iterations}\n"
        f"Замечания QA: {qa_info[:2000]}\n"
        f"Спецификация (кратко): {spec[:1000]}"
    )
    return call_deepseek(system, prompt, max_tokens=800)

def agent_router(user_message: str) -> str:
    """
    🧭 Router: определяет тип запроса.
    Возвращает 'task' (запустить пайплайн) или 'question' (просто ответить).
    """
    system = (
        "Ты определяешь тип запроса пользователя. "
        "Если пользователь хочет СОЗДАТЬ, РАЗРАБОТАТЬ, НАПИСАТЬ КОД, СДЕЛАТЬ бота/сайт/приложение/скрипт — ответь ТОЛЬКО словом: task "
        "Если пользователь задаёт ВОПРОС, просит ОБЪЯСНИТЬ, СРАВНИТЬ, ПОСОВЕТОВАТЬ, ПОМОЧЬ разобраться — ответь ТОЛЬКО словом: question "
        "Отвечай ТОЛЬКО одним словом: task или question"
    )
    try:
        result = call_deepseek(system, user_message, max_tokens=10)
        if "task" in result.lower():
            return "task"
        return "question"
    except Exception:
        return "task"  # по умолчанию запускаем пайплайн


def agent_answer(user_message: str) -> str:
    """
    💬 Консультант: отвечает на вопросы без запуска пайплайна.
    """
    system = (
        "Ты опытный Senior Software Engineer и технический консультант. "
        "Отвечай чётко, по делу, на русском языке. "
        "Используй примеры кода где уместно."
    )
    return call_deepseek(system, user_message, max_tokens=1500)

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
    result_files = []  # Список файлов для финальной отправки

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

        # Короткое имя файла: первые 3 слова + порядковый номер задачи
        words = re.sub(r'[^\w\s]', '', task['title']).split()[:3]
        short_name = '_'.join(words) + f"_{task['id']}"
        filename_base = short_name.lower()

        # Frontend — параллельный поток (если нужен)
        frontend_thread = None
        if with_frontend:
            def run_frontend(s=spec, t=task, fb=filename_base):
                try:
                    notify("🎨 Designer создаёт дизайн-концепцию...")
                    design = agent_designer(t, s)
                    notify(f"✅ Designer: концепция готова ({len(design)} символов)")
                    # Передаём дизайн-концепцию во Frontend
                    spec_with_design = s + "\n\n--- Дизайн-концепция от Designer ---\n" + design
                    notify("🖥️ Frontend реализует интерфейс по дизайну...")
                    html = agent_frontend(spec_with_design)
                    # Убираем markdown-обёртки если модель их добавила
                    html_clean = html.strip()
                    if html_clean.startswith("```"):
                        html_clean = re.sub(r'^```[a-z]*\n?', '', html_clean)
                        html_clean = re.sub(r'```$', '', html_clean).strip()
                    html_path = rp(f"{fb}_frontend.html")
                    with open(html_path, "w", encoding="utf-8") as fh:
                        fh.write(html_clean)
                    notify(f"✅ Frontend готов: {fb}_frontend.html ({len(html)} символов)")
                    # Запоминаем html для финальной отправки
                    result_files.append((html_path, f"🎨 Frontend: {fb}"))
                except Exception as e:
                    notify(f"❌ Frontend: ошибка — {e}")
            frontend_thread = threading.Thread(target=run_frontend, daemon=True)
            frontend_thread.start()

        # Backend + QA цикл
        code = ""
        code_clean = ""
        qa_report = ""
        qa_passed = False
        final_iteration = 1

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
                final_iteration = iteration
                break
            else:
                notify(f"❌ QA нашёл замечания:\n{qa_report[:600]}")
                spec = (f"{spec}\n\n--- Замечания QA (итерация {iteration}) ---\n"
                        f"{qa_report}\nИсправь все проблемы.")

        if not qa_passed:
            notify("⚠️ QA: не удалось пройти за 3 попытки. Сохраняю лучший вариант.")

        # Сохраняем код и QA-отчёт
        # Проверяем что код не пустой перед сохранением
        if not code_clean or len(code_clean) < 10:
            notify(f"⚠️ Код для задачи '{task['title']}' пустой — пропускаю.")
            continue

        # Убираем markdown-обёртки если модель их добавила
        code_clean = code.strip()
        if code_clean.startswith("```"):
            code_clean = re.sub(r'^```[a-z]*\n?', '', code_clean)
            code_clean = re.sub(r'```$', '', code_clean).strip()

        py_path = rp(f"{filename_base}.py")
        with open(py_path, "w", encoding="utf-8") as f:
            f.write(f"# Задача: {task['title']}\n# Описание: {task['description']}\n\n")
            f.write(code_clean)

        # Проверяем что файл реально записался
        if os.path.getsize(py_path) < 10:
            notify(f"⚠️ Файл {filename_base}.py записался пустым — пропускаю.")
            continue

        notify(f"💾 Код готов ({len(code_clean)} символов), формирую отчёт...")

        # Генерируем человеческий отчёт
        try:
            summary = agent_summary(task['title'], spec, qa_report, final_iteration)
        except Exception as e:
            summary = f"Задача '{task['title']}' выполнена за {final_iteration} итерации QA.\nОшибка генерации отчёта: {e}"

        if not summary or len(summary.strip()) < 5:
            summary = f"Задача '{task['title']}' выполнена за {final_iteration} итерации QA."

        summary_path = rp(f"{filename_base}_отчёт.txt")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"Задача: {task['title']}\n")
            f.write("=" * 50 + "\n\n")
            f.write(summary)

        # Запоминаем только .py и отчёт
        result_files.append((py_path, f"💻 Код: {task['title']}"))
        result_files.append((summary_path, f"📝 Отчёт: {task['title']}"))



        # Ждём завершения frontend если он запускался
        if frontend_thread:
            frontend_thread.join(timeout=120)

        if task != tasks[-1]:
            time.sleep(2)

    # Собираем всё в один итоговый файл каждого типа
    notify("\n🎉 Все задачи выполнены! Собираю итоговые файлы...")

    # Объединяем весь код в один .py
    all_code_path = rp("итог_код.py")
    all_report_path = rp("итог_отчёт.txt")

    try:
        with open(all_code_path, "w", encoding="utf-8") as f_code, \
             open(all_report_path, "w", encoding="utf-8") as f_rep:
            for file_path, caption in result_files:
                if file_path.endswith(".py"):
                    f_code.write(f"# {'='*50}\n# {caption}\n# {'='*50}\n\n")
                    f_code.write(open(file_path, encoding="utf-8").read())
                    f_code.write("\n\n")
                elif file_path.endswith(".txt"):
                    f_rep.write(open(file_path, encoding="utf-8").read())
                    f_rep.write("\n\n")

        if chat_id:
            # Отправляем только 2 файла: код + отчёт
            for path, cap in [(all_code_path, "💻 Итоговый код"), (all_report_path, "📝 Итоговый отчёт")]:
                try:
                    with open(path, "rb") as f:
                        bot.send_document(chat_id, f, caption=cap)
                    time.sleep(0.5)
                except Exception as e:
                    notify(f"⚠️ {cap}: {e}")

            # HTML только если был фронтенд
            html_files = [(p, c) for p, c in result_files if p.endswith(".html")]
            if html_files:
                # Берём последний html
                path, cap = html_files[-1]
                try:
                    with open(path, "rb") as f:
                        bot.send_document(chat_id, f, caption="🎨 Интерфейс")
                except Exception as e:
                    notify(f"⚠️ HTML: {e}")

        notify("✅ Готово! Отправлено максимум 3 файла.")
    except Exception as e:
        notify(f"❌ Ошибка сборки итогов: {e}")


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
        "🎨 Designer + Frontend — подключаются автоматически если нужен интерфейс\n\n"
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

    caption = (message.caption or "").strip()
    caption_lower = caption.lower()

    # Если есть текст под файлом — передаём файл + задачу в пайплайн
    if caption and not any(kw in caption_lower for kw in ["улучши", "improve", "devops", "docker", "qa"]):
        bot.reply_to(
            message,
            f"📎 Файл `{doc.file_name}` получен.\n"
            f"📋 Задача: *{caption}*\n"
            f"🚀 Передаю в команду ИИ...",
            parse_mode="Markdown"
        )
        try:
            code = download_file_content(doc.file_id)
            # Запускаем полный пайплайн с кодом файла как контекстом
            task_with_context = (
                f"{caption}\n\n"
                f"Вот существующий код файла {doc.file_name} для контекста:\n\n{code[:30000]}"
            )
            threading.Thread(
                target=run_team,
                args=(task_with_context, message.chat.id),
                daemon=True
            ).start()
        except Exception as e:
            bot.reply_to(message, f"❌ Не удалось скачать файл: {e}")
        return

    # Режим анализа файла
    if "улучши" in caption_lower or "improve" in caption_lower:
        mode, mode_label = "improve", "улучшение архитектуры"
    elif "devops" in caption_lower or "docker" in caption_lower:
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

    def process():
        route = agent_router(message.text)
        if route == "question":
            try:
                answer = agent_answer(message.text)
                # Разбиваем длинный ответ на части если > 4000 символов
                for i in range(0, len(answer), 4000):
                    bot.send_message(message.chat.id, answer[i:i+4000])
            except Exception as e:
                bot.reply_to(message, f"❌ Ошибка: {e}")
        else:
            bot.reply_to(
                message,
                "🚀 Команда ИИ начала работу! Буду отправлять статусы по мере выполнения...",
                parse_mode="Markdown"
            )
            run_team(message.text, message.chat.id)

    threading.Thread(target=process, daemon=True).start()


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
