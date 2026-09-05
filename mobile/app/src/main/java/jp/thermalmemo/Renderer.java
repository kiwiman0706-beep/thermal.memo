package jp.thermalmemo;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.text.Layout;
import android.text.StaticLayout;
import android.text.TextPaint;

import java.io.InputStream;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/**
 * 印刷用ビットマップの生成。
 *
 * <p>テキストは Canvas に描いてから二値化する。日本語の折り返しは StaticLayout に任せる。
 */
public final class Renderer {

    public static final int MODE_DITHER = 0;
    public static final int MODE_THRESHOLD = 1;

    private static final int MARGIN = 10;

    private Renderer() {
    }

    // ------------------------------------------------------------------ テキスト

    /** テキストを白地・黒文字のビットマップへ（この時点ではまだ二値化していない）。 */
    public static Bitmap renderText(String text, int widthDots, int fontSize, boolean bold,
                                    String header, boolean timestamp) {
        TextPaint body = new TextPaint(Paint.ANTI_ALIAS_FLAG);
        body.setColor(Color.BLACK);
        body.setTextSize(fontSize);
        body.setTypeface(bold ? Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD) : Typeface.SANS_SERIF);

        TextPaint small = new TextPaint(Paint.ANTI_ALIAS_FLAG);
        small.setColor(Color.BLACK);
        small.setTextSize(Math.max(12f, fontSize * 0.62f));
        small.setTypeface(Typeface.SANS_SERIF);

        int content = Math.max(16, widthDots - MARGIN * 2);
        String head = buildHeader(header, timestamp);
        String shown = (text == null || text.length() == 0) ? " " : text;

        StaticLayout headLayout = head.length() == 0 ? null : layout(head, small, content);
        StaticLayout bodyLayout = layout(shown, body, content);

        int height = MARGIN * 2 + bodyLayout.getHeight();
        if (headLayout != null) {
            height += headLayout.getHeight() + 16;
        }

        Bitmap bitmap = Bitmap.createBitmap(widthDots, Math.max(height, fontSize + MARGIN * 2),
                Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        canvas.drawColor(Color.WHITE);
        canvas.translate(MARGIN, MARGIN);
        if (headLayout != null) {
            headLayout.draw(canvas);
            canvas.translate(0, headLayout.getHeight() + 6);
            Paint rule = new Paint();
            rule.setColor(Color.BLACK);
            rule.setStrokeWidth(2f);
            canvas.drawLine(0f, 0f, (float) content, 0f, rule);
            canvas.translate(0, 10);
        }
        bodyLayout.draw(canvas);
        return bitmap;
    }

