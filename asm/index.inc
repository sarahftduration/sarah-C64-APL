; Indexing: A[i], A[i;j] and A[i;j]<-v. Spec: apl64.py index_value, index_assign.
; Included by eval.asm.
;
; The evaluator leaves, on the value stack from the bottom: (for an assignment, the value v),
; a marker cell (tag $81), the index groups from the last to the first (an elided axis is a
; cell with tag $82), then the indexed array on top. p_index replaces the marker, the groups
; and the array by the result. p_iasg builds the changed array, stores it in the variable
; xvar and leaves v. Checks run in the model's order: axis count (RANK), then per axis the
; index type (DOMAIN) and range (INDEX), then the selection's rank (LIMIT); then p_index
; checks the size (WS FULL) and p_iasg the shape of v (RANK, LENGTH) and the types (DOMAIN).
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
xtmp    = WS+$c9                ; (3) one element of v in the type of the result
xvar    = WS+$cc                ; the variable being assigned
xvt     = WS+$cd                ; type of v
xvsc    = WS+$ce                ; v is a scalar
xemp    = WS+$cf                ; the selection is empty
xmode   = WS+$ea                ; 0 gather (index), 1 scatter (assignment)
xbig    = WS+$ec                ; the selection has 65536 or more elements
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

; Validate the indices against the array on top of the stack and work out the selection:
; nrk, nd0, nd1 its shape, nn its count (low 16 bits), xbig, xemp, xmk, xk, xt, xrk, xd.
ix_prep:
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
px_n:   lda #0
        sta xbig
        lda xk                  ; selection count
        cmp #2
        beq px_mul
        lda xpn
        sta nn
        lda xpn+1
        sta nn+1
        ora nn
        jmp px_e
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
        sta xbig
        lda p0
        sta nn
        lda p1
        sta nn+1
        ora p0
        ora p2
        ora p3
px_e:   ldx #0                  ; A = 0 iff the selection is empty
        cmp #0
        bne px_e1
        inx
px_e1:  stx xemp
        clc
        rts

p_index:
        jsr ix_prep
        bcc pi_1
        rts
pi_1:   lda xbig
        beq pi_2
        lda #E_WSFULL
        sec
        rts
pi_2:   lda #0
        sta xmode
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
        lda xemp
        beq px_go
        jmp px_fin
px_go:  jsr topcell
        jsr getval
        lda vp
        sta xbase
        lda vp+1
        sta xbase+1
        jsr fill_run
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

; Visit the selection in order, calling act for each element with xrow + im - 1 the
; element number in the indexed array. The cursors are re-derived here, so this may only
; run when nothing allocates.
fill_run:
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
        jsr act
        jsr dec_rem0
        bne px_vec
        rts
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
        jsr act
        lda xrem+2
        bne px_c1
        dec xrem+3
px_c1:  dec xrem+2
        lda xrem+2
        ora xrem+3
        bne px_col
        jsr dec_rem0
        bne px_mat
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

act:    lda xmode
        bne scatter
        jsr elemaddr
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

; cs = xbase + (xrow + im - 1) * xw
elemaddr:
        clc
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
        rts

; assignment: the next element of v (or the scalar v) goes to the selected element
scatter:
        lda xvsc
        bne sx1
        jsr conv1
        ldx xvt
        clc
        lda op
        adc WIDTHT,x
        sta op
        bcc sx1
        inc op+1
sx1:    jsr elemaddr
        ldy #0
sx2:    lda xtmp,y
        sta (cs),y
        iny
        cpy xw
        bne sx2
        rts

; the element of v at op, converted to the result's type nt, into xtmp
conv1:  lda op
        sta vp
        lda op+1
        sta vp+1
        lda xvt
        sta vt
        lda #1
        sta vn
        lda #0
        sta vn+1
        lda #<xtmp
        sta dp
        lda #>xtmp
        sta dp+1
        jmp cvcopy

; A[i;j]<-v: see the top of the file. xvar = the variable's symbol index.
p_iasg: jsr ix_prep
        bcc ia_1
        rts
ia_1:   sec                     ; v is just below the marker
        lda xmk
        sbc #4
        sta cptr
        lda xmk+1
        sbc #0
        sta cptr+1
        jsr getval
        lda vt
        sta xvt
        lda vrk
        beq ia_conf
        cmp nrk
        beq ia_c1
        lda #E_RANK
        sec
        rts
ia_c1:  lda vs0
        cmp nd0
        bne ia_len
        lda vs0+1
        cmp nd0+1
        bne ia_len
        lda vrk
        cmp #2
        bne ia_conf
        lda vs1
        cmp nd1
        bne ia_len
        lda vs1+1
        cmp nd1+1
        beq ia_conf
ia_len: lda #E_LENGTH
        sec
        rts
ia_conf:
        lda xemp                ; nothing selected: nothing changes
        beq ia_go
        jmp ia_fin
ia_go:  lda xt                  ; the type of the result
        cmp xvt
        beq ia_nt
        lda xt
        cmp #1
        beq ia_dom
        lda xvt
        cmp #1
        beq ia_dom
        lda xt
        cmp xvt
        bcs ia_nt
        lda xvt
ia_nt:  sta nt
        jsr topcell             ; a new array shaped like A
        jsr getval
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
        bcc ia_2
        rts
ia_dom: lda #E_DOMAIN
        sec
        rts
ia_2:   lda dp
        sta xbase
        lda dp+1
        sta xbase+1
        jsr topcell             ; A's elements, converted, into it
        jsr getval
        jsr cvcopy
        ldx nt
        lda WIDTHT,x
        sta xw
        sec                     ; v (its address may have moved)
        lda xmk
        sbc #4
        sta cptr
        lda xmk+1
        sbc #0
        sta cptr+1
        jsr getval
        lda vp
        sta op
        lda vp+1
        sta op+1
        lda #1
        sta xmode
        ldx #0
        lda vrk
        bne ia_3
        inx
ia_3:   stx xvsc
        txa
        beq ia_5
        jsr conv1               ; a scalar v is converted once
ia_5:   jsr fill_run
        lda xvar                ; the variable now holds the new array
        jsr varcell
        ldy #3
ia_6:   lda cv,y
        sta (cptr),y
        dey
        bpl ia_6
ia_fin: lda xmk                 ; drop the marker, the groups and the array; v stays
        sta vsp
        lda xmk+1
        sta vsp+1
        clc
        rts
