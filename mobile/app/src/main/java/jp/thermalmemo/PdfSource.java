package jp.thermalmemo;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.pdf.PdfRenderer;
import android.net.Uri;
import android.os.ParcelFileDescriptor;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * PDF をページ画像として読む。
 *
 * <p>Android 標準の PdfRenderer を使うためライブラリ依存はないが、
 * テキスト抽出はできない（デスクトップ版と違い、スマホ側はページ画像のみ）。
 * PdfRenderer はシーク可能な FD を要求するので、いったんキャッシュへコピーする。
 */
public final class PdfSource {

    private final File cacheFile;
    private final ParcelFileDescriptor descriptor;
    private final PdfRenderer renderer;

    public PdfSource(Context context, Uri uri) throws IOException {
        this.cacheFile = copyToCache(context, uri);
        this.descriptor = ParcelFileDescriptor.open(cacheFile, ParcelFileDescriptor.MODE_READ_ONLY);
        this.renderer = new PdfRenderer(descriptor);
    }

    public int pageCount() {
        return renderer.getPageCount();
    }

    /** 指定ページを用紙幅に合わせて描画する（白地・グレースケール相当）。 */
    public Bitmap renderPage(int index, int widthDots) {
        PdfRenderer.Page page = renderer.openPage(index);
        try {
            int width = Math.max(16, widthDots);
            int height = Math.max(1, width * page.getHeight() / Math.max(1, page.getWidth()));
            Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
            // PdfRenderer は透明部分を塗らないので、先に白で埋める
            Canvas canvas = new Canvas(bitmap);
            canvas.drawColor(Color.WHITE);
            page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_PRINT);
            return bitmap;
        } finally {
            page.close();
        }
    }

    public void close() {
        try {
            renderer.close();
        } catch (Exception ignored) {
            // 無視
        }
        try {
            descriptor.close();
        } catch (Exception ignored) {
            // 無視
        }
        if (cacheFile.exists() && !cacheFile.delete()) {
            cacheFile.deleteOnExit();
        }
    }

    private static File copyToCache(Context context, Uri uri) throws IOException {
        File file = new File(context.getCacheDir(), "shared-" + System.currentTimeMillis() + ".pdf");
        InputStream in = context.getContentResolver().openInputStream(uri);
        if (in == null) {
            throw new IOException("PDF を開けませんでした");
        }
        OutputStream out = new FileOutputStream(file);
        try {
            byte[] buffer = new byte[16384];
            int read;
            while ((read = in.read(buffer)) > 0) {
                out.write(buffer, 0, read);
            }
            out.flush();
        } finally {
            try {
                in.close();
            } catch (IOException ignored) {
                // 無視
            }
            try {
                out.close();
            } catch (IOException ignored) {
                // 無視
            }
        }
        return file;
    }
}
