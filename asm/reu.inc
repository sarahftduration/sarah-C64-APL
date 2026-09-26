; RAM Expansion Unit: detection, size, and the two block transfers. See DESIGN.md, REU.
;
; The CPU cannot address an REU; a DMA controller at $DF00 copies a block between C64 RAM and
; the REU. The registers double as the parameter block: a caller stores the C64 address in
; REU_C64, the REU address (24 bits: offset low, offset high, bank) in REU_ADDR and the length
; in REU_LEN, then calls reu_stash (C64 -> REU) or reu_fetch (REU -> C64). The other registers
; are set here once (address control 0: both addresses count up; no interrupts). A length of 0
; means 65536. The CPU is stopped while the transfer runs, so it is done when the call returns.
;
; The REU is optional at run time: reu_banks is the number of 64 KB banks found, 0 for none.
; The features that live in overlays need it and report an error without it.

REU_STATUS = $df00
REU_CMD    = $df01
REU_C64    = $df02              ; (2) C64 address
REU_ADDR   = $df04              ; (3) REU address: offset low, offset high, bank
REU_LEN    = $df07              ; (2) length
REU_IRQ    = $df09              ; interrupt mask
REU_CTRL   = $df0a              ; address control

REUCMD_STASH  = $90                ; execute at once, no waiting for a write to $FF00; C64 -> REU
REUCMD_FETCH  = $91                ; the same, REU -> C64

reu_banks: .byte 0              ; 64 KB banks in the REU (at most 255: a 16 MB unit counts as 255); 0 = none
reu_tmp:   .byte 0              ; the byte the size probe moves

reu_stash:
        lda #REUCMD_STASH
        bne reu_go
reu_fetch:
        lda #REUCMD_FETCH
reu_go:
reu_trig: sta REU_CMD           ; (the tests emulate the transfer at this instruction)
        rts

; Carry set if there is no REU, else clear with reu_banks set. Two register patterns must read
; back (nothing else answers at $DF02-$DF05), then the size is found by address wrap-around: an
; REU of N banks (a power of two) has bank N as another name for bank 0.
reu_detect:
        lda #0
        sta reu_banks
        lda #$5a
        jsr reu_try
        bcs rd_no
        lda #$a5
        jsr reu_try
        bcs rd_no
        lda #0                  ; the fixed registers
        sta REU_IRQ
        sta REU_CTRL
        lda #$11                ; bank 0 holds $11
        sta reu_tmp
        lda #0
        ldx #REUCMD_STASH
        jsr reu_one
        ldy #2
rd_sz:  lda #$22                ; bank Y holds $22: if that changed bank 0, Y is the size
        sta reu_tmp
        tya
        ldx #REUCMD_STASH
        jsr reu_one
        lda #0
        ldx #REUCMD_FETCH
        jsr reu_one
        lda reu_tmp
        cmp #$22
        beq rd_found
        tya
        asl
        bcs rd_big              ; no wrap up to bank 128: 16 MB
        tay
        jmp rd_sz
rd_big: ldy #255
rd_found:
        sty reu_banks
        clc
        rts
rd_no:  sec
        rts

; the registers $DF02-$DF05 must read back A xor rq_mask, byte for byte
reu_try: sta reu_tmp
        ldx #3
rq1:    lda reu_tmp
        eor rq_mask,x
        sta REU_C64,x
        dex
        bpl rq1
        ldx #3
rq2:    lda reu_tmp
        eor rq_mask,x
        cmp REU_C64,x
        bne rq_bad
        dex
        bpl rq2
        clc
        rts
rq_bad: sec
        rts
rq_mask: .byte $00, $ff, $0f, $f0

; one byte, reu_tmp <-> bank A at offset 0 of the REU; X = REUCMD_STASH or REUCMD_FETCH
reu_one:
        sta REU_ADDR+2
        lda #0
        sta REU_ADDR
        sta REU_ADDR+1
        sta REU_LEN+1
        lda #<reu_tmp
        sta REU_C64
        lda #>reu_tmp
        sta REU_C64+1
        lda #1
        sta REU_LEN
        txa
        jmp reu_go
