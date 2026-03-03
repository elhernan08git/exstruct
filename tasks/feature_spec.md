# Feature Spec

## Feature Name

Issue 72: MCP `exstruct_capture_sheet_images` (範囲指定付き画像エクスポート)

## Goal

AIエージェントがExcelシートを視覚検証できるように、MCPツールからPNG画像を安全に出力できるようにする。

- 範囲指定（`A1:B2` / `Sheet1!A1:B2` / `'Sheet 1'!A1:B2`）を受け付ける
- COM限定で動作させる
- `copyPicture` は使わず、PDF変換 + `pypdfium2` で画像化する
- `out_dir` 未指定時は root 直下に一意ディレクトリを作る
- `out_dir` 指定有無に関係なく、実行後に出力先ディレクトリパスを返す

## Scope

### In Scope

- MCP新規ツール `exstruct_capture_sheet_images` 追加
- `sheet` / `range` 入力に基づく対象シート・対象範囲の画像出力
- root配下の一意出力ディレクトリ解決
- COM可用性チェック
- 関連テスト追加・更新
- docs更新

### Out of Scope

- `copyPicture` ベース実装
- openpyxlのみでの画像出力
- 既存CLI引数の拡張
- PDF以外の中間形式追加

## Public API / Interface Changes

### MCP Tool (new)

- Tool name: `exstruct_capture_sheet_images`
- Input:
  - `xlsx_path: str` (required)
  - `out_dir: str | None = None`
  - `dpi: int = 144` (`>= 1`)
  - `sheet: str | None = None`
  - `range: str | None = None`
- Output:
  - `out_dir: str` (resolved output directory, always returned)
  - `image_paths: list[str]`
  - `warnings: list[str]`

### Python Internal API Changes

- `src/exstruct/render/__init__.py`
  - `export_sheet_images(...)` に以下を追加:
    - `sheet: str | None = None`
    - `a1_range: str | None = None`

### Internal Models (new)

- `CaptureSheetImagesRequest` (Pydantic BaseModel)
  - `xlsx_path: Path`
  - `out_dir: Path | None = None`
  - `dpi: int = Field(default=144, ge=1)`
  - `sheet: str | None = None`
  - `range: str | None = None`
- `CaptureSheetImagesResult` (Pydantic BaseModel)
  - `out_dir: str`
  - `image_paths: list[str]`
  - `warnings: list[str] = Field(default_factory=list)`

## Behavior Spec

### 1. `sheet` / `range` のルール

- `range is None`:
  - `sheet is None` の場合は全シート出力
  - `sheet` 指定時は指定シートのみ出力
- `range is not None`:
  - `sheet` 必須（未指定はエラー）
  - `range` は以下を許可:
    - `A1:B2`
    - `Sheet1!A1:B2`
    - `'Sheet 1'!A1:B2`
  - `sheet` と `range` のシート名が不一致ならエラー

### 2. 出力先ディレクトリ

- `out_dir` 指定あり:
  - 指定先を利用（`PathPolicy` で許可範囲検証）
- `out_dir` 未指定:
  - MCP `--root` 直下に `<workbook_stem>_images` を候補作成
  - 競合時は `<workbook_stem>_images_1`, `_2`, ... で一意化
- 実行結果には常に `out_dir`（解決済み実パス）を含める

### 3. バックエンド/実装制約

- COM限定機能（Excel COM利用不可ならエラー）
- 画像生成パイプラインは現行維持:
  - `ExportAsFixedFormat(PDF)` -> `pypdfium2` -> PNG
- `copyPicture` は採用しない

## Error Handling

- `dpi < 1` -> ValidationError
- `range` 形式不正 -> ValueError
- `range` 指定時の `sheet` 未指定 -> ValueError
- `sheet` と `range` シート修飾不一致 -> ValueError
- COM不可 -> ValueError (COM必須メッセージ)
- 出力先が `PathPolicy` 範囲外 -> ValueError
- PDF/画像変換失敗 -> RenderError

## Files to Change

- `src/exstruct/mcp/server.py`
- `src/exstruct/mcp/tools.py`
- `src/exstruct/mcp/render_runner.py` (new)
- `src/exstruct/mcp/shared/output_path.py`
- `src/exstruct/mcp/shared/a1.py`
- `src/exstruct/mcp/__init__.py`
- `src/exstruct/render/__init__.py`
- `tests/mcp/test_tool_models.py`
- `tests/mcp/test_tools_handlers.py`
- `tests/mcp/test_server.py`
- `tests/mcp/shared/test_output_path.py`
- `tests/render/test_render_init.py`
- `docs/mcp.md`
- `README.md`
- `README.ja.md`

## Test Scenarios

### Model/Validation

- `dpi=0` を拒否
- `range` 指定時の `sheet` 未指定を拒否
- `range` のシート修飾付き形式を受理・正規化
- `sheet` / `range` 不一致を拒否

### Tool Handler/Server

- `exstruct_capture_sheet_images` が登録される
- 入力が `run_capture_sheet_images_tool` に正しく渡る
- 出力 `out_dir` / `image_paths` が返る

