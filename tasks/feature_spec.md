# Feature Spec

## Issue

- Issue #56: LibreOffice backend / `libreoffice` mode 追加
- 目的: Excel COM に依存していた一部の抽出を、Linux / macOS / server / CI でも best-effort で実行できるようにする

## 背景

- 現状の rich extraction は `standard` / `verbose` で Excel COM に依存している。
- 非 COM 環境では `light` 相当のフォールバックしかなく、shape / connector / chart の構造情報が落ちる。
- issue 56 の要求は「COM 同等の厳密性」ではなく、「server-first の best-effort 抽出」を追加することにある。

## ゴール

- 新しい抽出モード `libreoffice` を追加する。
- `libreoffice` mode は `light` より多く、`standard` より少ない情報を返す。
- v1 では shape / connector / chart を対象にし、connector graph を最優先で復元する。
- 出力に provenance / confidence を持たせ、downstream が精度差を判定できるようにする。

## 非ゴール

- Excel COM と同一のレイアウト再現
- Excel の `DisplayFormat` 相当の見た目再現
- SmartArt の忠実な復元
- auto page-break の LibreOffice 版実装
- LibreOffice を使った PDF / PNG rendering の追加
- `.xls` の LibreOffice mode 対応
- `standard` / `verbose` での自動 LibreOffice フォールバック

## 公開仕様

### 1. モード

`ExtractionMode` は次の 4 値にする。

```python
ExtractionMode = Literal["light", "libreoffice", "standard", "verbose"]
```

各モードの意味は次のとおり。

| mode | 目的 | 主な出力 |
| --- | --- | --- |
| `light` | 最小・高速 | cells, table_candidates, print_areas |
| `libreoffice` | 非 COM 環境向け best-effort | `light` + merged_cells + shapes + connectors + charts |
| `standard` | 既定 | COM 利用可能なら既存の rich extraction |
| `verbose` | 最多情報 | `standard` + size / links / maps |

### 2. `libreoffice` mode の既定値

- `include_cell_links=False`
- `include_print_areas=True`
- `include_auto_page_breaks=False`
- `include_colors_map=False`
- `include_formulas_map=False`
- `include_merged_cells=True`
- `include_merged_values_in_rows=True`

### 3. `libreoffice` mode の対象拡張子

- 対象: `.xlsx`, `.xlsm`
- 非対象: `.xls`
- `.xls` を `mode="libreoffice"` で指定した場合は、処理開始前に `ValueError` を返す。
- エラーメッセージは「`.xls` is not supported in libreoffice mode; use COM-backed standard/verbose or convert to .xlsx`」相当の明確な文言にする。

### 4. `libreoffice` mode の出力保証

- `rows`, `table_candidates`, `print_areas`, `merged_cells` は既存の openpyxl / pandas ベース抽出をそのまま使う。
- `shapes` は LibreOffice UNO + OOXML drawing を使って best-effort で抽出する。
- `charts` は OOXML chart 定義 + LibreOffice UNO geometry で best-effort で抽出する。
- `auto_print_areas` は常に空とする。
- `colors_map`, `formulas_map`, cell hyperlink は既定では出さない。

### 5. LibreOffice 不在時 / 実行失敗時の挙動

- `mode="libreoffice"` 指定時に `soffice` または `uno` が使えない場合、処理は落とさず pre-analysis までの成果物で fallback workbook を返す。
- この fallback workbook には `rows`, `table_candidates`, `print_areas`, `merged_cells` を含め、`shapes` / `charts` は空配列にする。
- `PipelineState.fallback_reason` に `LIBREOFFICE_UNAVAILABLE` または `LIBREOFFICE_PIPELINE_FAILED` を設定する。
- `standard` / `verbose` は従来どおり COM 専用とし、LibreOffice への自動切り替えは行わない。

### 6. CLI / process API の互換性ルール

- `mode="libreoffice"` は抽出専用モードとして扱う。
- `process_excel(...)` / `ExStructEngine.process(...)` で `mode="libreoffice"` と以下の組み合わせを指定した場合、処理開始前に `ConfigError` を返す。
  - `pdf=True`
  - `image=True`
  - `auto_page_breaks_dir` を指定
- `extract_workbook(...)` / `ExStructEngine.extract(...)` で `include_auto_page_breaks=True` 相当になった場合も、`mode="libreoffice"` では `ConfigError` を返す。
- エラーは silent ignore ではなく hard fail に統一する。
- エラーメッセージは少なくとも以下の意図を含む明確な文言にする。
  - `libreoffice mode does not support PDF/PNG rendering`
  - `libreoffice mode does not support auto page-break export`
  - `use standard/verbose with Excel COM`

## モデル変更

### 1. Shape metadata

`BaseShape` に次の任意フィールドを追加する。

```python
class BaseShape(BaseModel):
    provenance: Literal["excel_com", "libreoffice_uno"] | None = None
    approximation_level: Literal["direct", "heuristic", "partial"] | None = None
    confidence: float | None = None
