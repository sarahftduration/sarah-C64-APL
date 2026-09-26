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
