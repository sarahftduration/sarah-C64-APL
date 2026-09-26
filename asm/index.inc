; Indexing: A[i], A[i;j]. Spec: apl64.py index_value. Included by eval.asm.
;
; The evaluator leaves, on the value stack from the bottom: a marker cell (tag $81), the
; index groups from the last to the first (an elided axis is a cell with tag $82), then the
; indexed array on top. p_index replaces all of them with the result. Checks run in the
; model's order: axis count (RANK), then per axis the index type (DOMAIN) and range
; (INDEX), then the result rank (LIMIT), then the size (WS FULL).
;
; Variables are in the cassette-buffer scratch, in bytes no other routine here uses;
; per-axis tables have a stride of 2 so that X = 2 * axis indexes them all.

xk      = WS+$b9                ; number of index groups
xmk     = WS+$ba                ; (2) the marker cell
xt      = WS+$bc                ; type of the indexed array
xrk     = WS+$bd                ; its rank
xd      = WS+$be                ; (2+2) its dimensions
xf      = WS+$c2                ; an index was out of range
xa      = WS+$c3                ; current axis (times 2 while filling)
xw      = WS+$c4                ; element width
xpn     = WS+$d4                ; (2+2) number of index elements per axis
xpt     = WS+$d8                ; type of the index per axis, $ff when elided; xpt+1: dims overflow
xrem    = WS+$dc                ; (2+2) elements of the axis still to visit
xp1i    = WS+$e0                ; (2) start of axis 1's cursor
xlin    = WS+$e2                ; (2) element number in the indexed array
xrow    = WS+$e4                ; (2) start of the current row
xov     = xpt+1
xcur    = qsrc                  ; axis cursors: qsrc for axis 0, mp for axis 1 (stride 2)
xbase   = sp                    ; data pointer of the indexed array

; cptr = the cell of index group A (0-based)
axcell: sec
        lda vsp
        sbc #8
        sta cptr
        lda vsp+1
        sbc #0
        sta cptr+1
        cpx #0
        beq axc1
        sec
        lda cptr
        sbc #4
        sta cptr
        bcs axc1
        dec cptr+1
axc1:   rts

; append the dimension in qd0 to the result shape (nrk counts them)
adddim: lda nrk
        bne ad1
        lda qd0
        sta nd0
        lda qd0+1
        sta nd0+1
        jmp ad3
ad1:    cmp #1
        bne ad2
        lda qd0
        sta nd1
        lda qd0+1
        sta nd1+1
        jmp ad3
ad2:    lda #1
        sta xov
        rts
ad3:    inc nrk
        rts

p_index:
        jsr topcell
        jsr getval
        lda vt
        sta xt
        lda vrk
        sta xrk
        lda vs0
        sta xd
        lda vs0+1
        sta xd+1
        lda vs1
        sta xd+2
        lda vs1+1
        sta xd+3
        lda #0
        sta xk
px_w:   sec                     ; walk down to the marker, counting the groups
        lda cptr
        sbc #4
        sta cptr
        bcs px_w1
        dec cptr+1
px_w1:  ldy #0
        lda (cptr),y
        cmp #$81
        beq px_wd
        inc xk
        jmp px_w
px_wd:  lda cptr
        sta xmk
        lda cptr+1
        sta xmk+1
        lda xk
        cmp xrk
        beq px_ax
        lda #E_RANK
        sec
        rts

; phase 1: validate every axis and build the result's shape
px_ax:  lda #0
        sta xa
        sta nrk
        sta xov
px_a1:  lda xa
        asl
        tax
        lda xa
        jsr axcell_a
        ldy #0
        lda (cptr),y
        cmp #$82
        bne px_arr
        lda #$ff                ; elided: the whole axis
        sta xpt,x
        lda xd,x
        sta xpn,x
        sta qd0
        lda xd+1,x
        sta xpn+1,x
        sta qd0+1
        jsr adddim
        jmp px_next
px_arr: jsr getval
        lda xa
        asl
        tax
        lda vt
        sta xpt,x
        lda vn
        sta xpn,x
        lda vn+1
        sta xpn+1,x
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        lda vn
        sta qcnt
        lda vn+1
        sta qcnt+1
        lda #0
        sta xf
px_v:   lda qcnt
        ora qcnt+1
        beq px_vd
        jsr elem_to_int
        bcc px_v1
        lda #E_DOMAIN
        sec
        rts
px_v1:  lda xa
        asl
        tax
        lda ineg
        ora ihuge
        bne px_bad
        lda im
        ora im+1
        beq px_bad
        lda xd,x                ; dim < index?
        cmp im
        lda xd+1,x
        sbc im+1
        bcs px_adv
px_bad: lda #1
        sta xf
px_adv: ldx vt
        clc
        lda ep
        adc WIDTHT,x
        sta ep
        bcc px_a3
        inc ep+1
px_a3:  lda qcnt
        bne px_a4
        dec qcnt+1
px_a4:  dec qcnt
        jmp px_v
px_vd:  lda xf
        beq px_shape
        lda #E_INDEX
        sec
        rts
px_shape:
        lda vrk                 ; the index's own dimensions join the result's
        beq px_next
        lda vs0
        sta qd0
        lda vs0+1
        sta qd0+1
        jsr adddim
        lda vrk
        cmp #2
        bcc px_next
        lda vs1
        sta qd0
        lda vs1+1
        sta qd0+1
        jsr adddim
px_next:
        inc xa
        lda xa
        cmp xk
        beq px_done
        jmp px_a1
