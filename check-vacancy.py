
import re, json, html, requests, time, os
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

URL = "https://sec.489.jp/rga/30/reserve/plan?adult=4"

# GitHub Actionsのシークレットから取得
LINE_TOKEN = os.environ.get("LINE_TOKEN")
TARGET_DATE = os.environ.get("TARGET_DATE")

def fetch_html() -> str:
    r = requests.get(URL, headers={"User-Agent":"Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    return r.text

def parse_rooms_payload(html_text: str) -> dict:
    m = re.search(r'prop-initial-display-rooms\s*=\s*"([^"]+)"', html_text)
    if not m:
        raise RuntimeError("prop-initial-display-rooms が見つかりません")
    return json.loads(html.unescape(m.group(1)))

def build_room_names(payload: dict):
    names = {}
    for _, grp in payload.get("calendarRooms", {}).items():
        for cell in grp.get("room", []):
            if cell.get("date") is None and cell.get("text"):
                names[cell.get("room_id")] = cell["text"]
    return names

def list_available(payload: dict, target_date: str):
    """指定日付の空きがあれば返す"""
    names = build_room_names(payload)
    avail_rooms = []
    for _, grp in payload.get("calendarRooms", {}).items():
        for cell in grp.get("room", []):
            d = cell.get("date")
            if d == target_date and cell.get("vacancyFlg", 0) == 1:
                room = names.get(cell.get("room_id"), f"room_id={cell.get('room_id')}")
                avail_rooms.append(room)
    return avail_rooms

def line_broadcast(text: str):
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    body = {"messages":[{"type":"text","text":text}]}
    r = requests.post(url, headers=headers, data=json.dumps(body), timeout=15)
    r.raise_for_status()

def check_once() -> bool:
    payload = parse_rooms_payload(fetch_html())
    rooms = list_available(payload, TARGET_DATE)

    # ログ出力用データ
    log_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "target_date": TARGET_DATE,
        "available_rooms": rooms,
        "url": URL
    }
    # ログファイル名例: vacancy-log-20250921.json
    log_filename = f"vacancy-log-{datetime.now().strftime('%Y%m%d')}.json"
    with open(log_filename, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    # 通知済み判定用ファイル
    notified_flag = f"vacancy-notified-{TARGET_DATE}.flag"

    if rooms:
        if os.path.exists(notified_flag):
            print(f"[{log_data['timestamp']}] {TARGET_DATE} は既に通知済みです")
            return True
        msg = f"【空き発見】{TARGET_DATE}\n" + " / ".join(rooms) + f"\n{URL}"
        line_broadcast(msg)
        # 通知済みフラグファイルを作成
        with open(notified_flag, "w") as f:
            f.write(log_data["timestamp"])
        print(f"[{log_data['timestamp']}] {TARGET_DATE} の空室を通知しました")
        return True
    else:
        ts = log_data["timestamp"]
        print(f"[{ts}] {TARGET_DATE} は空室なし")
        return False



if __name__ == "__main__":
    try:
        check_once()
    except Exception as e:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] エラー: {e}")
