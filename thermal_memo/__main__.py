"""エントリポイント。

  GUI :  python -m thermal_memo
  CLI :  python -m thermal_memo print-text "こんにちは" --host 192.168.1.50
         python -m thermal_memo print-file memo.pdf --mode thumbnail
         python -m thermal_memo test --host 192.168.1.50
"""

from __future__ import annotations

import argparse
import sys

from . import __version__, config


def _printer_config(args, cfg):
    from .printer import PrinterConfig

    data = dict(cfg["printer"])
    if args.host:
        data["host"] = args.host
    if args.port:
        data["port"] = args.port
    if args.width:
        data["width_dots"] = args.width
    if args.no_cut:
        data["cut"] = False
    return PrinterConfig.from_dict(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thermal_memo", description="サーマルプリンタ メモ印刷")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--host"), parser.add_argument("--port", type=int)
    parser.add_argument("--width", type=int, help="印字ドット数")
    parser.add_argument("--no-cut", action="store_true")
    sub = parser.add_subparsers(dest="command")

    text_cmd = sub.add_parser("print-text", help="テキストを印刷")
    text_cmd.add_argument("text", nargs="?", help="省略時は標準入力から読む")
    text_cmd.add_argument("--size", type=int, default=None)
    text_cmd.add_argument("--copies", type=int, default=1)

    file_cmd = sub.add_parser("print-file", help="PDF / Word / 画像を印刷")
    file_cmd.add_argument("path")
    file_cmd.add_argument("--mode", choices=["text", "thumbnail"], default="text")
    file_cmd.add_argument("--pages", default="all")
    file_cmd.add_argument("--copies", type=int, default=1)

    sub.add_parser("test", help="接続テスト")
    sub.add_parser("test-page", help="テストページを印刷")

    args = parser.parse_args(argv)
    cfg = config.load()

    if args.command is None:
        from .app import main as gui_main

        return gui_main()

    from . import documents, printer, render

    pcfg = _printer_config(args, cfg)

    if args.command == "test":
        ok, message = printer.test_connection(pcfg)
        print(message)
        return 0 if ok else 1

    text_cfg = cfg["text"]

    if args.command == "test-page":
        image = render.text_to_image(
            "thermal.memo テストページ\nあいうえお 漢字 ABCabc 0123\n"
            f"用紙幅 {pcfg.width_dots} dot",
            width_dots=pcfg.width_dots, font_path=text_cfg["font_path"],
            font_size=text_cfg["font_size"],
        )
    elif args.command == "print-text":
        body = args.text if args.text is not None else sys.stdin.read()
        if not body.strip():
            print("印刷するテキストがありません", file=sys.stderr)
            return 1
        image = render.text_to_image(
            body, width_dots=pcfg.width_dots, font_path=text_cfg["font_path"],
            font_size=args.size or text_cfg["font_size"],
            line_spacing=text_cfg["line_spacing"], margin=text_cfg["margin"],
            timestamp=text_cfg["timestamp"], timestamp_format=text_cfg["timestamp_format"],
        )
    else:  # print-file
        if args.mode == "thumbnail":
            pages = documents.render_pages(args.path, pages=args.pages, width_dots=pcfg.width_dots)
            image = render.stack(
                [render.process_image(p, width_dots=pcfg.width_dots, mode="threshold", autocrop=False)
                 for p in pages],
                width_dots=pcfg.width_dots,
            )
        else:
            body = documents.extract_text(args.path, pages=args.pages)
            image = render.text_to_image(
                body, width_dots=pcfg.width_dots, font_path=text_cfg["font_path"],
                font_size=max(18, text_cfg["font_size"] - 4),
                header=args.path, timestamp=True,
                timestamp_format=text_cfg["timestamp_format"],
            )

    copies = getattr(args, "copies", 1)
    try:
        sent = printer.print_image(pcfg, image, copies=copies)
    except printer.PrinterError as exc:
        print(f"印刷失敗: {exc}", file=sys.stderr)
        return 1
    print(f"送信しました: {sent} バイト / 約 {image.height / 8:.0f} mm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
