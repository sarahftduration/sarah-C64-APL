; Decode and encode: B⊥V and B⊤V. Spec: apl64.py decode, encode. An overlay (see overlay.inc), entered
; through s_decode/s_encode. Dyadic only (apply_mon has no entry for either token, so a monadic call is
; NONCE ERROR for free). B (the left operand, topcell) is rank 0 or 1; its elements and V's are read one
; at a time with elemaddr and combined with the scalar engine (p_sdyad), exactly as they would be inline,
; so int16 overflow promotes to FLOAT exactly as it would there. Nothing here builds a whole-array
; operand: every step is a single scalar pair, kept off the value stack in bc_bi/bc_r/bc_tmp between
; p_sdyad calls (which pop what they are given), and pushed fresh each time it is needed again.

; The variables live in this image, like inner product's (asm/inner.inc): plain bytes, not WS+ scratch,
; since WS is already fully claimed by resident code and every other overlay put together and nothing
; is free there. Nothing here is executed (every entry point is a label below, never the top of the file).
bc_bt:   .byte 0                ; B: type, rank
bc_brk:  .byte 0
bc_bn:   .byte 0, 0              ; (2) count
bc_bp:   .byte 0, 0              ; (2) data pointer
bc_vt:   .byte 0                ; V: type, rank
bc_vrk:  .byte 0
bc_vn:   .byte 0, 0              ; (2) count
bc_vs0:  .byte 0, 0              ; (2) dimensions
bc_vs1:  .byte 0, 0              ; (2)
bc_vp:   .byte 0, 0              ; (2) data pointer
bc_n:    .byte 0, 0              ; (2) the digit count
bc_k:    .byte 0, 0              ; (2) decode: columns of a matrix V; encode: elements of V
bc_i:    .byte 0, 0              ; (2) the digit position
bc_j:    .byte 0, 0              ; (2) the column (decode) or value (encode) being worked on
bc_vstep: .byte 0, 0             ; (2) decode: V's index is i*bc_vstep + bc_vbase
bc_vbase: .byte 0, 0             ; (2)
bc_idx:  .byte 0, 0              ; (2) element index, into whichever array elemaddr is reading
bc_bi:   .byte 0, 0, 0, 0        ; (4) a scalar cell: the radix just fetched
bc_r:    .byte 0, 0, 0, 0        ; (4) a scalar cell: the running total (decode) or what is left (encode)
bc_tmp:  .byte 0, 0, 0, 0        ; (4) a scalar cell: the latest result off the value stack
bc_rt:   .byte 0                 ; the result array's current type (widened as bigger elements arrive)
bc_rc:   .byte 0, 0              ; (2) its cell (still on the value stack, above the operands)
bc_zero: .byte 0                 ; encode: this digit's radix was 0 (it absorbed everything left)
bc_nrk:  .byte 0                 ; the result array's rank, count and dimensions, fixed once at allocation
bc_nn:   .byte 0, 0              ; (2)
bc_nd0:  .byte 0, 0              ; (2)
bc_nd1:  .byte 0, 0              ; (2)

; --- shared bits ------------------------------------------------------------------------------------

; Fetch element bc_idx of an array (its base already in xbase, its width in X) as a scalar cell into
; bc_tmp: the tag byte (A, the type) then the width's worth of data, the rest of the 4 bytes zeroed.
bc_getelem:
        sta bc_tmp
        stx xw
        lda bc_idx
        sta im
        lda bc_idx+1
        sta im+1
        lda #0
        sta xrow
        sta xrow+1
        jsr elemaddr
        ldy #0
bcg_l:  cpy xw
        beq bcg_pad
        lda (cs),y
        sta bc_tmp+1,y
        iny
        jmp bcg_l
bcg_pad:
        cpy #3
        beq bcg_done
        lda #0
        sta bc_tmp+1,y
        iny
        jmp bcg_pad
bcg_done:
        rts

; Drop the top value-stack cell (4 bytes): a p_sdyad result already read into bc_tmp/bc_bi/bc_r.
bc_drop:
        sec
        lda vsp
        sbc #4
        sta vsp
        lda vsp+1
        sbc #0
        sta vsp+1
        rts

bc_push_bi:
        ldy #3
bpbi:   lda bc_bi,y
        sta cv,y
        dey
        bpl bpbi
        jmp pushcv

bc_push_r:
        ldy #3
bpr:    lda bc_r,y
        sta cv,y
        dey
        bpl bpr
        jmp pushcv