    private static String buildHeader(String header, boolean timestamp) {
        StringBuilder builder = new StringBuilder();
        if (timestamp) {
            builder.append(new SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.JAPAN).format(new Date()));
        }
        if (header != null && header.trim().length() > 0) {
            if (builder.length() > 0) {
                builder.append(" / ");
            }
            builder.append(header.trim());
        }
        return builder.toString();
    }

    // StaticLayout.Builder は API 23 以降。ここでは全 API で同じ結果になる旧コンストラクタを使う。
    @SuppressWarnings("deprecation")
    private static StaticLayout layout(String text, TextPaint paint, int width) {
        return new StaticLayout(text, paint, width, Layout.Alignment.ALIGN_NORMAL, 1.0f, 6f, false);
    }

    // -------------------------------------------------------------------- 二値化

    /**
     * 二値化する。
     *
     * @param mode      {@link #MODE_DITHER}（誤差拡散・写真向き）か {@link #MODE_THRESHOLD}（文字向き）
     * @param threshold 0-255。ディザ時も明暗のバイアスとして効く
     */
    public static Bitmap binarize(Bitmap source, int mode, int threshold, float brightness,
                                  float contrast, boolean invert) {
        int width = source.getWidth();
        int height = source.getHeight();
        int[] pixels = new int[width * height];
        source.getPixels(pixels, 0, width, 0, 0, width, height);

        float[] gray = new float[width * height];
        for (int i = 0; i < pixels.length; i++) {
            int color = pixels[i];
            int alpha = (color >>> 24) & 0xFF;
            float value = 0.299f * ((color >> 16) & 0xFF)
                    + 0.587f * ((color >> 8) & 0xFF)
                    + 0.114f * (color & 0xFF);
            if (alpha < 255) {
                // 透過部分は白い紙の上に置いたものとして合成する
                float ratio = alpha / 255f;
                value = value * ratio + 255f * (1f - ratio);
            }
            value = (value - 128f) * contrast + 128f;
            value = value * brightness;
            gray[i] = clamp(value);
        }

        int limit = Math.max(1, Math.min(254, threshold));
        if (mode == MODE_DITHER) {
            floydSteinberg(gray, width, height, limit);
        }

        int[] out = new int[width * height];
        for (int i = 0; i < gray.length; i++) {
            boolean black = gray[i] < (mode == MODE_DITHER ? 128f : limit);
            if (invert) {
                black = !black;
            }
            out[i] = black ? 0xFF000000 : 0xFFFFFFFF;
        }
        Bitmap result = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        result.setPixels(out, 0, width, 0, 0, width, height);
        return result;
    }

    private static void floydSteinberg(float[] gray, int width, int height, int threshold) {
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int index = y * width + x;
                float original = gray[index];
                float quantized = original < threshold ? 0f : 255f;
                gray[index] = quantized;
                float error = original - quantized;
                if (x + 1 < width) {
                    gray[index + 1] += error * 7f / 16f;
                }
                if (y + 1 < height) {
                    if (x > 0) {
                        gray[index + width - 1] += error * 3f / 16f;
                    }
                    gray[index + width] += error * 5f / 16f;
                    if (x + 1 < width) {
                        gray[index + width + 1] += error * 1f / 16f;
                    }
                }
            }
        }
    }

    private static float clamp(float value) {
        if (value < 0f) {
            return 0f;
        }
        if (value > 255f) {
            return 255f;
        }
        return value;
    }

    // -------------------------------------------------------------------- 配置

    public static Bitmap scaleToWidth(Bitmap source, int width) {
        if (source.getWidth() == width) {
            return source;
        }
        int height = Math.max(1, Math.round(source.getHeight() * (float) width / source.getWidth()));
        return Bitmap.createScaledBitmap(source, width, height, true);
    }

    /** 用紙幅より狭い画像を白地の中央に置く。 */
    public static Bitmap padToWidth(Bitmap source, int width) {
        if (source.getWidth() >= width) {
            return source;
        }
        Bitmap out = Bitmap.createBitmap(width, source.getHeight(), Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(out);
        canvas.drawColor(Color.WHITE);
        canvas.drawBitmap(source, (width - source.getWidth()) / 2f, 0f, null);
        return out;
    }

    /** 複数の画像を縦に連結する。 */
    public static Bitmap stack(List<Bitmap> images, int gap, int width) {
        int height = gap * Math.max(0, images.size() - 1);
        for (int i = 0; i < images.size(); i++) {
            height += images.get(i).getHeight();
        }
        Bitmap out = Bitmap.createBitmap(width, Math.max(1, height), Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(out);
        canvas.drawColor(Color.WHITE);
        float y = 0f;
        for (int i = 0; i < images.size(); i++) {
            Bitmap image = images.get(i);
            canvas.drawBitmap(image, (width - image.getWidth()) / 2f, y, null);
            y += image.getHeight() + gap;
        }
        return out;
    }

    // -------------------------------------------------------------------- 読み込み

    /**
     * 巨大な写真でも OOM しないよう間引きながら読み込む。
     *
     * @param opener 同じ内容を 2 回開けるようにするためのファクトリ
     */
    public static Bitmap decodeSampled(StreamOpener opener, int targetWidth) throws Exception {
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        InputStream first = opener.open();
        try {
            BitmapFactory.decodeStream(first, null, bounds);
        } finally {
            close(first);
        }

        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = sampleSize(bounds.outWidth, targetWidth * 2);
        InputStream second = opener.open();
        try {
            Bitmap bitmap = BitmapFactory.decodeStream(second, null, options);
            if (bitmap == null) {
                throw new Exception("画像を読み込めませんでした");
            }
            return bitmap;
        } finally {
            close(second);
        }
    }

    private static int sampleSize(int sourceWidth, int targetWidth) {
        int sample = 1;
        while (sourceWidth > 0 && targetWidth > 0 && sourceWidth / (sample * 2) >= targetWidth) {
            sample *= 2;
        }
        return sample;
    }

    private static void close(InputStream stream) {
        if (stream != null) {
            try {
                stream.close();
            } catch (Exception ignored) {
                // 無視
            }
        }
    }

    /** InputStream を必要なだけ開き直すための小さなインタフェース。 */
    public interface StreamOpener {
        InputStream open() throws Exception;
    }
}
