; Roll and deal, ?n and a?b (an overlay, see overlay.inc). Spec: apl64.py rng_draw, roll, deal.
;
; The generator is xorshift32 in rnd_state (four bytes, low first, kept in overlay.inc so that it survives the
; overlay being replaced); a draw is the top 16 bits of the state, rd_r. A roll scales it: (r * n) >> 16 + 1.

rd_r:    .word 0
rd_t:    .fill 4
rd_zero: .byte 0                ; a 0 among the numbers rolled: the result is FLOAT
rd_rk:   .byte 0                ; the argument's rank, count and shape
rd_n:    .word 0
rd_d0:   .word 0
rd_d1:   .word 0
rd_na:   .word 0                ; deal: a, b, and the counts qan of each
rd_nb:   .word 0
rd_ca:   .byte 0
rd_i:    .word 0                ; the deal loop
rd_pp:   .word 0                ; the start of the permutation

; rd_t = rnd_state
rd_cp:  ldx #3
rd_c1:  lda rnd_state,x
        sta rd_t,x
        dex
        bpl rd_c1
        rts
; rnd_state = rnd_state xor rd_t
rd_xor: ldx #3
rd_x1:  lda rnd_state,x
        eor rd_t,x
        sta rnd_state,x
        dex
        bpl rd_x1
        rts
rd_shl: asl rd_t                ; rd_t = rd_t << X
        rol rd_t+1
        rol rd_t+2
        rol rd_t+3
        dex
        bne rd_shl
        rts
rd_shr: lsr rd_t+3              ; rd_t = rd_t >> X
        ror rd_t+2
        ror rd_t+1
        ror rd_t
        dex
        bne rd_shr
        rts
; one draw into rd_r
rd_draw:
        jsr rd_cp
        ldx #13
        jsr rd_shl
        jsr rd_xor
        jsr rd_cp
        ldx #17
        jsr rd_shr
        jsr rd_xor
        jsr rd_cp
        ldx #5
        jsr rd_shl
        jsr rd_xor
        lda rnd_state+2
        sta rd_r
        lda rnd_state+3
        sta rd_r+1
        rts

; p2:p3 = the high 16 bits of rd_r times bl:bh (the caller sets bl, bh)
rd_scale:
        lda rd_r
        sta p0
        lda rd_r+1
        sta p1
        jmp mul16

; --- ?v -------------------------------------------------------------------------------------------------------------
p_roll: jsr topcell
        jsr getval
        lda vt
        cmp #1
        bne rd_rl_1
        jmp rd_rl_dom
rd_rl_1:   lda vrk
        sta rd_rk
        lda vn
        sta rd_n
        lda vn+1
        sta rd_n+1
        lda vs0
        sta rd_d0
        lda vs0+1
        sta rd_d0+1
        lda vs1
        sta rd_d1
        lda vs1+1
        sta rd_d1+1
        lda vp                  ; pass 1: every element must be a whole number from 0 to 32767
        sta ep
        lda vp+1
        sta ep+1
        lda vn
        sta qcnt
        lda vn+1
        sta qcnt+1
        lda #0
        sta rd_zero
rd_rl_p1:  lda qcnt
        ora qcnt+1
        beq rd_rl_al
        jsr elem_to_int
        bcs rd_rl_dom
        lda ineg
        ora ihuge
        bne rd_rl_dom
        lda im+1
        bmi rd_rl_dom
        ora im
        bne rd_rl_nz
        inc rd_zero
rd_rl_nz:  ldx vt
        clc
        lda ep
        adc WIDTHT,x
        sta ep
        bcc rd_rl_p2
        inc ep+1
rd_rl_p2:  lda qcnt
        bne rd_rl_p3
        dec qcnt+1
rd_rl_p3:  dec qcnt
        jmp rd_rl_p1
rd_rl_dom: lda #E_DOMAIN
        sec
        rts
rd_rl_al:  lda #2                  ; INT, or FLOAT if there was a 0
        ldx rd_zero
        beq rd_rl_t
        lda #3
