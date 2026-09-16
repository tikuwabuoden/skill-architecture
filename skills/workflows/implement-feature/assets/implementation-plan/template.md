# {{ title }}

## 実現する振る舞い

{{#each behavior}}- {{ this }}
{{#empty}}- なし
{{/each}}
## 対象外

{{#each outOfScope}}- {{ this }}
{{#empty}}- なし
{{/each}}
## 採用する実装方針

{{#each approach}}- {{ this }}
{{#empty}}- なし
{{/each}}
## 機能単位の実装計画

{{#each implementationUnits}}{{#if @index}}
{{/if}}### {{ @number }}. {{ name }}

#### 実現すること

- {{ outcome }}

#### 主な変更

{{#each changes}}- {{ this }}
{{#empty}}- なし
{{/each}}
#### 前提となる単位

{{#each dependsOn}}- {{ this }}
{{#empty}}- なし
{{/each}}
#### 実装後の確認

{{#each verification}}- {{ this }}
{{#empty}}- なし
{{/each}}{{/each}}
## 変更する責務

{{#each responsibilities}}- {{ this }}
{{#empty}}- なし
{{/each}}
## 処理の流れ

{{#if flowDiagram}}```{{ flowDiagram.type }}
{{ flowDiagram.source }}
```
{{#else}}図なし
{{/if}}
## インターフェースまたはデータへの影響

{{#each interfaceImpacts}}- {{ this }}
{{#empty}}- なし
{{/each}}
## 制約への対応

{{#each constraints}}- {{ this }}
{{#empty}}- なし
{{/each}}
## テストと検証方法

{{#each verification}}- {{ this }}
{{#empty}}- なし
{{/each}}
## 未確定事項とリスク

{{#each risks}}- {{ this }}
{{#empty}}- なし
{{/each}}
