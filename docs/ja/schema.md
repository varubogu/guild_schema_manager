# スキーマ仕様

## ファイル形式
- 単一 YAML ファイル。
- 論理セクション:
  - `version`
  - `guild`
  - `roles`
  - `categories`
  - `channels`

## トップレベル例
```yaml
version: 1
guild:
  id: "123456789012345678"
  name: "Example Guild"

roles:
  - id: "223456789012345678"
    name: "Moderators"
    bot_managed: false
    color: 3447003
    hoist: true
    mentionable: false
    permissions:
      - manage_channels
      - mute_members

categories:
  - id: "323456789012345678"
    name: "Information"
    position: 0
    overwrites:
      - target:
          type: role
          id: "223456789012345678"
        allow: [view_channel]
        deny: []

channels:
  - id: "423456789012345678"
    name: "announcements"
    type: text
    parent_id: "323456789012345678"
    position: 0
    topic: "Official updates"
    nsfw: false
    slowmode_delay: 0
    overwrites: []
```

## 同一判定ルール
- 既定は ID 優先で同一判定する。
- 既定モードでは、ファイルに `id` がある場合は `id` で同一判定する。
- アップロード内 `guild.id` が現在ギルドと不一致で、ユーザーが明示的に続行した場合のみ、roles/categories/channels の同一判定は name 優先に切り替える。
- name 優先モードでは、一意な name 一致が見つからず `id` がある場合に限り `id` をフォールバック利用する。
- channels の name ベース一致では、name に加えて親カテゴリスコープとチャンネル種別も照合する。
- 同一親スコープ・同一種別・同一nameで重複する場合は、決定的な内部一時順序で区別して照合する。
- `name` は更新対象データとして扱う。
- `id` がない場合のみ、同一スコープ内 `name` 一致で補助判定する。

## name のみ指定時の挙動
- 一意に一致: 更新対象として扱う。
- 複数一致:
  - `/schema diff` と `/schema apply`: 比較を継続し、曖昧な項目は未一致の差異として扱う。
- 一致なし: 新規作成扱い。

## ロールの Bot 管理フラグ
- `roles[].bot_managed` は任意の boolean（既定: `false`）。
- `export` は Discord role tag `bot_id` を持つロールを `bot_managed: true` で出力する。
- `bot_managed: true` のロール差分は `/schema diff` と `/schema apply` プレビューに通常どおり表示する。
- `/schema apply` では `bot_managed: true` のロール `Create`/`Update`/`Delete`/`Reorder` は実行対象外とし、`skipped[]` に理由 `bot_managed_role` で記録する。
- `/schema apply` では、ロール `Create` の要求 `position` が Bot のトップロール位置以上の場合、`bot top role position - 1` へクランプして実行する。
- `/schema apply` では、Bot のトップロール位置以上のロールを対象とする `Update`/`Reorder` は実行対象外とし、`skipped[]` に理由 `role_hierarchy_restriction` で記録する。
- ロール操作で発生した階層制約由来の `discord.Forbidden` は、理由 `role_hierarchy_restriction` のスキップとして扱う。
- `/schema diff` 出力と `/schema apply` プレビューは、実行時に除外見込みの操作を `適用時スキップ理由` 列に表示する。
- `/schema diff` 出力と `/schema apply` プレビューは、`current_server` / `config_file` / `applied`（および対応する `*_name`）列で、現在状態・構成ファイル意図・適用後状態を分離表示する。

## 入力モードの挙動（`/schema diff`、`/schema apply`）
- `file_trust_mode=false`（既定）: アップロードを部分パッチとしてマージする。
- パッチモードでは未指定セクション（`roles`、`categories`、`channels`）と未指定フィールドは現状維持。
- パッチモードではセクション内の未記載リソースも現状維持（未記載による削除はしない）。
- `file_trust_mode=true`: アップロードを完全スキーマ（source-of-truth）として解析する。
- 信頼モードでは未記載リソースを削除意図として差分化する。
- `/schema diff` では YAML の構造と対応済みキー/種別を検証したうえで、一致判定が曖昧でも可能な範囲で比較を継続する。

## 管理対象
- Roles。
- Categories。
- 実行中 `discord.py` バージョンが扱える Guild channel 種別。
- カテゴリ/チャンネルの permission overwrites。

## チャンネル種別ポリシー
- 実装は、実行中 `discord.py` が作成・管理可能な Guild channel 種別を対象とする。
- 未対応または未知の `type` 値は diff/apply 前の検証でエラーとする。

## 順序と依存関係
適用プランは以下を厳守:
1. Roles
2. Categories
3. Channels
4. 親カテゴリの割り当てを先に解決
5. 依存解決後に並び替え操作

## 検証ルール
- 未知のトップレベルキーはエラー。
- 必須項目（`name`、必要な `type` など）の欠落は、完全スキーマ解析・信頼モード・パッチモードの作成対象でエラー。
- 無効な overwrite 参照はエラー。
- 矛盾した親参照（`parent_id` と不一致 `parent_name`）はエラー。
- 同一セクション内の重複明示 ID はエラー。

## 公開 JSON Schema
- バージョン固定パス: `/schema/v1/schema.json`
- 最新エイリアス: `/schema/latest/schema.json`
- 推奨 YAML ヘッダー:
  - `# yaml-language-server: $schema=https://example.com/schema/v1/schema.json`
- 重複明示 ID や overwrite 参照先存在チェックなどの相互参照制約は、引き続き Bot の実行時検証でも判定する。
