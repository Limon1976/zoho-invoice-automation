#!/bin/bash

# Получаем путь к корню проекта (на уровень выше scripts/)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Активируем виртуальную среду
source "$PROJECT_ROOT/venv/bin/activate"

# Устанавливаем PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT/mcp_servers/mcp-memory-bank/src:$PYTHONPATH"

# Запускаем Memory Bank MCP Server
cd "$PROJECT_ROOT/mcp_servers/mcp-memory-bank"
python src/mcp_memory_bank/main.py 