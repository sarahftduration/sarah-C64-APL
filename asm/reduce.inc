; Reduce: f/ for the scalar dyadic functions. Spec: apl64.py make_reduce, _reduce_row.
;
; Along the last axis. A scalar operand is returned unchanged. Each row gives
; one scalar: an empty row gives the function's identity; + sums exactly (BOOL and
; INT as integers, FLOAT in a 40-byte fixed-point accumulator, rounded once);
; a single element has its own rules; otherwise the row is folded right to left
; through the full dyadic function (so INT overflow turns the accumulator FLOAT
; part-way, exactly as in the model). A matrix gives a vector of row results, all
; converted to the widest row type.
; Variables are absolute RAM: the folds run the scalar engine, which uses the
; zero page.

RV      = $5d80
rgl     = RV+0
rt      = RV+1
rrank   = RV+2
rn      = RV+3
rlead   = RV+5
rw      = RV+7
rbytes  = RV+8
rcell   = RV+10
rrow    = RV+12
rdest   = RV+14
rk      = RV+16
rbase   = RV+18
rptr    = RV+20
rdp     = RV+22
rres    = RV+24
rcv     = RV+28
risum   = RV+32
msh     = RV+36
mhb     = RV+37
mk      = RV+38
mn      = RV+40
mtmp    = RV+41
mwt     = RV+42
fexp    = RV+47
fneg    = RV+48
fsh     = RV+49
fobyte  = RV+50
fv0     = RV+51
fv1     = RV+52
fv2     = RV+53
rtl     = RV+54
rth     = RV+55
rte     = RV+56
FACC    = $5e00

red_ident:
        .byte 2, 0, 0, 0        ; +
        .byte 2, 0, 0, 0        ; -
        .byte 2, 1, 0, 0        ; ×
        .byte 3, $81, 0, 0      ; ÷
        .byte 0, 1, 0, 0        ; =
        .byte 0, 0, 0, 0        ; ≠
        .byte 0, 0, 0, 0        ; <
        .byte 0, 1, 0, 0        ; ≤
        .byte 0, 0, 0, 0        ; >
        .byte 0, 1, 0, 0        ; ≥

; A = function index 0..9 (the operand is the top cell)
p_reduce:
        sta rgl
        jsr topcell
        lda cptr
        sta rcell
        lda cptr+1
        sta rcell+1
        jsr getval
        lda vrk
        bne pr_go
        clc
        rts
pr_go:  lda vt
        sta rt
        lda vrk
        sta rrank
        ldx vt
        lda WIDTHT,x
        sta rw
        lda vrk
        cmp #2
        beq pr_m
        lda vn
        sta rn
        lda vn+1
        sta rn+1
        lda #1
        sta rlead
        lda #0
        sta rlead+1
        jmp pr_b
pr_m:   lda vs1
        sta rn
        lda vs1+1
        sta rn+1
        lda vs0
        sta rlead
        lda vs0+1
        sta rlead+1
pr_b:   lda rn
        sta rbytes
        lda rn+1
        sta rbytes+1
        lda rw
        cmp #2
        bcc pr_b2
        clc
        lda rbytes
        adc rn
        sta rbytes
        lda rbytes+1
        adc rn+1
        sta rbytes+1
        lda rw
        cmp #3
        bcc pr_b2
        clc
        lda rbytes
        adc rn
        sta rbytes
        lda rbytes+1
        adc rn+1
        sta rbytes+1
pr_b2:  lda rrank
        cmp #2
        beq pr_mat
        lda #0                  ; a vector: one row, a scalar result
        sta rrow
        sta rrow+1
        jsr red_row
        bcc pr_v1
        rts
pr_v1:  ldy #3
pr_v2:  lda rres,y
        sta cv,y
        dey
        bpl pr_v2
        jmp setmon

pr_mat: lda rlead
        ora rlead+1
        bne pm_first
        lda rgl                 ; no rows: an empty vector of the identity's type
        asl
        asl
        tax
        lda red_ident,x
        sta rdest
        jmp pm_alloc
pm_first:
        lda #0
        sta rrow
        sta rrow+1
        jsr red_row
        bcc pm_f1
        rts
pm_f1:  lda rres
        sta rdest
pm_alloc:
        lda rdest
        sta nt
        lda #1
        sta nrk
        lda rlead
        sta nn
        sta nd0
        lda rlead+1
        sta nn+1
        sta nd0+1
        jsr newarr
        bcc pm_ok
        cmp #E_WSFULL           ; the model computes every row before it checks the size
        beq pm_dry
        rts
pm_dry: lda #0
        sta rrow
        sta rrow+1
pm_d1:  lda rrow
        cmp rlead
        bne pm_d2
        lda rrow+1
        cmp rlead+1
        beq pm_d3
