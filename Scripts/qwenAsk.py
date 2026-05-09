#!/usr/bin/env python3
"""qwenAsk.py — Single-shot prompt to local Qwen3 via llama.cpp OpenAI-compatible API."""

import sys
import json
import argparse
import urllib.request
import urllib.error

DEFAULT_URL       = "http://localhost:8080"
DEFAULT_MODEL     = "Qwen3.6-35B-A3B-UD-Q6_K.gguf"
DEFAULT_TEMP      = 0.6
DEFAULT_TOKENS    = 2048
DEFAULT_TOKENS_THINK = 8192
DEFAULT_TIMEOUT   = 120


def buildPayload(args, prompt):
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": prompt})

    maxTokens = args.maxTokens
    if maxTokens is None:
        maxTokens = DEFAULT_TOKENS_THINK if args.think else DEFAULT_TOKENS

    payload = {
        "model": args.model,
        "messages": messages,
        "temperature": args.temp,
        "max_tokens": maxTokens,
        "chat_template_kwargs": {"enable_thinking": args.think},
    }
    return payload


def main():
    parser = argparse.ArgumentParser(description="Single-shot prompt to local Qwen3 llama.cpp server")
    parser.add_argument("prompt", nargs="?", help="Prompt text (reads stdin if omitted)")
    parser.add_argument("--think",        action="store_true",  help="Enable chain-of-thought reasoning (slower)")
    parser.add_argument("--showThinking", action="store_true",  help="Print reasoning_content before answer (requires --think)")
    parser.add_argument("--system",       default=None,         help="System prompt")
    parser.add_argument("--temp",         type=float,           default=DEFAULT_TEMP,    metavar="FLOAT", help=f"Temperature (default {DEFAULT_TEMP})")
    parser.add_argument("--maxTokens",    type=int,             default=None,            metavar="INT",   help=f"max_tokens (default {DEFAULT_TOKENS}, or {DEFAULT_TOKENS_THINK} with --think)")
    parser.add_argument("--json",         action="store_true",  help="Print raw JSON response instead of content")
    parser.add_argument("--url",          default=DEFAULT_URL,  help=f"Server base URL (default {DEFAULT_URL})")
    parser.add_argument("--model",        default=DEFAULT_MODEL, help=f"Model id (default {DEFAULT_MODEL})")
    parser.add_argument("--timeout",      type=int,             default=DEFAULT_TIMEOUT, metavar="SECONDS", help=f"Request timeout in seconds (default {DEFAULT_TIMEOUT})")
    args = parser.parse_args()

    # Resolve prompt
    if args.prompt:
        promptText = args.prompt
    else:
        promptText = sys.stdin.read().strip()
        if not promptText:
            print("error: no prompt provided (pass as argument or via stdin)", file=sys.stderr)
            sys.exit(1)

    payload = buildPayload(args, promptText)
    endpoint = args.url.rstrip("/") + "/v1/chat/completions"
    bodyBytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=bodyBytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            rawBody = resp.read()
    except urllib.error.URLError as e:
        reason = str(e.reason) if hasattr(e, "reason") else str(e)
        if "Connection refused" in reason or "connection refused" in reason:
            print(f"error: server not running at {args.url} (connection refused)", file=sys.stderr)
        else:
            print(f"error: could not reach {args.url}: {reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        print(f"error: server returned HTTP {e.code}: {body[:300]}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(rawBody)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON in response: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(data, indent=2))
        sys.exit(0)

    choices = data.get("choices")
    if not choices:
        print("error: response has no choices field", file=sys.stderr)
        sys.exit(1)

    message = choices[0].get("message", {})
    content = message.get("content", "").strip()
    reasoningContent = message.get("reasoning_content", "").strip()

    if args.showThinking and reasoningContent:
        print("--- thinking ---")
        print(reasoningContent)
        print("--- answer ---")

    if not content:
        print("error: response content is empty", file=sys.stderr)
        sys.exit(1)

    print(content)


if __name__ == "__main__":
    main()
