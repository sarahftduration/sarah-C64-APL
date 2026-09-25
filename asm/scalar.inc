; Scalar functions: dyadic + - × ÷ = ≠ < ≤ > ≥, monadic - × ÷.
; Spec: apl64.py dyadic_scalar/_arith/_div/_cmp, monadic_scalar, f_teq..f_ge.
;
; One engine runs every dyadic: shapes are conformed (equal, or scalar
; extension), types checked, a result allocated, then each element goes through
; four routines chosen per operation and operand types: load B, load A, kernel,
; store. Integer arithmetic runs into an INT result; if any element overflows
; int16 the whole operation is redone into a FLOAT result (as the model does).
; Monadic - and ÷ are 0-x and 1÷x with a synthetic scalar left operand.

SDV     = $5d00                 ; vectors: load B, load A, kernel, store
sdop    = WS+$50
sdta    = WS+$51
sdtb    = WS+$52
sdar    = WS+$53
sdbr    = WS+$54
sdrr    = WS+$55
sdrt    = WS+$56
sdov    = WS+$57
sdw     = WS+$58
sdres   = WS+$59
sdmode  = WS+$5a
sdstra  = WS+$5b
sdstrb  = WS+$5c
ceq     = WS+$5d
clt     = WS+$60
cgt     = WS+$61
sdan    = WS+$62
sdbn    = WS+$64
ca      = WS+$94
cb      = WS+$97
cdx     = WS+$9a
kna     = WS+$9b
knb     = WS+$9c
ms      = WS+$9d
mt      = WS+$9e
sdav0   = WS+$a0
sdav1   = WS+$a2
sdbv0   = WS+$a4
sdbv1   = WS+$a6
sdrd0   = WS+$a8
sdrd1   = WS+$aa
sdn     = WS+$ac
sdcnt   = WS+$ae

sd_lb:  jmp (SDV)
sd_la:  jmp (SDV+2)
sd_k:   jmp (SDV+4)
sd_st:  jmp (SDV+6)

; --- the element loop ------------------------------------------------------------
sd_run: lda sdcnt
        ora sdcnt+1
        beq sr_done
        jsr sd_lb
        jsr sd_la
        jsr sd_k
        bcs sr_err
        jsr sd_st
        clc
        lda sdpa
        adc sdstra
        sta sdpa
        bcc sr1
        inc sdpa+1
sr1:    clc
        lda sdpb
        adc sdstrb
        sta sdpb
        bcc sr2
        inc sdpb+1
sr2:    clc
        lda dp
        adc sdw
        sta dp
        bcc sr3
        inc dp+1
sr3:    lda sdcnt
        bne sr4
        dec sdcnt+1
sr4:    dec sdcnt
        jmp sd_run
sr_done: clc
sr_err: rts

; --- loaders -------------------------------------------------------------------------
sd_nop: rts

la_bool_i:
        ldy #0
        lda (sdpa),y
        sta ia
        sty ia+1
        rts
la_int_i:
        ldy #0
        lda (sdpa),y
        sta ia
        iny
        lda (sdpa),y
        sta ia+1
        rts
la_bool_f:
        jsr la_bool_i
        jmp i_to_f
la_int_f:
        jsr la_int_i
        jmp i_to_f
la_flt: ldy #0
        lda (sdpa),y
        sta fa
        iny
        lda (sdpa),y
        sta fa+1
        iny
        lda (sdpa),y
        sta fa+2
        rts
lb_bool_i:
        ldy #0
        lda (sdpb),y
        sta ib
        sty ib+1
        rts
lb_int_i:
        ldy #0
        lda (sdpb),y
        sta ib
        iny
        lda (sdpb),y
        sta ib+1
        rts
lb_bool_f:
        ldy #0
        lda (sdpb),y
        sta ia
        sty ia+1
        jmp lb_tof
lb_int_f:
        ldy #0
        lda (sdpb),y
        sta ia
        iny
        lda (sdpb),y
        sta ia+1
lb_tof: jsr i_to_f
        lda fa
        sta fb
        lda fa+1
        sta fb+1
        lda fa+2
        sta fb+2
        rts
lb_flt: ldy #0
        lda (sdpb),y
        sta fb
        iny
        lda (sdpb),y
        sta fb+1
        iny
        lda (sdpb),y
        sta fb+2
        rts

; --- kernels ---------------------------------------------------------------------------
k_iadd: jsr i_add
        jmp k_iov
k_isub: jsr i_sub
        jmp k_iov
k_imul: jsr i_mul
k_iov:  bcc k_iok
        lda #1
        sta sdov
