#!/usr/bin/env bash
# Crypto Signal Bot — автонастройка сервера (Ubuntu 24.04)
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()  { echo -e "${GREEN}✓ $1${NC}"; }
info(){ echo -e "${YELLOW}→ $1${NC}"; }
err() { echo -e "${RED}✗ $1${NC}" >&2; }

echo "=============================="
echo "  Crypto Signal Bot Setup"
echo "=============================="
echo ""

# 1. System packages
info "Обновление системы..."
if ! command -v python3.12 &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y python3.12 python3.12-venv python3-pip git curl
    ok "Python 3.12 установлен"
else
    ok "Python 3.12 уже установлен"
fi

# 2. Docker
if ! command -v docker &>/dev/null; then
    info "Установка Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    ok "Docker установлен"
else
    ok "Docker уже установлен"
fi

# 3. Config
if [ ! -f .env ]; then
    info "Настройка конфига..."
    read -rp "Telegram Bot Token: " TOKEN
    read -rp "Telegram Chat ID: " CHAT_ID
    read -rp "Gemini API Key (Enter чтобы пропустить): " GEMINI_KEY

    cat > .env <<EOF
TELEGRAM_TOKEN=${TOKEN}
TELEGRAM_CHAT_ID=${CHAT_ID}
GEMINI_API_KEY=${GEMINI_KEY}
EOF
    ok ".env создан"

    if [ ! -f config.yaml ]; then
        cp config.example.yaml config.yaml
        ok "config.yaml создан из примера"
    fi
else
    ok ".env уже существует"
fi

# 4. Python env
if [ ! -d .venv ]; then
    info "Создание виртуального окружения..."
    python3.12 -m venv .venv
    .venv/bin/pip install --upgrade pip -q
    .venv/bin/pip install -e . -q
    ok "Зависимости установлены"
else
    ok "Виртуальное окружение уже существует"
fi

mkdir -p data
ok "Папка data создана"

# 5. Systemd service
SERVICE_FILE="/etc/systemd/system/crypto-bot.service"
if [ ! -f "$SERVICE_FILE" ]; then
    info "Создание systemd сервиса..."
    WORK_DIR=$(pwd)
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Crypto Signal Bot
After=network.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${WORK_DIR}
ExecStart=${WORK_DIR}/.venv/bin/python -m src.main
Restart=always
RestartSec=10
EnvironmentFile=${WORK_DIR}/.env

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable crypto-bot
    sudo systemctl start crypto-bot
    ok "Сервис запущен"
    systemctl status crypto-bot --no-pager
else
    ok "Сервис уже существует"
    sudo systemctl restart crypto-bot
    ok "Сервис перезапущен"
fi

echo ""
echo "=============================="
ok "Установка завершена!"
echo "Логи: journalctl -u crypto-bot -f"
echo "Статус: systemctl status crypto-bot"
echo "=============================="
