# AGENTS.md

## Đây là repo gì

**opencode-room-setup** (git repo lồng, `origin` `ss-kuroz/opencode-room-setup`
— fork của `hoangnb24/codex-room-setup`, branch `main` — commit bên trong nó,
không bao giờ từ root Kuro.agentic): cấu hình tái lập cho phòng 3 vai trò SLP
(Supervisor / Lead / Peer) chạy bằng **OpenCode** qua **Paseo đã cài sẵn trên
máy**. Kế thừa lineage codex-room-setup → amp-room-setup qua git history; room
Amp đã về hưu — repo amp-room-setup đã xoá, room OpenCode thay thế hoàn toàn.

## Kiến trúc trong 1 câu

`scripts/room.py sync` công bố phòng thành **hai tầng** trong
`~/.paseo/config.json`: ba provider dẫn xuất `agents.providers`
("opencode-supervisor" / "opencode-lead" / "opencode-peer", mỗi cái
`extends: "opencode"` + label riêng + catalog model với model và thinking của
vai trò được đánh `isDefault`) và ba `daemon.agentProfiles` cùng tên (provider
trỏ vào provider dẫn xuất tương ứng, model Ollama Cloud `deepseek-v4.1-flash` /
`deepseek-v4-pro` / `deepseek-v4.1-flash` kèm thinking `low` / `max` / `low`, mode
`build`, `auto_accept`, prompt từ `roles/*.md`), cộng mục provider gốc
`opencode` (ghim `enabled: true` + `command` override vào exe thật, mà ba
provider dẫn xuất kế thừa; ba provider dẫn xuất còn mang overlay
`env.OPENCODE_CONFIG_CONTENT` tắt multi-agent của OpenCode cho ghế (mục
`nativeAgents: false` trong spec sinh ra nó, provider gốc không bị đụng);
upsert theo tên/id và giữ nguyên id cùng mọi thứ
khác, cài `workflow/WORKSPACE_PROTOCOL.md` tới
`~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md`, rồi gọi
`paseo daemon reload` (không bao giờ restart daemon).

Vì sao phải hai tầng: provider không mang được `notes` (prompt vai trò) hay
`auto_accept`, còn profile thì không xuất hiện trong danh sách provider của
Paseo. Provider cho "ghế" hiện ra kèm default model/thinking; profile giữ hợp
đồng vai trò.

## Nguồn sự thật

- Prompt 3 role: `roles/<role>.md` (được nhúng vào field `notes` của profile).
- Model/thinking/mode/auto-accept/tên profile: `config/room.json`.
- Provider dẫn xuất cho từng vai trò (id, label, catalog model): mục
  `providers` trong `config/room.json`. `models` **thay thế** catalog Paseo dò
  từ OpenCode, nên phải liệt kê đủ model + thinking option của ghế đó.
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
ở `~/.local/bin`, OpenCode CLI v2.0.29 cài global qua npm (exe thật ở
`AppData\Roaming\npm\node_modules\@opencode\cli\bin\opencode.exe`, shim
`opencode.CMD` ở `AppData\Roaming\npm`), Ollama Cloud đã auth trong OpenCode.
Provider `opencode` là built-in của Paseo — sync quản lý 2 key trong entry:
`enabled: true` và `command` override trỏ vào exe thật (xem gotcha về npm
shim bên dưới); các key khác trong entry được giữ nguyên.

## Gotchas

- Model của room chạy qua **Ollama Cloud trong OpenCode** (không qua Amp):
  mất auth thì agent start lỗi — kiểm tra bằng
  `paseo provider diagnostic opencode`, đăng nhập lại bằng
  `opencode auth login`.
- Thinking effort là per-model: `deepseek-v4.1-flash` có low/high/max, còn
  `deepseek-v4-pro` chỉ có high/max — đổi model trong `config/room.json` thì
  kiểm tra lại thinking hợp lệ bằng `paseo provider models opencode`.
- **Multi-agent của OpenCode bị tắt riêng cho ba ghế room.** Mỗi provider dẫn
  xuất (`opencode-supervisor` / `-lead` / `-peer`) mang
  `env.OPENCODE_CONFIG_CONTENT` do mục `nativeAgents: false` trong
  `config/room.json` sinh ra: deny quyền `subagent` và disable hai agent con
  built-in `general` / `explore`, nên ghế không còn tool agent con nào. Đây là
  invariant kế thừa từ codex room (native agents disabled trong từng runtime) —
  Paseo sở hữu topology, agent con tự sinh sẽ nằm ngoài hợp đồng báo cáo. Provider
  gốc `opencode` **không** mang overlay, nên việc OpenCode riêng của bạn vẫn còn
  multi-agent. Kiểm tra: `py scripts\room.py verify` (xem `env` như managed key)
  và `paseo daemon config get agents.providers --json` (đường dẫn config có key
  động không đọc được, phải đọc cả object); đừng xóa tay
  key này — chạy lại `sync` là khôi phục. Overlay là env của process, nên phải
  tạo agent mới sau khi sync mới thấy hiệu lực.
- **Paseo Desktop UI có thể xóa/sửa agent profile** (đã từng xảy ra với room
  Amp lúc 2026-10-14). Đó không phải bug của sync — chạy lại `sync` để khôi
  phục; `verify` chỉ ra drift.
- **npm install tạo shim `opencode.CMD` — Node không spawn được `.cmd` không
  shell (spawn EINVAL). Không có command override thì Paseo fallback âm thầm
  sang integration OpenCode v1 legacy (root paths) và agent fail với lỗi
  "Request is not supported by this version of OpenCode Server". Sync tự pin
  `command: {mode: "replace", argv: [<opencode.exe thật>]}` trong entry
  provider `opencode` (resolve từ shim lúc sync). Đừng xóa key này bằng tay —
  chạy lại `sync` là khôi phục.**
- Session đang chạy không nhận prompt mới; profile chỉ có hiệu lực khi tạo
  agent mới.
- **Tạo agent từ trong agent phải theo 2 luật của cầu Paseo** (đã dính thật,
  2026-10-15): `provider` phải ở dạng `provider/model` — ví dụ
  `opencode-peer/ollama-cloud/deepseek-v4.1-flash`, truyền `opencode-peer` trần
  là HTTP 500; và `create_agent` **không** nhận key `background`. Cách đúng: tạo
  session với `initialPrompt` một dòng, rồi gửi brief thật bằng
  `send_agent_prompt` kèm `background: true` + `notifyOnFinish: true`. Truyền
  `workspaceId` của project, đừng để top-level create mở workspace mới. Chi
  tiết ở `docs/troubleshooting.md`, cách giao việc ở `docs/operations.md`.
- Vòng báo cáo Sup ↔ Lead dựa trên hai thứ, không phải thiện chí: (1) phong bì
  dispatch ghi **địa chỉ báo cáo** — agent id của session giao việc, đọc từ env
  `PASEO_AGENT_ID` mà Paseo inject cho mỗi session (kèm `PASEO_AGENT_CWD`); env
  này nằm trong bundle `app.asar` của Paseo, đã kiểm chứng bằng `PASEO_AGENT_ID`
  trong `resources/app.asar`; (2) Lead giữ **status surface** của project hiện
  thời. Lý do: Paseo arm finish-notification theo *từng* lần `send_agent_prompt`,
  nên Lead được đánh thức bởi notification của Peer rồi đóng việc thì Sup không
  nhận event nào. Sup mỗi lần wake phải đọc state vòng đời + activity của Lead
  và status surface trước khi kết luận "không có gì xảy ra", idle-mà-còn-task-mở
  thì hỏi đúng một lần, việc đã đóng mà chưa relay cho Human là supervision gap.
  Lead bí về scope/priority/authority/intent thì hỏi Sup **một câu hỏi bounded**
  và vẫn chạy việc lành khác; Sup trả lời từ evidence, route lên Human nếu là
  quyết định của Human, hoặc nói không có evidence — trả lời không biến Sup
  thành technical Lead. Luật đầy đủ ở mục "Reporting, status, and escalation"
  của `workflow/WORKSPACE_PROTOCOL.md`.
- Việc chân tay của một task đã được giao thuộc về **Peer**, không phải
  workload của Lead: Lead giữ framing, hợp đồng giữa các phần, integration,
  kiểm chứng và accept/reject. Luật này nằm ở `roles/lead.md` và mục
  "Ownership and dispatch" của `workflow/WORKSPACE_PROTOCOL.md` — sửa ở đó nếu
  muốn đổi, đừng nhắc lại bằng lời trong từng phiên.
- Không sửa tay các mục room trong `~/.paseo/config.json` — regenerated.
- Backup mọi lần sync nằm ở `~/.opencode-room-backups/`.
- File tiếng Việt/markdown phải UTF-8 không BOM, line ending LF.
- **VenV ở root workspace là shim của Windows Store Python — bị Windows chặn
  ghi vào mọi path trong `%USERPROFILE%` (PermissionError cả ở `~/.paseo`).
  `room.py sync` ghi vào `~/.paseo/config.json` và `~/.config/`, nên trên máy
  này phải chạy bằng `py` (Python 3.14 Win32 thật ở
  `AppData\Local\Programs\Python\Python314`).**