# Guild Schema Manager

Discord サーバー構成を YAML ファイルで管理する Bot です。変更は必ず明示確認後にのみ実行します。

## できること
1. 現在のギルド構成を YAML として出力 (`/schema export`)。
2. アップロードした YAML と現行構成の差分表示 (`/schema diff file:<attachment>`)。
3. 差分プレビュー後、実行者本人の確認で適用 (`/schema apply file:<attachment>`)。

管理対象:
- ロール
- カテゴリ
- チャンネル
- カテゴリ/チャンネルの権限

## セーフティモデル（常時適用）
- DB は使用しない。
- サーバー側にスキーマを永続保存しない。
- Bot に `Administrator` 権限を付与しない。
- `/schema` コマンドはギルド管理者のみ実行可能。
- apply は必ず `preview -> confirmation -> backup -> execute -> report` の順。
- 確認操作は実行者本人のみ可能。
- apply 実行前にフルバックアップ export を必須化。

apply 時の削除挙動:
- チャンネル削除は `GSM-Dustbox` への移動に変換。
- カテゴリ削除は子チャンネルを `GSM-Dustbox` へ移動し、カテゴリ本体は手動整理前提でアーカイブ。
- ロール削除は Bot がハード削除せず、手動削除対象として報告。

## クイックスタート（ローカル）
前提:
- Python `3.11+`
- `uv`

1. 依存を同期。
```bash
uv sync
```

2. 環境変数ファイルを作成。
```bash
cp .env.example .env
```

3. `.env` に必須値を設定。
- `DISCORD_TOKEN`（必須）
- `APPLICATION_ID`（必須）
- `LOG_LEVEL`（任意、既定 `INFO`）
- `CONFIRM_TTL_SECONDS`（任意、既定 `600`）
- `SCHEMA_REPO_OWNER`（任意）
- `SCHEMA_REPO_NAME`（任意）

4. Bot を起動。
```bash
uv run python -m bot
```

5. ギルド内で Slash コマンドを実行。
- `/schema export`: 現在のギルド構成を `guild-schema.yaml` として出力（ベースライン/バックアップ用途）。
- `/schema diff file:<attachment>`: アップロードした YAML を検証し、Create/Update/Delete/Move/Reorder の差分を表示（変更は実行しない）。
- `/schema apply file:<attachment>`: 差分プレビュー表示後に実行者本人確認を要求し、フルバックアップ取得のうえで実行し、`applied[]` / `failed[]` / `skipped[]` を返す。
- 詳細なコマンド契約: `docs/ja/commands.md`

## Discord 初期設定チェックリスト
1. Discord Application と Bot User を作成。
2. スコープを有効化。
- `bot`
- `applications.commands`
3. Bot 権限は最小限のみ付与。
- `Manage Roles`
- `Manage Channels`
- `View Channels`
- `Send Messages`
- `Attach Files`
- `Read Message History`
- `Use Application Commands`

## 初回の実運用フロー
1. `/schema export` を実行し `guild-schema.yaml` を取得。
2. YAML を編集（ロール/カテゴリ/チャンネル/overwrite）。
3. `/schema diff file:<edited yaml>` を実行して差分とリスク表示を確認。
4. `/schema apply file:<edited yaml>` を実行。
5. 同じ実行者が TTL 内（既定10分）に確認ボタンを押す。
6. 最終レポートの以下を確認。
- `applied[]`
- `failed[]`
- `skipped[]`
7. 返却された `guild-schema-backup.yaml` をロールバック基準として保管。

## 最小 YAML 形
```yaml
version: 1
guild:
  id: "123456789012345678"
  name: "Example Guild"
roles: []
categories: []
channels: []
```

未知キーや未対応チャンネル種別は検証エラーになります。

## 開発コマンド
テスト:
```bash
uv run pytest
```

型チェック、フォーマット、Lint:
```bash
uv run pyright
uv run ruff format
uv run ruff check
```

## ドキュメント索引
- ドキュメント（英語）: `docs/en/*`
- ドキュメント（日本語）: `docs/ja/*`
- 主要ドキュメント:
  - `docs/ja/README.md`
  - `docs/ja/commands.md`
  - `docs/ja/schema.md`
  - `docs/ja/diff-and-apply.md`
  - `docs/ja/permissions-and-security.md`
  - `docs/ja/deployment.md`
