"""
Google Sheets → data/*.json 変換スクリプト
GitHub Actions から自動実行される
"""

import os
import json
import requests

SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
API_KEY  = os.environ["GOOGLE_API_KEY"]

SHEET_TABS = {
    "shinjuku": "data/shinjuku.json",
    "shibuya":  "data/shibuya.json",
    "ginza":    "data/ginza.json",
}

AREA_META = {
    "shinjuku": {"id": "shinjuku", "name": {"en": "Shinjuku", "zh": "新宿", "ko": "신주쿠", "ja": "新宿"}, "lat": 35.6938, "lng": 139.7036},
    "shibuya":  {"id": "shibuya",  "name": {"en": "Shibuya",  "zh": "涩谷", "ko": "시부야",  "ja": "渋谷"},  "lat": 35.6580, "lng": 139.7016},
    "ginza":    {"id": "ginza",    "name": {"en": "Ginza",    "zh": "银座", "ko": "긴자",    "ja": "銀座"},   "lat": 35.6714, "lng": 139.7659},
}


def fetch_sheet(sheet_tab_name):
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
        f"/values/{sheet_tab_name}?key={API_KEY}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    rows = resp.json().get("values", [])
    if not rows:
        raise ValueError(f"シート '{sheet_tab_name}' にデータがありません")
    return rows


def parse_rows(rows):
    header = rows[0]
    return [
        {header[i]: (row[i] if i < len(row) else "") for i in range(len(header))}
        for row in rows[1:]
        if any(cell.strip() for cell in row)
    ]


def build_shop(r):
    def tag(n):
        label_en = r.get(f"tag{n}_label_en", "").strip()
        if not label_en:
            return None
        return {
            "l": {
                "en": label_en,
                "ja": r.get(f"tag{n}_label_ja", label_en).strip(),
                "zh": r.get(f"tag{n}_label_zh", label_en).strip(),
                "ko": r.get(f"tag{n}_label_ko", label_en).strip(),
            },
            "cls": r.get(f"tag{n}_cls", "").strip(),
        }

    tags = [t for t in [tag(1), tag(2), tag(3)] if t]

    def split_csv(val):
        return [v.strip() for v in val.split(",") if v.strip()]

    shop = {
        "id":       r.get("id", "").strip(),
        "name":     r.get("name", "").strip(),
        "name_ja":  r.get("name_ja", "").strip(),
        "type":     r.get("type", "").strip(),
        "area_label": {
            "en": r.get("area_label_en", "").strip(),
            "ja": r.get("area_label_ja", "").strip(),
            "zh": r.get("area_label_zh", "").strip(),
            "ko": r.get("area_label_ko", "").strip(),
        },
        "lat":     float(r.get("lat", 0) or 0),
        "lng":     float(r.get("lng", 0) or 0),
        "rating":  float(r.get("rating", 0) or 0),
        "reviews": int(r.get("reviews", 0) or 0),
        "price_range": r.get("price_range", "").strip(),
        "hours": {
            "en": r.get("hours_en", "").strip(),
            "ja": r.get("hours_ja", "").strip(),
        },
        "flavors": split_csv(r.get("flavors", "")),
        "vibes":   split_csv(r.get("vibes", "")),
        "tags":    tags,
        "comment": {
            "en": r.get("comment_en", "").strip(),
            "ja": r.get("comment_ja", "").strip(),
            "zh": r.get("comment_zh", "").strip(),
            "ko": r.get("comment_ko", "").strip(),
        },
        "mapUrl": r.get("mapUrl", "").strip(),
    }

    if not shop["id"]:
        raise ValueError(f"idが空の行があります: {r}")
    if not shop["name"]:
        raise ValueError(f"nameが空の行があります: id={shop['id']}")

    return shop


def convert_tab(tab_name, output_path):
    print(f"\n--- {tab_name} → {output_path} ---")
    rows = fetch_sheet(tab_name)
    records = parse_rows(rows)
    shops = []
    for rec in records:
        try:
            shops.append(build_shop(rec))
        except Exception as e:
            print(f"  ⚠️  スキップ: {e}")

    area = AREA_META.get(tab_name, {"id": tab_name})
    data = {"area": area, "shops": shops}

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  ✓ {len(shops)} 店舗を書き出しました → {output_path}")


def main():
    print("=== Sheets → JSON 変換開始 ===")
    success = 0
    skipped = 0

    for tab_name, output_path in SHEET_TABS.items():
        try:
            convert_tab(tab_name, output_path)
            success += 1
        except requests.HTTPError as e:
            # ★修正: 400・403・404 すべてシート未存在としてスキップ
            if e.response.status_code in (400, 403, 404):
                print(f"  ℹ️  '{tab_name}' シートが見つかりません（スキップ）")
                skipped += 1
            else:
                print(f"  ❌ '{tab_name}' 予期しないHTTPエラー: {e}")
                raise
        except ValueError as e:
            print(f"  ℹ️  '{tab_name}' データなし（スキップ）: {e}")
            skipped += 1
        except Exception as e:
            print(f"  ❌ '{tab_name}' エラー: {e}")
            raise

    print(f"\n=== 完了: {success}件成功, {skipped}件スキップ ===")


if __name__ == "__main__":
    main()
