; int16 arithmetic: add, subtract, multiply with overflow reported in carry.
; Spec: apl64.py _arith (INT path), f_from_int.
;
; i_add   ia = ia + ib     i_sub   ia = ia - ib
;   Out: ia holds the wrapped 16-bit result; carry set = the true result
;   left int16 (signed overflow).
; i_mul   ia = ia * ib    same convention: low 16 bits of the signed product,
;   carry set if the true product does not fit int16.
; i_to_f  fa = float24(ia), exact.   m_to_f: same, from magnitude ia + sign bit in sgn.

        .include "float24.inc"

ia      = $30
ib      = $32
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

; signed multiply via |ia| * |ib| (unsigned 16x16 -> 32), then negate the
; 32-bit product if the signs differ; it fits int16 iff p3:p2 is the sign
; extension of p1 bit 7.
i_mul:  lda ia+1
        eor ib+1
        sta sgn
        lda ia
        sta p0
        lda ia+1
        sta p1
        bpl imp1
        sec
        lda #0
        sbc p0
        sta p0
        lda #0
        sbc p1
        sta p1
imp1:   lda ib
        sta bl
        lda ib+1
        sta bh
        bpl imp2
        sec
        lda #0
        sbc bl
        sta bl
        lda #0
        sbc bh
        sta bh
imp2:   jsr mul16
        lda sgn
        bpl imchk
        sec
        lda #0
        sbc p0
        sta p0
        lda #0
        sbc p1
        sta p1
        lda #0
        sbc p2
        sta p2
        lda #0
        sbc p3
        sta p3
imchk:  lda p0
        sta ia
        lda p1
        sta ia+1
        lda #0
        ldx p1
        bpl imcmp
        lda #$ff
imcmp:  cmp p2
        bne iover
        cmp p3
        bne iover
        clc
        rts

; exponent = 128 + bit length of |ia|; mantissa = |ia| shifted to 16 bits
i_to_f: lda ia+1
        and #$80
        sta sgn
        bpl m_to_f
        sec
        lda #0
        sbc ia
        sta ia
        lda #0
        sbc ia+1
        sta ia+1
; m_to_f: fa = float24 of the unsigned magnitude in ia, sign in bit 7 of sgn
m_to_f: lda ia
        ora ia+1
        bne itnz
        sta fa
        sta fa+1
        sta fa+2
        rts
itnz:   ldx #144
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
