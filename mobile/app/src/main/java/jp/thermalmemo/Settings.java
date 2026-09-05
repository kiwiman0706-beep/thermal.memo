package jp.thermalmemo;

import android.content.Context;
import android.content.SharedPreferences;

/** SharedPreferences に保存する設定。 */
public final class Settings {

    private static final String PREFS = "thermal_memo";

    private final SharedPreferences prefs;

    public Settings(Context context) {
        this.prefs = context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public String host() {
        return prefs.getString("host", "");
    }

    public int port() {
        return prefs.getInt("port", 9100);
    }

    public int widthDots() {
        return prefs.getInt("width_dots", 576);
    }

    public boolean cut() {
        return prefs.getBoolean("cut", true);
    }

    public int feedLines() {
        return prefs.getInt("feed_lines", 3);
    }

    public int chunkRows() {
        return prefs.getInt("chunk_rows", 128);
    }

    public int timeoutMs() {
        return prefs.getInt("timeout_ms", 8000);
    }

    public int fontSize() {
        return prefs.getInt("font_size", 30);
    }

    public boolean timestamp() {
        return prefs.getBoolean("timestamp", true);
    }

    public boolean historyEnabled() {
        return prefs.getBoolean("history", true);
    }

    public int imageMode() {
        return prefs.getInt("image_mode", Renderer.MODE_DITHER);
    }

    public int threshold() {
        return prefs.getInt("threshold", 128);
    }

    public boolean isConfigured() {
        return host().trim().length() > 0;
    }

    public void setPrinter(String host, int port, int widthDots, boolean cut, int feedLines,
                           int chunkRows, int timeoutMs) {
        prefs.edit()
                .putString("host", host == null ? "" : host.trim())
                .putInt("port", port)
                .putInt("width_dots", widthDots)
                .putBoolean("cut", cut)
                .putInt("feed_lines", feedLines)
                .putInt("chunk_rows", chunkRows)
                .putInt("timeout_ms", timeoutMs)
                .apply();
    }

    public void setFormat(int fontSize, boolean timestamp, boolean history) {
        prefs.edit()
                .putInt("font_size", fontSize)
                .putBoolean("timestamp", timestamp)
                .putBoolean("history", history)
                .apply();
    }

    public void setImage(int mode, int threshold) {
        prefs.edit().putInt("image_mode", mode).putInt("threshold", threshold).apply();
    }
}
