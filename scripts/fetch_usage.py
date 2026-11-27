#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シングル使用率データの自動取得（GitHub Actions から約72時間ごとに実行）

取得元（2026-11-27 に実在を確認）:
- Smogon 公式統計 https://www.smogon.com/stats/{YYYY-MM}/chaos/
  の `gen9championsbssregmc-{cutoff}.json`
  = Pokémon Champions / Battle Stadium Singles / Regulation M-C の月次統計。
  2026-09 と 2026-10 の両方に実在することを確認済み。
- cutoff は 1630 を優先し、無ければ 1500、0 の順に試す。
- ダブル/VGC 系フォーマット（gen9championsvgc* 等）は絶対に使わない。
- GameWith / Game8 / OP.GG は公開APIがなく自動取得の可否が規約で確認できないため、
  ここでは一切取得しない（アプリ内の手動インポート専用）。

方針（捏造禁止・安全弁）:
- usage_pct は chaos JSON の usage（0〜1）を百分率化した実測値のみ。推測補完はしない。
- 名前は Showdown 表記 → PokeAPI slug → DB の日本語名へ変換できたものだけを採用する。
- 安全弁: 取得成功 かつ 20件以上 かつ「上位50件のうち40件以上」が DB に
  マッピングできる かつ 統計月が既存データより新しい場合のみ data/usage.json を上書き。
- それ以外の場合は既存の data/usage.json を一切変更せず、終了コード 0 で終わる。
- 注意: Smogon 統計は Pokémon Showdown ラダーの集計であり、ゲーム内ランクバトルの
  使用率とは母集団が異なる。その旨は生成する usage.json の note にも明記する。
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USAGE_PATH = ROOT / "data" / "usage.json"
DB_PATH = ROOT / "data" / "pokemon.json"
UA = {"User-Agent": "PokeBuild/1.0 (personal non-commercial project; scheduled fetch)"}

# Champions Battle Stadium Singles / Regulation M-C（cutoff は優先順）
FORMAT_BASE = "gen9championsbssregmc"
CUTOFFS = [1630, 1500, 0]

# Showdown 表記 → PokeAPI slug の例外対応（直接変換で一致しないもの）
ALIASES = {
    "indeedee": "indeedee-male", "indeedee-f": "indeedee-female",
    "basculegion": "basculegion-male", "basculegion-f": "basculegion-female",
    "meowstic": "meowstic-male", "meowstic-f": "meowstic-female",
    "mimikyu": "mimikyu-disguised", "aegislash": "aegislash-shield",
    "toxtricity": "toxtricity-amped", "palafin": "palafin-zero",
    "gourgeist": "gourgeist-average", "pumpkaboo": "pumpkaboo-average",
    "lycanroc": "lycanroc-midday", "wishiwashi": "wishiwashi-solo",
    "tatsugiri": "tatsugiri-curly", "dudunsparce": "dudunsparce-two-segment",
    "sinistea": "sinistea-phony", "poltchageist": "poltchageist-counterfeit",
    "squawkabilly": "squawkabilly-green-plumage",
    "maushold": "maushold-family-of-four",
    "mr. mime": "mr-mime", "mr. rime": "mr-rime",
    "farfetch'd": "farfetchd", "sirfetch'd": "sirfetchd",
    "type: null": "type-null",
    "nidoran-f": "nidoran-female", "nidoran-m": "nidoran-male",
}


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


def normalize(name):
    """Showdown 表記を slug 形式（小文字・ハイフン区切り）に寄せる"""
    return name.strip().lower().replace(" ", "-").replace(".", "").replace("'", "")


