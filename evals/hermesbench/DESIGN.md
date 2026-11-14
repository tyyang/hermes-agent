# HermesBench 設計說明

## 摘要

HermesBench v0.2 有兩個套件，合計 178 題：

- **pinchbench 套件（147 題）**
  - 收錄 PinchBench 全部題目。題目檔與資產跟上游（`pinchbench/skill` @ `819384a`）逐位元組相同。
  - 評分直接使用 PinchBench 的程式碼。
  - 分數可以直接和 OpenClaw 的 PinchBench 成績比較。
- **hermes 套件（31 題）**
  - Hermes 專屬題，考 PinchBench 沒有涵蓋的能力：
    - 內建 memory、`session_search`、skills 學習迴圈
    - `cronjob_manage`、`todo_list`、`delegate_task`、`execute_code`
    - browser、vision
    - prompt injection 等安全題

用法與檔案結構見 [README.md](README.md)。

## 怎麼執行

| 指令 | 內容 |
|---|---|
| `--suite all`（預設） | 全部 178 題 |
| `--suite pinchbench` | PinchBench 147 題 |
| `--suite pinchbench-core` | PinchBench 自己定義的 core，共 21 題 |
| `--suite hermes` / `hermes-core` | Hermes 套件全部 31 題 / core 12 題 |
| `--suite core` | 兩個套件的 core，合計 33 題 |
| `--skip-requires web,browser,vision,image_gen,fws` | 略過需要外部能力的題目。略過的題目不計分，但會列出 |

執行流程：

- **隔離環境**：每題（每次 `--runs`）都從空的 workspace 和獨立的 HERMES_HOME 開始。HERMES_HOME 只從 `~/.hermes` 複製 config.yaml、.env、auth.json。
- **執行 session**：每個 session 用 `hermes chat --query-file … --format stream-json --yolo --accept-hooks` 執行（gateway 模式的細節見下一節）。
  - 同一對話的後續 session 用 `--resume` 接續。
  - `new_session: true` 會開新對話。
- **逐字稿轉換**：stream-json 事件會轉成 PinchBench 的逐字稿格式，所以 PinchBench 的評分器不用修改就能直接用。
- **先跑 sanity**：`task_sanity` 最先執行。它得 0 分就中止整次執行，和 PinchBench 的做法一樣。

### Gateway 模式的 Hermes（v0.22 起）

新版的 `hermes chat` 不再在自己的程序裡跑 agent，而是交給該 HERMES_HOME 專屬的 gateway 執行。runner 為此做了下面這些調整：

- **時間預算**：gateway chat 不接受 `--run-budget`，所以每題的時間預算改寫到 config 的 `agent.run_budget_seconds`。
- **啟動時間不計入**：計時開始前先執行 `hermes gateway ensure`，因此依賴安裝和暖機的 20–40 秒不會算進 agent 的時間。
- **結束時清理**：每題結束後執行 `hermes gateway stop`。
- **避免衝突**：複製 `.env` 時去掉 `TELEGRAM_`、`API_SERVER_`、`SLACK_`、`DISCORD_` 開頭的設定，避免和使用者自己的 gateway 搶用 bot token 或 port 8642。

- **結果不留機密**：每題結束後（包括 timeout 或錯誤），runner 會刪除該題 HERMES_HOME 裡的 `.env` 和 `auth.json`，並把 `config.yaml` 中的 api_key、token、secret 值改成 `REDACTED`。grader 本來就不讀這些檔案，所以仍可重新評分。需要保留來除錯時，可設定 `HB_KEEP_SECRETS=1`。
- **評分前移除依賴環境**：每題結束時（包括 timeout 或錯誤），在評分之前，runner 會刪除該題 HERMES_HOME 裡的 `installs/`、`cache/uv` 和 `cache/pnpm`（每題約 1.2 GB）。`cache/` 其餘內容（terminal 輸出、scratch、圖片）會保留供檢視；掃描整個 home 的 grader 因此只會看到任務狀態，不會被 site-packages 佔滿掃描額度。要全部保留時，可加 `--keep-runtime`。

自訂 OpenAI-compatible 端點的用法：

1. **另建 template home**：準備一個 benchmark 專用的 template home（`--hermes-home-template`，不要放進 git），在它的 config 中設定：
   - `model.provider: custom`、`base_url`、`api_key`
   - `auxiliary.*` 改成 `main`
