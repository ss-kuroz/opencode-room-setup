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
trỏ vào provider dẫn xuất tương ứng, model Ollama Cloud `deepseek-v4.1-flash:1017` /
`deepseek-v4-pro` / `deepseek-v4.1-flash:1017` kèm thinking `low` / `max` / `low`, mode
`build`, `auto_accept`, prompt từ `roles/*.md` đặt ở `notes`), cộng mục provider gốc
`opencode` (ghim `command` dạng argv array vào exe thật và gỡ `enabled: false`
nếu có, mà ba provider dẫn xuất kế thừa. Mỗi provider dẫn xuất mang overlay `env` làm hai việc:
`OPENCODE_CONFIG_DIR` trỏ vào thư mục config của ghế — nơi sync đặt
`agents/build.md` mang **prompt thật** của ghế (role prompt + hợp đồng chung), vì
OpenCode lấy agent definition trong thư mục đó làm prompt (đây là **cách duy nhất**
ghế nhận được vai: `notes` chỉ là metadata cho người chọn profile) — và
`OPENCODE_CONFIG_CONTENT` mang policy tắt multi-agent của OpenCode cho ghế (mục
`nativeAgents: false` trong spec sinh ra nó; provider gốc không bị đụng).
Upsert theo tên/id và giữ nguyên id cùng mọi thứ
khác, cài `workflow/WORKSPACE_PROTOCOL.md` tới
`~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md` cùng
`seats/<provider>/agents/build.md` tới `~/.config/opencode-room/seats/`, rồi gọi
`paseo daemon reload` (không bao giờ restart daemon).

Vì sao phải hai tầng: provider không mang được `auto_accept` hay `modeId`, còn
profile thì không xuất hiện trong danh sách provider của Paseo. Provider cho "ghế"
hiện ra kèm default model/thinking; profile giữ mode/auto-accept và giữ prompt vai
trò để người vận hành đọc — còn prompt thật tới ghế qua `OPENCODE_CONFIG_DIR` +
`agents/build.md` của chính ghế đó.

## Nguồn sự thật

- Prompt 3 role: `roles/<role>.md` (nhúng vào `notes` của profile, và được render
  vào `~/.config/opencode-room/seats/<provider>/agents/build.md` — prompt mà server
  OpenCode của ghế nạp, kèm `workflow/WORKSPACE_PROTOCOL.md`).
- Model/thinking/mode/auto-accept/tên profile: `config/room.json`.
- Provider dẫn xuất cho từng vai trò (id, label, catalog model, `paseoTools`):
  mục `providers` trong `config/room.json`. `models` **thay thế** catalog Paseo dò
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
Provider `opencode` là built-in của Paseo — sync quản lý `command` (argv array trỏ
vào exe thật, xem gotcha về npm shim bên dưới) và bảo đảm provider không bị tắt
(`enabled: false` bị gỡ; `enabled: true` là default của Paseo nên không ghi); các
key khác trong entry được giữ nguyên.

## Gotchas

- Model của room chạy qua **Ollama Cloud trong OpenCode** (không qua Amp):
  mất auth thì agent start lỗi — kiểm tra bằng
  `paseo provider diagnostic opencode`, đăng nhập lại bằng
  `opencode auth login`.
- Thinking effort là per-model: `deepseek-v4.1-flash:1017` có low/high/max, còn
  `deepseek-v4-pro` chỉ có high/max — đổi model trong `config/room.json` thì
  kiểm tra lại thinking hợp lệ bằng `paseo provider models opencode`.
- **Ghế nhận vai qua `OPENCODE_CONFIG_DIR` + `agents/build.md`, KHÔNG phải `notes` của profile.**
  Paseo định nghĩa `notes` là free text "surfaced to orchestrating agents by the
  `list_profiles` MCP tool": nó hiện trong danh sách profile và trong output của
  tool đó cho người/agent chọn profile; profile cố ý không mang system prompt vì
  `systemPrompt` của Paseo chỉ áp lúc tạo session. Override của provider cũng
  không có field prompt nào (`extends`, `label`, `description`, `command`, `env`,
  `options`, `params`, `models`, `additionalModels`, `disallowedTools`,
  `paseoTools`, `enabled`, `order`). Nên sync dựng prompt thật của ghế tại
  `~/.config/opencode-room/seats/<provider>/agents/build.md` (role prompt + hợp đồng
  chung) rồi trỏ `OPENCODE_CONFIG_DIR` của provider vào thư mục đó — OpenCode lấy
  agent definition trong thư mục ấy làm prompt của ghế. Hai cách lân cận **không**
  chạy trên OpenCode 2.0.29 nên đừng dùng: list `instructions` trong config (inline
  hay file `OPENCODE_CONFIG`) bị bỏ qua ở tầng model, và `agents.build.prompt` trong
  config document cũng không có tác dụng. Sai/thiếu `OPENCODE_CONFIG_DIR` (hoặc mất
  file) thì ghế chạy như agent OpenCode thường: **Supervisor sẽ tự làm việc của
  project thay vì giao Lead**, Lead sẽ tự sửa file thay vì dispatch Peer. Kiểm tra:
  `py scripts\room.py verify` (báo cả `env` lẫn file prompt), và trong session thì
  hỏi ghế xem nó là vai nào — quên điều này thì phải gửi thẳng vai cho session đó
  hoặc tạo agent mới. Đây cũng là lý do một ghế "biết vai" nhờ tự gọi `list_profiles`
  chỉ là may mắn, không phải cơ chế.
- **Multi-agent của OpenCode bị tắt riêng cho ba ghế room.** Mỗi provider dẫn
  xuất (`opencode-supervisor` / `-lead` / `-peer`) mang
  `env.OPENCODE_CONFIG_CONTENT` do mục `nativeAgents: false` trong
  `config/room.json` sinh ra: deny quyền `subagent` và disable hai agent con
  built-in `general` / `explore`, nên ghế không còn tool `subagent` của OpenCode.
  Cầu Paseo (`create_agent`, `send_agent_prompt`, reads) vẫn hiện cho ghế vì Lead
  phải dispatch Peer qua đó; riêng Peer mang `paseoTools.disabledTools` chặn
  `create_agent`/`kill_agent`/`create_workspace`/schedule/... nên chỉ còn đọc và
  báo cáo. Đây là
  invariant kế thừa từ codex room (native agents disabled trong từng runtime) —
  Paseo sở hữu topology, agent con tự sinh sẽ nằm ngoài hợp đồng báo cáo. Provider
  gốc `opencode` **không** mang overlay, nên việc OpenCode riêng của bạn vẫn còn
  multi-agent. Kiểm tra: `py scripts\room.py verify` (xem `env` như managed key)
  và `paseo daemon config get agents.providers --json` (đường dẫn config có key
  động không đọc được, phải đọc cả object); đừng xóa tay
  key này — chạy lại `sync` là khôi phục. Overlay là env của process, nên phải
  tạo agent mới sau khi sync mới thấy hiệu lực. Nửa `OPENCODE_CONFIG_DIR` của overlay
  không tắt theo `nativeAgents` — nó là đường ghế nhận vai.
- **Paseo Desktop UI có thể xóa/sửa agent profile** (đã từng xảy ra với room
  Amp lúc 2026-10-14). Đó không phải bug của sync — chạy lại `sync` để khôi
  phục; `verify` chỉ ra drift.
- **npm install tạo shim `opencode.CMD` — Node không spawn được `.cmd` không
  shell (spawn EINVAL). Không có command override thì Paseo fallback âm thầm
  sang integration OpenCode v1 legacy (root paths) và agent fail với lỗi
  "Request is not supported by this version of OpenCode Server". Sync tự pin
  `command: ["<opencode.exe thật>"]` trong entry provider `opencode` (argv array
  là dạng Paseo ghi và ưu tiên; dạng cũ `{mode: "replace", argv: [...]}` vẫn được
  `verify` chấp nhận vì Paseo normalize cả hai). Đừng xóa key này bằng tay —
  chạy lại `sync` là khôi phục.**
- Session đang chạy không nhận prompt mới; profile chỉ có hiệu lực khi tạo
  agent mới.
- **Tạo agent từ trong agent phải theo 2 luật của cầu Paseo** (đã dính thật,
  2026-10-15): `provider` phải ở dạng `provider/model` — ví dụ
  `opencode-peer/ollama-cloud/deepseek-v4.1-flash:1017`, truyền `opencode-peer` trần
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