import requests
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

SEARCH_URL = "https://api.notion.com/v1/search"
PAGE_URL = "https://api.notion.com/v1/pages/"
USER_URL = "https://api.notion.com/v1/users/"

since = datetime.now(timezone.utc) - timedelta(hours=24)

pages = {}
parent_cache = {}
user_cache = {}

cursor = None


def get_title(page):

    if page.get("properties"):
        for p in page["properties"].values():
            if p["type"] == "title" and p["title"]:
                return p["title"][0]["plain_text"]

    return "Untitled"


def get_user_name(user_id):

    if user_id in user_cache:
        return user_cache[user_id]

    res = requests.get(USER_URL + user_id, headers=headers).json()

    name = res.get("name", "unknown")

    user_cache[user_id] = name

    return name


def get_parent_title(parent):

    if parent["type"] != "page_id":
        return None

    pid = parent["page_id"]

    if pid in parent_cache:
        return parent_cache[pid]

    res = requests.get(PAGE_URL + pid, headers=headers).json()

    title = get_title(res)

    parent_cache[pid] = title

    return title


while True:

    payload = {
        "filter": {"value": "page", "property": "object"},
        "sort": {"timestamp": "last_edited_time", "direction": "descending"},
        "page_size": 100
    }

    if cursor:
        payload["start_cursor"] = cursor

    res = requests.post(SEARCH_URL, headers=headers, json=payload).json()

    for r in res["results"]:

        edited = datetime.fromisoformat(
            r["last_edited_time"].replace("Z", "+00:00")
        )

        if edited < since:
            continue

        page_id = r["id"]

        if page_id in pages:
            continue

        title = get_title(r)

        parent_title = get_parent_title(r["parent"])

        if parent_title:
            path = parent_title + " / " + title
        else:
            path = title

        icon = ""

        if r.get("icon"):
            if r["icon"]["type"] == "emoji":
                icon = r["icon"]["emoji"]
            else:
                icon = "📄"

        editor = "unknown"

        if r.get("last_edited_by"):
            uid = r["last_edited_by"].get("id")
            if uid:
                editor = get_user_name(uid)

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


updates = list(pages.values())

updates.sort(key=lambda x: x["time"], reverse=True)


if not updates:
    raise SystemExit(0)

else:

    header = f"📘 Notion更新（過去24時間：{len(updates)}件）\n\n"

    lines = []

    for u in updates:

        t = u["time"].astimezone(
            ZoneInfo("Asia/Tokyo")
        ).strftime("%Y-%m-%d %H:%M")

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


for m in messages:
    requests.post(DISCORD_WEBHOOK, json={"content": m})