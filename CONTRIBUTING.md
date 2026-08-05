# Góp sức vào thichhoc-dict

Cảm ơn bạn. Dự án này sống được là nhờ người dùng máy đọc sách báo lại những từ tra không
ra và những nghĩa dịch sai — đó là loại lỗi không có cách nào tự phát hiện bằng script.

Có ba mức đóng góp, xếp theo công sức. **Mức 1 không cần cài gì cả.**

---

## Trước hết: một luật không thoả hiệp

**Không đưa dữ liệu từ điển thương mại vào dự án, dưới bất kỳ hình thức nào.**

Áp dụng cho mọi từ điển thương mại, và cả các bản Anh–Việt trôi nổi trên forum có nguồn
gốc từ đó. Điều này bao gồm cả:

- chép nguyên nghĩa,
- diễn đạt lại nghĩa của họ bằng câu chữ khác,
- dán nghĩa của họ vào prompt cho LLM rồi lấy kết quả.

Cả ba đều tạo ra tác phẩm phái sinh và làm hỏng chuỗi license sạch của dự án — thứ khiến
`thichhoc-dict` đứng tên công khai được và bạn fork rồi phát hành lại được. Một PR dính
vào đây sẽ bị đóng, kể cả khi nghĩa dịch chính xác hơn bản hiện có.

Nguồn được phép nằm trong [dict-en-vi/LICENSE-DATA](dict-en-vi/LICENSE-DATA): WordNet 3.1,
CMUdict, Wiktionary, cùng vốn tiếng Việt của chính bạn. Nếu không chắc một nguồn có dùng
được không, mở issue hỏi trước khi làm.

---

## Mức 1 — Báo lỗi (không cần cài gì)