px_done:
        lda xov
        beq px_n
        lda #E_LIMIT
        sec
        rts
px_n:   lda xk                  ; result count
        cmp #2
        beq px_mul
        lda xpn
        sta nn
        lda xpn+1
        sta nn+1
        jmp px_alloc
px_mul: lda xpn
        sta p0
        lda xpn+1
        sta p1
        lda xpn+2
        sta bl
        lda xpn+3
        sta bh
        jsr mul16
        lda p2
        ora p3
        beq px_m1
        lda #E_WSFULL
        sec
        rts
px_m1:  lda p0
        sta nn
        lda p1
        sta nn+1
px_alloc:
        ldx xt
        lda WIDTHT,x
        sta xw
        lda nrk
        bne px_new
        lda xt                  ; scalar result: build it in cv
        sta cv
        lda #0
        sta cv+1
        sta cv+2
        sta cv+3
        lda #<(cv+1)
        sta dp
        lda #>(cv+1)
        sta dp+1
        jmp px_fill
px_new: lda xt
        sta nt
        jsr newarr
        bcc px_fill
        rts

; phase 2: gather. Nothing here allocates, so the addresses derived now stay valid.
px_fill:
        lda nn
        ora nn+1
        bne px_go
        jmp px_fin
px_go:  jsr topcell
        jsr getval
        lda vp
        sta xbase
        lda vp+1
        sta xbase+1
        lda #0
        sta xa
px_i:   lda xa
        asl
        tax
        lda xpn,x
        sta xrem,x
        lda xpn+1,x
        sta xrem+1,x
        lda xpt,x
        cmp #$ff
        bne px_i1
        lda #1                  ; elided: the cursor counts 1, 2, ...
        sta xcur,x
        lda #0
        sta xcur+1,x
        jmp px_i2
px_i1:  lda xa
        jsr axcell_a
        jsr getval
        lda xa
        asl
        tax
        lda vp
        sta xcur,x
        lda vp+1
        sta xcur+1,x
px_i2:  inc xa
        lda xa
        cmp xk
        bne px_i
        lda xcur+2              ; axis 1 restarts for every row
        sta xp1i
        lda xcur+3
        sta xp1i+1
        lda #0
        sta xrow
        sta xrow+1
        lda xk
        cmp #2
        beq px_mat
px_vec: ldx #0
        jsr ax_next
        jsr gather
        jsr dec_rem0
        bne px_vec
        jmp px_fin
px_mat: ldx #0
        jsr ax_next             ; row r: xrow = (r-1) * columns
        sec
        lda im
        sbc #1
        sta p0
        lda im+1
        sbc #0
        sta p1
        lda xd+2
        sta bl
        lda xd+3
        sta bh
        jsr mul16
        lda p0
        sta xrow
        lda p1
        sta xrow+1
        lda xp1i
        sta xcur+2
        lda xp1i+1
        sta xcur+3
        lda xpn+2
        sta xrem+2
        lda xpn+3
        sta xrem+3
px_col: ldx #2
        jsr ax_next
        jsr gather
        lda xrem+2
        bne px_c1
        dec xrem+3
px_c1:  dec xrem+2
        lda xrem+2
        ora xrem+3
        bne px_col
        jsr dec_rem0
        bne px_mat
px_fin: lda xmk                 ; the result replaces the marker, the groups and the array
        sta cptr
        clc
        adc #4
        sta vsp
        lda xmk+1
        sta cptr+1
        adc #0
        sta vsp+1
        ldy #3
px_f1:  lda cv,y
        sta (cptr),y
        dey
        bpl px_f1
        clc
        rts

; the group number in A -> cptr (X is preserved as 2 * A)
axcell_a:
        pha
        tax
        jsr axcell
        pla
        asl
        tax
        rts

dec_rem0:
        lda xrem
        bne dr1
        dec xrem+1
dr1:    dec xrem
        lda xrem
        ora xrem+1
        rts

; im = the next index of axis X/2, 1-based
ax_next:
        stx xa
        lda xpt,x
        cmp #$ff
        bne an1
        lda xcur,x
        sta im
        lda xcur+1,x
        sta im+1
        inc xcur,x
        bne an_r
        inc xcur+1,x
an_r:   rts
an1:    sta vt
        lda xcur,x
        sta ep
        lda xcur+1,x
        sta ep+1
        jsr elem_to_int
        ldx xa
        ldy vt
        lda WIDTHT,y
        clc
        adc xcur,x
        sta xcur,x
        bcc an_r
        inc xcur+1,x
        rts

; copy the element (xrow + im - 1) of the indexed array to dp
gather: clc
        lda xrow
        adc im
        sta xlin
        lda xrow+1
        adc im+1
        sta xlin+1
        lda xlin
        bne ga1
        dec xlin+1
ga1:    dec xlin
        lda xlin
        sta cs
        lda xlin+1
        sta cs+1
        lda xw
        cmp #1
        beq ga_a
        asl cs
        rol cs+1
        lda xw
        cmp #3
        bne ga_a
        clc
        lda cs
        adc xlin
        sta cs
        lda cs+1
        adc xlin+1
        sta cs+1
ga_a:   clc
        lda cs
        adc xbase
        sta cs
        lda cs+1
        adc xbase+1
        sta cs+1
        ldy #0
ga_c:   lda (cs),y
        sta (dp),y
        iny
        cpy xw
        bne ga_c
        clc
        lda dp
        adc xw
        sta dp
        bcc ga_r
        inc dp+1
ga_r:   rts