bc_push_tmp:
        ldy #3
bptm:   lda bc_tmp,y
        sta cv,y
        dey
        bpl bptm
        jmp pushcv

; The value on top of the value stack, into bc_tmp; drops it. Carry is always clear (topcell cannot fail).
bc_pop_tmp:
        jsr topcell
        ldy #3
bpt:    lda (cptr),y
        sta bc_tmp,y
        dey
        bpl bpt
        jmp bc_drop

; bc_tmp into bc_r (a scalar copy, no value-stack access).
bc_tmp_to_r:
        ldy #3
btr:    lda bc_tmp,y
        sta bc_r,y
        dey
        bpl btr
        rts

; --- validate B and V, common to ⊥ and ⊤ (B = topcell, V = secondcell); A on entry: 2 (⊥) sets the
; RANK ERROR bound for V at 2, 1 (⊤) at 1 (its matrix case is not done). Leaves bc_bt..bc_vp filled in;
; carry set on error.
bc_prep:
        sta bc_j                 ; (spare: the V rank bound, until bc_j is needed for real)
        jsr topcell
        jsr getval
        lda vt
        sta bc_bt
        lda vrk
        sta bc_brk
        lda vn
        sta bc_bn
        lda vn+1
        sta bc_bn+1
        lda vp
        sta bc_bp
        lda vp+1
        sta bc_bp+1
        jsr secondcell
        jsr getval
        lda vt
        sta bc_vt
        lda vrk
        sta bc_vrk
        lda vn
        sta bc_vn
        lda vn+1
        sta bc_vn+1
        lda vs0
        sta bc_vs0
        lda vs0+1
        sta bc_vs0+1
        lda vs1
        sta bc_vs1
        lda vs1+1
        sta bc_vs1+1
        lda vp
        sta bc_vp
        lda vp+1
        sta bc_vp+1
        lda bc_brk                ; both ranks (RANK ERROR), then both domains (DOMAIN ERROR)
        cmp #2
        bcc bp_v1
        lda #E_RANK
        sec
        rts
bp_v1:  lda bc_vrk
        cmp bc_j
        bcc bp_d1
        beq bp_d1
        lda #E_RANK
        sec
        rts
bp_d1:  lda bc_bt
        cmp #1
        bne bp_d2
        lda #E_DOMAIN
        sec
        rts
bp_d2:  lda bc_vt
        cmp #1
        bne bp_ok
        lda #E_DOMAIN
        sec
        rts
bp_ok:  clc
        rts

; Place the scalar cell at bc_tmp at 0-based element bc_idx of the result array (bc_rc, current type
; bc_rt, fixed rank/count/dims bc_nrk/bc_nn/bc_nd0/bc_nd1), widening it first if bc_tmp needs a wider
; type. Carry set (A = the error) on WS FULL.
bc_place:
        lda bc_tmp
        cmp bc_rt
        bcc bpl_go
        beq bpl_go
        sta nt                   ; wider: a new array, with what is already in the old one converted
        lda bc_nrk
        sta nrk
        lda bc_nn
        sta nn
        lda bc_nn+1
        sta nn+1
        lda bc_nd0
        sta nd0
        lda bc_nd0+1
        sta nd0+1
        lda bc_nd1
        sta nd1
        lda bc_nd1+1
        sta nd1+1
        jsr newarr
        bcc bpl_w1
        rts
bpl_w1: lda bc_rc
        sta cptr
        lda bc_rc+1
        sta cptr+1
        jsr getval               ; the old array: vt, vn, vp
        jsr cvcopy               ; -> the new dp, converting to nt (still set from above)
        ldy #3
bpl_w2: lda cv,y                 ; the new array's cell takes the old one's place on the value stack
        sta (cptr),y
        dey
        bpl bpl_w2
        lda bc_tmp
        sta bc_rt
bpl_go: lda bc_rc
        sta cptr
        lda bc_rc+1
        sta cptr+1
        jsr getval               ; vp: the (possibly just-widened) array's data
        lda bc_idx
        sta p0
        lda bc_idx+1
        sta p1
        ldx bc_rt
        lda WIDTHT,x
        sta bl
        lda #0
        sta bh
        jsr mul16
        clc
        lda vp
        adc p0
        sta dp
        lda vp+1
        adc p1
        sta dp+1
        lda bc_tmp
        sta vt
        lda #1
        sta vn
        lda #0
        sta vn+1
        lda #<(bc_tmp+1)
        sta vp
        lda #>(bc_tmp+1)
        sta vp+1
        lda bc_rt
        sta nt
        jmp cvcopy

