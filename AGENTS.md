# Skill architecture

Skillを追加または変更する前に、`ARCHITECTURE.md`を最後まで読み、その設計に従う。

- Skillの責務からWorkflow、Capability、Adapterのいずれか1つを選び、対応するディレクトリへ配置する。
- 他のSkillを名前で参照する場合は、実装前に依存方向が`ARCHITECTURE.md`で許可されているか確認する。
- CapabilityからAdapterへ依存させる場合は、`ARCHITECTURE.md`にある4条件をすべて満たすことを確認する。満たさない場合はWorkflowで組み合わせる。
- Skillの実行順、停止条件、結果の受け渡しなどのオーケストレーションはWorkflowに置く。
- 変更後は、追加したSkill参照を確認し、禁止された依存や循環依存がないことを検査する。
- ユーザーの要求がアーキテクチャと矛盾する場合は、独断で設計を変更せず、矛盾点を伝えて判断を求める。

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
