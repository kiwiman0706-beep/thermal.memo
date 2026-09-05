package jp.thermalmemo;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

import java.security.MessageDigest;

/**
 * Python 実装（thermal_memo/escpos.py）との出力一致を検証する。
 *
 * <p>期待値は Python 側で生成した golden データ。両実装が同じバイト列を吐くことを
 * 保証するため、片方を変更したらこのテストが落ちる。
 */
public class EscPosTest {

    private static final int BLACK = 0xFF000000;
    private static final int WHITE = 0xFFFFFFFF;

    /** 16x4 の決め打ちパターン。ジョブ全体のバイト列を照合する。 */
    private static final String SMALL_JOB_HEX =
            "1b401d4c00001b61001d76300002000200800110001d76300002000200008080011b64021d564200";

    /** 64x40 の縞パターン、2 部・16 行分割。 */
    private static final String BIG_JOB_SHA256 =
            "f3087a875507fdb2c799deeb15f3612fc6bebea027db44fbe8792c51506c54dc";
    private static final int BIG_JOB_LENGTH = 714;

    @Test
    public void packsBlackPixelAsHighBit() {
        int[] pixels = new int[]{BLACK, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE};
        byte[] packed = EscPos.pack1bit(pixels, 8, 1);
        assertEquals(1, packed.length);
        assertEquals((byte) 0x80, packed[0]);
    }

    @Test
    public void leavesRowPaddingWhite() {
        // 幅 12（= 1.5 バイト）。全白なら余りビットも含めて全ビット 0 でなければならない。
        // ここが黒く出ると印字の右端に黒帯が走る。
        int[] pixels = new int[12 * 2];
        for (int i = 0; i < pixels.length; i++) {
            pixels[i] = WHITE;
        }
        byte[] packed = EscPos.pack1bit(pixels, 12, 2);
        assertEquals(4, packed.length);
        for (int i = 0; i < packed.length; i++) {
            assertEquals("index " + i, (byte) 0x00, packed[i]);
        }
    }

    @Test
    public void matchesPythonForSmallImage() throws Exception {
        int[] pixels = new int[16 * 4];
        for (int i = 0; i < pixels.length; i++) {
            pixels[i] = WHITE;
        }
        int[][] black = {{0, 0}, {15, 0}, {3, 1}, {8, 2}, {15, 3}, {0, 3}};
        for (int i = 0; i < black.length; i++) {
            pixels[black[i][1] * 16 + black[i][0]] = BLACK;
        }
        byte[] job = EscPos.buildJob(pixels, 16, 4, 1, true, 2, 2, false);
        assertEquals(SMALL_JOB_HEX, hex(job));
    }

    @Test
    public void matchesPythonForStripedImage() throws Exception {
        int width = 64;
        int height = 40;
        int[] pixels = new int[width * height];
        for (int i = 0; i < pixels.length; i++) {
            pixels[i] = WHITE;
        }
        for (int x = 0; x < width; x += 3) {
            for (int y = 0; y < height; y += 2) {
                pixels[y * width + x] = BLACK;
            }
        }
        byte[] job = EscPos.buildJob(pixels, width, height, 2, true, 3, 16, false);
        assertEquals(BIG_JOB_LENGTH, job.length);
        assertEquals(BIG_JOB_SHA256, sha256(job));
    }

    @Test
    public void splitsRasterIntoChunks() throws Exception {
        int[] pixels = new int[576 * 300];
        for (int i = 0; i < pixels.length; i++) {
            pixels[i] = WHITE;
        }
        byte[] job = EscPos.buildJob(pixels, 576, 300, 1, false, 0, 128, false);
        // 128 + 128 + 44 の 3 バンドに割れる
        assertEquals(3, countChunks(job));
    }

    @Test
    public void feedIsEmptyForZeroLines() {
        assertEquals(0, EscPos.feed(0).length);
        assertEquals(3, EscPos.feed(4).length);
        assertEquals((byte) 4, EscPos.feed(4)[2]);
    }

    private static int countChunks(byte[] job) {
        int count = 0;
        for (int i = 0; i + 2 < job.length; i++) {
            if (job[i] == 0x1D && job[i + 1] == 'v' && job[i + 2] == '0') {
                count++;
            }
        }
        return count;
    }

    private static String hex(byte[] data) {
        StringBuilder builder = new StringBuilder(data.length * 2);
        for (int i = 0; i < data.length; i++) {
            builder.append(String.format("%02x", data[i] & 0xFF));
        }
        return builder.toString();
    }

    private static String sha256(byte[] data) throws Exception {
        return hex(MessageDigest.getInstance("SHA-256").digest(data));
    }
}