pm_d2:  jsr red_row
        bcc pm_d4
        rts
pm_d4:  inc rrow
        bne pm_d1
        inc rrow+1
        jmp pm_d1
pm_d3:  lda #E_WSFULL
        sec
        rts
pm_ok:  ldy #3
pm_s1:  lda cv,y
        sta rcv,y
        dey
        bpl pm_s1
        lda dp
        sta rdp
        lda dp+1
        sta rdp+1
        lda #0
        sta rrow
        sta rrow+1
pm_row: lda rrow
        cmp rlead
        bne pm_r1
        lda rrow+1
        cmp rlead+1
        beq pm_done
pm_r1:  jsr red_row
        bcc pm_r2
        rts
pm_r2:  lda rres
        cmp rdest
        beq pm_store
        cmp #1                  ; CHAR does not mix with numbers
        beq pm_dom
        lda rdest
        cmp #1
        beq pm_dom
        lda rres
        cmp rdest
        bcc pm_store            ; narrower: convert it
        sta rdest               ; wider: start again with the wider type
        jmp pm_alloc
pm_dom: lda #E_DOMAIN
        sec
        rts
pm_store:
        lda rres
        sta vt
        lda #<(rres+1)
        sta vp
        lda #>(rres+1)
        sta vp+1
        lda #1
        sta vn
        lda #0
        sta vn+1
        lda rdest
        sta nt
        lda rdp
        sta dp
        lda rdp+1
        sta dp+1
        jsr cvcopy
        lda dp
        sta rdp
        lda dp+1
        sta rdp+1
        inc rrow
        bne pm_row
        inc rrow+1
        jmp pm_row
pm_done:
        ldy #3
pm_e1:  lda rcv,y
        sta cv,y
        dey
        bpl pm_e1
        jmp setmon

; --- one row: rrow -> rres (a cell) -------------------------------------------------------
red_row:
        lda rcell
        sta cptr
        lda rcell+1
        sta cptr+1
        jsr getval
        lda rrow
        sta p0
        lda rrow+1
        sta p1
        lda rbytes
        sta bl
        lda rbytes+1
        sta bh
        jsr mul16
        clc
        lda vp
        adc p0
        sta rbase
        lda vp+1
        adc p1
        sta rbase+1
        lda rn
        ora rn+1
        bne rr1
        jmp rr_ident
rr1:    lda rgl
        bne rr2
        jmp rr_plus
rr2:    lda rn+1
        bne rr3
        lda rn
        cmp #1
        bne rr3
        jmp rr_single
rr3:    jmp rr_fold

rr_ident:
        lda rgl
        asl
        asl
        tax
        ldy #0
ri1:    lda red_ident,x
        sta rres,y
        inx
        iny
        cpy #4
        bne ri1
        clc
        rts

rr_dom: lda #E_DOMAIN
        sec
        rts

rr_plus:
        lda rt
        cmp #1
        beq rr_dom
        cmp #3
        bne rp1
        jmp rr_fsum
rp1:    jmp rr_isum

; a single element
rr_single:
        lda rbase
        sta ep
        lda rbase+1
        sta ep+1
        lda rgl
        cmp #4
        bcs rs_plain
        lda rt
        cmp #1
        beq rr_dom
        lda rgl
        cmp #3
        bne rs_notdiv
        lda rt
        cmp #3
        beq rs_plain
        jsr rs_ia               ; ÷ of a BOOL or INT: its FLOAT value
        jsr i_to_f
        lda #3
        sta rres
        lda fa
        sta rres+1
        lda fa+1
        sta rres+2
        lda fa+2
        sta rres+3
        clc
        rts
rs_notdiv:
        lda rt
        bne rs_plain
        jsr rs_ia               ; - or × of a BOOL: an INT
        lda #2
        sta rres
        lda ia
        sta rres+1
        lda ia+1
        sta rres+2
        lda #0
        sta rres+3
        clc
        rts
rs_plain:
        lda rt
        sta rres
        lda #0
        sta rres+1
        sta rres+2
        sta rres+3
        ldy #0
        ldx #1
rs_p1:  lda (ep),y
        sta rres,x
        iny
        inx
        cpy rw
        bne rs_p1
        clc
        rts
rs_ia:  ldy #0
        lda (ep),y
        sta ia
        lda #0
        sta ia+1
        lda rt
        beq rs_ia2
        iny
        lda (ep),y
        sta ia+1
rs_ia2: rts

; the fold, right to left through the dyadic scalar function
rr_fold:
        clc
        lda rbase
        adc rbytes
        sta rptr
        lda rbase+1
        adc rbytes+1
        sta rptr+1
        lda rn
        sta rk
        lda rn+1
        sta rk+1
        jsr rf_push             ; the last element is the accumulator
        bcc rf1
        rts
