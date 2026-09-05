package jp.thermalmemo;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;

import java.io.File;
import java.io.FileOutputStream;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/** 印刷履歴（端末内 SQLite ＋ PNG）。 */
public class HistoryStore extends SQLiteOpenHelper {

    public static final String KIND_TEXT = "text";
    public static final String KIND_IMAGE = "image";
    public static final String KIND_PDF = "pdf";

    private static final String DB_NAME = "history.db";
    private static final int DB_VERSION = 1;

    private final Context context;

    public HistoryStore(Context context) {
        super(context.getApplicationContext(), DB_NAME, null, DB_VERSION);
        this.context = context.getApplicationContext();
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE prints ("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                + "created_at TEXT NOT NULL,"
                + "kind TEXT NOT NULL,"
                + "title TEXT NOT NULL DEFAULT '',"
                + "body TEXT NOT NULL DEFAULT '',"
                + "image_path TEXT,"
                + "printer TEXT NOT NULL DEFAULT '',"
                + "status TEXT NOT NULL DEFAULT 'ok',"
                + "error TEXT NOT NULL DEFAULT '')");
        db.execSQL("CREATE INDEX idx_prints_created ON prints(created_at DESC)");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        // 単純にテーブルを作り直す（履歴は失われても致命的でないため）
        db.execSQL("DROP TABLE IF EXISTS prints");
        onCreate(db);
    }

    /** 1 件追加する。画像は PNG としてアプリ専用領域に保存する。 */
    public long add(String kind, Bitmap image, String title, String body, String printer,
                    String status, String error) {
        String now = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.JAPAN).format(new Date());
        String path = null;
        if (image != null) {
            File directory = new File(context.getFilesDir(), "history");
            if (directory.exists() || directory.mkdirs()) {
                File file = new File(directory, System.currentTimeMillis() + ".png");
                FileOutputStream out = null;
                try {
                    out = new FileOutputStream(file);
                    image.compress(Bitmap.CompressFormat.PNG, 100, out);
                    path = file.getAbsolutePath();
                } catch (Exception ignored) {
                    path = null;
                } finally {
                    if (out != null) {
                        try {
                            out.close();
                        } catch (Exception ignored) {
                            // 無視
                        }
                    }
                }
            }
        }
        ContentValues values = new ContentValues();
        values.put("created_at", now);
        values.put("kind", kind);
        values.put("title", title == null ? "" : title);
        values.put("body", body == null ? "" : body);
        values.put("image_path", path);
        values.put("printer", printer == null ? "" : printer);
        values.put("status", status);
        values.put("error", error == null ? "" : error);
        return getWritableDatabase().insert("prints", null, values);
    }

    public List<Entry> list(String query, int limit) {
        List<Entry> result = new ArrayList<Entry>();
        String sql = "SELECT id, created_at, kind, title, body, image_path, printer, status, error"
                + " FROM prints";
        String[] args;
        if (query != null && query.trim().length() > 0) {
            sql += " WHERE title LIKE ? OR body LIKE ?";
            String like = "%" + query.trim() + "%";
            args = new String[]{like, like};
        } else {
            args = new String[0];
        }
        sql += " ORDER BY id DESC LIMIT " + Math.max(1, limit);

        Cursor cursor = getReadableDatabase().rawQuery(sql, args);
        try {
            while (cursor.moveToNext()) {
                Entry entry = new Entry();
                entry.id = cursor.getLong(0);
                entry.createdAt = cursor.getString(1);
                entry.kind = cursor.getString(2);
                entry.title = cursor.getString(3);
                entry.body = cursor.getString(4);
                entry.imagePath = cursor.getString(5);
                entry.printer = cursor.getString(6);
                entry.status = cursor.getString(7);
                entry.error = cursor.getString(8);
                result.add(entry);
            }
        } finally {
            cursor.close();
        }
        return result;
    }

    public Bitmap imageOf(Entry entry) {
        if (entry.imagePath == null) {
            return null;
        }
        return BitmapFactory.decodeFile(entry.imagePath);
    }

    public void delete(Entry entry) {
        if (entry.imagePath != null) {
            File file = new File(entry.imagePath);
            if (file.exists()) {
                boolean removed = file.delete();
                if (!removed) {
                    file.deleteOnExit();
                }
            }
        }
        getWritableDatabase().delete("prints", "id=?", new String[]{String.valueOf(entry.id)});
    }

    /** 履歴 1 件。 */
    public static class Entry {
        public long id;
        public String createdAt;
        public String kind;
        public String title;
        public String body;
        public String imagePath;
        public String printer;
        public String status;
        public String error;

        public String label() {
            String text = title != null && title.length() > 0 ? title : body;
            if (text == null) {
                text = "";
            }
            text = text.replace('\n', ' ').trim();
            if (text.length() > 60) {
                text = text.substring(0, 60) + "…";
            }
            if ("ok".equals(status)) {
                return text;
            }
            return "⚠ " + text;
        }

        public String subtitle() {
            String kindLabel = KIND_IMAGE.equals(kind) ? "画像"
                    : KIND_PDF.equals(kind) ? "PDF" : "テキスト";
            return createdAt + "  " + kindLabel;
        }
    }
}
