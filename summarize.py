"""Generate short cached summaries for organization session titles."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = (
    "あなたはハッカソンの運営スタッフです。あるチームのDevinセッションのタイトル一覧から、"
    "そのチームが何を作っているかを日本語で簡潔にまとめます。出力は40〜60文字程度の1文のみ。"
    "前置き・箇条書き・鉤括弧・チーム名の繰り返しは禁止。推測が難しい場合は共通する作業内容を述べる。"
)
USER_TEMPLATE = (
    "チーム名: {org_name}\n"
    "セッションタイトル一覧:\n"
    "{titles}\n\n"
    "このチームが作っているものを1文で要約してください。"
)


def fallback_summary(titles: list[str]) -> str:
    return " / ".join(title for title in titles[:3] if title)


def summarize_org(org_name: str, titles: list[str], api_key: str | None = None) -> str:
    fallback = fallback_summary(titles)
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key or not titles:
        return fallback
    body = json.dumps(
        {
            "model": MODEL,
            "temperature": 0.2,
            "max_tokens": 120,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_TEMPLATE.format(
                        org_name=org_name,
                        titles="\n".join(f"- {title}" for title in titles),
                    ),
                },
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"].strip()
        return content or fallback
    except (OSError, KeyError, IndexError, TypeError, ValueError, urllib.error.URLError):
        return fallback
