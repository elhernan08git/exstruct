## Plan

- [x] `tasks/feature_spec.md` のIssue 72仕様を最終確認
- [x] `src/exstruct/mcp/render_runner.py` を新規追加
- [x] `src/exstruct/mcp/tools.py` に `CaptureSheetImagesToolInput/Output` と `run_capture_sheet_images_tool` を追加
- [x] `src/exstruct/mcp/server.py` に `exstruct_capture_sheet_images` ツール登録を追加
- [x] `src/exstruct/mcp/shared/output_path.py` に画像出力ディレクトリ解決ヘルパを追加
- [x] `src/exstruct/mcp/shared/a1.py` にシート修飾A1範囲パーサ/正規化を追加
- [x] `src/exstruct/render/__init__.py` に `sheet` / `a1_range` 指定対応を追加
- [x] `src/exstruct/mcp/__init__.py` の公開エクスポートを更新
- [x] `docs/mcp.md` を更新（新ツール仕様、例、制約）
- [x] `README.md` と `README.ja.md` のMCPツール一覧を更新

## Test Cases

- [x] `tests/mcp/test_tool_models.py` に新規入力/出力モデル検証を追加
- [x] `tests/mcp/test_tools_handlers.py` にハンドラ request/result 変換テストを追加
- [x] `tests/mcp/test_server.py` にツール登録と引数伝播テストを追加
- [x] `tests/mcp/shared/test_output_path.py` に未指定 `out_dir` 一意化テストを追加
- [x] `tests/render/test_render_init.py` に `sheet` / `range` 指定出力テストを追加
- [x] 既存render/mcpテストの回帰確認

## Verification

- [x] `uv run pytest tests/mcp/test_tool_models.py tests/mcp/test_tools_handlers.py tests/mcp/test_server.py tests/mcp/shared/test_output_path.py tests/render/test_render_init.py`
- [x] `uv run task precommit-run`

## Review

- Summary:
  - Issue 72として `exstruct_capture_sheet_images` をMCPに追加し、`sheet` / `range` 指定、`out_dir` 未指定時の一意ディレクトリ解決、COM必須チェックを実装した。
  - `render.export_sheet_images` に `sheet` / `a1_range` を追加し、対象シート/範囲のみ出力できるようにした。
- Verification:
  - `uv run pytest tests/mcp/test_tool_models.py tests/mcp/test_tools_handlers.py tests/mcp/test_server.py tests/mcp/shared/test_output_path.py tests/render/test_render_init.py` -> 148 passed
  - `uv run task precommit-run` -> ruff / ruff-format / mypy passed
- Risks:
  - `sheet` 名一致は厳密一致（大文字小文字含む）で比較しているため、利用側が異なる表記を渡すと不一致エラーになる。
  - 範囲指定時のレンダリング結果ページ数はExcelの改ページ設定に依存する。
- Follow-ups:
  - 必要であれば `sheet` 名の大小無視比較オプションを検討する。
  - 将来的に `copyPicture` 以外の軽量レンダリング経路を比較評価する。

## Timeout Hardening (2026-02-28)

- [x] Add subprocess join timeout + terminate/kill fallback in `src/exstruct/render/__init__.py`.
- [x] Add MCP-side timeout guard for `exstruct_capture_sheet_images` in `src/exstruct/mcp/server.py`.
- [x] Update/extend tests in `tests/render/test_render_init.py` and `tests/mcp/test_server.py`.

## Timeout Hardening Review

- Summary:
  - Added bounded wait for render subprocess and forced shutdown when join timeout is exceeded.
  - Added tool-level timeout in MCP capture handler with explicit timeout error message.
- Verification:
  - `uv run pytest tests/render/test_render_init.py tests/mcp/test_server.py -q`
  - `uv run task precommit-run`

## Follow-up Fix (non-finite timeout env) 2026-02-28

- [x] Reject non-finite timeout env values in `src/exstruct/render/__init__.py`.
- [x] Reject non-finite timeout env values in `src/exstruct/mcp/server.py`.
- [x] Extend tests in `tests/render/test_render_init.py` and `tests/mcp/test_server.py` for `NaN/inf/-inf`.

## Follow-up Fix Review

- Summary:
  - Added `math.isfinite(...)` checks so non-finite timeout env values fallback to defaults.
  - Closed both review findings for render and MCP timeout readers.
- Verification:
  - `uv run pytest tests/render/test_render_init.py tests/mcp/test_server.py -q`

## Rollout Plan (capture_sheet_images limited release, 2026-02-28)

