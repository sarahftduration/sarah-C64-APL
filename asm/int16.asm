; int16 arithmetic and the optimistic-INT vector kernel.
; Spec: apl64.py _arith (INT path), f_from_int.
;
; i_add   ia = ia + ib     i_sub   ia = ia - ib
;   Out: ia holds the wrapped 16-bit result; carry set = the true result
;   left int16 (signed overflow).
; i_to_f  fa = float24(ia), exact.
; vec_add / vec_sub   elementwise INT op over flat data, all-or-nothing:
;   In:  pa, pb = element pointers; pr = result pointer (room for 3*cnt bytes);
;        cnt = element count; stra, strb = byte strides (2, or 0 to repeat a
;        scalar).
;   Out: carry clear: pr holds cnt INT elements (2 bytes each).
;        carry set:   some element overflowed int16, so the whole operation
;                     was redone and pr holds cnt FLOAT elements (3 bytes each).

        .include "float24.asm"

ia      = $30
ib      = $32
pa      = $34
pb      = $36
pr      = $38
cnt     = $3a
stra    = $3c
strb    = $3d
vop     = $3e
sva     = $40           ; saved copy of pa, pb, pr, cnt
sgn     = $48

i_add:  clc
        lda ia
        adc ib
        sta ia
        lda ia+1
        adc ib+1
        sta ia+1
        bvs iover
        clc
        rts
iover:  sec
        rts

i_sub:  sec
        lda ia
        sbc ib
        sta ia
        lda ia+1
        sbc ib+1
        sta ia+1
        bvs iover
        clc
        rts

; exponent = 128 + bit length of |ia|; mantissa = |ia| shifted to 16 bits
i_to_f: lda ia
        ora ia+1
        bne itnz
        sta fa
        sta fa+1
        sta fa+2
        rts
itnz:   lda ia+1
        and #$80
        sta sgn
        bpl itpos
        sec
        lda #0
        sbc ia
        sta ia
        lda #0
        sbc ia+1
        sta ia+1
itpos:  ldx #144
itnl:   lda ia+1
        bmi itdone
        asl ia
        rol ia+1
        dex
        bne itnl
itdone: stx fa
        lda ia+1
        and #$7f
        ora sgn
        sta fa+1
        lda ia
        sta fa+2
        rts

; add A to the 16-bit zero-page pointer at X
adv:    clc
        adc $00,x
        sta $00,x
        lda $01,x
        adc #0
        sta $01,x
        rts

vec_add: lda #0
        beq vgo
vec_sub: lda #1
vgo:    sta vop
        ldx #7
vsave:  lda pa,x
        sta sva,x
        dex
        bpl vsave

p1loop: lda cnt
        ora cnt+1
        beq p1done
        ldy #0
        lda (pa),y
        sta ia
        iny
        lda (pa),y
        sta ia+1
        ldy #0
        lda (pb),y
        sta ib
        iny
        lda (pb),y
        sta ib+1
        lda vop
        bne p1sub
        jsr i_add
        jmp p1chk
p1sub:  jsr i_sub
p1chk:  bcs redo
        ldy #0
        lda ia
        sta (pr),y
        iny
        lda ia+1
        sta (pr),y
        ldx #pa
        lda stra
        jsr adv
        ldx #pb
        lda strb
        jsr adv
        ldx #pr
        lda #2
        jsr adv
        lda cnt
        bne p1dec
        dec cnt+1
p1dec:  dec cnt
        jmp p1loop
p1done: clc
        rts

redo:   ldx #7
vrest:  lda sva,x
        sta pa,x
        dex
        bpl vrest
rloop:  lda cnt
        ora cnt+1
        beq rdone
        ldy #0
        lda (pb),y
        sta ia
        iny
        lda (pb),y
        sta ia+1
        jsr i_to_f
        ldx #2
rcopy:  lda fa,x
        sta fb,x
        dex
        bpl rcopy
        ldy #0
        lda (pa),y
        sta ia
        iny
        lda (pa),y
        sta ia+1
        jsr i_to_f
        lda vop
        bne rsub
        jsr f_add
        jmp rstore
rsub:   jsr f_sub
rstore: ldy #0
        lda fa
        sta (pr),y
        iny
        lda fa+1
        sta (pr),y
        iny
        lda fa+2
        sta (pr),y
        ldx #pa
        lda stra
        jsr adv
        ldx #pb
        lda strb
        jsr adv
        ldx #pr
        lda #3
        jsr adv
        lda cnt
        bne rdec
        dec cnt+1
rdec:   dec cnt
        jmp rloop
rdone:  sec
        rts