### Output Path

- 未指定 `out_dir` で `<stem>_images` 作成
- 衝突時に連番リネーム
- 指定 `out_dir` はそのまま使う

### Render

- `sheet + range` 指定で対象のみ出力
- `sheet` のみ指定で単一シート出力
- `range` なしで既存動作を維持
- 不正範囲入力時に失敗する

## Acceptance Criteria

- MCPツール `exstruct_capture_sheet_images` が利用できる
- 範囲指定仕様（A1/B2、シート修飾、不一致エラー）が満たされる
- `out_dir` 未指定時に root直下へ一意ディレクトリ作成される
- レスポンスに常に `out_dir` が含まれる
- COM限定・PDF->PNG経路が守られる
- 追加テストと既存回帰テストが通る

## Verification Commands

- `uv run pytest tests/mcp/test_tool_models.py tests/mcp/test_tools_handlers.py tests/mcp/test_server.py tests/mcp/shared/test_output_path.py tests/render/test_render_init.py`
- `uv run task precommit-run`

## Timeout Hardening Addendum (2026-02-28)

### Scope
- Add bounded subprocess wait to render pipeline to avoid indefinite hang.
- Add MCP timeout guard for `exstruct_capture_sheet_images` to avoid client-side disconnect cascades.

### New Env Vars
- `EXSTRUCT_RENDER_SUBPROCESS_JOIN_TIMEOUT_SEC` (default: `120`)
- `EXSTRUCT_RENDER_SUBPROCESS_RESULT_TIMEOUT_SEC` (default: `5`)
- `EXSTRUCT_MCP_CAPTURE_SHEET_IMAGES_TIMEOUT_SEC` (default: `120`)

### Expected Behavior
- If render subprocess exceeds join timeout, terminate/kill and raise `RenderError`.
- If MCP capture exceeds tool timeout, raise `TimeoutError` with actionable guidance.

## Timeout Validation Hardening Addendum (2026-02-28)

### Scope
- Treat non-finite timeout env values (`NaN`, `inf`, `-inf`) as invalid in both render and MCP timeout readers.

### Expected Behavior
- `EXSTRUCT_RENDER_SUBPROCESS_JOIN_TIMEOUT_SEC` and `EXSTRUCT_RENDER_SUBPROCESS_RESULT_TIMEOUT_SEC`:
  - When the env value is non-finite, fallback to default timeout.
- `EXSTRUCT_MCP_CAPTURE_SHEET_IMAGES_TIMEOUT_SEC`:
  - When the env value is non-finite, fallback to default timeout.

### Verification
- Add tests that set env vars to `NaN`, `inf`, `-inf` and assert default fallback.

## Rollout Strategy Addendum (2026-02-28)

### Product Decision
- Do not drop `exstruct_capture_sheet_images`.
- Ship as `experimental` with explicit operational constraints until stability criteria are met.

### Operational Policy (Phase 1)
- Keep tool name and API unchanged.
- Default runtime should set `EXSTRUCT_RENDER_SUBPROCESS=0` for MCP server deployments.
- Keep MCP timeout guard enabled; recommend `EXSTRUCT_MCP_CAPTURE_SHEET_IMAGES_TIMEOUT_SEC >= 180` in production.
- Document that COM + Excel desktop + render dependencies are required and behavior depends on workbook/page settings.

### Risks / Trade-offs (accepted in Phase 1)
- In-process PDF rendering reduces crash isolation and may increase long-running process memory pressure.
- This is accepted short-term to avoid current subprocess hang/timeout behavior in MCP context.

### Stabilization Scope (Phase 2)
- Investigate and fix subprocess rendering hang in MCP runtime context.
- Add diagnostics to distinguish: COM export time, subprocess start/join, queue result wait, and PNG write.
- Re-enable subprocess mode by default only after acceptance criteria are satisfied.

### Formalization Criteria (GA gate)
- Success rate >= 99% on representative workbook suite in MCP execution path.
- No silent 120s timeout; failures must return explicit actionable errors.
- Repeated runs do not show unacceptable memory growth in MCP server process.

### Documentation Requirements
- `docs/mcp.md`: add Experimental label, required env vars, and recommended production settings.
- `README.md` / `README.ja.md`: add operational note for `capture_sheet_images`.
- Release notes: record default `EXSTRUCT_RENDER_SUBPROCESS=0` policy for MCP runtime.

### Verification Commands
- `uv run pytest tests/mcp/test_server.py tests/render/test_render_init.py`
- `uv run task precommit-run`

## Subprocess Stabilization Addendum (2026-03-02)

### Problem Statement
- `EXSTRUCT_RENDER_SUBPROCESS=1` の `capture_sheet_images` が MCP 実行コンテキストで不安定。
- 既知失敗モード:
  - Windows `spawn` 子プロセス起動時に親 `__main__` 復元が失敗し、worker結果が返らない。
  - worker が結果を返却済みでも、親が `join(timeout)` を先に待ってタイムアウト扱いになる。

