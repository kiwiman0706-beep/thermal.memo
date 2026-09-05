# thermal.memo for Android

他アプリの「共有」からそのままサーマルプリンタへ流せる Android アプリ。
デスクトップ版と同じ「1bit 画像を ESC/POS ラスタで TCP 9100 に送る」方式なので、
**サーバもクラウドも介さず**、院内 Wi-Fi から直接印刷します。

## 対応インテント

| どこから | インテント | 挙動 |
| --- | --- | --- |
| 任意のアプリの「共有」→ テキスト | `ACTION_SEND` `text/plain` | メモ画面に読み込み。**編集してから**印刷できる。件名は見出しとして印字 |
| 任意のアプリで文字列を選択 → メニュー | `ACTION_PROCESS_TEXT` | 選択したテキストをそのまま取り込む（ブラウザ・メール・PDF ビューア等どこでも） |
| ギャラリー・カメラ・スクショの共有 | `ACTION_SEND` `image/*` | 二値化（ディザ／しきい値）としきい値・幅をその場で調整して印刷 |
| ファイルアプリ等から PDF の共有 | `ACTION_SEND` `application/pdf` | ページを画像として描画。ページ送り・全ページ印刷（最大 20 ページ） |
| 複数画像の共有 | `ACTION_SEND_MULTIPLE` `image/*` | 縦に連結して 1 枚として印刷 |

スクショを撮って共有シートから「thermal.memo」を選べば、そのまま手帳用に出せます。

## 画面

- **メモ**: 本文・文字サイズ・部数・日時印字。プレビューは実際に印字されるドットそのもの
- **共有（画像 / PDF）**: プレビュー＋二値化調整＋キャプション
- **設定**: IP・ポート・用紙幅プリセット・カット・フィード・分割行数、接続テスト、テストページ
- **履歴**: 端末内に保存した印刷を検索・再印刷・プレビュー・削除

## ビルド

### GitHub Actions（推奨・手元に何も要らない）

`mobile/` を含むコミットを push すると
[`.github/workflows/android.yml`](../.github/workflows/android.yml) が APK をビルドします。
Actions の実行ページ → **Artifacts → `thermal-memo-apk`** をダウンロードしてください。
デバッグ署名済みなので、そのまま端末にサイドロードできます。

### 手元の Android Studio / CLI

```bash
cd mobile
./gradlew assembleDebug
# mobile/app/build/outputs/apk/debug/app-debug.apk
```

Android Studio で `mobile/` を開いてもそのままビルドできます。
必要なもの: JDK 17、Android SDK（compileSdk 35 / build-tools 35）。

### 端末へのインストール

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

adb を使わない場合は APK を端末に転送し、「不明なアプリのインストール」を許可して開きます。

## 設計

- **外部ライブラリはゼロ**。AndroidX も使わない素の SDK だけで書いてあるため、
  依存解決で壊れることがなく APK も小さい
- `EscPos.java` は `thermal_memo/escpos.py` の移植。
  **黒い画素にだけビットを立てる**実装なので、行末パディングが黒帯になる問題は原理的に起きない
  （Python 版は反転方式なのでマスクが要る。詳細は [docs/PROTOCOL.md](../docs/PROTOCOL.md)）
- 日本語は `Canvas` + `StaticLayout` で描画してから二値化する。
  プリンタ内蔵フォントやコードページに依存しないのはデスクトップ版と同じ考え方
- 履歴は端末内 SQLite ＋ PNG（`getFilesDir()/history/`）

```
mobile/app/src/main/java/jp/thermalmemo/
├── EscPos.java          ESC/POS コマンド生成（UI 非依存）
├── PrinterClient.java   TCP 9100 への送信・接続テスト
├── Renderer.java        テキスト→Bitmap、二値化、拡縮・連結
├── PdfSource.java       PdfRenderer による PDF ページ描画
├── Printing.java        送信 + 履歴記録（ワーカースレッド）
├── Settings.java        SharedPreferences
├── HistoryStore.java    SQLite 履歴
├── MainActivity.java    メモ画面（テキスト共有・PROCESS_TEXT の受け口）
├── ShareActivity.java   画像 / PDF 共有の受け口
├── SettingsActivity.java
└── HistoryActivity.java
```

## デスクトップ版との違い

| | デスクトップ | Android |
| --- | --- | --- |
| PDF | サムネイル / **テキスト抽出** を選択 | ページ画像のみ（標準 API にテキスト抽出が無いため） |
| 二値化 | ディザ / しきい値 / 適応的 | ディザ / しきい値 |
| Word (.docx) | テキスト抽出可 | 非対応（PDF に書き出して共有してください） |
| 履歴の同期 | 同期フォルダへ Markdown + PNG | 端末内のみ（v2 で対応予定） |

## 実機なしで試す

PC でデスクトップ版の擬似プリンタを動かし、その PC の IP を設定に入れると
送信内容が PNG として復元されます。

```bash
python tools/fake_printer.py --host 0.0.0.0 --port 9100 --outdir out
```

## 既知の制限・今後

- 履歴のクラウド同期は未実装（デスクトップ版が書き出す `index.ndjson` と
  `YYYY/MM/*.md` を読む形で揃える予定）
- Bluetooth 接続のモバイルプリンタは未対応。バイト列生成は共通なので、
  送信層（`PrinterClient`）を差し替えれば載る
- iOS 版は別途必要（同じ ESC/POS 方式で作れる。`docs/MOBILE.md` 参照）
