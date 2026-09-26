; Dyadic /: replicate and compress. Spec: apl64.py replicate. Included by eval.asm.
; The left operand is the top cell, the right one below. Checks in the model's order: the left
; argument's rank and whole-number-ness (arg_ints), the right argument's rank, the lengths,
; negative counts, the size.

yk      = WS+$b9                ; (2) elements of the left argument
ym      = WS+$bb                ; (2) elements of the right argument
yt      = WS+$bd                ; type of the right argument, and of the result
ylt     = WS+$be                ; type of the left argument
ytot    = WS+$bf                ; (2) the result's size
yneg    = WS+$c1
yovf    = WS+$c2
yp      = WS+$c3                ; (2) pairs of (count, element) still to do
ywr     = WS+$c9                ; element width of the right argument
ywl     = WS+$ca                ; ... of the left

p_repl: jsr topcell
        jsr arg_ints            ; RANK, DOMAIN
        bcc yq_1
        rts
yq_1:   lda qan
        sta yk
        lda qan+1
        sta yk+1
        jsr secondcell
        jsr getval
        lda vrk
        cmp #2
        bcc yq_2
        lda #E_NONCE
        sec
        rts
yq_2:   lda vt
        sta yt
        lda vn
        sta ym
        lda vn+1
        sta ym+1
        lda yk                  ; k = m, or one of them is 1
        cmp ym
        bne yq_l
        lda yk+1
        cmp ym+1
        beq yq_3
yq_l:   lda yk+1
        bne yq_4
        lda yk
        cmp #1
        beq yq_3
yq_4:   lda ym+1
        bne yq_5
        lda ym
        cmp #1
        beq yq_3
yq_5:   lda #E_LENGTH
        sec
        rts
yq_3:   jsr topcell             ; add up the counts, noting negative and huge ones
        jsr getval
        lda vt
        sta ylt
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        lda vn
        sta qcnt
        lda vn+1
        sta qcnt+1
        lda #0
        sta ytot
        sta ytot+1
        sta yneg
        sta yovf
yq_s:   lda qcnt
        ora qcnt+1
        beq yq_d
        jsr elem_to_int
        lda ineg
        ora yneg
        sta yneg
        lda ihuge
        ora yovf
        sta yovf
        clc
        lda ytot
        adc im
        sta ytot
        lda ytot+1
        adc im+1
        sta ytot+1
        bcc yq_n
        lda #1
        sta yovf
yq_n:   ldx ylt
        clc
        lda ep
        adc WIDTHT,x
        sta ep
        bcc yq_c
        inc ep+1
yq_c:   lda qcnt
        bne yq_e
        dec qcnt+1
yq_e:   dec qcnt
        jmp yq_s
yq_d:   lda yk+1                ; one count for many elements: count * m
        bne yq_6
        lda yk
        cmp #1
        bne yq_6
        lda ym+1
        bne yq_7
        lda ym
        cmp #1
        beq yq_6
        lda ym                  ; no elements: the count is not used, whatever it was
        ora ym+1
        bne yq_7
        sta yneg
        sta yovf
        sta ytot
        sta ytot+1
        beq yq_6
yq_7:   lda ytot
        sta p0
        lda ytot+1
        sta p1
        lda ym
        sta bl
        lda ym+1
        sta bh
        jsr mul16
        lda p2
        ora p3
        beq yq_8
        lda #1
        sta yovf
yq_8:   lda p0
        sta ytot
        lda p1
        sta ytot+1
yq_6:   lda yneg
        beq yq_9
        lda #E_DOMAIN
        sec
        rts
yq_9:   lda yovf
        beq yq_a
        lda #E_WSFULL
        sec
        rts
yq_a:   lda yt
        sta nt
        lda #1
        sta nrk
        lda ytot
        sta nn
        sta nd0
        lda ytot+1
        sta nn+1
        sta nd0+1
        jsr newarr
        bcc yq_b
        rts
yq_b:   jsr topcell             ; (the collector may have moved them) the left cursor
        jsr getval
        lda vp
        sta qsrc
        lda vp+1
        sta qsrc+1
        ldx vt
        lda WIDTHT,x
        sta ywl
        jsr secondcell          ; the right cursor
        jsr getval
        lda vp
        sta mp
        lda vp+1
        sta mp+1
        ldx yt
        lda WIDTHT,x
        sta ywr
        lda yk+1                ; pairs: the right argument's length, or the left's
        bne yq_f
        lda yk
        cmp #1
        bne yq_f
        lda ym
        sta yp
        lda ym+1
        sta yp+1
        jmp yq_g
yq_f:   lda yk
        sta yp
        lda yk+1
        sta yp+1
yq_g:   lda yp
        ora yp+1
        bne yq_h
        jmp setdy
yq_h:   lda qsrc                ; the count of this pair
        sta ep
        lda qsrc+1
        sta ep+1
        lda ylt
        sta vt
        jsr elem_to_int
        lda im
        sta qcnt
        lda im+1
        sta qcnt+1
yq_r:   lda qcnt
        ora qcnt+1
        beq yq_x
        ldy #0
