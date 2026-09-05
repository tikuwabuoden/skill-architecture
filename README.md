# skill-architecture

複数のCodex Skillを、責務と依存関係に基づいて組み合わせるためのアーキテクチャを設計・検証するリポジトリです。

## Architecture

Skillを次の3種類に分けます。

- **Workflow**: 複数のSkillを組み合わせ、ユースケース全体を進める
- **Capability**: 調査、変換、生成、検証などの再利用可能な能力を提供する
- **Adapter**: 外部ツールやサービスなど、具体的な技術との接続を扱う

詳しい責務と依存ルールは [ARCHITECTURE.md](ARCHITECTURE.md) を参照してください。

## Repository structure

```text
.
|-- README.md
|-- ARCHITECTURE.md
`-- skills/
    |-- workflows/
    |   `-- implement-feature/
    |       `-- SKILL.md
    |-- capabilities/
    |   |-- analyze-codebase/
    |   |-- assess-change-impact/
    |   |-- implement-code-change/
    |   |-- plan-code-change/
    |   `-- verify-code-change/
    `-- adapters/
```

最初の試作として、既存リポジトリへの機能追加を進める `implement-feature` Workflowと、そこから利用する5つのCapabilityを収録しています。
