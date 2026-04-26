# 🧠 Recall

> AI-powered CLI command assistant for developers. Never forget a command again.

---

## What it does

Recall helps you find, understand, run, and automate CLI commands using plain English.  
Supports **Anthropic Claude**, **OpenAI**, and any **local model** (Ollama, LM Studio, etc.).

```bash
recall ask "squash last 3 commits"
recall explain "docker run -it --rm -v $(pwd):/app ubuntu bash"
recall run "git stash"
recall do "create a redis instance with redisinsight GUI"
recall change "setup postgres with pgadmin"   # edit the plan before running
```

---

## Installation

```bash
git clone https://github.com/yourusername/recall.git
cd recall
pip install -e .
```

---

## Configuration

Copy `.env.example` to `.env` and set one of the following:

```env
# Option 1: Anthropic Claude (default)
ANTHROPIC_API_KEY=your_key_here

# Option 2: Google Gemini
GEMINI_API_KEY=your_gemini_key
# RECALL_MODEL=gemini-2.0-flash   # optional, defaults to gemini-2.0-flash

# Option 3: OpenAI
OPENAI_API_KEY=sk-...
RECALL_MODEL=gpt-4o

# Option 4: Local model via Ollama
RECALL_API_BASE=http://localhost:11434/v1
RECALL_MODEL=llama3.2

# Option 5: LM Studio / Groq / any OpenAI-compatible API
RECALL_API_BASE=https://api.groq.com/openai/v1
RECALL_API_KEY=your_groq_key
RECALL_MODEL=llama3-8b-8192
```

---

## Commands

### Core

| Command | Description |
|---|---|
| `recall ask "<query>"` | Convert natural language to a shell command |
| `recall explain "<command>"` | Understand what a command does, with a breakdown |
| `recall save "<command>" --desc "..." --tags git,docker` | Save a command manually |
| `recall search "<query>"` | Search saved commands by keyword, tag, or tool |
| `recall list` | List all saved commands |
| `recall list --tool git` | Filter saved commands by tool |
| `recall delete <id>` | Delete a saved command by ID |
| `recall run <id or keyword>` | Run a saved command (or ask AI if not found) |

### Multi-step automation

| Command | Description |
|---|---|
| `recall do "<goal>"` | AI breaks goal into steps and executes them sequentially |
| `recall change "<goal>"` | Same as `do`, but lets you edit the plan before running |

**`recall do` / `recall change` step controls:**  
At each step you can type `r` (run), `s` (skip), or `a` (abort).

**`recall change` edit commands** (shown before execution):

| Edit command | Action |
|---|---|
| `e 2` | Edit step 2's command and title |
| `m 1 3` | Swap / move steps 1 and 3 |
| `d 2` | Delete step 2 |
| `a` | Add a new step at the end |
| `done` | Proceed to execution |

---

## Options

| Flag | Applies to | Description |
|---|---|---|
| `--save` / `-s` | `ask`, `explain` | Save result to library after displaying |
| `--yes` / `-y` | `run`, `do`, `change`, `delete` | Skip all confirmation prompts |
| `--tool` | `list` | Filter by tool name |

---

## Smart `run` behaviour

```bash
recall run 3                        # run saved command #3
recall run "stash"                  # search library, pick if multiple matches
recall run "install fastapi"        # not in library? AI generates + runs it
```

- Commands with `<placeholders>` prompt you to fill them in before executing.
- When AI returns alternatives, you can pick which one to run.
- Successful AI-generated commands can be saved to your library on the spot.

---

## Data

All saved commands are stored locally at `~/.recall/recall.db` (SQLite). Nothing leaves your machine.

---

Built with [Typer](https://typer.tiangolo.com) · [Rich](https://rich.readthedocs.io) · [Anthropic](https://anthropic.com) · [OpenAI](https://openai.com)
