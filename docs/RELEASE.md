# リリースの出し方

タグを push すると GitHub Actions が各 OS 向けの配布物を作り、
GitHub Release に添付します。手元に Windows も Mac も要りません。

## 手順

1. `thermal_memo/__init__.py` の `__version__` を上げる
2. `mobile/app/build.gradle` の `versionName`（と `versionCode`）を合わせる
3. `CHANGELOG.md` に新しい節（`## 0.2.0`）を書く
4. コミットして push
5. タグを打って push

```bash
git tag v0.2.0
git push origin v0.2.0
```

タグと `__version__` が食い違っているとワークフローが止まります（打ち間違い防止）。

タグを作らずに試したいときは Actions の **Release** ワークフローを
`workflow_dispatch` で手動実行し、バージョン欄に `0.0.0-test` などを入れてください。

## できるもの

| ファイル | 中身 |
| --- | --- |
| `thermal-memo-<ver>-windows-setup.exe` | Inno Setup 製インストーラ。**管理者権限不要**（`%LocalAppData%` に入る） |
| `thermal-memo-<ver>-windows-portable.exe` | 単一 exe。USB で持ち運ぶ用 |
| `thermal-memo-<ver>-macos-arm64.dmg` | Apple Silicon 向け |
| `thermal-memo-<ver>-macos-x86_64.dmg` | Intel Mac 向け |
| `thermal-memo-<ver>-android.apk` | Android 版（デバッグ署名） |
| `SHA256SUMS.txt` | 自動更新時の検証に使う |

## 署名について

現状どれも署名していません。院内の数台に配る用途を想定しています。

- **Windows**: SmartScreen の警告が出ます。「詳細情報」→「実行」で進めます。
  頻繁に配るなら EV コード署名証明書の購入を検討してください
- **macOS**: Gatekeeper に止められます。初回は右クリック →「開く」。
  または `xattr -dr com.apple.quarantine /Applications/thermal.memo.app`
- **Android**: デバッグ署名です。Play ストアに出す場合はリリース署名鍵が要ります
  （鍵を作ったら GitHub Secrets に入れてワークフローに署名手順を足す）

## 自動更新との関係

アプリは `https://api.github.com/repos/<repo>/releases/latest` を見ています。

- **事前リリース**（`gh release create --prerelease`）は、
  設定で「事前リリースも対象にする」を有効にした人にだけ通知されます
- 配布物のファイル名の末尾（`windows-setup.exe` など）で選ぶので、
  **命名規則を変えると自動更新が配布物を見つけられなくなります**
- `SHA256SUMS.txt` があればダウンロード後に必ず突き合わせます。
  一致しなければインストールを中止します

## 手元でビルドしたいとき

```bash
pip install pyinstaller
python packaging/build.py --mode onedir --clean     # 起動が速い（インストーラ用）
python packaging/build.py --mode onefile            # 単一ファイル

# Windows でインストーラまで作る場合（Inno Setup 6 が必要）
iscc /DAppVersion=0.1.0 packaging\installer.iss
```