; --- decode: B⊥V ------------------------------------------------------------------------------------

p_decode:
        lda #2
        jsr bc_prep
        bcc pd_1
        rts
pd_1:   lda bc_vrk
        cmp #2
        bne pd_vec
        lda bc_vs0               ; a matrix: one column decoded per result element
        sta bc_n
        lda bc_vs0+1
        sta bc_n+1
        lda bc_vs1
        sta bc_k
        lda bc_vs1+1
        sta bc_k+1
        jmp pd_blen
pd_vec: lda #1                   ; a scalar (n = 1); a vector: n = its length
        sta bc_n
        lda #0
        sta bc_n+1
        lda bc_vrk
        beq pd_v2
        lda bc_vn
        sta bc_n
        lda bc_vn+1
        sta bc_n+1
pd_v2:  lda #1
        sta bc_k
        lda #0
        sta bc_k+1
pd_blen: lda bc_brk               ; B: one radix per digit, or one for all
        beq pd_bok
        lda bc_bn
        cmp #1
        bne pd_blc
        lda bc_bn+1
        bne pd_blc
        jmp pd_bok
pd_blc: lda bc_bn
        cmp bc_n
        bne pd_blerr
        lda bc_bn+1
        cmp bc_n+1
        beq pd_bok
pd_blerr: lda #E_LENGTH
        sec
        rts
pd_bok: lda bc_vrk
        cmp #2
        beq pd_mat
        lda #1                   ; a scalar result: no allocation, no axis to step through columns
        sta bc_vstep
        lda #0
        sta bc_vstep+1
        sta bc_vbase
        sta bc_vbase+1
        jsr bc_horner
        bcc pd_s1
        rts
pd_s1:  ldy #3
pd_s2:  lda bc_r,y
        sta cv,y
        dey
        bpl pd_s2
        jmp setdy

pd_mat: lda bc_k                 ; k columns: a vector result, widened as it fills
        sta bc_nn
        lda bc_k+1
        sta bc_nn+1
        lda bc_k
        sta bc_nd0
        lda bc_k+1
        sta bc_nd0+1
        lda #1
        sta bc_nrk
        lda bc_nn                ; BOOL to start (the first real element corrects it), but INT if
        ora bc_nn+1              ; it stays empty (no element ever will): the model's identity type
        bne pd_m0a
        lda #2
        jmp pd_m0b
pd_m0a: lda #0
pd_m0b: sta nt
        lda #1
        sta nrk
        lda bc_nn
        sta nn
        lda bc_nn+1
        sta nn+1
        lda bc_nd0
        sta nd0
        lda bc_nd0+1
        sta nd0+1
        jsr newarr
        bcc pd_m1
        rts
pd_m1:  lda nt
        sta bc_rt
        jsr pushcv
        jsr topcell
        lda cptr
        sta bc_rc
        lda cptr+1
        sta bc_rc+1
        lda bc_k
        sta bc_vstep
        lda bc_k+1
        sta bc_vstep+1
        lda #0
        sta bc_j
        sta bc_j+1
pd_mloop: lda bc_j
        cmp bc_k
        bne pd_mgo
        lda bc_j+1
        cmp bc_k+1
        beq pd_mdone
pd_mgo: lda bc_j
        sta bc_vbase
        lda bc_j+1
        sta bc_vbase+1
        jsr bc_horner
        bcc pd_m2
        rts
pd_m2:  ldy #3
pd_m3:  lda bc_r,y
        sta bc_tmp,y
        dey
        bpl pd_m3
        lda bc_j
        sta bc_idx
        lda bc_j+1
        sta bc_idx+1
        jsr bc_place
        bcc pd_m4
        rts
pd_m4:  inc bc_j
        bne pd_mloop
        inc bc_j+1
        jmp pd_mloop
pd_mdone:
        lda bc_rc
        sta cptr
        lda bc_rc+1
        sta cptr+1
        ldy #3
pd_md1: lda (cptr),y
        sta cv,y
        dey
        bpl pd_md1
        sec
        lda vsp
        sbc #12
        sta vsp
        lda vsp+1
        sbc #0
        sta vsp+1
        jmp setmon