```

意味は以下。

- `provenance`: 抽出元 backend
- `approximation_level`:
  - `direct`: backend が直接持っている情報を採用
  - `heuristic`: 幾何推定などの推論を含む
  - `partial`: 一部は direct だが、一部欠落または代替手段を使った
- `confidence`: 0.0 から 1.0 の best-effort 信頼度

### 2. Chart metadata

`Chart` に同じ 3 フィールドを追加する。

```python
class Chart(BaseModel):
    provenance: Literal["excel_com", "libreoffice_uno"] | None = None
    approximation_level: Literal["direct", "heuristic", "partial"] | None = None
    confidence: float | None = None
```

既存の `name`, `chart_type`, `title`, `series`, `y_axis_title`, `y_axis_range`, `l`, `t`, `w`, `h`, `error` は維持する。

## 内部インターフェース仕様

### 1. pipeline 入力型

`ExtractionInputs.mode` は `libreoffice` を許容する。

```python
@dataclass(frozen=True)
class ExtractionInputs:
    file_path: Path
    mode: Literal["light", "libreoffice", "standard", "verbose"]
    ...
```

### 2. rich backend 抽象

shape / chart 抽出を backend 境界に寄せるため、内部専用 protocol を追加する。

```python
class RichBackend(Protocol):
    def extract_shapes(
        self,
        *,
        mode: Literal["libreoffice", "standard", "verbose"],
    ) -> dict[str, list[Shape | Arrow | SmartArt]]: ...

    def extract_charts(
        self,
        *,
        mode: Literal["libreoffice", "standard", "verbose"],
    ) -> dict[str, list[Chart]]: ...
```

- 既存 COM 抽出はこの protocol に合わせてラップする。
- 新規 `LibreOfficeRichBackend` を追加する。

### 3. LibreOffice session helper

LibreOffice UNO 呼び出しは subprocess 分離で扱う。

```python
@dataclass(frozen=True)
class LibreOfficeSessionConfig:
    soffice_path: Path
    startup_timeout_sec: float
    exec_timeout_sec: float
    profile_root: Path | None

class LibreOfficeSession:
    def __enter__(self) -> LibreOfficeSession: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    def load_workbook(self, file_path: Path) -> object: ...
    def close_workbook(self, workbook: object) -> None: ...
    def extract_draw_page_shapes(
        self, file_path: Path
    ) -> dict[str, list[LibreOfficeDrawPageShape]]: ...
    def extract_chart_geometries(
        self, file_path: Path
    ) -> dict[str, list[LibreOfficeChartGeometry]]: ...
```

設定元環境変数:

- `EXSTRUCT_LIBREOFFICE_PATH`
- `EXSTRUCT_LIBREOFFICE_STARTUP_TIMEOUT_SEC`
- `EXSTRUCT_LIBREOFFICE_EXEC_TIMEOUT_SEC`
- `EXSTRUCT_LIBREOFFICE_PROFILE_ROOT`

### 4. OOXML helper

connector explicit ref と chart semantic を取るため、OOXML helper を追加する。

```python
@dataclass(frozen=True)
class DrawingShapeRef:
    drawing_id: int
    name: str
    kind: Literal["shape", "connector", "chart"]
    left: int | None
    top: int | None
    width: int | None
    height: int | None

@dataclass(frozen=True)
class DrawingConnectorRef:
    drawing_id: int
    start_drawing_id: int | None
    end_drawing_id: int | None

@dataclass(frozen=True)
class OoxmlChartInfo:
    name: str
    chart_type: str
    title: str | None
    y_axis_title: str
    y_axis_range: list[float]
    series: list[ChartSeries]
    anchor_left: int | None
    anchor_top: int | None
    anchor_width: int | None
    anchor_height: int | None
```

### 5. LibreOffice draw-page payload

`libreoffice` mode shape extraction adds a UNO draw-page payload model.

```python
@dataclass(frozen=True)
class LibreOfficeDrawPageShape:
    name: str
    shape_type: str | None = None
    text: str = ""
    left: int | None = None
    top: int | None = None
    width: int | None = None
    height: int | None = None
    rotation: float | None = None
    is_connector: bool = False
    start_shape_name: str | None = None
    end_shape_name: str | None = None
