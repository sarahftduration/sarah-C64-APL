; Inner product a f.g b: an overlay (see overlay.inc), entered through s_inner. Spec: apl64.py make_inner.
;
; A = f*16 + g, the engine's operation numbers of f and g (the same numbers reduce uses). The left
; operand is the top cell, the right one below it. For each result element (row i of a, column j of b):
; the two are copied into new vectors of n elements (a scalar operand is repeated), g is applied with the
; scalar engine (p_sdyad), f is reduced over the result (p_reduce), and the scalar that comes out is stored
; in the result array, which is allocated once the first element has given its type and is widened, keeping
; what is there, when a later element needs a wider one. An error stops at once, except that a result that
; does not fit (WS FULL) lets the rest be computed first, so that a DOMAIN ERROR anywhere wins, as in the
; model. The variables live in this image: it stays loaded while the operation runs (everything it calls
; is resident).

iq_fop:  .byte 0
iq_gop:  .byte 0
iq_ca:   .word 0                ; the cells of a and b (on the value stack: they do not move)
iq_cb:   .word 0
iq_vsp0: .word 0                ; the stack pointer on entry
iq_ra:   .byte 0                ; ranks
iq_rb:   .byte 0
iq_ta:   .byte 0                ; types (only for the vt of the copies: they are read again from the cells)
iq_na:   .word 0                ; last axis of a
iq_nb:   .word 0                ; first axis of b
iq_n:    .word 0                ; length of the inner axis
iq_m:    .word 0                ; rows of a (1 unless a matrix)
iq_p:    .word 0                ; columns of b (1 unless a matrix)
iq_rr:   .byte 0                ; rank of the result
iq_d0:   .word 0                ; its dimensions
iq_d1:   .word 0
iq_tot:  .word 0                ; its element count
iq_i:    .word 0
iq_j:    .word 0
iq_as:   .word 0                ; element index of the start of row i of a
iq_dry:  .byte 0                ; 1: the result does not fit, so results are only checked
iq_have: .byte 0                ; 1: the result array exists (its cell is on the stack, at iq_rc)
iq_rc:   .word 0
iq_rt:   .byte 0                ; its type
iq_off:  .word 0                ; byte offset of the next element
iq_k:    .word 0                ; elements stored
iq_st:   .byte 0                ; the last scalar result: its type and data (its cell)
iq_sd:   .byte 0, 0, 0
iq_gc:   .word 0                ; gather: the source cell, first element, step
iq_gs:   .word 0
iq_gk:   .word 0
iq_gw:   .byte 0                ; element width
iq_gkb:  .word 0                ; step in bytes
iq_cnt:  .word 0
iq_tmp:  .word 0
iq_tm2:  .word 0

p_inner:
        pha
        lsr
        lsr
        lsr
        lsr
        sta iq_fop
        pla
        and #15
        sta iq_gop
        jsr topcell
        lda cptr
        sta iq_ca
        lda cptr+1
        sta iq_ca+1
        jsr secondcell
        lda cptr
        sta iq_cb
        lda cptr+1
        sta iq_cb+1
        lda vsp
        sta iq_vsp0
        lda vsp+1
        sta iq_vsp0+1
        lda #0
        sta iq_dry
        sta iq_have
        sta iq_as
        sta iq_as+1
        lda #1                  ; rows and columns, until the operands say otherwise
        sta iq_m
        sta iq_p
        sta iq_na
        sta iq_nb
        lda #0
        sta iq_m+1
        sta iq_p+1
        sta iq_na+1
        sta iq_nb+1
        lda iq_ca               ; a
        sta cptr
        lda iq_ca+1
        sta cptr+1
        jsr getval
        lda vrk
        sta iq_ra
        beq iq_ia_1
        lda vs0
        sta iq_na
        lda vs0+1
        sta iq_na+1
        lda vrk
        cmp #2
        bne iq_ia_1
        lda vs0                 ; a matrix: vs0 rows of vs1
        sta iq_m
        lda vs0+1
        sta iq_m+1
        lda vs1
        sta iq_na
        lda vs1+1
        sta iq_na+1
iq_ia_1:   lda iq_cb               ; b
        sta cptr
        lda iq_cb+1
        sta cptr+1
        jsr getval
        lda vrk
        sta iq_rb
        beq iq_ib_1
        lda vs0
        sta iq_nb
        lda vs0+1
        sta iq_nb+1
        lda vrk
        cmp #2
        bne iq_ib_1
        lda vs1
        sta iq_p
        lda vs1+1
        sta iq_p+1