k_iok:  clc
        rts

k_fadd: jsr f_add
        jmp k_fchk
k_fsub: jsr f_sub
        jmp k_fchk
k_fmul: jsr f_mul
k_fchk: bcc k_fok
        lda #E_DOMAIN
        sec
k_fok:  rts

k_fdiv: lda fb                  ; x ÷ 0 is DOMAIN ERROR, but 0 ÷ 0 is 1
        bne kd1
        lda fa
        bne kd_dom
        lda #$81
        sta fa
        lda #0
        sta fa+1
        sta fa+2
        clc
        rts
kd1:    jsr f_div
        bcc kd_ok
kd_dom: lda #E_DOMAIN
        sec
kd_ok:  rts

; comparison kernels set ceq/clt/cgt (equal, less, greater) and end in cmp_map
k_cmp_i:
        lda #0
        sta ceq
        sta clt
        sta cgt
        lda ia
        cmp ib
        bne kci1
        lda ia+1
        cmp ib+1
        bne kci1
        lda #1
        sta ceq
        jmp cmp_map
kci1:   sec
        lda ia
        sbc ib
        lda ia+1
        sbc ib+1
        bvc kci2
        eor #$80
kci2:   bmi kci_lt
        lda #1
        sta cgt
        jmp cmp_map
kci_lt: lda #1
        sta clt
        jmp cmp_map

k_cmp_c:
        lda #0
        sta ceq
        sta clt
        sta cgt
        lda sdta
        cmp #1
        bne kcc_r
        lda sdtb
        cmp #1
        bne kcc_r
        ldy #0
        lda (sdpa),y
        cmp (sdpb),y
        bne kcc_r
        lda #1
        sta ceq
kcc_r:  jmp cmp_map

k_cmp_f:
        jsr f_cmp3
        bcc cmp_map
        lda #E_DOMAIN
        sec
        rts

; sdres = the comparison selected by sdop (4 = ≠ ... 9 ≥) from ceq/clt/cgt
cmp_map:
        lda sdop
        sec
        sbc #4
        tax
        beq cm_eq
        dex
        beq cm_ne
        dex
        beq cm_lt
        dex
        beq cm_le
        dex
        beq cm_gt
        lda ceq                 ; ≥ : equal or greater
        ora cgt
        jmp cm_set
cm_eq:  lda ceq
        jmp cm_set
cm_ne:  lda ceq
        eor #1
        jmp cm_set
cm_lt:  lda ceq                 ; < : not equal, and less
        bne cm_zero
        lda clt
        jmp cm_set
cm_le:  lda ceq
        ora clt
        jmp cm_set
cm_gt:  lda ceq
        bne cm_zero
        lda cgt
        jmp cm_set
cm_zero: lda #0
cm_set: sta sdres
        clc
        rts

; --- stores -----------------------------------------------------------------------------------
st_i:   ldy #0
        lda ia
        sta (dp),y
        iny
        lda ia+1
        sta (dp),y
        rts
st_f:   ldy #0
        lda fa
        sta (dp),y
        iny
        lda fa+1
        sta (dp),y
        iny
        lda fa+2
        sta (dp),y
        rts
st_b:   ldy #0
        lda sdres
        sta (dp),y
        rts

; --- float comparison: the model's f_teq / _fkey -------------------------------------
; In: fa, fb. Out: carry clear with ceq (tolerantly equal), clt/cgt (key order);
; carry set: the subtraction in the tolerance test overflowed (DOMAIN ERROR).
f_cmp3: ldx #2
c3s:    lda fa,x
        sta ca,x
        lda fb,x
        sta cb,x
        dex
        bpl c3s
        lda #0
        sta ceq
        sta clt
        sta cgt
        lda ca
        cmp cb
        bne c3t
        lda ca+1
        cmp cb+1
        bne c3t
        lda ca+2
        cmp cb+2
        bne c3t
        lda #1
        sta ceq
        jmp c3k
c3t:    jsr f_sub
        bcc c3t2
        lda #E_DOMAIN
        sec
        rts
c3t2:   lda fa
        bne c3t3
        lda #1
        sta ceq
        jmp c3k
c3t3:   sta cdx
        lda ca                  ; exp(a-b) <= max(exp a, exp b) - 14
        cmp cb
        bcs c3m
        lda cb
c3m:    sec
        sbc #14
        bcc c3k
        cmp cdx
        bcc c3k
        lda #1
        sta ceq
c3k:    jsr keycmp
        cmp #0
        beq c3d
        cmp #1
        bne c3lt
        lda #1
        sta cgt
        jmp c3d
