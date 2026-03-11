# CLAUDE.md — Crypto Signal Bot

## КОНЦЕПЦИЯ

Telegram-бот который круглосуточно мониторит крипторынок и присылает сигналы:
**когда покупать, когда продавать, и почему** — с данными, индикаторами и AI-комментарием.

Тишина → сигнал → доказательства → решай сам.

Один бот. Одна задача. Никакого шума.

---

## КРИТИЧЕСКИЕ ОГРАНИЧЕНИЯ

```
ЗАПРЕЩЕНО:
  ✗ Streamlit, Flask, FastAPI, любой веб-фреймворк
  ✗ Веб-интерфейс, дашборд, UI
  ✗ Платные API (только бесплатные)
  ✗ Binance API ключи (только публичные эндпоинты)
  ✗ numpy, pandas (overkill — чистый Python)
  ✗ google-generativeai SDK (синхронный, тяжёлый — только REST)

ОБЯЗАТЕЛЬНО:
  ✓ Фоновый процесс: python -m src.main
  ✓ Интерфейс ТОЛЬКО через Telegram
  ✓ Дисклеймер в КАЖДОМ сигнале
  ✓ Бот НИКОГДА не падает — логирует ошибки и продолжает
  ✓ Если Gemini/F&G/любой API недоступен — бот работает без него
```

---

## АРХИТЕКТУРА

```
crypto-signal-bot/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── config.yaml
├── config.example.yaml
├── .env.example
├── .gitignore
├── setup.sh                     # автонастройка сервера
│
├── src/
│   ├── __init__.py
│   ├── main.py                  # asyncio orchestrator
│   ├── config.py                # Pydantic конфиг
│   ├── logger.py                # структурное логирование
│   │
│   ├── market/                  # СБОР ДАННЫХ
│   │   ├── __init__.py
│   │   ├── binance.py           # цены, свечи, объёмы (публичный API)
│   │   ├── fear_greed.py        # Fear & Greed Index
│   │   ├── indicators.py        # RSI, SMA, EMA, volume ratio
│   │   └── store.py             # SQLite хранилище
│   │
│   ├── strategy/                # МОЗГ
│   │   ├── __init__.py
│   │   ├── scorer.py            # скоринг RSI + F&G + SMA + Volume
│   │   ├── engine.py            # сборка данных → оценка → сигнал
│   │   └── cooldown.py          # защита от спама
│   │
│   ├── backtest/                # ДОКАЗАТЕЛЬСТВО
│   │   ├── __init__.py
│   │   ├── loader.py            # загрузка исторических данных
│   │   ├── runner.py            # прогон стратегии на истории
│   │   └── metrics.py           # win rate, drawdown, sharpe
│   │
│   ├── ai/                      # КОММЕНТАРИЙ
│   │   ├── __init__.py
│   │   ├── gemini.py            # Gemini Flash REST клиент
│   │   └── prompts.py           # системные промпты
│   │
│   └── telegram/                # ДОСТАВКА
│       ├── __init__.py
│       ├── bot.py               # бот, регистрация handlers
│       ├── handlers.py          # обработчики команд
│       ├── formatter.py         # форматирование сигналов
│       └── charts.py            # графики
│
├── tests/
│   ├── __init__.py
│   ├── test_indicators.py       # RSI, SMA на известных данных
│   ├── test_scorer.py           # все комбинации скоринга
│   ├── test_engine.py           # сборка snapshot, генерация сигналов
│   ├── test_cooldown.py         # кулдаун, сброс при смене направления
│   ├── test_backtest.py         # честность бэктеста, метрики
│   └── test_formatter.py        # форматирование сообщений
│
└── data/                        # runtime (gitignored)
    └── .gitkeep
```

---

## ВНЕШНИЕ API (все бесплатные, без ключей)

| API | Эндпоинт | Лимит | Что берём |
|-----|----------|-------|-----------|
| Binance | `/api/v3/ticker/price` | ~1200/мин | Текущие цены |
| Binance | `/api/v3/klines` | ~1200/мин | Свечи (история + RSI + SMA) |
| Binance | `/api/v3/ticker/24hr` | ~1200/мин | Объём, 24ч хай/лоу |
| Alternative.me | `/fng/?limit=1` | без лимита | Fear & Greed Index |
| Alternative.me | `/fng/?limit=365` | без лимита | F&G история (для бэктеста) |
| Gemini Flash | `generativelanguage.googleapis.com` | 15 RPM | AI-комментарии |