iq_ib_1:   lda iq_ra               ; the inner axes must agree unless one operand is a scalar
        beq iq_ic_n
        lda iq_rb
        beq iq_ic_n
        lda iq_na
        cmp iq_nb
        bne iq_ic_len
        lda iq_na+1
        cmp iq_nb+1
        beq iq_ic_n
iq_ic_len: lda #E_LENGTH
        sec
        rts
iq_ic_n:   lda iq_ra               ; n: the axis of the operand that has one
        bne iq_ic_n1
        lda iq_nb
        sta iq_n
        lda iq_nb+1
        sta iq_n+1
        jmp iq_ic_z
iq_ic_n1:  lda iq_na
        sta iq_n
        lda iq_na+1
        sta iq_n+1
iq_ic_z:   lda iq_m                ; no elements in the result: NONCE
        ora iq_m+1
        beq iq_ic_nonce
        lda iq_p
        ora iq_p+1
        bne iq_ic_shape
iq_ic_nonce:
        lda #E_NONCE
        sec
        rts
iq_ic_shape:
        lda #0                  ; the result's shape: a's rows then b's columns
        sta iq_rr
        lda iq_ra
        cmp #2
        bne iq_is_b
        inc iq_rr
        lda iq_m
        sta iq_d0
        lda iq_m+1
        sta iq_d0+1
iq_is_b:   lda iq_rb
        cmp #2
        bne iq_is_c
        inc iq_rr
        lda iq_rr
        cmp #2
        beq iq_is_two
        lda iq_p                ; (a matrix and a vector, or a vector and a matrix: one dimension)
        sta iq_d0
        lda iq_p+1
        sta iq_d0+1
        jmp iq_is_c
iq_is_two: lda iq_p
        sta iq_d1
        lda iq_p+1
        sta iq_d1+1
iq_is_c:   lda iq_rr
        beq iq_is_one
        cmp #2
        beq iq_is_mul
        lda iq_d0               ; one dimension: the count
        sta iq_tot
        lda iq_d0+1
        sta iq_tot+1
        jmp in_go
iq_is_one: lda #1
        sta iq_tot
        lda #0
        sta iq_tot+1
        jmp in_go
iq_is_mul: lda iq_m
        sta p0
        lda iq_m+1
        sta p1
        lda iq_p
        sta bl
        lda iq_p+1
        sta bh
        jsr mul16
        lda p0
        sta iq_tot
        lda p1
        sta iq_tot+1
        lda p2
        ora p3
        beq in_go
        lda #1                  ; over 65535 elements: it cannot fit
        sta iq_dry

in_go:  lda #0
        sta iq_i
        sta iq_i+1
in_iloop:
        lda #0
        sta iq_j
        sta iq_j+1
in_jloop:
        jsr in_pair
        bcs in_ret
        jsr in_store
        bcs in_ret
        inc iq_j
        bne iq_ij_1
        inc iq_j+1
iq_ij_1:   lda iq_j
        cmp iq_p
        bne in_jloop
        lda iq_j+1
        cmp iq_p+1
        bne in_jloop
        lda iq_ra               ; the next row of a
        cmp #2
        bne iq_ij_2
        clc
        lda iq_as
        adc iq_n
        sta iq_as
        lda iq_as+1
        adc iq_n+1
        sta iq_as+1
iq_ij_2:   inc iq_i
        bne iq_ij_3
        inc iq_i+1
iq_ij_3:   lda iq_i
        cmp iq_m
        bne in_iloop
        lda iq_i+1
        cmp iq_m+1
        bne in_iloop
        jmp in_finish
in_ret: rts

; --- the result: one cell in place of a and b ------------------------------------------------------------
in_finish:
        lda iq_dry
        bne iq_fn_ws
        lda iq_rr
        beq iq_fn_sc
        lda iq_rc               ; the result array's cell
        sta cptr
        lda iq_rc+1
        sta cptr+1
        ldy #3
iq_fn_1:   lda (cptr),y
        sta cv,y
        dey
        bpl iq_fn_1
        jmp iq_fn_set
iq_fn_sc:  lda iq_st               ; a scalar
        sta cv
        lda iq_sd
        sta cv+1
        lda iq_sd+1
        sta cv+2
        lda iq_sd+2
        sta cv+3
iq_fn_set: sec                     ; the result goes where b was
        lda iq_vsp0
        sbc #4
        sta vsp
        lda iq_vsp0+1
        sbc #0
        sta vsp+1
        jmp setmon
