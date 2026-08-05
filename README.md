<a href="https://thichhoc.com/brand">
  <img src="docs/assets/thichhoc-daisy.svg" alt="thichhoc" width="96" align="right">
</a>

# Từ điển Anh–Việt cho Kindle, Kobo, KOReader và Boox — mã nguồn mở

**Từ điển Anh–Việt offline cho máy đọc sách**: tra trực tiếp khi đang đọc sách tiếng Anh
trên Kindle, Kobo, KOReader hay Boox — **tra được cả biến thể từ** (`stopped`, `ran`,
`geese`, `criteria`), license sạch 100%, dữ liệu và pipeline mở hoàn toàn.

[![validate → build → release](https://github.com/thichhoc-org/thichhoc-dict/actions/workflows/release.yml/badge.svg)](https://github.com/thichhoc-org/thichhoc-dict/actions/workflows/release.yml)
[![Code license: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Data license: CC BY-SA 4.0](https://img.shields.io/badge/data-CC%20BY--SA%204.0-lightgrey.svg)](dict-en-vi/LICENSE-DATA)
[![Mục từ](https://img.shields.io/badge/mục%20từ-155%2C139-brightgreen.svg)](#số-liệu-thực-tế)
[![Nghĩa tiếng Việt](https://img.shields.io/badge/nghĩa%20tiếng%20Việt-100%25-brightgreen.svg)](#số-liệu-thực-tế)
[![Định dạng](https://img.shields.io/badge/định%20dạng-MOBI%20·%20Kobo%20·%20StarDict-orange.svg)](#tải-về)

**Tra nhanh:** [Tải về](#tải-về) · [Cài trên Kindle](#cài-từ-điển-anhviệt-cho-kindle) ·
[Cài trên Kobo](#cài-từ-điển-anhviệt-cho-kobo) ·
[KOReader / Boox](#cài-từ-điển-anhviệt-cho-koreader-boox-và-goldendict) ·
[Số liệu](#số-liệu-thực-tế) · [Sửa một từ](#sửa-một-từ) ·
[Câu hỏi thường gặp](#câu-hỏi-thường-gặp) · [Góp sức](CONTRIBUTING.md)

---

## Trạng thái dự án

| Project | Trạng thái | Nền tảng |
|---|---|---|
| **[dict-en-vi](dict-en-vi/)** — Từ điển Anh–Việt | Beta — mọi mục từ đã có nghĩa tiếng Việt; đang review theo tầng tần suất | Kindle (MOBI) · Kobo · StarDict |
| **dict-zh-vi** — Từ điển Trung–Việt | Chưa bắt đầu (Phase B) | — |

## Tải về

Bản mới nhất: **[v0.9.0](https://github.com/thichhoc-org/thichhoc-dict/releases/latest)** —
155.139 mục từ, mọi mục đều có nghĩa tiếng Việt. Mỗi bản gồm ba gói, chọn đúng gói cho máy
đọc sách của bạn:

| Tệp | Dùng cho máy | Chép vào |
|---|---|---|
| `thichhoc-en-vi.mobi` | **Kindle** (mọi đời sideload được) | `documents/dictionaries/` |
| `dicthtml-en-vi.zip` | **Kobo** | `.kobo/dict/` |
| `stardict-en-vi.zip` | **KOReader, Boox, GoldenDict, PocketBook** | thư mục từ điển của phần mềm đọc |

Tất cả đều là **từ điển offline** — cài xong không cần mạng, và không dính giới hạn
5–6 thiết bị như từ điển mua trên Kindle Store.

> **Vì sao còn là beta:** nghĩa tiếng Việt đã phủ 100% mục từ nhưng do LLM sinh, chưa mục
> nào qua review của người. Dùng được ngay khi đọc sách; gặp nghĩa nào sai thì
> [mở issue](https://github.com/thichhoc-org/thichhoc-dict/issues/new/choose) — đó là cách
> bản kế tiếp tốt lên.

### Cài từ điển Anh–Việt cho Kindle

1. Cắm Kindle vào máy tính bằng cáp USB.
2. Chép `thichhoc-en-vi.mobi` vào thư mục `documents/dictionaries/`.
3. Rút cáp, vào **Settings → Language & Dictionaries → Dictionaries → English** rồi chọn
   từ điển thichhoc Anh–Việt làm mặc định.
4. Mở một cuốn sách tiếng Anh, chạm giữ vào một từ bất kỳ — kể cả từ đã chia thì như
   `stopped` hay `ran` — nghĩa hiện ngay trong ô popup.

### Cài từ điển Anh–Việt cho Kobo

1. Cài [redphx/kobo-tieng-viet](https://github.com/redphx/kobo-tieng-viet) trước, vì
   firmware gốc của Kobo không hiện tuỳ chọn từ điển tiếng Việt.
2. Cắm Kobo vào máy tính, chép `dicthtml-en-vi.zip` vào thư mục ẩn `.kobo/dict/`.
3. Rút cáp, khởi động lại máy, rồi chọn từ điển tiếng Việt trong phần cài đặt.

### Cài từ điển Anh–Việt cho KOReader, Boox và GoldenDict

Giải nén `stardict-en-vi.zip` rồi chép cả bốn tệp (`.ifo`, `.idx`, `.syn`, `.dict.dz`)
vào một thư mục con trong thư mục từ điển của phần mềm đọc:

- **KOReader** (kể cả KOReader chạy trên chính Kindle hoặc Boox):
  `koreader/data/dict/thichhoc-en-vi/`
- **GoldenDict** trên máy tính: thêm thư mục vào *Edit → Dictionaries → Sources*

Định dạng StarDict luôn build được bằng Python thuần, không cần công cụ ngoài — xem
[docs/build-toolchain.md](docs/build-toolchain.md).

## Vì sao có project này

Ba điều các từ điển Anh–Việt hiện có chưa làm được:

1. **Tra được mọi biến thể từ.** `stopped`, `ran`, `geese`, `criteria` — tất cả phải ra
   kết quả. Đây là phàn nàn số 1 của người dùng máy đọc sách suốt cả thập kỷ: phải mở từ
   điển Anh–Anh cho nó cắt đuôi `-ed`, `-s` rồi tra ngược lại. Bản MOBI dùng markup
   `idx:iform` của Kindle nên máy tự quy về mục từ gốc.
2. **License sạch 100%.** Chỉ dùng nguồn mở đã ghi rõ trong
   [dict-en-vi/LICENSE-DATA](dict-en-vi/LICENSE-DATA). Không đụng tới dữ liệu từ điển
   thương mại dưới bất kỳ hình thức nào — kể cả viết lại hay đưa vào prompt cho LLM.
   Nhờ vậy dự án đứng tên công khai được, và bạn fork rồi phát hành lại cũng được.
3. **Dữ liệu và pipeline mở.** Sai một nghĩa thì sửa đúng một dòng JSONL rồi gửi PR —
   không phải chờ ai đó phát hành bản mới, không phải đi dò link chết trên forum.

## Số liệu thực tế

Chạy `make stats` để tự kiểm chứng. Số liệu ngày 2026-08-05:

| Chỉ số | Giá trị |
|---|---|
| Mục từ | 155.139 |
| Mục từ gốc riêng biệt | 147.192 |
| **Dạng tra được** (mục từ + biến thể) | **285.412** |
| Có phiên âm IPA | 90.718 · 58,5% |
| Có biến thể từ | 121.217 · 78,1% |
| Có định nghĩa tiếng Anh | 155.139 · 100% |
| **Có nghĩa tiếng Việt** | **155.139 · 100%** |
| Đã review bằng mắt người | 0 · 0% |

**Mọi mục từ đều đã có nghĩa tiếng Việt** — không còn mục nào chỉ có định nghĩa tiếng Anh.
Việc còn lại không phải là dịch mà là **review**: nghĩa hiện tại do LLM sinh, và cột cuối
bảng trên đang là 0%. Đó là lý do bản phát hành mang nhãn beta, và cũng là lý do
[báo lỗi một nghĩa sai](#sửa-một-từ) là đóng góp có giá trị nhất lúc này.

## Kiến trúc 2 giai đoạn

```
Stage 1 — SKELETON     deterministic, miễn phí, chạy lại thoải mái
  headword + từ loại + phiên âm + toàn bộ biến thể;  senses_vi rỗng
  → build được ngay, test tra cứu trên máy thật từ tuần 1
  → đo coverage và dự toán chi phí LLM trước khi tiêu tiền

Stage 2 — NGHĨA        tốn tiền, incremental, có cache
  khớp nguồn Việt sẵn có → LLM dịch phần còn thiếu
  chỉ xử lý entry có senses_vi rỗng → resume được
```

Tách như vậy vì phần đắt (nghĩa) và phần rẻ (danh mục từ + biến thể) có nhịp làm việc
hoàn toàn khác nhau. Stage 1 chạy lại trong vài phút; Stage 2 không bao giờ dịch lại thứ
đã dịch.

## Tự build từ mã nguồn

Cần [uv](https://docs.astral.sh/uv/).

Dữ liệu đã nằm sẵn trong repo (`dict-en-vi/data/entries/`, 93 shard JSONL), nên build
không cần tải corpus gốc:

```bash
uv sync                    # cài dependency
make validate              # kiểm dữ liệu khớp schema
make test                  # bộ test biến thể — phải pass 100%
make build                 # build StarDict + Kobo + nguồn MOBI vào build/
make stats                 # báo cáo coverage
```

> **`make stage1` không nằm trong trình tự trên, và đừng chạy nó nếu chỉ muốn build.**
> Stage 1 dựng lại kho entry từ WordNet rồi ghi đè cả `data/entries/` — cả 155.139
> nghĩa tiếng Việt trong bản làm việc của bạn sẽ mất, và bạn build ra một bản skeleton.
> Nó chỉ dành cho người đang sửa chính pipeline Stage 1; xem
> [CONTRIBUTING.md](CONTRIBUTING.md#mức-3--sửa-pipeline).

`make build` luôn tạo được StarDict (thuần Python, không cần công cụ ngoài). MOBI cần
kindlegen trong Kindle Previewer 3; Kobo cần `dictgen` (tự tải về). Thiếu công cụ nào thì
build vẫn chạy, ghi rõ thiếu gì và để lại phần nguồn đã sinh — xem
[docs/build-toolchain.md](docs/build-toolchain.md).

## Cấu trúc

```
core/                    ⭐ dùng chung cho mọi cặp ngôn ngữ
  schema.py              Entry + validate
  store.py               kho JSONL chia shard (không dùng database)
  render.py              renderer HTML + CSS an toàn cho e-ink
  builders/              mobi.py · kobo.py · stardict.py · dictzip.py
  attribution.py         ghi nguồn nhúng vào chính từ điển + ATTRIBUTION.txt
  llm/                   provider + prompt cho Stage 2
  tools/entry.py         CLI đọc/sửa đúng 1 entry
dict-en-vi/              Phase A
  LICENSE-DATA           giấy phép + nghĩa vụ ghi nguồn của dữ liệu
  data/source/           script tải nguồn (dữ liệu tải về không vào git)
  data/entries/          JSONL — đây mới là thứ ta phát hành
  data/overrides/        sửa tay, ghi đè lên dữ liệu sinh tự động
  pipeline/              s1_lemmas · s1_ipa · s1_inflect · s1_build_skeleton · s2_*
  tests/                 bộ test biến thể
qa/                      report_stats.py · make_sample.py · make_test_epub.py
```

## Sửa một từ

```bash
uv run python -m core.tools.entry get en:run:v --dir dict-en-vi/data/entries
uv run python -m core.tools.entry set en:run:v --sense "chạy" --sense "vận hành"
```

Lệnh `set` ghi vào `data/overrides/corrections.jsonl`, nên chạy lại pipeline không làm mất
sửa đổi. Gửi PR — CI validate rồi merge, release tự build.

Thấy một từ tra không ra hay một nghĩa sai? Mở
[issue](https://github.com/thichhoc-org/thichhoc-dict/issues/new/choose) — mỗi báo cáo thành
một dòng override trong bản phát hành kế tiếp. Báo lỗi không cần cài gì cả.

Quy trình đầy đủ — gồm luật về nguồn dữ liệu, cách chạy pipeline và các cổng CI:
[CONTRIBUTING.md](CONTRIBUTING.md).

## Câu hỏi thường gặp

### Từ điển này có tra được từ đã chia thì như `stopped`, `ran`, `geese` không?

Có — đây chính là lý do dự án tồn tại. Kho dữ liệu có 285.412 dạng tra được, và bộ test
biến thể phải pass 100% mới được phát hành. Bản MOBI dùng markup `idx:iform`, cơ chế duy
nhất khiến Kindle tự quy `stopped` về `stop` mà người đọc không phải sửa tay.

### Cài lên Kindle có cần jailbreak không?

Không. Từ điển sideload chép thẳng vào `documents/dictionaries/` qua cáp USB, firmware gốc
nhận bình thường và không dính giới hạn số thiết bị như từ điển mua trên Kindle Store.

### Có dùng offline được không?

Được. Toàn bộ từ điển nằm trong tệp trên máy đọc sách, tra không gọi mạng.

### Từ điển này khác gì các bản Anh–Việt đang lưu hành trên forum?

Ba điểm: license sạch 100% (không gộp dữ liệu thương mại), pipeline công khai (ai cũng sửa
và build lại được), và xử lý biến thể từ triệt để. Ngoài ra bản phát hành nằm ở GitHub
Releases nên không có chuyện link chết.

### Nghĩa tiếng Việt do người dịch hay máy dịch?

Máy — cụ thể là LLM, chạy theo tầng tần suất từ từ hay gặp nhất trở xuống, và hiện đã phủ
100% mục từ. Chưa mục nào qua review của người, nên bản phát hành mang nhãn beta. Từ hay
gặp được dịch trước nên cũng là phần được nhiều mắt người đọc soi nhất khi dùng thật; thấy
nghĩa nào sai thì [mở issue](https://github.com/thichhoc-org/thichhoc-dict/issues/new/choose),
mỗi báo cáo thành một dòng override trong bản kế tiếp.

### Dùng cho mục đích thương mại được không?

Mã nguồn theo MIT nên thoải mái. Dữ liệu theo CC BY-SA 4.0: dùng được, kể cả thương mại,
nhưng phải ghi nguồn và giữ nguyên giấy phép share-alike cho bản phái sinh.

### Bao giờ có từ điển Trung–Việt?

Sau khi Anh–Việt ra bản 1.0. Toàn bộ `core/` dùng chung nên phần lớn công sức còn lại nằm
ở dữ liệu.

## Dùng lại từ điển trong phần mềm của bạn

Được, kể cả sản phẩm thương mại. Dữ liệu theo **CC BY-SA 4.0**, nên bạn cần đặt khối ghi
nguồn này ở nơi **người dùng cuối đọc được** — màn hình Giới thiệu/Credits, hoặc trang
thông tin của từ điển:

```
Dữ liệu từ điển: Từ điển Anh–Việt thichhoc.com (thichhoc-dict),
giấy phép CC BY-SA 4.0.
https://github.com/thichhoc-org/thichhoc-dict
Nguồn gốc: WordNet 3.1 (Princeton), CMUdict (CMU), Wiktionary.
[Đã chỉnh sửa dữ liệu. / Giữ nguyên, không chỉnh sửa.]
```

Kèm theo: nêu rõ nếu đã sửa dữ liệu, phát hành bản phái sinh theo chính CC BY-SA 4.0, và
giữ nguyên ghi nguồn của các nguồn gốc. Share-alike áp lên **dữ liệu**, không lan sang mã
nguồn phần mềm chỉ đọc/đóng gói dữ liệu — app của bạn giữ giấy phép riêng.

Ghi nguồn đi theo sản phẩm ở ba chỗ nên bạn không phải tự dựng lại: `ATTRIBUTION.txt`
trong bản phát hành, metadata của chính file từ điển (`.ifo`, OPF), và **một mục từ ghi
nguồn nằm trong chính từ điển — tra `thichhoc` là ra**. Chi tiết đầy đủ:
[dict-en-vi/LICENSE-DATA](dict-en-vi/LICENSE-DATA).

## License

Code: [MIT](LICENSE). Dữ liệu: [CC BY-SA 4.0](dict-en-vi/LICENSE-DATA) — bắt buộc do kế
thừa từ nguồn share-alike (Wiktionary), không phải một lựa chọn tự do. Ghi nguồn đầy đủ
kèm trong mỗi bản phát hành (`ATTRIBUTION.txt`).

---

## English summary

**thichhoc-dict** builds open-source **English–Vietnamese dictionaries for e-readers** —
Kindle (MOBI), Kobo (dicthtml) and StarDict for KOReader, Boox and GoldenDict. 155,139
entries and 285,412 lookup forms, so inflected words (`stopped`, `ran`, `geese`,
`criteria`) resolve to their headword while you read. Every entry carries a Vietnamese
sense; none has been human-reviewed yet, which is what the beta label is for. Every source is openly licensed and
the entire pipeline is public: fix a sense in one JSONL line and send a pull request.
Code is MIT; dictionary data is CC BY-SA 4.0.