Mở [issue](https://github.com/thichhoc-org/thichhoc-dict/issues/new/choose). Hai loại
báo cáo hữu ích nhất:

**Từ tra không ra.** Ghi rõ từ bạn chạm vào *trên máy*, không phải dạng nguyên thể. Ví dụ
hữu ích: "chạm `outdid` trên Kindle Paperwhite → không hiện gì". Ví dụ ít hữu ích hơn:
"từ `outdo` bị thiếu" — vì `outdo` có thể có sẵn mà chỉ riêng biến thể `outdid` là thiếu,
và đó là hai lỗi khác nhau ở hai chỗ khác nhau trong pipeline.

**Nghĩa sai hoặc lạc ngữ cảnh.** Ghi từ, nghĩa đang hiện, và nghĩa đúng theo bạn. Nếu câu
trong sách làm rõ được vấn đề thì chép cả câu vào — ngữ cảnh giúp phân biệt "dịch sai" với
"dịch đúng nhưng thiếu nét nghĩa này".

Mỗi báo cáo hợp lệ thành một dòng override trong bản phát hành kế tiếp.

---

## Mức 2 — Sửa một nghĩa (PR, cần `uv`)

```bash
uv sync
uv run python -m core.tools.entry find outdo --dir dict-en-vi/data/entries
uv run python -m core.tools.entry get en:run:v --dir dict-en-vi/data/entries
uv run python -m core.tools.entry set en:run:v --sense "chạy" --sense "vận hành, điều hành"
```

Lệnh `set` **không** ghi vào `data/entries/`. Nó ghi vào
[dict-en-vi/data/overrides/corrections.jsonl](dict-en-vi/data/overrides/corrections.jsonl),
được áp dụng *sau* pipeline — nên chạy lại Stage 1 không bao giờ làm mất sửa đổi của bạn.

> **Đừng sửa tay tệp trong `data/entries/`.** Đó là dữ liệu sinh tự động; lần
> `make stage1` kế tiếp sẽ ghi đè lên. Mọi phán đoán của con người sống trong `overrides/`.
> Đây là lý do duy nhất hai thư mục đó tách nhau.

Mỗi dòng override là một entry *một phần*: chỉ khoá nào có mặt mới bị thay thế, `id` là
bắt buộc. Ghi `--reviewed` khi bạn đã đối chiếu kỹ, để phân biệt với nghĩa máy sinh.

Trước khi gửi PR:

```bash
make validate    # entry store khớp schema
make test        # bộ test biến thể — phải pass 100%
```

Nhắm tới mỗi PR một chủ đề. Một PR sửa 30 nghĩa của cùng một nhóm từ thì dễ review; một PR
sửa 30 nghĩa rải rác không liên quan thì không.

---

## Mức 3 — Sửa pipeline

Bố cục thư mục và kiến trúc 2 giai đoạn nằm trong [README](README.md#kiến-trúc-2-giai-đoạn).
Vài điều không đọc code sẽ không đoán ra:

**Stage 1 ghi đè kho entry, không gộp vào.** Đây là điều quan trọng nhất trong mục này.
`make stage1` dựng lại toàn bộ từ WordNet rồi ghi đè `data/entries/` — nghĩa là cả 155.139
nghĩa tiếng Việt đang có trong repo biến mất khỏi bản làm việc của bạn, chỉ còn lại những
gì `overrides/corrections.jsonl` khôi phục được. Đừng chạy nó để "cho chắc"; chỉ chạy khi
bạn đang thật sự sửa một script Stage 1:

```bash
make download    # ~40MB vào raw/, gitignored — chỉ Stage 1 mới cần
make stage1      # ⚠ ghi đè data/entries/, mất senses_vi
make validate && make test
```

Sau đó `git checkout dict-en-vi/data/entries` để lấy lại dữ liệu thật, trừ khi thay đổi
của bạn đúng là nhằm phát hành một kho entry mới — và khi đó nó phải đi kèm một lần chạy
Stage 2 để lấp lại phần nghĩa, chứ không phải một PR làm coverage tụt về 0.

Muốn đổi chính sách headword (lọc rác, xếp tầng tần suất) mà **giữ** phần nghĩa thì dùng
`make retier` — nó tồn tại chính vì lý do này.

**Stage 2 tốn tiền.** Mọi lệnh gọi LLM mặc định là `--dry-run`; phải truyền `GO=1` mới thật
sự gửi request. Cứ để nguyên mặc định đó — chạy dry-run trước để xem dự toán chi phí.
`make stage2-match` (miễn phí, khớp nguồn Việt sẵn có) luôn chạy trước `stage2-llm`, vì mỗi
entry nó lấp được là một entry LLM không bao giờ phải nhìn tới.

**Bộ test biến thể là hợp đồng, không phải ảnh chụp.** Tệp test đã commit chính là thứ được
bảo vệ. Đừng chạy `make tests-regen` để làm test xanh trở lại — nếu một trường hợp fail thì
đó là pipeline hỏng, không phải test hỏng. `tests-regen` chỉ dùng khi bổ sung ca lỗi mới
được báo cáo.

**CI chạy đúng thứ tự này**, xem [.github/workflows/release.yml](.github/workflows/release.yml):
validate → test biến thể → báo cáo coverage → build. Schema đứng trước tiên vì một entry
sai schema sẽ thành một lần tra hỏng trên Kindle của người khác.

Lưu ý về `kindlegen`: CI không cài được (Amazon chỉ phát hành nó bên trong Kindle Previewer,
không có bộ cài headless và không có quyền phân phối lại). CI xuất phần nguồn MOBI; tệp
`.mobi` được build trên máy maintainer rồi đính vào release. Nên PR của bạn không cần có
kindlegen — StarDict build được bằng Python thuần.

---

## Quy ước

**Commit** theo [Conventional Commits](https://www.conventionalcommits.org/): `feat(data):`,
`fix(pipeline):`, `docs(readme):`. Phần mô tả viết như một câu nói ra điều gì đã thay đổi,
không phải nhãn dán — xem `git log` để bắt nhịp.

**Nhánh** đặt tên `fix/…`, `feat/…`, `docs/…`.

**Ngôn ngữ**: issue và PR viết tiếng Việt hoặc tiếng Anh đều được. Comment trong code viết
tiếng Anh, giải thích *vì sao* chứ không mô tả lại *cái gì*.

## License

Gửi PR tức là bạn đồng ý phần đóng góp được phát hành theo license của dự án: mã nguồn
[MIT](LICENSE), dữ liệu từ điển [CC BY-SA 4.0](dict-en-vi/LICENSE-DATA).