```

Connector resolution priority is fixed:
1. OOXML explicit ref (`stCxn`/`endCxn`)
2. UNO direct ref (`StartShape`/`EndShape`)
3. geometry heuristic (endpoint vs shape bbox)

`extract_shapes(mode="libreoffice")` uses the UNO draw-page payload as the
canonical emitted order when available. OOXML remains a supplemental source for
Excel-like shape type labels, connector arrowhead styles, explicit refs, and
heuristic endpoint geometry.

## 抽出アルゴリズム

### 1. shape / connector

`libreoffice` mode の shape / connector は以下の責務分担で組み立てる。

- UNO:
  - `DrawPage` から shape 一覧を取得
  - type, text, left/top, width/height, rotation を取得
  - `ConnectorShape` を識別
- OOXML drawing:
  - `xdr:sp`, `xdr:cxnSp`, `xdr:graphicFrame` を解析
  - `cNvPr id` と `stCxn/endCxn` を取得

node id と connector 解決のルールは固定する。

1. non-connector shape にだけシート内連番 `id` を振る
2. OOXML `cNvPr.id` と shape 名の両方を保持する
3. connector の begin/end は次の優先順で決める
   - OOXML `stCxn/endCxn` で解決できる場合:
     - `approximation_level="direct"`
     - `confidence=1.0`
   - UNO `StartShape/EndShape` が使える場合:
     - `approximation_level="direct"`
     - `confidence=0.9`
   - どちらも無い場合は幾何推定:
     - `approximation_level="heuristic"`
     - `confidence=0.6`
4. 幾何推定は connector の両端点と shape bbox の距離で nearest shape を選ぶ
5. 候補が見つからない側は `None` のままにする

### 2. chart

`libreoffice` mode の chart は以下の責務分担で組み立てる。

- OOXML / openpyxl:
  - chart 定義を読む
  - `chart_type`, `title`, `series`, `y_axis_title`, `y_axis_range` を構築
  - anchor から近似 geometry を得る
- UNO:
- `sheet.getCharts()` または `DrawPage` の `OLE2Shape` から chart geometry 候補を得る
  - v1 では LibreOffice 同梱 Python bridge subprocess から `sheet.getCharts()` と `DrawPage` の `OLE2Shape` を読む
  - `PersistName` と draw-page 順序を保持して OOXML chart との pairing 候補にする

pairing ルールは次のとおり。

1. OOXML chart の並び順を基準に 1 件ずつ構築する
2. UNO chart / OLE2Shape が同数で取得できる場合は順序で対応付ける
   - まず chart name / `PersistName` の一致を優先する
   - 残差だけを順序 pairing する
3. UNO geometry が無い場合は openpyxl anchor を使う
4. UNO geometry 使用時:
   - `approximation_level="partial"`
   - `confidence=0.8`
5. anchor のみ使用時:
   - `approximation_level="partial"`
   - `confidence=0.5`

## mode ごとの backend 解決

- `light`
  - rich backend 不使用
- `libreoffice`
  - pre-analysis: pandas / openpyxl
  - rich backend: LibreOffice UNO + OOXML
- `standard`
  - pre-analysis: 既存どおり
  - rich backend: Excel COM
- `verbose`
  - pre-analysis / rich backend とも既存どおり COM 前提

## テスト受け入れ条件

- API / CLI / MCP が `mode="libreoffice"` を受け付ける
- 無効 mode は従来どおり早期エラー
- `.xls` を `mode="libreoffice"` で指定すると早期エラー
- `process_excel(...)` / CLI で `mode="libreoffice"` と `pdf` / `image` / `auto_page_breaks_dir` を併用すると早期に `ConfigError` / 非ゼロ終了になる
- `extract_workbook(...)` / `ExStructEngine.extract(...)` で auto page-break を要求した場合も `mode="libreoffice"` では早期エラーになる
- `sample/flowchart/sample-shape-connector.xlsx` で connector の `begin_id/end_id` が十分数復元される
- `sample/basic/sample.xlsx` で chart が 1 件以上返り、title / series / geometry が埋まる
- LibreOffice 不在時は `rows` / `table_candidates` / `print_areas` / `merged_cells` を保った fallback を返す
- `standard` / `verbose` の既存 COM 系テストに回帰を出さない
- `model_dump(exclude_none=True)` により、新 metadata は未設定時に JSON に出ない

## 実装上の前提

- `soffice` と `uno` は optional dependency / 実行環境依存機能として扱う
- v1 では LibreOffice rendering は追加しないため、既存 `render` extra と切り離す
- 既存 sample を優先して回帰テストを作り、新規 fixture 追加は必要最小限にする