; Horner's rule over bc_n digits of B against a V accessed as i*bc_vstep+bc_vbase: acc = acc*B[i]+V[i],
; left to right (the first radix never affects the result). Leaves the total in bc_r.
bc_horner:
        lda #2                   ; INT 0: the identity, matching an empty V (n = 0)
        sta bc_r
        lda #0
        sta bc_r+1
        sta bc_r+2
        sta bc_r+3
        lda #0
        sta bc_i
        sta bc_i+1
bch_lp: lda bc_i
        cmp bc_n
        bne bch_go
        lda bc_i+1
        cmp bc_n+1
        bne bch_go
        jmp bch_ok
bch_go: lda bc_bn                ; B[i], or B[0] if it is one for all
        cmp #1
        bne bch_bi
        lda bc_bn+1
        bne bch_bi
        lda #0
        sta bc_idx
        sta bc_idx+1
        jmp bch_bf
bch_bi: lda bc_i
        sta bc_idx
        lda bc_i+1
        sta bc_idx+1
bch_bf: lda bc_bp
        sta xbase
        lda bc_bp+1
        sta xbase+1
        ldx bc_bt
        lda WIDTHT,x
        tax
        lda bc_bt
        jsr bc_getelem
        jsr bc_push_tmp           ; acc × B[i]: order does not matter (both commutative)
        jsr bc_push_r
        lda #2
        jsr p_sdyad
        bcs bch_err
        jsr bc_pop_tmp
        jsr bc_tmp_to_r

        lda bc_i                 ; V's element: i*bc_vstep + bc_vbase
        sta p0
        lda bc_i+1
        sta p1
        lda bc_vstep
        sta bl
        lda bc_vstep+1
        sta bh
        jsr mul16
        clc
        lda p0
        adc bc_vbase
        sta bc_idx
        lda p1
        adc bc_vbase+1
        sta bc_idx+1
        lda bc_vp
        sta xbase
        lda bc_vp+1
        sta xbase+1
        ldx bc_vt
        lda WIDTHT,x
        tax
        lda bc_vt
        jsr bc_getelem
        jsr bc_push_tmp           ; acc + V[i]
        jsr bc_push_r
        lda #0
        jsr p_sdyad
        bcs bch_err
        jsr bc_pop_tmp
        jsr bc_tmp_to_r

        inc bc_i
        beq bch_l1
        jmp bch_lp
bch_l1: inc bc_i+1
        jmp bch_lp
bch_ok: clc
        rts
bch_err: rts

; --- encode: B⊤V ------------------------------------------------------------------------------------

p_encode:
        lda #1
        jsr bc_prep
        bcc pe_1
        rts
pe_1:   lda bc_brk                ; n: the length of B (1 if a scalar)
        beq pe_n1
        lda bc_bn
        sta bc_n
        lda bc_bn+1
        sta bc_n+1
        jmp pe_m
pe_n1:  lda #1
        sta bc_n
        lda #0
        sta bc_n+1
pe_m:   lda bc_vrk                ; m: the length of V (1 if a scalar); the result's rank follows
        beq pe_m1
        lda bc_vn
        sta bc_k
        lda bc_vn+1
        sta bc_k+1
        lda #2
        sta bc_nrk
        jmp pe_alloc
pe_m1:  lda #1
        sta bc_k
        lda #0
        sta bc_k+1
        lda #1
        sta bc_nrk
pe_alloc:
        lda bc_n
        sta p0
        lda bc_n+1
        sta p1
        lda bc_k
        sta bl
        lda bc_k+1
        sta bh
        jsr mul16
        lda p0
        sta bc_nn
        lda p1
        sta bc_nn+1
        lda bc_n
        sta bc_nd0
        lda bc_n+1
        sta bc_nd0+1
        lda bc_k
        sta bc_nd1
        lda bc_k+1
        sta bc_nd1+1
        lda bc_nn                ; BOOL to start (the first real element corrects it), but INT if it
        ora bc_nn+1              ; stays empty (no element ever will): the model's identity type
        bne pe_a0a
        lda #2
        jmp pe_a0b
pe_a0a: lda #0
pe_a0b: sta nt
        lda bc_nrk
        sta nrk
        lda bc_nn
        sta nn
        lda bc_nn+1
        sta nn+1
        lda bc_nd0
        sta nd0
        lda bc_nd0+1
        sta nd0+1
        lda bc_nd1
        sta nd1
        lda bc_nd1+1
        sta nd1+1
        jsr newarr
        bcc pe_1a
        rts
