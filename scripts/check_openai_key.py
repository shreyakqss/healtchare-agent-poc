import os
import sys
from pathlib import Path
from typing import Tuple

import requests
from dotenv import load_dotenv


HERE = Path(__file__).resolve().parent
DOTENV_PATH = HERE / ".env"


def load_key() -> str | None:
    # Load backend/.env if present, then read env var
    if DOTENV_PATH.exists():
        load_dotenv(dotenv_path=DOTENV_PATH)
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    # sanitize surrounding quotes and whitespace
    return key.strip().strip("'\"")

def check_key(api_key: str) -> tuple[bool, str]:
    """Return (is_valid, message)."""
    url = "https://api.openai.com/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as exc:
        return False, f"Network error: {exc}"

    if resp.status_code == 200:
        return True, "Key is valid (able to list models)."
    if resp.status_code == 401:
        return False, "Unauthorized: the API key is invalid or revoked."
    if resp.status_code == 429:
        return True, "Rate-limited or quota exceeded — the key is valid but throttled."
    # other errors
    return False, f"Unexpected response {resp.status_code}: {resp.text.strip()[:200]}"


def ask_model(api_key: str, model: str, question: str) -> Tuple[bool, str]:
    """Send `question` to the chat `model`. Returns (success, reply_or_error)."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": question}],
        "max_tokens": 800,
        "temperature": 0.2,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        return False, f"Network error: {exc}"

    if resp.status_code == 200:
        try:
            data = resp.json()
            # Typical shape: {choices: [{message: {content: ...}}]}
            choices = data.get("choices") or []
            if choices and isinstance(choices, list):
                msg = choices[0].get("message", {})
                content = msg.get("content") or msg.get("text")
                if content:
                    return True, content
            # fallback: try top-level `text`
            return True, data.get("text", "(no text in response)")
        except ValueError:
            return False, "Invalid JSON in response"
    if resp.status_code == 401:
        return False, "Unauthorized: the API key is invalid or revoked."
    if resp.status_code == 429:
        return False, "Rate-limited or quota exceeded."
    return False, f"Unexpected response {resp.status_code}: {resp.text.strip()[:400]}"

def main() -> int:
    key = load_key()
    if not key:
        print("OPENAI_API_KEY not found in environment or backend/.env", file=sys.stderr)
        return 2

    valid, message = check_key(key)
    if not valid:
        print("FAIL:", message, file=sys.stderr)
        return 3

    print("OK:", message)

    # Ask the user for a question to send to the specified model
    model = "gpt-4.1-2025-04-14"
    try:
        question = input(f"Enter question to send to {model} (empty to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("No question provided; exiting.")
        return 0

    if not question:
        print("No question provided; exiting.")
        return 0

    ok, reply = ask_model(key, model, question)
    if ok:
        print("--- Model reply ---")
        print(reply)
        return 0
    else:
        print("Model request failed:", reply, file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