rf1:    lda rk
        bne rf2
        dec rk+1
rf2:    dec rk
rf_loop:
        lda rk
        ora rk+1
        beq rf_done
        jsr rf_push
        bcc rf3
        rts
rf3:    lda rgl
        jsr p_sdyad
        bcc rf4
        rts
rf4:    lda rk
        bne rf5
        dec rk+1
rf5:    dec rk
        jmp rf_loop
rf_done:
        jsr topcell
        ldy #3
rf6:    lda (cptr),y
        sta rres,y
        dey
        bpl rf6
        sec
        lda vsp
        sbc #4
        sta vsp
        lda vsp+1
        sbc #0
        sta vsp+1
        clc
        rts

; step back one element and push it as a scalar cell
rf_push:
        sec
        lda rptr
        sbc rw
        sta rptr
        lda rptr+1
        sbc #0
        sta rptr+1
        lda rptr
        sta ep
        lda rptr+1
        sta ep+1
        lda rt
        sta cv
        lda #0
        sta cv+1
        sta cv+2
        sta cv+3
        ldy #0
        ldx #1
rp2:    lda (ep),y
        sta cv,x
        iny
        inx
        cpy rw
        bne rp2
        jmp pushcv

; + over BOOL or INT: a 32-bit sum
rr_isum:
        lda #0
        sta risum
        sta risum+1
        sta risum+2
        sta risum+3
        lda rbase
        sta rptr
        lda rbase+1
        sta rptr+1
        lda rn
        sta rk
        lda rn+1
        sta rk+1
ri_l:   lda rk
        ora rk+1
        beq ri_done
        lda rptr
        sta ep
        lda rptr+1
        sta ep+1
        ldy #0
        lda (ep),y
        sta rtl
        lda #0
        sta rth
        sta rte
        lda rt
        beq ri_add
        iny
        lda (ep),y
        sta rth
        bpl ri_add
        lda #$ff
        sta rte
ri_add: clc
        lda risum
        adc rtl
        sta risum
        lda risum+1
        adc rth
        sta risum+1
        lda risum+2
        adc rte
        sta risum+2
        lda risum+3
        adc rte
        sta risum+3
        clc
        lda rptr
        adc rw
        sta rptr
        bcc ri_n1
        inc rptr+1
ri_n1:  lda rk
        bne ri_n2
        dec rk+1
ri_n2:  dec rk
        jmp ri_l
ri_done:
        lda risum+2             ; INT if it fits int16
        cmp risum+3
        bne ri_big
        cmp #0
        beq ri_pos
        cmp #$ff
        bne ri_big
        lda risum+1
        bpl ri_big
        jmp ri_fit
ri_pos: lda risum+1
        bmi ri_big
ri_fit: lda #2
        sta rres
        lda risum
        sta rres+1
        lda risum+1
        sta rres+2
        lda #0
        sta rres+3
        clc
        rts
ri_big: lda #0                  ; too big: a FLOAT, rounded once
        sta sa
        lda risum+3
        bpl ri_b2
        lda #$80
        sta sa
        ldx #0
ri_b1:  lda risum,x
        eor #$ff
        sta risum,x
        inx
        cpx #4
        bne ri_b1
        ldx #0
ri_b3:  inc risum,x
        bne ri_b2
        inx
        cpx #4
        bne ri_b3
ri_b2:  lda #<risum
        sta mp
        lda #>risum
        sta mp+1
        lda #4
        sta mn
        lda #128
        sta mk
        lda #0
        sta mk+1
        jsr mag_round
        bcc *+5
        jmp rf_dom2
        jmp rf_fl

; + over FLOAT: exact fixed-point sum, bit k of FACC weighs 2^(k-143)
rr_fsum:
        ldx #39
        lda #0
rfs0:   sta FACC,x
        dex
        bpl rfs0
        lda rbase
        sta rptr
        lda rbase+1
        sta rptr+1
        lda rn
        sta rk
        lda rn+1
        sta rk+1
rfs_l:  lda rk
        ora rk+1
        bne rfs_1
        jmp rfs_done
rfs_1:  lda rptr
        sta ep
        lda rptr+1
        sta ep+1
        ldy #0
        lda (ep),y
        bne rfs_2
        jmp rfs_next
rfs_2:  sta fexp
        iny
        lda (ep),y
        pha
        and #$80
        sta fneg
        pla
        and #$7f
        ora #$80
        sta fv1
        iny
        lda (ep),y
        sta fv0
        lda #0
        sta fv2
        lda fexp
        sec
        sbc #1
        pha
        and #7
        sta fsh
        pla
        lsr
        lsr
        lsr
        sta fobyte
        ldx fsh
        beq rfs_3
