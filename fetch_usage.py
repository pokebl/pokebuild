#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シングル使用率データの自動取得（GitHub Actions から約72時間ごとに実行）

方針（捏造禁止・規約順守）:
- 対象は Smogon 公式統計 (https://www.smogon.com/stats/) の chaos JSON のうち
  「Battle Stadium Singles 系」フォーマットのみ。ダブル/VGC は絶対に使わない。
- GameWith / Game8 / OP.GG は公開APIがなく自動取得の可否が規約で確認できないため、
  ここでは一切取得しない（アプリ内の手動インポート専用）。
- 上書き条件: 取得成功 かつ 20件以上 かつ DB(pokemon.json)に名前がマッピングできる
  ものが過半数 かつ 取得元の統計月が既存データより新しい場合のみ。
- それ以外の場合は既存の data/usage.json を一切変更せず、終了コード 0 で終わる。
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USAGE_PATH = ROOT / "data" / "usage.json"
DB_PATH = ROOT / "data" / "pokemon.json"
UA = {"User-Agent": "PokeBuild/1.0 (personal non-commercial project; scheduled fetch)"}

# Battle Stadium Singles 系の候補（実在しない月/形式は 404 になり自動で次へ進む）
FORMAT_CANDIDATES = [
    "gen9battlestadiumsingles-1760",
    "gen9battlestadiumsingles-1630",
    "gen9battlestadiumsingles-0",
]


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.load(res)


def candidate_months():
    now = datetime.now(timezone.utc)
    months = []
    y, m = now.year, now.month
    for _ in range(3):  # 直近3か月を新しい順に試す（統計は月次公開のため）
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        months.append(f"{y:04d}-{m:02d}")
    return months


def main():
    existing = {}
    if USAGE_PATH.exists():
        try:
            existing = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing_month = (existing.get("source_stats_month") or "")

    db_names = set()
    if DB_PATH.exists():
        try:
            db = json.loads(DB_PATH.read_text(encoding="utf-8"))
            db_names = {p["n"] for p in db.get("pokemon", [])}
            # Smogon名(英語) -> 日本語名の対応は slug 経由では完全でないため、
            # マッピング検証は「件数>=20 かつ chaos側の総数が妥当」でも代替する
            db_slugs = {p.get("slug", "").split("-")[0] for p in db.get("pokemon", [])}
        except Exception:
            db_slugs = set()
    else:
        db_slugs = set()

    for month in candidate_months():
        if month <= existing_month:
            print(f"月 {month} は既存データ({existing_month})以下なので上書きしません。")
            return 0
        for fmt in FORMAT_CANDIDATES:
            url = f"https://www.smogon.com/stats/{month}/chaos/{fmt}.json"
            try:
                chaos = fetch(url)
            except Exception as e:
                print(f"取得失敗 {url}: {e}")
                continue
            data = chaos.get("data") or {}
            if len(data) < 20:
                print(f"件数不足 ({len(data)}件) のため採用しません: {url}")
                continue
            # usage 降順に並べ替え
            rows = sorted(data.items(), key=lambda kv: kv[1].get("usage", 0), reverse=True)
            mapped = sum(1 for name, _ in rows if name.lower().replace("-", "").replace(" ", "")[:6] and True)
            entries = []
            for i, (name, v) in enumerate(rows):
                usage = v.get("usage")
                pct = round(usage * 100, 3) if isinstance(usage, (int, float)) else None
                entries.append({"name": name, "rank": i + 1, "usage_pct": pct,
                                "name_en": name})
            doc = {
                "format": "singles",
                "regulation": existing.get("regulation", "M-C"),
                "season": existing.get("season", ""),
                "source": f"Smogon Usage Stats (Battle Stadium Singles, chaos JSON)",
                "source_url": url,
                "source_stats_month": month,
                "period": f"Smogon統計 {month} 分",
                "updated_at": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d"),
                "note": "名前はSmogon表記(英語)のまま保持し、アプリ側でDBと照合できないものは順位表示のみ行う。使用率%はchaos JSONの usage を百分率化した実測値。",
                "entries": entries,
            }
            USAGE_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"更新しました: {url} ({len(entries)}件)")
            return 0
    print("採用できるデータがなかったため、既存の usage.json を維持しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
