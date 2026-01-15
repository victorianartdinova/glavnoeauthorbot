#!/usr/bin/env bash
set -euo pipefail

OUT="docs/CLAUDE_BOOT.md"
mkdir -p "$(dirname "$OUT")"
mkdir -p "scripts"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "UNKNOWN")"
BRANCH="$(git branch --show-current 2>/dev/null || echo "UNKNOWN")"
HEAD_HASH="$(git rev-parse --short HEAD 2>/dev/null || echo "UNKNOWN")"
HEAD_SUBJECT="$(git log -1 --pretty=%s 2>/dev/null || echo "UNKNOWN")"
STATUS_SHORT="$(git status -sb 2>/dev/null | head -n 1 || echo "UNKNOWN")"

LAST_COMMITS="$(git log -5 --oneline 2>/dev/null || true)"
DIFFSTAT="$(git diff --stat HEAD~1..HEAD 2>/dev/null || echo "No diffstat (maybe <2 commits)")"
CHANGED_FILES="$(git diff --name-only HEAD~1..HEAD 2>/dev/null || true)"

# Lightweight map (exists check)
map_line () {
  local path="$1"
  if [ -f "$path" ]; then
    echo "- $path"
  fi
}

HANDLERS_LIST="$(
  map_line "handlers/voice_handler.py"
  map_line "handlers/focus_handler.py"
  map_line "handlers/content_handler.py"
  map_line "handlers/plan_handler.py"
  map_line "handlers/journal_handler.py"
)"

UTILS_LIST="$(
  map_line "utils/transcription.py"
  map_line "utils/memory_store.py"
  map_line "utils/history_index.py"
  map_line "utils/anti_repeat.py"
  map_line "utils/editor_pass.py"
  map_line "utils/prompt_variations.py"
  map_line "utils/markdown_escape.py"
)"

DATA_HINTS="- data/memory/{client}/memory.json
- data/memory/{client}/history_index.json
- data/content_journal/{client}/journal.json"

cat > "$OUT" <<EOF
# GLAVNOE BOT — CLAUDE BOOT (AUTO)

## 0) Repo snapshot
- Root: $REPO_ROOT
- Branch: $BRANCH
- Head: $HEAD_HASH — $HEAD_SUBJECT
- Status: $STATUS_SHORT

## 1) What changed recently
### Last commits
$LAST_COMMITS

### Diffstat (HEAD~1..HEAD)
$DIFFSTAT

### Changed files (HEAD~1..HEAD)
$CHANGED_FILES

## 2) Project map (where to look)
### Handlers
$HANDLERS_LIST

### Utils
$UTILS_LIST

### Data
$DATA_HINTS

## 3) Golden rules (no nonsense)
- Не обсуждай "баги OpenAI" без **лога/трейса/исключения**.
- Если "не вижу изменения" — сначала проверяй:
  1) \`pwd\` (ты в нужном repo root?)
  2) \`git status -sb\` (ветка/изменения?)
  3) \`git log -5 --oneline\` (коммиты?)
  4) \`git diff --stat HEAD~1..HEAD\` (что менялось?)
- Если контекст переполнен — используй только этот файл + \`git diff\`.

## 4) Fast diagnostics (copy/paste)
\`\`\`bash
pwd
git rev-parse --show-toplevel
git status -sb
git branch --show-current
git log -5 --oneline
git diff --stat HEAD~1..HEAD || true
\`\`\`

## 5) Quick pointers
- Whisper: смотри \`handlers/voice_handler.py\` + \`utils/transcription.py\`
- Память: \`data/memory/*\` + \`utils/memory_store.py\` + \`utils/history_index.py\`
- Качество: \`utils/editor_pass.py\` + \`utils/anti_repeat.py\`
EOF

echo "✅ Boot updated: $OUT"
