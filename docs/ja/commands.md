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
2. `/schema diff file:<attachment>`
3. `/schema apply file:<attachment>`

## `/schema export`
目的: 現在のギルド構成を YAML で出力する。

入力:
- 添付入力なし。

出力:
- YAML 添付 (`guild-schema.yaml`)。
- 必要に応じて短い Markdown 要約。

必要な Bot 権限:
- `View Channels`
- `Read Message History`
- `Send Messages`
- `Attach Files`
- `Use Application Commands`

## `/schema diff file:<attachment>`
目的: アップロードされたスキーマと現行構成との差分を表示する。

入力:
- YAML 添付 1件。

出力:
- Markdown 要約。
- 差分詳細テーブル（Create/Update/Delete/Move/Reorder）。

挙動:
- 変更は実行しない。
- 不正スキーマ時はフィールドパス付きエラーを返す。

## `/schema apply file:<attachment>`
目的: 確認付きでスキーマ変更を適用する。

入力:
- YAML 添付 1件。

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
