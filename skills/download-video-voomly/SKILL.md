---
name: download-video-voomly
description: Tải toàn bộ video từ Voomly spotlight mà người dùng sở hữu hoặc có quyền truy cập hợp lệ. Dùng khi người dùng cung cấp `spotlight_id`, URL/API `spotlights`, hoặc muốn liệt kê và tải toàn bộ lesson video trong một spotlight/course của Voomly sang file `.mp4`, ưu tiên `1080p`, có thể chạy chế độ chỉ in danh sách output trước khi tải.
---

# Download Video Voomly

Skill này dùng script tại `scripts/download_voomly.py` để:

- đọc `spotlight_id`
- lấy bearer token từ `.env`
- gọi API `https://api.voomly.com/spotlights/{spotlight_id}`
- gom toàn bộ `video.id` trong spotlight
- resolve link HLS qua `https://api.voomly.com/videos/{video_id}/voomly`
- ưu tiên `1080p`, fallback về mức cao nhất có sẵn
- tải về `.mp4`

Ngay từ lúc bắt đầu, phải copy file `scripts/download_voomly.py` ra thư mục làm việc gốc, cùng cấp với `.env.example`, để người dùng có thể chạy lệnh trực tiếp từ root.

## File Chính

- Script: `scripts/download_voomly.py`
- Token local: `.env`

## Chuẩn Bị

Copy script ra root:

```powershell
Copy-Item .\skills\download-video-voomly\scripts\download_voomly.py .\
```

Tạo hoặc kiểm tra `.env` ở thư mục làm việc:

```env
VOOMLY_TOKEN=your_bearer_token_here
```

Nếu chưa có dependency:

```powershell
python -m pip install requests imageio-ffmpeg
```

## Cách Dùng

In danh sách video trước khi tải:

```powershell
python skills/download-video-voomly/scripts/download_voomly.py <spotlight_id> --list-only
```

Tải toàn bộ video vào thư mục riêng:

```powershell
python skills/download-video-voomly/scripts/download_voomly.py <spotlight_id> --quality 1080p --output-dir spotlight_<spotlight_id>
```

Ví dụ:

```powershell
python skills/download-video-voomly/scripts/download_voomly.py 7qfgdp2pny --quality 1080p --output-dir spotlight_7qfgdp2pny
```

## Workflow Chuẩn

1. Xác định `spotlight_id` từ URL hoặc API path.
2. Copy `scripts/download_voomly.py` ra root, cùng cấp với `.env.example`.
3. Kiểm tra `.env` đã có `VOOMLY_TOKEN`.
4. Chạy `--list-only` trước nếu người dùng muốn kiểm tra số lượng video.
5. Chạy tải thật vào một thư mục output tách riêng cho spotlight đó.
6. Nếu một file đã tồn tại, script sẽ bỏ qua file đó.

## Output Mong Đợi

Mỗi video tạo ra:

- file `.mp4`
- tên file theo mẫu:

```txt
<lesson_name> [<video_id>] <quality>.mp4
```

Ví dụ:

```txt
Giới Thiệu [459745d8-3399-4b15-9b5c-49669f0c05c7] 1080p.mp4
```

## Quy Tắc Chất Lượng

- Ưu tiên `1080p` nếu API trả về `qualityOptions`.
- Nếu không có `1080p`, lấy mức cao nhất trong `qualityOptions`.
- Nếu video không có `qualityOptions`, fallback về `metadata.url` mặc định.

## Khi Nào Nên Dùng

- Người dùng muốn tải toàn bộ video của một spotlight/course Voomly.
- Người dùng đã có `spotlight_id` hoặc API response của spotlight.
- Người dùng muốn chỉ in ra danh sách video và đường dẫn output trước khi tải.

## Khi Không Nên Dùng

- Người dùng chỉ đưa một `m3u8` rời và không muốn làm việc theo spotlight.
- Người dùng không có token hoặc không có quyền hợp lệ với spotlight đó.
- Nguồn không phải Voomly spotlight API.

## Lỗi Thường Gặp

- `Missing token`
  - `.env` chưa có `VOOMLY_TOKEN` hoặc token sai.
- `401` hoặc `403`
  - token hết hạn hoặc spotlight/video không còn quyền truy cập.
- Video không có `1080p`
  - script sẽ tự fallback về chất lượng cao nhất còn khả dụng.
- Một số video đã tải từ lần trước
  - script sẽ in `Skipping existing file`.

## Kiểm Tra Nhanh

Kiểm tra syntax:

```powershell
python -m py_compile skills/download-video-voomly/scripts/download_voomly.py
```

Kiểm tra resolve danh sách:

```powershell
python skills/download-video-voomly/scripts/download_voomly.py <spotlight_id> --list-only
```
