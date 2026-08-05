"""Attribution that travels with the dictionary.

CC BY-SA 4.0 §3.a.1 requires a downstream user to *retain* the attribution
notice the licensor supplied, and §3.a.3 lets that notice be satisfied "in any
reasonable manner based on the medium" — including by a link. Left at that, the
credit a reader actually sees depends entirely on the goodwill of whoever ships
the file, and a notice that exists only in this repository cannot be retained by
someone who embeds the .mobi inside their own app.

So the notice is generated into three places, none of which a repackager has to
opt into:

1. **Container metadata** — ``description``/``website`` in the StarDict .ifo,
   ``dc:rights``/``dc:publisher`` in the MOBI OPF. Read by the device, and the
   first thing a developer inspecting the file sees.
2. **ATTRIBUTION.txt** beside the artifacts, carrying the full source list from
   the project's LICENSE-DATA, so every release bundle is self-contained.
3. **An entry inside the dictionary itself** — :func:`attribution_entry`. Kobo's
   dicthtml format has no metadata block at all, so this is the only mechanism
   that reaches a Kobo user; it is also the only one an end user can *look up*.
   Ship the data, ship the credit: they are the same file.

The obligations themselves are spelled out once, in each project's LICENSE-DATA.
This module only stamps the short form.
"""

from __future__ import annotations

from pathlib import Path

from .schema import Entry

#: The dictionary data is share-alike by inheritance, not by preference — see
#: dict-en-vi/LICENSE-DATA. Changing this string is a licensing decision.
DATA_LICENSE = "CC BY-SA 4.0"
DATA_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"

HOMEPAGE = "https://github.com/thichhoc-org/thichhoc-dict"

#: Upstream corpora whose own licenses also require a notice, per language pair.
#: Short enough to fit in a popup — the full list, with license texts, is in
#: LICENSE-DATA and is what ATTRIBUTION.txt carries.
DATA_SOURCES: dict[str, str] = {
    "en-vi": "WordNet 3.1 (Princeton), CMUdict (CMU), Wiktionary",
}

#: Headword of the in-dictionary credit entry, plus the other spellings that
#: should reach it. Deliberately not a real English word: hijacking "about"
#: would cost a reader the lookup they actually wanted.
CREDIT_HEADWORD = "thichhoc"
CREDIT_FORMS = ("thichhoc-dict", "thichhoc.com")


def short_notice(name: str, lang: str = "", sep: str = " ") -> str:
    """The credit a reuser puts on an About screen.

    ``sep`` is how the lines join: a space for anywhere the notice has to be one
    string, ``"\\n    "`` for the block quoted in ATTRIBUTION.txt — where a
    single 200-column line is exactly the thing nobody copies correctly.
    """
    sources = DATA_SOURCES.get(lang, "")
    parts = [
        f"Dữ liệu từ điển: {name} (thichhoc-dict), giấy phép {DATA_LICENSE}.",
        HOMEPAGE,
    ]
    if sources:
        parts.append(f"Nguồn gốc: {sources}.")
    return sep.join(parts)


def attribution_entry(name: str, lang: str, version: str = "", date: str = "") -> Entry:
    """The credit entry that ships inside the dictionary.

    ``pos`` is empty on purpose: this is not a word, and the renderer prints the
    part-of-speech span verbatim, so any value here would label the credit as a
    noun. Sorting handles it (``entry_order`` falls through to its default
    bucket) and validation never sees it — the entry is synthesized at build
    time and is not part of the entry store.
    """
    stamp = " ".join(x for x in (version, f"({date})" if date else "") if x)
    sources = DATA_SOURCES.get(lang, "")

    text = f"{name} — từ điển mã nguồn mở"
    if stamp:
        text += f", bản {stamp}"
    text += (
        f". Dữ liệu theo giấy phép {DATA_LICENSE}"
        + (f"; nguồn gốc: {sources}" if sources else "")
        + f". Bản mới nhất, mã nguồn và nơi báo lỗi: {HOMEPAGE}"
    )

    lang_code = lang.split("-")[0] or "en"
    return Entry(
        id=f"{lang_code}:{CREDIT_HEADWORD}:meta",
        lang=lang,
        headword=CREDIT_HEADWORD,
        pos="",
        variants=list(CREDIT_FORMS),
        senses_vi=[text],
        freq_tier=1,
        source="thichhoc",
    )


