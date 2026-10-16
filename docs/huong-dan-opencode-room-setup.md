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
         mỗi entry còn mang `env`: `OPENCODE_CONFIG_DIR` trỏ vào thư mục config
         của ghế (nơi có prompt vai trò), cộng policy tắt agent con của OpenCode
         trong `OPENCODE_CONFIG_CONTENT`
    -> daemon.agentProfiles "opencode-supervisor | opencode-lead | opencode-peer"
         mỗi vai trò một profile, trỏ vào provider dẫn xuất tương ứng: mode build,
         auto_accept, model + thinking đã ghim, và prompt vai trò ở `notes`
         (notes là metadata để chọn profile, không phải system prompt)
    -> opencode (ACP server có sẵn trong OpenCode CLI, không cần adapter)
    -> model Ollama Cloud resolve qua OpenCode: deepseek-v4.1-flash /
       deepseek-v4-pro / deepseek-v4.1-flash, kèm thinking effort low / max / low
    -> file do sync cài, dùng để dựng prompt cho từng ghế:
         ~/.config/opencode-room/seats/<provider>/agents/build.md
         ~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md
```

Repo không cài Paseo, OpenCode, hay Ollama. Nó chỉ sở hữu ba thứ: các mục
provider trong `~/.paseo/config.json` (provider gốc `opencode` mà sync ghim
`enabled: true` và `command` override trỏ vào exe thật, cộng ba provider dẫn
xuất cho ba vai trò) và ba agent profile, các file ở `~/.config/opencode-room/`
(hợp đồng chung và prompt của từng ghế), và backup config ở
`~/.opencode-room-backups/`. Toàn bộ phần còn lại của `~/.paseo/config.json`
(listen, plugins, provider khác, profile khác) được giữ nguyên, không đụng tới.

Phòng được công bố thành hai tầng vì Paseo tách hai việc: **provider** giữ thứ
người vận hành chọn trước khi đặt tên cho agent (model, và thinking effort của
model đó), còn **agent profile** giữ `modeId`, `auto_accept`, và model + thinking
đã ghim. Provider không mang được mấy thứ đó, nên ba provider dẫn xuất không thay
thế profile; cả hai tầng mới là phòng. Nhờ tầng provider, danh sách provider của
Paseo có `OpenCode - Supervisor / Lead / Peer`, mỗi mục đã mặc định sẵn model và
thinking effort của vai trò.

Không tầng nào tự đưa prompt vào context của agent: `notes` của profile chỉ là
metadata để chọn profile (Paseo hiện nó trong danh sách profile và trả lại cho ai
gọi tool `list_profiles`), và profile cố ý không mang system prompt — system
prompt của Paseo chỉ áp lúc tạo session, nên một profile mang prompt sẽ chạy với
agent mới nhưng im lặng vô hiệu khi áp vào agent đang chạy. Vì vậy sync dựng prompt
của ghế tại `~/.config/opencode-room/seats/<provider>/agents/build.md` (prompt vai
trò + hợp đồng chung) rồi trỏ `OPENCODE_CONFIG_DIR` của provider vào thư mục đó —
OpenCode đọc agent definition trong thư mục này khi server của ghế khởi động, và
thân file markdown đó **chính là** prompt của ghế. Đây là đường duy nhất theo từng
ghế đi vào context của agent: hai cách lân cận **không** hoạt động trên OpenCode
2.0.29 (list `instructions` trong config inline hay trong file `OPENCODE_CONFIG`,
và `agents.build.prompt` trong config document) nên room không dùng. Một ghế mất
overlay (hoặc mất file prompt) là mất luôn vai: nó chạy như agent OpenCode bình
thường, không biết mình là Supervisor, Lead, hay Peer — và sẽ tự làm việc được giao
thay vì dispatch.

Ba provider dẫn xuất còn mang thêm policy **tắt multi-agent của OpenCode** trong
`OPENCODE_CONFIG_CONTENT` của cùng overlay `env`: deny quyền `subagent` và gỡ hai
agent con built-in `general` / `explore` khỏi catalog, nên ghế không còn tool gọi
agent con nào cả. Lý do: Paseo sở hữu topology Supervisor/Lead/Peer, một agent con
do ghế tự sinh sẽ nằm ngoài hợp đồng dispatch / ownership / báo cáo. Provider gốc
`opencode` **không** bị đụng tới, nên phần việc OpenCode riêng của bạn vẫn giữ
nguyên multi-agent và prompt riêng của bạn.

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
python scripts/room.py sync        # publish provider + profiles + protocol + seat prompts, reload daemon
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
`deepseek-v4.1-flash` có low/high/max, còn `deepseek-v4-pro` chỉ có
high/max). Model không có thinking option thì bỏ trường `thinkingOptionId`;
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

## Vòng báo cáo: Sup ↔ Lead ↔ Human

Một assignment đóng xong mà session đã giao việc không hề biết là lỗi vận
hành, không phải "êm". Ba thói quen giữ vòng đó kín:

- **Địa chỉ báo cáo.** Session giao việc đọc agent id của chính nó từ
  environment (`PASEO_AGENT_ID`) và ghi vào phong bì dispatch, để bên nhận biết
  gửi kết quả về đâu. Đây là metadata vận hành, không phải attribution — không
  đưa vào brief của Peer hay artifact của project.
- **Status surface.** Chủ của phần việc đang chạy giữ nguồn work-status sẵn có
  của project luôn hiện thời: assignment và owner, state (dispatched / in
  progress / awaiting <ai> / blocked / accepted), checkpoint kế tiếp, và mọi
  quyết định đang mở kèm owner. Human và Sup đọc đây thay vì ngắt việc lành.
- **Báo lên trên.** Khi outcome đóng (accept / reject / block), owner gửi report
  ngắn cho session đã giao: outcome, candidate và base, evidence, giới hạn còn
  lại, và quyết định Human phải ra. Gửi bằng background message kèm
  `notifyOnFinish` — một turn được đánh thức bởi notification của Peer không
  đảm bảo phát finish event cho requester, nên kết thúc im lặng là mất kết quả.
  Hết việc sẵn sàng trong phạm vi được giao cũng báo theo cách đó.

Khi scope, priority, authority, hay intent không giải quyết được từ instruction
và evidence hiện có, Lead gửi Sup **một câu hỏi bounded**: điểm mơ hồ, evidence,
quyết định cần có, các phương án, và việc Lead vẫn tiếp tục trong lúc chờ. Không
tự phát minh scope, không đoán intent, không im lặng chờ. Hỏi không phải điểm
dừng: việc lành không liên quan vẫn chạy tiếp, và câu trả lời là quyết định để
áp dụng, không phải một approval gate mới.

Phía Sup: mỗi lần wake (event hoặc heartbeat) phải đọc state vòng đời của Lead
đang giám sát, activity gần nhất, và status surface **trước khi** kết luận là
không có gì xảy ra. Lead idle mà còn assignment mở → hỏi Lead đúng một lần, ngắn,
xin kết quả hoặc blocker. Assignment đã đóng mà chưa ai nói với Human → đó là
supervision gap. Sup trả lời câu hỏi của Lead từ evidence hiện có, route lên
Human nếu là quyết định thuộc Human, hoặc nói thẳng là không có evidence; trả lời
không biến Sup thành technical Lead — Sup không accept candidate, không ra lệnh
cho Peer.

## Sửa ở đâu?

- Đổi prompt hoặc authority của role: sửa `roles/<role>.md`. `sync` dựng lại
  prompt của ghế tại `~/.config/opencode-room/seats/<provider>/agents/build.md`
  (đường dẫn mà `OPENCODE_CONFIG_DIR` của provider trỏ tới) và cập nhật `notes`
  trong profile — nhưng **session đang chạy giữ nguyên prompt lúc nó khởi động**,
  nên phải tạo agent mới để thấy thay đổi.
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
- Bật/tắt multi-agent của OpenCode cho ba ghế: mục `nativeAgents` trong
  `config/room.json` (`false` = tắt, giá trị đang dùng). Khi tắt, sync render
  policy deny `subagent` + disable `general`/`explore` vào
  `OPENCODE_CONFIG_CONTENT` của từng provider dẫn xuất. Nửa còn lại của overlay —
  `OPENCODE_CONFIG_DIR` trỏ vào thư mục prompt của ghế — **luôn** có, vì đó là cách
  ghế nhận vai. `verify` coi cả `env` là managed key nên báo drift nếu ghế mất
  overlay, và báo cả khi file prompt của ghế bị thiếu/sửa tay. Provider gốc không
  bao giờ nhận overlay này.
- Đổi nguyên tắc phối hợp chung: sửa `workflow/WORKSPACE_PROTOCOL.md`.
- Đổi logic merge/render: sửa `scripts/room.py` và test boundary tương ứng
  trong `tests/test_room.py`.

Không sửa trực tiếp các mục room trong `~/.paseo/config.json`; đó là output
được sinh lại từ `sync`. Không đưa auth, session, log, database, keypair,
token, hay private workspace state vào Git.