c3lt:   lda #1
        sta clt
c3d:    clc
        rts

; A = 0, 1 or $ff as key(ca) is equal to, above or below key(cb)
keycmp: ldx #0
        lda ca
        beq kc1
        lda ca+1
        bpl kc1
        ldx #1
kc1:    stx kna
        ldx #0
        lda cb
        beq kc2
        lda cb+1
        bpl kc2
        ldx #1
kc2:    stx knb
        lda kna
        cmp knb
        beq kc_same
        lda kna
        bne kc_less
        lda #1
        rts
kc_less: lda #$ff
        rts
kc_same: jsr magcmp
        ldx kna
        beq kc_r
        eor #$ff                ; both negative: the order reverses
        clc
        adc #1
kc_r:   rts

; A = 0, 1 or $ff as |ca| is equal to, above or below |cb| (sign bit ignored)
magcmp: lda ca
        cmp cb
        bcc mg_lt
        bne mg_gt
        lda ca+1
        and #$7f
        sta ms
        lda cb+1
        and #$7f
        sta mt
        lda ms
        cmp mt
        bcc mg_lt
        bne mg_gt
        lda ca+2
        cmp cb+2
        bcc mg_lt
        bne mg_gt
        lda #0
        rts
mg_gt:  lda #1
        rts
mg_lt:  lda #$ff
        rts

; --- tables for choosing routines by mode and type -------------------------------------------------
; modes: 0 INT arithmetic, 1 FLOAT arithmetic and ÷, 2 compare ints, 3 compare floats, 4 compare CHAR
mode_rt: .byte 2, 3, 0, 0, 0
mode_w:  .byte 2, 3, 1, 1, 1
mode_stl: .byte <st_i, <st_f, <st_b, <st_b, <st_b
mode_sth: .byte >st_i, >st_f, >st_b, >st_b, >st_b
kint_l: .byte <k_iadd, <k_isub, <k_imul
kint_h: .byte >k_iadd, >k_isub, >k_imul
kflt_l: .byte <k_fadd, <k_fsub, <k_fmul, <k_fdiv
kflt_h: .byte >k_fadd, >k_fsub, >k_fmul, >k_fdiv
lai_l:  .byte <la_bool_i, <sd_nop, <la_int_i, <sd_nop
lai_h:  .byte >la_bool_i, >sd_nop, >la_int_i, >sd_nop
laf_l:  .byte <la_bool_f, <sd_nop, <la_int_f, <la_flt
laf_h:  .byte >la_bool_f, >sd_nop, >la_int_f, >la_flt
lbi_l:  .byte <lb_bool_i, <sd_nop, <lb_int_i, <sd_nop
lbi_h:  .byte >lb_bool_i, >sd_nop, >lb_int_i, >sd_nop
lbf_l:  .byte <lb_bool_f, <sd_nop, <lb_int_f, <lb_flt
lbf_h:  .byte >lb_bool_f, >sd_nop, >lb_int_f, >lb_flt

; install the four routines for sdmode / sdop / sdta / sdtb; set sdrt and sdw
sd_setvecs:
        ldx sdmode
        lda mode_rt,x
        sta sdrt
        lda mode_w,x
        sta sdw
        lda mode_stl,x
        sta SDV+6
        lda mode_sth,x
        sta SDV+7
        cpx #4
        bne sv_n4
        lda #<sd_nop
        sta SDV
        sta SDV+2
        lda #>sd_nop
        sta SDV+1
        sta SDV+3
        lda #<k_cmp_c
        sta SDV+4
        lda #>k_cmp_c
        sta SDV+5
        rts
sv_n4:  cpx #0
        bne sv_n0
        ldy sdop
        lda kint_l,y
        sta SDV+4
        lda kint_h,y
        sta SDV+5
        jmp sv_li
sv_n0:  cpx #1
        bne sv_n1
        ldy sdop
        lda kflt_l,y
        sta SDV+4
        lda kflt_h,y
        sta SDV+5
        jmp sv_lf
sv_n1:  cpx #2
        bne sv_n2
        lda #<k_cmp_i
        sta SDV+4
        lda #>k_cmp_i
        sta SDV+5
        jmp sv_li
sv_n2:  lda #<k_cmp_f
        sta SDV+4
        lda #>k_cmp_f
        sta SDV+5
sv_lf:  ldy sdta
        lda laf_l,y
        sta SDV+2
        lda laf_h,y
        sta SDV+3
        ldy sdtb
        lda lbf_l,y
        sta SDV
        lda lbf_h,y
        sta SDV+1
        rts