_HEADER = """\
================================================================
{name}
bản {version} · {date}
================================================================

Dữ liệu từ điển:  {license}
                  {license_url}
Mã nguồn:         MIT — xem LICENSE trong repo
Nguồn / báo lỗi:  {homepage}


GHI NGUỒN BẮT BUỘC
------------------

Phát hành lại bộ dữ liệu này, hoặc nhúng nó vào phần mềm của bạn, thì
{license} (§3.a) buộc bạn giữ phần ghi nguồn dưới đây và đặt nó ở nơi
NGƯỜI DÙNG CUỐI ĐỌC ĐƯỢC — màn hình "Giới thiệu"/"Credits" của phần mềm,
hoặc trang thông tin của từ điển:

    {notice}
    [Đã chỉnh sửa dữ liệu. / Giữ nguyên, không chỉnh sửa.]

Kèm theo đó, giấy phép buộc bạn:

  - nêu rõ nếu đã chỉnh sửa dữ liệu;
  - phát hành bản phái sinh theo chính {license} (điều khoản share-alike);
  - không áp thêm điều kiện pháp lý hay biện pháp kỹ thuật nào ngăn người
    khác làm những gì giấy phép này cho phép;
  - giữ nguyên phần ghi nguồn của các nguồn gốc liệt kê bên dưới. WordNet
    và CMUdict có yêu cầu ghi nguồn riêng, độc lập với {license}.

Bộ dữ liệu có sẵn một mục từ ghi nguồn: tra "{credit}" trong chính từ điển.
Xóa mục đó khỏi bản phát hành lại là gỡ bỏ phần ghi nguồn mà giấy phép
buộc phải giữ.


REQUIRED ATTRIBUTION (English)
------------------------------

If you redistribute this dictionary data, or embed it in your own software,
{license} (§3.a) requires you to retain the notice below and to present it
where YOUR END USERS CAN READ IT — your About/Credits screen, or the
dictionary's own information page:

    Dictionary data: {name} (thichhoc-dict), licensed {license}.
    {homepage}
    [Modified. / Unmodified.]

You must also indicate if you modified the data, license any adaptation under
{license} itself, apply no additional legal or technical restrictions, and
retain the upstream notices listed below — WordNet and CMUdict carry their own
attribution requirements, independent of {license}.

The data ships a credit entry: look up "{credit}" in the dictionary itself.
Removing it from a redistribution removes attribution the license requires you
to keep.


================================================================
NGUỒN GỐC ĐẦY ĐỦ  ·  FULL SOURCE ATTRIBUTION
================================================================

"""


def attribution_text(
    name: str,
    lang: str,
    version: str,
    date: str,
    license_data: Path | None = None,
) -> str:
    """Full ATTRIBUTION.txt: the required-notice header, then LICENSE-DATA.

    LICENSE-DATA is appended verbatim rather than summarised — it is the
    audit trail of every upstream source, and a bundle that paraphrases it
    would drift from the file the project is actually bound by.
    """
    text = _HEADER.format(
        name=name,
        version=version or "—",
        date=date or "—",
        license=DATA_LICENSE,
        license_url=DATA_LICENSE_URL,
        homepage=HOMEPAGE,
        notice=short_notice(name, lang, sep="\n    "),
        credit=CREDIT_HEADWORD,
    )

    if license_data and license_data.is_file():
        return text + license_data.read_text(encoding="utf-8")
    return text + (
        "LICENSE-DATA không có trong bản build này — xem\n"
        f"{HOMEPAGE}\n"
    )


__all__ = [
    "DATA_LICENSE",
    "DATA_LICENSE_URL",
    "HOMEPAGE",
    "DATA_SOURCES",
    "CREDIT_HEADWORD",
    "attribution_entry",
    "attribution_text",
    "short_notice",
]
