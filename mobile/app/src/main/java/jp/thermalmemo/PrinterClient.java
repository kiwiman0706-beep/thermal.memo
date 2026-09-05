package jp.thermalmemo;

import java.io.IOException;
import java.io.OutputStream;
import java.net.ConnectException;
import java.net.InetSocketAddress;
import java.net.NoRouteToHostException;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

/** LAN サーマルプリンタ（RAW / TCP 9100）への送信。 */
public final class PrinterClient {

    private PrinterClient() {
    }

    /** 生バイト列を送る。必ずワーカースレッドから呼ぶこと。 */
    public static void send(String host, int port, int timeoutMs, byte[] payload) throws IOException {
        if (host == null || host.trim().length() == 0) {
            throw new IOException("プリンタの IP アドレスが未設定です");
        }
        Socket socket = new Socket();
        try {
            socket.connect(new InetSocketAddress(host.trim(), port), timeoutMs);
            socket.setSoTimeout(timeoutMs);
            OutputStream out = socket.getOutputStream();
            out.write(payload);
            out.flush();
            // 送信直後に閉じるとバッファを捨てる機種があるので少し待つ
            try {
                Thread.sleep(200);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        } finally {
            try {
                socket.close();
            } catch (IOException ignored) {
                // クローズ失敗は無視
            }
        }
    }

    /** TCP 接続だけ試す（用紙を消費しない）。 */
    public static void testConnection(String host, int port, int timeoutMs) throws IOException {
        if (host == null || host.trim().length() == 0) {
            throw new IOException("プリンタの IP アドレスが未設定です");
        }
        Socket socket = new Socket();
        try {
            socket.connect(new InetSocketAddress(host.trim(), port), timeoutMs);
        } finally {
            try {
                socket.close();
            } catch (IOException ignored) {
                // クローズ失敗は無視
            }
        }
    }

    /** 例外を日本語の短い説明にする。 */
    public static String describe(Throwable error) {
        if (error instanceof SocketTimeoutException) {
            return "接続がタイムアウトしました。IP と電源・Wi-Fi を確認してください";
        }
        if (error instanceof ConnectException) {
            return "接続を拒否されました。IP とポートを確認してください";
        }
        if (error instanceof NoRouteToHostException) {
            return "経路がありません。プリンタと同じ Wi-Fi に接続していますか？";
        }
        if (error instanceof UnknownHostException) {
            return "ホスト名を解決できません";
        }
        String message = error.getMessage();
        return message == null ? error.getClass().getSimpleName() : message;
    }
}
