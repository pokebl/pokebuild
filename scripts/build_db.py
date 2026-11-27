#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PokeBuild 用ポケモンデータベース生成スクリプト（ビルド時一括取得）

- 取得元: PokeAPI (https://pokeapi.co/api/v2) 無料・認証不要
- フェアユースポリシー: 「ローカルにキャッシュすること」が条件。
  そのためユーザー端末から毎回叩かず、本スクリプトで一度だけ取得して
  data/pokemon.json として同梱する方式を取る。
- リクエスト間隔は 0.25 秒（要件 0.15 秒以上）。User-Agent を明示する
  （UAなしだと PokeAPI 側ファイアウォールで 403 になることを実測確認）。
- 取得に失敗したポケモンは、元アプリ内蔵データ（タイプ/素早さ/特性）で補完し、
  全種族値が欠ける場合は stats を null とする。数値の捏造はしない。
"""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE = "https://pokeapi.co/api/v2"
UA = {"User-Agent": "PokeBuild/1.0 (personal non-commercial project; build-time fetch)"}
INTERVAL = 0.25

TYPE_EN_JA_IDX = {  # PokeAPI英語タイプ名 -> アプリ内タイプ番号(0-17)
    "normal": 0, "fire": 1, "water": 2, "electric": 3, "grass": 4, "ice": 5,
    "fighting": 6, "poison": 7, "ground": 8, "flying": 9, "psychic": 10,
    "bug": 11, "rock": 12, "ghost": 13, "dragon": 14, "dark": 15,
    "steel": 16, "fairy": 17,
}

# 元アプリ内蔵データ（フォールバック用、そのまま転記）
# 形式: 日本語名|タイプ番号(カンマ区切り)|S種族値|特性(カンマ区切り)
FALLBACK_RAW = """ガブリアス|14,8|102|さめはだ,すながくれ
アシレーヌ|2,17|60|げきりゅう,うるおいボイス
カバルドン|8|47|すなおこし,すなのちから
ブリジュラス|16,14|85|じきゅうりょく,がんじょう,すじがねいり
ルカリオ|6,16|90|せいしんりょく,ふくつのこころ,せいぎのこころ
ミミッキュ|13,17|96|ばけのかわ
リザードン|1,9|100|もうか,サンパワー
イダイトウ（オス）|2,13|78|すいすい,てきおうりょく,かたやぶり
ボーマンダ|14,9|100|いかく,じしんかじょう
サーフゴー|16,13|84|おうごんのからだ
マスカーニャ|4,15|123|しんりょく,へんげんじざい
アーマーガア|9,16|67|ミラーアーマー,プレッシャー,きんちょうかん
カイリュー|14,9|80|マルチスケイル,せいしんりょく
ゴリランダー|4|85|グラスメイカー,しんりょく
メタグロス|16,10|70|クリアボディ,ライトメタル
セグレイブ|14,5|87|ねつこうかん,アイスボディ
キラフロル|12,7|86|どくげしょう,ふしょく
ギャラドス|2,9|81|いかく,じしんかじょう
エースバーン|1|119|もうか,リベロ
ブラッキー|15|65|シンクロ,せいしんりょく
ゲンガー|13,7|110|のろわれボディ
ヒートロトム|3,1|86|ふゆう
ウォッシュロトム|3,2|86|ふゆう
ゲッコウガ|2,15|122|げきりゅう,へんげんじざい,きずなへんげ
ドドゲザン|15,16|50|そうだいしょう,まけんき,プレッシャー
バシャーモ|1,6|80|かそく,もうか
ラグラージ|2,8|60|げきりゅう,しめりけ
バンギラス|12,15|61|すなおこし,きんちょうかん
ウルガモス|11,1|100|ほのおのからだ,むしのしらせ
オオニューラ|6,7|120|かるわざ,プレッシャー,どくしゅ
アローラキュウコン|5,17|109|ゆきふらし,ゆきがくれ
ピクシー|17|60|てんねん,マジックガード,メロメロボディ
サザンドラ|15,14|98|ふゆう
ドヒドイデ|7,2|35|さいせいりょく,ひとでなし,じゅうなん
ハッサム|11,16|65|テクニシャン,むしのしらせ,ライトメタル
ラウドボーン|1,13|66|てんねん,もうか
ソウブレイズ|1,13|85|もらいび,くだけるよろい
ペリッパー|2,9|65|あめふらし,するどいめ,あめうけざら
オーロンゲ|15,17|60|いたずらごころ,おみとおし,わるいてぐせ
ドリュウズ|8,16|88|かたやぶり,すなかき,すなのちから
サーナイト|10,17|80|トレース,シンクロ,テレパシー
ヒスイヌメルゴン|16,14|60|そうしょく,シェルアーマー,ぬめぬめ
エンペルト|2,16|60|げきりゅう,かちき
ニンフィア|17|60|フェアリースキン,メロメロボディ
ドラパルト|14,13|142|すりぬけ,クリアボディ,のろわれボディ
カビゴン|0|30|あついしぼう,めんえき,くいしんぼう
マンムー|5,8|80|あついしぼう,どんかん,ゆきがくれ
エアームド|16,9|70|がんじょう,するどいめ,くだけるよろい
コノヨザル|6,13|90|まけんき,やるき,せいしんりょく
エルフーン|4,17|116|いたずらごころ,すりぬけ,ようりょくそ
マリルリ|2,17|50|ちからもち,そうしょく,あついしぼう
ガオガエン|1,15|60|いかく,もうか
シャワーズ|2|65|ちょすい,うるおいボディ
ミミズズ|16|65|どしょく,すながくれ
シャンデラ|13,1|80|もらいび,すりぬけ,ほのおのからだ
グライオン|8,9|95|ポイズンヒール,かいりきバサミ,すながくれ
シビルドン|3|50|ふゆう
キョジオーン|12|35|きよめのしお,がんじょう,クリアボディ
サンダース|3|130|ちくでん,はやあし
ヤバソチャ|4,13|70|たいねつ,おもてなし
ヌメルゴン|14|80|そうしょく,うるおいボディ,ぬめぬめ
デカヌチャン|17,16|94|かたやぶり,マイペース,わるいてぐせ
メガリザードンX|1,14|100|かたいツメ
メガリザードンY|1,9|100|ひでり
メガルカリオ|6,16|112|てきおうりょく
メガギャラドス|2,15|81|かたやぶり
メガボーマンダ|14,9|120|スカイスキン
メガメタグロス|16,10|110|かたいツメ
メガゲンガー|13,7|130|かげふみ"""

# 対象ポケモン: (PokeAPI slug, 期待する日本語表示名)
# 元69匹 + GameWith シーズンM-8 シングル使用率リスト掲載ポケモン + 代表メガ
TARGETS = [
    ("garchomp", "ガブリアス"), ("primarina", "アシレーヌ"), ("hippowdon", "カバルドン"),
    ("archaludon", "ブリジュラス"), ("lucario", "ルカリオ"), ("mimikyu-disguised", "ミミッキュ"),
    ("charizard", "リザードン"), ("basculegion-male", "イダイトウ（オス）"),
    ("salamence", "ボーマンダ"), ("gholdengo", "サーフゴー"), ("meowscarada", "マスカーニャ"),
    ("corviknight", "アーマーガア"), ("dragonite", "カイリュー"), ("rillaboom", "ゴリランダー"),
    ("metagross", "メタグロス"), ("baxcalibur", "セグレイブ"), ("glimmora", "キラフロル"),
    ("gyarados", "ギャラドス"), ("cinderace", "エースバーン"), ("umbreon", "ブラッキー"),
    ("gengar", "ゲンガー"), ("rotom-heat", "ヒートロトム"), ("rotom-wash", "ウォッシュロトム"),
    ("greninja", "ゲッコウガ"), ("kingambit", "ドドゲザン"), ("blaziken", "バシャーモ"),
    ("swampert", "ラグラージ"), ("tyranitar", "バンギラス"), ("volcarona", "ウルガモス"),
    ("sneasler", "オオニューラ"), ("ninetales-alola", "アローラキュウコン"),
    ("clefable", "ピクシー"), ("hydreigon", "サザンドラ"), ("toxapex", "ドヒドイデ"),
    ("scizor", "ハッサム"), ("skeledirge", "ラウドボーン"), ("ceruledge", "ソウブレイズ"),
    ("pelipper", "ペリッパー"), ("grimmsnarl", "オーロンゲ"), ("excadrill", "ドリュウズ"),
    ("gardevoir", "サーナイト"), ("goodra-hisui", "ヒスイヌメルゴン"),
    ("empoleon", "エンペルト"), ("sylveon", "ニンフィア"), ("dragapult", "ドラパルト"),
    ("snorlax", "カビゴン"), ("mamoswine", "マンムー"), ("skarmory", "エアームド"),
    ("annihilape", "コノヨザル"), ("whimsicott", "エルフーン"), ("azumarill", "マリルリ"),
    ("incineroar", "ガオガエン"), ("vaporeon", "シャワーズ"), ("orthworm", "ミミズズ"),
    ("chandelure", "シャンデラ"), ("gliscor", "グライオン"), ("eelektross", "シビルドン"),
    ("garganacl", "キョジオーン"), ("jolteon", "サンダース"), ("sinistcha", "ヤバソチャ"),
    ("goodra", "ヌメルゴン"), ("tinkaton", "デカヌチャン"),
    ("charizard-mega-x", "メガリザードンX"), ("charizard-mega-y", "メガリザードンY"),
    ("lucario-mega", "メガルカリオ"), ("gyarados-mega", "メガギャラドス"),
    ("salamence-mega", "メガボーマンダ"), ("metagross-mega", "メガメタグロス"),
    ("gengar-mega", "メガゲンガー"),
    # --- GameWith M-8 シングル上位リスト追加分 ---
    ("golisopod", "グソクムシャ"), ("indeedee-male", "イエッサン（オス）"),
    ("raichu", "ライチュウ"), ("floette-eternal", "フラエッテ（えいえんのはな）"),
    ("pawmot", "パーモット"), ("aegislash-shield", "ギルガルド"),
    ("samurott-hisui", "ヒスイダイケンキ"), ("blastoise", "カメックス"),
    ("staraptor", "ムクホーク"), ("slowking-galar", "ガラルヤドキング"),
    ("starmie", "スターミー"), ("scovillain", "スコヴィラン"), ("delphox", "マフォクシー"),
    ("venusaur", "フシギバナ"), ("hatterene", "ブリムオン"), ("mawile", "クチート"),
    ("meganium", "メガニウム"), ("ditto", "メタモン"), ("vanilluxe", "バイバニラ"),
    ("banette", "ジュペッタ"), ("bellibolt", "ハラバリー"), ("lopunny", "ミミロップ"),
    ("kleavor", "バサギリ"), ("zoroark-hisui", "ヒスイゾロアーク"),
    ("espathra", "クエスパトラ"), ("milotic", "ミロカロス"), ("absol", "アブソル"),
    ("gallade", "エルレイド"), ("politoed", "ニョロトノ"),
    # --- 代表メガシンカ（フォルム違いを個別エントリに） ---
    ("venusaur-mega", "メガフシギバナ"), ("blastoise-mega", "メガカメックス"),
    ("mawile-mega", "メガクチート"), ("banette-mega", "メガジュペッタ"),
    ("lopunny-mega", "メガミミロップ"), ("absol-mega", "メガアブソル"),
    ("gallade-mega", "メガエルレイド"), ("gardevoir-mega", "メガサーナイト"),
    ("scizor-mega", "メガハッサム"), ("tyranitar-mega", "メガバンギラス"),
    ("blaziken-mega", "メガバシャーモ"), ("swampert-mega", "メガラグラージ"),
]

# GameWith シーズンM-8 シングル使用率リスト（順位順）。ここに載る名前は reg="mc_listed"
MC_LISTED = """ガブリアス,アシレーヌ,カバルドン,ブリジュラス,ルカリオ,ミミッキュ,グソクムシャ,リザードン,イダイトウ（オス）,ボーマンダ,サーフゴー,マスカーニャ,アーマーガア,カイリュー,ゴリランダー,メタグロス,イエッサン（オス）,セグレイブ,キラフロル,ギャラドス,エースバーン,ブラッキー,ゲンガー,ヒートロトム,ゲッコウガ,ウォッシュロトム,ドドゲザン,バシャーモ,ライチュウ,フラエッテ（えいえんのはな）,ラグラージ,パーモット,バンギラス,ウルガモス,ギルガルド,オオニューラ,アローラキュウコン,ピクシー,ヒスイダイケンキ,サザンドラ,ドヒドイデ,カメックス,ハッサム,ムクホーク,ガラルヤドキング,ラウドボーン,スターミー,ソウブレイズ,スコヴィラン,マフォクシー,ペリッパー,オーロンゲ,フシギバナ,ドリュウズ,サーナイト,ヒスイヌメルゴン,ブリムオン,クチート,エンペルト,メガニウム,ニンフィア,メタモン,バイバニラ,ドラパルト,ジュペッタ,カビゴン,ハラバリー,ミミロップ,バサギリ,ヒスイゾロアーク,クエスパトラ,マンムー,ミロカロス,アブソル,エアームド,エルレイド,ニョロトノ""".split(",")


def parse_fallback():
    fb = {}
    for line in FALLBACK_RAW.strip().split("\n"):
        n, t, s, a = line.split("|")
        fb[n] = {"n": n, "t": [int(x) for x in t.split(",")], "s": int(s),
                 "a": a.split(","), "stats": None}
    return fb


def fetch_json(path):
    req = urllib.request.Request(BASE + path, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.load(res)


def ja_name(names, fallback):
    for e in names:
        if e.get("language", {}).get("name") == "ja":
            return e["name"]
    return fallback


def main():
    out_path = Path(__file__).resolve().parent.parent / "data" / "pokemon.json"
    fallback = parse_fallback()
    ability_cache = {}   # slug -> 日本語名（重複取得しない）
    species_cache = {}   # species slug -> 日本語名
    entries, failed = [], []

    def ability_ja(slug):
        if slug in ability_cache:
            return ability_cache[slug]
        time.sleep(INTERVAL)
        try:
            d = fetch_json(f"/ability/{slug}")
            name = ja_name(d.get("names", []), slug)
        except Exception:
            name = slug
        ability_cache[slug] = name
        return name

    for i, (slug, expected_ja) in enumerate(TARGETS):
        try:
            time.sleep(INTERVAL)
            poke = fetch_json(f"/pokemon/{slug}")
            types = [TYPE_EN_JA_IDX[t["type"]["name"]] for t in sorted(poke["types"], key=lambda x: x["slot"])]
            raw = [s["base_stat"] for s in poke["stats"]]  # hp,atk,def,spa,spd,spe
            stats = {"h": raw[0], "a": raw[1], "b": raw[2], "c": raw[3], "d": raw[4], "s": raw[5]}
            abilities = [ability_ja(a["ability"]["name"]) for a in poke["abilities"]]
            # 日本語名は species から取る
            sp_slug = poke["species"]["name"]
            if sp_slug not in species_cache:
                time.sleep(INTERVAL)
                try:
                    sp = fetch_json(f"/pokemon-species/{sp_slug}")
                    species_cache[sp_slug] = ja_name(sp.get("names", []), expected_ja)
                except Exception:
                    species_cache[sp_slug] = expected_ja
            name = expected_ja  # フォルム名はアプリ側の表示名を正とする（メガ/性別等の区別のため）
            entries.append({
                "id": len(entries), "slug": slug, "n": name, "t": types,
                "s": stats["s"], "stats": stats, "a": abilities,
                "reg": "mc_listed" if name in MC_LISTED else "base",
                "src": "pokeapi",
            })
            print(f"[{i+1}/{len(TARGETS)}] OK {slug} -> {name}")
        except Exception as e:
            print(f"[{i+1}/{len(TARGETS)}] FAIL {slug}: {e} -> フォールバック")
            failed.append(slug)
            fb = fallback.get(expected_ja)
            if fb:
                entries.append({
                    "id": len(entries), "slug": slug, "n": expected_ja, "t": fb["t"],
                    "s": fb["s"], "stats": None, "a": fb["a"],
                    "reg": "mc_listed" if expected_ja in MC_LISTED else "base",
                    "src": "fallback_embedded",
                })
            else:
                entries.append({
                    "id": len(entries), "slug": slug, "n": expected_ja, "t": [],
                    "s": None, "stats": None, "a": [],
                    "reg": "mc_listed" if expected_ja in MC_LISTED else "base",
                    "src": "unavailable",
                })
        # id を振り直す
        entries[-1]["id"] = len(entries) - 1

    doc = {
        "source": "PokeAPI (https://pokeapi.co/api/v2) - build-time fetch, locally cached per Fair Use Policy",
        "regulation_note": "reg='mc_listed' は GameWith シーズンM-8 シングル使用率リスト掲載（=レギュレーションM-C期間）。それ以外は出典未確認のため UI では『M-Cリスト掲載』絞り込み対象外として扱う。",
        "count": len(entries),
        "failed_slugs": failed,
        "pokemon": entries,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for e in entries if e["src"] == "pokeapi")
    print(f"\n生成完了: {out_path} / 全{len(entries)}件 (PokeAPI成功 {ok}件, フォールバック等 {len(entries)-ok}件)")


if __name__ == "__main__":
    main()
