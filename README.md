# ハッカソン モニタリングダッシュボード

Devin Enterprise API から Org 別のハッカソン進行状況（ACU 利用量 / PR 作成・マージ / マージ率）を
収集し、1時間バケットの時系列と Org ランキングをブラウザに表示する自己完結型ダッシュボード。

- 依存パッケージなし（Python 3.10+ 標準ライブラリのみ、Chart.js は `static/` に同梱）
- 収集した値は SQLite に蓄積されるため、再起動しても履歴は失われない

## 使い方

```bash
export DEVIN_ENTERPRISE_API_KEY=...          # enterprise 管理者 API キー
export DEVIN_API_BASE=https://aiau.devinenterprise.com/api
export HACKATHON_START="2026-08-14 12:00"    # JST。省略時は最初のデータ時刻
export HACKATHON_END="2026-08-15 18:00"      # JST。残り時間と着地予測に使用
python3 server.py                            # http://localhost:8787
```

| 環境変数 | 既定値 | 説明 |
| --- | --- | --- |
| `DEVIN_ENTERPRISE_API_KEY` | （必須） | enterprise 管理者 API キー |
| `DEVIN_API_BASE` | `https://aiau.devinenterprise.com/api` | API ベース URL |
| `PORT` | `8787` | HTTP ポート |
| `POLL_INTERVAL` | `60` | API ポーリング間隔（秒） |
| `ORG_REFRESH_INTERVAL` | `600` | Org 一覧・ユーザー数の再取得間隔（秒） |
| `DASHBOARD_DB` | `dashboard.db` | SQLite ファイル |
| `HACKATHON_START` / `HACKATHON_END` | なし | JST の ISO 日時または UNIX 秒 |
| `MAX_HOURS` | `72` | グラフに表示する直近バケット数 |

## 表示内容

全体: 総 ACU / PR 作成・マージ / マージ率 / 直近1時間の ACU / 着地予測 / セッション数（稼働中・エラー）/
参加 Org 数 / アクティブユーザーと参加率 / マージ PR あたり ACU、および ACU・PR マージ数・マージ率の
「1時間ごと + 累積」グラフと Org 別累積 ACU の積み上げ。

Org 別（ACU 降順）: 順位・Org 名・ユーザー数（稼働ユーザー数）・ACU・ACU/人・セッション数・PR 作成・
PR マージ・マージ率・ACU スパークライン・最終活動時刻。加えて Org×時間の ACU ヒートマップ、
未着手 Org のハイライト、直近セッションのライブフィード、セッション状態と Devin モードの分布。

## データソースと集計方法

`GET /v3/enterprise/sessions`（org_id / acus_consumed / pull_requests / created_at）を全件取得し、
`GET /v3/enterprise/organizations` と `/members/users` で Org 名とユーザー数を補う。

ACU はセッション単位の累積値、PR には発生時刻が無いため、時系列はポーリング間の差分で構築する。

- 初回検出したセッションの ACU は `created_at` の時間バケットに計上（初回起動時の履歴バックフィル）
- 以降の ACU 増分は観測した時刻のバケットに計上
- PR は初回観測時、マージは `merged` 状態を初めて観測した時刻のバケットに計上

したがって起動前の履歴はセッション作成時刻ベースの近似、起動後は観測ベースの実測となる。

## 検証

```bash
python3 -m pyflakes *.py     # 静的チェック
python3 selftest.py          # インメモリ SQLite で収集・集計ロジックを検証
```
