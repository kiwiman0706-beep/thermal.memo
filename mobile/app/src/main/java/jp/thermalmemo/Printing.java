package jp.thermalmemo;

import android.content.Context;
import android.graphics.Bitmap;
import android.os.Handler;
import android.os.Looper;

/** 二値化済みビットマップの送信と履歴記録をまとめる。 */
public final class Printing {

    /** 送信結果を UI スレッドで受け取るコールバック。 */
    public interface Callback {
        void onResult(boolean ok, String message);
    }

    private Printing() {
    }

    /**
     * バックグラウンドで印刷して結果をコールバックする。
     *
     * @param monochrome 二値化済みのビットマップ（幅は用紙幅ちょうどにしておくこと）
     */
    public static void printAsync(final Context context, final Bitmap monochrome, final int copies,
                                  final String kind, final String title, final String body,
                                  final Callback callback) {
        final Context appContext = context.getApplicationContext();
        final Settings settings = new Settings(appContext);
        final Handler handler = new Handler(Looper.getMainLooper());

        new Thread(new Runnable() {
            @Override
            public void run() {
                boolean ok;
                String message;
                try {
                    byte[] job = EscPos.buildJob(monochrome, copies, settings.cut(),
                            settings.feedLines(), settings.chunkRows(), false);
                    PrinterClient.send(settings.host(), settings.port(), settings.timeoutMs(), job);
                    ok = true;
                    message = "印刷しました（" + copies + " 部 / 約 "
                            + Math.round(monochrome.getHeight() / 8f) + " mm）";
                } catch (Throwable error) {
                    ok = false;
                    message = "印刷失敗: " + PrinterClient.describe(error);
                }

                if (settings.historyEnabled()) {
                    try {
                        HistoryStore store = new HistoryStore(appContext);
                        store.add(kind, monochrome, title, body,
                                settings.host() + ":" + settings.port(),
                                ok ? "ok" : "error", ok ? "" : message);
                        store.close();
                    } catch (Throwable ignored) {
                        // 履歴の失敗で印刷結果を上書きしない
                    }
                }

                final boolean resultOk = ok;
                final String resultMessage = message;
                handler.post(new Runnable() {
                    @Override
                    public void run() {
                        callback.onResult(resultOk, resultMessage);
                    }
                });
            }
        }).start();
    }
}
