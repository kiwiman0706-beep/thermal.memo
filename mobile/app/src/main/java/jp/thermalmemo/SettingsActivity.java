package jp.thermalmemo;

import android.app.Activity;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

/** プリンタ・体裁の設定。 */
public class SettingsActivity extends Activity {

    private static final String[] PAPER_LABELS = {"58mm (384dot)", "80mm (576dot)",
            "80mm (512dot)", "112mm (832dot)", "カスタム"};
    private static final int[] PAPER_DOTS = {384, 576, 512, 832, -1};

    private EditText host;
    private EditText port;
    private EditText widthDots;
    private EditText feedLines;
    private EditText chunkRows;
    private EditText fontSize;
    private CheckBox cut;
    private CheckBox timestamp;
    private CheckBox history;
    private Spinner paper;
    private TextView status;

    private Settings settings;
    private final Handler handler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_settings);
        settings = new Settings(this);

        host = (EditText) findViewById(R.id.host);
        port = (EditText) findViewById(R.id.port);
        widthDots = (EditText) findViewById(R.id.width_dots);
        feedLines = (EditText) findViewById(R.id.feed_lines);
        chunkRows = (EditText) findViewById(R.id.chunk_rows);
        fontSize = (EditText) findViewById(R.id.font_size);
        cut = (CheckBox) findViewById(R.id.cut);
        timestamp = (CheckBox) findViewById(R.id.timestamp);
        history = (CheckBox) findViewById(R.id.history);
        paper = (Spinner) findViewById(R.id.paper);
        status = (TextView) findViewById(R.id.status);

        host.setText(settings.host());
        port.setText(String.valueOf(settings.port()));
        widthDots.setText(String.valueOf(settings.widthDots()));
        feedLines.setText(String.valueOf(settings.feedLines()));
        chunkRows.setText(String.valueOf(settings.chunkRows()));
        fontSize.setText(String.valueOf(settings.fontSize()));
        cut.setChecked(settings.cut());
        timestamp.setChecked(settings.timestamp());
        history.setChecked(settings.historyEnabled());

        ArrayAdapter<String> adapter = new ArrayAdapter<String>(this,
                android.R.layout.simple_spinner_item, PAPER_LABELS);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        paper.setAdapter(adapter);
        paper.setSelection(indexOfDots(settings.widthDots()));
        paper.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                if (PAPER_DOTS[position] > 0) {
                    widthDots.setText(String.valueOf(PAPER_DOTS[position]));
                }
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
            }
        });

        findViewById(R.id.save).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                save();
                Toast.makeText(SettingsActivity.this, "保存しました", Toast.LENGTH_SHORT).show();
                finish();
            }
        });

        findViewById(R.id.test_connection).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                testConnection();
            }
        });

        findViewById(R.id.test_page).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                printTestPage();
            }
        });
    }

    private static int indexOfDots(int dots) {
        for (int i = 0; i < PAPER_DOTS.length; i++) {
            if (PAPER_DOTS[i] == dots) {
                return i;
            }
        }
        return PAPER_DOTS.length - 1;
    }

    private int parse(EditText field, int fallback, int min, int max) {
        try {
            int value = Integer.parseInt(field.getText().toString().trim());
            if (value < min || value > max) {
                field.setText(String.valueOf(fallback));
                return fallback;
            }
            return value;
        } catch (NumberFormatException error) {
            field.setText(String.valueOf(fallback));
            return fallback;
        }
    }

    private void save() {
        settings.setPrinter(
                host.getText().toString(),
                parse(port, 9100, 1, 65535),
                parse(widthDots, 576, 64, 4096),
                cut.isChecked(),
                parse(feedLines, 3, 0, 20),
                parse(chunkRows, 128, 8, 1024),
                8000);
        settings.setFormat(parse(fontSize, 30, 10, 120), timestamp.isChecked(), history.isChecked());
    }

    private void testConnection() {
        save();
        final String target = settings.host() + ":" + settings.port();
        status.setText("接続テスト中… " + target);
        final int timeout = settings.timeoutMs();
        final String printerHost = settings.host();
        final int printerPort = settings.port();

        new Thread(new Runnable() {
            @Override
            public void run() {
                String message;
                try {
                    long started = System.currentTimeMillis();
                    PrinterClient.testConnection(printerHost, printerPort, timeout);
                    message = "接続OK  " + target + "  ("
                            + (System.currentTimeMillis() - started) + " ms)";
                } catch (Throwable error) {
                    message = "接続失敗: " + PrinterClient.describe(error);
                }
                final String result = message;
                handler.post(new Runnable() {
                    @Override
                    public void run() {
                        status.setText(result);
                    }
                });
            }
        }).start();
    }

    private void printTestPage() {
        save();
        String sample = "thermal.memo テストページ\n"
                + "あいうえお 漢字 ｶﾀｶﾅ ABCabc 0123\n"
                + "髙﨑 ①②③ ㎎ ㎖ ℃ №\n"
                + "用紙幅 " + settings.widthDots() + " dot / カット "
                + (settings.cut() ? "ON" : "OFF");
        Bitmap rendered = Renderer.renderText(sample, settings.widthDots(), settings.fontSize(),
                false, "", true);
        Bitmap mono = Renderer.binarize(rendered, Renderer.MODE_THRESHOLD, 150, 1f, 1f, false);
        status.setText("送信中…");
        Printing.printAsync(this, mono, 1, HistoryStore.KIND_TEXT, "テストページ", sample,
                new Printing.Callback() {
                    @Override
                    public void onResult(boolean ok, String message) {
                        status.setText(message);
                    }
                });
    }
}
