# スピンオフ：スマホアプリの設計メモ

デスクトップ版と同じ「1bit 画像を ESC/POS ラスタで TCP 9100 に流す」方式なので、
スマホからも**サーバなしで直接**印刷できる（同じ院内 Wi-Fi にいることが前提）。

## 想定するユースケース

- 院内で気づいたことをその場でメモして手帳用に印刷
- スマホで撮った書類・画面を二値化して印刷
- デスクトップ版が同期フォルダに書き出した履歴をスマホから閲覧・再印刷

## 技術選定

**Flutter を推奨**（既に Flutter SDK が入っている環境のため、iOS / Android を 1 コードで賄える）。

| 層 | 実装 |
| --- | --- |
| 画面 | Flutter（Material 3） |
| 画像生成 | `dart:ui` の `PictureRecorder` でテキストを描画 → `toImage()` → RGBA |
| 二値化 | `image` パッケージ（`grayscale` → 誤差拡散 / しきい値）または自前で 30 行程度 |
| 送信 | `dart:io` の `Socket.connect(host, 9100)` に生バイトを書く |
| 履歴 | `sqflite` ＋ 端末内 PNG。クラウドは Drive / iCloud のフォルダ or `share_plus` で共有 |
| 設定 | `shared_preferences` |

Bluetooth 接続のモバイルプリンタも将来対象にするなら `flutter_blue_plus` を追加し、
**送信層だけ差し替える**（バイト列生成はそのまま流用できる）。

## 移植すべきコア

`thermal_memo/escpos.py` の 3 関数だけ移せば印刷は成立する。

```dart
// 1 = 黒。行末パディングは必ず白に戻す（docs/PROTOCOL.md 参照）
Uint8List pack1bit(List<bool> pixels, int width, int height) { … }

Iterable<Uint8List> rasterChunks(Uint8List packed, int bytesPerRow, int height,
                                 {int chunkRows = 128}) sync* {
  for (var top = 0; top < height; top += chunkRows) {
    final rows = min(chunkRows, height - top);
    yield Uint8List.fromList([
      0x1D, 0x76, 0x30, 0x00,
      bytesPerRow & 0xFF, (bytesPerRow >> 8) & 0xFF,
      rows & 0xFF, (rows >> 8) & 0xFF,
      ...packed.sublist(top * bytesPerRow, (top + rows) * bytesPerRow),
    ]);
  }
}

Future<void> send(String host, int port, Uint8List job) async {
  final socket = await Socket.connect(host, port,
      timeout: const Duration(seconds: 8));
  socket.add(job);
  await socket.flush();
  await Future.delayed(const Duration(milliseconds: 200));
  await socket.close();
}
```

検証は `tools/fake_printer.py` を PC で動かし、スマホからその PC の IP に送る。
復元された PNG がデスクトップ版と一致すれば移植成功。

## 画面構成（最小構成 v1）

1. **メモ**タブ … 複数行入力＋定型文チップ＋文字サイズ、下部に印刷 FAB
2. **画像**タブ … カメラ / ギャラリー / スクショ選択 → しきい値・明るさスライダ → プレビュー
3. **履歴**タブ … 端末内履歴の検索・再印刷
4. **設定** … プリンタ IP・ポート・用紙幅・カット有無（デスクトップ版と同じ項目）

プレビューは**デスクトップ版と同じく実際の 1bit 画像を出す**こと。
サーマル印刷は「思ったより薄い / 潰れる」が起きやすく、事前確認が効く。

## 段階的な進め方

1. **v1**: メモ印刷のみ（設定＋テキスト＋プレビュー＋送信）。1 日で組める規模
2. **v2**: 画像・カメラ取り込みと二値化調整
3. **v3**: 履歴とクラウド同期（デスクトップ版が書く `index.ndjson` と
   `YYYY/MM/*.md` を読めば、履歴フォーマットを共通化できる）
4. **v4**: Bluetooth プリンタ対応、ショートカット（iOS）や共有シートからの直接印刷

## 注意点

- iOS はローカルネットワークアクセスに許可ダイアログが要る
  （`Info.plist` に `NSLocalNetworkUsageDescription` と `NSBonjourServices`）
- Android 9 以降は平文 TCP 自体は制限されないが、`android:usesCleartextTraffic` の設定に注意
- 患者情報を扱いうるため、端末のパスコード必須化と、クラウド同期先の共有範囲は要確認
