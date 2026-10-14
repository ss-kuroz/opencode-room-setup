# Hướng dẫn opencode-room-setup

Tài liệu này giải thích cách bộ setup tạo một phòng OpenCode gồm ba vai trò
(SLP: Supervisor, Lead, Peer) trên máy đã cài Paseo, và cách các vai trò phối
hợp để hoàn thành một outcome kỹ thuật.

## Bức tranh tổng thể

```text
Paseo daemon (đã cài trên máy, ~/.paseo/config.json)
    -> agents.providers "opencode-supervisor | opencode-lead | opencode-peer"
         mỗi vai trò là một provider dẫn xuất ("extends": "opencode", label riêng),
         catalog model của nó chỉ gồm model của vai trò đó, và thinking effort của
         vai trò được đánh dấu là default ở cấp provider
    -> daemon.agentProfiles "opencode-supervisor | opencode-lead | opencode-peer"
         mỗi vai trò một profile, trỏ vào provider dẫn xuất tương ứng: mode build,
         auto_accept, và prompt vai trò lấy từ roles/<role>.md
    -> opencode (ACP server có sẵn trong OpenCode CLI, không cần adapter)
    -> model Ollama Cloud resolve qua OpenCode: deepseek-v4.1-flash / glm-5.3 /
       deepseek-v4.1-flash, kèm thinking effort low / high / low
    -> hợp đồng chung: ~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md
```

Repo không cài Paseo, OpenCode, hay Ollama. Nó chỉ sở hữu ba thứ: các mục
provider trong `~/.paseo/config.json` (provider gốc `opencode` mà sync ghim
`enabled: true` và `command` override trỏ vào exe thật, cộng ba provider dẫn
xuất cho ba vai trò) và ba agent profile, file hợp đồng chung ở
`~/.config/opencode-room/workflow/`, và backup config ở
`~/.opencode-room-backups/`. Toàn bộ phần còn lại của `~/.paseo/config.json`
(listen, plugins, provider khác, profile khác) được giữ nguyên, không đụng tới.

Phòng được công bố thành hai tầng vì Paseo tách hai việc: **provider** giữ thứ
người vận hành chọn trước khi đặt tên cho agent (model, và thinking effort của
model đó), còn **agent profile** là tầng duy nhất có `notes` — nơi chứa prompt
vai trò — cùng `modeId` và `auto_accept`. Provider không mang được prompt hay
auto-accept, nên ba provider dẫn xuất không thay thế profile; cả hai tầng mới là
phòng. Nhờ tầng provider, danh sách provider của Paseo có `OpenCode - Supervisor
/ Lead / Peer`, mỗi mục đã mặc định sẵn model và thinking effort của vai trò.

## Ranh giới trách nhiệm

- Human giữ mục tiêu sản phẩm, ưu tiên, chi phí vật chất, tác động bên ngoài,
  và quyết định rủi ro không thể đảo ngược.
- Supervisor quan sát workspace, chuyển nguyên vẹn chỉ thị của Human, và thực
  hiện phục hồi vận hành có giới hạn. Supervisor không trở thành Lead thứ hai.
- Lead giữ quyết định kỹ thuật của một dự án, dependency order, tích hợp,
  kiểm chứng, và quyết định chấp nhận candidate.
- Peer nhận đúng một outcome có giới hạn. Peer có thể triển khai, điều tra,
  đưa ra ý kiến kiến trúc, hoặc kiểm tra candidate trong phạm vi được giao.

Peer có thể gửi `REOPEN_REQUEST` khi tiền đề kỹ thuật thất bại,
`DEPENDENCY_REQUEST` khi thiếu prerequisite chưa có owner, hoặc `BLOCKED` khi
không còn bước an toàn trong phạm vi. Mỗi tín hiệu cần nêu bằng chứng, hệ quả,
và quyết định cần có.

Khi một quyết định kiến trúc hoặc candidate có rủi ro đủ lớn, Lead có thể gọi
một Peer mới ở chế độ chỉ đọc để xem đúng candidate hoặc snapshot đã cố định.
Đây vẫn là Peer theo nhiệm vụ, không tạo thêm provider hay cấp bậc mới.

