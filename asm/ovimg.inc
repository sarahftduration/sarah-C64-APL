; The overlay images, after everything else in the PRG (included last by eval.asm). Each runs at OVWIN;
; OVP_x is where its image is in the PRG, OVN_x its length. See overlay.inc.

OVL_IMG = *

OVP_SYS = *
        .logical OVWIN
        .include "sysov.inc"
        .here
OVN_SYS = * - OVP_SYS

OVP_DISK = *
        .logical OVWIN
        .include "disk.inc"
        .here
OVN_DISK = * - OVP_DISK

OVP_SEARCH = *
        .logical OVWIN
        .include "search.inc"
        .here
OVN_SEARCH = * - OVP_SEARCH

OVP_RESHAPE = *
        .logical OVWIN
        .include "reshape.inc"
        .here
OVN_RESHAPE = * - OVP_RESHAPE

OVP_REPL = *
        .logical OVWIN
        .include "replicate.inc"
        .here
OVN_REPL = * - OVP_REPL

OVP_FDEF = *
        .logical OVWIN
        .include "fdef.inc"
        .here
OVN_FDEF = * - OVP_FDEF

OVP_FLOOR = *
        .logical OVWIN
        .include "floor.inc"
        .here
OVN_FLOOR = * - OVP_FLOOR

OVP_INNER = *
        .logical OVWIN
        .include "inner.inc"
        .here
OVN_INNER = * - OVP_INNER

OVP_CATM = *
        .logical OVWIN
        .include "catm.inc"
        .here
OVN_CATM = * - OVP_CATM

OVP_TRANSP = *
        .logical OVWIN
        .include "transp.inc"
        .here
OVN_TRANSP = * - OVP_TRANSP

OVP_MATH = *
        .logical OVWIN
        .include "math.inc"
        .here
OVN_MATH = * - OVP_MATH

OVP_FACT = *
        .logical OVWIN
        .include "fact.inc"
        .here
OVN_FACT = * - OVP_FACT

OVP_RAND = *
        .logical OVWIN
        .include "rand.inc"
        .here
OVN_RAND = * - OVP_RAND

OVP_GFX = *
        .logical OVWIN
        .include "gfx.inc"
        .here
OVN_GFX = * - OVP_GFX

OVP_DRAW = *
        .logical OVWIN
        .include "draw.inc"
        .here
OVN_DRAW = * - OVP_DRAW

OVP_SPR = *
        .logical OVWIN
        .include "spr.inc"
        .here
OVN_SPR = * - OVP_SPR

OVP_BASE = *
        .logical OVWIN
        .include "baseconv.inc"
        .here
OVN_BASE = * - OVP_BASE

OVL_TOT = * - OVL_IMG
OVM_1 = OVN_SYS > OVN_DISK ? OVN_SYS : OVN_DISK
OVM_2 = OVM_1 > OVN_SEARCH ? OVM_1 : OVN_SEARCH
OVM_3 = OVM_2 > OVN_RESHAPE ? OVM_2 : OVN_RESHAPE
OVM_4 = OVM_3 > OVN_REPL ? OVM_3 : OVN_REPL
OVM_5 = OVM_4 > OVN_FDEF ? OVM_4 : OVN_FDEF
OVM_6 = OVM_5 > OVN_FLOOR ? OVM_5 : OVN_FLOOR
OVM_7 = OVM_6 > OVN_INNER ? OVM_6 : OVN_INNER
OVM_8 = OVM_7 > OVN_CATM ? OVM_7 : OVN_CATM
OVM_9 = OVM_8 > OVN_TRANSP ? OVM_8 : OVN_TRANSP
OVM_10 = OVM_9 > OVN_MATH ? OVM_9 : OVN_MATH
OVM_11 = OVM_10 > OVN_FACT ? OVM_10 : OVN_FACT
OVM_12 = OVM_11 > OVN_RAND ? OVM_11 : OVN_RAND
OVM_13 = OVM_12 > OVN_GFX ? OVM_12 : OVN_GFX
OVM_14 = OVM_13 > OVN_DRAW ? OVM_13 : OVN_DRAW
OVM_15 = OVM_14 > OVN_SPR ? OVM_14 : OVN_SPR
OVWIN_MAX = OVM_15 > OVN_BASE ? OVM_15 : OVN_BASE        ; the window's size (bss.inc): the biggest overlay
        .cerror OVN_BASE > OVWIN_SIZE, "the window is too small for the decode/encode overlay"
        .cerror OVN_SYS > OVWIN_SIZE, "the window is too small for the system command overlay"
        .cerror OVN_DISK > OVWIN_SIZE, "the window is too small for the disk overlay"
        .cerror OVN_FDEF > OVWIN_SIZE, "the window is too small for the function editor overlay"
        .cerror OVN_FLOOR > OVWIN_SIZE, "the window is too small for the floor overlay"
        .cerror OVN_INNER > OVWIN_SIZE, "the window is too small for the inner product overlay"
        .cerror OVN_CATM > OVWIN_SIZE, "the window is too small for the matrix catenation overlay"
        .cerror OVN_TRANSP > OVWIN_SIZE, "the window is too small for the transpose overlay"
        .cerror OVN_MATH > OVWIN_SIZE, "the window is too small for the numeric functions overlay"
        .cerror OVN_FACT > OVWIN_SIZE, "the window is too small for the factorial overlay"
        .cerror OVN_RAND > OVWIN_SIZE, "the window is too small for the roll and deal overlay"
        .cerror OVN_GFX > OVWIN_SIZE, "the window is too small for the graphics overlay"
        .cerror OVN_DRAW > OVWIN_SIZE, "the window is too small for the drawing overlay"
        .cerror OVN_SPR > OVWIN_SIZE, "the window is too small for the sprite overlay"
        .cerror OVL_TOT > $e000, "the overlay images must end below $E000, where the text screen is kept while a picture is up"
        .cerror OVL_TOT > $ffff, "the overlay images must fit one 64 KB REU bank"
        .cerror OVN_SEARCH > OVWIN_SIZE, "the window is too small for the search overlay"
        .cerror OVN_RESHAPE > OVWIN_SIZE, "the window is too small for the reshape overlay"
        .cerror OVN_REPL > OVWIN_SIZE, "the window is too small for the repl overlay"

; Start-up data, after the images and so not copied to the REU: the character shapes, read once by
; build_charset. This RAM is taken over by the tables and the heap, so nothing may be written to it
; before build_charset is done (the guard below covers the one variable it uses).
INIT_START = *
        .include "glyphs.inc"
INIT_END = *
        .cerror gtp >= INIT_START && gtp < INIT_END, "build_charset's pointer lies in the glyph data it is reading"
