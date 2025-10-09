#!/bin/bash
# Скрипт для просмотра всех документов анализа рефакторинга

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║         📚 ПРОСМОТР ДОКУМЕНТАЦИИ РЕФАКТОРИНГА                 ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

files=(
    "INDEX.md"
    "README_REFACTORING.md"
    "QUICK_SUMMARY.md"
    "REFACTORING_ANALYSIS.md"
    "COMPARISON_TABLE.md"
    "RECOVERY_PLAN.md"
)

for file in "${files[@]}"; do
    if [ -f "/workspace/$file" ]; then
        echo "✅ $file ($(wc -l < /workspace/$file) строк)"
        echo "   Первые 10 строк:"
        head -10 "/workspace/$file" | sed 's/^/   │ /'
        echo ""
    else
        echo "❌ $file - не найден"
    fi
done

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║ Чтобы прочитать полный файл: cat /workspace/FILENAME.md      ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
