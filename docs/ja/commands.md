# コマンド仕様

## コマンド体系
- Slash コマンドのみ。
- コマンドグループ: `/schema`。

## 実行者要件（全コマンド共通）
- コマンド実行者はギルド `Administrator` 権限を持つ必要がある。
- 非管理者の実行は diff/apply 計画作成前に拒否する。
- この制約は `/schema export`、`/schema diff`、`/schema apply` すべてに適用する。

## レスポンス言語
- ユーザー向けメッセージは実行者ロケールに応じて表示する。
- ユーザーロケールが日本語（`ja`）の場合は日本語で表示する。
- 日本語以外のロケールはすべて英語（`en`）として扱う。
- ローカライズ対象は、コマンド説明、ボタンラベル、確認プロンプト、エラーメッセージ、diff/apply の Markdown 見出しと状態名。

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
- YAML 添付 (`{guild.name}-{yyyyMMdd_HHmmss}.yaml`)。
- 必要に応じて短い Markdown 要約。
- `SCHEMA_HINT_URL_TEMPLATE` が設定されている場合は、YAML先頭にスキーマヒントコメントを付与:
  - `# yaml-language-server: $schema=<解決後URL>`
  - `SCHEMA_HINT_URL_TEMPLATE` 内の `{version}` はスキーマバージョンに置換される。
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
- Markdown 要約（短い場合は本文表示）。
- 詳細差分を含むダウンロード用ファイル（`{guild.name}-{yyyyMMdd_HHmmss}_diff.md`）。

挙動:
- 変更は実行しない。
- スキーマ構造上の不正（未知キー、未対応チャンネル種別など）はフィールドパス付きエラーを返す。
- name 一致が曖昧な場合は差異として扱い、比較を継続する。
- channels の name 一致は親カテゴリスコープ + チャンネル種別 + name で照合し、それでも曖昧な場合は決定的な内部一時順序で区別する。
- `file_trust_mode=false`: アップロードを部分パッチとしてマージし、未指定セクション・未指定リソース・未指定フィールドは現状維持とする。
- `file_trust_mode=false`: guild に存在しアップロードで未定義のリソースは `変更なし（ファイル未定義）` として表示する。
- guild とアップロードの両方で定義され、完全一致するリソースは `変更なし（完全一致）` として表示する。
- `file_trust_mode=true`: アップロードを完全スキーマとして扱い、未記載リソースは削除差分になる。
- アップロード内の `guild.id` が定義されていて現在ギルドIDと異なる場合、続行前に現在ギルドIDへ上書きするか確認する。
- この確認がキャンセルまたはタイムアウトした場合、コマンドは中止する。

## `/schema apply file:<attachment>`
目的: 確認付きでスキーマ変更を適用する。

入力:
- YAML 添付 1件。
- 任意の boolean パラメータ:
  - `file_trust_mode`（既定: `false`）

フロー:
1. アップロードファイルを読み取り、`guild.id` 不一致を確認。
2. 不一致時は `guild.id` を現在ギルドIDへ上書きするか確認。
3. 解析と検証。
4. 差分計算とプレビュー表示。
5. 有効期限付き確認ボタンを表示（既定10分）。
6. 実行者本人のみ確認可能。
7. 確認後にバックアップ作成と適用実行。
8. 最終結果を返却。

出力:
- 確認前: Markdown プレビュー（短い場合は本文表示）+ プレビュー添付ファイル（`{guild.name}-{yyyyMMdd_HHmmss}_apply.md`） + 確認 UI。
- 確認後: バックアップ添付 + 適用結果レポート添付ファイル（`{guild.name}-{yyyyMMdd_HHmmss}_apply.md`）。

実行ルール:
- 削除は確認前に実行しない。
- `file_trust_mode=false`: roles/categories/channels を未記載にしても削除差分は生成しない。
- `file_trust_mode=true`: 完全スキーマで未記載のリソースは削除差分を生成する。
- アップロード内 `guild.id` の不一致確認がキャンセルまたはタイムアウトした場合、apply は続行しない。
- アップロード内 `guild.id` の不一致確認を承認した場合、そのリクエストの roles/categories/channels 同一判定は name 優先で処理し、ID へのフォールバックは行わない。
- 確認後のチャンネル削除はハード削除せず `GSM-Dustbox` へ移動する。
- カテゴリ削除は子チャンネルを `GSM-Dustbox` へ移動し、カテゴリ本体は手動削除前提でアーカイブする。
- `GSM-Dustbox` がなければ管理者のみ閲覧可能な権限で自動作成する。
- ロール削除は Bot がハード削除せず、手動削除対象として報告する。
- 有効期限切れ時はタイムアウトとして再実行を要求。
- 差分なしの場合は no-op 要約を返す。

## レスポンス契約
- Diff モデル:
  - `summary`
  - `changes[]` (`action`, `target_type`, `target_id`, `before_name`, `after_name`, `before`, `after`, `risk`)
  - `informational_changes[]` (`action`, `target_type`, `target_id`, `before_name`, `after_name`, `before`, `after`)
- Apply モデル:
  - `backup_file`
  - `applied[]`
  - `failed[]`
  - `skipped[]`
