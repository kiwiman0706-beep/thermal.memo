package jp.thermalmemo;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.Map;

/**
 * 更新の確認からインストールまでの画面まわり。
 *
 * <p>ネットワークはワーカースレッド、画面操作は Handler でメインスレッドに戻す。
 */
public class UpdateFlow {

    private final Activity activity;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private boolean busy;

    private AlertDialog progressDialog;
    private ProgressBar progressBar;
    private TextView progressLabel;
    private long downloadId = -1;
    private String expectedDigest = "";

    public UpdateFlow(Activity activity) {
        this.activity = activity;
    }

    /**
     * 更新を確認する。
     *
     * @param silent 起動時の自動確認。更新が無いときや失敗したときは何も出さない。
     */
    public void check(final boolean silent) {
        if (busy) {
            return;
        }
        busy = true;
        if (!silent) {
            toast("更新を確認しています…");
        }
        final Settings settings = new Settings(activity);
        final String repo = settings.updateRepo();
        final String current = Updates.currentVersion(activity);

        new Thread(new Runnable() {
            @Override
            public void run() {
                Updates.Release release = null;
                String error = null;
                try {
                    release = Updates.fetchLatest(repo);
                } catch (Exception exception) {
                    error = exception.getMessage();
                }
                final Updates.Release found = release;
                final String failure = error;
                handler.post(new Runnable() {
                    @Override
                    public void run() {
                        busy = false;
                        if (failure != null) {
                            if (!silent) {
                                toast("更新の確認に失敗: " + failure);
                            }
                            return;
                        }
                        onChecked(found, current, silent);
                    }
                });
            }
        }).start();
    }

    private void onChecked(Updates.Release release, String current, boolean silent) {
        Settings settings = new Settings(activity);
        if (release.prerelease && !settings.includePrerelease()) {
            if (!silent) {
                toast("最新は事前リリースのみです");
            }
            return;
        }
        if (!Updates.isNewer(release.version, current)) {
            if (!silent) {
                toast("最新版です（" + current + "）");
            }
            return;
        }
        if (!release.hasApk()) {
            if (!silent) {
                openPage(release);
            }
            return;
        }
        if (silent && release.version.equals(settings.skipVersion())) {
            return;
        }
        promptUpdate(release, current);
    }

