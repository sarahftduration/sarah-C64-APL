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

OVL_TOT = * - OVL_IMG
        .cerror OVN_SYS > OVWIN_SIZE, "the window is too small for the system command overlay"
        .cerror OVN_DISK > OVWIN_SIZE, "the window is too small for the disk overlay"
        .cerror OVL_TOT > $ffff, "the overlay images must fit one 64 KB REU bank"
        .cerror OVN_SEARCH > OVWIN_SIZE, "the window is too small for the search overlay"
        .cerror OVN_RESHAPE > OVWIN_SIZE, "the window is too small for the reshape overlay"
        .cerror OVN_REPL > OVWIN_SIZE, "the window is too small for the repl overlay"
