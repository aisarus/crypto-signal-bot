# Crypto Signal Bot

Telegram-бот для мониторинга крипторынка и генерации сигналов на основе технического анализа.

## Что делает

- Мониторит 5 монет (BTC, ETH, SOL, BNB, XRP) каждые 5 минут
- Каждый час оценивает рынок по 4 индикаторам: RSI, Fear & Greed, SMA(200), Объём
- Отправляет сигнал в Telegram когда несколько индикаторов совпадают
- Показывает статистику стратегии из бэктеста
- AI-комментарий через Gemini Flash (опционально)

## Быстрый старт

```bash
# 1. Клонировать и настроить
cp .env.example .env
# Заполни: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY

# 2. Установить зависимости
pip install -e .

# 3. Запустить
python -m src.main

# 4. В Telegram: /check
```

## Получить токены

**Telegram Bot Token** — напиши [@BotFather](https://t.me/BotFather), команда /newbot

**Telegram Chat ID** — напиши [@userinfobot](https://t.me/userinfobot)

**Gemini API Key** — [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (бесплатно)

## Команды

| Команда | Описание |
|---------|----------|
| `/check` | Принудительная проверка всех монет |
| `/check BTC` | Проверка одной монеты |
| `/signal` | Текущие сигналы |
| `/backtest BTC 365` | Бэктест стратегии |
| `/health` | Статус системы |
| `/debug BTC` | Детальный дамп данных |
| `/coins` | Список монет |
| `/add DOGE` | Добавить монету |
| `/remove DOGE` | Убрать монету |
| `/params` | Параметры стратегии |

## Docker

```bash
cp .env.example .env
# Заполни .env
docker compose up -d
docker compose logs -f
```

## Деплой на сервер (Ubuntu)

```bash
bash setup.sh
```

## Архитектура

- `src/market/` — получение данных: Binance API, Fear & Greed Index, индикаторы
- `src/strategy/` — скоринг и движок сигналов
- `src/backtest/` — бэктест на исторических данных
- `src/ai/` — AI-комментарии через Gemini Flash
- `src/telegram/` — бот, команды, форматирование

## Зависимости

Все API бесплатные, не требуют ключей (кроме Telegram и Gemini):
- Binance публичный API (цены, свечи)
- Alternative.me Fear & Greed Index
- Google Gemini Flash (опционально)