### Scope
- `src/exstruct/render/__init__.py` のサブプロセス実行経路を安定化する。
- 失敗時メッセージを stage-aware にして、原因切り分け可能にする。
- 既存の公開API（`export_sheet_images`, MCP tool I/O）を変更しない。

### Out of Scope
- `copyPicture` ベースへの切り替え。
- MCP tool 名・入力・出力の互換性破壊。

### Design Requirements
- 親プロセスは「結果受信」を「終了待ち」より優先して扱う（join先行を廃止）。
- worker が `paths` を返した場合、親は成功として扱い、その後に bounded cleanup を行う。
- worker が `error` を返した場合、`RenderError` に stage情報（startup/join/result/worker）を含める。
- worker bootstrapping 失敗時は、空メッセージではなく actionable なエラーを返す。
- サブプロセス起動は、親の `stdin` / `-c` 実行形態に依存しない方式にする。
- 例外時でも orphan process（python/Excel）を残しにくい終了手順を実装する。
- timeout 設定は `EXSTRUCT_RENDER_SUBPROCESS_STARTUP_TIMEOUT_SEC`（default: `5`）、
  `EXSTRUCT_RENDER_SUBPROCESS_RESULT_TIMEOUT_SEC`、`EXSTRUCT_RENDER_SUBPROCESS_JOIN_TIMEOUT_SEC`
  の3段階で管理する。

### Preferred Implementation Direction
- `multiprocessing.Process + Queue` 直結ではなく、専用 worker エントリポイントを独立モジュール化する。
- 親は `subprocess` で worker を起動し、結果をシリアライズ（stdout or artifact file）で受け取る。
- タイムアウトは「起動」「結果待ち」「終了待ち」の3段階で管理する。

### Acceptance Criteria (Phase 2)
- 代表Workbookセットで `EXSTRUCT_RENDER_SUBPROCESS=1` の成功率が 99%以上。
- 「subprocess did not return results」のような非特定エラーを残さない。
- worker 結果返却済みケースで joinタイムアウト誤判定が発生しない。
- 再試行実行後に orphan python/excel process が増加しない。

### Verification Commands (Phase 2)
- `uv run pytest tests/render/test_render_init.py tests/mcp/test_server.py -q`
- `uv run task precommit-run`

## Documentation Finalization Addendum (2026-03-03)

### Validation Outcome
- 代表Workbookセットの手動評価（`EXSTRUCT_RENDER_SUBPROCESS=1`）で 63/63 成功（100.00%）。
- `stage=startup/join/result/worker` の失敗分類と 3 段階 timeout（startup/result/join）が実装・テスト済み。

### Runtime Policy (current)
- MCPサーバー既定は `EXSTRUCT_RENDER_SUBPROCESS=1`（`setdefault`）へ更新。
- 同一プロセス運用が必要な配備では `EXSTRUCT_RENDER_SUBPROCESS=0` を明示指定して運用可能。

### Documentation Requirements (fulfilled)
- `docs/mcp.md`:
  - `EXSTRUCT_RENDER_SUBPROCESS_STARTUP_TIMEOUT_SEC` を含む timeout 一覧を反映。
  - stage-aware エラー（`startup/join/result/worker`）の意味と切り分けガイドを反映。
- `README.md` / `README.ja.md`:
  - MCP runtime 既定値（`EXSTRUCT_RENDER_SUBPROCESS=1`）と fallback (`=0`) 手順を反映。
  - timeout 調整項目（MCP全体 + startup/join/result）を反映。
- `CHANGELOG.md`:
  - Unreleased に subprocess 安定化（専用 worker / 結果先行 wait / actionable error）を記録。

## Evaluation Method Hardening Addendum (2026-03-03)

### Problem
- unattended の安定性評価で `sheet + range=A1:A1` を固定すると、Workbook条件により Excel 確認ダイアログで評価が停止する場合がある。

### Requirement
- 評価ケースの最小範囲は固定 `A1:A1` ではなく「対象シートの非空1セル」を使う。
- Excel モーダルが出た試行は有効データに含めず、条件修正後に再実行する。
- 画像レンダリング経路（`export_sheet_images`）でも `app.display_alerts = False` を明示設定する。

### Verification
- `tests/render/test_render_init.py` で `export_sheet_images` 実行時に `display_alerts=False` が設定されることを確認する。

## Default Switch Addendum (2026-03-03)

### Decision
- MCPサーバー既定値を `EXSTRUCT_RENDER_SUBPROCESS=1` に切り替える。

### Evidence
- MCP相当の timeout 処理（`anyio.fail_after(180s)` + `to_thread.run_sync(abandon_on_cancel=True)`) で profile比較を実施。
- 集計結果:
  - profile=0: total=63, success=63/63 (100.00%), p50=2.434769s, p95=2.933822s, max=3.162273s
  - profile=1: total=63, success=63/63 (100.00%), p50=3.346434s, p95=3.868789s, max=4.002274s

### Compatibility
- 既存配備で in-process が必要な場合は `EXSTRUCT_RENDER_SUBPROCESS=0` を明示指定すれば従来運用を継続できる。
