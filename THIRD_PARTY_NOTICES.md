# 借用と謝辞（Third-party notices）

## 読みやすさの規則（readability-rules.md）

`.claude/readability-rules.md` の原則は、mathbullet/skills の
**ja-text-communication**（MIT License, Copyright (c) 2026 mathbullet）から
考え方を借用しています。中身（否定側の言い回しリスト）はこのリポジトリで
較正し直したものであり、mathbullet/skills のファイルをそのまま複製したもの
ではありません。

フックが指示文に出す読みやすさの決まり（`.claude/hooks/visual/instructions.py`）と、
否定側の言い回しを数える部品（`.claude/hooks/visual/readability.py`）も、同じ
ja-text-communication の原則（B1・B2・B4・C2・C3・E7）から借用しています。

その MIT ライセンスの全文は次のとおりです。

```
MIT License

Copyright (c) 2026 mathbullet

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 指摘と添削の画面（review_scripts.py・markdown_lite.py）

説明の頁と原稿の頁の「指摘」（段落に札とひとことを付けて返す）と「添削」
（本文を直接書き換え、差分と完成形を返す）の画面は、**akapen 0.2.0**（赤ペン先生。
配布元は YouTube のチャンネル「まさおAIじっくり解説ch」）の
`assets/shiteki/kit-template.html` と `assets/tensaku/template.html` の script と
様式を移植し、この仕組みに合わせて直したものです（回答文の組み立て・固定の頭と脚・
外部のフォントの読み込み・色を差し替えた）。原稿をブロックに分ける規則
（`.claude/hooks/visual/markdown_lite.py`）も、同じ添削の雛形の `parseBlocks` と
同じにしてあります。札の7種と回答文の「## 指摘」「## 添削」の形は akapen の
`references/reply-format.md` に合わせています。

akapen の配布物には、INSTALL.md に「License: MIT」の1行があるだけで、
LICENSE ファイルと著作権者の行はありません。MIT の本文は次のとおりです
（著作権者の欄は配布物に表記が無いため、作品名で示します）。

```
MIT License

Copyright (c) akapen authors (akapen 0.2.0)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## explain-page 本体のライセンス

このリポジトリ自身も MIT License です。作者表記・全文は `LICENSE` を見てください。