def map_to_slug(showdown_name, slugs):
    """Showdown 表記 → PokeAPI slug。対応できなければ None"""
    raw = showdown_name.strip().lower()
    if raw in ALIASES and ALIASES[raw] in slugs:
        return ALIASES[raw]
    n = normalize(showdown_name)
    if n in slugs:
        return n
    if n in ALIASES and ALIASES[n] in slugs:
        return ALIASES[n]
    # 性別サフィックス: -F → -female / -M → -male
    if n.endswith("-f") and n[:-2] + "-female" in slugs:
        return n[:-2] + "-female"
    if n.endswith("-m") and n[:-2] + "-male" in slugs:
        return n[:-2] + "-male"
    # 性別ありメガ: 例 meowstic-m-mega → meowstic-male-mega
    m = re.match(r"(.+)-([mf])-mega(.*)$", n)
    if m:
        cand = "%s-%s-mega%s" % (m.group(1),
                                 "male" if m.group(2) == "m" else "female",
                                 m.group(3))
        if cand in slugs:
            return cand
    # 接頭辞が一意な場合のみデフォルトフォルムとして採用
    pref = [s for s in slugs if s.startswith(n + "-")]
    if len(pref) == 1:
        return pref[0]
    return None


def main():
    existing = {}
    if USAGE_PATH.exists():
        try:
            existing = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing_month = existing.get("source_stats_month") or ""

    slug2name = {}
    if DB_PATH.exists():
        try:
            db = json.loads(DB_PATH.read_text(encoding="utf-8"))
            slug2name = {p["slug"]: p["n"] for p in db.get("pokemon", [])
                         if p.get("slug") and p.get("n")}
        except Exception:
            slug2name = {}
    slugs = set(slug2name)
    if not slugs:
        print("DB(pokemon.json)が読めないため、既存の usage.json を維持しました。")
        return 0

    for month in candidate_months():
        if existing_month and month <= existing_month:
            print(f"月 {month} は既存データ({existing_month})以下なので上書きしません。")
            return 0
        for cutoff in CUTOFFS:
            fmt = f"{FORMAT_BASE}-{cutoff}"
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
            info = chaos.get("info") or {}
            rows = sorted(data.items(),
                          key=lambda kv: kv[1].get("usage", 0), reverse=True)
            # 名前マッピングと安全弁（上位50のうち40件以上マッピングできること）
            mapped_rows = []
            top50_mapped = 0
            for i, (name, v) in enumerate(rows):
                slug = map_to_slug(name, slugs)
                if slug and i < 50:
                    top50_mapped += 1
                mapped_rows.append((name, v, slug))
            if top50_mapped < 40:
                print(f"マッピング不足 (上位50中 {top50_mapped}件) のため採用しません: {url}")
                continue
            entries = []
            for i, (name, v, slug) in enumerate(mapped_rows):
                usage = v.get("usage")
                pct = round(usage * 100, 2) if isinstance(usage, (int, float)) else None
                entries.append({
                    "name": slug2name.get(slug, name),
                    "rank": i + 1,
                    "usage_pct": pct,
                    "name_en": name,
                    "slug": slug,
                })
            battles = info.get("number of battles")
            doc = {
                "format": "singles",
                "regulation": "M-C",
                "season": f"Smogon {month}",
                "source": "Smogon公式統計（Pokémon Showdown）Champions BSS Reg M-C",
                "source_url": url,
                "source_stats_month": month,
                "period": f"{month} 集計分（cutoff {cutoff}"
                          + (f"、対戦数 {battles}" if battles else "") + "）",
                "updated_at": datetime.now(
                    timezone(timedelta(hours=9))).strftime("%Y-%m-%d"),
                "note": "Showdownラダーの集計であり、ゲーム内ランクバトルの使用率とは"
                        "母集団が異なる。使用率%はchaos JSONの usage を百分率化した実測値。"
                        "ダブル(VGC)のデータは含まない。",
                "entries": entries,
            }
            USAGE_PATH.write_text(
                json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
            mapped_total = sum(1 for _, _, s in mapped_rows if s)
            print(f"更新しました: {url} ({len(entries)}件, "
                  f"マッピング {mapped_total}/{len(mapped_rows)}, "
                  f"上位50マッピング {top50_mapped}/50)")
            return 0
    print("採用できるデータがなかったため、既存の usage.json を維持しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
