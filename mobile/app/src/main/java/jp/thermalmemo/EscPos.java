package jp.thermalmemo;

import android.graphics.Bitmap;

import java.io.ByteArrayOutputStream;
import java.io.IOException;

/**
 * ESC/POS コマンド生成。
 *
 * <p>デスクトップ版 thermal_memo/escpos.py の移植。仕様は docs/PROTOCOL.md 参照。
 * 印刷対象はすべて 1bit ラスタ画像として送るため、プリンタ内蔵フォントには依存しない。
 */
public final class EscPos {

    public static final byte[] INIT = {0x1B, '@'};
    public static final byte[] LEFT_MARGIN_0 = {0x1D, 'L', 0x00, 0x00};
    public static final byte[] ALIGN_LEFT = {0x1B, 'a', 0x00};
    public static final byte[] ALIGN_CENTER = {0x1B, 'a', 0x01};
    public static final byte[] CUT_PARTIAL = {0x1D, 'V', 0x42, 0x00};

    private EscPos() {
    }

    /** n 行フィード（ESC d n）。 */
    public static byte[] feed(int lines) {
        int n = Math.max(0, Math.min(255, lines));
        if (n == 0) {
            return new byte[0];
        }
        return new byte[]{0x1B, 'd', (byte) n};
    }

    /** 1 行ぶんの ARGB 画素を out の offset 以降へ詰める。 */
    static void packRow(int[] row, int width, byte[] out, int offset) {
        for (int x = 0; x < width; x++) {
            int color = row[x];
            int luminance = (((color >> 16) & 0xFF) * 77
                    + ((color >> 8) & 0xFF) * 150
                    + (color & 0xFF) * 29) >> 8;
            if (luminance < 128) {
                out[offset + (x >> 3)] |= (byte) (0x80 >> (x & 7));
            }
        }
    }

    /**
     * ARGB 配列を「ビット 1 = 黒」のラスタデータへ詰める（Android 非依存。テストもこちらを叩く）。
     *
     * <p>黒い画素にだけビットを立てるので、行末のパディングビットは 0（白）のまま残る。
     * 反転方式で実装すると右端に黒帯が出るので注意（docs/PROTOCOL.md）。
     */
    public static byte[] pack1bit(int[] argb, int width, int height) {
        int bytesPerRow = (width + 7) / 8;
        byte[] out = new byte[bytesPerRow * height];
        int[] row = new int[width];
        for (int y = 0; y < height; y++) {
            System.arraycopy(argb, y * width, row, 0, width);
            packRow(row, width, out, y * bytesPerRow);
        }
        return out;
    }

    /** Bitmap 版。巨大な画像でも一度に全画素を持たないよう 1 行ずつ処理する。 */
    public static byte[] pack1bit(Bitmap bitmap) {
        int width = bitmap.getWidth();
        int height = bitmap.getHeight();
        int bytesPerRow = (width + 7) / 8;
        byte[] out = new byte[bytesPerRow * height];
        int[] row = new int[width];
        for (int y = 0; y < height; y++) {
            bitmap.getPixels(row, 0, width, 0, y, width, 1);
            packRow(row, width, out, y * bytesPerRow);
        }
        return out;
    }

    /**
     * 1 枚分の印刷ジョブを組み立てる。
     *
     * @param chunkRows GS v 0 を分割送信する行数。バッファの小さい機種では小さくする。
     */
    public static byte[] buildJob(Bitmap bitmap, int copies, boolean cut, int feedLines,
                                  int chunkRows, boolean center) throws IOException {
        return assemble(pack1bit(bitmap), bitmap.getWidth(), bitmap.getHeight(),
                copies, cut, feedLines, chunkRows, center);
    }

    /** ARGB 配列から組み立てる（Android 非依存。テストもこちらを叩く）。 */
    public static byte[] buildJob(int[] argb, int width, int height, int copies, boolean cut,
                                  int feedLines, int chunkRows, boolean center) throws IOException {
        return assemble(pack1bit(argb, width, height), width, height,
                copies, cut, feedLines, chunkRows, center);
    }

    private static byte[] assemble(byte[] data, int width, int height, int copies, boolean cut,
                                   int feedLines, int chunkRows, boolean center) throws IOException {
        int bytesPerRow = (width + 7) / 8;

        ByteArrayOutputStream raster = new ByteArrayOutputStream();
        int rowsPerChunk = Math.max(1, chunkRows);
        for (int top = 0; top < height; top += rowsPerChunk) {
            int rows = Math.min(rowsPerChunk, height - top);
            raster.write(new byte[]{
                    0x1D, 'v', '0', 0x00,
                    (byte) (bytesPerRow & 0xFF), (byte) ((bytesPerRow >> 8) & 0xFF),
                    (byte) (rows & 0xFF), (byte) ((rows >> 8) & 0xFF)});
            raster.write(data, top * bytesPerRow, rows * bytesPerRow);
        }
        byte[] band = raster.toByteArray();

        ByteArrayOutputStream job = new ByteArrayOutputStream();
        job.write(INIT);
        job.write(LEFT_MARGIN_0);
        job.write(center ? ALIGN_CENTER : ALIGN_LEFT);
        int total = Math.max(1, copies);
        for (int i = 0; i < total; i++) {
            if (i > 0) {
                job.write(feed(1));
            }
            job.write(band);
            job.write(feed(feedLines));
            if (cut) {
                job.write(CUT_PARTIAL);
            }
        }
        return job.toByteArray();
    }
}
