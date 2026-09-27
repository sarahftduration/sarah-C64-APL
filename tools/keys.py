"""Keyboard entry: PETSCII from the KERNAL's GETIN to our character codes, and the digraph table.

An unshifted letter arrives as $41-$5A and a shifted one as $C1-$DA; in our charset those are
lower and upper case. The pound key ($5C) is the digraph prefix; the left-arrow key ($5F) types
the APL assignment arrow directly. After the prefix, the next key (as translated to our code)
is looked up here; the positions follow the standard APL keyboard where the C64 has the key.
"""

RETURN, DEL, CLR, UP, PREFIX, LARROW = 0x0D, 0x14, 0x93, 0x91, 0x5C, 0x5F
LEFT_ARROW_GLYPH = 0x91          # our code for ←

# translated second key (our code) -> our code typed
DIGRAPHS = {
    ord('i'): 0x8A,              # ⍳
    ord('r'): 0x8B,              # ⍴
    ord('-'): 0x82,              # ×
    ord('='): 0x83,              # ÷
    ord('8'): 0x85,              # ≠
    ord('4'): 0x87,              # ≤
    ord('<'): 0x87,              # ≤
    ord('6'): 0x89,              # ≥
    ord('>'): 0x89,              # ≥
    ord('2'): 0x90,              # ¯
    ord('1'): 0xC2,              # ¨
    ord('0'): 0xC5,              # ⍤
    ord('j'): 0xC4,              # ∘
    ord("'"): 0x94,              # ⍬
    ord('['): 0x91,              # ←
    ord(']'): 0x92,              # →
    ord('.'): 0x93,              # ⋄
    ord(','): 0x95,              # ⍝
    ord('h'): 0x96,              # ∆
    ord('H'): 0x97,              # ⍙
    ord('g'): 0x98,              # ∇
    ord('s'): 0x8D,              # ⌈
    ord('d'): 0x8E,              # ⌊
    ord('l'): 0x7C,              # |
    ord('w'): 0x99,              # ∧
    ord('v'): 0x9A,              # ∨
    ord('n'): 0x7E,              # ~
    ord('a'): 0x9B,              # ⌽
    ord('y'): 0x9C,              # ↑
    ord('u'): 0x9D,              # ↓
    ord('e'): 0x9E,              # ∊
    ord('7'): 0x9F,              # ⍋
    ord('3'): 0xA0,              # ⍒
    ord('t'): 0xA1,              # ⍉
    ord('*'): 0xA2,              # ⍟
    ord('o'): 0xA3,              # ○
    ord('L'): 0xA4,              # ⎕
    ord('A'): 0xA5,              # ⊖ (shift of 'a'->⌽: the axis-1 form of the same key)
    ord('/'): 0xA6,              # ⌿ (axis-1 reduce/scan: the '/' key, like the glyph itself)
    ord('?'): 0xA7,              # ⍀ (axis-1 scan/expand: shift of the same key as ⌿)
    ord('b'): 0xA8,              # ⊥ (base value / decode)
    ord('B'): 0xA9,              # ⊤ (encode: ⊤ is ⊥ upside down, so the shift of the same key)
    LEFT_ARROW_GLYPH: 0x5F,      # the ← key again: underscore
    PREFIX: 0x5C,                # the prefix twice: backslash
}


def translate(petscii):
    """PETSCII -> our code, or None if the key does nothing when typed."""
    if 0x20 <= petscii <= 0x40:
        return petscii
    if 0x41 <= petscii <= 0x5A:
        return petscii | 0x20
    if petscii in (0x5B, 0x5D, 0x5E):
        return petscii
    if petscii == LARROW:
        return LEFT_ARROW_GLYPH
    if 0xC1 <= petscii <= 0xDA:
        return petscii - 0x80
    return None