    private void promptUpdate(final Updates.Release release, String current) {
        String notes = release.notes.trim();
        if (notes.length() > 1200) {
            notes = notes.substring(0, 1200) + "\n…";
        }
        String message = "お使いの版: " + current + "\n新しい版: " + release.tag + "\n\n" + notes;

        new AlertDialog.Builder(activity)
                .setTitle("更新があります")
                .setMessage(message)
                .setPositiveButton("更新", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface dialog, int which) {
                        startDownload(release);
                    }
                })
                .setNeutralButton("この版をスキップ", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface dialog, int which) {
                        new Settings(activity).setSkipVersion(release.version);
                        toast(release.tag + " をスキップします");
                    }
                })
                .setNegativeButton("後で", null)
                .show();
    }

    private void openPage(Updates.Release release) {
        if (release.htmlUrl.length() == 0) {
            return;
        }
        activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(release.htmlUrl)));
    }

    // ------------------------------------------------------------ ダウンロード

    private void startDownload(final Updates.Release release) {
        if (!Updates.canInstall(activity)) {
            new AlertDialog.Builder(activity)
                    .setTitle("インストールの許可が必要です")
                    .setMessage("この端末では、thermal.memo に「不明なアプリのインストール」を"
                            + "許可する必要があります。設定画面を開きますか？")
                    .setPositiveButton("設定を開く", new DialogInterface.OnClickListener() {
                        @Override
                        public void onClick(DialogInterface dialog, int which) {
                            activity.startActivity(Updates.installPermissionIntent(activity));
                        }
                    })
                    .setNegativeButton("やめる", null)
                    .show();
            return;
        }

        showProgressDialog(release);
        downloadId = Updates.enqueue(activity, release);

        new Thread(new Runnable() {
            @Override
            public void run() {
                Map<String, String> checksums = Updates.fetchChecksums(release);
                final String digest = checksums.get(release.apkName);
                handler.post(new Runnable() {
                    @Override
                    public void run() {
                        expectedDigest = digest == null ? "" : digest;
                    }
                });
            }
        }).start();

        handler.postDelayed(poller, 700);
    }

    private final Runnable poller = new Runnable() {
        @Override
        public void run() {
            if (downloadId < 0) {
                return;
            }
            Updates.Progress progress = Updates.query(activity, downloadId);
            if (!progress.finished()) {
                updateProgress(progress);
                handler.postDelayed(this, 700);
                return;
            }
            dismissProgressDialog();
            if (!progress.succeeded()) {
                toast("ダウンロードに失敗しました（コード " + progress.reason + "）");
                downloadId = -1;
                return;
            }
            finishDownload();
        }
    };

    private void finishDownload() {
        final Uri uri = Updates.downloadedUri(activity, downloadId);
        downloadId = -1;
        if (uri == null) {
            toast("ダウンロードしたファイルが見つかりません");
            return;
        }
        if (!Updates.verify(activity, uri, expectedDigest)) {
            new AlertDialog.Builder(activity)
                    .setTitle("検証に失敗しました")
                    .setMessage("ダウンロードした APK のハッシュが SHA256SUMS.txt と一致しません。"
                            + "インストールを中止しました。")
                    .setPositiveButton("閉じる", null)
                    .show();
            return;
        }
        try {
            activity.startActivity(Updates.installIntent(uri));
        } catch (Exception error) {
            toast("インストーラを開けません: " + error.getMessage());
        }
    }

    // ------------------------------------------------------------------ 進捗表示

    private void showProgressDialog(Updates.Release release) {
        LinearLayout layout = new LinearLayout(activity);
        layout.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (16 * activity.getResources().getDisplayMetrics().density);
        layout.setPadding(pad, pad, pad, pad);

        progressLabel = new TextView(activity);
        progressLabel.setText("接続しています…");
        progressLabel.setGravity(Gravity.START);
        layout.addView(progressLabel);

        progressBar = new ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);
        layout.addView(progressBar);

        progressDialog = new AlertDialog.Builder(activity)
                .setTitle("更新をダウンロード中 " + release.tag)
                .setView(layout)
                .setCancelable(false)
                .setNegativeButton("中止", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface dialog, int which) {
                        cancelDownload();
                    }
                })
                .show();
    }

    private void updateProgress(Updates.Progress progress) {
        if (progressBar == null || progressLabel == null) {
            return;
        }
        progressBar.setProgress(progress.percent());
        if (progress.total > 0) {
            progressLabel.setText(String.format("%d%%  (%.1f / %.1f MB)",
                    progress.percent(),
                    progress.downloaded / 1048576f,
                    progress.total / 1048576f));
        } else {
            progressLabel.setText(String.format("%.1f MB", progress.downloaded / 1048576f));
        }
    }

    private void dismissProgressDialog() {
        if (progressDialog != null) {
            progressDialog.dismiss();
            progressDialog = null;
        }
        progressBar = null;
        progressLabel = null;
    }

    private void cancelDownload() {
        if (downloadId >= 0) {
            android.app.DownloadManager manager = (android.app.DownloadManager)
                    activity.getSystemService(android.content.Context.DOWNLOAD_SERVICE);
            manager.remove(downloadId);
            downloadId = -1;
        }
        dismissProgressDialog();
        toast("更新を中止しました");
    }

    /** 画面が閉じるときに後片付けする。 */
    public void dispose() {
        handler.removeCallbacks(poller);
        dismissProgressDialog();
    }

    private void toast(String message) {
        Toast.makeText(activity, message, Toast.LENGTH_SHORT).show();
    }
}
