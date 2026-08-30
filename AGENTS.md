# Commit convention

コミットメッセージは Conventional Commits 形式にする。

```text
<type>(<scope>): <summary>
```

`scope` は変更対象が明確になる場合だけ付ける。

## Types

- `feat`: 機能の追加または変更
- `fix`: 不具合の修正
- `docs`: ドキュメントのみの変更
- `refactor`: 振る舞いを変えない内部構造の変更
- `test`: テストの追加または変更
- `chore`: 上記に該当しない保守作業

## Rules

- `summary` は変更内容を簡潔に表し、文末に句点を付けない。
- 1コミットには1つの論理的な変更だけを含める。
- 後方互換性を壊す変更は、typeまたはscopeの後に `!` を付ける。

```text
feat(workflow): 調査フローを追加
docs: アーキテクチャの依存方向を明確化
feat(adapter)!: 外部ツール接続方式を変更
```
