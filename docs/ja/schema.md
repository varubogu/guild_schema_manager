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
- ID 優先を必須とする。
- ファイルに `id` がある場合、同一判定は `id` のみで行う。
- `name` は更新対象データとして扱う。
- `id` がない場合のみ、同一スコープ内 `name` 一致で補助判定する。

## name のみ指定時の挙動
- 一意に一致: 更新対象として扱う。
- 複数一致: 検証エラー。
- 一致なし: 新規作成扱い。

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
- 必須項目（`name`、必要な `type` など）の欠落はエラー。
- 無効な overwrite 参照はエラー。
- 矛盾した親参照（`parent_id` と不一致 `parent_name`）はエラー。
- 同一セクション内の重複明示 ID はエラー。
