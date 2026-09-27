; Factorial and binomial (an overlay, see overlay.inc): the kernels of ! for the scalar engine, which loads this one
; for the operations 20 and 24. Spec: apl64.py f_fact, f_binom. fa = the (left) argument, fb = the right one; the
; result is in fa; carry set and A = the error on failure. Whole numbers from 0 to 65535 only (DOMAIN ERROR
; otherwise); the products are taken a step at a time through the same float routines as the model.

fx_mv_wl:   .byte 0
fx_mv_wh:   .byte 0
fx_mv_na:   .word 0
fx_mv_nb:   .word 0
fx_mv_i:    .word 0
fx_mv_kk:   .word 0
fx_mv_neg:  .byte 0
fx_mv_t:    .fill 3
fx_mv_tb:   .fill 3
fx_mv_ta:   .fill 3

fx_mk_fbfa: ldx #2
fx_mf_1:   lda fb,x
        sta fa,x
        dex
        bpl fx_mf_1
        rts
fx_mk_zero: lda #0
        sta fa
        sta fa+1
        sta fa+2
        clc
        rts
fx_mk_dom: lda #E_DOMAIN
        sec
        rts

; fa = a whole number from 0 to 65535 -> carry clear, ia = it; else carry set (negative, not whole, or too big)
fx_mk_whole:
        ldx #2
fx_mw_1:   lda fa,x
        sta fx_mv_t,x
        dex
        bpl fx_mw_1
        jsr flr_q
        cmp #1
        bne fx_mw_s
        lda fx_mv_t             ; 32768 and above: whole already; only 32768 to 65535 (exponent 144) fits
        cmp #144
        bne fx_mw_bad
        lda fx_mv_t+1
        bmi fx_mw_bad           ; (negative)
        ora #$80
        sta ia+1
        lda fx_mv_t+2
        sta ia
        clc
        rts
fx_mw_s: lda ia
        sta fx_mv_wl
        lda ia+1
        sta fx_mv_wh
        lda sgn
        sta fx_mv_neg
        jsr m_to_f
        ldx #2
fx_mw_2:   lda fa,x
        cmp fx_mv_t,x
        bne fx_mw_bad
        dex
        bpl fx_mw_2
        lda fx_mv_neg
        bpl fx_mw_ok
        lda fx_mv_wl
        ora fx_mv_wh
        bne fx_mw_bad              ; below zero
fx_mw_ok:  lda fx_mv_wl
        sta ia
        lda fx_mv_wh
        sta ia+1
        clc
        rts
fx_mw_bad: sec
        rts

; fa = ia (unsigned) as a float, fb = the same (both scratch); used by the loops below
fx_mv_uf:  lda #0
        sta sgn
        jmp m_to_f

; the factorial of fb
k_ffact:
        jsr fx_mk_fbfa
        jsr fx_mk_whole
        bcc fx_mfa_ok
        jmp fx_mk_dom
fx_mfa_ok:  lda ia
        sta fx_mv_na
        lda ia+1
        sta fx_mv_na+1
        jsr fx_mk_one_t            ; mv_t = 1
        lda #2
        sta fx_mv_i
        lda #0
        sta fx_mv_i+1
fx_mfa_l:   lda fx_mv_na+1             ; done when i > n
        cmp fx_mv_i+1
        bcc fx_mfa_done
        bne fx_mfa_go
        lda fx_mv_na
        cmp fx_mv_i
        bcc fx_mfa_done
fx_mfa_go:  lda fx_mv_i
        sta ia
        lda fx_mv_i+1
        sta ia+1
        jsr fx_mv_uf
        ldx #2
fx_mfa_1:   lda fa,x
        sta fb,x
        lda fx_mv_t,x
        sta fa,x
        dex
        bpl fx_mfa_1
        jsr f_mul
        bcs fx_mfa_dom
        ldx #2
fx_mfa_2:   lda fa,x
        sta fx_mv_t,x
        dex
        bpl fx_mfa_2
        inc fx_mv_i
        bne fx_mfa_l
        inc fx_mv_i+1
        jmp fx_mfa_l
fx_mfa_done: ldx #2
fx_mfa_3:   lda fx_mv_t,x
        sta fa,x
        dex
        bpl fx_mfa_3
        clc
        rts
