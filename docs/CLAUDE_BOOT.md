# GLAVNOE BOT — CLAUDE BOOT (AUTO)

## 0) Repo snapshot
- Root: /root/glavnoe-bot
- Branch: master
- Head: a09b245 — feat: add meme to post menu + manual journal entries
- Status: ## master...origin/master [ahead 4]

## 1) What changed recently
### Last commits
a09b245 feat: add meme to post menu + manual journal entries
a531ad9 Add design doc: meme in post menu + manual journal entries
c5aa92a feat: add content journal + meme generation
9d7f68f Add design: content journal + memes feature
9d7b28a Add multi-client support with context management

### Diffstat (HEAD~1..HEAD)
 CONTEXT.md                                         |   5 +
 .../content_journal/apple_real_estate/journal.json |  11 +
 handlers/content_handler.py                        | 192 +++++++++++++++++-
 handlers/journal_handler.py                        | 224 +++++++++++++++++++++
 4 files changed, 431 insertions(+), 1 deletion(-)

### Changed files (HEAD~1..HEAD)
CONTEXT.md
data/content_journal/apple_real_estate/journal.json
handlers/content_handler.py
handlers/journal_handler.py

## 2) Project map (where to look)
### Handlers
- handlers/voice_handler.py
- handlers/focus_handler.py
- handlers/content_handler.py
- handlers/plan_handler.py
- handlers/journal_handler.py

### Utils
- utils/transcription.py
- utils/memory_store.py
- utils/history_index.py
- utils/anti_repeat.py
- utils/editor_pass.py
- utils/prompt_variations.py
- utils/markdown_escape.py

### Data
- data/memory/{client}/memory.json
- data/memory/{client}/history_index.json
- data/content_journal/{client}/journal.json

## 3) Golden rules (no nonsense)
- Не обсуждай "баги OpenAI" без **лога/трейса/исключения**.
- Если "не вижу изменения" — сначала проверяй:
  1) `pwd` (ты в нужном repo root?)
  2) `git status -sb` (ветка/изменения?)
  3) `git log -5 --oneline` (коммиты?)
  4) `git diff --stat HEAD~1..HEAD` (что менялось?)
- Если контекст переполнен — используй только этот файл + `git diff`.

## 4) Fast diagnostics (copy/paste)
```bash
pwd
git rev-parse --show-toplevel
git status -sb
git branch --show-current
git log -5 --oneline
git diff --stat HEAD~1..HEAD || true
```

## 5) Quick pointers
- Whisper: смотри `handlers/voice_handler.py` + `utils/transcription.py`
- Память: `data/memory/*` + `utils/memory_store.py` + `utils/history_index.py`
- Качество: `utils/editor_pass.py` + `utils/anti_repeat.py`
