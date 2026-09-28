"""記事を自動生成するスクリプト。

- scripts/topics_seed.yaml と scripts/topics_state.json から未使用トピックを選ぶ
- 種トピックを使い切ったら、AI自身に新しいトピック案を出してもらう
- GEMINI_API_KEY が設定されていれば Gemini API で本文を生成する
- 設定されていない場合はローカル動作確認用のプレースホルダー記事を生成する(--allow-fallback時のみ)

使い方:
    python scripts/generate_post.py
    python scripts/generate_post.py --allow-fallback   # APIキーが無くても動作確認できる
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "posts"
CONFIG_PATH = ROOT / "config.yaml"
TOPICS_SEED_PATH = Path(__file__).resolve().parent / "topics_seed.yaml"
TOPICS_STATE_PATH = Path(__file__).resolve().parent / "topics_state.json"
# 混雑や廃止で主モデルが使えないとき、この順で切り替える
FALLBACK_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
]


def generate_content(client, model_name: str, contents: str):
    """一時的な混雑(503)や上限(429)は待って再試行し、モデル廃止時は次のモデルに切り替える。"""
    models = [model_name] + [name for name in FALLBACK_MODELS if name != model_name]
    last_error: Exception | None = None

    for model in models:
        for attempt in range(1, 4):
            try:
                response = client.models.generate_content(model=model, contents=contents)
                if model != model_name:
                    print(f"モデルを {model} に切り替えて生成しました", file=sys.stderr)
                return response
            except Exception as exc:
                last_error = exc
                message = str(exc)
                unavailable = any(
                    token in message
                    for token in ("503", "429", "500", "502", "504", "UNAVAILABLE", "RESOURCE_EXHAUSTED")
                )
                retired = any(
                    token in message
                    for token in ("404", "NOT_FOUND", "no longer available", "not found")
                )
                if retired:
                    print(f"モデル {model} は利用できないため次を試します", file=sys.stderr)
                    break
                if not unavailable or attempt == 3:
                    if not unavailable:
                        raise
                    print(f"モデル {model} は再試行上限に達したため次を試します", file=sys.stderr)
                    break
                wait = 25 * attempt
                print(
                    f"{model} が一時的に失敗しました ({attempt}/3)。{wait}秒後に再試行します。",
                    file=sys.stderr,
                )
                time.sleep(wait)

    if last_error is not None:
        raise last_error
    raise RuntimeError("記事生成に失敗しました")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_topics_state() -> dict:
    if TOPICS_STATE_PATH.exists():
        with open(TOPICS_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"used_topics": [], "extra_topics": []}


def save_topics_state(state: dict) -> None:
    with open(TOPICS_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def slugify(text: str) -> str:
    """タイトルからASCIIのみのスラッグを作る(URLの安全性のため日本語は使わない)。"""
    text = unicodedata.normalize("NFKC", text)
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    if ascii_part:
        return f"{ascii_part}-{digest}"
    return digest


def pick_next_topic(state: dict, client=None, model_name: str | None = None) -> str:
    with open(TOPICS_SEED_PATH, "r", encoding="utf-8") as f:
        seed_topics = yaml.safe_load(f)["topics"]

    used = set(state["used_topics"])
    pool = [t for t in seed_topics + state.get("extra_topics", []) if t not in used]

    if pool:
        return pool[0]

    if client is None:
        # フォールバック: プール空 & AIなしの場合は連番トピックを作る
        return f"AIとガジェット活用の新しいアイデア #{len(used) + 1}"

    recent = "\n".join(f"- {topic}" for topic in state["used_topics"][-30:])
    prompt = (
        "あなたは日本語のテックブログの編集者です。"
        "「AIツール・アプリ・ガジェットの活用術」という分野で、"
        "まだ記事化されていない具体的で検索されやすい記事タイトル案を10個、"
        "日本語で、1行に1つずつ、番号や記号なしで出力してください。\n"
        "次の既存タイトルと同じテーマ・同じ製品の言い換えは避けてください。\n"
        f"{recent}"
    )
    response = generate_content(client, model_name, prompt)
    candidates = [line.strip("・-1234567890. 　") for line in response.text.splitlines() if line.strip()]
    candidates = [c for c in candidates if c and c not in used]
    if not candidates:
        return f"AIとガジェット活用の新しいアイデア #{len(used) + 1}"

    state["extra_topics"] = list(dict.fromkeys(state.get("extra_topics", []) + candidates))
    return candidates[0]


def build_prompt(topic: str, min_words: int, max_words: int) -> str:
    return f"""あなたは日本語のテックブログのプロライターです。
