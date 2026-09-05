# スマホ版について

## 現状

**Android 版は実装済み**（[`mobile/`](../mobile) / セットアップと対応インテントは
[mobile/README.md](../mobile/README.md)）。iOS 版は未着手。

Android は「他のアプリから共有で送って印刷する」用途と相性が良く、
共有シートとテキスト選択メニューの両方から入れるため、素の SDK（Java）で実装した。

| | 方式 | 状態 |
| --- | --- | --- |
| Android | 素の Android SDK（Java、AndroidX なし・外部依存ゼロ） | 実装済み |
| iOS | 下記の方針（Share Extension が必須） | 未着手 |

### なぜ Flutter ではなく素の Android SDK にしたか

当初は Flutter を想定していたが、この用途では素の SDK を選んだ。

- 中心機能が **共有インテントの受け取り**で、Flutter だとプラグイン頼み or
  プラットフォームチャネル経由になり、結局 Android 側のコードを書くことになる
- `PdfRenderer`（PDF ページ描画）と `StaticLayout`（日本語の折り返し）が
  標準 SDK に入っており、追加ライブラリが要らない
- 依存ゼロなので CI が壊れにくく、APK も小さい

iOS も作るとなれば話は変わる。その場合は共通ロジック（ESC/POS 生成・二値化）を
Flutter or Kotlin Multiplatform に寄せ、共有受け口だけ各 OS ネイティブにするのが素直。

## 移植の要点（iOS や他フレームワークへ）

印刷そのものは 3 つだけ移せば成立する。仕様は [PROTOCOL.md](PROTOCOL.md)。

1. **1bit へのパック** — 黒い画素にだけビットを立てる。
   反転方式にすると行末パディングが黒帯になるので、その場合はマスクが要る
2. **`GS v 0` の分割送信** — 既定 128 行ごと
3. **TCP 9100 へ書く** — 送信後 0.2 秒待ってから close

Swift ならこの程度で足りる。

```swift
func rasterChunks(packed: [UInt8], bytesPerRow: Int, height: Int,
                  chunkRows: Int = 128) -> [[UInt8]] {
    var chunks: [[UInt8]] = []
    var top = 0
    while top < height {
        let rows = min(chunkRows, height - top)
        var command: [UInt8] = [0x1D, 0x76, 0x30, 0x00,
                                UInt8(bytesPerRow & 0xFF), UInt8((bytesPerRow >> 8) & 0xFF),
                                UInt8(rows & 0xFF), UInt8((rows >> 8) & 0xFF)]
        command += packed[(top * bytesPerRow)..<((top + rows) * bytesPerRow)]
        chunks.append(command)
        top += chunkRows
    }
    return chunks
}
```

検証は PC で `tools/fake_printer.py` を動かし、スマホからその PC の IP へ送る。
復元された PNG がデスクトップ版と一致すれば移植成功。

## iOS を作る場合の注意

- 共有シートに出すには **Share Extension** が必要（アプリ本体だけでは出ない）。
  テキスト選択メニューからの起動は Android の `ACTION_PROCESS_TEXT` に相当するものが無く、
  共有シート経由になる
- ローカルネットワークへの接続に許可ダイアログが要る
  （`Info.plist` に `NSLocalNetworkUsageDescription`。Bonjour を使うなら `NSBonjourServices` も）
- 実機配布には Apple Developer Program が要る。院内数台なら
  無料プロビジョニング（7 日ごとに再署名）か Ad Hoc 配布で足りる

## Android 版の残タスク

- 履歴のクラウド同期（デスクトップ版が書き出す `index.ndjson` と `YYYY/MM/*.md` を読む形に揃える）
- Bluetooth プリンタ対応（送信層の差し替えのみ）
- クイック設定タイル、ホーム画面ウィジェットからの直接印刷

## 注意

患者情報を扱いうるため、端末のパスコード必須化と、
クラウド同期を足す場合の共有範囲は事前に確認すること。
