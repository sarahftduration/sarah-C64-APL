; float24 arithmetic. Spec: apl64.py (f_add, f_sub); layout in DESIGN.md.
;
; A float24 is 3 bytes: exponent (excess-128, 0 = zero), sign|hi7, lo8.
;
; f_add   fa = fa + fb    f_sub   fa = fa - fb
; f_mul   fa = fa * fb     f_div   fa = fa / fb
; Out: carry clear on success, carry set on overflow (DOMAIN ERROR);
;      f_div also sets carry for a zero divisor.
;      fb is clobbered.

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
p0      = $21           ; f_mul: 32-bit product p3:p2:p1:p0
p1      = $22
p2      = $23
p3      = $24
rl      = $21           ; f_div: remainder rh:rl, quotient qh:ql
rh      = $22
ql      = $23
qh      = $24

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

; ---------------------------------------------------------------------
; f_mul: 16x16 -> 32 shift-add multiply of the mantissas, then normalize
; to 16 bits, guard byte = next 8 bits, lowest bit jammed with the rest.
; Result exponent = ea + eb - 128 (or - 129 when the product needs a left
; shift). Rounding and packing are shared with f_add.

f_mul:  lda fa
        beq mzero
        lda fb
        bne mnz
mzero:  jmp zero
mnz:    lda fa+1
        eor fb+1
        sta sa
        lda fa+2
        sta p0
        lda fa+1
        and #$7f
        ora #$80
        sta p1
        lda fb+2
        sta bl
        lda fb+1
        and #$7f
        ora #$80
        sta bh
        jsr mul16

        clc
        lda fa
        adc fb
        sta ex
        lda #0
        adc #0
        sta ex+1
        sec
        lda ex
        sbc #129
        sta ex
        lda ex+1
        sbc #0
        sta ex+1
        lda p3
        bmi mnorm
        asl p0
        rol p1
        rol p2
        rol p3
        jmp mgo
mnorm:  inc ex
        bne mgo
        inc ex+1
mgo:    lda p3
        sta ah
        lda p2
        sta al
        lda p1
        sta ag
        lda p0
        beq mrnd
        lda ag
        ora #1
        sta ag
mrnd:   jmp round

; ---------------------------------------------------------------------
; f_div: restoring division producing a 17-bit quotient (leading 1, 15
; mantissa bits, guard bit); a nonzero final remainder is the sticky bit.
; If ma < mb the dividend is doubled first and the exponent is one lower.

f_div:  lda fb
        bne dnz
        sec
        rts
dnz:    lda fa
        bne dnz2
        jmp zero
dnz2:   lda fa+1
        eor fb+1
        sta sa
        lda fa+2
        sta rl
        lda fa+1
        and #$7f
        ora #$80
        sta rh
        lda fb+2
        sta bl
        lda fb+1
        and #$7f
        ora #$80
        sta bh

        sec
        lda fa
        sbc fb
        sta ex
        lda #0
        sbc #0
        sta ex+1
        clc
        lda ex
        adc #128
        sta ex
        lda ex+1
        adc #0
        sta ex+1

        lda rh
        cmp bh
        bcc dsmall
        bne dgeq
        lda rl
        cmp bl
        bcc dsmall
dgeq:   inc ex
        bne dg1
        inc ex+1
dg1:    sec
        lda rl
        sbc bl
        sta rl
        lda rh
        sbc bh
        sta rh
        jmp dgo
dsmall: asl rl
        rol rh
        sec
        lda rl
        sbc bl
        sta rl
        lda rh
        sbc bh
        sta rh

dgo:    lda #0
        sta ql
        sta qh
        ldx #16
dl:     asl rl
        rol rh
        bcs dsub
        lda rh
        cmp bh
        bcc dno
        bne dsub
        lda rl
        cmp bl
        bcc dno
dsub:   sec
        lda rl
        sbc bl
        sta rl
        lda rh
        sbc bh
        sta rh
        sec
        bcs dins
dno:    clc
dins:   rol ql
        rol qh
        dex
        bne dl

        sec                     ; the implicit leading quotient bit
        ror qh
        ror ql
        lda #0
        bcc dg0
        lda #$80                ; guard bit
dg0:    sta ag
        lda qh
        sta ah
        lda ql
        sta al
        lda rl
        ora rh
        beq drnd
        lda ag
        ora #1
        sta ag
drnd:   jmp round

; mul16: p3:p2:p1:p0 = (p1:p0) * (bh:bl), unsigned 16x16 -> 32.
; Shifts the 32-bit register right each step; the multiplier drains out of
; the low end while the product fills the high end.
mul16:  lda #0
        sta p2
        sta p3
        ldx #16
mlp:    clc
        lda p0
        and #1
        beq mskip
        clc
        lda p2
        adc bl
        sta p2
        lda p3
        adc bh
        sta p3
mskip:  ror p3
        ror p2
        ror p1
        ror p0
        dex
        bne mlp
        rts
