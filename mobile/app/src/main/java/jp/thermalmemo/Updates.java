package jp.thermalmemo;

import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * GitHub Releases を見て新しい APK を取ってくる。
 *
 * <p>Play ストア外の配布なので、ダウンロードは DownloadManager に任せ、
 * 取得した content:// URI をそのままインストール用インテントに渡す
 * （FileProvider を用意せずに済む）。SHA256SUMS.txt と突き合わせてから
 * インストールを促す。
 */
public final class Updates {

    public static final String DEFAULT_REPO = "kiwiman0706-beep/thermal.memo";
    private static final String API = "https://api.github.com/repos/%s/releases/latest";
    private static final String CHECKSUMS = "SHA256SUMS.txt";
    private static final int TIMEOUT_MS = 15000;

    private Updates() {
    }

    /** リリース 1 件分。 */
    public static class Release {
        public String tag = "";
        public String version = "";
        public String notes = "";
        public String htmlUrl = "";
        public boolean prerelease;
        public String apkName = "";
        public String apkUrl = "";
        public String checksumsUrl = "";
        public long apkSize;

        public boolean hasApk() {
            return apkUrl.length() > 0;
        }
    }

    // ------------------------------------------------------------ バージョン比較

    private static final Pattern VERSION = Pattern.compile(
            "^v?(\\d+)(?:\\.(\\d+))?(?:\\.(\\d+))?(?:[-_.]?(dev|alpha|beta|rc|a|b)\\.?(\\d+)?)?",
            Pattern.CASE_INSENSITIVE);

    private static int stageRank(String stage) {
        if (stage == null || stage.length() == 0) {
            return 4;
        }
        String lower = stage.toLowerCase();
        if (lower.startsWith("rc")) {
            return 3;
        }
        if (lower.startsWith("b")) {
            return 2;
        }
        if (lower.startsWith("a")) {
            return 1;
        }
        return 0;
    }

    /** 比較用の数値列にする。読めなければ null。 */
    static int[] parseVersion(String text) {
        if (text == null) {
            return null;
        }
        Matcher matcher = VERSION.matcher(text.trim());
        if (!matcher.find()) {
            return null;
        }
        return new int[]{
                Integer.parseInt(matcher.group(1)),
                matcher.group(2) == null ? 0 : Integer.parseInt(matcher.group(2)),
                matcher.group(3) == null ? 0 : Integer.parseInt(matcher.group(3)),
                stageRank(matcher.group(4)),
                matcher.group(5) == null ? 0 : Integer.parseInt(matcher.group(5)),
        };
    }

    /** candidate が current より新しければ true。 */
    public static boolean isNewer(String candidate, String current) {
        int[] left = parseVersion(candidate);
        int[] right = parseVersion(current);
        if (left == null || right == null) {
            return false;
        }
        for (int i = 0; i < left.length; i++) {
            if (left[i] != right[i]) {
                return left[i] > right[i];
            }
        }
        return false;
    }

    public static String currentVersion(Context context) {
        try {
            return context.getPackageManager()
                    .getPackageInfo(context.getPackageName(), 0).versionName;
        } catch (Exception error) {
            return "0.0.0";
        }
    }

    // ------------------------------------------------------------------ 取得

    /** 最新リリースを取る。必ずワーカースレッドから呼ぶこと。 */
    public static Release fetchLatest(String repo) throws IOException {
        String body = get(String.format(API, repo));
        try {
            JSONObject json = new JSONObject(body);
            Release release = new Release();
            release.tag = json.optString("tag_name", "");
            release.version = release.tag.replaceAll("^[vV]", "");
            release.notes = json.optString("body", "");
            release.htmlUrl = json.optString("html_url", "");
            release.prerelease = json.optBoolean("prerelease", false);

            JSONArray assets = json.optJSONArray("assets");
            if (assets != null) {
                for (int i = 0; i < assets.length(); i++) {
                    JSONObject asset = assets.getJSONObject(i);
                    String name = asset.optString("name", "");
                    String url = asset.optString("browser_download_url", "");
                    if (url.length() == 0) {
                        continue;
                    }
                    if (name.endsWith(".apk")) {
                        release.apkName = name;
                        release.apkUrl = url;
                        release.apkSize = asset.optLong("size", 0);
                    } else if (CHECKSUMS.equals(name)) {
                        release.checksumsUrl = url;
                    }
                }
            }
            return release;
        } catch (Exception error) {
            throw new IOException("更新情報を読み取れませんでした: " + error.getMessage());
        }
    }

    /** SHA256SUMS.txt を取って「ファイル名 → ハッシュ」にする。取れなければ空。 */
    public static Map<String, String> fetchChecksums(Release release) {
        Map<String, String> result = new HashMap<String, String>();
        if (release.checksumsUrl.length() == 0) {
            return result;
        }
        try {
            for (String line : get(release.checksumsUrl).split("\n")) {
                String[] parts = line.trim().split("\\s+");
                if (parts.length >= 2 && parts[0].length() == 64) {
                    result.put(parts[parts.length - 1].replaceFirst("^\\*", ""),
                            parts[0].toLowerCase());
                }
            }
        } catch (IOException ignored) {
            // チェックサムが取れないことは致命的でない（呼び出し側で判断する）
        }
        return result;
    }

