import json
import sqlite3
import random
import requests
from datetime import datetime
from typing import List, Dict, Optional
import re
import os
import asyncio
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ВСТАВЬТЕ ВАШ ТОКЕН СЮДА
BOT_TOKEN = "8289474312:AAGws38BTRTSWBhdrfVhUmwKEqj0HkVotjI"

# Состояния для ConversationHandler
(CHOOSING_PROVIDER, OPENROUTER_KEY, MODEL_SELECTION, MAIN_MENU,
 CHAR_NAME, CHAR_CONCEPT, CHAR_QUESTIONS, CHAR_FINISH,
 SELECT_CHARACTER, MANAGE_CHARACTERS, DELETE_CHARACTER,
 SETTING_NAME, SETTING_CONCEPT,
 GAME_ACTION, GAME_MENU) = range(15)


# === ВСЕ КЛАССЫ ИЗ ПРЕДЫДУЩЕГО КОДА ===

class DatabaseManager:
    def __init__(self, db_path="rpg_telegram.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Таблица пользователей телеграм
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS telegram_users
                       (
                           user_id
                           INTEGER
                           PRIMARY
                           KEY,
                           username
                           TEXT,
                           current_character_id
                           INTEGER,
                           provider
                           TEXT,
                           model
                           TEXT,
                           api_key
                           TEXT,
                           created_at
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP
                       )
                       ''')

        # Таблица персонажей (добавляем user_id)
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS characters
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY,
                           user_id
                           INTEGER,
                           name
                           TEXT,
                           description
                           TEXT,
                           stats
                           TEXT,
                           created_at
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP,
                           UNIQUE
                       (
                           user_id,
                           name
                       )
                           )
                       ''')

        # Остальные таблицы как раньше
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS inventory
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY,
                           character_id
                           INTEGER,
                           item_name
                           TEXT,
                           item_description
                           TEXT,
                           quantity
                           INTEGER
                           DEFAULT
                           1,
                           FOREIGN
                           KEY
                       (
                           character_id
                       ) REFERENCES characters
                       (
                           id
                       )
                           )
                       ''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS game_events
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY,
                           character_id
                           INTEGER,
                           event_type
                           TEXT,
                           description
                           TEXT,
                           importance
                           INTEGER
                           DEFAULT
                           1,
                           timestamp
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP,
                           tags
                           TEXT,
                           FOREIGN
                           KEY
                       (
                           character_id
                       ) REFERENCES characters
                       (
                           id
                       )
                           )
                       ''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS settings
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY,
                           user_id
                           INTEGER,
                           name
                           TEXT,
                           description
                           TEXT,
                           world_facts
                           TEXT,
                           created_at
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP
                       )
                       ''')

        conn.commit()
        conn.close()


class OpenRouterClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1"
        self.model = None

    def check_connection(self) -> bool:
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            response = requests.get(f"{self.base_url}/models", headers=headers, timeout=10)
            return response.status_code == 200
        except:
            return False

    def get_popular_models(self) -> List[Dict]:
        """Получает популярные модели для RPG"""
        popular_models = [
            {"name": "anthropic/claude-3.5-sonnet", "display": "Claude 3.5 Sonnet (лучший для RPG)"},
            {"name": "openai/gpt-4o", "display": "GPT-4o (быстрый и качественный)"},
            {"name": "anthropic/claude-3-opus", "display": "Claude 3 Opus (самый умный)"},
            {"name": "meta-llama/llama-3.1-70b-instruct", "display": "Llama 3.1 70B (бесплатный)"},
            {"name": "openai/gpt-3.5-turbo", "display": "GPT-3.5 Turbo (быстрый)"},
            {"name": "mistralai/mixtral-8x7b-instruct", "display": "Mixtral 8x7B (хороший баланс)"}
        ]
        return popular_models

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.model:
            return "❌ Модель не выбрана!"

        url = f"{self.base_url}/chat/completions"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": None,
            "stream": False
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=180)
            if response.status_code == 200:
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            else:
                return f"❌ Ошибка API: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"


class OllamaClient:
    def __init__(self, base_url="http://localhost:11434"):
        self.base_url = base_url
        self.model = "huihui_ai/qwen3-abliterated:8b"

    def check_connection(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False

    def list_models(self) -> List[str]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                return [model.get("name", "") for model in models if model.get("name")]
            return []
        except:
            return []

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.model:
            return "❌ Модель не выбрана!"

        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": 0.8,
                "num_predict": -1,
                "top_p": 0.9
            }
        }

        try:
            response = requests.post(url, json=payload, timeout=300)
            if response.status_code == 200:
                return response.json().get("response", "").strip()
            else:
                return f"❌ Ошибка Ollama: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"


class GameInventory:
    def __init__(self, db_manager: DatabaseManager, character_id: int):
        self.db = db_manager
        self.character_id = character_id

    def add_item(self, name: str, description: str, quantity: int = 1):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        cursor.execute('''
                       SELECT quantity
                       FROM inventory
                       WHERE character_id = ?
                         AND item_name = ?
                       ''', (self.character_id, name))

        existing = cursor.fetchone()
        if existing:
            new_quantity = existing[0] + quantity
            cursor.execute('''
                           UPDATE inventory
                           SET quantity = ?
                           WHERE character_id = ?
                             AND item_name = ?
                           ''', (new_quantity, self.character_id, name))
        else:
            cursor.execute('''
                           INSERT INTO inventory (character_id, item_name, item_description, quantity)
                           VALUES (?, ?, ?, ?)
                           ''', (self.character_id, name, description, quantity))

        conn.commit()
        conn.close()

    def get_inventory(self) -> List[Dict]:
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        cursor.execute('''
                       SELECT item_name, item_description, quantity
                       FROM inventory
                       WHERE character_id = ?
                       ''', (self.character_id,))

        items = []
        for row in cursor.fetchall():
            items.append({
                "name": row[0],
                "description": row[1],
                "quantity": row[2]
            })

        conn.close()
        return items


class EventMemory:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def add_event(self, character_id: int, event_type: str, description: str,
                  importance: int = 1, tags: List[str] = None):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        tags_str = ",".join(tags) if tags else ""

        cursor.execute('''
                       INSERT INTO game_events (character_id, event_type, description, importance, tags)
                       VALUES (?, ?, ?, ?, ?)
                       ''', (character_id, event_type, description, importance, tags_str))

        conn.commit()
        conn.close()

    def get_recent_events(self, character_id: int, limit: int = 5) -> List[Dict]:
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        cursor.execute('''
                       SELECT event_type, description, importance, timestamp
                       FROM game_events
                       WHERE character_id = ?
                       ORDER BY timestamp DESC
                           LIMIT ?
                       ''', (character_id, limit))

        events = []
        for row in cursor.fetchall():
            events.append({
                "type": row[0],
                "description": row[1],
                "importance": row[2],
                "timestamp": row[3]
            })

        conn.close()
        return events


# === ГЛАВНЫЙ КЛАСС ТЕЛЕГРАМ БОТА ===

class TelegramRPGBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.user_clients = {}  # user_id -> llm_client
        self.user_data = {}  # user_id -> game_data

    def get_user_client(self, user_id: int):
        return self.user_clients.get(user_id)

    def get_user_data(self, user_id: int) -> dict:
        if user_id not in self.user_data:
            self.user_data[user_id] = {}
        return self.user_data[user_id]

    # === КОМАНДЫ БОТА ===

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"

        # Сохраняем пользователя в базу
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO telegram_users (user_id, username)
            VALUES (?, ?)
        ''', (user_id, username))
        conn.commit()
        conn.close()

        welcome_text = """🎮 **Добро пожаловать в RPG игру с ИИ!**

Это текстовая ролевая игра, где ваши действия обрабатывает искусственный интеллект.

**Возможности:**
🎭 Создание персонажей с помощью ИИ
🎲 Система вероятностей как в D&D
🎒 Инвентарь и память событий
🌍 Создание игровых миров
🤖 Поддержка Ollama и OpenRouter

Выберите провайдера ИИ:"""

        keyboard = [
            [KeyboardButton("🏠 Ollama (локальный)")],
            [KeyboardButton("☁️ OpenRouter (облачный)")],
            [KeyboardButton("❌ Отмена")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
        return CHOOSING_PROVIDER

    async def choose_provider(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text.strip()

        if "Ollama" in text:
            # Проверяем доступность Ollama
            client = OllamaClient()
            if not client.check_connection():
                await update.message.reply_text(
                    "❌ Не удается подключиться к Ollama!\n"
                    "Убедитесь, что Ollama запущен: `ollama serve`",
                    parse_mode='Markdown'
                )
                return CHOOSING_PROVIDER

            models = client.list_models()
            if not models:
                await update.message.reply_text("❌ Модели в Ollama не найдены!")
                return CHOOSING_PROVIDER

            # Сохраняем клиент и показываем модели
            self.user_clients[user_id] = client

            text = "🤖 **Выберите модель Ollama:**\n\n"
            keyboard = []

            for i, model in enumerate(models[:8], 1):  # Показываем первые 8 моделей
                text += f"{i}. `{model}`\n"
                keyboard.append([KeyboardButton(f"{i}. {model}")])

            keyboard.append([KeyboardButton("🔙 Назад")])
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return MODEL_SELECTION

        elif "OpenRouter" in text:
            await update.message.reply_text(
                "🔑 **Настройка OpenRouter**\n\n"
                "Отправьте ваш API ключ OpenRouter.\n"
                "Получить ключ: https://openrouter.ai/keys\n\n"
                "Или отправьте /cancel для отмены",
                parse_mode='Markdown'
            )
            return OPENROUTER_KEY

        elif "Отмена" in text:
            await update.message.reply_text("👋 До встречи!")
            return ConversationHandler.END

        else:
            await update.message.reply_text("Пожалуйста, выберите провайдера из меню.")
            return CHOOSING_PROVIDER

    async def openrouter_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        api_key = update.message.text.strip()

        if len(api_key) < 10:
            await update.message.reply_text("❌ Ключ слишком короткий. Попробуйте еще раз.")
            return OPENROUTER_KEY

        # Создаем и проверяем клиент
        client = OpenRouterClient(api_key)
        if not client.check_connection():
            await update.message.reply_text("❌ Неверный API ключ или проблемы с подключением.")
            return OPENROUTER_KEY

        # Сохраняем клиент
        self.user_clients[user_id] = client

        # Показываем популярные модели
        models = client.get_popular_models()
        text = "🤖 **Выберите модель OpenRouter:**\n\n"
        keyboard = []

        for i, model in enumerate(models, 1):
            text += f"{i}. {model['display']}\n"
            keyboard.append([KeyboardButton(f"{i}. {model['display']}")])

        keyboard.append([KeyboardButton("🔙 Назад")])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return MODEL_SELECTION

    async def select_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text.strip()
        client = self.user_clients.get(user_id)

        if not client:
            await update.message.reply_text("❌ Ошибка: клиент не найден")
            return CHOOSING_PROVIDER

        if "Назад" in text:
            return CHOOSING_PROVIDER

        # Извлекаем номер модели
        try:
            model_num = int(text.split('.')[0]) - 1

            if isinstance(client, OllamaClient):
                models = client.list_models()
                if 0 <= model_num < len(models):
                    client.model = models[model_num]
                else:
                    await update.message.reply_text("❌ Неверный номер модели")
                    return MODEL_SELECTION

            elif isinstance(client, OpenRouterClient):
                models = client.get_popular_models()
                if 0 <= model_num < len(models):
                    client.model = models[model_num]['name']
                else:
                    await update.message.reply_text("❌ Неверный номер модели")
                    return MODEL_SELECTION

        except (ValueError, IndexError):
            await update.message.reply_text("❌ Неверный формат. Выберите номер модели.")
            return MODEL_SELECTION

        # Тестируем модель
        await update.message.reply_text("🧪 Тестирование модели...")

        test_result = client.generate("Скажи 'Привет' на русском", "Отвечай кратко")

        if "❌" in test_result:
            await update.message.reply_text(f"❌ Ошибка модели: {test_result}")
            return MODEL_SELECTION

        provider = "Ollama" if isinstance(client, OllamaClient) else "OpenRouter"
        await update.message.reply_text(
            f"✅ **Модель подключена!**\n\n"
            f"Провайдер: {provider}\n"
            f"Модель: `{client.model}`\n"
            f"Тест: {test_result}",
            parse_mode='Markdown'
        )

        # Переходим в главное меню
        await self.show_main_menu(update, context)
        return MAIN_MENU

    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        # Проверяем текущего персонажа
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT current_character_id FROM telegram_users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        current_char_id = result[0] if result else None

        current_char_name = "Не выбран"
        if current_char_id:
            cursor.execute('SELECT name FROM characters WHERE id = ?', (current_char_id,))
            result = cursor.fetchone()
            if result:
                current_char_name = result[0]

        conn.close()

        text = f"🎮 **ГЛАВНОЕ МЕНЮ**\n\nТекущий персонаж: **{current_char_name}**"

        keyboard = [
            [KeyboardButton("👤 Создать персонажа"), KeyboardButton("👥 Выбрать персонажа")],
            [KeyboardButton("🗂️ Управление персонажами"), KeyboardButton("🌍 Создать сеттинг")],
            [KeyboardButton("🎲 Начать игру"), KeyboardButton("🔧 Диагностика")],
            [KeyboardButton("🚪 Выход")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text.strip()

        if "Создать персонажа" in text:
            await update.message.reply_text(
                "👤 **Создание персонажа**\n\nВведите имя персонажа:",
                parse_mode='Markdown'
            )
            return CHAR_NAME

        elif "Выбрать персонажа" in text:
            return await self.show_characters(update, context)

        elif "Управление персонажами" in text:
            return await self.show_manage_characters(update, context)

        elif "Создать сеттинг" in text:
            await update.message.reply_text(
                "🌍 **Создание сеттинга**\n\nВведите название мира:",
                parse_mode='Markdown'
            )
            return SETTING_NAME

        elif "Начать игру" in text:
            return await self.start_game(update, context)

        elif "Диагностика" in text:
            return await self.show_diagnostics(update, context)

        elif "Выход" in text:
            await update.message.reply_text("👋 До встречи! Для запуска снова используйте /start")
            return ConversationHandler.END

        else:
            await update.message.reply_text("Выберите опцию из меню.")
            return MAIN_MENU

    # === СОЗДАНИЕ ПЕРСОНАЖА ===

    async def char_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        name = update.message.text.strip()

        if len(name) < 2:
            await update.message.reply_text("❌ Имя слишком короткое. Попробуйте еще раз.")
            return CHAR_NAME

        # Проверяем уникальность
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM characters WHERE user_id = ? AND name = ?', (user_id, name))
        if cursor.fetchone():
            await update.message.reply_text(f"❌ Персонаж '{name}' уже существует!")
            conn.close()
            return CHAR_NAME
        conn.close()

        # Сохраняем имя
        user_data = self.get_user_data(user_id)
        user_data['char_name'] = name

        await update.message.reply_text(
            f"✅ Имя персонажа: **{name}**\n\n"
            "🎭 Теперь опишите концепцию персонажа:\n"
            "(раса, класс, предыстория, особенности)",
            parse_mode='Markdown'
        )
        return CHAR_CONCEPT

    async def char_concept(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        concept = update.message.text.strip()
        client = self.get_user_client(user_id)

        if not client:
            await update.message.reply_text("❌ Ошибка: ИИ не подключен")
            return MAIN_MENU

        user_data = self.get_user_data(user_id)
        user_data['char_concept'] = concept

        await update.message.reply_text("🤖 ИИ генерирует уточняющие вопросы...")

        # Генерируем вопросы
        questions_system = """Ты помощник для создания персонажей RPG. На основе концепции создай ровно 5 уточняющих вопросов.

Вопросы должны касаться:
1. Внешности и физических особенностей
2. Характера и личности  
3. Предыстории и мотивации
4. Навыков и способностей
5. Отношений с миром/людьми

Формат: только 5 вопросов, каждый с новой строки, без нумерации.
Пиши на русском языке."""

        questions_prompt = f"Персонаж: {user_data['char_name']}\nКонцепция: {concept}\n\nСоздай 5 уточняющих вопросов:"

        questions_response = client.generate(questions_prompt, questions_system)

        if "❌" in questions_response:
            questions = [
                "Как выглядит ваш персонаж? Опишите внешность.",
                "Какой у него характер? Основные черты личности?",
                "Что произошло в его прошлом? Предыстория?",
                "Какими навыками или способностями он обладает?",
                "Как он относится к другим людям и миру?"
            ]
        else:
            questions = [q.strip() for q in questions_response.split('\n') if q.strip()][:5]

        user_data['questions'] = questions
        user_data['answers'] = []
        user_data['current_question'] = 0

        # Задаем первый вопрос
        question = questions[0]
        await update.message.reply_text(
            f"❓ **Вопрос 1/5:**\n\n{question}\n\n"
            "💡 Можете пропустить, отправив 'пропуск'",
            parse_mode='Markdown'
        )

        return CHAR_QUESTIONS

    async def char_questions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        answer = update.message.text.strip()
        user_data = self.get_user_data(user_id)

        questions = user_data.get('questions', [])
        current_q = user_data.get('current_question', 0)
        answers = user_data.get('answers', [])

        # Сохраняем ответ
        if answer.lower() == 'пропуск':
            answers.append("(пропущено)")
        else:
            answers.append(answer)

        user_data['answers'] = answers
        current_q += 1
        user_data['current_question'] = current_q

        # Проверяем, есть ли еще вопросы
        if current_q < len(questions):
            question = questions[current_q]
            await update.message.reply_text(
                f"❓ **Вопрос {current_q + 1}/5:**\n\n{question}\n\n"
                "💡 Можете пропустить, отправив 'пропуск'",
                parse_mode='Markdown'
            )
            return CHAR_QUESTIONS
        else:
            # Все вопросы заданы, создаем персонажа
            await update.message.reply_text("⚙️ Создание персонажа... Это может занять время.")
            return await self.finish_character(update, context)

    async def finish_character(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        client = self.get_user_client(user_id)
        user_data = self.get_user_data(user_id)

        name = user_data.get('char_name', 'Неизвестный')
        concept = user_data.get('char_concept', 'Обычный персонаж')
        questions = user_data.get('questions', [])
        answers = user_data.get('answers', [])

        # Создаем финальное описание
        final_system = """Ты опытный мастер RPG, создающий детальные описания персонажей.

Создай живое, подробное описание персонажа на основе концепции и ответов на вопросы.

Структура:
1. Внешность
2. Характер и личность
3. Предыстория и мотивация
4. Навыки и особенности

Пиши живо и интересно на русском языке."""

        all_info = f"Имя: {name}\nКонцепция: {concept}\n\n"
        for i, (q, a) in enumerate(zip(questions, answers), 1):
            all_info += f"Вопрос {i}: {q}\nОтвет: {a}\n\n"

        final_prompt = f"{all_info}Создай детальное описание персонажа:"
        description = client.generate(final_prompt, final_system)

        if "❌" in description:
            description = f"Персонаж {name}. Концепция: {concept}"

        # Создаем характеристики
        stats = {
            "сила": random.randint(8, 18),
            "ловкость": random.randint(8, 18),
            "интеллект": random.randint(8, 18),
            "мудрость": random.randint(8, 18),
            "харизма": random.randint(8, 18),
            "здоровье": 100
        }

        # Сохраняем в базу
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        cursor.execute('''
                       INSERT INTO characters (user_id, name, description, stats)
                       VALUES (?, ?, ?, ?)
                       ''', (user_id, name, description, json.dumps(stats)))

        character_id = cursor.lastrowid

        # Устанавливаем как текущего персонажа
        cursor.execute('''
                       UPDATE telegram_users
                       SET current_character_id = ?
                       WHERE user_id = ?
                       ''', (character_id, user_id))

        conn.commit()
        conn.close()

        # Показываем результат
        stats_text = "\n".join([f"⚡ {k.capitalize()}: {v}" for k, v in stats.items()])

        result_text = f"✅ **ПЕРСОНАЖ СОЗДАН!**\n\n" \
                      f"👤 **Имя:** {name}\n\n" \
                      f"📖 **Описание:**\n{description[:500]}{'...' if len(description) > 500 else ''}\n\n" \
                      f"📊 **Характеристики:**\n{stats_text}"

        await update.message.reply_text(result_text, parse_mode='Markdown')

        # Возвращаемся в меню
        await self.show_main_menu(update, context)
        return MAIN_MENU

    # === ВЫБОР И УПРАВЛЕНИЕ ПЕРСОНАЖАМИ ===

    async def show_characters(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, description FROM characters WHERE user_id = ?', (user_id,))
        characters = cursor.fetchall()
        conn.close()

        if not characters:
            await update.message.reply_text("❌ У вас нет персонажей. Создайте нового!")
            await self.show_main_menu(update, context)
            return MAIN_MENU

        text = "👥 **ВЫБОР ПЕРСОНАЖА**\n\n"
        keyboard = []

        for i, (char_id, name, desc) in enumerate(characters, 1):
            short_desc = desc[:60] + "..." if len(desc) > 60 else desc
            text += f"{i}. **{name}**\n{short_desc}\n\n"
            keyboard.append([KeyboardButton(f"{i}. {name}")])

        keyboard.append([KeyboardButton("🔙 Назад в меню")])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return SELECT_CHARACTER

    async def select_character(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text.strip()

        if "Назад в меню" in text:
            await self.show_main_menu(update, context)
            return MAIN_MENU

        try:
            char_num = int(text.split('.')[0]) - 1

            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT id, name FROM characters WHERE user_id = ?', (user_id,))
            characters = cursor.fetchall()

            if 0 <= char_num < len(characters):
                char_id, name = characters[char_num]

                # Устанавливаем текущего персонажа
                cursor.execute('''
                               UPDATE telegram_users
                               SET current_character_id = ?
                               WHERE user_id = ?
                               ''', (char_id, user_id))

                conn.commit()
                conn.close()

                await update.message.reply_text(f"✅ Выбран персонаж: **{name}**", parse_mode='Markdown')
                await self.show_main_menu(update, context)
                return MAIN_MENU
            else:
                await update.message.reply_text("❌ Неверный номер персонажа")
                return SELECT_CHARACTER

        except (ValueError, IndexError):
            await update.message.reply_text("❌ Выберите персонажа из списка")
            return SELECT_CHARACTER

    # === ИГРА ===

    async def start_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        client = self.get_user_client(user_id)

        if not client:
            await update.message.reply_text("❌ ИИ не подключен!")
            return MAIN_MENU

        # Проверяем персонажа
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT current_character_id FROM telegram_users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        char_id = result[0] if result else None

        if not char_id:
            await update.message.reply_text("❌ Сначала выберите персонажа!")
            conn.close()
            await self.show_main_menu(update, context)
            return MAIN_MENU

        cursor.execute('SELECT name, description, stats FROM characters WHERE id = ?', (char_id,))
        char_data = cursor.fetchone()
        conn.close()

        if not char_data:
            await update.message.reply_text("❌ Персонаж не найден!")
            return MAIN_MENU

        name, description, stats_json = char_data
        stats = json.loads(stats_json)

        # Сохраняем данные для игры
        user_data = self.get_user_data(user_id)
        user_data['current_character_id'] = char_id
        user_data['character_stats'] = stats

        await update.message.reply_text("⚙️ Генерация начальной ситуации...")

        # Генерируем начальную ситуацию
        system_prompt = """Ты опытный мастер RPG игры. Создай интересную начальную ситуацию для персонажа.

Опиши место, обстановку и что происходит. Создай интригу и возможности для действий.
Пиши живо и детально на русском языке."""

        situation_prompt = f"Создай начальную игровую ситуацию для персонажа: {description[:300]}"
        situation = client.generate(situation_prompt, system_prompt)

        if "❌" in situation:
            situation = "Вы просыпаетесь в незнакомом месте. Вокруг тишина, но чувствуется напряжение..."

        # Сохраняем событие
        memory = EventMemory(self.db)
        memory.add_event(char_id, "начало игры", situation, 3, ["начало"])

        # Игровое меню
        keyboard = [
            [KeyboardButton("🎒 Инвентарь"), KeyboardButton("🧠 Память")],
            [KeyboardButton("📊 Характеристики"), KeyboardButton("🔙 Выйти из игры")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        game_text = f"🎮 **ИГРА НАЧАЛАСЬ**\n\n" \
                    f"👤 **Персонаж:** {name}\n\n" \
                    f"📖 **Ситуация:**\n{situation}\n\n" \
                    f"💭 Что вы хотите делать? Опишите своё действие или используйте меню."

        await update.message.reply_text(game_text, reply_markup=reply_markup, parse_mode='Markdown')
        return GAME_ACTION

    async def game_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text.strip()
        client = self.get_user_client(user_id)
        user_data = self.get_user_data(user_id)

        char_id = user_data.get('current_character_id')
        char_stats = user_data.get('character_stats', {})

        if text == "🎒 Инвентарь":
            return await self.show_inventory(update, context, char_id)
        elif text == "🧠 Память":
            return await self.show_memory(update, context, char_id)
        elif text == "📊 Характеристики":
            return await self.show_stats(update, context, char_stats)
        elif text == "🔙 Выйти из игры":
            await update.message.reply_text("👋 Выход из игры.")
            await self.show_main_menu(update, context)
            return MAIN_MENU

        # Обрабатываем игровое действие
        await update.message.reply_text("🎲 Обработка действия...")

        # Вычисляем вероятность
        probability = self.calculate_probability(text, char_stats)

        # Бросаем кубик
        result, roll = self.roll_dice(probability)

        # Генерируем результат
        system_prompt = f"""Ты мастер RPG игры. Игрок пытается выполнить действие.

Результат броска: {result} (бросок {roll} при вероятности {probability}%)

Опиши что происходит. Будь креативным и детальным.
Пиши живо на русском языке."""

        # Получаем недавние события для контекста
        memory = EventMemory(self.db)
        recent_events = memory.get_recent_events(char_id, 3)
        context_text = "Недавние события:\n" + "\n".join([f"- {e['description'][:100]}..." for e in recent_events])

        outcome_prompt = f"{context_text}\n\nИгрок: {text}\nРезультат: {result} ({roll}/100)\nОпиши что происходит:"
        outcome = client.generate(outcome_prompt, system_prompt)

        if "❌" in outcome:
            outcome = f"Ваша попытка '{text}' завершается с результатом: {result}"

        # Сохраняем событие
        importance = 3 if "критический" in result else 2 if "успех" in result else 1
        memory.add_event(char_id, "действие игрока", f"Действие: {text}. {outcome}", importance, ["действие"])

        # Отправляем результат
        result_text = f"🎲 **РЕЗУЛЬТАТ ДЕЙСТВИЯ**\n\n" \
                      f"📝 **Действие:** {text}\n" \
                      f"🎯 **Вероятность:** {probability}%\n" \
                      f"🎲 **Бросок:** {roll} - **{result.upper()}**\n\n" \
                      f"📖 **Что происходит:**\n{outcome}\n\n" \
                      f"💭 Что дальше?"

        await update.message.reply_text(result_text, parse_mode='Markdown')

        # Проверяем предметы
        if any(word in outcome.lower() for word in ['находишь', 'получаешь', 'берёшь']):
            await update.message.reply_text(
                "🎒 В результате действия вы можете получить предмет. Напишите название или 'пропуск'")

        return GAME_ACTION

    def calculate_probability(self, action: str, stats: Dict) -> int:
        """Вычисляет вероятность успеха действия"""
        base = 50
        action_lower = action.lower()

        if any(word in action_lower for word in ['атака', 'удар', 'сила', 'сломать']):
            modifier = (stats.get('сила', 10) - 10) * 3
        elif any(word in action_lower for word in ['скрытность', 'ловкость', 'уклонение']):
            modifier = (stats.get('ловкость', 10) - 10) * 3
        elif any(word in action_lower for word in ['магия', 'изучить', 'знание']):
            modifier = (stats.get('интеллект', 10) - 10) * 3
        elif any(word in action_lower for word in ['восприятие', 'заметить']):
            modifier = (stats.get('мудрость', 10) - 10) * 3
        elif any(word in action_lower for word in ['убеждение', 'обман']):
            modifier = (stats.get('харизма', 10) - 10) * 3
        else:
            modifier = 0

        return max(5, min(95, base + modifier))

    def roll_dice(self, probability: int) -> tuple:
        """Бросает кубик и определяет результат"""
        roll = random.randint(1, 100)

        if roll <= 5:
            return "критический провал", roll
        elif roll <= 35:
            return "провал", roll
        elif roll <= 65:
            return "частичный успех", roll
        elif roll <= 90:
            return "успех", roll
        else:
            return "критический успех", roll

    # === ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===

    async def show_inventory(self, update: Update, context: ContextTypes.DEFAULT_TYPE, char_id: int):
        inventory = GameInventory(self.db, char_id)
        items = inventory.get_inventory()

        if items:
            text = "🎒 **ИНВЕНТАРЬ**\n\n"
            for item in items:
                text += f"📦 **{item['name']}** (x{item['quantity']})\n   {item['description']}\n\n"
        else:
            text = "🎒 **ИНВЕНТАРЬ ПУСТ**"

        await update.message.reply_text(text, parse_mode='Markdown')
        return GAME_ACTION

    async def show_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE, char_id: int):
        memory = EventMemory(self.db)
        events = memory.get_recent_events(char_id, 5)

        if events:
            text = "🧠 **НЕДАВНИЕ СОБЫТИЯ**\n\n"
            for event in events:
                text += f"📅 **[{event['type']}]**\n{event['description'][:150]}...\n\n"
        else:
            text = "🧠 **СОБЫТИЙ НЕТ**"

        await update.message.reply_text(text, parse_mode='Markdown')
        return GAME_ACTION

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE, stats: Dict):
        text = "📊 **ХАРАКТЕРИСТИКИ**\n\n"
        for stat, value in stats.items():
            text += f"⚡ **{stat.capitalize()}:** {value}\n"

        await update.message.reply_text(text, parse_mode='Markdown')
        return GAME_ACTION

    async def show_diagnostics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        client = self.get_user_client(user_id)

        if not client:
            await update.message.reply_text("❌ ИИ не подключен!")
            return MAIN_MENU

        provider = "Ollama" if isinstance(client, OllamaClient) else "OpenRouter"

        # Тест соединения
        connection_ok = client.check_connection()

        # Тест генерации
        test_result = client.generate("Скажи 'тест'", "Отвечай одним словом")
        generation_ok = "❌" not in test_result

        text = f"🔧 **ДИАГНОСТИКА СИСТЕМЫ**\n\n" \
               f"🤖 **Провайдер:** {provider}\n" \
               f"📡 **Соединение:** {'✅ OK' if connection_ok else '❌ Ошибка'}\n" \
               f"🧪 **Генерация:** {'✅ OK' if generation_ok else '❌ Ошибка'}\n" \
               f"🎯 **Модель:** `{client.model}`\n\n"

        if generation_ok:
            text += f"📝 **Тест:** {test_result}"

        await update.message.reply_text(text, parse_mode='Markdown')
        await self.show_main_menu(update, context)
        return MAIN_MENU

    # === ДОПОЛНИТЕЛЬНЫЕ МЕТОДЫ ===

    async def show_manage_characters(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🗂️ Управление персонажами пока не реализовано в боте.")
        await self.show_main_menu(update, context)
        return MAIN_MENU

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ Операция отменена. Используйте /start для начала.")
        return ConversationHandler.END


# === ЗАПУСК БОТА ===

def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Установите токен бота в переменной BOT_TOKEN!")
        return

    # Создаем бота
    bot = TelegramRPGBot()

    # Создаем приложение
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Настраиваем ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', bot.start)],
        states={
            CHOOSING_PROVIDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.choose_provider)],
            OPENROUTER_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.openrouter_key)],
            MODEL_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.select_model)],
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.main_menu)],
            CHAR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.char_name)],
            CHAR_CONCEPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.char_concept)],
            CHAR_QUESTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.char_questions)],
            SELECT_CHARACTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.select_character)],
            MANAGE_CHARACTERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.show_manage_characters)],
            SETTING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.show_manage_characters)],
            GAME_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.game_action)],
        },
        fallbacks=[CommandHandler('cancel', bot.cancel)]
    )

    application.add_handler(conv_handler)

    print("🤖 Телеграм бот запущен!")
    print("🔑 Не забудьте установить токен в BOT_TOKEN")

    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
