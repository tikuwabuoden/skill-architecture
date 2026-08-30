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
```

現在はアーキテクチャの基盤のみを定義しており、具体的なSkillはまだ実装していません。