sv_li:  ldy sdta
        lda lai_l,y
        sta SDV+2
        lda lai_h,y
        sta SDV+3
        ldy sdtb
        lda lbi_l,y
        sta SDV
        lda lbi_h,y
        sta SDV+1
        rts

; --- allocate the result: a scalar cell or an array of sdrt, shape sdrr/sdrd0/sdrd1 ---------
sd_alloc:
        lda sdrr
        bne sa_arr
        lda sdrt
        sta cv
        lda #0
        sta cv+1
        sta cv+2
        sta cv+3
        lda #<(cv+1)
        sta dp
        lda #>(cv+1)
        sta dp+1
        clc
        rts
sa_arr: lda sdrt
        sta nt
        lda sdrr
        sta nrk
        lda sdn
        sta nn
        lda sdn+1
        sta nn+1
        lda sdrd0
        sta nd0
        lda sdrd0+1
        sta nd0+1
        lda sdrd1
        sta nd1
        lda sdrd1+1
        sta nd1+1
        jmp newarr

; re-derive the operand pointers (an allocation may have moved the arrays) and the count
sd_prep:
        jsr topcell
        jsr getval
        lda vp
        sta sdpa
        lda vp+1
        sta sdpa+1
        jsr secondcell
        jsr getval
        lda vp
        sta sdpb
        lda vp+1
        sta sdpb+1
        lda sdn
        sta sdcnt
        lda sdn+1
        sta sdcnt+1
        rts

; --- the dyadic scalar function; A = operation index 0..9 ---------------------------------------
p_sdyad:
        sta sdop
        jsr topcell             ; left operand
        jsr getval
        lda vt
        sta sdta
        lda vrk
        sta sdar
        lda vn
        sta sdan
        lda vn+1
        sta sdan+1
        lda vs0
        sta sdav0
        lda vs0+1
        sta sdav0+1
        lda vs1
        sta sdav1
        lda vs1+1
        sta sdav1+1
        jsr secondcell          ; right operand
        jsr getval
        lda vt
        sta sdtb
        lda vrk
        sta sdbr
        lda vn
        sta sdbn
        lda vn+1
        sta sdbn+1
        lda vs0
        sta sdbv0
        lda vs0+1
        sta sdbv0+1
        lda vs1
        sta sdbv1
        lda vs1+1
        sta sdbv1+1
        ; conform: equal shapes, or one scalar
        lda sdar
        cmp sdbr
        bne sc_ne
        lda sdav0
        cmp sdbv0
        bne sc_ne
        lda sdav0+1
        cmp sdbv0+1
        bne sc_ne
        lda sdav1
        cmp sdbv1
        bne sc_ne
        lda sdav1+1
        cmp sdbv1+1
        bne sc_ne
        ldx sdta
        lda WIDTHT,x
        sta sdstra
        ldx sdtb
        lda WIDTHT,x
        sta sdstrb
        lda sdar
        sta sdrr
        jmp sc_fromA
sc_ne:  lda sdar
        bne sc_anz
        lda #0                  ; scalar left: the right operand's shape
        sta sdstra
        ldx sdtb
        lda WIDTHT,x
        sta sdstrb
        lda sdbr
        sta sdrr
        lda sdbn
        sta sdn
        lda sdbn+1
        sta sdn+1
        lda sdbv0
        sta sdrd0
        lda sdbv0+1
        sta sdrd0+1
        lda sdbv1
        sta sdrd1
        lda sdbv1+1
        sta sdrd1+1
        jmp sc_types
sc_anz: lda sdbr
        bne sc_bnz
        lda #0                  ; scalar right: the left operand's shape
        sta sdstrb
        ldx sdta
        lda WIDTHT,x
        sta sdstra
        lda sdar
        sta sdrr
        jmp sc_fromA
sc_bnz: lda sdar
        cmp sdbr
        beq sc_len
        lda #E_RANK
        sec
        rts
sc_len: lda #E_LENGTH
        sec
        rts
sc_fromA:
        lda sdan
        sta sdn
        lda sdan+1
        sta sdn+1
        lda sdav0
        sta sdrd0
        lda sdav0+1
        sta sdrd0+1
        lda sdav1
        sta sdrd1
        lda sdav1+1
        sta sdrd1+1
sc_types:
        lda sdop                ; CHAR: only = and ≠ accept it
        cmp #4
        bcs ty_cmp
        lda sdta
        cmp #1
        beq ty_dom
        lda sdtb
        cmp #1
        beq ty_dom
        cmp #3
        beq ty_flt
        lda sdta
        cmp #3
        beq ty_flt
        lda sdop
        cmp #3
        beq ty_flt
        lda #0                  ; mode 0: INT arithmetic
        beq ty_set
