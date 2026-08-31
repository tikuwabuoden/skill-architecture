# Commit convention

コミットメッセージは Conventional Commits 形式にする。

```text
<type>(<scope>): <summary>
```

## Types

- `feat`: 機能の追加または変更
- `fix`: 不具合の修正
- `docs`: ドキュメントのみの変更
- `refactor`: 振る舞いを変えない内部構造の変更
- `test`: テストの追加または変更
- `chore`: 上記に該当しない保守作業

## Scope

- 単一のSkillを変更する場合は、Skillディレクトリ名をそのまま`scope`に使う。
- 新しいSkillを追加する場合も、そのSkill名を`scope`に使う。
- 複数のSkillにまたがる変更では`scope`を省略する。
- READMEやアーキテクチャなど、リポジトリ全体の文書変更では`scope`を省略する。
- `workflow`、`capability`、`adapter`などの分類名を`scope`に使わない。
- 適切な`scope`を一意に決められない場合は省略する。
- 定義されていない`scope`体系を推測で追加しない。

## Rules

- `summary` は変更内容を簡潔に表し、文末に句点を付けない。
- 1コミットには1つの論理的な変更だけを含める。
- 後方互換性を壊す変更は、typeまたはscopeの後に `!` を付ける。

```text
feat(implement-feature): 機能実装フローを追加
fix(analyze-codebase): 影響範囲の判定を修正
feat: 複数Skillの連携方法を追加
docs: アーキテクチャの依存方向を明確化
```
