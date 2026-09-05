package jp.thermalmemo;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

/**
 * メイン画面。手入力のほか、他アプリからの
 * ACTION_SEND(text/plain) と ACTION_PROCESS_TEXT を受ける。
 */
public class MainActivity extends Activity {

    // API 23 の定数を直接参照せずに済ませる（minSdk を下げても壊れないように）
    private static final String ACTION_PROCESS_TEXT = "android.intent.action.PROCESS_TEXT";
    private static final String EXTRA_PROCESS_TEXT = "android.intent.extra.PROCESS_TEXT";

    private static final int MIN_FONT_SIZE = 16;
    private static final int MENU_SETTINGS = 1;
    private static final int MENU_HISTORY = 2;
    private static final int MENU_TEST_PAGE = 3;

    private EditText input;
    private EditText copies;
    private CheckBox timestamp;
    private SeekBar fontSize;
    private TextView fontSizeValue;
    private TextView status;
    private ImageView preview;
    private Button printButton;

    private Settings settings;
    private Bitmap current;
    private String sharedHeader = "";
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
        setContentView(R.layout.activity_main);
        settings = new Settings(this);

        input = (EditText) findViewById(R.id.input);
        copies = (EditText) findViewById(R.id.copies);
        timestamp = (CheckBox) findViewById(R.id.timestamp);
        fontSize = (SeekBar) findViewById(R.id.font_size);
        fontSizeValue = (TextView) findViewById(R.id.font_size_value);
        status = (TextView) findViewById(R.id.status);
        preview = (ImageView) findViewById(R.id.preview);
        printButton = (Button) findViewById(R.id.print);

        timestamp.setChecked(settings.timestamp());
        fontSize.setProgress(Math.max(0, settings.fontSize() - MIN_FONT_SIZE));
        fontSizeValue.setText(String.valueOf(settings.fontSize()));

        input.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
            }

            @Override
            public void afterTextChanged(Editable s) {
                schedulePreview();
            }
        });

        fontSize.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar bar, int progress, boolean fromUser) {
                fontSizeValue.setText(String.valueOf(progress + MIN_FONT_SIZE));
                schedulePreview();
            }

            @Override
            public void onStartTrackingTouch(SeekBar bar) {
            }

            @Override
            public void onStopTrackingTouch(SeekBar bar) {
            }
        });

        timestamp.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                schedulePreview();
            }
        });

        findViewById(R.id.clear).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                input.setText("");
                sharedHeader = "";
                schedulePreview();
            }
        });

        printButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                print();
            }
        });

        handleIntent(getIntent());
        schedulePreview();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
        schedulePreview();
    }

    @Override
    protected void onResume() {
        super.onResume();
        // 設定画面から戻ったときに用紙幅などを反映する
        schedulePreview();
    }

    /** 他アプリからの共有・テキスト選択を取り込む。 */
    private void handleIntent(Intent intent) {
        if (intent == null) {
            return;
        }
        String action = intent.getAction();
        CharSequence shared = null;

        if (Intent.ACTION_SEND.equals(action)) {
            shared = intent.getStringExtra(Intent.EXTRA_TEXT);
            String subject = intent.getStringExtra(Intent.EXTRA_SUBJECT);
            if (subject != null && subject.trim().length() > 0) {
                sharedHeader = subject.trim();
            }
        } else if (ACTION_PROCESS_TEXT.equals(action)) {
            shared = intent.getCharSequenceExtra(EXTRA_PROCESS_TEXT);
        }

        if (shared != null && shared.length() > 0) {
            input.setText(shared.toString());
            input.setSelection(input.getText().length());
            toast("共有されたテキストを読み込みました");
        }
    }

    private void schedulePreview() {
        handler.removeCallbacks(previewTask);
        handler.postDelayed(previewTask, 180);
    }

    private void updatePreview() {
        String text = input.getText().toString();
        int size = fontSize.getProgress() + MIN_FONT_SIZE;
        Bitmap rendered = Renderer.renderText(text, settings.widthDots(), size, false,
                sharedHeader, timestamp.isChecked());
        // 文字はしきい値方式のほうが鮮明に出る
        current = Renderer.binarize(rendered, Renderer.MODE_THRESHOLD, 150, 1f, 1f, false);
        preview.setImageBitmap(current);
        status.setText(current.getWidth() + " × " + current.getHeight() + " dot  /  約 "
                + Math.round(current.getHeight() / 8f) + " mm");
    }

    private void print() {
        if (input.getText().toString().trim().length() == 0) {
            toast("本文を入力してください");
            return;
        }
        if (!settings.isConfigured()) {
            toast("先に設定でプリンタの IP を入力してください");
            startActivity(new Intent(this, SettingsActivity.class));
            return;
        }
        updatePreview();
        settings.setFormat(fontSize.getProgress() + MIN_FONT_SIZE, timestamp.isChecked(),
                settings.historyEnabled());

        final Bitmap target = current;
        if (target == null) {
            return;
        }
        String body = input.getText().toString();
        String title = firstLine(body);
        printButton.setEnabled(false);
        status.setText("送信中…");
        Printing.printAsync(this, target, parseCopies(), HistoryStore.KIND_TEXT, title, body,
                new Printing.Callback() {
                    @Override
                    public void onResult(boolean ok, String message) {
                        printButton.setEnabled(true);
                        status.setText(message);
                        toast(message);
                    }
                });
    }

    private int parseCopies() {
        try {
            int value = Integer.parseInt(copies.getText().toString().trim());
            return Math.max(1, Math.min(20, value));
        } catch (NumberFormatException error) {
            copies.setText("1");
            return 1;
        }
    }

    private static String firstLine(String body) {
        String[] lines = body.split("\n");
        for (int i = 0; i < lines.length; i++) {
            if (lines[i].trim().length() > 0) {
                String line = lines[i].trim();
                return line.length() > 60 ? line.substring(0, 60) : line;
            }
        }
        return "";
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, MENU_SETTINGS, 0, R.string.settings);
        menu.add(0, MENU_HISTORY, 1, R.string.history);
        menu.add(0, MENU_TEST_PAGE, 2, "テストページ");
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        int id = item.getItemId();
        if (id == MENU_SETTINGS) {
            startActivity(new Intent(this, SettingsActivity.class));
            return true;
        }
        if (id == MENU_HISTORY) {
            startActivity(new Intent(this, HistoryActivity.class));
            return true;
        }
        if (id == MENU_TEST_PAGE) {
            printTestPage();
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    private void printTestPage() {
        if (!settings.isConfigured()) {
            toast("先に設定でプリンタの IP を入力してください");
            startActivity(new Intent(this, SettingsActivity.class));
            return;
        }
        String sample = "thermal.memo テストページ\n"
                + "あいうえお 漢字 ｶﾀｶﾅ ABCabc 0123\n"
                + "髙﨑 ①②③ ㎎ ㎖ ℃ №\n"
                + "用紙幅 " + settings.widthDots() + " dot";
        Bitmap rendered = Renderer.renderText(sample, settings.widthDots(), settings.fontSize(),
                false, "", true);
        Bitmap mono = Renderer.binarize(rendered, Renderer.MODE_THRESHOLD, 150, 1f, 1f, false);
        Printing.printAsync(this, mono, 1, HistoryStore.KIND_TEXT, "テストページ", sample,
                new Printing.Callback() {
                    @Override
                    public void onResult(boolean ok, String message) {
                        status.setText(message);
                        toast(message);
                    }
                });
    }
}
