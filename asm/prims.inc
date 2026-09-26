; Primitives. Included by eval.asm.
;
; Monadic: the operand is the top cell; the result replaces it.
; Dyadic:  the LEFT operand is the top cell, the RIGHT the one below it; both
;          are replaced by the result.
; Each returns carry clear, or carry set with A = error code. Any allocation may
; run the collector, so operand pointers (vp) are re-derived after newarr.
; Scratch overlaps the tokenizer's zero page, which is idle during evaluation
; (but not symcnt at $5e).

im      = $3c
ihuge   = WS+$6c
ineg    = $fe
e0      = WS+$6e
qat     = WS+$6f
qbt     = $88
qar     = WS+$71
qbr     = WS+$72
qan     = $4e
qbn     = WS+$75
qd0     = $83
qd1     = $7e
qneg0   = WS+$7b
qneg1   = WS+$7c
qhuge0  = WS+$7d
qhuge1  = WS+$7e
qidx    = WS+$7f
qw      = $36
qcnt    = $0a
qend    = WS+$85
qbase   = WS+$87
bc      = $39
qe      = WS+$8b

fillbuf: .byte 0, 0, 0

; bc = vn * width(vt)
bytecount:
        ldx vt
        lda WIDTHT,x
        sta qw
        lda vn
        sta bc
        lda vn+1
        sta bc+1
        lda qw
        cmp #2
        bcc bcret
        clc
        lda bc
        adc vn
        sta bc
        lda bc+1
        adc vn+1
        sta bc+1
        lda qw
        cmp #3
        bcc bcret
        clc
        lda bc
        adc vn
        sta bc
        lda bc+1
        adc vn+1
        sta bc+1
bcret:  rts

; copy bc bytes from vp to dp (both kept)
copy_vp_dp:
        lda vp
        sta cs
        lda vp+1
        sta cs+1
        lda dp
        sta cd
        lda dp+1
        sta cd+1
        lda bc
        sta t0
        lda bc+1
        sta t0+1
        jmp memcpy_cs_cd

setmon: jsr topcell
        ldy #3
sm1:    lda cv,y
        sta (cptr),y
        dey
        bpl sm1
        clc
        rts

setdy:  sec
        lda vsp
        sbc #4
        sta vsp
        lda vsp+1
        sbc #0
        sta vsp+1
        jmp setmon

; --- element to integer ---------------------------------------------------------
; In: vt, ep. Out: carry clear: im = magnitude, ihuge = magnitude >= 65536, ineg.
; Carry set: not a whole number (or a CHAR): DOMAIN ERROR.
elem_to_int:
        lda #0
        sta ihuge
        sta ineg
        sta im
        sta im+1
        ldy #0
        lda vt
        beq eti_b
        cmp #1
        beq eti_bad
        cmp #2
        beq eti_i
        lda (ep),y              ; FLOAT: exponent
        beq eti_ok
        sta e0
        iny
        lda (ep),y
        sta qe
        and #$80
        beq eti_f1
        lda #1
        sta ineg
eti_f1: lda qe
        and #$7f
        ora #$80
        sta im+1
        iny
        lda (ep),y
        sta im
        lda e0
        cmp #145
        bcs eti_huge
        cmp #144
        beq eti_ok
        cmp #129                ; below 2^0 * 2^15 shifts: not whole
        bcc eti_bad
        lda #144
        sec
        sbc e0
        tax
eti_sh: lsr im+1
        ror im
        bcs eti_bad
        dex
        bne eti_sh
eti_ok: clc
        rts
eti_huge:
        lda #1
        sta ihuge
        lda #0
        sta im
        sta im+1
        clc
        rts
eti_b:  lda (ep),y
        sta im
        clc
        rts
eti_i:  lda (ep),y
        sta im
        iny
        lda (ep),y
        sta im+1
        bpl eti_ok
        lda #1
        sta ineg
        sec
        lda #0
        sbc im
        sta im
        lda #0
        sbc im+1
        sta im+1
        clc
        rts
eti_bad:
        sec
        rts