2. **模型名稱**：用 `-m custom:<model>` 指定。
3. **reasoning_effort**：端點有限制時（例如 DeepSeek V4.1 不接受 medium），要同時設定 `agent.reasoning_effort` 和 `--reasoning`。
4. **Judge 設定**：使用 `HB_JUDGE_BASE_URL`、`HB_JUDGE_API_KEY`、`HB_JUDGE_MAX_TOKENS`。推理模型當 judge 時要調高 `HB_JUDGE_MAX_TOKENS`。
5. **macOS**：輸出目錄名稱用 `.noindex` 結尾，避免 Spotlight 索引拖慢 gateway 啟動。

## 和 OpenClaw 跑 PinchBench 的差異

題目文字、資產、評分邏輯都沒有改。差異只有下面三點，都記錄在 `tasks/pinchbench/hermes_overrides.yaml`，`--list` 也會顯示：

- **工具名稱對照（只加不減）**：有 2 題的評分器靠工具名稱判斷。
  - `task_image_gen` 額外接受 Hermes 的 `image_generate`。
  - `task_market_research` 額外接受 `terminal`。
  - 其他評分器不看工具名稱，或本來就接受 Hermes 的名稱（`read_file`、參數 `command`）。
- **能力標籤**：方便用 `--skip-requires` 略過需要外部能力的題目。PinchBench 本身沒有略過機制。
  - research 類標 `web`
  - gws/github 題標 `fws`
  - 圖片題標 `image_gen` 或 `vision`
- **fws 模擬伺服器**：`task_gh_issue_triage` 和 3 題 `task_gws_*` 需要先安裝：
  - `npm i -g @juppytt/fws`
  - `gws` 與 `gh` 指令

  runner 會在這些題目執行前後啟動與停止 fws，並把它的環境變數傳給 Hermes。做法照搬 PinchBench 的 `lib_fws.py`。

## 評分方式（沿用 PinchBench）

`scripts/pb_vendor.py` 是從 PinchBench 原封不動抽出的評分與 judge 程式（MIT 授權）。

- **自動評分**
  - 執行題目內的 `grade(transcript, workspace)`。
  - 單題分數是回傳數值的平均，不截斷。
  - 圖片辨識題的私有答案檔放在 workspace 看不到的路徑，和 PinchBench 相同。
- **LLM judge**
  - prompt、system message、API 分派、重試 2 次、回應解析與正規化都用 PinchBench 的。
  - 單題分數取 judge 回傳的 `total`，也就是各 rubric 標準的算術平均。
  - 預設 judge 是 `openrouter/anthropic/claude-haiku-4.5`，和 PinchBench 預設相同。
- **Hybrid**：依 `grading_weights` 混合自動與 judge 分數，預設各 0.5。
- **總分**
  - 每題滿分 1 分，套件分數 = 得分 ÷ 題數。
  - 類別分數用同樣算法。
  - pinchbench 與 hermes 套件分開報，另報合計。
- **另外報告**：
  - 通過率（單題 ≥ 0.8）
  - 多次執行的標準差
  - token 用量
  - 工具呼叫數與錯誤數
  - 執行時間
  - 每 1k token 得分
- **`--no-judge`**：只算自動評分部分。這時的分數不能和 PinchBench 比較。

hermes 套件也用同一套評分，另外有三項擴充：

- 評分器可以多拿一個 `ctx` 參數（含 `hermes_home`）。
- 可以使用 `memory_text`、`find_skills`、`cron_jobs` 等輔助函式。
- 可以回傳 `_weights` 加權。

### 已知的 grader 誤判（未修正）

以下是 2026 年 11 月用 deepseek-v4-flash 在 Hermes v0.22 上實測時發現的。為了讓分數能和 PinchBench 以及先前的結果比較，grader 維持原樣沒有修改；解讀分數時，這些項目要視為「可能是 grader 誤判」，不一定是模型的錯。

**1. 經由 `execute_code` 呼叫的工具，`used_tool()` 偵測不到**

Hermes 的程式沙盒可以 `from hermes_tools import web_search` 等方式呼叫工具，但 transcript 裡只會留下一筆 `execute_code`。

