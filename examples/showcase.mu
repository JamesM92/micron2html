#!bg=111
#!fg=ccc

`c`F4af◆━━━━━━━━━━━━━━━━━━━━━━━━━━━◆`f
`c`F4af`! Micron2HTML feature showcase `!`f
`c`F4af◆━━━━━━━━━━━━━━━━━━━━━━━━━━━◆`f

`l

>Headings

>>Sub-section

>>>Sub-sub-section

-=

>Inline formatting

`!Bold`! and `*italic`* and `_underlined`_ text.

`F4af Foreground colour `f and `Bf40 background colour `b in 3-hex shorthand.

`Faaa Dim grey `f text used for muted secondary content.

-~

>Alignment

`c Centred line.
`r Right-aligned line.
`l Back to left-aligned.

-~

>Dividers

Single rule:
---

Double rule:
-=

Wave divider:
-~

Asterisk row:
-*

-~

>Links

External: `[Reticulum`https://reticulum.network]
Node link: `[About this node`/about.mu]
URL only: `[`https://example.com]

-~

>Anchors

`[Jump to the anchor below`#custom-anchor]
`[Jump to the next heading`#]

`:custom-anchor
This paragraph is a jump target declared with an explicit anchor tag.

Every heading (including this one) is also an anchor automatically — its
slug is derived from the heading text.

-~

>Literal block

`=
  Verbatim content — Micron tokens are NOT processed inside.
  `!this stays literal`!
  `F40this colour token also stays as text`f
`=

-~

>Tables

`t
| Name | Price | Qty |
| ---- | :---: | --: |
| `F3a3Apple`f | Free | `!5`! |
| Orange | Ask, nicely | 3 |
`t

-~

>Form fields

  Username:    `<20|username`>
  Password:    `<20!|password`>
  Subscribe:   `<?|subscribe|yes|*`Yes, sign me up>
  Plan:        `<^|plan|free|*`Free>  `<^|plan|pro`Pro>

-=

`c`Faaa Generated with `[Micron2HTML`https://github.com/JamesM92/Micron2HTML]