iq_fn_ws:  lda #E_WSFULL
        sec
        rts

; --- one element: leaves the scalar in iq_st, iq_sd -------------------------------------------------------
in_pair:
        lda iq_cb               ; column j of b (pushed first: it is the right argument)
        sta iq_gc
        lda iq_cb+1
        sta iq_gc+1
        lda #0
        sta iq_gs
        sta iq_gs+1
        sta iq_gk+1
        sta iq_gk
        lda iq_rb
        beq iq_pr_b
        inc iq_gk               ; a step of 1: a vector
        cmp #2
        bne iq_pr_b
        lda iq_j                ; a matrix: the column starts at j and steps by its width
        sta iq_gs
        lda iq_j+1
        sta iq_gs+1
        lda iq_p
        sta iq_gk
        lda iq_p+1
        sta iq_gk+1
iq_pr_b:   jsr in_gather
        bcs iq_pr_ret
        lda iq_ca               ; row i of a
        sta iq_gc
        lda iq_ca+1
        sta iq_gc+1
        lda #0
        sta iq_gs
        sta iq_gs+1
        sta iq_gk
        sta iq_gk+1
        lda iq_ra
        beq iq_pr_a
        inc iq_gk
        cmp #2
        bne iq_pr_a
        lda iq_as
        sta iq_gs
        lda iq_as+1
        sta iq_gs+1
iq_pr_a:   jsr in_gather
        bcs iq_pr_ret
        lda iq_gop
        jsr p_sdyad
        bcs iq_pr_ret
        lda iq_fop
        jsr p_reduce
        bcs iq_pr_ret
        jsr topcell             ; take the scalar off the stack
        ldy #0
        lda (cptr),y
        sta iq_st
        iny
        lda (cptr),y
        sta iq_sd
        iny
        lda (cptr),y
        sta iq_sd+1
        iny
        lda (cptr),y
        sta iq_sd+2
        sec
        lda vsp
        sbc #4
        sta vsp
        lda vsp+1
        sbc #0
        sta vsp+1
        clc
iq_pr_ret: rts

; --- gather: a new vector of n elements from the cell iq_gc, starting at element iq_gs and stepping iq_gk
; elements (0: the scalar is repeated); pushed on the stack
in_gather:
        lda iq_gc
        sta cptr
        lda iq_gc+1
        sta cptr+1
        jsr getval
        lda vt
        sta nt
        lda #1
        sta nrk
        lda iq_n
        sta nn
        sta nd0
        lda iq_n+1
        sta nn+1
        sta nd0+1
        jsr newarr
        bcc *+3
        rts
        jsr pushcv
        bcc *+3
        rts
        lda iq_gc               ; (the allocation may have moved the source)
        sta cptr
        lda iq_gc+1
        sta cptr+1
        jsr getval
        ldx vt
        lda WIDTHT,x
        sta iq_gw
        lda iq_gs               ; cs = the first element
        sta iq_tmp
        lda iq_gs+1
        sta iq_tmp+1
        ldx iq_gw
        jsr in_wmul
        clc
        lda vp
        adc iq_tmp
        sta cs
        lda vp+1
        adc iq_tmp+1
        sta cs+1
        lda iq_gk
        sta iq_tmp
        lda iq_gk+1
        sta iq_tmp+1
        ldx iq_gw
        jsr in_wmul
        lda iq_tmp
        sta iq_gkb
        lda iq_tmp+1
        sta iq_gkb+1
        lda iq_n
        sta iq_cnt
        lda iq_n+1
        sta iq_cnt+1
iq_ga_l:   lda iq_cnt
        ora iq_cnt+1
        beq iq_ga_done
        ldy #0
iq_ga_c:   lda (cs),y
        sta (dp),y
        iny
        cpy iq_gw
        bne iq_ga_c
        clc
        lda dp
        adc iq_gw
        sta dp
        bcc iq_ga_1
        inc dp+1
iq_ga_1:   clc
        lda cs
        adc iq_gkb
        sta cs
        lda cs+1
        adc iq_gkb+1
        sta cs+1
        lda iq_cnt
        bne iq_ga_2
        dec iq_cnt+1
iq_ga_2:   dec iq_cnt
        jmp iq_ga_l
iq_ga_done: clc
iq_ga_ret: rts

; iq_tmp = iq_tmp * X (X = 1 to 3)
in_wmul:
        lda iq_tmp
        sta iq_tm2
        lda iq_tmp+1
        sta iq_tm2+1
        dex
        beq iq_wm_r