; The cell at cptr as an integer argument list (the model's to_ints): rank <= 1,
; every element converted in order. Records the count in qan and the first two
; elements in qd0/qneg0/qhuge0 and qd1/qneg1/qhuge1.
arg_ints:
        jsr getval
        lda vrk
        cmp #2
        bcc ai1
        lda #E_RANK
        sec
        rts
ai1:    lda vn
        sta qan
        lda vn+1
        sta qan+1
        lda #0
        sta qd0
        sta qd0+1
        sta qneg0
        sta qhuge0
        sta qd1
        sta qd1+1
        sta qneg1
        sta qhuge1
        sta qidx
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        lda vn
        sta qcnt
        lda vn+1
        sta qcnt+1
ail:    lda qcnt
        ora qcnt+1
        beq aidone
        jsr elem_to_int
        bcs aibad
        ldx qidx
        bne ai_n0
        lda im
        sta qd0
        lda im+1
        sta qd0+1
        lda ineg
        sta qneg0
        lda ihuge
        sta qhuge0
        jmp ai_adv
ai_n0:  cpx #1
        bne ai_adv
        lda im
        sta qd1
        lda im+1
        sta qd1+1
        lda ineg
        sta qneg1
        lda ihuge
        sta qhuge1
ai_adv: lda qidx
        cmp #2
        bcs ai_a2
        inc qidx
ai_a2:  ldx vt
        clc
        lda ep
        adc WIDTHT,x
        sta ep
        bcc ai_a3
        inc ep+1
ai_a3:  lda qcnt
        bne ai_a4
        dec qcnt+1
ai_a4:  dec qcnt
        jmp ail
aidone: clc
        rts
aibad:  lda #E_DOMAIN
        sec
        rts

; --- monadic + : identity on numbers ---------------------------------------------
p_plusm:
        jsr topcell
        jsr getval
        lda vt
        cmp #1
        bne ppm1
        lda #E_DOMAIN
        sec
        rts
ppm1:   clc
        rts

; --- monadic , : ravel -----------------------------------------------------------
p_ravel:
        jsr topcell
        jsr getval
        lda vrk
        cmp #1
        bne prv1
        clc
        rts
prv1:   lda vt
        sta nt
        lda #1
        sta nrk
        lda vn
        sta nn
        sta nd0
        lda vn+1
        sta nn+1
        sta nd0+1
        jsr newarr
        bcs prvx
        jsr topcell
        jsr getval
        jsr bytecount
        jsr copy_vp_dp
        jmp setmon
prvx:   rts

; --- monadic ⍴ : shape ---------------------------------------------------------------
p_shape:
        jsr topcell
        jsr getval
        lda #2
        sta nt
        lda #1
        sta nrk
        lda vrk
        sta nn
        sta nd0
        lda #0
        sta nn+1
        sta nd0+1
        jsr newarr
        bcs psx
        lda vrk
        beq psdone
        ldy #0
        lda vs0
        sta (dp),y
        iny
        lda vs0+1
        sta (dp),y
        lda vrk
        cmp #2
        bne psdone
        iny
        lda vs1
        sta (dp),y
        iny
        lda vs1+1
        sta (dp),y
psdone: jmp setmon
psx:    rts

; --- monadic ⍳ : index generator -----------------------------------------------------
p_iota: jsr topcell
        jsr arg_ints
        bcs pix
        lda qan+1
        bne pi_len
        lda qan
        cmp #1
        bne pi_len
        lda qneg0
        ora qhuge0
        bne pi_dom
        lda qd0+1
        bmi pi_dom
        lda #2
        sta nt
        lda #1
        sta nrk
        lda qd0
        sta nn
        sta nd0
        lda qd0+1
        sta nn+1
        sta nd0+1
        jsr newarr
        bcs pix
        lda nn
        ora nn+1
        beq iodone
        lda #1
        sta qd1
        lda #0
        sta qd1+1
        lda nn
        sta qcnt
        lda nn+1
        sta qcnt+1
iol:    ldy #0
        lda qd1
        sta (dp),y
        iny
        lda qd1+1
        sta (dp),y
        clc
        lda dp
        adc #2
        sta dp
        bcc pil2
        inc dp+1
pil2:   inc qd1
        bne pil3
        inc qd1+1
pil3:   lda qcnt
        bne pil4
        dec qcnt+1
pil4:   dec qcnt
        lda qcnt
        ora qcnt+1
        bne iol
iodone: jmp setmon
pi_len: lda #E_LENGTH
        sec
        rts
pi_dom: lda #E_DOMAIN
        sec
pix:    rts

; --- dyadic ⍴ : reshape ----------------------------------------------------------------
p_reshape:
        jsr topcell
        jsr arg_ints
        bcc *+3
        rts
        lda qan+1
        beq *+5
        jmp prs_lim
        lda qan
        cmp #3
        bcc *+5
        jmp prs_lim
        lda qneg0
        ora qneg1
        beq *+5
        jmp prs_dom
        lda qhuge0
        ora qhuge1
        beq *+5
        jmp prs_ws
        lda qan                 ; n = product of the dimensions
        beq prs_n1
        cmp #1
        beq prs_n2
        lda qd0
        sta p0
        lda qd0+1
        sta p1
        lda qd1
        sta bl
        lda qd1+1
        sta bh
        jsr mul16
        lda p2
        ora p3
        beq *+5
        jmp prs_ws
        lda p0
        sta nn
        lda p1
        sta nn+1
        jmp prs_r
prs_n1: lda #1
        sta nn
        lda #0
        sta nn+1
        jmp prs_r
prs_n2: lda qd0
        sta nn
        lda qd0+1
        sta nn+1
prs_r:  lda qd0
        sta nd0
        lda qd0+1
        sta nd0+1
        lda qd1
        sta nd1
        lda qd1+1
        sta nd1+1
        lda qan
        sta nrk
        jsr secondcell          ; the right argument gives the data and the type
        jsr getval
        lda vt
        sta nt
        lda vn
        sta qbn
        lda vn+1
        sta qbn+1
        lda nrk
        bne prs_arr
        ; scalar result: its first element, or the fill element
        lda nt
        sta cv
        lda #0
        sta cv+1
        sta cv+2
        sta cv+3
        lda qbn
        ora qbn+1
        bne prs_sc1
        lda nt
        cmp #1
        bne prs_scd
        lda #32
        sta cv+1
        jmp prs_scd
prs_sc1: ldx nt
        lda WIDTHT,x
        sta qw
        ldy #0
        ldx #1
prs_sc2: lda (vp),y
        sta cv,x
        iny
        inx
        dec qw
        bne prs_sc2
prs_scd: jmp setdy
prs_arr: jsr newarr
        bcc *+3
        rts
        jsr secondcell
        jsr getval
        lda vn
        ora vn+1
        bne prs_src
        lda #0                  ; empty right argument: fill element
        sta fillbuf
        lda nt
        cmp #1
        bne prs_f1
        lda #32
        sta fillbuf
prs_f1: lda #<fillbuf
        sta qbase
        lda #>fillbuf
        sta qbase+1
        ldx nt
        lda WIDTHT,x
        sta qw
        clc
        adc qbase
        sta qend
        lda qbase+1
        adc #0
        sta qend+1
        jmp prs_go
prs_src: jsr bytecount
        lda vp
        sta qbase
        lda vp+1
        sta qbase+1
        lda vp
        clc
        adc bc
        sta qend
        lda vp+1
        adc bc+1
        sta qend+1
prs_go: lda qbase
        sta qsrc
        lda qbase+1
        sta qsrc+1
        lda nn
        sta qcnt
        lda nn+1
        sta qcnt+1
prs_l:  lda qcnt
        ora qcnt+1
        beq prs_done
        ldy #0
prs_b:  lda (qsrc),y
        sta (dp),y
        iny
        cpy qw
        bne prs_b
        clc
        lda dp
        adc qw
        sta dp
        bcc prs_c1
        inc dp+1
prs_c1: clc
        lda qsrc
        adc qw
        sta qsrc
        bcc prs_c2
        inc qsrc+1
prs_c2: lda qsrc
        cmp qend
        bne prs_c3
        lda qsrc+1
        cmp qend+1
        bne prs_c3
        lda qbase
        sta qsrc
        lda qbase+1
        sta qsrc+1
prs_c3: lda qcnt
        bne prs_c4
        dec qcnt+1
prs_c4: dec qcnt
        jmp prs_l
prs_done:
        jmp setdy
prs_lim: lda #E_LIMIT
        sec
        rts
prs_dom: lda #E_DOMAIN
        sec
        rts
prs_ws: lda #E_WSFULL
        sec
prsx:   rts

; --- dyadic , : catenate ---------------------------------------------------------------
p_catenate:
        jsr topcell
        jsr getval
        lda vt
        sta qat
        lda vrk
        sta qar
        lda vn
        sta qan
        lda vn+1
        sta qan+1
        jsr secondcell
        jsr getval
        lda vt
        sta qbt
        lda vrk
        sta qbr
        lda vn
        sta qbn
        lda vn+1
        sta qbn+1
        lda qar
        cmp #2
        bcs pc_nonce
        lda qbr
        cmp #2
        bcs pc_nonce
        lda qan
        ora qan+1
        bne pcn1
        lda qbt
        sta nt
        jmp pct
pcn1:   lda qbn
        ora qbn+1
        bne pcn2
        lda qat
        sta nt
        jmp pct
pcn2:   lda qat
        cmp qbt
        beq pcsame
        cmp #1
        beq pc_dom
        lda qbt
        cmp #1
        beq pc_dom
        lda qat
        cmp qbt
        bcs pcmaxa
        lda qbt
pcmaxa: sta nt
        jmp pct
pcsame: sta nt
pct:    clc
        lda qan
        adc qbn
        sta nn
        sta nd0
        lda qan+1
        adc qbn+1
        sta nn+1
        sta nd0+1
        bcs pc_ws
        lda #1
        sta nrk
        jsr newarr
        bcs pcx
        jsr topcell
        jsr getval
        jsr cvcopy
        jsr secondcell
        jsr getval
        jsr cvcopy
        jmp setdy
pc_nonce:
        lda #E_NONCE
        sec
        rts
pc_dom: lda #E_DOMAIN
        sec
        rts
pc_ws:  lda #E_WSFULL
        sec
pcx:    rts

; append the array at vp (vt, vn) to dp, converting to type nt; advances dp
cvcopy: lda vn
        ora vn+1
        beq cvx
        lda vt
        cmp nt
        bne cvconv
        jsr bytecount
        jsr copy_vp_dp
        clc
        lda dp
        adc bc
        sta dp
        lda dp+1
        adc bc+1
        sta dp+1
cvx:    rts
cvconv: lda vp
        sta ep
        lda vp+1
        sta ep+1
        lda vn
        sta qcnt
        lda vn+1
        sta qcnt+1
cvl:    ldy #0
        lda (ep),y
        sta ia
        lda #0
        sta ia+1
        lda vt
        cmp #2
        bne cv_b
        iny
        lda (ep),y
        sta ia+1
cv_b:   lda nt
        cmp #3
        beq cv_f
        ldy #0
        lda ia
        sta (dp),y
        iny
        lda ia+1
        sta (dp),y
        lda #2
        jmp cv_dp
cv_f:   jsr i_to_f
        ldy #0
        lda fa
        sta (dp),y
        iny
        lda fa+1
        sta (dp),y
        iny
        lda fa+2
        sta (dp),y
        lda #3
cv_dp:  clc
        adc dp
        sta dp
        bcc cv_e
        inc dp+1
cv_e:   ldx vt
        clc
        lda ep
        adc WIDTHT,x
        sta ep
        bcc cv_n
        inc ep+1
cv_n:   lda qcnt
        bne cv_n2
        dec qcnt+1
cv_n2:  dec qcnt
        lda qcnt
        ora qcnt+1
        bne cvl
        rts
