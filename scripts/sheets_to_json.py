"""
Google Sheets → data/shinjuku.json 変換スクリプト
GitHub Actions から自動実行される

スプレッドシートの列構成（1行目がヘッダー）:
id | name | name_ja | type | area_label_en | area_label_ja | area_label_zh | area_label_ko
lat | lng | rating | reviews | price_range | hours_en | hours_ja
flavors | vibes
tag1_label_en | tag1_label_ja | tag1_label_zh | tag1_label_ko | tag1_cls
tag2_label_en | tag2_label_ja | tag2_label_zh | tag2_label_ko | tag2_cls
tag3_label_en | tag3_label_ja | tag3_label_zh | tag3_label_ko | tag3_cls
comment_en | comment_ja | comment_zh | comment_ko
mapUrl
"""

import os
import json
import requests

SHEET_ID  = os.environ["SHEET_ID"]
API_KEY   = os.environ["GOOGLE_API_KEY"]

# シート名ごとに出力ファイルをマッピング
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
    """Google Sheets APIでシートデータを取得する"""
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
    """ヘッダー行をキーにして辞書のリストを返す"""
    header = rows[0]
    return [
        {header[i]: (row[i] if i < len(row) else "") for i in range(len(header))}
        for row in rows[1:]
        if any(cell.strip() for cell in row)   # 空行スキップ
    ]


def build_shop(r):
    """1行の辞書をshop JSONオブジェクトに変換する"""

    def tag(n):
        """n番目のタグを作る（1, 2, 3）"""
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

    # flavors と vibes はカンマ区切りの文字列 → リスト
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
        "lat":      float(r.get("lat", 0) or 0),
        "lng":      float(r.get("lng", 0) or 0),
        "rating":   float(r.get("rating", 0) or 0),
        "reviews":  int(r.get("reviews", 0) or 0),
        "price_range": r.get("price_range", "").strip(),
        "hours": {
            "en": r.get("hours_en", "").strip(),
            "ja": r.get("hours_ja", "").strip(),
        },
        "flavors":  split_csv(r.get("flavors", "")),
        "vibes":    split_csv(r.get("vibes", "")),
        "tags":     tags,
        "comment": {
            "en": r.get("comment_en", "").strip(),
            "ja": r.get("comment_ja", "").strip(),
            "zh": r.get("comment_zh", "").strip(),
            "ko": r.get("comment_ko", "").strip(),
        },
        "mapUrl":   r.get("mapUrl", "").strip(),
    }

    # 必須フィールドのバリデーション
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
    for tab_name, output_path in SHEET_TABS.items():
        try:
            convert_tab(tab_name, output_path)
        except requests.HTTPError as e:
            if e.response.status_code == 400:
                # シートタブが存在しない場合はスキップ（まだ作っていないエリア）
                print(f"  ℹ️  {tab_name} シートが見つかりません（スキップ）")
            else:
                raise
    print("\n=== 完了 ===")


if __name__ == "__main__":
    main()
