import requests
import os
from datetime import datetime, timedelta, timezone

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]

NOTION_VERSION = "2022-06-28"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}

SEARCH_URL = "https://api.notion.com/v1/search"
PAGE_URL = "https://api.notion.com/v1/pages/"

since = datetime.now(timezone.utc) - timedelta(hours=24)

pages = {}
parent_cache = {}
cursor = None


# ----------------------------
# ページタイトル取得
# ----------------------------
def get_page_title(page):

    if page.get("properties"):
        for p in page["properties"].values():
            if p["type"] == "title":
                if p["title"]:
                    return p["title"][0]["plain_text"]

    return "Untitled"


# ----------------------------
# 親階層取得（再帰）
# ----------------------------
def get_parent_path(parent):

    if parent["type"] != "page_id":
        return None

    pid = parent["page_id"]

    if pid in parent_cache:
        return parent_cache[pid]

    res = requests.get(PAGE_URL + pid, headers=headers).json()

    title = get_page_title(res)

    parent_path = title

    if res.get("parent") and res["parent"]["type"] == "page_id":
        p = get_parent_path(res["parent"])
        if p:
            parent_path = p + " / " + parent_path

    parent_cache[pid] = parent_path

    return parent_path


# ----------------------------
# 全ページ取得
# ----------------------------
while True:

    payload = {
        "filter": {"value": "page", "property": "object"},
        "sort": {
            "timestamp": "last_edited_time",
            "direction": "descending"
        },
        "page_size": 100
    }

    if cursor:
        payload["start_cursor"] = cursor

    res = requests.post(SEARCH_URL, headers=headers, json=payload).json()

    for r in res["results"]:

        edited = datetime.fromisoformat(
            r["last_edited_time"].replace("Z","+00:00")
        )

        if edited < since:
            continue

        page_id = r["id"]

        if page_id in pages:
            continue

        title = get_page_title(r)

        icon = ""

        if r.get("icon"):
            if r["icon"]["type"] == "emoji":
                icon = r["icon"]["emoji"]
            else:
                icon = "📄"

        editor = r.get("last_edited_by", {}).get("name", "unknown")

        parent_path = get_parent_path(r["parent"])

        path = title
        if parent_path:
            path = parent_path + " / " + title

        pages[page_id] = {
            "path": path,
            "icon": icon,
            "url": r["url"],
            "editor": editor,
            "time": edited
        }

    if not res.get("has_more"):
        break

    cursor = res["next_cursor"]


# ----------------------------
# 更新リスト
# ----------------------------
updates = list(pages.values())

updates.sort(key=lambda x: x["time"], reverse=True)


# ----------------------------
# Discordメッセージ生成
# ----------------------------
if not updates:

    messages = ["📘 Notion更新（過去24時間）：なし"]

else:

    header = f"📘 Notion更新（過去24時間：{len(updates)}件）\n\n"

    lines = []

    for u in updates:

        t = u["time"].astimezone().strftime("%m-%d %H:%M")

        lines.append(
            f"{u['icon']} **{u['path']}**\n"
            f"{u['url']}\n"
            f"edited by {u['editor']} ({t})\n"
        )

    messages = []
    current = header

    for line in lines:

        if len(current) + len(line) > 1900:
            messages.append(current)
            current = ""

        current += line + "\n"

    messages.append(current)


# ----------------------------
# Discord送信
# ----------------------------
for m in messages:

    try:
        requests.post(DISCORD_WEBHOOK, json={"content": m})
    except:
        pass