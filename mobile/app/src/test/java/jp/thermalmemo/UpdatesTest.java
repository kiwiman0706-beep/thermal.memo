package jp.thermalmemo;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * バージョン比較のテスト。
 *
 * <p>デスクトップ版 thermal_memo/updater.py と同じ順序になっていないと、
 * 「Android だけ更新に気付かない」といった食い違いが起きる。
 */
public class UpdatesTest {

    @Test
    public void parsesCommonForms() {
        assertArrayEquals(new int[]{1, 2, 3, 4, 0}, Updates.parseVersion("v1.2.3"));
        assertArrayEquals(new int[]{1, 2, 0, 4, 0}, Updates.parseVersion("1.2"));
        assertArrayEquals(new int[]{2, 0, 0, 4, 0}, Updates.parseVersion("2"));
        assertArrayEquals(new int[]{1, 0, 0, 3, 2}, Updates.parseVersion("1.0.0-rc2"));
    }

    @Test
    public void unparsableReturnsNull() {
        assertNull(Updates.parseVersion("nightly"));
        assertNull(Updates.parseVersion(null));
    }

    @Test
    public void ordersReleases() {
        assertTrue(Updates.isNewer("0.2.0", "0.1.9"));
        assertTrue(Updates.isNewer("0.10.0", "0.9.0"));   // 文字列比較では逆転する組
        assertFalse(Updates.isNewer("0.1.0", "0.1.0"));
        assertFalse(Updates.isNewer("0.0.9", "0.1.0"));
    }

    @Test
    public void prereleaseIsOlderThanFinal() {
        assertTrue(Updates.isNewer("1.0.0", "1.0.0-rc2"));
        assertFalse(Updates.isNewer("1.0.0-rc2", "1.0.0"));
        assertTrue(Updates.isNewer("1.0.0-rc2", "1.0.0-rc1"));
        assertTrue(Updates.isNewer("1.0.0-beta1", "1.0.0-alpha9"));
    }

    @Test
    public void unparsableIsNeverNewer() {
        assertFalse(Updates.isNewer("latest", "0.1.0"));
        assertFalse(Updates.isNewer("0.2.0", "unknown"));
    }
}