yq_y:   lda (mp),y
        sta (dp),y
        iny
        cpy ywr
        bne yq_y
        clc
        lda dp
        adc ywr
        sta dp
        bcc yq_z
        inc dp+1
yq_z:   lda qcnt
        bne yq_w
        dec qcnt+1
yq_w:   dec qcnt
        jmp yq_r
yq_x:   lda yk+1                ; on to the next pair: each cursor moves unless its argument
        bne yq_m                ; has a single element
        lda yk
        cmp #1
        beq yq_o
yq_m:   clc
        lda qsrc
        adc ywl
        sta qsrc
        bcc yq_o
        inc qsrc+1
yq_o:   lda ym+1
        bne yq_q
        lda ym
        cmp #1
        beq yq_p
yq_q:   clc
        lda mp
        adc ywr
        sta mp
        bcc yq_p
        inc mp+1
yq_p:   lda yp
        bne yq_t
        dec yp+1
yq_t:   dec yp
        jmp yq_g

; --- expand: a\b ------------------------------------------------------------------------------------------
; Spec: apl64.py expand. The left operand is the top cell, the right one below it. a is 0s and 1s (RANK,
; DOMAIN from arg_ints, then NONCE for a matrix b, DOMAIN for other values, LENGTH unless b is a scalar or has
; one element per 1); the result is a vector as long as a: the next element of b where a has a 1 (a scalar
; b is used again each time), a blank or a 0 where it has a 0.

xp_n:    .word 0                ; the length of a
xp_ones: .word 0                ; its 1s
xp_bt:   .byte 0                ; b's type, rank, count and element width
xp_br:   .byte 0
xp_bn:   .word 0
xp_bw:   .byte 0

p_expand:
        jsr topcell
        jsr arg_ints
        bcc xp_1
        rts
xp_1:   lda qan
        sta xp_n
        lda qan+1
        sta xp_n+1
        jsr secondcell
        jsr getval
        lda vrk
        cmp #2
        bcc xp_2
        lda #E_NONCE
        sec
        rts
xp_2:   sta xp_br
        lda vt
        sta xp_bt
        lda vn
        sta xp_bn
        lda vn+1
        sta xp_bn+1
        ldx vt
        lda WIDTHT,x
        sta xp_bw
        jsr topcell             ; count the 1s
        jsr getval
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        lda vn
        sta qcnt
        lda vn+1
        sta qcnt+1
        lda #0
        sta xp_ones
        sta xp_ones+1
xp_c:   lda qcnt
        ora qcnt+1
        beq xp_cd
        jsr elem_to_int
        lda ineg
        ora ihuge
        ora im+1
        bne xp_dom
        lda im
        beq xp_z
        cmp #1
        bne xp_dom
        inc xp_ones
        bne xp_z
        inc xp_ones+1
xp_z:   ldx vt
        clc
        lda ep
        adc WIDTHT,x
        sta ep
        bcc xp_z1
        inc ep+1
xp_z1:  lda qcnt
        bne xp_z2
        dec qcnt+1
xp_z2:  dec qcnt
        jmp xp_c
xp_dom: lda #E_DOMAIN
        sec
        rts
xp_cd:  lda xp_br               ; a vector b needs one element for each 1
        beq xp_al
        lda xp_bn
        cmp xp_ones
        bne xp_len
        lda xp_bn+1
        cmp xp_ones+1
        bne xp_len
xp_al:  lda xp_bt
        sta nt
        lda #1
        sta nrk
        lda xp_n
        sta nn
        sta nd0
        lda xp_n+1
        sta nn+1
        sta nd0+1
        jsr newarr
        bcc xp_go
        rts
xp_len: lda #E_LENGTH
        sec
        rts
xp_go:  jsr secondcell          ; (the collector may have moved them) b's cursor
        jsr getval
        lda vp
        sta mp
        lda vp+1
        sta mp+1
        jsr topcell             ; a's cursor
        jsr getval
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        lda vn
        sta qcnt
        lda vn+1
        sta qcnt+1
xp_l:   lda qcnt
        ora qcnt+1
        beq xp_done
        jsr elem_to_int
        ldy #0
        lda im
        beq xp_fill
xp_k:   lda (mp),y              ; a 1: the next element of b
        sta (dp),y
        iny
        cpy xp_bw
        bne xp_k
        lda xp_br
        beq xp_adv              ; (a scalar b stays)
        clc
        lda mp
        adc xp_bw
        sta mp
        bcc xp_adv
        inc mp+1
        jmp xp_adv
xp_fill:
        lda #0                  ; a 0: a blank for characters, else zeros
        ldx xp_bt
        cpx #1
        bne xp_f1
        lda #' '
xp_f1:  sta (dp),y
        iny
        cpy xp_bw
        bne xp_f1
xp_adv: clc
        lda dp
        adc xp_bw
        sta dp
        bcc xp_a1
        inc dp+1
xp_a1:  ldx vt
        clc
        lda ep
        adc WIDTHT,x
        sta ep
        bcc xp_a2
        inc ep+1
xp_a2:  lda qcnt
        bne xp_a3
        dec qcnt+1
xp_a3:  dec qcnt
        jmp xp_l
xp_done: jmp setdy