## Cài đặt và sync

Điều kiện trước: Paseo đã cài và đang chạy (`paseo daemon status`), OpenCode
CLI v2.0.29+ nằm trên PATH (`opencode --version`) và đã đăng nhập Ollama Cloud
(`paseo provider diagnostic opencode` thấy API key), Python 3.11+.

```bash
python scripts/room.py sync        # publish provider + profiles + protocol, reload daemon
python scripts/room.py verify      # kiểm tra source lẫn installed (read-only)
python scripts/room.py verify --source   # chỉ kiểm tra source, không đụng HOME
python scripts/room.py uninstall   # gỡ đúng những gì sync quản lý
make test                          # unit test cho logic merge/render
```

`sync` là idempotent và cũng là đường sửa chữa: nếu Paseo Desktop UI xóa hoặc
sửa một profile của room, chạy lại `sync` để khôi phục. `id` của profile cùng
tên được giữ nguyên nên agent và schedule đang tham chiếu không bị đứt gãy.
`sync` không bao giờ restart daemon; nó chỉ gọi `paseo daemon reload` khi
daemon đang chạy.

Đổi model hoặc thinking effort: sửa `config/room.json` (cả mục `providers` của
vai trò và `model`/`thinkingOptionId` của profile). Thinking là per-model — kiểm
tra option hợp lệ bằng `paseo provider models opencode` (ví dụ
`deepseek-v4.1-flash` chỉ có low/high/max, còn `glm-5.3` cũng chỉ có
low/high/max). Model không có thinking option thì bỏ trường `thinkingOptionId`;
sync sẽ xóa nó khỏi profile đã cài.

## Luồng một candidate

Lead gửi cho Peer outcome quan sát được, dependency, write scope, invariant,
bằng chứng nghiệm thu, và điều kiện cần mở lại quyết định. Peer tự điều tra
trong phạm vi đó, chạy proof phù hợp, rồi trả immutable candidate (commit hoặc
snapshot), base ban đầu, danh sách path, lệnh đã chạy, và rủi ro còn lại.

Lead đọc artifact chính xác và đưa ra quyết định kỹ thuật rõ ràng: chấp nhận
hoặc từ chối, kèm lý do. Test pass, thông báo hoàn thành, và trạng thái
workspace là bằng chứng hỗ trợ; chúng không tự tạo thành acceptance.

Sau khi dispatch, các role chờ event finish, error, attention, hoặc decision.
Không lặp lại truy vấn khi state chưa đổi.

## Sửa ở đâu?

- Đổi prompt hoặc authority của role: sửa `roles/<role>.md`.
- Đổi model, thinking effort, mode, auto-accept, tên profile, và provider dẫn
  xuất của vai trò (id, label, catalog model): sửa `config/room.json`. Mảng
  `models` của provider dẫn xuất **thay thế** catalog mà Paseo dò được từ
  OpenCode, nên phải liệt kê đủ mọi model và thinking option mà ghế đó được
  phép dùng; model và `providerId` của profile phải khớp với nhau.
- Đổi provider gốc: sửa `config/room.json` (mục `provider`). Với provider
  built-in `opencode`, sync quản lý 2 key trong entry — `enabled` và
  `command` override trỏ vào exe thật (xem gotcha về npm shim trong
  AGENTS.md); các key khác trong entry được giữ nguyên. Ba provider dẫn xuất
  kế thừa launch này nên đường dẫn exe chỉ được ghi ở một chỗ.
- Đổi nguyên tắc phối hợp chung: sửa `workflow/WORKSPACE_PROTOCOL.md`.
- Đổi logic merge/render: sửa `scripts/room.py` và test boundary tương ứng
  trong `tests/test_room.py`.

Không sửa trực tiếp các mục room trong `~/.paseo/config.json`; đó là output
được sinh lại từ `sync`. Không đưa auth, session, log, database, keypair,
token, hay private workspace state vào Git.