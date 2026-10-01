#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import tty
import termios
import select

# Curated standard model list matching latest available models in September 2026
MODELS = [
    {
        "id": "claude-sonnet-5",
        "name": "Claude Sonnet 5",
        "desc": "Modelo balanceado, recomendado para tareas diarias"
    },
    {
        "id": "claude-fable-5",
        "name": "Claude Fable 5",
        "desc": "Modelo élite para razonamiento autónomo complejo"
    },
    {
        "id": "claude-opus-5",
        "name": "Claude Opus 5",
        "desc": "Máxima inteligencia para tareas de diseño and análisis"
    },
    {
        "id": "claude-haiku-4-5-20251001",
        "name": "Claude Haiku 4.5",
        "desc": "Modelo súper rápido y económico para tareas simples"
    },
    {
        "id": "anthropic/gemini/models/gemini-3.5-flash",
        "name": "Gemini 3.5 Flash",
        "desc": "Modelo rápido de Google, excelente rendimiento general"
    },
    {
        "id": "anthropic/gemini/models/gemini-3.5-pro",
        "name": "Gemini 3.5 Pro",
        "desc": "Modelo avanzado de Google de alta capacidad"
    },
    {
        "id": "claude-3-5-sonnet-20241022",
        "name": "Claude 3.5 Sonnet (Classic)",
        "desc": "Versión clásica de Sonnet 3.5"
    },
    {
        "id": "claude-3-5-opus-20241022",
        "name": "Claude 3.5 Opus (Classic)",
        "desc": "Versión clásica de Opus 3.5"
    },
    {
        "id": "claude-3-haiku-20241022",
        "name": "Claude 3 Haiku",
        "desc": "Versión clásica de Haiku"
    }
]

