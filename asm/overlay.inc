; Overlays: code that lives in the REU and runs from a window in main RAM. See DESIGN.md, REU.
;
; Each overlay is assembled to run at OVWIN (a .logical block in ovimg.inc) and its image sits in the
; PRG right after the resident code, in the space the tables and heap later take over; start-up
; (ov_init) copies all the images to the REU at offset 0, before anything else touches that RAM. An
; overlay is made resident by fetching its image into the window. The window is as big as the biggest
; overlay, so what is gained is the size of the others.
;
; Rules (tests/harness.py checks the second one whenever a test runs):
;  - an overlay may call resident code, and jump to it;
;  - nothing an overlay calls may load another overlay while the overlay is still running: its return
;    address would point into a window that now holds other code. (A jump to a stub, which leaves the
;    overlay for good, is fine.)
; Without an REU (reu_banks = 0) the overlaid features fail with NO REU.

OVID_SYS  = 1                   ; ids start at 1: 0 means the window is empty
OVID_DISK = 2
OVID_SEARCH = 3
OVID_RESHAPE = 4
OVID_REPL = 5

E_NOREU   = 11

ov_cur:  .byte 0                ; the overlay in the window, 0 for none
ov_sa:   .byte 0                ; A, X and Y of a call, kept while the overlay is loaded
ov_sx:   .byte 0
ov_sy:   .byte 0
ov_arg:  .byte 0, 0, 0          ; the inline arguments of ov_call: id, entry address
        .cerror (ov_arg+1) & $ff == $ff, "the indirect jump through ov_arg would wrap"

; the entry point of a routine in an overlay: put it in resident code where a jsr or jmp to the routine
; used to go:  name: .ovstub routine, OVID_x   (a and x and y arrive as they were, and the routine's rts
; returns to whoever called name)
ovstub  .macro
        jsr ov_call
        .byte \2
        .word \1
        .endm

; the entry points of the routines in overlays (jump or call these: s_x runs p_x)
s_gradeup: .ovstub p_gradeup, OVID_SEARCH
s_gradedown: .ovstub p_gradedown, OVID_SEARCH
s_member: .ovstub p_member, OVID_SEARCH
s_indexof: .ovstub p_indexof, OVID_SEARCH
s_rev: .ovstub p_rev, OVID_RESHAPE
s_drop: .ovstub p_drop, OVID_RESHAPE
s_rot: .ovstub p_rot, OVID_RESHAPE
s_take: .ovstub p_take, OVID_RESHAPE
s_repl: .ovstub p_repl, OVID_REPL

ov_call:
        sta ov_sa
        stx ov_sx
        sty ov_sy
        pla                     ; the address of the last byte of the jsr: the arguments follow it
        sta ov_rd+1
        pla
        sta ov_rd+2
        ldy #1
ov_l:
ov_rd:  lda $ffff,y             ; (the address is the one just pulled)
        sta ov_arg-1,y
        iny
        cpy #4
        bne ov_l
        lda ov_arg
        jsr ov_ensure
        bcs ov_err
        lda ov_sa
        ldx ov_sx
        ldy ov_sy
        jmp (ov_arg+1)
ov_err: rts                     ; NO REU, to the caller of the stub

; A = an overlay id: make it the one in the window. Carry set with A = NO REU if it cannot be. Clobbers A, X, Y.
ov_ensure:
        cmp ov_cur
        beq oe_ok
        tax
        lda reu_banks
        beq oe_no
        lda #<OVWIN
        sta REU_C64
        lda #>OVWIN
        sta REU_C64+1
        lda ov_off_lo,x
        sta REU_ADDR
        lda ov_off_hi,x
        sta REU_ADDR+1
        lda #0
        sta REU_ADDR+2
        lda ov_len_lo,x
        sta REU_LEN
        lda ov_len_hi,x
        sta REU_LEN+1
ov_fetch: jsr reu_fetch         ; (the tests look at the stack here)
        stx ov_cur
oe_ok:  clc
        rts
oe_no:  lda #E_NOREU
        sec
        rts

; Start-up, with an REU: copy every overlay image to the REU (offset 0).
ov_init:
        lda #<OVL_IMG
        sta REU_C64
        lda #>OVL_IMG
        sta REU_C64+1
        lda #0
        sta REU_ADDR
        sta REU_ADDR+1
        sta REU_ADDR+2
        sta ov_cur
        lda #<OVL_TOT
        sta REU_LEN
        lda #>OVL_TOT
        sta REU_LEN+1
        jmp reu_stash

; where each image is in the REU, and how long it is; indexed by id
ov_off_lo: .byte 0, <(OVP_SYS-OVL_IMG), <(OVP_DISK-OVL_IMG), <(OVP_SEARCH-OVL_IMG), <(OVP_RESHAPE-OVL_IMG), <(OVP_REPL-OVL_IMG)
ov_off_hi: .byte 0, >(OVP_SYS-OVL_IMG), >(OVP_DISK-OVL_IMG), >(OVP_SEARCH-OVL_IMG), >(OVP_RESHAPE-OVL_IMG), >(OVP_REPL-OVL_IMG)
ov_len_lo: .byte 0, <OVN_SYS, <OVN_DISK, <OVN_SEARCH, <OVN_RESHAPE, <OVN_REPL
ov_len_hi: .byte 0, >OVN_SYS, >OVN_DISK, >OVN_SEARCH, >OVN_RESHAPE, >OVN_REPL