rd_rl_t:   sta nt
        lda rd_rk
        bne rd_rl_ar
        lda nt                  ; a scalar
        sta cv
        lda #0
        sta cv+1
        sta cv+2
        sta cv+3
        lda #<(cv+1)
        sta dp
        lda #>(cv+1)
        sta dp+1
        jmp rd_rl_go
rd_rl_ar:  sta nrk
        lda rd_n
        sta nn
        lda rd_n+1
        sta nn+1
        lda rd_d0
        sta nd0
        lda rd_d0+1
        sta nd0+1
        lda rd_d1
        sta nd1
        lda rd_d1+1
        sta nd1+1
        jsr newarr
        bcc rd_rl_go
        rts
rd_rl_go:  jsr topcell             ; pass 2: the draws, in order
        jsr getval
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        lda rd_n
        sta qcnt
        lda rd_n+1
        sta qcnt+1
rd_rl_l:   lda qcnt
        ora qcnt+1
        bne rd_rl_e
        jmp setmon
rd_rl_e:   jsr elem_to_int
        jsr rd_draw
        lda im
        ora im+1
        beq rd_rl_f
        lda im                  ; (r * n) >> 16, plus 1
        sta bl
        lda im+1
        sta bh
        jsr rd_scale
        clc
        lda p2
        adc #1
        sta ia
        lda p3
        adc #0
        sta ia+1
        lda rd_zero
        beq rd_rl_i
        jsr i_to_f              ; FLOAT (some 0 elsewhere): the number as a float
        jmp rd_rl_sf
rd_rl_i:   ldy #0
        lda ia
        sta (dp),y
        iny
        lda ia+1
        sta (dp),y
        lda #2
        bne rd_rl_adv
rd_rl_f:   lda rd_r                ; a 0: (r | 1) / 65536
        ora #1
        sta ia
        lda rd_r+1
        sta ia+1
        lda #0
        sta sgn
        jsr m_to_f
        lda fa
        sec
        sbc #16
        sta fa
rd_rl_sf:  ldy #0
        lda fa
        sta (dp),y
        iny
        lda fa+1
        sta (dp),y
        iny
        lda fa+2
        sta (dp),y
        lda #3
rd_rl_adv: clc
        adc dp
        sta dp
        bcc rd_rl_a2
        inc dp+1
rd_rl_a2:  ldx vt
        clc
        lda ep
        adc WIDTHT,x
        sta ep
        bcc rd_rl_a3
        inc ep+1
rd_rl_a3:  lda qcnt
        bne rd_rl_a4
        dec qcnt+1
rd_rl_a4:  dec qcnt
        jmp rd_rl_l

; --- a?b ------------------------------------------------------------------------------------------------------------
p_deal: jsr topcell
        jsr arg_ints            ; RANK, DOMAIN for each, then the lengths
        bcc rd_dl_1
        rts
rd_dl_1:   lda qan
        sta rd_ca
        lda qan+1
        ora rd_ca
        sta rd_ca               ; (nonzero: not empty; the exact count is checked below)
        lda qan+1
        sta rd_zero             ; the high byte of a's count
        lda qan
        sta rd_rk               ; a's count
        lda qd0
        sta rd_na
        lda qd0+1
        sta rd_na+1
        lda qneg0
        ora qhuge0
        sta rd_d0
        jsr secondcell
        jsr arg_ints
        bcc rd_dl_2
        rts
rd_dl_2:   lda rd_zero             ; both must have exactly one element
        bne rd_dl_len
        lda rd_rk
        cmp #1
        bne rd_dl_len
        lda qan+1
        bne rd_dl_len
        lda qan
        cmp #1
        beq rd_dl_3
rd_dl_len: lda #E_LENGTH
        sec
        rts