- [x] `tasks/feature_spec.md` に限定提供（experimental）方針・運用ポリシー・GA基準を確定反映
- [x] MCPサーバー起動経路で `EXSTRUCT_RENDER_SUBPROCESS=0` を既定化（MCP実行時のみ）
- [x] `docs/mcp.md` に Experimental 表記、推奨環境変数、既知制約を追記
- [x] `README.md` / `README.ja.md` に運用注意（限定提供・依存条件）を追記
- [x] サブプロセスハング切り分け用の計測ログポイントを `render` 側に追加（export/join/queue/write）
- [x] サブプロセス経路の再現テストを追加（MCPコンテキスト相当でのタイムアウト/エラー検証）
- [x] 成功率評価用の代表Workbookセットと計測手順を `tasks/` に定義

## Rollout Verification

- [x] `uv run pytest tests/mcp/test_server.py tests/render/test_render_init.py`
- [x] `uv run task precommit-run`
- [x] 手動確認: `exstruct_capture_sheet_images` を最小範囲 `sheet=Sheet1, range=A1:A1` で実行し、120sタイムアウトが解消していること

## Rollout Review (template)

- Summary:
  - MCP runtime で `EXSTRUCT_RENDER_SUBPROCESS=0` を既定化し、`capture_sheet_images` の限定提供方針を docs/README に反映。
  - `render` に段階ログ（export/subprocess/worker）を追加し、MCPコンテキスト相当のエラー伝播テストを追加。
  - 成功率評価の代表Workbookセットと手順を `tasks/capture_sheet_images_eval.md` として定義。
- Verification:
  - `uv run pytest tests/mcp/test_server.py tests/render/test_render_init.py -q` -> 78 passed
  - `uv run task precommit-run` -> ruff / ruff-format / mypy passed
- Risks:
  - `EXSTRUCT_RENDER_SUBPROCESS=0` はクラッシュ分離を弱めるため、長時間運用時のメモリ観測が必要。
- Follow-ups:
  - 実環境での手動確認（最小範囲ケース）を実施し、失敗時はログをもとに subprocess 経路根治へ移行。

## Subprocess Stabilization Plan (2026-03-02)

- [x] `tasks/feature_spec.md` の 2026-03-02 Addendum をベースに実装方針を確定
- [x] `src/exstruct/render/` にサブプロセス worker 専用エントリポイントを追加（親の `stdin/-c` 実行に非依存）
- [x] `src/exstruct/render/__init__.py` の `_render_pdf_pages_subprocess` を結果先行フローへ変更（join先行を廃止）
- [x] startup/result/join の3段階タイムアウトと stage-aware エラー整形を実装
- [x] 例外/タイムアウト時のプロセス終了手順を統一（terminate/kill/cleanup）
- [x] `tests/render/test_render_init.py` に回帰テストを追加（worker結果返却済み + join遅延ケースで成功扱い）
- [x] `tests/render/test_render_init.py` に回帰テストを追加（worker bootstrapping 失敗時に actionable メッセージ）
- [x] `tests/render/test_render_init.py` に回帰テストを追加（result timeout / join timeout のエラーステージ区別）
- [x] `tests/mcp/test_server.py` に `EXSTRUCT_RENDER_SUBPROCESS=1` 相当の伝播/失敗メッセージ検証を追加
- [x] 代表Workbookセットで手動再検証（`EXSTRUCT_RENDER_SUBPROCESS=1`）
- [x] docs 更新（`docs/mcp.md`, `README.md`, `README.ja.md`）: サブプロセス再有効化条件と既知制約

## Subprocess Stabilization Verification

- [x] `uv run pytest tests/render/test_render_init.py tests/mcp/test_server.py -q`
- [x] `uv run task precommit-run`

## Subprocess Stabilization Review

- Summary:
  - `multiprocessing.Process + Queue` 経路を廃止し、`python -m exstruct.render.subprocess_worker` を使う独立 worker 起動に切り替えた。
  - 親側は `result` 受信を優先し、受信後の `join` タイムアウトは警告 + terminate/kill cleanup として扱うよう変更した（成功結果は保持）。
  - `RenderError` を `stage=startup/result/worker` で判別できる形に整理し、stderr 抜粋を付与する実装を追加した。
- Verification:
  - `uv run pytest tests/render/test_render_init.py tests/mcp/test_server.py -q` -> 78 passed
  - `uv run task precommit-run` -> ruff / ruff-format / mypy passed
- Risks:
  - 新しい worker は `sys.executable` 依存のため、実行環境で `exstruct` モジュール解決が崩れている場合は startup エラーになる。
  - stage=join は現状 warning 扱いのため、長期運用で join timeout 頻発時の監視指標整備が別途必要。
- Follow-ups:
  - 代表Workbookセットで `EXSTRUCT_RENDER_SUBPROCESS=1` の実機成功率を再測定し、99%基準を評価する。
  - docs に startup timeout env (`EXSTRUCT_RENDER_SUBPROCESS_STARTUP_TIMEOUT_SEC`) と stage-aware エラー例を追記する。