    private static String get(String url) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setConnectTimeout(TIMEOUT_MS);
        connection.setReadTimeout(TIMEOUT_MS);
        connection.setRequestProperty("User-Agent", "thermal.memo-android");
        connection.setRequestProperty("Accept", "application/vnd.github+json");
        try {
            int status = connection.getResponseCode();
            if (status == 404) {
                throw new IOException("まだリリースが公開されていません");
            }
            if (status == 403) {
                throw new IOException("GitHub API の回数制限に達しました");
            }
            if (status >= 400) {
                throw new IOException("更新情報を取得できません（HTTP " + status + "）");
            }
            InputStream in = connection.getInputStream();
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192];
            int read;
            while ((read = in.read(buffer)) > 0) {
                out.write(buffer, 0, read);
            }
            in.close();
            return out.toString("UTF-8");
        } finally {
            connection.disconnect();
        }
    }

    // ------------------------------------------------------------ ダウンロード

    /** DownloadManager に APK の取得を依頼して、そのリクエスト ID を返す。 */
    public static long enqueue(Context context, Release release) {
        DownloadManager manager =
                (DownloadManager) context.getSystemService(Context.DOWNLOAD_SERVICE);
        DownloadManager.Request request = new DownloadManager.Request(Uri.parse(release.apkUrl));
        request.setTitle("thermal.memo " + release.tag);
        request.setDescription("更新をダウンロードしています");
        request.setMimeType("application/vnd.android.package-archive");
        request.setNotificationVisibility(
                DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
        request.setDestinationInExternalFilesDir(context, null, release.apkName);
        return manager.enqueue(request);
    }

    /** ダウンロードの状態。 */
    public static class Progress {
        public int status;
        public long downloaded;
        public long total;
        public int reason;

        public boolean finished() {
            return status == DownloadManager.STATUS_SUCCESSFUL
                    || status == DownloadManager.STATUS_FAILED;
        }

        public boolean succeeded() {
            return status == DownloadManager.STATUS_SUCCESSFUL;
        }

        public int percent() {
            return total > 0 ? (int) (downloaded * 100 / total) : 0;
        }
    }

    public static Progress query(Context context, long downloadId) {
        DownloadManager manager =
                (DownloadManager) context.getSystemService(Context.DOWNLOAD_SERVICE);
        Progress progress = new Progress();
        Cursor cursor = manager.query(new DownloadManager.Query().setFilterById(downloadId));
        if (cursor == null) {
            progress.status = DownloadManager.STATUS_FAILED;
            return progress;
        }
        try {
            if (cursor.moveToFirst()) {
                progress.status = cursor.getInt(
                        cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                progress.downloaded = cursor.getLong(cursor.getColumnIndexOrThrow(
                        DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
                progress.total = cursor.getLong(cursor.getColumnIndexOrThrow(
                        DownloadManager.COLUMN_TOTAL_SIZE_BYTES));
                progress.reason = cursor.getInt(
                        cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON));
            } else {
                progress.status = DownloadManager.STATUS_FAILED;
            }
        } finally {
            cursor.close();
        }
        return progress;
    }

    public static Uri downloadedUri(Context context, long downloadId) {
        DownloadManager manager =
                (DownloadManager) context.getSystemService(Context.DOWNLOAD_SERVICE);
        return manager.getUriForDownloadedFile(downloadId);
    }

    /** ダウンロードした APK のハッシュを検証する。期待値が無ければ true。 */
    public static boolean verify(Context context, Uri uri, String expected) {
        if (expected == null || expected.length() == 0) {
            return true;
        }
        InputStream in = null;
        try {
            in = context.getContentResolver().openInputStream(uri);
            if (in == null) {
                return false;
            }
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[65536];
            int read;
            while ((read = in.read(buffer)) > 0) {
                digest.update(buffer, 0, read);
            }
            StringBuilder hex = new StringBuilder(64);
            for (byte value : digest.digest()) {
                hex.append(String.format("%02x", value));
            }
            return hex.toString().equals(expected.toLowerCase());
        } catch (Exception error) {
            return false;
        } finally {
            if (in != null) {
                try {
                    in.close();
                } catch (IOException ignored) {
                    // 無視
                }
            }
        }
    }

    // ------------------------------------------------------------ インストール

    /** 「提供元不明のアプリ」を許可済みか。 */
    public static boolean canInstall(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return true;
        }
        return context.getPackageManager().canRequestPackageInstalls();
    }

    /** 許可画面を開くインテント。 */
    public static Intent installPermissionIntent(Context context) {
        Intent intent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES);
        intent.setData(Uri.parse("package:" + context.getPackageName()));
        return intent;
    }

    /** インストーラを開くインテント。 */
    public static Intent installIntent(Uri apk) {
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(apk, "application/vnd.android.package-archive");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        return intent;
    }
}
