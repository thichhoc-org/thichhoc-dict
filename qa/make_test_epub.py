#!/usr/bin/env python3
"""Build a small EPUB whose only job is to exercise dictionary lookup.

Plan §7.5 makes on-device lookup a release gate, and that cannot be checked
from a terminal: the question is whether long-pressing a word *while reading*
returns the right entry. So this generates a real book — running prose, not a
word list — because tapping a word mid-sentence is the actual gesture, and a
bare list does not reproduce the way a reader meets an inflected form.

Every target word is verified against the built entry store before it goes in,
and each chapter targets one thing that can independently be broken:

  1. inflected forms       the headline feature — "stopped" must find "stop"
  2. translated entries    tier 1, where a full entry should render
  3. untranslated entries  the skeleton note should show, not an empty popup
  4. multi-sense headwords one page carrying several parts of speech

The checklist chapter is deliberately last: read it on the device with the
book open, so a failure is recorded against the word that caused it.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.store import iter_entries


@dataclass(slots=True)
class Chapter:
    id: str
    title: str
    intro: str
    paragraphs: list[str]
    targets: list[str]


# Prose written so each target word appears in a natural sentence, at the
# inflection a reader would actually meet, and far enough into the line that
# long-pressing it is a realistic gesture rather than a corner case.
CHAPTERS = [
    Chapter(
        id="inflect",
        title="1 · Biến thể từ",
        intro="Chạm giữ vào các từ <b>in đậm</b>. Mỗi từ là một dạng đã biến đổi — "
              "từ điển phải trả về mục từ gốc, không phải báo không tìm thấy.",
        paragraphs=[
            "He had <b>stopped</b> at the edge of the water, watching the "
            "<b>geese</b> come down through the mist. The morning was colder "
            "than he had expected, and he had <b>brought</b> nothing warm.",
            "She <b>ran</b> the whole way, and by the time she arrived the "
            "committee had already <b>begun</b> to argue about which "
            "<b>criteria</b> mattered. Two of them had <b>taught</b> the "
            "subject for years; the rest had merely read about it.",
            "The <b>children</b> had left their <b>knives</b> on the table, "
            "beside a bowl of half-eaten fruit. Three <b>mice</b> had "
            "<b>gotten</b> in overnight and the cat, <b>panicked</b>, had "
            "<b>hidden</b> under the stairs.",
            "It was the <b>worst</b> harvest in living memory. The oxen were "
            "<b>driven</b> out at dawn, the fields were <b>swept</b> clean, "
            "and by evening the <b>indices</b> everyone had been quoting all "
            "spring looked <b>foolish</b>.",
        ],
        targets=["stopped", "geese", "brought", "ran", "begun", "criteria",
                 "taught", "children", "knives", "mice", "gotten", "panicked",
                 "hidden", "worst", "driven", "swept", "indices"],
    ),
    Chapter(
        id="translated",
        title="2 · Mục từ đã có nghĩa tiếng Việt",
        intro="Những từ này nằm trong tier 1 và đã được dịch. Mục từ phải hiện "
              "<b>nghĩa tiếng Việt</b>, không phải dòng “chưa có nghĩa”.",
        paragraphs=[
            "The <b>captain</b> would <b>coach</b> the younger players himself "
            "on Sundays, and the <b>minutes</b> of every meeting recorded it "
            "as a <b>statement</b> of intent rather than a decision.",
            "Her <b>purchase</b> of the building was <b>announced</b> in a "
            "single paragraph. The <b>protection</b> it offered was <b>limited</b>, "
            "but she could <b>manage</b> — she had learned to <b>distance</b> "
            "herself from what she could not fix.",
            "The <b>whole</b> arrangement rested on a <b>spring</b> that had "
            "long since lost its tension. Nobody could <b>ensure</b> anything; "
            "they could only <b>advocate</b>, and hope the <b>breakthrough</b> "
            "arrived before the money ran out.",
        ],
        targets=["captain", "coach", "minutes", "statement", "purchase",
                 "announced", "protection", "limited", "manage", "distance",
                 "whole", "spring", "ensure", "advocate", "breakthrough"],
    ),
    Chapter(
        id="skeleton",
        title="3 · Mục từ chưa có nghĩa",
        intro="Những từ này chưa được dịch. Mục từ phải hiện định nghĩa tiếng Anh "
              "và dòng <b>“— chưa có nghĩa tiếng Việt (bản skeleton) —”</b>. "
              "Nếu popup trống thì đó là lỗi.",
        paragraphs=[
            "The <b>aardwolf</b> is a nocturnal animal, rarely seen. Its diet "
            "is almost entirely insects, which makes it an <b>anomalous</b> "
            "member of its family and a <b>perennial</b> difficulty for anyone "
            "writing a field guide.",
            "He described the arrangement as <b>serendipitous</b>, though the "
            "word did little to explain how a <b>zygote</b> in a laboratory "
            "freezer had become a <b>quandary</b> for three separate ethics "
            "committees.",
        ],
        targets=["aardwolf", "anomalous", "perennial", "serendipitous",
                 "zygote", "quandary"],
    ),
    Chapter(
        id="multipos",
        title="4 · Từ nhiều từ loại",
        intro="Mỗi từ dưới đây có nhiều từ loại. Một lần tra phải hiện "
              "<b>tất cả</b> trên cùng một trang, xếp theo tần suất — động từ "
              "trước danh từ với <i>run</i>, danh từ trước động từ với <i>table</i>.",
        paragraphs=[
            "She would <b>run</b> the bakery herself now. There was a "
            "<b>light</b> on in the back room, a <b>table</b> pushed against "
            "the wall, and a <b>book</b> lying open where someone had left it.",
            "They agreed to <b>table</b> the motion. It was the <b>right</b> "
            "decision, though nobody said so, and the <b>set</b> of problems "
            "it postponed would still be there in the spring.",
        ],
        targets=["run", "light", "table", "book", "right", "set"],
    ),
]

CSS = """\
body { font-family: serif; line-height: 1.65; margin: 1em; }
h1 { font-size: 1.3em; margin: 0 0 .3em; }
.intro { font-size: .9em; color: #444; border-left: 3px solid #ccc;
         padding-left: .8em; margin: 0 0 1.2em; }
