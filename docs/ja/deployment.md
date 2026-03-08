# デプロイ

## 採用技術
- Python
- `discord.py`
- `uv`
- `ruff`
- `pytest`
- Docker（本番実行）

## 環境変数
最小実行変数:
- `DISCORD_TOKEN`: Bot トークン
- `APPLICATION_ID`: Discord Application ID
- `LOG_LEVEL`: 任意（既定 `INFO`）
- `CONFIRM_TTL_SECONDS`: 任意（既定 `600`）
- `SCHEMA_REPO_OWNER`: 任意。`/schema export` のスキーマヒントURLに使うGitHub owner
- `SCHEMA_REPO_NAME`: 任意。`/schema export` のスキーマヒントURLに使うリポジトリ名

`SCHEMA_REPO_OWNER` と `SCHEMA_REPO_NAME` の両方を設定すると、exportしたYAML先頭に次を付与:
- `# yaml-language-server: $schema=https://<owner>.github.io/<repo>/schema/v<version>/schema.json`

## ローカル開発
想定フロー:
1. `uv` をインストール。
2. 依存を同期。
3. `ruff` でフォーマットとチェックを実行。
4. 環境変数を設定して Bot を起動。
5. `pytest` を実行。

例:
```bash
uv sync
uv run ruff format
uv run ruff check
uv run python -m bot
uv run pytest
```

## 開発ドキュメント作成ルール
- 実装提案・実装計画ドキュメントは、次の固定構成で記述することを必須とする。
  1. `概要`
  2. `実装変更`
  3. `テスト計画`
  4. `前提・デフォルト`
- このルールは、`plans/` 配下を含む実装計画ドキュメント全体に適用する。

## Docker 本番運用
コンテナ要件:
- 非 root ユーザーで実行。
- 可能な範囲で read-only root filesystem。
- 添付処理用の短命 temp 書き込み領域。
- シークレットは環境変数注入で管理。

想定エントリポイント:
```bash
python -m bot
```

起動例:
```bash
docker run --rm \
  -e DISCORD_TOKEN=*** \
  -e APPLICATION_ID=*** \
  -e LOG_LEVEL=INFO \
  -e SCHEMA_REPO_OWNER=your-org \
  -e SCHEMA_REPO_NAME=guild_schema_manager \
  discord-schema-manager:latest
```

## 招待 URL 方針
スコープ:
- `bot`
- `applications.commands`

権限は `permissions-and-security.md` の最小セットのみ付与。

## 必要時のみ招待する運用
推奨手順:
1. 最小権限付き招待 URL を生成。
2. 対象ギルドに Bot を招待。
3. export/diff/apply を実施。
4. 作業完了後に Bot を退出。

## 本番運用メモ
- コマンド失敗率とレート制限警告を監視。
- トークン漏えい疑い時は即時ローテーション。
- `discord.py` 更新時に対応チャンネル種別を再検証。
