#!/usr/bin/env bash

###############################################################################
# AUTO-UPDATE SCRIPT FOR GLAVNOE BOT
# Автоматически пулит изменения с GitHub и перезапускает бота
# Используется вместе с GitHub webhook или cron
###############################################################################

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Пути
BOT_DIR="/home/user/glavnoeauthorbot"
BRANCH="claude/fix-yandex-parsing-issues-1TFAw"
LOG_DIR="/var/log/glavnoe-bot"
LOG_FILE="$LOG_DIR/auto_update.log"
PID_FILE="/var/run/glavnoe-bot.pid"

# Убедимся, что директория для логов существует
mkdir -p "$LOG_DIR"

# Функция логирования
log_message() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

# Функция вывода в консоль (цветной)
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
    log_message "INFO" "$message"
}

###############################################################################
# STEP 1: Проверка что мы в правильной директории
###############################################################################
step_check_directory() {
    print_status "$BLUE" "→ Проверка директории..."

    if [ ! -d "$BOT_DIR" ]; then
        print_status "$RED" "✗ Директория $BOT_DIR не найдена!"
        log_message "ERROR" "Bot directory not found: $BOT_DIR"
        exit 1
    fi

    if [ ! -d "$BOT_DIR/.git" ]; then
        print_status "$RED" "✗ Это не git репозиторий!"
        log_message "ERROR" "Not a git repository: $BOT_DIR"
        exit 1
    fi

    print_status "$GREEN" "✓ Директория OK: $BOT_DIR"
    cd "$BOT_DIR"
}

###############################################################################
# STEP 2: Проверка текущей ветки
###############################################################################
step_check_branch() {
    print_status "$BLUE" "→ Проверка текущей ветки..."

    CURRENT_BRANCH=$(git branch --show-current)

    if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
        print_status "$YELLOW" "! Текущая ветка: $CURRENT_BRANCH (ожидается $BRANCH)"
        print_status "$YELLOW" "  Переключаюсь на $BRANCH..."
        git fetch origin "$BRANCH" 2>&1 | tee -a "$LOG_FILE"
        git checkout "$BRANCH" 2>&1 | tee -a "$LOG_FILE"
    fi

    print_status "$GREEN" "✓ Ветка: $BRANCH"
}

###############################################################################
# STEP 3: Пулим изменения с GitHub
###############################################################################
step_pull_changes() {
    print_status "$BLUE" "→ Пулим изменения с GitHub..."

    # Сохраняем информацию о текущем HEAD
    OLD_HEAD=$(git rev-parse HEAD)

    # Пулим с retry логикой
    if ! git pull origin "$BRANCH" 2>&1 | tee -a "$LOG_FILE"; then
        log_message "ERROR" "Failed to pull from origin"
        print_status "$RED" "✗ Ошибка при пуле из репозитория"
        exit 1
    fi

    # Проверяем были ли изменения
    NEW_HEAD=$(git rev-parse HEAD)

    if [ "$OLD_HEAD" = "$NEW_HEAD" ]; then
        print_status "$YELLOW" "ℹ Нет новых изменений"
        return 1
    else
        print_status "$GREEN" "✓ Новые изменения получены"
        echo "  Коммит: $OLD_HEAD → $NEW_HEAD"
        git log -1 --oneline | tee -a "$LOG_FILE"
        return 0
    fi
}