Gemini Flash требует API ключ (бесплатный, получить на https://aistudio.google.com/apikey).
Если ключ не задан — бот работает без AI-комментариев.

---

## ФАЗА 1: Инфраструктура

### 1.1 — Конфиг (config.py)

```python
from pydantic import BaseModel
from pydantic_settings import BaseSettings

class StrategyParams(BaseModel):
    rsi_period: int = 14
    rsi_oversold: float = 30
    rsi_overbought: float = 70
    fg_fear: int = 25
    fg_greed: int = 75
    sma_period: int = 200
    volume_spike: float = 1.5
    weight_rsi: float = 0.35
    weight_fg: float = 0.25
    weight_sma: float = 0.25
    weight_volume: float = 0.15
    min_confidence: float = 0.3
    cooldown_hours: int = 8
    strong_cooldown_hours: int = 4

class BacktestParams(BaseModel):
    default_days: int = 365
    initial_capital: float = 10000
    position_size_pct: float = 10
    commission_pct: float = 0.1
    cache_refresh_hours: int = 24

class Config(BaseSettings):
    telegram_token: str
    telegram_chat_id: str
    gemini_api_key: str = ""
    coins: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    check_interval_sec: int = 300
    signal_interval_sec: int = 3600
    strategy: StrategyParams = StrategyParams()
    backtest: BacktestParams = BacktestParams()
    db_path: str = "data/signals.db"
    log_level: str = "INFO"
    timezone: str = "Asia/Jerusalem"
```

- Загрузка: `config.yaml` → переопределение env vars (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`)
- `config.example.yaml` с комментариями на русском
- `.env.example` с плейсхолдерами
- **Критерий:** Валидация при старте; понятная ошибка при отсутствии обязательных полей

### 1.2 — Логирование (logger.py)

- Формат: `[%(asctime)s] %(levelname)s | %(name)s | %(message)s`
- stdout + файл `data/bot.log` (RotatingFileHandler, 5MB, 3 бэкапа)
- **Критерий:** Логи в консоли и файле

### 1.3 — Хранилище (store.py)

```python
class MarketStore:
    async def init_db(self)
    async def save_price(self, symbol: str, price: float, volume: float, ts: datetime)
    async def save_candles(self, symbol: str, interval: str, candles: list[Candle])
    async def get_hourly_closes(self, symbol: str, count: int) -> list[float]
    async def get_daily_closes(self, symbol: str, days: int) -> list[float]
    async def get_daily_volumes(self, symbol: str, days: int) -> list[float]
    async def get_latest_price(self, symbol: str) -> float | None
    async def get_record_count(self) -> int
    async def cleanup(self, keep_days: int = 90)
    async def close(self)
```

- Таблицы: `prices` (тик каждые 5 мин), `candles` (часовые/дневные свечи)
- Индексы: (symbol, timestamp), (symbol, interval, timestamp)
- **Критерий:** Запись и чтение 200 дней < 50мс

### 1.4 — Проект

- `pyproject.toml`, `.gitignore`, `data/.gitkeep`
- **Критерий:** `pip install -e .` работает

---

## ФАЗА 2: Сбор данных

### 2.1 — Binance клиент (binance.py)

```python
class BinanceClient:
    async def get_all_prices(self, symbols: list[str]) -> dict[str, float]
    async def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]
    async def get_24h_stats(self, symbol: str) -> TickerStats
    async def close(self)

@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class TickerStats:
    volume: float
    quote_volume: float
    price_change_pct: float
    high_24h: float
    low_24h: float
```

- Retry: 3 попытки, exponential backoff
- Таймаут: 10 сек
- **Критерий:** Получение цен 5 монет < 1 сек

### 2.2 — Fear & Greed (fear_greed.py)

```python
class FearGreedIndex:
    async def get_current(self) -> int | None
    async def refresh(self)          # принудительное обновление (для /check)
    async def get_history(self, days: int) -> list[tuple[datetime, int]]
    async def close(self)
```

- Кэш: 30 минут (refresh() игнорирует кэш)
- **Критерий:** Значение 0-100 или None при ошибке

### 2.3 — Индикаторы (indicators.py)

```python
class Indicators:
    @staticmethod
    def rsi(closes: list[float], period: int = 14) -> float | None

    @staticmethod
    def sma(closes: list[float], period: int = 200) -> float | None

    @staticmethod
    def ema(closes: list[float], period: int = 50) -> float | None

    @staticmethod
    def volume_ratio(volumes: list[float], period: int = 20) -> float | None
        """Последний объём / средний за period. >1.5 = аномальный."""

    @staticmethod
    def crossed_sma(closes: list[float], sma: float, lookback: int = 5) -> str | None
        """Пересечение SMA за последние N свечей. Возвращает 'up'/'down'/None."""
```

- Чистый Python, без numpy/pandas
- RSI: классическая формула (Wilder's smoothing)
- **Критерий:** Тесты на известных данных; RSI(14) на 200 точках < 1мс

### 2.4 — Начальная загрузка при старте

При первом запуске (БД пустая или мало данных):
1. Загрузить 200 дневных свечей для каждой монеты (для SMA(200))
2. Загрузить 24ч часовых свечей (для RSI)
3. Сохранить в store

Это гарантирует что стратегия работает с первой минуты.
- **Критерий:** После старта в БД достаточно данных для SMA(200) и RSI(14)

---

## ФАЗА 3: Стратегия

### 3.1 — Скоринг (scorer.py)

```python
@dataclass
class MarketSnapshot:
    symbol: str
    price: float
    rsi: float | None
    sma_200: float | None
    ema_50: float | None
    fear_greed: int | None
    volume_ratio: float | None
    change_24h_pct: float | None
    timestamp: datetime

@dataclass
class ScoreBreakdown:
    rsi_score: float             # -1.0 до +1.0
    rsi_value: float | None
    rsi_label: str               # "перепродан", "нейтрально", "перекуплен"
    rsi_hit: bool                # условие выполнено?

    fg_score: float
    fg_value: int | None
    fg_label: str
    fg_hit: bool

    sma_score: float
    sma_value: float | None
    sma_label: str               # "выше тренда", "ниже тренда", "пересечение вверх"
    sma_hit: bool

    vol_score: float
    vol_ratio: float | None
    vol_label: str               # "подтверждение ×1.8", "нормальный"
    vol_hit: bool

    total_score: float           # взвешенная сумма
    hits: int                    # сколько ✅ из 4
    confidence_bar: str          # "██████░░░░"

class Scorer:
    def __init__(self, params: StrategyParams)
    def score(self, snap: MarketSnapshot) -> ScoreBreakdown
```

**Скоринг:**

```
RSI (вес 0.35):
  ≤ 20 → +1.0    ≤ 30 → +0.5    30-70 → 0.0    ≥ 70 → -0.5    ≥ 80 → -1.0

Fear & Greed (вес 0.25, contrarian — покупай когда боятся):
  ≤ 15 → +1.0    ≤ 25 → +0.5    25-75 → 0.0    ≥ 75 → -0.5    ≥ 85 → -1.0

SMA(200) (вес 0.25):
  Пересёк снизу вверх (5д) → +1.0
  Цена > SMA → +0.3
  Пересёк сверху вниз (5д) → -1.0
  Цена < SMA → -0.3

Volume (вес 0.15, подтверждающий — усиливает направление):
  ratio > 2.0 и остальные > 0 → +0.5
  ratio > 2.0 и остальные < 0 → -0.5
  ratio > 1.5 → ±0.3 (в сторону основного сигнала)
  иначе → 0.0
```

**confidence_bar** — визуальная шкала:
```python
def confidence_bar(score: float) -> str:
    filled = round(abs(score) * 10)
    return "█" * filled + "░" * (10 - filled)
# Пример: score=0.65 → "██████░░░░"
```

- **Критерий:** RSI=25, F&G=18, ниже SMA, объём ×1.8 → score ≈ +0.58 (STRONG_BUY)

### 3.2 — Движок (engine.py)

```python
class SignalType(Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"

@dataclass
class Signal:
    type: SignalType
    symbol: str
    price: float
    breakdown: ScoreBreakdown
    backtest_summary: str | None    # "Win Rate: 67% | Ср. +4.2%"
    ai_comment: str | None
    timestamp: datetime

class StrategyEngine:
    def __init__(self, scorer, store, binance, fear_greed, indicators)

    async def build_snapshot(self, symbol: str) -> MarketSnapshot
        """Собрать все данные для скоринга одной монеты."""

    async def evaluate(self, symbol: str) -> Signal
        """Оценить одну монету → сигнал."""

    async def evaluate_all(self) -> list[Signal]
        """Оценить все монеты."""

    async def force_check(self, symbol: str | None = None) -> list[Signal]
        """Принудительная проверка (для /check). Обновляет данные, игнорирует кулдаун."""
```

**Маппинг:**
```
score ≥ +0.6  → STRONG_BUY
score ≥ +0.3  → BUY
-0.3 < score  → NEUTRAL
score ≤ -0.3  → SELL
score ≤ -0.6  → STRONG_SELL
```

- **Критерий:** evaluate() возвращает корректный Signal со всеми данными

### 3.3 — Кулдаун (cooldown.py)

```python
class Cooldown:
    def __init__(self, normal_hours: int = 8, strong_hours: int = 4)
    def can_send(self, symbol: str, signal_type: SignalType) -> bool
    def record(self, symbol: str, signal_type: SignalType)
    def reset(self, symbol: str)      # при смене направления
    def get_status(self, symbol: str) -> dict   # для /debug
```

- BUY/SELL: не чаще раз в 8ч по одной монете
- STRONG_BUY/STRONG_SELL: не чаще раз в 4ч
- Смена направления (BUY → SELL): кулдаун сбрасывается сразу
- /check игнорирует кулдаун
- **Критерий:** Нет спама; смена направления проходит мгновенно

---

## ФАЗА 4: Бэктест

### 4.1 — Загрузка исторических данных (loader.py)

```python
class HistoricalLoader:
    async def load_candles(self, symbol: str, interval: str, days: int) -> list[Candle]
    async def load_fear_greed(self, days: int) -> list[tuple[datetime, int]]
```

- Binance klines пачками по 1000, пауза 200мс
- F&G: один запрос `?limit=365`
- Кэш в SQLite — не загружать повторно
- **Критерий:** 365 дней BTC дневных свечей < 5 сек

### 4.2 — Прогон бэктеста (runner.py)

```python
@dataclass
class BacktestResult:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl_pct: float
    max_drawdown_pct: float
    avg_trade_pnl_pct: float
    best_trade_pnl_pct: float
    worst_trade_pnl_pct: float
    sharpe: float | None
    hodl_pnl_pct: float
    vs_hodl: float               # стратегия минус HODL
    equity_curve: list[tuple[datetime, float]]
    trades: list[BacktestTrade]

class BacktestRunner:
    def __init__(self, scorer: Scorer)
    async def run(self, symbol: str, days: int, config: BacktestParams) -> BacktestResult
```

**Правила:**
- Вход по close свечи (без look-ahead)
- Комиссия 0.1% на каждую сделку
- Размер позиции: % от ТЕКУЩЕГО капитала
- Макс одновременных позиций: 3
- SMA(200) не считается если < 200 свечей — SMA score = 0
- F&G: ближайшее дневное значение
- Сравнение с HODL обязательно
- **Критерий:** 365 дней < 3 сек; результаты корректны

### 4.3 — Метрики (metrics.py)

```python
class Metrics:
    @staticmethod
    def win_rate(trades) -> float
    @staticmethod
    def max_drawdown(equity_curve) -> float
    @staticmethod
    def sharpe_ratio(returns, risk_free=0.04) -> float
    @staticmethod
    def profit_factor(trades) -> float
```

### 4.4 — Кэширование бэктеста

- Результаты бэктеста кэшируются в SQLite (таблица `backtest_cache`)
- Обновляются раз в 24 часа автоматически
- Краткая строка из кэша вставляется в каждый сигнал: `"Win Rate: 67% | Ср. +4.2%"`
- `/backtest` запускает свежий прогон (не из кэша)
- **Критерий:** Сигналы содержат актуальную статистику стратегии

---

## ФАЗА 5: AI-комментарий

### 5.1 — Gemini клиент (gemini.py)

```python
class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash")
    async def generate(self, prompt: str, system: str, temperature: float = 0.7, max_tokens: int = 512) -> str | None
    async def close(self)
```

- REST API: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}`
- Retry: 2 попытки
- Rate limit: 15 RPM (простой счётчик + asyncio.sleep)
- Таймаут: 15 сек
- Нет ключа → None, бот работает без AI
- **Критерий:** Ответ или None, никогда не бросает exception наружу

### 5.2 — Промпты (prompts.py)

```python
SIGNAL_SYSTEM = """
Ты — лаконичный криптоаналитик. 2-3 предложения на русском.

Тебе дают сигнал стратегии с данными. Объясни:
1. Что говорят индикаторы вместе
2. Один конкретный нюанс или риск

НЕЛЬЗЯ: "купи", "продай", "инвестируй", "рекомендую", "советую"
МОЖНО: "данные указывают", "исторически", "стоит обратить внимание"
Максимум 3 предложения. Чистый текст без markdown.
"""
```

**Промпт для сигнала** формируется динамически:
```
Сигнал: {BUY/SELL} для {BTC}
Score: {+0.45}
RSI(14) = {28} — {перепродан}
Fear & Greed = {22} — {Extreme Fear}
Цена ${69,500}, SMA(200) = ${72,300} — {ниже тренда}
Объём ×{1.8} среднего
24ч: {-4.3%}
Бэктест: Win Rate {67%}, средняя сделка {+4.2%}
```

---

## ФАЗА 6: Telegram

### 6.1 — Форматирование (formatter.py)

**Автоматический сигнал (STRONG_BUY):**
```
🟢🟢 ПОКУПКА — BTC

💰 $69,500

📊 Почему:
  ✅ RSI(14) = 25 — перепродан
  ✅ Fear & Greed = 18 — паника
  ❌ Ниже SMA(200) $72,300
  ✅ Объём ×1.8 — подтверждение

Сила: ██████░░░░ 65%

📈 Стратегия (365д): 67% в плюс | Ср. +4.2%

🤖 Перепроданность при экстремальном страхе и
повышенном объёме — типичный паттерн разворота.
Позиция ниже SMA(200) добавляет риск.

⚠️ Анализ данных, не финансовый совет.
```

**Автоматический сигнал (STRONG_SELL):**
```
🔴🔴 ПРОДАЖА — BTC

💰 $85,200

📊 Почему:
  ✅ RSI(14) = 82 — перекуплен
  ✅ Fear & Greed = 88 — эйфория
  ✅ Выше SMA(200) на +18%
  ✅ Объём ×2.1

Сила: █████████░ 90%

📈 Стратегия (365д): 67% в плюс | Ср. +4.2%

🤖 Все индикаторы в зоне перегрева.
Коррекция 10-15% вероятна.

⚠️ Анализ данных, не финансовый совет.
```

**Ответ на /check (все монеты, включая нейтральные):**
```
🔍 Проверка — 11.03.2026 15:42

🟢 BTC: BUY (+0.42)
  RSI=28 ✅ | F&G=22 ✅ | <SMA ❌ | Vol ×1.3
⚪ ETH: NEUTRAL (+0.08)
  RSI=51 | F&G=22 ✅ | >SMA ✅ | Vol ×0.9
⚪ SOL: NEUTRAL (-0.11)
  RSI=55 | F&G=22 ✅ | <SMA ❌ | Vol ×0.7
⚪ BNB: NEUTRAL (+0.15)
  RSI=44 | F&G=22 ✅ | >SMA ✅ | Vol ×1.0
🔴 XRP: SELL (-0.38)
  RSI=74 ❌ | F&G=22 ✅ | >SMA ✅ | Vol ×2.1 ✅
```
Если есть сигналы выше порога — после сводки отправить полноформатный сигнал с AI-комментарием.

**Ответ на /health:**
```
🏥 Статус

✅ Binance — ок (120мс)
✅ Fear & Greed — 22 (кэш 12м назад)
✅ Gemini — ок (850мс)  [или ⚠️ нет ключа]
✅ SQLite — 14,352 записей
⏱ Uptime: 3д 14ч 22мин
🔔 Сигналов за 24ч: 1 | За неделю: 4
```

**Ответ на /debug BTC:**
```
🔬 BTC — 11.03.2026 15:42

💰 $69,500

Данные:
  RSI(14): 28.3
  SMA(200): $72,318
  EMA(50): $71,450
  Цена/SMA: 96.1%
  F&G: 22
  Vol 24h: $28.5B | Avg: $21.2B | Ratio: 1.34x

Скоринг:
  RSI:  +0.50 × 0.35 = +0.175
  F&G:  +0.50 × 0.25 = +0.125
  SMA:  -0.30 × 0.25 = -0.075
  Vol:  +0.30 × 0.15 = +0.045
  ───────────────────
  ИТОГО:         +0.270

Результат: NEUTRAL (порог ±0.30)
До BUY: +0.030 | До SELL: -0.570
Кулдаун: свободен
```

**Ответ на /backtest BTC 365:**
```
📊 Бэктест: BTC (365 дней)
Капитал: $10,000 | Комиссия: 0.1%

Сделок: 18 (12 🟢 / 6 🔴)
Win Rate: 66.7%
P&L: +$2,340 (🟢 +23.4%)
Просадка: -8.2%
Ср. сделка: +1.3%
Лучшая: +8.9% | Худшая: -3.2%

vs HODL: +15.1%
Стратегия лучше на +8.3% ✅

⚠️ Результаты на истории НЕ гарантируют будущее.
```

### 6.2 — Команды бота (handlers.py)

| Команда | Что делает |
|---------|------------|
| `/start` | Приветствие: что делает бот, как работает, список команд |
| `/check` | **Принудительная проверка ВСЕХ монет прямо сейчас.** Обновляет данные, игнорирует кулдаун, показывает все (включая neutral). Главная команда для тестирования. |
| `/check BTC` | Принудительная проверка одной монеты с полным сигналом |
| `/signal` | Текущие сигналы (без обновления данных, из последнего цикла) |
| `/signal BTC` | Сигнал по одной монете |
| `/backtest BTC 365` | Бэктест стратегии. По умолчанию 365 дней. |
| `/health` | Статус всех компонентов, uptime, кол-во сигналов |
| `/debug BTC` | Полный дамп: сырые данные, скоринг, кулдаун |
| `/coins` | Список отслеживаемых монет |
| `/add DOGEUSDT` | Добавить монету |
| `/remove DOGEUSDT` | Убрать монету |
| `/params` | Текущие параметры стратегии |
| `/help` | Список команд |

Все команды — только от разрешённого chat_id.

### 6.3 — Графики (charts.py)

```python
class SignalChart:
    def generate(self, signal: Signal, candles: list[Candle]) -> bytes | None
```

Один тип графика на все случаи:
- Линия цены (24ч или 7д в зависимости от данных)
- SMA(200): тонкая оранжевая пунктирная
- Маркер сигнала: ▲ зелёный (BUY) или ▼ красный (SELL) в точке текущей цены
- RSI subplot внизу (20% высоты): линия RSI + пунктиры на 30 и 70
- Тёмный фон (#1a1a2e), цвет линии зависит от монеты

**ПРАВИЛА Y-ОСИ:**
1. Масштаб ТОЛЬКО по данным цен (±0.2%)
2. SMA рисуется только если попадает в видимый диапазон
3. ЗАПРЕЩЕНО растягивать ось до SMA
4. Линия цены занимает ~80% высоты

- Размер: 800×500, DPI 100
- **Критерий:** График читаем на телефоне; RSI subplot информативен

---

## ФАЗА 7: Оркестрация

### 7.1 — Main loop (main.py)

```python
async def main():
    config = load_config()
    setup_logging(config.log_level)

    # Инициализация
    store = MarketStore(config.db_path)
    binance = BinanceClient()
    fg = FearGreedIndex()
    indicators = Indicators()
    scorer = Scorer(config.strategy)
    engine = StrategyEngine(scorer, store, binance, fg, indicators)
    cooldown = Cooldown(config.strategy.cooldown_hours, config.strategy.strong_cooldown_hours)
    gemini = GeminiClient(config.gemini_api_key) if config.gemini_api_key else None
    bot = TelegramBot(config, engine, cooldown, gemini, store, binance, fg)

    await store.init_db()

    # Начальная загрузка (SMA(200) нужно 200 дней)
    log.info("Загрузка исторических данных...")
    for symbol in config.coins:
        candles = await binance.get_klines(symbol, "1d", 200)
        await store.save_candles(symbol, "1d", candles)
        hourly = await binance.get_klines(symbol, "1h", 24)
        await store.save_candles(symbol, "1h", hourly)
    log.info("Данные загружены")

    await bot.send_text("🤖 Signal Bot запущен\n/check — проверить сейчас")

    # Параллельные задачи
    await asyncio.gather(
        price_loop(config, binance, store),         # каждые 5 мин: цены
        signal_loop(config, engine, cooldown, gemini, bot, store),  # каждый час: сигналы
        backtest_cache_loop(config, scorer, store),  # раз в сутки: кэш бэктеста
        cleanup_loop(store),                         # раз в час: очистка
        bot.start_polling(),                         # Telegram
    )
```

**Graceful shutdown:** SIGINT/SIGTERM → закрыть сессии, БД, отправить "🔴 Bot остановлен".

### 7.2 — Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY src/ src/
COPY config.yaml .
RUN useradd -m bot
USER bot
CMD ["python", "-m", "src.main"]
```

```yaml
# docker-compose.yml
services:
  bot:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./config.yaml:/app/config.yaml:ro
    restart: unless-stopped
```

### 7.3 — setup.sh

Скрипт автонастройки сервера (Ubuntu 24.04 / Oracle Cloud):
1. apt update + python3.12 + docker
2. Интерактивный ввод TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY
3. Создание .env, config.yaml
4. venv + pip install
5. systemd сервис + enable + start
6. Проверка статуса
- Идемпотентный, цветной вывод, пропуск уже сделанных шагов

### 7.4 — README.md (на русском)

```
## Быстрый старт

1. cp .env.example .env
   # Заполни: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY

2. pip install -e .

3. python -m src.main

4. В Telegram: /check
```

- Как получить Telegram токен (@BotFather)
- Как получить chat_id (@userinfobot)
- Как получить Gemini API ключ (aistudio.google.com)
- Список команд
- Docker запуск
- Деплой на Oracle Cloud (ссылка на инструкцию)

### 7.5 — Тесты

- `pytest` + `pytest-asyncio`
- **Обязательные тесты:**
  - `test_indicators.py` — RSI, SMA, EMA на данных с известным результатом
  - `test_scorer.py` — все комбинации: strong_buy, buy, neutral, sell, strong_sell; объём усиливает; нет данных → score 0
  - `test_cooldown.py` — кулдаун работает; смена направления сбрасывает; /check игнорирует
  - `test_backtest.py` — нет look-ahead; комиссия учтена; HODL корректен
  - `test_engine.py` — build_snapshot собирает данные; evaluate возвращает Signal
  - `test_formatter.py` — формат сигнала содержит все секции
- Покрытие > 80%
- **Критерий:** `pytest` зелёный

---

## ТАЙМИНГИ И ТРИГГЕРЫ

| Что | Когда | Отправка в Telegram |
|-----|-------|---------------------|
| Сбор цен | Каждые 5 мин | Нет |
| Проверка стратегии | Каждые 60 мин | Да, если score ≥ 0.3 или ≤ -0.3 |
| Кулдаун обычный | 8 часов | — |
| Кулдаун сильный | 4 часа | — |
| Обновление бэктест-кэша | Раз в 24ч | Нет |
| Очистка БД | Раз в 60 мин | Нет |
| `/check` | По команде | Да, все монеты, игнорирует кулдаун |
| `/backtest` | По команде | Да, отчёт + графики |

---

## ПОРЯДОК РАЗРАБОТКИ

```
Фаза 1 (инфраструктура) → Фаза 2 (данные) → Фаза 3 (стратегия) →
Фаза 4 (бэктест) → Фаза 5 (AI) → Фаза 6 (Telegram) → Фаза 7 (оркестрация)
```

После каждой фазы: проверить запуск, запустить тесты.
Коммитить после каждой задачи.

---

## ЗАВИСИМОСТИ

```toml
[project]
name = "crypto-signal-bot"
version = "3.0.0"
requires-python = ">=3.12"
dependencies = [
    "aiohttp>=3.9",
    "aiosqlite>=0.20",
    "python-telegram-bot[all]>=21.0",
    "matplotlib>=3.8",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.0",
    "aioresponses>=0.7",
    "ruff>=0.3",
]
```
