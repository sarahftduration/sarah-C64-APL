; float24 arithmetic. Spec: apl64.py (f_add, f_sub); layout in DESIGN.md.
;
; A float24 is 3 bytes: exponent (excess-128, 0 = zero), sign|hi7, lo8.
;
; f_add   fa = fa + fb    f_sub   fa = fa - fb
; Out: carry clear on success, carry set on overflow (DOMAIN ERROR).
;      fb is preserved except that f_add may swap it with fa; treat as clobbered.

        * = $C000

fa      = $10           ; operand A / result (3 bytes)
fb      = $13           ; operand B (3 bytes)

ah      = $16           ; mantissa A, 24 bits: ah:al:ag (ag = extra low bits)
al      = $17
ag      = $18
bh      = $19           ; mantissa B, aligned, bh:bl:bg
bl      = $1a
bg      = $1b
sa      = $1c           ; sign of A in bit 7
sb      = $1d           ; sign of B in bit 7
ex      = $1e           ; result exponent, signed 16-bit (ex, ex+1)
sticky  = $20

f_sub:  lda fb
        beq f_add
        lda fb+1
        eor #$80
        sta fb+1

f_add:  lda fa
        bne a_nz
        ldx #2
cpb:    lda fb,x
        sta fa,x
        dex
        bpl cpb
        clc
        rts
a_nz:   lda fb
        bne both
        clc
        rts

; make A the operand with the larger exponent
both:   lda fa
        cmp fb
        bcs ordered
        ldx #2
swp:    lda fa,x
        tay
        lda fb,x
        sta fa,x
        tya
        sta fb,x
        dex
        bpl swp

ordered:
        lda fa
        sta ex
        lda #0
        sta ex+1
        sta ag
        sta bg
        sta sticky
        lda fa+1
        sta sa
        and #$7f
        ora #$80
        sta ah
        lda fa+2
        sta al
        lda fb+1
        sta sb
        and #$7f
        ora #$80
        sta bh
        lda fb+2
        sta bl

; align B: shift right by the exponent difference, collecting lost bits
        lda fa
        sec
        sbc fb
        tax
        beq aligned
        cpx #24
        bcs far
shl:    lsr bh
        ror bl
        ror bg
        bcc nolost
        lda #1
        sta sticky
nolost: dex
        bne shl
        lda sticky
        beq aligned
        lda bg
        ora #1                  ; jam lost bits into the lowest bit
        sta bg
        jmp aligned
far:    lda #0
        sta bh
        sta bl
        lda #1
        sta bg
aligned:

        lda sa
        eor sb
        bmi dosub

        clc
        lda ag
        adc bg
        sta ag
        lda al
        adc bl
        sta al
        lda ah
        adc bh
        sta ah
        bcc norm
        ror ah                  ; carry out: shift right, exponent + 1
        ror al
        ror ag
        bcc ovinc
        lda ag
        ora #1
        sta ag
ovinc:  inc ex
        bne round
        inc ex+1
        jmp round

dosub:  sec
        lda ag
        sbc bg
        sta ag
        lda al
        sbc bl
        sta al
        lda ah
        sbc bh
        sta ah
        bcs subok
        sec                     ; B was larger: negate, flip sign
        lda #0
        sbc ag
        sta ag
        lda #0
        sbc al
        sta al
        lda #0
        sbc ah
        sta ah
        lda sa
        eor #$80
        sta sa
subok:  lda ah
        ora al
        ora ag
        bne norm
        jmp zero

; normalize: shift left until the top bit of ah is set
norm:   lda ah
        bmi round
nl:     asl ag
        rol al
        rol ah
        lda ex
        bne exdec
        dec ex+1
exdec:  dec ex
        lda ah
        bpl nl

; round to nearest even using ag as guard (bit 7) plus lower bits
round:  lda ag
        cmp #$80
        bcc pack
        bne up
        lda al                  ; exact tie: round up only if odd
        and #1
        beq pack
up:     inc al
        bne pack
        inc ah
        bne pack
        lda #$80                ; mantissa reached 65536
        sta ah
        inc ex
        bne pack
        inc ex+1

pack:   lda ex+1
        bmi zero                ; underflow flushes to zero
        bne over
        lda ex
        beq zero
        sta fa
        lda ah
        and #$7f
        sta fa+1
        lda sa
        and #$80
        ora fa+1
        sta fa+1
        lda al
        sta fa+2
        clc
        rts

zero:   lda #0
        sta fa
        sta fa+1
        sta fa+2
        clc
        rts

over:   sec
        rts