ty_flt: lda #1
        bne ty_set
ty_cmp: lda sdta
        cmp #1
        beq ty_c
        lda sdtb
        cmp #1
        beq ty_c
        lda sdta
        cmp #3
        beq ty_f
        lda sdtb
        cmp #3
        beq ty_f
        lda #2
        bne ty_set
ty_f:   lda #3
        bne ty_set
ty_c:   lda sdop
        cmp #6
        bcs ty_dom
        lda #4
ty_set: sta sdmode
        jmp sd_go
ty_dom: lda #E_DOMAIN
        sec
        rts

sd_go:  lda sdmode
        bne sg_notint
        lda #0                  ; INT arithmetic, redone in FLOAT on overflow
        sta sdov
        jsr sd_setvecs
        jsr sd_alloc
        bcc sg_i1
        rts
sg_i1:  jsr sd_prep
        jsr sd_run
        lda sdov
        beq sg_fin
        lda #1
        sta sdmode
        jsr sd_setvecs
        jsr sd_alloc
        bcc sg_i2
        rts
sg_i2:  jsr sd_prep
        jsr sd_run
        bcc sg_fin
        rts
sg_fin: jmp setdy
sg_notint:
        jsr sd_setvecs
        jsr sd_alloc
        bcc sg_go
        cmp #E_WSFULL           ; the model computes before it checks the size, so a
        bne sg_ret              ; DOMAIN ERROR from any element wins over WS FULL
        ldx sdmode
        cpx #1
        beq sg_dry
        cpx #3
        bne sg_ws
sg_dry: lda #<sd_nop
        sta SDV+6
        lda #>sd_nop
        sta SDV+7
        jsr sd_prep
        jsr sd_run
        bcs sg_ret
sg_ws:  lda #E_WSFULL
        sec
sg_ret: rts
sg_go:  jsr sd_prep
        jsr sd_run
        bcc sg_fin
        rts

; --- monadic - and ÷: 0-x and 1÷x ---------------------------------------------------------------
p_neg:  lda #0
        ldx #1
        bne mo_const
p_recip: lda #1
        ldx #3
mo_const:
        stx sdop
        sta cv+1
        lda #2                  ; a scalar INT constant on top: it is the left operand
        sta cv
        lda #0
        sta cv+2
        sta cv+3
        jsr pushcv
        bcc mo_go
        rts
mo_go:  lda sdop
        jmp p_sdyad

; --- monadic ×: signum, always INT ----------------------------------------------------------------
p_signum:
        jsr topcell
        jsr getval
        lda vt
        cmp #1
        bne sg1
        lda #E_DOMAIN
        sec
        rts
sg1:    lda vrk
        bne sg_arr
        lda #2
        sta cv
        lda #0
        sta cv+1
        sta cv+2
        sta cv+3
        lda #<(cv+1)
        sta dp
        lda #>(cv+1)
        sta dp+1
        jmp sg_fill
sg_arr: lda #2
        sta nt
        lda vrk
        sta nrk
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
        bcc sg_a2
        rts
sg_a2:  jsr topcell
        jsr getval
sg_fill:
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        lda vn
        sta qcnt
        lda vn+1
        sta qcnt+1
sgl:    lda qcnt
        ora qcnt+1
        beq sg_done
        ldy #0
        lda vt
        beq sgb
        cmp #2
        beq sgi
        lda (ep),y              ; FLOAT: zero has exponent 0
        beq sg_zero
        iny
        lda (ep),y
        bmi sg_neg
        jmp sg_pos
sgb:    lda (ep),y
        beq sg_zero
        jmp sg_pos
sgi:    lda (ep),y
        iny
        ora (ep),y
        beq sg_zero
        lda (ep),y
        bmi sg_neg
sg_pos: lda #1
        ldx #0
        jmp sg_put
sg_neg: lda #$ff
        tax
        jmp sg_put
sg_zero: lda #0
        tax
sg_put: ldy #0
        sta (dp),y
        iny
        txa
        sta (dp),y
        clc
        lda dp
        adc #2
        sta dp
        bcc sg_p1
        inc dp+1
sg_p1:  ldx vt
        clc
        lda ep
        adc WIDTHT,x
        sta ep
        bcc sg_p2
        inc ep+1
sg_p2:  lda qcnt
        bne sg_p3
        dec qcnt+1
sg_p3:  dec qcnt
        jmp sgl
sg_done: jmp setmon