def get_current_model():
    """Reads current model from settings.json"""
    paths = [
        os.path.expanduser("~/.claude/settings.json"),
        os.path.expanduser("~/.claude/settings.local.json"),
        os.path.abspath(".claude/settings.json")
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "model" in data:
                        return data["model"]
            except Exception:
                pass
    return "claude-sonnet-5"

def read_key():
    """Reads a single key or key sequence from stdin in raw mode"""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        # Read first char
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            # Check for escape sequence (arrow keys, etc.)
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r:
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    r, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if r:
                        ch3 = sys.stdin.read(1)
                        if ch3 == 'A':
                            return 'UP'
                        elif ch3 == 'B':
                            return 'DOWN'
                        elif ch3 == 'C':
                            return 'RIGHT'
                        elif ch3 == 'D':
                            return 'LEFT'
                return 'ESC'
            return 'ESC'
        elif ch == '\x7f' or ch == '\x08':
            return 'BACKSPACE'
        elif ch in ('\r', '\n'):
            return 'ENTER'
        elif ord(ch) == 3: # Ctrl+C
            return 'CTRL_C'
        elif ord(ch) == 4: # Ctrl+D
            return 'CTRL_D'
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def render(query, selected_idx, filtered_models, max_visible=8):
    """Renders the filtered list cleanly to the screen"""
    # Hide cursor
    sys.stdout.write("\033[?25l")

    # 1. Header input line
    sys.stdout.write(f"\r🔍 Buscar modelo (escribe para filtrar): \033[1;32m{query}\033[0m\n")

    # 2. Top separator
    sys.stdout.write("─" * 70 + "\n")

    # Calculate visible window
    total_matches = len(filtered_models)
    if total_matches <= max_visible:
        start_idx = 0
        end_idx = total_matches
    else:
        # Sliding window centering selected_idx
        if selected_idx < max_visible // 2:
            start_idx = 0
        elif selected_idx >= total_matches - max_visible // 2:
            start_idx = total_matches - max_visible
        else:
            start_idx = selected_idx - max_visible // 2
        end_idx = start_idx + max_visible

    # 3. Print items
    for i in range(start_idx, end_idx):
        item = filtered_models[i]
        is_selected = (i == selected_idx)

        # Determine prefix and coloring
        if is_selected:
            prefix = "➔ \033[1;36m●\033[0m"
            model_str = f"\033[1;36m{item['id']}\033[0m"
            name_str = f"\033[1m({item['name']})\033[0m"
            desc_str = f"\033[36m{item['desc']}\033[0m"
        else:
            prefix = "  \033[90m○\033[0m"
            model_str = f"\033[37m{item['id']}\033[0m"
            name_str = f"\033[90m({item['name']})\033[0m"
            desc_str = f"\033[90m{item['desc']}\033[0m"

        sys.stdout.write(f"\r{prefix} {model_str} {name_str} — {desc_str}\n")

    # Show scroll/overflow info if applicable
    lines_written = 3 + (end_idx - start_idx)
    if total_matches > max_visible:
        remaining = total_matches - max_visible
        sys.stdout.write(f"\r   \033[90m... y {remaining} modelos más (sigue escribiendo para filtrar) ...\033[0m\n")
        lines_written += 1

    # 4. Bottom separator
    sys.stdout.write("─" * 70 + "\n")

    # 5. Legend
    sys.stdout.write("\r\033[90mUse ↑/↓ para navegar │ Letras para buscar │ Enter para seleccionar │ Esc para cancelar\033[0m\n")

    sys.stdout.flush()
    return lines_written + 2

def clear_output(line_count):
    """Erases previously rendered lines dynamically"""
    if line_count > 0:
        # Move up and clear line_count times, then reset carriage to 0
        sys.stdout.write("\r" + "".join("\033[F\033[2K" for _ in range(line_count)))
        sys.stdout.flush()

def run_non_tty():
    """Fallback interactive prompt for redirected non-TTY environments"""
    sys.stdout.write("⚠️ Terminal no interactiva detectada. Usando interfaz de búsqueda por consola.\n")
    sys.stdout.flush()
    query = ""
    while True:
        # 1. Filter models
        filtered = []
        q_clean = query.strip().lower()
        for m in MODELS:
            if not q_clean or q_clean in m["id"].lower() or q_clean in m["name"].lower() or q_clean in m["desc"].lower():
                filtered.append(m)

        # Fallback custom input
        if not filtered and q_clean:
            filtered.append({
                "id": query.strip(),
                "name": f"Modelo personalizado: {query.strip()}",
                "desc": "Usar el ID ingresado literalmente"
            })

        # 2. Print current filtered list
        sys.stdout.write("\n🔍 Modelos disponibles (filtro activo: '" + (query or "ninguno") + "'):\n")
        sys.stdout.write("─" * 70 + "\n")
        for idx, item in enumerate(filtered):
            sys.stdout.write(f" [{idx + 1}] {item['id']} ({item['name']}) — {item['desc']}\n")
        sys.stdout.write("─" * 70 + "\n")
        sys.stdout.write("Escribe un término para filtrar, el número para elegir, o presiona Enter sin texto para cancelar:\n")
        sys.stdout.write("> ")
        sys.stdout.flush()

        # 3. Read input
        line = sys.stdin.readline()
        if not line: # EOF
            sys.exit(1)

        val = line.strip()
        if not val:
            sys.stdout.write("❌ Búsqueda/Cambio cancelado.\n")
            sys.exit(1)

        # Check if they entered an integer option
        if val.isdigit():
            opt_idx = int(val) - 1
            if 0 <= opt_idx < len(filtered):
                # Print selected model ID and exit 0
                print(filtered[opt_idx]["id"])
                sys.exit(0)
            else:
                sys.stdout.write(f"❌ Selección inválida: {val}. Fuera de rango (1-{len(filtered)})\n")
        else:
            # Update search query
            query = val

def main():
    if not sys.stdin.isatty():
        run_non_tty()
        return

    # Fetch current model to initialize pre-selection
    curr_model = get_current_model()

    # Initialize state
    query = ""
    selected_idx = 0
    last_rendered_lines = 0

    # Set default index matching the active model if possible
    for i, m in enumerate(MODELS):
        if m["id"] == curr_model:
            selected_idx = i
            break

    # Initial extra spacing so we don't overwrite user terminal input
    sys.stdout.write("\n")
    sys.stdout.flush()

    try:
        while True:
            # 1. Filter models based on query
            filtered = []
            q_clean = query.strip().lower()
            for m in MODELS:
                if not q_clean or q_clean in m["id"].lower() or q_clean in m["name"].lower() or q_clean in m["desc"].lower():
                    filtered.append(m)

            # Fallback custom input if absolutely nothing matches
            if not filtered and q_clean:
                filtered.append({
                    "id": query.strip(),
                    "name": f"Modelo personalizado: {query.strip()}",
                    "desc": "Usar el ID ingresado literalmente"
                })

            # Keep selected index in bounds of filtered list
            if not filtered:
                selected_idx = 0
            else:
                selected_idx = max(0, min(selected_idx, len(filtered) - 1))

            # 2. Erase previous render frame
            clear_output(last_rendered_lines)

            # 3. Draw new frame
            last_rendered_lines = render(query, selected_idx, filtered)

            # 4. Read keystroke
            key = read_key()

            # 5. Handle keys
            if key == 'UP':
                if filtered:
                    selected_idx = (selected_idx - 1) % len(filtered)
            elif key == 'DOWN':
                if filtered:
                    selected_idx = (selected_idx + 1) % len(filtered)
            elif key == 'BACKSPACE':
                query = query[:-1]
                selected_idx = 0
            elif key == 'ENTER':
                # Final clean before printing result or exiting
                clear_output(last_rendered_lines)
                sys.stdout.write("\033[?25h") # show cursor
                sys.stdout.flush()

                if filtered:
                    # Output selection to stdout and exit successfully
                    print(filtered[selected_idx]["id"])
                    sys.exit(0)
                else:
                    sys.exit(1)
            elif key in ('ESC', 'CTRL_C', 'CTRL_D'):
                clear_output(last_rendered_lines)
                sys.stdout.write("\033[?25h") # show cursor
                sys.stdout.flush()
                sys.exit(1)
            elif key is not None and len(key) == 1:
                # Append printable characters to query
                if ord(key) >= 32 and ord(key) < 127:
                    query += key
                    selected_idx = 0

    except KeyboardInterrupt:
        # Emergency restore cursor on interrupt
        sys.stdout.write("\033[?25h\n")
        sys.stdout.flush()
        sys.exit(1)

if __name__ == "__main__":
    main()
