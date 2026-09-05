package jp.thermalmemo;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Parcelable;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.CompoundButton;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.RadioGroup;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * 他アプリの「共有」から画像・PDF を受け取って印刷する画面。
 *
 * <p>受けるインテント:
 * ACTION_SEND (image/*, application/pdf) と ACTION_SEND_MULTIPLE (image/*)。
 */
public class ShareActivity extends Activity {

    private static final int MIN_SCALE = 20;

    private TextView source;
    private TextView status;
    private TextView pageLabel;
    private TextView thresholdValue;
    private TextView scaleValue;
    private ImageView preview;
    private SeekBar threshold;
    private SeekBar scale;
    private RadioGroup mode;
    private EditText caption;
    private CheckBox allPages;
    private LinearLayout pageBar;
    private Button printButton;

    private Settings settings;
    private PdfSource pdf;
    private final List<Bitmap> sources = new ArrayList<Bitmap>();
    private int pageIndex;
    private String sourceName = "";
    private Bitmap current;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable previewTask = new Runnable() {
        @Override
        public void run() {
            updatePreview();
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_share);
        settings = new Settings(this);

        source = (TextView) findViewById(R.id.source);
        status = (TextView) findViewById(R.id.status);
        pageLabel = (TextView) findViewById(R.id.page_label);
        thresholdValue = (TextView) findViewById(R.id.threshold_value);
        scaleValue = (TextView) findViewById(R.id.scale_value);
        preview = (ImageView) findViewById(R.id.preview);
        threshold = (SeekBar) findViewById(R.id.threshold);
        scale = (SeekBar) findViewById(R.id.scale);
        mode = (RadioGroup) findViewById(R.id.mode);
        caption = (EditText) findViewById(R.id.caption);
        allPages = (CheckBox) findViewById(R.id.all_pages);
        pageBar = (LinearLayout) findViewById(R.id.page_bar);
        printButton = (Button) findViewById(R.id.print);

        threshold.setProgress(settings.threshold());
        thresholdValue.setText(String.valueOf(settings.threshold()));
        scale.setProgress(100 - MIN_SCALE);
        scaleValue.setText("100");
        if (settings.imageMode() == Renderer.MODE_THRESHOLD) {
            mode.check(R.id.mode_threshold);
        }

        SeekBar.OnSeekBarChangeListener listener = new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar bar, int progress, boolean fromUser) {
                thresholdValue.setText(String.valueOf(threshold.getProgress()));
                scaleValue.setText(String.valueOf(scale.getProgress() + MIN_SCALE));
                schedulePreview();
            }

            @Override
            public void onStartTrackingTouch(SeekBar bar) {
            }

            @Override
            public void onStopTrackingTouch(SeekBar bar) {
            }
        };
        threshold.setOnSeekBarChangeListener(listener);
        scale.setOnSeekBarChangeListener(listener);

        mode.setOnCheckedChangeListener(new RadioGroup.OnCheckedChangeListener() {
            @Override
            public void onCheckedChanged(RadioGroup group, int checkedId) {
                schedulePreview();
            }
        });

        allPages.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            @Override
            public void onCheckedChanged(CompoundButton button, boolean checked) {
                schedulePreview();
            }
        });

        findViewById(R.id.prev_page).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                movePage(-1);
            }
        });
        findViewById(R.id.next_page).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                movePage(1);
            }
        });
        printButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                print();
            }
        });

        load(getIntent());
    }

    @Override
    protected void onDestroy() {
        if (pdf != null) {
            pdf.close();
            pdf = null;
        }
        super.onDestroy();
    }

    // ------------------------------------------------------------------ 読み込み

    private void load(Intent intent) {
        if (intent == null) {
            finishWith("共有データがありません");
            return;
        }
        final String action = intent.getAction();
        final String type = intent.getType() == null ? "" : intent.getType();
        final List<Uri> uris = new ArrayList<Uri>();

        if (Intent.ACTION_SEND.equals(action)) {
            Uri uri = (Uri) intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if (uri != null) {
                uris.add(uri);
            }
        } else if (Intent.ACTION_SEND_MULTIPLE.equals(action)) {
            ArrayList<Parcelable> extras = intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
            if (extras != null) {
                for (int i = 0; i < extras.size(); i++) {
                    if (extras.get(i) instanceof Uri) {
                        uris.add((Uri) extras.get(i));
                    }
                }
            }
        }

        if (uris.isEmpty()) {
            finishWith("共有された画像・PDF が見つかりません");
            return;
        }

        source.setText("読み込み中…");
        final boolean isPdf = type.startsWith("application/pdf");
        new Thread(new Runnable() {
            @Override
            public void run() {
                String error = null;
                try {
                    if (isPdf) {
                        loadPdf(uris.get(0));
                    } else {
                        loadImages(uris);
                    }
                } catch (Throwable throwable) {
                    error = throwable.getMessage() == null
                            ? throwable.getClass().getSimpleName() : throwable.getMessage();
                }
                final String failure = error;
                handler.post(new Runnable() {
                    @Override
                    public void run() {
                        if (failure != null) {
                            finishWith("読み込み失敗: " + failure);
                            return;
                        }
                        onLoaded(isPdf);
                    }
                });
            }
        }).start();
    }

    private void loadPdf(Uri uri) throws Exception {
        pdf = new PdfSource(this, uri);
        sourceName = "PDF（" + pdf.pageCount() + " ページ）";
        sources.clear();
        sources.add(pdf.renderPage(0, settings.widthDots()));
        pageIndex = 0;
    }

    private void loadImages(List<Uri> uris) throws Exception {
        sources.clear();
        for (int i = 0; i < uris.size(); i++) {
            final Uri uri = uris.get(i);
            Bitmap bitmap = Renderer.decodeSampled(new Renderer.StreamOpener() {
                @Override
                public InputStream open() throws Exception {
                    InputStream stream = getContentResolver().openInputStream(uri);
                    if (stream == null) {
                        throw new Exception("画像を開けませんでした");
                    }
                    return stream;
                }
            }, settings.widthDots());
            sources.add(bitmap);
        }
        sourceName = sources.size() == 1 ? "画像 1 枚" : "画像 " + sources.size() + " 枚";
        pageIndex = 0;
    }

    private void onLoaded(boolean isPdf) {
        source.setText(sourceName);
        if (isPdf && pdf != null && pdf.pageCount() > 1) {
            pageBar.setVisibility(View.VISIBLE);
            updatePageLabel();
        }
        schedulePreview();
    }

    private void movePage(int delta) {
        if (pdf == null) {
            return;
        }
        int next = pageIndex + delta;
        if (next < 0 || next >= pdf.pageCount()) {
            return;
        }
        pageIndex = next;
        sources.clear();
        sources.add(pdf.renderPage(pageIndex, settings.widthDots()));
        updatePageLabel();
        schedulePreview();
    }

    private void updatePageLabel() {
        if (pdf != null) {
            pageLabel.setText((pageIndex + 1) + " / " + pdf.pageCount());
        }
    }

    // ------------------------------------------------------------------ 描画

    private void schedulePreview() {
        handler.removeCallbacks(previewTask);
        handler.postDelayed(previewTask, 150);
    }

    private void updatePreview() {
        if (sources.isEmpty()) {
            return;
        }
        try {
            current = build();
            preview.setImageBitmap(current);
            status.setText(current.getWidth() + " × " + current.getHeight() + " dot  /  約 "
                    + Math.round(current.getHeight() / 8f) + " mm");
        } catch (Throwable throwable) {
            status.setText("プレビュー生成に失敗: " + throwable);
        }
    }

    /** 現在の設定で印刷用ビットマップを組み立てる。 */
    private Bitmap build() {
        int widthDots = settings.widthDots();
        int selectedMode = mode.getCheckedRadioButtonId() == R.id.mode_threshold
                ? Renderer.MODE_THRESHOLD : Renderer.MODE_DITHER;
        int limit = Math.max(1, threshold.getProgress());
        int percent = scale.getProgress() + MIN_SCALE;
        int target = Math.max(16, widthDots * percent / 100);

        List<Bitmap> pages = new ArrayList<Bitmap>();
        List<Bitmap> input = allPagesRequested() ? renderAllPdfPages() : sources;
        for (int i = 0; i < input.size(); i++) {
            Bitmap scaled = Renderer.scaleToWidth(input.get(i), target);
            Bitmap mono = Renderer.binarize(scaled, selectedMode, limit, 1f, 1f, false);
            pages.add(Renderer.padToWidth(mono, widthDots));
        }

        String text = caption.getText().toString().trim();
        if (text.length() > 0 || settings.timestamp()) {
            Bitmap head = Renderer.renderText(text.length() > 0 ? text : " ", widthDots,
                    Math.max(20, (int) (settings.fontSize() * 0.8f)), false, "",
                    settings.timestamp());
            pages.add(0, Renderer.binarize(head, Renderer.MODE_THRESHOLD, 150, 1f, 1f, false));
        }
        return pages.size() == 1 ? pages.get(0) : Renderer.stack(pages, 10, widthDots);
    }

    private boolean allPagesRequested() {
        return pdf != null && allPages.isChecked();
    }

    private List<Bitmap> renderAllPdfPages() {
        List<Bitmap> pages = new ArrayList<Bitmap>();
        int count = Math.min(pdf.pageCount(), 20);
        for (int i = 0; i < count; i++) {
            pages.add(pdf.renderPage(i, settings.widthDots()));
        }
        return pages;
    }

    // ------------------------------------------------------------------ 印刷

    private void print() {
        if (current == null) {
            Toast.makeText(this, "プレビューがまだできていません", Toast.LENGTH_SHORT).show();
            return;
        }
        if (!settings.isConfigured()) {
            Toast.makeText(this, "先に設定でプリンタの IP を入力してください", Toast.LENGTH_LONG).show();
            startActivity(new Intent(this, SettingsActivity.class));
            return;
        }
        settings.setImage(mode.getCheckedRadioButtonId() == R.id.mode_threshold
                ? Renderer.MODE_THRESHOLD : Renderer.MODE_DITHER, threshold.getProgress());

        printButton.setEnabled(false);
        status.setText("送信中…");
        String kind = pdf != null ? HistoryStore.KIND_PDF : HistoryStore.KIND_IMAGE;
        String title = caption.getText().toString().trim();
        if (title.length() == 0) {
            title = sourceName;
        }
        Printing.printAsync(this, current, 1, kind, title, sourceName, new Printing.Callback() {
            @Override
            public void onResult(boolean ok, String message) {
                printButton.setEnabled(true);
                status.setText(message);
                Toast.makeText(ShareActivity.this, message, Toast.LENGTH_SHORT).show();
                if (ok) {
                    finish();
                }
            }
        });
    }

    private void finishWith(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
        finish();
    }
}
