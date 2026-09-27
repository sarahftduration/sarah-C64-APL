; Code the two graphics overlays (gfx.inc and draw.inc) share: each includes this file in a block of its own, so each has a
; copy of it. See gfx.inc.

gq_v:   .word 0                 ; the last number read (int16)
gq_a:   .byte 0
gq_c:   .fill 8                 ; up to four numbers, as words
gq_t:   .word 0
gq_k:   .byte 0
gq_svp: .byte 0                 ; the processor status and $01 kept by gq_ron
gq_sv1: .byte 0

gq_nonce:
        lda #E_NONCE
        sec
        rts

; the result of a function is a dummy INT 0: the evaluator drops it and lets the statement end (qfin)
gq_ret1: jsr gq_dummy
        jmp setmon
gq_ret2: jsr gq_dummy
        jmp setdy
gq_dummy:
        lda #2
        sta cv
        lda #0
        sta cv+1
        sta cv+2
        sta cv+3
        rts


; --- the checks the functions share ---------------------------------------------------------------------------------------
gq_mode: bit gr_on
        bmi gqm_ok
        lda #E_NOGR
        sec
        rts
gqm_ok: clc
        rts

gq_top: jsr topcell
        jmp getval
gq_sec: jsr secondcell
        jmp getval

; the argument just fetched must not be CHARs
gq_type: lda vt
        cmp #1
        bne gqt_ok
        lda #E_DOMAIN
        sec
        rts
gqt_ok: clc
        rts

; the argument must have A elements (A below 256)
gq_isn: cmp vn
        bne gqi_bad
        lda vn+1
        bne gqi_bad
        clc
        rts
gqi_bad: lda #E_LENGTH
        sec
        rts

; the element at ep (of type vt) as an int16 in gq_v: floats are floored, and saturate at -32768 and 32767. X is kept.
gq_elem:
        ldy #0
        lda vt
        beq gqe_b
        cmp #2
        beq gqe_i
        lda (ep),y
        sta fa
        iny
        lda (ep),y
        sta fa+1
        iny
        lda (ep),y
        sta fa+2
        txa                     ; (flr_q uses X)
        pha
        jsr flr_q
        sta gq_a
        pla
        tax
        lda gq_a
        cmp #1
        beq gqe_big
        lda sgn
        bmi gqe_neg
        lda ia
        sta gq_v
        lda ia+1
        sta gq_v+1
        rts
gqe_neg: sec                    ; (the magnitude is at most 32768)
        lda #0
        sbc ia
        sta gq_v
        lda #0
        sbc ia+1
        sta gq_v+1
        rts
gqe_big: lda fa+1
        bmi gqe_bn
        lda #$ff
        sta gq_v
        lda #$7f
        sta gq_v+1
        rts
gqe_bn: lda #0
        sta gq_v
        lda #$80
        sta gq_v+1
        rts
gqe_b:  lda (ep),y
        sta gq_v
        lda #0
        sta gq_v+1
        rts
gqe_i:  lda (ep),y
        sta gq_v
        iny
        lda (ep),y
        sta gq_v+1
        rts

; ep += the width of a vt element
gq_next:
        ldy vt
        lda WIDTHT,y
        clc
        adc ep
        sta ep
        bcc gqn_r
        inc ep+1
gqn_r:  rts

; the argument just fetched (at most four elements): its numbers into gq_c from offset X
gq_readn:
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        lda vn
        sta gq_k
gqr_l:  lda gq_k
        beq gqr_d
        jsr gq_elem
        lda gq_v
        sta gq_c,x
        lda gq_v+1
        sta gq_c+1,x
        inx
        inx
        jsr gq_next
        dec gq_k
        jmp gqr_l
gqr_d:  rts


; the CPU sees RAM under the KERNAL while interrupts are off and $01 has HIRAM clear
gq_ron: php
        pla
        sta gq_svp
        sei
        lda $01
        sta gq_sv1
        and #$fd
        sta $01
        rts
gq_roff: lda gq_sv1
        sta $01
        lda gq_svp
        pha
        plp
        rts