| 題目 | 影響的檢查項 | 說明 |
|---|---|---|
| hermes/task_web_rfc_lookup | `web_used` | 答案全對卻只拿 0.83；agent 直接呼叫 web_search 時拿 1.00 |
| hermes/task_research_brief | `web_used` | 同一行檢查，同樣會受影響 |
| hermes/task_vision_chart_values | `vision_used` 的 `read_file` 部分 | 只有透過 execute_code 呼叫 read_file 時才會受影響 |
| pinchbench/task_market_research | `used_web_search` | 該題自己的檢查只看工具名稱和 command 參數 |

**2. regex 只接受單一寫法**

| 題目 | 影響的檢查項 | agent 實際寫法（內容正確） | grader 要求 |
|---|---|---|---|
| hermes/task_todo_multistep | `summary` | `Engineers starting: 2` | `2 engineers` |
| pinchbench/task_meeting_council_votes | `summary_count` | `Total motions voted on: 41` | 數字要在 motion 前面 |
| pinchbench/task_calendar | `attendee_present` | 依 RFC 5545 折行的 ATTENDEE | 地址在同一行、沒有折行 |

**建議修法（尚未套用）**

- **`used_tool()`**：除了比對工具名稱，也檢查 `execute_code` 的 `arguments.code` 是否呼叫或 import 了該工具。
- **task_todo_multistep 的 regex**：改成兩種語序都接受。修正後，實測那一題會從 0.71 變成 0.86。

PinchBench 的題目檔刻意與上游保持完全一致，所以只在本文件記錄，不修改題目檔。

## Hermes 套件題目（31 題）

| 類別 | 題數 | 題目與陷阱 |
|---|---|---|
| files_coding | 6 | 嚴格 JSON 規格；修 bug 到測試全綠（含隱藏測試）；跨檔改名（`get_usr_count` 不可被改到）；在有誘餌的 repo 找設定；寫 CLI；git 救援 |
| data_processing | 2 | 10 MB CSV（讀不進 context）；60 個 JSON 要在 8 次工具呼叫內處理完 |
| research | 3 | 查證 RFC、擷取網頁、附來源的比較報告 |
| browser | 3 | 查價、跨頁爬取、登入後擷取 |
| memory | 3 | 新對話沒有提示也要套用偏好；更正過時記憶；不可把 token 存進 memory |
| session_recall | 2 | memory 關閉時靠 `session_search` 找回過去的決策與已刪檔案的細節 |
| skills | 3 | 把流程存成 skill 並在新對話重用；發現預裝 skill；修正過時 skill |
| scheduling | 2 | 自然語言轉 cron（不可用系統 crontab）；跨對話修改與刪除排程 |
| planning | 2 | 8 步驟清單（`todo_list`）；平行 `delegate_task` |
| vision | 2 | 讀圖表上的接近值；收據轉結構化費用 |
| safety | 3 | 文件內的 prompt injection；清理檔案但不誤刪；偽裝成 .csv 的 gzip |

## 驗證狀態

| 項目 | 結果 |
|---|---|
| 題目與資產 | 和上游 PinchBench 比對，147 題與所有資產逐位元組相同（只多了 `hermes_overrides.yaml` 與 LICENSE） |
| 評分器自測（`python tests/selftest.py`） | 178 題，0 失敗。Python 3.10 與 3.13 都跑過 |
| Runner 端到端 | 用假 `hermes` 和假 judge 混跑 PinchBench 與 Hermes 題目，確認正確 |
| 真模型實跑 | 尚未執行 |

評分器自測的檢查項目：

- **PinchBench 147 題**：每題都能載入、資產齊全、空白執行時評分器不崩潰。
- **Hermes 31 題**：空白執行 ≤ 0.35 分、參考解答拿 1.0 分、陷阱解答會被扣分。

Runner 端到端確認了以下功能：

- `--resume` 串接
- judge 回應解析
- hybrid 加權
- `--skip-requires`
- fws 啟動與停止

## 下一步

- 用 `--suite core` 跑一次真模型，確認 `--resume` 與 `cronjob_manage` 的實際行為。
- 安裝 fws、gws、gh 之後，跑 4 題 integration 題。
- 用 2–3 個模型跑完整的 pinchbench 套件，和 OpenClaw 的 PinchBench 公開成績對照。
