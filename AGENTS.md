# Skill architecture

Skillを追加または変更する前に、`ARCHITECTURE.md`を最後まで読み、その設計に従う。

- Skillの責務からWorkflow、Capability、Adapterのいずれか1つを選び、対応するディレクトリへ配置する。
- 他のSkillを名前で参照する場合は、実装前に依存方向が`ARCHITECTURE.md`で許可されているか確認する。
- CapabilityからAdapterへ依存させる場合は、`ARCHITECTURE.md`にある4条件をすべて満たすことを確認する。満たさない場合はWorkflowで組み合わせる。
- Skillの実行順、停止条件、結果の受け渡しなどのオーケストレーションはWorkflowに置く。
- 変更後は、追加したSkill参照を確認し、禁止された依存や循環依存がないことを検査する。
- ユーザーの要求がアーキテクチャと矛盾する場合は、独断で設計を変更せず、矛盾点を伝えて判断を求める。

# Commit convention

コミットメッセージとPRタイトルは[policy/NAMING.md](policy/NAMING.md)に従う。利用先固有のscope許可条件、意味判断が必要なscopeの選び方、ブランチ名、issue参照も同文書で確認する。

1コミットには1つの論理的な変更だけを含める。
