; Scalar functions: dyadic + - × ÷ = ≠ < ≤ > ≥ ⌈ ⌊ |, monadic - × ÷ ⌈ ⌊ |.
; Spec: apl64.py dyadic_scalar/_arith/_div/_cmp, monadic_scalar, f_teq..f_ge.
;
; One engine runs every dyadic: shapes are conformed (equal, or scalar
; extension), types checked, a result allocated, then each element goes through
; four routines chosen per operation and operand types: load B, load A, kernel,
; store. Integer arithmetic runs into an INT result; if any element overflows
; int16 the whole operation is redone into a FLOAT result (as the model does).
; Monadic - and ÷ are 0-x and 1÷x with a synthetic scalar left operand.

sdop    = $41
sdta    = $3b
sdtb    = $42
sdar    = $89
sdbr    = WS+$54
sdrr    = WS+$55
sdrt    = WS+$56
sdov    = WS+$57
sdw     = WS+$58
sdres   = WS+$59
sdmode  = WS+$5a
sdstra  = WS+$5b
sdstrb  = WS+$5c
ceq     = $29
clt     = $80
cgt     = $81
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

; Outer product a∘.f b (spec: apl64.py make_outer): p_outer runs the same engine with owa set to
; the width of a's elements. When both operands are vectors the result is a matrix with a row
; per element of a; each row is a pass over b (a's pointer stands still, sdstra = 0).
; With a scalar operand it is the ordinary scalar extension, and owa goes back to 0.
owa     = RV+64                 ; 0, or the element width of a in an outer product
om      = RV+65                 ; (2) elements of b: the length of a pass
otot    = RV+67                 ; (2) elements still to do
opbb    = RV+69                 ; (2) the start of b

sd_lb:  jmp (SDV)
sd_la:  jmp (SDV+2)
sd_k:   jmp (SDV+4)
sd_st:  jmp (SDV+6)

; --- the element loop ------------------------------------------------------------
sd_run: lda owa
        bne so_go
sd_run0: lda sdcnt
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
        jmp sd_run0
sr_done: clc
sr_err: rts

so_go:  lda sdcnt
        sta otot
        lda sdcnt+1
        sta otot+1
        lda sdpb
        sta opbb
        lda sdpb+1
        sta opbb+1
so_row: lda otot
        ora otot+1
        beq sr_done
        lda om
        sta sdcnt
        lda om+1
        sta sdcnt+1
        lda opbb
        sta sdpb
        lda opbb+1
        sta sdpb+1
        jsr sd_run0
        bcs sr_err
        clc
        lda sdpa
        adc owa
        sta sdpa
        bcc so_1
        inc sdpa+1
so_1:   sec
        lda otot
        sbc om
        sta otot
        lda otot+1
        sbc om+1
        sta otot+1
        jmp so_row

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

; ⌈ ⌊ on INT: ia = the larger or smaller of ia, ib
icmp:   sec                     ; N set if ia < ib
        lda ia
        sbc ib
        lda ia+1
        sbc ib+1
        bvc ic1
        eor #$80
ic1:    rts
k_imax: jsr icmp
        bpl k_ikeep
k_icpb: lda ib
        sta ia
        lda ib+1
        sta ia+1
k_ikeep: clc
        rts
k_imin: jsr icmp
        bmi k_ikeep
        bpl k_icpb

; ... on FLOAT: exact order (keycmp), no tolerance
k_fcp:  ldx #2
kf_1:   lda fa,x
        sta ca,x
        lda fb,x
        sta cb,x
        dex
        bpl kf_1
        jmp keycmp
k_fmax: jsr k_fcp
        cmp #$ff
        bne k_fkeep
k_fcpb: lda fb
        sta fa
        lda fb+1
        sta fa+1
        lda fb+2
        sta fa+2
k_fkeep: clc
        rts
k_fmin: jsr k_fcp
        cmp #1
        beq k_fcpb
        clc
        rts

; magnitude: |ib|, INT overflow (-32768) redoes the array in FLOAT
k_iabs: lda ib
        sta ia
        lda ib+1
        sta ia+1
        bpl kia_r
        sec
        lda #0
        sbc ib
        sta ia
        lda #0
        sbc ib+1
        sta ia+1
        bpl kia_r
        lda #1
        sta sdov
kia_r:  clc
        rts
k_fabs: lda fb
        sta fa
        lda fb+1
        and #$7f
        sta fa+1
        lda fb+2
        sta fa+2
        clc
        rts

; the logical functions: ∧ (op 14), ∨ (15) and ~ (16, its left operand is a 0 put there); each operand
; must be 0 or 1. The result is left in sdres for st_b.
k_lgc_i: lda ia+1
        ora ib+1
        bne kl_dom
        lda ia
        cmp #2
        bcs kl_dom
        lda ib
        cmp #2
        bcs kl_dom
        lda ib
        ldx ia
        jmp kl_op
k_lgc_f: ldx #0                 ; A = fa's bit, then fb's
        jsr fbit
        bcs kl_dom
        pha
        ldx #3
        jsr fbit
        bcs kl_bad
        tay
        pla
        tax
        tya                     ; A = B's bit, X = A's bit
kl_op:  ldy sdop
        cpy #16
        beq kl_not
        cpy #15
        beq kl_or
        stx sdres               ; and
        and sdres
        jmp kl_set
kl_or:  stx sdres
        ora sdres
        jmp kl_set
kl_not: eor #1
kl_set: sta sdres
        clc
        rts
kl_bad: pla
kl_dom: lda #E_DOMAIN
        sec
        rts
; carry set unless the float at fa+X is 0 or 1, then A = 0 or 1
fbit:   lda fa,x
        beq fb_z
        cmp #$81
        bne fb_bad
        lda fa+1,x
        ora fa+2,x
        bne fb_bad
        lda #1
        clc
        rts
fb_z:   clc
        rts
fb_bad: sec
        rts

; residue on INT: ia | ib = ib mod ia with the sign of ia; 0 | b is b
; ua = |ia|, ub = |ib|, r = ub mod ua; the same signs give r, opposite signs ua - r (0 stays 0);
; the sign of ia is put on the result
rsa     = WS+$ed
rsb     = WS+$ee
rrem    = WS+$ef                ; (2)
k_ires: lda ia
        ora ia+1
        bne kr_1
        lda ib
        sta ia
        lda ib+1
        sta ia+1
        clc
        rts
kr_1:   lda ia+1
        and #$80
        sta rsa
        bpl kr_2
        sec
        lda #0
        sbc ia
        sta ia
        lda #0
        sbc ia+1
        sta ia+1
kr_2:   lda ib+1
        and #$80
        sta rsb
        bpl kr_3
        sec
        lda #0
        sbc ib
        sta ib
        lda #0
        sbc ib+1
        sta ib+1
kr_3:   lda #0                  ; rrem = ub mod ua by shifting ub in and subtracting
        sta rrem
        sta rrem+1
        ldx #16
kr_4:   asl ib
        rol ib+1
        rol rrem
        rol rrem+1
        sec
        lda rrem
        sbc ia
        tay
        lda rrem+1
        sbc ia+1
        bcc kr_5
        sta rrem+1
        sty rrem
kr_5:   dex
        bne kr_4
        lda rrem
        ora rrem+1
        beq kr_z
        lda rsa
        eor rsb
        bpl kr_6                ; the same sign: r itself
        sec                     ; opposite signs: ua - r
        lda ia
        sbc rrem
        sta rrem
        lda ia+1
        sbc rrem+1
        sta rrem+1
kr_6:   lda rrem
        sta ia
        lda rrem+1
        sta ia+1
        lda rsa
        bpl kr_ok
        sec
        lda #0
        sbc ia
        sta ia
        lda #0
        sbc ia+1
        sta ia+1
kr_ok:  clc
        rts
kr_z:   lda #0
        sta ia
        sta ia+1
        clc
        rts

; residue on FLOAT: the model's f_residue. fa = A, fb = B; ca = A, cb = B are kept.
k_fres: lda fa
        bne kq_1
        lda fb                  ; A = 0: the result is B
        sta fa
        lda fb+1
        sta fa+1
        lda fb+2
        sta fa+2
        clc
        rts
kq_1:   ldx #2
kq_2:   lda fa,x
        sta ca,x
        lda fb,x
        sta cb,x
        dex
        bpl kq_2
        ldx #2                  ; q = floor(B / A)
kq_3:   lda cb,x
        sta fa,x
        lda ca,x
        sta fb,x
        dex
        bpl kq_3
        jsr f_div
        bcs kq_dom
        jsr f_floor
        ldx #2                  ; A * q
kq_4:   lda ca,x
        sta fb,x
        dex
        bpl kq_4
        jsr f_mul
        bcs kq_dom
        ldx #2                  ; r = B - A * q
kq_5:   lda fa,x
        sta fb,x
        lda cb,x
        sta fa,x
        dex
        bpl kq_5
        jsr f_sub
        bcs kq_dom
        lda fa
        beq kq_done
        lda fa+1                ; a sign different from A's: r + A
        eor ca+1
        bpl kq_same
        ldx #2
kq_6:   lda ca,x
        sta fb,x
        dex
        bpl kq_6
        jsr f_add
        bcs kq_dom
kq_done: clc
        rts
kq_same: ldx #2                 ; the same sign: r - A if |r| >= |A|
kq_7:   lda fa,x
        sta cb,x
        dex
        bpl kq_7
        jsr magcmp              ; |ca| against |cb|: 1 if |A| > |r|
        cmp #1
        beq kq_done
        ldx #2
kq_8:   lda ca,x
        sta fb,x
        dex
        bpl kq_8
        jsr f_sub
        bcs kq_dom
        clc
        rts
kq_dom: lda #E_DOMAIN
        sec
        rts

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
; indexed by the operation for + - × ÷ (0-3), and by the operation - 6 for ⌈ ⌊ | and the
; magnitude (10-13, the engine's four extra operations)
kint_l: .byte <k_iadd, <k_isub, <k_imul, <k_iadd, <k_imax, <k_imin, <k_ires, <k_iabs
kint_h: .byte >k_iadd, >k_isub, >k_imul, >k_iadd, >k_imax, >k_imin, >k_ires, >k_iabs
kflt_l: .byte <k_fadd, <k_fsub, <k_fmul, <k_fdiv, <k_fmax, <k_fmin, <k_fres, <k_fabs
kflt_h: .byte >k_fadd, >k_fsub, >k_fmul, >k_fdiv, >k_fmax, >k_fmin, >k_fres, >k_fabs
lai_l:  .byte <la_bool_i, <sd_nop, <la_int_i, <sd_nop
lai_h:  .byte >la_bool_i, >sd_nop, >la_int_i, >sd_nop
laf_l:  .byte <la_bool_f, <sd_nop, <la_int_f, <la_flt
laf_h:  .byte >la_bool_f, >sd_nop, >la_int_f, >la_flt
lbi_l:  .byte <lb_bool_i, <sd_nop, <lb_int_i, <sd_nop
lbi_h:  .byte >lb_bool_i, >sd_nop, >lb_int_i, >sd_nop
lbf_l:  .byte <lb_bool_f, <sd_nop, <lb_int_f, <lb_flt
lbf_h:  .byte >lb_bool_f, >sd_nop, >lb_int_f, >lb_flt

; Y = the kernel table index of sdop
opidx:  ldy sdop
        cpy #10
        bcc oi_r
        tya
        sec
        sbc #6
        tay
oi_r:   rts

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
        jsr opidx
        lda kint_l,y
        sta SDV+4
        lda kint_h,y
        sta SDV+5
        jmp sv_li
sv_n0:  cpx #1
        bne sv_n1
        jsr opidx
        lda kflt_l,y
        sta SDV+4
        lda kflt_h,y
        sta SDV+5
        jmp sv_lf
sv_n1:  cpx #2
        bne sv_n2
        lda #<k_cmp_i
        ldy #>k_cmp_i
        ldx sdop
        cpx #14
        bcc sv_k1
        lda #<k_lgc_i
        ldy #>k_lgc_i
sv_k1:  sta SDV+4
        sty SDV+5
        jmp sv_li
sv_n2:  lda #<k_cmp_f
        ldy #>k_cmp_f
        ldx sdop
        cpx #14
        bcc sv_k2
        lda #<k_lgc_f
        ldy #>k_lgc_f
sv_k2:  sta SDV+4
        sty SDV+5
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
p_outer:
        sta sdop
        lda #1
        bne sd_ent
p_sdyad:
        sta sdop
        lda #0
sd_ent: sta owa
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
        lda owa
        bne so_chk
        jmp sc_std
so_chk: lda sdar
        beq so_off              ; a scalar operand: plain scalar extension
        lda sdbr
        bne so_two
so_off: lda #0
        sta owa
        jmp sc_std
so_two: clc                     ; both are arrays: LIMIT ERROR unless both are vectors
        lda sdar
        adc sdbr
        cmp #3
        bcc so_3
        lda #E_LIMIT
        sec
        rts
so_3:   lda sdan
        sta p0
        lda sdan+1
        sta p1
        lda sdbn
        sta bl
        lda sdbn+1
        sta bh
        jsr mul16
        lda p2
        ora p3
        beq so_4
        lda #E_WSFULL           ; over 65535 elements: no need to look at them
        sec
        rts
so_4:   lda p0
        sta sdn
        lda p1
        sta sdn+1
        lda sdbn
        sta om
        lda sdbn+1
        sta om+1
        lda sdan
        sta sdrd0
        lda sdan+1
        sta sdrd0+1
        lda sdbn
        sta sdrd1
        lda sdbn+1
        sta sdrd1+1
        lda #2
        sta sdrr
        ldx sdta
        lda WIDTHT,x
        sta owa
        lda #0
        sta sdstra
        ldx sdtb
        lda WIDTHT,x
        sta sdstrb
        jmp sc_types
sc_std:
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
        bcc ty_ar
        cmp #10
        bcc ty_cmp
        cmp #14                 ; 14-16, the logical functions, give BOOL like the comparisons
        bcs ty_cmp
ty_ar:  lda sdta
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

; --- floor and ceiling ---------------------------------------------------------------------------------
; flr_q: the floor of fa. A = 0: the result is a small whole number, magnitude in ia and the sign
; in bit 7 of sgn (zero has ia = 0); A = 1: fa is 2^16 or more, so it is whole already.
flw     = WS+$f0
pfm     = WS+$f1                ; 0 floor, 1 ceiling
pfa     = WS+$f2                ; every result fits int16
flr_q:  lda fa
        cmp #144
        bcs fq_big
        cmp #128
        bcc fq_small
        eor #$ff                ; the shift: 144 - exponent, 1 to 16
        clc
        adc #145
        tax
        lda fa+1
        and #$80
        sta sgn
        lda fa+1
        and #$7f
        ora #$80
        sta ia+1
        lda fa+2
        sta ia
        lda #0
        sta flw
fq_l:   lsr ia+1
        ror ia
        bcc fq_n
        lda #1
        sta flw
fq_n:   dex
        bne fq_l
        lda flw                 ; below zero, bits lost: one more
        beq fq_d
        lda sgn
        bpl fq_d
        inc ia
        bne fq_d
        inc ia+1
fq_d:   lda #0
        rts
fq_small:
        lda #0                  ; below one half: 0, or -1 if negative and not zero
        sta ia+1
        sta sgn
        sta ia
        lda fa
        beq fq_d
        lda fa+1
        and #$80
        sta sgn
        bpl fq_d
        lda #1
        sta ia
        bne fq_d
fq_big: lda #1
        rts

f_floor:
        jsr flr_q
        cmp #1
        beq ff_r
        jmp m_to_f
ff_r:   rts

; monadic |: the magnitude, through the engine with a 0 on the left
p_abs:  lda #0
        ldx #13
        jmp mo_const

; monadic ~: 1-x for a 0 or 1, through the engine (op 16) with a 0 on the left
p_not:  lda #0
        ldx #16
        jmp mo_const
