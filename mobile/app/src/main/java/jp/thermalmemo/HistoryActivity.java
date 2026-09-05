package jp.thermalmemo;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.widget.AdapterView;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.ListView;
import android.widget.SimpleAdapter;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** 端末内の印刷履歴。タップで再印刷・プレビュー・削除。 */
public class HistoryActivity extends Activity {

    private ListView list;
    private EditText query;
    private TextView empty;

    private HistoryStore store;
    private List<HistoryStore.Entry> entries = new ArrayList<HistoryStore.Entry>();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_history);
        store = new HistoryStore(this);

        list = (ListView) findViewById(R.id.list);
        query = (EditText) findViewById(R.id.query);
        empty = (TextView) findViewById(R.id.empty);

        query.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
            }

            @Override
            public void afterTextChanged(Editable s) {
                reload();
            }
        });

        list.setOnItemClickListener(new AdapterView.OnItemClickListener() {
            @Override
            public void onItemClick(AdapterView<?> parent, View view, int position, long id) {
                showActions(entries.get(position));
            }
        });

        reload();
    }

    @Override
    protected void onDestroy() {
        store.close();
        super.onDestroy();
    }

    private void reload() {
        entries = store.list(query.getText().toString(), 300);
        List<Map<String, String>> rows = new ArrayList<Map<String, String>>();
        for (int i = 0; i < entries.size(); i++) {
            HistoryStore.Entry entry = entries.get(i);
            Map<String, String> row = new HashMap<String, String>();
            row.put("title", entry.label());
            row.put("subtitle", entry.subtitle());
            rows.add(row);
        }
        SimpleAdapter adapter = new SimpleAdapter(this, rows,
                android.R.layout.simple_list_item_2,
                new String[]{"title", "subtitle"},
                new int[]{android.R.id.text1, android.R.id.text2});
        list.setAdapter(adapter);
        empty.setVisibility(entries.isEmpty() ? View.VISIBLE : View.GONE);
    }

    private void showActions(final HistoryStore.Entry entry) {
        String[] actions = {"もう一度印刷", "プレビュー", "削除"};
        new AlertDialog.Builder(this)
                .setTitle(entry.label())
                .setItems(actions, new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface dialog, int which) {
                        if (which == 0) {
                            reprint(entry);
                        } else if (which == 1) {
                            showPreview(entry);
                        } else {
                            confirmDelete(entry);
                        }
                    }
                })
                .show();
    }

    private void reprint(HistoryStore.Entry entry) {
        Bitmap image = store.imageOf(entry);
        if (image == null) {
            Toast.makeText(this, "この履歴には画像が残っていません", Toast.LENGTH_SHORT).show();
            return;
        }
        Printing.printAsync(this, image, 1, entry.kind, entry.title, entry.body,
                new Printing.Callback() {
                    @Override
                    public void onResult(boolean ok, String message) {
                        Toast.makeText(HistoryActivity.this, message, Toast.LENGTH_SHORT).show();
                        reload();
                    }
                });
    }

    private void showPreview(HistoryStore.Entry entry) {
        Bitmap image = store.imageOf(entry);
        if (image == null) {
            Toast.makeText(this, "画像が残っていません", Toast.LENGTH_SHORT).show();
            return;
        }
        ImageView view = new ImageView(this);
        view.setAdjustViewBounds(true);
        view.setImageBitmap(image);
        new AlertDialog.Builder(this).setView(view).setPositiveButton("閉じる", null).show();
    }

    private void confirmDelete(final HistoryStore.Entry entry) {
        new AlertDialog.Builder(this)
                .setMessage("この履歴を削除しますか？")
                .setPositiveButton("削除", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface dialog, int which) {
                        store.delete(entry);
                        reload();
                    }
                })
                .setNegativeButton("やめる", null)
                .show();
    }
}
