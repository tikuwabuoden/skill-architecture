# Template and Schema Syntax

`render_markdown.py`は、外部パッケージを使わず、ここに示すJSON Schemaのサブセットとテンプレート構文を処理する。未対応のスキーマキーワードやテンプレートタグはエラーにする。

## JSON Schema

次のキーワードを使用できる。

- 注釈: `$schema`、`title`、`description`
- 型と値: `type`、`const`、`enum`、`anyOf`
- オブジェクト: `properties`、`required`、`additionalProperties`
- 配列: `items`、`minItems`
- 文字列: `minLength`、`pattern`

`type`は`object`、`array`、`string`、`integer`、`number`、`boolean`、`null`のいずれか1つを指定する。厳密な入力契約が必要なオブジェクトでは、全項目を`required`へ列挙し、`additionalProperties`を`false`にする。

Markdownの構造を壊し得る改行やコードフェンスなどは、データが挿入される位置に応じて呼び出し元のスキーマの`pattern`で禁止する。レンダラーは用途を知らないため、内容固有の制約を補わない。

## Template

テンプレートはUTF-8のMarkdownとし、次のタグを使用できる。パスは現在のオブジェクトを基準とし、`.`で子要素へ移動する。

値を挿入する:

```text
{{ title }}
{{ diagram.source }}
```

配列を順番どおり繰り返す。空配列の場合だけ`#empty`側を出力する。繰り返し内では`this`が現在の要素、`@index`が0始まり、`@number`が1始まりの番号を表す。

```text
{{#each items}}- {{ @number }}. {{ this }}
{{#empty}}- なし
{{/each}}
```

値が真として評価される場合と、それ以外を分岐する。`null`の有無による分岐にも使用できる。

````text
{{#if diagram}}```{{ diagram.type }}
{{ diagram.source }}
```
{{#else}}図なし
{{/if}}
````

`#each`と`#if`は入れ子にできる。値のタグには文字列、数値、真偽値だけを指定でき、配列、オブジェクト、`null`を直接挿入するとエラーになる。生成結果はUTF-8、LF改行、末尾改行1つに正規化する。