p { margin: 0 0 1em; text-indent: 1.2em; }
p.first { text-indent: 0; }
table { border-collapse: collapse; width: 100%; font-size: .85em; }
td, th { border-bottom: 1px solid #ddd; padding: .35em .4em; text-align: left; }
.box { border: 1px solid #ccc; padding: .8em; margin: 1em 0; font-size: .9em; }
"""

_XHTML = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"
      xml:lang="en" lang="en">
<head><title>{title}</title><meta charset="utf-8"/>
<link rel="stylesheet" type="text/css" href="style.css"/></head>
<body>{body}</body>
</html>
"""


def resolve_index(entries_dir: Path) -> dict[str, str]:
    """lookup form (lowercased) -> the headword it resolves to."""
    index: dict[str, str] = {}
    for entry in iter_entries(entries_dir):
        for form in entry.lookup_forms:
            index.setdefault(form.lower(), entry.headword)
    return index


def translated_headwords(entries_dir: Path) -> set[str]:
    return {e.headword.lower() for e in iter_entries(entries_dir) if e.senses_vi}


def build_chapter(chapter: Chapter) -> str:
    paras = "".join(
        f'<p class="first">{p}</p>' if i == 0 else f"<p>{p}</p>"
        for i, p in enumerate(chapter.paragraphs)
    )
    body = (f"<h1>{chapter.title}</h1>"
            f'<div class="intro">{chapter.intro}</div>{paras}')
    return _XHTML.format(title=chapter.title, body=body)


def build_checklist(rows: list[tuple[str, str, str, str]]) -> str:
    trs = "".join(
        f"<tr><td>{form}</td><td>{resolves}</td><td>{state}</td><td>{ch}</td></tr>"
        for form, resolves, state, ch in rows
    )
    body = (
        "<h1>5 · Bảng đối chiếu</h1>"
        '<div class="intro">Cột “ra mục từ” là kết quả <b>đúng</b> mà từ điển '
        "phải trả về. Đọc bảng này trên máy, mở song song với các chương trước.</div>"
        '<div class="box">Nếu một từ tra không ra: ghi lại từ đó và chương chứa nó. '
        "Đó là ca cần thêm vào <code>tests/inflection_500.txt</code>.</div>"
        "<table><tr><th>chạm vào</th><th>ra mục từ</th><th>trạng thái</th>"
        f"<th>chương</th></tr>{trs}</table>"
    )
    return _XHTML.format(title="Bảng đối chiếu", body=body)


def build_intro(counts: dict[str, int]) -> str:
    body = f"""<h1>Sách thử tra từ — thichhoc.com</h1>
<div class="intro">Sách này không có nội dung để đọc. Nó tồn tại để kiểm tra
một việc: chạm giữ vào một từ khi đang đọc thì từ điển có trả về đúng mục từ
không.</div>
<p class="first">Cài từ điển trước, rồi mở sách này và làm lần lượt bốn chương.
Mỗi chương kiểm tra một thứ có thể hỏng độc lập với nhau.</p>
<div class="box">
<b>Đang kiểm tra:</b><br/>
{counts['total']} từ mục tiêu · {counts['translated']} đã có nghĩa tiếng Việt ·
{counts['skeleton']} còn ở dạng skeleton<br/>
Kho từ điển: {counts['entries']:,} mục từ, {counts['forms']:,} dạng tra được
</div>
<p>Chương 1 là quan trọng nhất. Đó là điểm mà mọi từ điển Anh–Việt trên máy
đọc sách đều hỏng: tra <i>stopped</i> hay <i>geese</i> thì không ra gì, người
đọc phải tự cắt đuôi từ rồi tra lại. Nếu chương 1 pass hết thì phần khác biệt
chính của bộ từ điển này đã hoạt động trên máy thật.</p>
"""
    return _XHTML.format(title="Sách thử tra từ", body=body)


def write_epub(out: Path, chapters: list[tuple[str, str, str]], title: str) -> Path:
    """chapters: [(filename, title, xhtml)] in spine order."""
    out.parent.mkdir(parents=True, exist_ok=True)
    uid = "urn:thichhoc:dict-lookup-test"

    manifest = "\n".join(
        f'    <item id="c{i}" href="{name}" media-type="application/xhtml+xml"/>'
        for i, (name, _, _) in enumerate(chapters)
    )
    spine = "\n".join(f'    <itemref idref="c{i}"/>' for i in range(len(chapters)))
    nav_items = "\n".join(
        f'      <li><a href="{name}">{t}</a></li>' for name, t, _ in chapters
    )
    ncx_points = "\n".join(
        f'    <navPoint id="n{i}" playOrder="{i + 1}"><navLabel><text>{t}</text>'
        f'</navLabel><content src="{name}"/></navPoint>'
        for i, (name, t, _) in enumerate(chapters)
    )

    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">{uid}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>en</dc:language>
    <dc:creator>thichhoc.com</dc:creator>
    <meta property="dcterms:modified">2026-08-04T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="css" href="style.css" media-type="text/css"/>
{manifest}
  </manifest>
  <spine toc="ncx">
{spine}
  </spine>
</package>
"""
    nav = _XHTML.format(title="Mục lục", body=(
        '<nav epub:type="toc"><h1>Mục lục</h1><ol>\n' + nav_items + "\n</ol></nav>"))
    ncx = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="{uid}"/></head>
  <docTitle><text>{title}</text></docTitle>
  <navMap>
{ncx_points}
  </navMap>
</ncx>
"""

    with zipfile.ZipFile(out, "w") as zf:
        # The spec requires mimetype first and stored, or strict readers reject
        # the file outright.
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                    compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml",
                    '<?xml version="1.0" encoding="utf-8"?>\n'
                    '<container version="1.0" '
                    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                    '  <rootfiles><rootfile full-path="OEBPS/content.opf" '
                    'media-type="application/oebps-package+xml"/></rootfiles>\n'
                    "</container>\n", compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", opf, zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/nav.xhtml", nav, zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/toc.ncx", ncx, zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/style.css", CSS, zipfile.ZIP_DEFLATED)
        for name, _, xhtml in chapters:
            zf.writestr(f"OEBPS/{name}", xhtml, zipfile.ZIP_DEFLATED)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--entries", type=Path, default=Path("dict-en-vi/data/entries"))
    parser.add_argument("--out", type=Path, default=Path("build/en-vi/lookup-test.epub"))
    args = parser.parse_args(argv)

    print(f"reading {args.entries}")
    index = resolve_index(args.entries)
    translated = translated_headwords(args.entries)
    print(f"  {len(index):,} lookup forms")

    rows: list[tuple[str, str, str, str]] = []
    missing: list[tuple[str, str]] = []
    n_translated = n_skeleton = 0

    for chapter in CHAPTERS:
        for form in chapter.targets:
            headword = index.get(form.lower())
            if headword is None:
                missing.append((form, chapter.title))
                rows.append((form, "—", "KHÔNG TRA RA", chapter.title.split(" ")[0]))
                continue
            has_vi = headword.lower() in translated
            n_translated += has_vi
            n_skeleton += not has_vi
            rows.append((form, headword,
                         "có nghĩa Việt" if has_vi else "skeleton",
                         chapter.title.split(" ")[0]))

    counts = {
        "total": sum(len(c.targets) for c in CHAPTERS),
        "translated": n_translated,
        "skeleton": n_skeleton,
        "entries": len({v for v in index.values()}),
        "forms": len(index),
    }

    files: list[tuple[str, str, str]] = [("intro.xhtml", "Giới thiệu", build_intro(counts))]
    files += [(f"{c.id}.xhtml", c.title, build_chapter(c)) for c in CHAPTERS]
    files.append(("checklist.xhtml", "5 · Bảng đối chiếu", build_checklist(rows)))

    path = write_epub(args.out, files, "Sách thử tra từ — thichhoc.com")

    print(f"\nwrote {path} ({path.stat().st_size:,} bytes)")
    print(f"  {counts['total']} target words: "
          f"{n_translated} with Vietnamese, {n_skeleton} skeleton")
    if missing:
        # A target that does not resolve is a bug in the dictionary, not the
        # book — surface it here rather than letting it show up on a device.
        print(f"\n  {len(missing)} target(s) DO NOT RESOLVE — fix before testing:")
        for form, where in missing:
            print(f"    {form}  ({where})")
        return 1
    print("  every target word resolves in the built store")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
