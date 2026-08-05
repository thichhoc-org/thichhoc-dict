# Công cụ build

Ba target, ba mức phụ thuộc khác nhau. Build luôn chạy được — thiếu công cụ
nào thì target đó dừng ở phần nguồn đã sinh và báo rõ thiếu gì, các target còn
lại vẫn ra sản phẩm.

| Target | Cần công cụ ngoài | Thiếu thì sao |
|---|---|---|
| **StarDict** | không | luôn build được |
| **Kobo** | `dictgen` | tự tải về `.tools/`; nếu chặn mạng thì để lại `.df` |
| **MOBI** | `kindlegen` | để lại nguồn đầy đủ trong `mobi-src/` |

## StarDict — không cần gì

Viết thẳng bằng Python: `.ifo`, `.idx`, `.dict.dz`, `.syn`. Đây là lý do target
này luôn là đường dự phòng — máy nào chạy được pipeline thì máy đó ra được từ
điển dùng ngay trên KOReader (kể cả KOReader chạy trên chính Kindle), Boox,
GoldenDict.

`.dict.dz` là gzip có thêm chỉ mục truy cập ngẫu nhiên, nên `gzip -d` giải nén
bình thường, còn máy đọc sách chỉ phải giải nén đúng một chunk 58 KB cho mỗi
lần tra thay vì cả file 56 MB.

**Cài trên máy:** chép cả 4 file vào một thư mục con trong thư mục từ điển của
phần mềm đọc (KOReader: `koreader/data/dict/thichhoc-en-vi/`).

## Kobo — dictgen

[pgaskin/dictutil](https://github.com/pgaskin/dictutil). Builder tự tải binary
đúng nền tảng về `.tools/` ở lần build đầu.

Nếu máy build không có mạng:

```bash
# tải sẵn rồi trỏ vào
export DICTGEN=/đường/dẫn/dictgen
make build
```

Kobo còn cần [redphx/kobo-tieng-viet](https://github.com/redphx/kobo-tieng-viet)
trên máy đọc thì firmware mới nhận từ điển tiếng Việt — đây là việc phía người
dùng cài đặt, không phải phía build.

## MOBI — kindlegen

Amazon đã ngừng phát hành kindlegen riêng lẻ. Nguồn hợp pháp duy nhất hiện nay
là **Kindle Previewer 3**, bên trong có sẵn kindlegen:

- macOS: `/Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen`
- Windows: `%LOCALAPPDATA%\Amazon\Kindle Previewer 3\lib\fc\bin\kindlegen.exe`

Builder tự dò các đường dẫn trên và `PATH`. Ép đường dẫn khác:

```bash
export KINDLEGEN=/đường/dẫn/kindlegen
make build
```

Không có kindlegen thì `build/en-vi/mobi-src/` vẫn có đủ nguồn (OPF + các file
HTML đã chia chunk) — chép sang máy có Kindle Previewer là build được ngay:

```bash
kindlegen build/en-vi/mobi-src/thichhoc-en-vi.opf -c1 -dont_append_source
```

### Vì sao markup MOBI quan trọng

Phần tra biến thể nằm ở đây:

```html
<idx:orth value="stop">
  <idx:infl>
    <idx:iform value="stopped"/>
    <idx:iform value="stopping"/>
    <idx:iform value="stops"/>
  </idx:infl>
</idx:orth>
```

`idx:iform` là cơ chế duy nhất khiến Kindle tra `stopped` ra `stop` mà người
đọc không phải tự cắt đuôi. Thiếu nó thì mọi thứ khác đều vô nghĩa — đây chính
là phàn nàn số 1 kéo dài cả thập kỷ (kế hoạch §3.0).

## Kiểm tra trên máy thật

Tiêu chí release bắt buộc (kế hoạch §7.5). Tra trực tiếp khi đang đọc sách,
không phải mở từ điển ra search tay:

1. Chép sản phẩm vào máy, khởi động lại phần mềm đọc
2. Mở một cuốn tiếng Anh, chạm giữ vào một từ **đã chia thì** — `stopped`,
   `ran`, `geese`, `criteria`
3. Bản skeleton phải hiện đúng mục từ gốc kèm dòng
   "— chưa có nghĩa tiếng Việt (bản skeleton) —"

Dòng đó có mặt là cố ý: nó phân biệt "tra ra từ nhưng chưa có nghĩa" với "tra
không ra", hai lỗi hoàn toàn khác nhau khi đang test.
