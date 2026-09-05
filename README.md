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

Android 版は他アプリの「共有」から直接: 共有シート → thermal.memo → 🖨
```

## できること

| 機能 | 内容 |
| --- | --- |
| テキスト印刷 | テキストボックスに入力 → 日時・見出し・罫線つきで印刷。定型文ボタン（受付メモ / TODO / 電話メモ / 申し送り） |
| スクショ印刷 | OS 標準の範囲選択・内蔵オーバーレイ選択・画面全体・クリップボード貼り付け。**二値化（ディザ / しきい値 / 適応的）をスライダで調整**しながらプレビュー |
| ファイル取り込み | PDF・Word・テキスト・画像を読み込み、**「サムネイル」か「テキスト抽出」を選択**。ページ指定（`1,3-5`）、OCR、抽出後の手直しも可能 |
| QR 印刷 | 任意の URL・テキストを QR にして印刷。**ファイルを Google ドライブに上げてそのリンクの QR を出す**導線つき（手帳に貼れば実体はクラウド） |
| 履歴 | 全印刷を SQLite に保存（画像＋本文）。検索・再印刷・PNG 書き出し・削除 |
| アーカイブ | ① 同期フォルダへ Markdown + PNG ② **印刷のたびに自分宛メール**（Gmail のフィルタでラベル自動付与） |
| CLI | `python -m thermal_memo print-text "…"` など。他ツールからの自動印刷に |

日本語は**すべて画像化して送信**しているため、プリンタ内蔵フォントやコードページに
依存せず、外字・記号（髙﨑 ①② ㎎ ℃ 等）もそのまま印字できます。

## スマホからも印刷できます（Android）

[`mobile/`](mobile) に Android アプリがあります。**他アプリの「共有」から直接印刷**できます。

| どこから | 挙動 |
| --- | --- |
| 共有シート → テキスト | メモ画面に読み込み、編集してから印刷 |
| 文字列を選択 → メニュー | 選択したテキストをそのまま印刷（どのアプリでも） |
| 共有シート → 画像・スクショ | 二値化を調整して印刷 |
| 共有シート → PDF | ページを描画して印刷（ページ送り・全ページ） |
| 共有シート → 複数画像 | 縦に連結して 1 枚として印刷 |

APK は `mobile/` を含むコミットを push すると GitHub Actions が作ります
（Actions の実行ページ → Artifacts → `thermal-memo-apk`）。
手元でビルドするなら `cd mobile && ./gradlew assembleDebug`。
詳細は [mobile/README.md](mobile/README.md)。

## インストール

[リリースページ](https://github.com/kiwiman0706-beep/thermal.memo/releases/latest)
から環境に合うものを取ってください。Python を入れなくても動きます。

| 環境 | ファイル | 備考 |
| --- | --- | --- |
| Windows | `...-windows-setup.exe` | **管理者権限は不要**（ユーザー領域に入ります） |
| Windows（持ち運び） | `...-windows-portable.exe` | インストール不要の単一 exe |
| macOS (Apple Silicon) | `...-macos-arm64.dmg` | 初回は右クリック →「開く」 |
| macOS (Intel) | `...-macos-x86_64.dmg` | 同上 |
| Android | `...-android.apk` | 「不明なアプリのインストール」の許可が要ります |

署名していないため、Windows は SmartScreen、macOS は Gatekeeper の警告が出ます
（[docs/RELEASE.md](docs/RELEASE.md) に回避手順）。

**更新は自動です。** 起動時に GitHub Releases を確認し、新しい版があれば知らせます。
ダウンロードしたファイルは `SHA256SUMS.txt` と突き合わせてから適用します。
`設定 → 更新` で自動確認の有無を切り替えられます。

ソースから動かす場合は下記のとおりです。

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
| `Ctrl+1`〜`Ctrl+5` | タブ切り替え |

## 履歴の残し方（3 通り、併用できます）

**Google Keep への直接保存は実装していません。** Keep には個人アカウントで使える公開 API が
無いためです（Keep API は Google Workspace の管理者向けで、一般ユーザーのメモ操作には使えず、
`gkeepapi` などの非公式ライブラリはアカウントロックのリスクと突然の破損があります）。
代わりに次の 3 つを用意しました。

### 1. ローカル SQLite（既定でオン）

`history.sqlite3` ＋ PNG。検索・再印刷の正データです。

### 2. 同期フォルダへの書き出し

`履歴` タブで Google ドライブ / iCloud / Dropbox のローカル同期フォルダを指定すると、
印刷のたびに `YYYY/MM/20260905-142312-00042.md` と同名の PNG が置かれます。
Markdown なのでスマホの Drive アプリからそのまま読めます。
併せて `index.ndjson` に 1 行 1 レコードの機械可読ログを追記します。

### 3. 自分宛メール → Gmail で管理（既定でオフ）

印刷のたびに本文＋印字画像を自分宛へ送ります。Gmail のフィルタでラベルを自動付与すれば、
**全文検索が効いてスマホでもそのまま読める**アーカイブになります。
SMTP + アプリパスワードで動くので Gmail API の設定は不要です。

送信先を `you+memo@gmail.com` のようなプラスアドレスにしておくと、
件名の文字列に依存しない確実なフィルタが作れます。
アプリパスワードは平文で保存せず、OS の資格情報ストア（keyring / Windows DPAPI /
macOS キーチェーン）に入れます。

> 患者情報を含みうる内容を外部のメールサービスへ送ることになります。
> 院内の運用方針を確認したうえで有効にしてください。既定はオフです。

手順は **[docs/GMAIL.md](docs/GMAIL.md)**。

## QR で「紙に貼れないもの」を手帳に貼る

`QR` タブで任意の URL・テキストを QR にして印刷できます。
**ファイルを Google ドライブにアップロードして、そのリンクの QR を出す**ボタンもあります
（実体はクラウド、手帳には QR だけ貼る）。

- ドライブ連携なしでも、コピーしたリンクを貼り付ければ QR は出せます
- 共有設定は**既定で変更しません**（自分のアカウントで開くだけなら公開不要）。
  「リンクを知っている全員に公開」は明示的なチェックと確認ダイアログつき
- 誤り訂正は既定 **Q**（サーマル印字は経時で薄れるため）。URL を文字でも併記できます

手順は **[docs/DRIVE_QR.md](docs/DRIVE_QR.md)**。

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
├── qrcodes.py    QR コードの生成（整数倍拡大で読み取り率を確保）
├── mailer.py     自分宛アーカイブメールの組み立てと SMTP 送信
├── credentials.py アプリパスワードの保管（keyring / DPAPI / キーチェーン）
├── drive.py      Google ドライブへのアップロードとリンク取得
├── updater.py    GitHub Releases を見て自動更新
├── history.py    SQLite 履歴と同期フォルダ書き出し
├── config.py     設定
├── app.py        メインウィンドウ
└── ui/           各タブ
```

