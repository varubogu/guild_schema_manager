# アーキテクチャ

## コンポーネント概要
主要ランタイム構成:
- Discord クライアント層 (`discord.py`): Slash コマンドと Interaction を受信。
- コマンドハンドラ: `export`、`diff`、`apply` の実行制御。
- スキーマパーサ/バリデータ: YAML 解析と構造検証。
- スナップショット生成: ギルド状態を正規化スキーマへ変換。
- 差分エンジン: Create/Update/Delete/Move/Reorder を算出。
- 適用プランナ/実行器: 差分を順序付き Discord API 操作へ変換。
- 確認セッションストア（メモリ内）: 短命な適用待ちプランを保持。
- 結果レンダラ: Markdown 要約と添付ファイル出力を生成。

## ソース構造（Cog + UseCase）
- 起動と依存注入: `src/bot/app.py`
- Slash コマンド Cog: `src/bot/commands/cogs/schema_cog.py`
- イベント Cog（`on_ready`）: `src/bot/commands/cogs/events_cog.py`
- Interaction View（実行者限定の確認 UI）: `src/bot/commands/views/*`
- Interaction 実行制御ハンドラ: `src/bot/commands/handlers/schema_handlers.py`
- ローカライズ翻訳器とコマンドメタデータ: `src/bot/commands/translator.py`
- UseCase 層（コマンドの業務ロジック）: `src/bot/usecases/schema/service.py`
- 既存 import 互換の再エクスポート: `src/bot/commands/service.py`

依存方向:
1. Cog / View 層（`commands/*`）は Discord I/O のみを担当する。
2. UseCase 層（`usecases/*`）が export/diff/apply ロジックを実行する。
3. ドメインモジュール（`schema`、`snapshot`、`diff`、`planner`、`executor`、`rendering`、`security`）が純粋処理と実行プリミティブを提供する。

## データフロー
### `/schema export`
1. コマンド実行者がギルド管理者権限を持つか検証。
2. 現在のギルド状態（ロール、カテゴリ、チャンネル、overwrites）を取得。
3. 正規化スキーマモデルへ変換。
4. YAML にシリアライズ。
5. 添付ファイルとして返却。

### `/schema diff file:<attachment>`
1. コマンド実行者がギルド管理者権限を持つか検証。
2. YAML 添付を受領。
3. スキーマ検証。
4. 現在状態のスナップショット生成。
5. 差分計算。
6. Markdown 要約と詳細テーブルを返却。

### `/schema apply file:<attachment>`
1. コマンド実行者がギルド管理者権限を持つか検証。
2. YAML 添付を受領。
3. スキーマ検証。
4. 現在状態との diff を算出。
5. プレビュー + 確認ボタン（実行者限定）を返却。
6. 確認後:
   - 現在状態をバックアップとしてエクスポート。
   - 順序付きで適用実行。
   - 結果レポート（`applied`、`failed`、`skipped`）とバックアップを返却。

## 状態管理
- DB なし、永続ディスク状態なし。
- 適用待ちプランはメモリ内 TTL 管理（既定: 10分）。
- プロセス再起動時に保留プランは失効。
- 受領ファイルと一時生成物はレスポンス処理後に削除。

## エラーハンドリング方針
- 検証エラー: 副作用なしで拒否し、修正可能なエラー情報を返す。
- 認可エラー: 非管理者のコマンド実行を計画作成前に拒否する。
- 権限エラー: 該当操作を停止し、不足権限を明示。
- 適用中の部分失敗: 独立操作はベストエフォートで継続し、操作単位で結果報告。
- 確認タイムアウト: 失効として扱い、`/schema apply` 再実行を要求。

## Discord API 制約への対応
- `discord.py` のレート制御機構を前提にしつつ、操作順序を制御する。
- 部分失敗（対象削除済み、階層衝突、ロール制限）を前提に設計。
- 適用順序:
  1. Roles
  2. Categories
  3. Channels
- 親子依存解決後に並び替えを行う。