pe_1a:  lda nt
        sta bc_rt
        jsr pushcv
        jsr topcell
        lda cptr
        sta bc_rc
        lda cptr+1
        sta bc_rc+1
        lda #0
        sta bc_j
        sta bc_j+1
pe_jloop: lda bc_j
        cmp bc_k
        bne pe_jgo
        lda bc_j+1
        cmp bc_k+1
        bne pe_jgo
        jmp pe_done
pe_jgo: lda bc_vrk                ; V[j], or V[0] if it is a scalar
        beq pe_v0
        lda bc_j
        sta bc_idx
        lda bc_j+1
        sta bc_idx+1
        jmp pe_vf
pe_v0:  lda #0
        sta bc_idx
        sta bc_idx+1
pe_vf:  lda bc_vp
        sta xbase
        lda bc_vp+1
        sta xbase+1
        ldx bc_vt
        lda WIDTHT,x
        tax
        lda bc_vt
        jsr bc_getelem
        jsr bc_tmp_to_r           ; bc_r: what is left of this column, so far all of it

        lda bc_n                  ; i counts down from n-1 to 0
        sta bc_i
        lda bc_n+1
        sta bc_i+1
        lda bc_i
        ora bc_i+1
        bne pe_dec
        jmp pe_jnext
pe_dec: sec
        lda bc_i
        sbc #1
        sta bc_i
        lda bc_i+1
        sbc #0
        sta bc_i+1
pe_iloop:
        lda bc_bn                ; B[i], or B[0] if it is one for all
        cmp #1
        bne pe_bi
        lda bc_bn+1
        bne pe_bi
        lda #0
        sta bc_idx
        sta bc_idx+1
        jmp pe_bf
pe_bi:  lda bc_i
        sta bc_idx
        lda bc_i+1
        sta bc_idx+1
pe_bf:  lda bc_bp
        sta xbase
        lda bc_bp+1
        sta xbase+1
        ldx bc_bt
        lda WIDTHT,x
        tax
        lda bc_bt
        jsr bc_getelem
        ldy #3
pe_bi2: lda bc_tmp,y
        sta bc_bi,y
        dey
        bpl pe_bi2
        lda bc_bi+1               ; a zero radix absorbs everything left
        ora bc_bi+2
        ora bc_bi+3
        beq pe_zero
        lda #0
        beq pe_zst
pe_zero: lda #1
pe_zst: sta bc_zero

        jsr bc_push_r             ; digit = Bi | R
        jsr bc_push_bi
        lda #12
        jsr p_sdyad
        bcc pe_dig1
        jmp pe_err
pe_dig1: jsr bc_pop_tmp
        ldy #3
        lda bc_i                  ; place it at row i, column j: i*bc_k + j
        sta p0
        lda bc_i+1
        sta p1
        lda bc_k
        sta bl
        lda bc_k+1
        sta bh
        jsr mul16
        clc
        lda p0
        adc bc_j
        sta bc_idx
        lda p1
        adc bc_j+1
        sta bc_idx+1
        jsr bc_place
        bcc pe_ip1
        rts
pe_ip1: lda bc_zero
        beq pe_div
        lda #2                    ; remaining is now 0 exactly (INT), not 0÷0
        sta bc_r
        lda #0
        sta bc_r+1
        sta bc_r+2
        sta bc_r+3
        jmp pe_inext
pe_div: jsr bc_push_tmp            ; diff = R - digit
        jsr bc_push_r
        lda #1
        jsr p_sdyad
        bcs pe_err
        jsr bc_pop_tmp
        jsr bc_push_bi             ; remaining = diff ÷ Bi
        jsr bc_push_tmp
        lda #3
        jsr p_sdyad
        bcs pe_err
        jsr bc_pop_tmp
        jsr bc_tmp_to_r
pe_inext:
        lda bc_i
        ora bc_i+1
        beq pe_jnext
        jmp pe_dec
pe_jnext:
        inc bc_j
        beq pe_jn1
        jmp pe_jloop
pe_jn1: inc bc_j+1
        jmp pe_jloop
pe_done:
        lda bc_rc
        sta cptr
        lda bc_rc+1
        sta cptr+1
        ldy #3
pe_d1:  lda (cptr),y
        sta cv,y
        dey
        bpl pe_d1
        sec
        lda vsp
        sbc #12
        sta vsp
        lda vsp+1
        sbc #0
        sta vsp+1
        jmp setmon
pe_err: rts
