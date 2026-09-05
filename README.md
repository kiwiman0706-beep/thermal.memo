# thermal.memo

クリニックの事務作業中に「システム手帳に貼る用のメモ」を LAN サーマルプリンタで
サッと出すためのデスクトップ小物アプリ。Windows / macOS 両対応（Python + Tkinter）。

```
┌ テキスト ──────────┐   ┌ プレビュー ─────┐
│ メモを打つ → Ctrl+P     │   │ 実際に印字される │
│ 定型文 / 見出し / 日時   │ → │ 1bit ドットを    │ → LAN 9100 → 🖨
│ スクショ（二値化調整）   │   │ そのまま表示     │
│ PDF/Word（サムネ/文字）  │   └──────────────┘
└──────────────────┘   すべて履歴に残る（＋同期フォルダへ書き出し）
```

## できること

| 機能 | 内容 |
| --- | --- |
| テキスト印刷 | テキストボックスに入力 → 日時・見出し・罫線つきで印刷。定型文ボタン（受付メモ / TODO / 電話メモ / 申し送り） |
| スクショ印刷 | OS 標準の範囲選択・内蔵オーバーレイ選択・画面全体・クリップボード貼り付け。**二値化（ディザ / しきい値 / 適応的）をスライダで調整**しながらプレビュー |
| ファイル取り込み | PDF・Word・テキスト・画像を読み込み、**「サムネイル」か「テキスト抽出」を選択**。ページ指定（`1,3-5`）、OCR、抽出後の手直しも可能 |
| 履歴 | 全印刷を SQLite に保存（画像＋本文）。検索・再印刷・PNG 書き出し・削除 |
| クラウド同期 | 指定した同期フォルダへ Markdown + PNG を自動書き出し（Google ドライブ等のフォルダを指定） |
| CLI | `python -m thermal_memo print-text "…"` など。他ツールからの自動印刷に |

日本語は**すべて画像化して送信**しているため、プリンタ内蔵フォントやコードページに
依存せず、外字・記号（髙﨑 ①② ㎎ ℃ 等）もそのまま印字できます。

## 動作要件

- Python 3.10 以降（Tkinter 同梱のもの。macOS は `brew install python-tk` が必要な場合あり）
- ESC/POS 対応の LAN サーマルプリンタ（RAW / port 9100。Epson TM シリーズや互換機の標準的な方式）

```bash
pip install -r requirements.txt   # 必須は Pillow のみ。他は任意（無ければその機能だけ無効）
```

| 任意ライブラリ | 無いとどうなるか |
| --- | --- |
| PyMuPDF | PDF のサムネイル不可（テキスト抽出は pdfplumber で代替） |
| python-docx | .docx のテキスト抽出不可 |
| opencv-python | 「適応的」二値化がしきい値方式に退化 |
| pytesseract（＋Tesseract 本体） | 画像 PDF の OCR 不可 |
| tkinterdnd2 | ウィンドウへのファイル D&D 不可（ファイル選択ダイアログは使える） |

## 起動

```bash
python run.py            # GUI
python -m thermal_memo   # 同上
```

Windows でコンソールを出したくない場合は `pythonw run.py`（ショートカットを作ると便利）。

## 初回設定

1. `設定` タブでプリンタの **IP アドレス**とポート（通常 9100）を入力
   - IP が分からなければ `LAN を探す` で同一サブネットの 9100 番を並列スキャン
2. `用紙幅` を選ぶ（203dpi の場合 58mm→384dot、80mm→576dot）
3. `接続テスト`（用紙を消費しない）→ `テストページを印刷` で実際の印字を確認
4. 印字が途中で切れる／文字化けする場合は `分割行数` を 128 → 64 に下げる

設定は `%APPDATA%\thermal.memo\config.json`（Win）／
`~/Library/Application Support/thermal.memo/config.json`（Mac）に保存されます。
リポジトリ直下に `local_config.json` を置くとそちらが優先されます（USB 持ち運び運用向け）。

## ショートカット

| キー | 動作 |
| --- | --- |
| `Ctrl+P` | 現在のタブの内容を印刷 |
| `Ctrl+Enter`（テキスト欄） | そのまま印刷 |
| `Ctrl+1`〜`Ctrl+4` | タブ切り替え |

## 履歴とクラウド同期について

**Google Keep への直接保存は実装していません。** Keep には個人アカウントで使える公開 API が
無いためです（Keep API は Google Workspace の管理者向けで、一般ユーザーのメモ操作には使えず、
`gkeepapi` などの非公式ライブラリはアカウントロックのリスクと突然の破損があります）。

代わりに次の構成にしています。

1. **ローカル SQLite**（`history.sqlite3` ＋ PNG）… 検索・再印刷の正データ
2. **同期フォルダへの書き出し** … `履歴` タブで Google ドライブ / iCloud / Dropbox の
   ローカル同期フォルダを指定すると、印刷のたびに
   `YYYY/MM/20260905-142312-00042.md` と同名の PNG が置かれます。
   Markdown なので**スマホの Drive アプリからそのまま読めます**（Keep 的な使い方ができます）。
   併せて `index.ndjson` に 1 行 1 レコードの機械可読ログを追記します。

将来 Drive API や自前サーバへ同期したくなった場合は `thermal_memo/history.py` の
`export_entry()` だけを差し替えれば済むようにしてあります。

## CLI

```bash
python -m thermal_memo test                                   # 接続テスト
python -m thermal_memo test-page                              # テストページ
python -m thermal_memo print-text "13:00 往診 山田さん"        # テキスト印刷
echo "標準入力からも印刷できます" | python -m thermal_memo print-text
python -m thermal_memo print-file 案内.pdf --mode thumbnail --pages 1
python -m thermal_memo --host 192.168.1.50 --width 384 print-text "58mm 機へ"
```

## 実機なしで試す

擬似プリンタを立ち上げると、送信した ESC/POS を PNG に復元して保存します。

```bash
python tools/fake_printer.py --port 9100 --outdir out
python -m thermal_memo --host 127.0.0.1 print-text "テスト"   # out/*.png を確認
```

## 開発

```
thermal_memo/
├── escpos.py     ESC/POS コマンド生成（GUI・通信に非依存。スマホ版の参照実装）
├── printer.py    TCP 9100 への送信・接続テスト・LAN スキャン
├── render.py     テキスト→1bit 画像、画像の二値化
├── capture.py    スクリーンショット（OS 標準 / 内蔵オーバーレイ / クリップボード）
├── documents.py  PDF・Word・テキストの取り込み（サムネ / テキスト抽出 / OCR）
├── history.py    SQLite 履歴と同期フォルダ書き出し
├── config.py     設定
├── app.py        メインウィンドウ
└── ui/           各タブ
```

```bash
python -m unittest discover -s tests -v
```

- [docs/PROTOCOL.md](docs/PROTOCOL.md) — 送っている ESC/POS バイト列の仕様
- [docs/MOBILE.md](docs/MOBILE.md) — スピンオフのスマホアプリ設計
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — 印字トラブル対処

## 注意

`LAN を探す` は自分の管理下のネットワークでのみ使用してください。
院内ネットワークの機器構成やセキュリティ方針については、事前に管理者の確認を取ることをおすすめします。