iq_wm_l:   clc
        lda iq_tmp
        adc iq_tm2
        sta iq_tmp
        lda iq_tmp+1
        adc iq_tm2+1
        sta iq_tmp+1
        dex
        bne iq_wm_l
iq_wm_r:   rts

; --- store the scalar in iq_st, iq_sd as the next element of the result ---------------------------------
in_store:
        lda iq_rr
        bne iq_st_arr
        clc                     ; a scalar result: it stays in iq_st, iq_sd
        rts
iq_st_arr: lda iq_dry
        bne iq_st_x
        lda iq_have
        bne iq_st_have
        lda iq_st               ; the first element gives the type
        sta iq_rt
        jsr in_new
        bcs iq_stx
        lda iq_dry              ; (it did not fit: nothing to store)
        bne iq_stx
        jmp iq_st_put
iq_stx: rts
iq_st_x:   clc
        rts
iq_st_have:
        lda iq_st
        cmp iq_rt
        bcc iq_put_j            ; narrower or equal: it is converted
        beq iq_put_j
        bcs iq_wider
iq_put_j: jmp iq_st_put
iq_wider:
        lda iq_st               ; wider: a bigger array, with what is stored so far converted into it
        sta nt
        lda iq_rr
        sta nrk
        lda iq_tot
        sta nn
        lda iq_tot+1
        sta nn+1
        lda iq_d0
        sta nd0
        lda iq_d0+1
        sta nd0+1
        lda iq_d1
        sta nd1
        lda iq_d1+1
        sta nd1+1
        jsr newarr
        bcc iq_sw_1
        jmp iq_st_full
iq_sw_1:   lda iq_rc               ; the old array's elements, converted into the new one
        sta cptr
        lda iq_rc+1
        sta cptr+1
        jsr getval              ; (dp is still the new array's data)
        lda iq_k
        sta vn
        lda iq_k+1
        sta vn+1
        lda iq_st
        sta nt
        jsr cvcopy
        lda iq_rc               ; the new array takes over the old one's cell
        sta cptr
        lda iq_rc+1
        sta cptr+1
        ldy #3
iq_sw_2:   lda cv,y
        sta (cptr),y
        dey
        bpl iq_sw_2
        lda iq_st
        sta iq_rt
        lda iq_k
        sta iq_tmp
        lda iq_k+1
        sta iq_tmp+1
        ldx iq_rt
        lda WIDTHT,x
        tax
        jsr in_wmul
        lda iq_tmp
        sta iq_off
        lda iq_tmp+1
        sta iq_off+1
iq_st_put: lda iq_rc               ; store one element at the offset
        sta cptr
        lda iq_rc+1
        sta cptr+1
        jsr getval
        clc
        lda vp
        adc iq_off
        sta dp
        lda vp+1
        adc iq_off+1
        sta dp+1
        lda iq_st
        sta vt
        lda #<iq_sd
        sta vp
        lda #>iq_sd
        sta vp+1
        lda #1
        sta vn
        lda #0
        sta vn+1
        lda iq_rt
        sta nt
        jsr cvcopy
        ldx iq_rt
        clc
        lda iq_off
        adc WIDTHT,x
        sta iq_off
        bcc iq_sp_1
        inc iq_off+1
iq_sp_1:   inc iq_k
        bne iq_sp_2
        inc iq_k+1
iq_sp_2:   clc
        rts
iq_st_full:
        cmp #E_WSFULL           ; the result does not fit: check the rest, then say so
        bne iq_st_err
        lda #1
        sta iq_dry
        clc
        rts
iq_st_err: sec
        rts

; allocate the result (type iq_rt) and put its cell on the stack
in_new: lda iq_rt
        sta nt
        lda iq_rr
        sta nrk
        lda iq_tot
        sta nn
        lda iq_tot+1
        sta nn+1
        lda iq_d0
        sta nd0
        lda iq_d0+1
        sta nd0+1
        lda iq_d1
        sta nd1
        lda iq_d1+1
        sta nd1+1
        jsr newarr
        bcs iq_st_full
        jsr pushcv
        bcs iq_st_err
        jsr topcell
        lda cptr
        sta iq_rc
        lda cptr+1
        sta iq_rc+1
        lda #0
        sta iq_off
        sta iq_off+1
        sta iq_k
        sta iq_k+1
        lda #1
        sta iq_have
        clc
        rts