rd_dl_3:   lda qd0
        sta rd_nb
        lda qd0+1
        sta rd_nb+1
        lda qneg0
        ora qhuge0
        ora rd_d0
        bne rd_dl_dom              ; negative or huge
        lda rd_na+1
        ora rd_nb+1
        bmi rd_dl_dom              ; 32768 or more
        lda rd_na+1             ; a must not be above b
        cmp rd_nb+1
        bcc rd_dl_ok
        bne rd_dl_dom
        lda rd_na
        cmp rd_nb
        bcc rd_dl_ok
        beq rd_dl_ok
rd_dl_dom: lda #E_DOMAIN
        sec
        rts
rd_dl_ok:  lda #2                  ; the permutation 1 to b, as an INT vector on the stack
        sta nt
        lda #1
        sta nrk
        lda rd_nb
        sta nn
        sta nd0
        lda rd_nb+1
        sta nn+1
        sta nd0+1
        jsr newarr
        bcc rd_dl_4
        rts
rd_dl_4:   jsr pushcv
        bcc rd_dl_5
        rts
rd_dl_5:   lda rd_nb
        sta qcnt
        lda rd_nb+1
        sta qcnt+1
        lda #1
        sta ia
        lda #0
        sta ia+1
rd_dl_f:   lda qcnt
        ora qcnt+1
        beq rd_dl_r
        ldy #0
        lda ia
        sta (dp),y
        iny
        lda ia+1
        sta (dp),y
        clc
        lda dp
        adc #2
        sta dp
        bcc rd_dl_f1
        inc dp+1
rd_dl_f1:  inc ia
        bne rd_dl_f2
        inc ia+1
rd_dl_f2:  lda qcnt
        bne rd_dl_f3
        dec qcnt+1
rd_dl_f3:  dec qcnt
        jmp rd_dl_f
rd_dl_r:   lda #2                  ; the result: a of them
        sta nt
        lda #1
        sta nrk
        lda rd_na
        sta nn
        sta nd0
        lda rd_na+1
        sta nn+1
        sta nd0+1
        jsr newarr
        bcc rd_dl_6
        rts
rd_dl_6:   jsr topcell             ; the permutation
        jsr getval
        lda vp
        sta rd_pp
        lda vp+1
        sta rd_pp+1
        lda #0
        sta rd_i
        sta rd_i+1
rd_dl_l:   lda rd_i                ; for i below a
        cmp rd_na
        bne rd_dl_go
        lda rd_i+1
        cmp rd_na+1
        bne rd_dl_go
        jmp rd_dl_done
rd_dl_go:  jsr rd_draw
        sec                     ; j = i + ((r * (b - i)) >> 16)
        lda rd_nb
        sbc rd_i
        sta bl
        lda rd_nb+1
        sbc rd_i+1
        sta bh
        jsr rd_scale
        clc
        lda p2
        adc rd_i
        sta p2
        lda p3
        adc rd_i+1
        sta p3
        asl p2                  ; the addresses of perm[j] (in cs) and perm[i] (in cd)
        rol p3
        clc
        lda rd_pp
        adc p2
        sta cs
        lda rd_pp+1
        adc p3
        sta cs+1
        lda rd_i
        sta p2
        lda rd_i+1
        sta p3
        asl p2
        rol p3
        clc
        lda rd_pp
        adc p2
        sta cd
        lda rd_pp+1
        adc p3
        sta cd+1
        ldy #0                  ; swap them
        lda (cs),y
        tax
        lda (cd),y
        sta (cs),y
        txa
        sta (cd),y
        iny
        lda (cs),y
        tax
        lda (cd),y
        sta (cs),y
        txa
        sta (cd),y
        ldy #0                  ; the result gets perm[i]
        lda (cd),y
        sta (dp),y
        iny
        lda (cd),y
        sta (dp),y
        clc
        lda dp
        adc #2
        sta dp
        bcc rd_dl_n
        inc dp+1
rd_dl_n:   inc rd_i
        bne rd_dl_j
        inc rd_i+1
rd_dl_j: jmp rd_dl_l
rd_dl_done:
        sec                     ; the permutation goes, and the result replaces the two arguments
        lda vsp
        sbc #4
        sta vsp
        lda vsp+1
        sbc #0
        sta vsp+1
        jmp setdy