```bash
python -m unittest discover -s tests -v
```

- [CHANGELOG.md](CHANGELOG.md) — 変更履歴
- [docs/RELEASE.md](docs/RELEASE.md) — リリースの出し方・署名・自動更新の仕組み
- [docs/GMAIL.md](docs/GMAIL.md) — 印刷の控えを Gmail に貯める（アプリパスワード・フィルタ）
- [docs/DRIVE_QR.md](docs/DRIVE_QR.md) — ドライブへアップして QR を貼る（OAuth 設定・共有の考え方）
- [docs/PROTOCOL.md](docs/PROTOCOL.md) — 送っている ESC/POS バイト列の仕様
- [mobile/README.md](mobile/README.md) — Android 版（対応インテント・ビルド方法）
- [docs/MOBILE.md](docs/MOBILE.md) — スマホ版の設計判断と iOS 版の方針
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — 印字トラブル対処

Android 版の ESC/POS 生成は、Python 版と同じバイト列を吐くことを CI のユニットテストで
突き合わせています（`mobile/app/src/test/java/jp/thermalmemo/EscPosTest.java`）。

## 注意

`LAN を探す` は自分の管理下のネットワークでのみ使用してください。
院内ネットワークの機器構成やセキュリティ方針については、事前に管理者の確認を取ることをおすすめします。
