; Floor and ceiling (monadic ⌊ ⌈): an overlay, see overlay.inc. Entered through s_floor and s_ceil.

; the floor (or ceiling) of the FLOAT element at ep, as flr_q gives it. For a ceiling the sign
; is turned round before and after: ceil(x) = -floor(-x).
pf_elem:
        ldy #0
        lda (ep),y
        sta fa
        iny
        lda (ep),y
        sta fa+1
        iny
        lda (ep),y
        sta fa+2
        jsr pf_neg
        jsr flr_q
        cmp #1
        beq pf_b
        lda pfm
        beq pf_z
        lda sgn
        eor #$80
        sta sgn
pf_z:   lda #0
        rts
pf_b:   jsr pf_neg
        lda #1
        rts
pf_neg: lda pfm
        beq pn_r
        lda fa
        beq pn_r
        lda fa+1
        eor #$80
        sta fa+1
pn_r:   rts

p_ceil: lda #1
        bne pf_go
p_floor: lda #0
pf_go:  sta pfm
        jsr topcell
        jsr getval
        lda vt
        cmp #1
        bne pf_1
        lda #E_DOMAIN
        sec
        rts
pf_1:   cmp #3
        beq pf_f
        clc                     ; BOOL and INT are whole already
        rts
pf_f:   lda vp                  ; first pass: does every result fit int16?
        sta ep
        lda vp+1
        sta ep+1
        lda vn
        sta qcnt
        lda vn+1
        sta qcnt+1
        lda #1
        sta pfa
pf_p1:  lda qcnt
        ora qcnt+1
        beq pf_a
        jsr pf_elem
        cmp #1
        bne pf_p2               ; a big whole number fits only as exactly -2^15
        lda fa
        cmp #144
        bne pf_nf
        lda fa+1
        cmp #$80
        bne pf_nf
        lda fa+2
        beq pf_p2
pf_nf:  lda #0
        sta pfa
pf_p2:  clc
        lda ep
        adc #3
        sta ep
        bcc pf_p3
        inc ep+1
pf_p3:  lda qcnt
        bne pf_p4
        dec qcnt+1
pf_p4:  dec qcnt
        jmp pf_p1
pf_a:   lda pfa                 ; the result: INT if all fit, else FLOAT
        eor #1
        clc
        adc #2
        sta nt                  ; 2 or 3
        lda vrk
        bne pf_arr
        lda nt
        sta cv
        lda #0
        sta cv+1
        sta cv+2
        sta cv+3
        lda #<(cv+1)
        sta dp
        lda #>(cv+1)
        sta dp+1
        jmp pf_fill
pf_arr: sta nrk
        lda vn
        sta nn
        lda vn+1
        sta nn+1
        lda vs0
        sta nd0
        lda vs0+1
        sta nd0+1
        lda vs1
        sta nd1
        lda vs1+1
        sta nd1+1
        jsr newarr
        bcc pf_a2
        rts
pf_a2:  jsr topcell             ; (the arrays may have moved)
        jsr getval
pf_fill:
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        lda vn
        sta qcnt
        lda vn+1
        sta qcnt+1
pf_l:   lda qcnt
        ora qcnt+1
        beq pf_done
        jsr pf_elem
        tax                     ; 0: ia and sgn, 1: fa
        ldy #0
        lda pfa
        beq pf_fl
        cpx #0                  ; INT: a two's complement 16-bit value
        bne pf_min
        lda sgn
        bpl pf_pos
        sec
        lda #0
        sbc ia
        sta ia
        lda #0
        sbc ia+1
        sta ia+1
pf_pos: lda ia
        sta (dp),y
        iny
        lda ia+1
        sta (dp),y
        lda #2
        bne pf_adv
pf_min: lda #0                  ; -2^15
        sta (dp),y
        iny
        lda #$80
        sta (dp),y
        lda #2
        bne pf_adv
pf_fl:  cpx #0
        bne pf_st
        jsr m_to_f
pf_st:  lda fa
        sta (dp),y
        iny
        lda fa+1
        sta (dp),y
        iny
        lda fa+2
        sta (dp),y
        lda #3
pf_adv: clc
        adc dp
        sta dp
        bcc pf_v1
        inc dp+1
pf_v1:  clc
        lda ep
        adc #3
        sta ep
        bcc pf_v2
        inc ep+1
pf_v2:  lda qcnt
        bne pf_v3
        dec qcnt+1
pf_v3:  dec qcnt
        jmp pf_l
pf_done: jmp setmon