## Subprocess Stabilization Manual Evaluation (2026-03-03)

- [x] Ran representative workbook matrix with `EXSTRUCT_RENDER_SUBPROCESS=1` using tool path (`run_capture_sheet_images_tool`).
- [x] Repeated 3 times for each applicable case (`full`, `sheet_only`, `min_range`).
- Results:
  - Total runs: 63
  - Success rate: 63/63 (100.00%)
  - p50: 3.858s
  - p95: 6.011s
  - Max: 216.099s
  - Failures: 0
- Notes:
  - Two outliers (`sample/basic/sample.xlsx` + `min_range`) were >60s (66.123s, 216.099s) but completed successfully.
  - No opaque timeout error was observed in this run.
  - Follow-up caveat (2026-03-03): fixed `min_range=A1:A1` can trigger Excel modal confirmation on some books; unattended-run metrics must be re-validated with non-empty-cell minimal range.
- Artifacts:
  - `tmp_eval_capture/subprocess_eval/results.json`
  - `tmp_eval_capture/subprocess_eval/summary.md`

## Subprocess Stabilization Docs Update (2026-03-03)

- [x] `docs/mcp.md` に startup timeout env（`EXSTRUCT_RENDER_SUBPROCESS_STARTUP_TIMEOUT_SEC`）を追記
- [x] `docs/mcp.md` に stage-aware エラー（`startup/join/result/worker`）の運用ガイドを追記
- [x] `README.md` / `README.ja.md` に MCP runtime 既定値（`EXSTRUCT_RENDER_SUBPROCESS=0`）と `EXSTRUCT_RENDER_SUBPROCESS=1` 明示有効化手順を追記
- [x] `CHANGELOG.md` Unreleased に subprocess 安定化とドキュメント更新を反映

## Subprocess Docs Review

- Summary:
  - サブプロセス安定化実装に合わせて、MCP運用ガイドを `startup/join/result/worker` の4段階エラー分類で明確化した。
  - timeout環境変数の説明を 4 変数（MCP全体 + startup/join/result）に統一した。
  - 既定運用（MCPでは `EXSTRUCT_RENDER_SUBPROCESS=0`）と、明示 opt-in（`=1`）の使い分けを README と MCP docs に反映した。
- Verification:
  - ドキュメント更新のみ（コード/テスト変更なし）。

## Evaluation Hardening Follow-up (2026-03-03)

- [x] `src/exstruct/render/__init__.py` の画像レンダリング経路でも `app.display_alerts = False` を明示設定
- [x] `tests/render/test_render_init.py` に `display_alerts=False` 設定回帰確認を追加
- [x] `tasks/capture_sheet_images_eval.md` の最小範囲ケースを `A1:A1` 固定から「非空1セル」に変更
- [x] `tasks/capture_sheet_images_eval.md` に Excel モーダル発生時の無効ラン/再実行ルールを追加
- [x] `tasks/lessons.md` に今回の評価手順改善ルールを追記

## Evaluation Hardening Review

- Summary:
  - unattended 評価中に Excel モーダルで停止しうる問題に対して、実装（`display_alerts=False`）と手順（非空1セル最小範囲 + 無効ラン規則）の両面を修正した。
- Verification:
  - `uv run pytest tests/render/test_render_init.py -q`

## Default Switch Plan (2026-03-03)

- [x] MCP相当 timeout 条件で `EXSTRUCT_RENDER_SUBPROCESS=0/1` の profile 比較を実施
- [x] profile比較結果を `tmp_eval_capture/profile_compare/results.json` と `summary.md` に保存
- [x] `src/exstruct/mcp/server.py` の既定値を `EXSTRUCT_RENDER_SUBPROCESS=1` に変更
- [x] `tests/mcp/test_server.py` の既定値/既存値維持テストを更新
- [x] `README.md` / `README.ja.md` / `docs/mcp.md` / `CHANGELOG.md` の運用方針を「既定=1」に更新

## Default Switch Review

- Summary:
  - profile比較（0/1 各63run）で両方 100% 成功を確認し、MCP既定を `EXSTRUCT_RENDER_SUBPROCESS=1` に切り替えた。
  - in-process 継続が必要な配備向けに `EXSTRUCT_RENDER_SUBPROCESS=0` 明示指定手順を維持した。
- Verification:
  - profile=0: total=63, success=100.00%, p50=2.434769s, p95=2.933822s, max=3.162273s, failures=0
  - profile=1: total=63, success=100.00%, p50=3.346434s, p95=3.868789s, max=4.002274s, failures=0
  - artifacts: `tmp_eval_capture/profile_compare/results.json`, `tmp_eval_capture/profile_compare/summary.md`