rfs_4:  asl fv0
        rol fv1
        rol fv2
        dex
        bne rfs_4
rfs_3:  clc
        lda #<FACC
        adc fobyte
        sta fp
        lda #>FACC
        adc #0
        sta fp+1
        sec                     ; 37 - fobyte bytes above the first three
        lda #37
        sbc fobyte
        tax
        lda fneg
        bne rfs_sub
        ldy #0
        clc
        lda (fp),y
        adc fv0
        sta (fp),y
        iny
        lda (fp),y
        adc fv1
        sta (fp),y
        iny
        lda (fp),y
        adc fv2
        sta (fp),y
        iny
rfs_a:  lda (fp),y
        adc #0
        sta (fp),y
        iny
        dex
        bne rfs_a
        jmp rfs_next
rfs_sub:
        ldy #0
        sec
        lda (fp),y
        sbc fv0
        sta (fp),y
        iny
        lda (fp),y
        sbc fv1
        sta (fp),y
        iny
        lda (fp),y
        sbc fv2
        sta (fp),y
        iny
rfs_b:  lda (fp),y
        sbc #0
        sta (fp),y
        iny
        dex
        bne rfs_b
rfs_next:
        clc
        lda rptr
        adc rw
        sta rptr
        bcc rfs_n1
        inc rptr+1
rfs_n1: lda rk
        bne rfs_n2
        dec rk+1
rfs_n2: dec rk
        jmp rfs_l
rfs_done:
        lda #0
        sta sa
        lda FACC+39
        bpl rfs_pos
        lda #$80
        sta sa
        ldx #0
rfs_c:  lda FACC,x
        eor #$ff
        sta FACC,x
        inx
        cpx #40
        bne rfs_c
        ldx #0
rfs_i:  inc FACC,x
        bne rfs_pos
        inx
        cpx #40
        bne rfs_i
rfs_pos:
        lda #<FACC
        sta mp
        lda #>FACC
        sta mp+1
        lda #40
        sta mn
        lda #<(-15)
        sta mk
        lda #>(-15)
        sta mk+1
        jsr mag_round
        bcs rf_dom2
rf_fl:  lda #3
        sta rres
        lda fa
        sta rres+1
        lda fa+1
        sta rres+2
        lda fa+2
        sta rres+3
        clc
        rts
rf_dom2: lda #E_DOMAIN
        sec
        rts

; Round a magnitude (mn little-endian bytes at mp, sign in sa) to float24 in fa.
; Its exponent field is 8*hb + 8 - s + mk, hb the top nonzero byte, s the leading
; zero bits of it. Carry set: overflow.
mag_round:
        ldy mn
        dey
mr1:    lda (mp),y
        bne mr2
        dey
        bpl mr1
        lda #0
        sta fa
        sta fa+1
        sta fa+2
        clc
        rts
mr2:    sty mhb
        ldx #0
mr3:    cmp #$80
        bcs mr4
        asl
        inx
        jmp mr3
mr4:    stx msh
        ldx #0                  ; a 5-byte window from the top byte down
mrw:    lda mhb
        stx mtmp
        sec
        sbc mtmp
        bcc mrz
        tay
        lda (mp),y
        jmp mrs
mrz:    lda #0
mrs:    sta mwt,x
        inx
        cpx #5
        bne mrw
        ldx msh
        beq mr_sh0
mrsl:   asl mwt+4
        rol mwt+3
        rol mwt+2
        rol mwt+1
        rol mwt
        dex
        bne mrsl
mr_sh0: lda mwt
        sta ah
        lda mwt+1
        sta al
        lda mwt+2
        sta ag
        lda mwt+3               ; sticky: everything below the guard byte
        ora mwt+4
        sta mtmp
        lda mhb
        sec
        sbc #5
        bcc mr_ns
        tax
        inx
        ldy #0
mr_lo:  lda (mp),y
        ora mtmp
        sta mtmp
        iny
        dex
        bne mr_lo
mr_ns:  lda mtmp
        beq mr_ex
        lda ag
        ora #1
        sta ag
mr_ex:  lda mhb
        sta ex
        lda #0
        sta ex+1
        asl ex
        rol ex+1
        asl ex
        rol ex+1
        asl ex
        rol ex+1
        clc
        lda ex
        adc #8
        sta ex
        bcc mr_e1
        inc ex+1
mr_e1:  sec
        lda ex
        sbc msh
        sta ex
        bcs mr_e2
        dec ex+1
mr_e2:  clc
        lda ex
        adc mk
        sta ex
        lda ex+1
        adc mk+1
        sta ex+1
        jmp round