###############################################################################
# STEP 4: Проверка синтаксиса Python
###############################################################################
step_check_syntax() {
    print_status "$BLUE" "→ Проверка синтаксиса Python файлов..."

    local errors=0

    # Проверяем основные файлы
    for file in bot.py config.py; do
        if [ -f "$file" ]; then
            if ! python3 -m py_compile "$file" 2>&1 | tee -a "$LOG_FILE"; then
                log_message "ERROR" "Syntax error in $file"
                errors=$((errors + 1))
            fi
        fi
    done

    # Проверяем handlers
    if [ -d "handlers" ]; then
        for file in handlers/*.py; do
            if [ -f "$file" ]; then
                if ! python3 -m py_compile "$file" 2>&1 | tee -a "$LOG_FILE"; then
                    log_message "ERROR" "Syntax error in $file"
                    errors=$((errors + 1))
                fi
            fi
        done
    fi

    # Проверяем utils
    if [ -d "utils" ]; then
        for file in utils/*.py; do
            if [ -f "$file" ]; then
                if ! python3 -m py_compile "$file" 2>&1 | tee -a "$LOG_FILE"; then
                    log_message "ERROR" "Syntax error in $file"
                    errors=$((errors + 1))
                fi
            fi
        done
    fi

    if [ $errors -eq 0 ]; then
        print_status "$GREEN" "✓ Синтаксис OK"
        return 0
    else
        print_status "$RED" "✗ Найдено $errors ошибок синтаксиса"
        log_message "ERROR" "Found $errors syntax errors"
        return 1
    fi
}

###############################################################################
# STEP 5: Останавливаем старый процесс бота
###############################################################################
step_stop_bot() {
    print_status "$BLUE" "→ Останавливаем старый процесс бота..."

    # Ищем процесс бота несколькими способами
    local pids=$(pgrep -f "python.*bot.py" || true)

    if [ -z "$pids" ]; then
        print_status "$YELLOW" "ℹ Процесс бота не найден (может быть уже остановлен)"
        log_message "INFO" "Bot process not found"
        return 0
    fi

    for pid in $pids; do
        print_status "$YELLOW" "  Убиваем процесс $pid..."
        kill $pid || true
        sleep 1

        # Если всё ещё жив, убиваем с SIGKILL
        if kill -0 $pid 2>/dev/null; then
            kill -9 $pid || true
        fi
    done

    # Подождём немного
    sleep 2

    # Проверяем что процесс действительно умер
    if pgrep -f "python.*bot.py" > /dev/null; then
        print_status "$RED" "✗ Не удалось остановить бота"
        log_message "ERROR" "Failed to stop bot process"
        return 1
    else
        print_status "$GREEN" "✓ Бот остановлен"
        log_message "INFO" "Bot process stopped successfully"
        return 0
    fi
}

###############################################################################
# STEP 6: Проверка конфигурации (doctor.py)
###############################################################################
step_check_config() {
    print_status "$BLUE" "→ Проверка конфигурации..."

    if [ ! -f "scripts/doctor.py" ]; then
        print_status "$YELLOW" "ℹ Скрипт doctor.py не найден, пропускаем проверку"
        return 0
    fi

    if python3 "scripts/doctor.py" 2>&1 | tee -a "$LOG_FILE"; then
        print_status "$GREEN" "✓ Конфигурация OK"
        return 0
    else
        print_status "$RED" "✗ Ошибки конфигурации"
        log_message "ERROR" "Config check failed"
        return 1
    fi
}

###############################################################################
# STEP 7: Запускаем бота
###############################################################################
step_start_bot() {
    print_status "$BLUE" "→ Запускаем бота..."

    # Запускаем в фоне и сохраняем PID
    nohup python3 "$BOT_DIR/bot.py" > "$LOG_DIR/bot_output.log" 2>&1 &
    local bot_pid=$!

    echo $bot_pid > "$PID_FILE"

    # Даём боту время на инициализацию
    sleep 3

    # Проверяем что процесс жив
    if kill -0 $bot_pid 2>/dev/null; then
        print_status "$GREEN" "✓ Бот запущен (PID: $bot_pid)"
        log_message "INFO" "Bot started successfully (PID: $bot_pid)"
        return 0
    else
        print_status "$RED" "✗ Бот не смог запуститься"
        log_message "ERROR" "Bot failed to start"
        # Выводим последние строки лога
        tail -20 "$LOG_DIR/bot_output.log" | tee -a "$LOG_FILE"
        return 1
    fi
}

###############################################################################
# MAIN FLOW
###############################################################################
main() {
    echo ""
    print_status "$BLUE" "╔════════════════════════════════════════╗"
    print_status "$BLUE" "║   GLAVNOE BOT - AUTO UPDATE SCRIPT     ║"
    print_status "$BLUE" "╚════════════════════════════════════════╝"
    echo ""

    log_message "INFO" "========== AUTO UPDATE STARTED =========="

    # Выполняем шаги
    step_check_directory || exit 1
    step_check_branch || exit 1

    # Если нет новых изменений - выходим
    if ! step_pull_changes; then
        print_status "$GREEN" "✓ Обновление не требуется"
        log_message "INFO" "========== AUTO UPDATE COMPLETED (NO CHANGES) =========="
        exit 0
    fi

    # Проверяем синтаксис (обязательно)
    step_check_syntax || exit 1

    # Останавливаем бота
    step_stop_bot || exit 1

    # Проверяем конфигурацию
    step_check_config || exit 1

    # Запускаем бота
    step_start_bot || exit 1

    echo ""
    print_status "$GREEN" "╔════════════════════════════════════════╗"
    print_status "$GREEN" "║   ✓ ОБНОВЛЕНИЕ УСПЕШНО ЗАВЕРШЕНО      ║"
    print_status "$GREEN" "╚════════════════════════════════════════╝"
    echo ""

    log_message "INFO" "========== AUTO UPDATE COMPLETED SUCCESSFULLY =========="

    exit 0
}

# Запускаем main
main