fx_mfa_dom: jmp fx_mk_dom

; mv_t = 1
fx_mk_one_t:
        lda #$81                ; 1.0
        sta fx_mv_t
        lda #0
        sta fx_mv_t+1
        sta fx_mv_t+2
        rts

; a!b: fa = a, fb = b
k_fbinom:
        ldx #2
fx_kb_1:   lda fb,x
        sta fx_mv_tb,x
        dex
        bpl fx_kb_1
        jsr fx_mk_whole            ; a
        bcc fx_kb_2
        jmp fx_mk_dom
fx_kb_2:   lda ia
        sta fx_mv_na
        lda ia+1
        sta fx_mv_na+1
        ldx #2
fx_kb_3:   lda fx_mv_tb,x
        sta fa,x
        dex
        bpl fx_kb_3
        jsr fx_mk_whole            ; b
        bcc fx_kb_4
        jmp fx_mk_dom
fx_kb_4:   lda ia
        sta fx_mv_nb
        lda ia+1
        sta fx_mv_nb+1
        lda fx_mv_na+1             ; a above b: 0
        cmp fx_mv_nb+1
        bcc fx_kb_5
        bne fx_kb_zero
        lda fx_mv_na
        cmp fx_mv_nb
        bcc fx_kb_5
        beq fx_kb_5
fx_kb_zero: jmp fx_mk_zero
fx_kb_5:   sec                     ; k = the smaller of a and b - a
        lda fx_mv_nb
        sbc fx_mv_na
        sta fx_mv_kk
        lda fx_mv_nb+1
        sbc fx_mv_na+1
        sta fx_mv_kk+1
        lda fx_mv_na+1             ; k = a if a < b - a
        cmp fx_mv_kk+1
        bcc fx_kb_ka
        bne fx_kb_6
        lda fx_mv_na
        cmp fx_mv_kk
        bcs fx_kb_6
fx_kb_ka:  lda fx_mv_na
        sta fx_mv_kk
        lda fx_mv_na+1
        sta fx_mv_kk+1
fx_kb_6:   jsr fx_mk_one_t
        lda #1
        sta fx_mv_i
        lda #0
        sta fx_mv_i+1
fx_kb_l:   lda fx_mv_kk+1             ; done when i > k
        cmp fx_mv_i+1
        bcc fx_kb_done
        bne fx_kb_go
        lda fx_mv_kk
        cmp fx_mv_i
        bcc fx_kb_done
fx_kb_go:  sec                     ; fb = b - k + i
        lda fx_mv_nb
        sbc fx_mv_kk
        sta ia
        lda fx_mv_nb+1
        sbc fx_mv_kk+1
        sta ia+1
        clc
        lda ia
        adc fx_mv_i
        sta ia
        lda ia+1
        adc fx_mv_i+1
        sta ia+1
        jsr fx_mv_uf
        ldx #2
fx_kb_7:   lda fa,x
        sta fb,x
        lda fx_mv_t,x
        sta fa,x
        dex
        bpl fx_kb_7
        jsr f_mul
        bcs fx_kb_dom
        ldx #2
fx_kb_8:   lda fa,x
        sta fx_mv_ta,x             ; (the product waits here while i becomes a float)
        dex
        bpl fx_kb_8
        lda fx_mv_i
        sta ia
        lda fx_mv_i+1
        sta ia+1
        jsr fx_mv_uf
        ldx #2
fx_kb_9:   lda fa,x
        sta fb,x
        lda fx_mv_ta,x
        sta fa,x
        dex
        bpl fx_kb_9
        jsr f_div
        bcs fx_kb_dom
        ldx #2
fx_kb_a:   lda fa,x
        sta fx_mv_t,x
        dex
        bpl fx_kb_a
        inc fx_mv_i
        bne fx_kb_j
        inc fx_mv_i+1
fx_kb_j:   jmp fx_kb_l
fx_kb_done: ldx #2
fx_kb_b:   lda fx_mv_t,x
        sta fa,x
        dex
        bpl fx_kb_b
        clc
        rts
fx_kb_dom: jmp fx_mk_dom