以下のトピックについて、読者にとって実際に役立つ、具体的で正確なブログ記事を書いてください。

# トピック
{topic}

# 執筆ルール
- 日本語で書く
- 文字数は{min_words}〜{max_words}文字程度
- 断定できない情報(価格、対応機種、最新の仕様など)は「執筆時点」「公式サイトで確認してください」のように書き、誤情報を断定しない
- Markdown形式で、大見出し(#)は使わず、##と###の小見出しを使って構成する
- 導入・本文(3〜5個の見出し)・まとめの構成にする
- 具体的な手順や比較表(Markdownテーブル)を積極的に使う
- 誇大な収益保証や医療・金融の断定的アドバイスは書かない
- 最後に「まとめ」の見出しで締める

# 出力形式(この形式を厳守)
1行目: SEOタイトル(32文字以内目安)
2行目: メタディスクリプション(80文字以内)
3行目以降: 本文(Markdown)
"""


def call_gemini(topic: str, min_words: int, max_words: int, model_name: str, client):
    prompt = build_prompt(topic, min_words, max_words)
    response = generate_content(client, model_name, prompt)
    text = response.text.strip()

    lines = text.splitlines()
    title = lines[0].strip("# ").strip()
    description = lines[1].strip() if len(lines) > 1 else topic
    body = "\n".join(lines[2:]).strip()
    return title, description, body


def fallback_article(topic: str) -> tuple[str, str, str]:
    title = topic
    description = f"{topic}について分かりやすく解説します。(ローカル動作確認用のダミー記事です)"
    body = f"""## はじめに

これはローカル動作確認用のプレースホルダー記事です。`GEMINI_API_KEY` を設定すると、
実際にはAIがこのトピック「{topic}」について本文を自動生成します。

## この記事について

- ビルドパイプラインの動作確認用です
- 実運用前に GEMINI_API_KEY を GitHub Actions の Secrets に設定してください

## まとめ

APIキーを設定して再実行すると、実際の記事本文に置き換わります。
"""
    return title, description, body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="GEMINI_API_KEYが無い場合にプレースホルダー記事で動作確認する",
    )
    args = parser.parse_args()

    config = load_config()
    gen_cfg = config.get("generation", {})
    min_words = gen_cfg.get("min_words", 900)
    max_words = gen_cfg.get("max_words", 1600)
    model_name = gen_cfg.get("model", "gemini-1.5-flash")

    state = load_topics_state()

    has_key = bool(os.environ.get("GEMINI_API_KEY"))
    client = None
    if has_key:
        from google import genai

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    topic = pick_next_topic(state, client=client, model_name=model_name)

    if has_key:
        title, description, body = call_gemini(topic, min_words, max_words, model_name, client)
    elif args.allow_fallback:
        title, description, body = fallback_article(topic)
    else:
        print(
            "エラー: GEMINI_API_KEY が設定されていません。\n"
            "動作確認だけしたい場合は --allow-fallback を付けて実行してください。",
            file=sys.stderr,
        )
        return 1

    today = dt.date.today().isoformat()
    slug = f"{today}-{slugify(title)[:60]}"
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    post_path = CONTENT_DIR / f"{slug}.md"

    frontmatter = f"""---
title: "{title.replace('"', "'")}"
description: "{description.replace('"', "'")}"
date: {today}
slug: {slug}
tags: ["AI", "ガジェット"]
source_topic: "{topic.replace('"', "'")}"
---

"""
    post_path.write_text(frontmatter + body + "\n", encoding="utf-8")

    state["used_topics"].append(topic)
    if topic in state.get("extra_topics", []):
        state["extra_topics"].remove(topic)
    save_topics_state(state)

    print(f"生成しました: {post_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
