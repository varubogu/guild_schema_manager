# コマンド仕様

## コマンド体系
- Slash コマンドのみ。
- コマンドグループ: `/schema`。

## 実行者要件（全コマンド共通）
- コマンド実行者はギルド `Administrator` 権限を持つ必要がある。
- 非管理者の実行は diff/apply 計画作成前に拒否する。
- この制約は `/schema export`、`/schema diff`、`/schema apply` すべてに適用する。

## 公開インターフェース
1. `/schema export`
2. `/schema diff file:<attachment> file_trust_mode:<bool=false>`
3. `/schema apply file:<attachment> file_trust_mode:<bool=false>`

## `/schema export`
目的: 現在のギルド構成を YAML で出力する。

入力:
- 添付入力なし。
- 任意の boolean パラメータ:
  - `include_name`（既定: `true`）
  - `include_permissions`（既定: `true`）
  - `include_role_overwrites`（既定: `true`）
  - `include_other_settings`（既定: `true`）

フィールド出力ルール:
- `id` は常に出力する。
- `name` は `include_name=true` の場合のみ出力する。
- ロール `permissions` は `include_permissions=true` の場合のみ出力する。
- カテゴリ/チャンネルの role 対象 overwrite は `include_role_overwrites=true` の場合のみ出力する。
- member 対象 overwrite と、それ以外の属性（`type`、`position`、`topic`、`hoist` など）は `include_other_settings=true` の場合のみ出力する。

出力:
- YAML 添付 (`guild-schema.yaml`)。
- 必要に応じて短い Markdown 要約。
- `SCHEMA_REPO_OWNER` と `SCHEMA_REPO_NAME` が設定されている場合は、YAML先頭にスキーマヒントコメントを付与:
  - `# yaml-language-server: $schema=https://<owner>.github.io/<repo>/schema/v<version>/schema.json`
- いずれかの出力オプションを無効化した場合、出力はフィルタ済みビューとなる。`/schema diff` と `/schema apply` では未指定セクション/項目を現状維持として扱う。

必要な Bot 権限:
- `View Channels`

## `/schema diff file:<attachment>`
目的: アップロードされたスキーマと現行構成との差分を表示する。

入力:
- YAML 添付 1件。
- 任意の boolean パラメータ:
  - `file_trust_mode`（既定: `false`）

出力:
- Markdown 要約。
- 差分詳細テーブル（Create/Update/Delete/Move/Reorder）。

挙動:
- 変更は実行しない。
- 不正スキーマ時はフィールドパス付きエラーを返す。
- `file_trust_mode=false`: アップロードを部分パッチとしてマージし、未指定セクション・未指定リソース・未指定フィールドは現状維持とする。
- `file_trust_mode=true`: アップロードを完全スキーマとして扱い、未記載リソースは削除差分になる。

## `/schema apply file:<attachment>`
目的: 確認付きでスキーマ変更を適用する。

入力:
- YAML 添付 1件。
- 任意の boolean パラメータ:
  - `file_trust_mode`（既定: `false`）

フロー:
1. 解析と検証。
2. 差分計算とプレビュー表示。
3. 有効期限付き確認ボタンを表示（既定10分）。
4. 実行者本人のみ確認可能。
5. 確認後にバックアップ作成と適用実行。
6. 最終結果を返却。

出力:
- 確認前: Markdown プレビュー + 確認 UI。
- 確認後: バックアップ添付 + 適用結果レポート。

実行ルール:
- 削除は確認前に実行しない。
- `file_trust_mode=false`: roles/categories/channels を未記載にしても削除差分は生成しない。
- `file_trust_mode=true`: 完全スキーマで未記載のリソースは削除差分を生成する。
- 確認後のチャンネル削除はハード削除せず `GSM-Dustbox` へ移動する。
- カテゴリ削除は子チャンネルを `GSM-Dustbox` へ移動し、カテゴリ本体は手動削除前提でアーカイブする。
- `GSM-Dustbox` がなければ管理者のみ閲覧可能な権限で自動作成する。
- ロール削除は Bot がハード削除せず、手動削除対象として報告する。
- 有効期限切れ時はタイムアウトとして再実行を要求。
- 差分なしの場合は no-op 要約を返す。

## レスポンス契約
- Diff モデル:
  - `summary`
  - `changes[]` (`action`, `target_type`, `target_id`, `before`, `after`, `risk`)
- Apply モデル:
  - `backup_file`
  - `applied[]`
  - `failed[]`
  - `skipped[]`
