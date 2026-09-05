---
name: implement-feature
description: 既存のソフトウェアリポジトリへ機能を追加または変更し、要求の具体化から実装、検証、結果報告まで完了する。コード変更まで求められる機能開発で使う。調査、計画、レビューだけの依頼や、コミット、PR、デプロイには使わない。
---

# Implement Feature

ユーザーが求める振る舞いを、既存リポジトリの規約と構造に沿って実装し、確認可能な状態まで進める。

## Capabilities

次のCapabilityを利用可能なSkill一覧から読み込み、各Capabilityの指示に従う。

- `analyze-codebase`
- `assess-change-impact`
- `plan-code-change`
- `implement-code-change`
- `verify-code-change`

Capabilityの責務をこのWorkflow内で重複して定義しない。必要なCapabilityが利用できない場合は、不足しているSkillを報告して停止する。

## Workflow

1. 依頼から、実装後に満たす振る舞いと対象外を明確にする。結果を大きく変える判断だけをユーザーへ確認する。
2. `analyze-codebase`を使い、現在の処理、責務、制約、関連テストを把握する。
3. `assess-change-impact`を使い、要求された変更の波及範囲、互換性、必要な対応を確認する。
4. `plan-code-change`を使い、要求、現状調査、影響評価から実装方針と検証方法を決める。
5. `implement-code-change`を使い、計画に沿って一貫した変更を実装する。
6. `verify-code-change`を使い、実装結果を検証する。範囲内の修正で解決できる問題は、検証結果を`implement-code-change`へ渡して修正し、再検証する。新しい要求判断や範囲拡大が必要ならユーザーへ確認する。
7. 各Capabilityの結果を統合し、実装結果と検証結果を報告する。

## Boundaries

- 診断のみ、計画のみ、レビューのみを求められた場合は、それぞれの依頼範囲を越えて実装しない。
- コミット、push、PR作成、デプロイ、リリースは、ユーザーが明示的に依頼した場合だけ行う。
- リポジトリにある未コミットの変更はユーザーの作業として扱い、上書きまたは破棄しない。
- 要求を満たすために公開インターフェースや保存データの互換性を壊す必要が生じた場合は、実装前に確認する。

## Completion

完了時は、次を簡潔に示す。

- 実現した振る舞い
- 主な変更箇所
- 実行した検証と結果
- 未検証事項または残存リスク
