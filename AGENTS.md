# AGENTS.md

## Đây là repo gì

**amp-room-setup** (git repo lồng, `origin` `ss-kuroz/codex-room-setup`,
branch `main` — commit bên trong nó, không bao giờ từ root Kuro.agentic):
cấu hình tái lập cho phòng 3 vai trò SLP (Supervisor / Lead / Peer) chạy bằng
**Amp** qua **Paseo đã cài sẵn trên máy**. Không còn mảng Codex runtime hay
build Paseo từ source — tất cả đã bị xóa trong refactor Oct 2026.

## Kiến trúc trong 1 câu

`scripts/room.py sync` render provider `amp-acp` + 3 `daemon.agentProfiles`
("SLP - Supervisor" medium / "SLP - Lead" high / "SLP - Peer" low, mode
`local`, `auto_accept`) từ `config/room.json` + `roles/*.md`, upsert theo tên
vào `~/.paseo/config.json` (giữ nguyên id và mọi thứ khác), cài
`workflow/WORKSPACE_PROTOCOL.md` tới
`~/.config/amp-room/workflow/WORKSPACE_PROTOCOL.md`, rồi gọi
`paseo daemon reload` (không bao giờ restart daemon).

## Nguồn sự thật

- Prompt 3 role: `roles/<role>.md` (được nhúng vào field `notes` của profile).
- Model/mode/auto-accept/tên profile: `config/room.json`.
- Hợp đồng phối hợp chung: `workflow/WORKSPACE_PROTOCOL.md`.
- Logic merge: `scripts/room.py` (stdlib Python, fail loud, exit != 0 khi lỗi).

## Lệnh

```powershell
# Test dùng venv root workspace cũng được (chỉ ghi vào repo/temp):
& d:\_Working\Kuro.agentic\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Sync/verify TRÊN MÁY NÀY phải dùng `py` (Python 3.14 Win32) — xem gotcha dưới:
py scripts\room.py sync
py scripts\room.py verify --source
```

Trên máy này (Windows): Paseo daemon desktop-managed port 6767, `paseo.cmd`
ở `~/.local/bin`, `amp-acp` cài global qua npm, `amp.exe` ở `~/.amp/bin`.
Provider entry đã tồn tại (có `AMP_CLI_PATH` riêng của máy) — sync không ghi
đè nó.

## Gotchas

- **Paseo Desktop UI có thể xóa/sửa agent profile** (đã xảy ra: cả 3 profile
  SLP bị xóa lúc 2026-10-14 22:57 ngay sau khi archive workspace). Đó không
  phải bug của sync — chạy lại `sync` để khôi phục; `verify` chỉ ra drift.
- Session đang chạy không nhận prompt mới; profile chỉ có hiệu lực khi tạo
  agent mới.
- Không sửa tay các mục room trong `~/.paseo/config.json` — regenerated.
- Backup mọi lần sync nằm ở `~/.amp-room-backups/`.
- File tiếng Việt/markdown phải UTF-8 không BOM, line ending LF.
- **VenV ở root workspace là shim của Windows Store Python — bị Windows chặn
  ghi vào mọi path trong `%USERPROFILE%` (PermissionError cả ở `~/.paseo`).
  `room.py sync` ghi vào `~/.paseo/config.json` và `~/.config/`, nên trên máy
  này phải chạy bằng `py` (Python 3.14 Win32 thật ở
  `AppData\Local\Programs\Python\Python314`).**