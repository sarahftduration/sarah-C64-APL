; Transpose and the axis check (an overlay, see overlay.inc): entered through s_transpose, s_transax and s_axis.

; --- transpose: ⍉B and A⍉B -------------------------------------------------------------------------------------
; Spec: apl64.py transpose, transpose_axes. A scalar or a vector is unchanged. For a matrix of m rows and n
; columns the result has n rows and m columns: column j of B, top to bottom, is row j of the result.

tr_cell: .word 0                ; the matrix's cell
tr_m:    .word 0                ; rows and columns of the matrix
tr_n:    .word 0
tr_w:    .byte 0                ; element width
tr_step: .word 0                ; bytes from one row of the matrix to the next
tr_row:  .word 0                ; the first element of the column being copied
tr_j:    .word 0                ; columns to do
tr_i:    .word 0                ; rows to do in this column

p_transpose:
        jsr topcell
        jsr getval
        lda vrk
        cmp #2
        beq tr_go
        clc
        rts
tr_go:  jsr tr_make
        bcc tr_ok
        rts
tr_ok:  jmp setmon

p_transax:
        jsr topcell             ; the left argument: whole numbers
        jsr arg_ints
        bcc tx_1
        rts
tx_1:   jsr secondcell          ; one per axis of the right one
        jsr getval
        lda qan+1
        bne tx_len
        lda qan
        cmp vrk
        beq tx_2
tx_len: lda #E_LENGTH
        sec
        rts
tx_2:   lda vrk                 ; the permutation of 1..rank
        beq tx_id
        cmp #2
        beq tx_m
        lda qneg0               ; a vector: (1)
        ora qhuge0
        ora qd0+1
        bne tx_dom
        lda qd0
        cmp #1
        bne tx_dom
        beq tx_id
tx_m:   lda qneg0               ; a matrix: (1 2) or (2 1)
        ora qhuge0
        ora qneg1
        ora qhuge1
        ora qd0+1
        ora qd1+1
        bne tx_dom
        lda qd0
        cmp #1
        bne tx_21
        lda qd1
        cmp #2
        beq tx_id
tx_dom: lda #E_DOMAIN
        sec
        rts
tx_21:  cmp #2
        bne tx_dom
        lda qd1
        cmp #1
        bne tx_dom
        jsr secondcell          ; (2 1): the matrix goes where the pair was
        jsr getval
        jsr tr_make
        bcc tx_3
        rts
tx_3:   jmp setdy
tx_id:  sec                     ; the identity: just the right argument
        lda vsp
        sbc #4
        sta vsp
        lda vsp+1
        sbc #0
        sta vsp+1
        clc
        rts

; the matrix in the cell at cptr (getval has just been called on it) transposed: the new array's cell in cv
tr_make:
        lda cptr
        sta tr_cell
        lda cptr+1
        sta tr_cell+1
        lda vs0
        sta tr_m
        sta nd1
        lda vs0+1
        sta tr_m+1
        sta nd1+1
        lda vs1
        sta tr_n
        sta nd0
        lda vs1+1
        sta tr_n+1
        sta nd0+1
        lda vn
        sta nn
        lda vn+1
        sta nn+1
        lda vt
        sta nt
        lda #2
        sta nrk
        jsr newarr
        bcc tm_1
        rts
tm_1:   lda vn                  ; (nothing to copy: an empty matrix)
        ora vn+1
        bne tm_2
        clc
        rts
tm_2:   lda tr_cell             ; the source again (the allocation may have moved it)
        sta cptr
        lda tr_cell+1
        sta cptr+1
        jsr getval
        ldx vt
        lda WIDTHT,x
        sta tr_w
        lda tr_n                ; the step: n elements
        sta tr_step
        lda tr_n+1
        sta tr_step+1
        lda tr_w
        cmp #2
        bcc tm_3
        clc
        lda tr_step
        adc tr_n
        sta tr_step
        lda tr_step+1
        adc tr_n+1
        sta tr_step+1
        lda tr_w
        cmp #3
        bcc tm_3
        clc
        lda tr_step
        adc tr_n
        sta tr_step
        lda tr_step+1
        adc tr_n+1
        sta tr_step+1
tm_3:   lda vp
        sta tr_row
        lda vp+1
        sta tr_row+1
        lda tr_n
        sta tr_j
        lda tr_n+1
        sta tr_j+1
tm_j:   lda tr_row
        sta cs
        lda tr_row+1
        sta cs+1
        lda tr_m
        sta tr_i
        lda tr_m+1
        sta tr_i+1
tm_i:   ldy #0
tm_c:   lda (cs),y
        sta (dp),y
        iny
        cpy tr_w
        bne tm_c
        clc
        lda dp
        adc tr_w
        sta dp
        bcc tm_4
        inc dp+1
tm_4:   clc
        lda cs
        adc tr_step
        sta cs
        lda cs+1
        adc tr_step+1
        sta cs+1
        lda tr_i
        bne tm_5
        dec tr_i+1
tm_5:   dec tr_i
        lda tr_i
        ora tr_i+1
        bne tm_i
        clc                     ; the next column
        lda tr_row
        adc tr_w
        sta tr_row
        bcc tm_6
        inc tr_row+1
tm_6:   lda tr_j
        bne tm_7
        dec tr_j+1
tm_7:   dec tr_j
        lda tr_j
        ora tr_j+1
        bne tm_j
        clc
        rts

; --- an axis: [k] after a function -------------------------------------------------------------------------------
; The top cell is the axis, the one below it the array it is for. Checks (the model's Interp._axis): a scalar
; (RANK), a whole number (DOMAIN), from 1 to the array's rank (INDEX). The axis is taken off the stack. The
; functions that take an axis work along the last axis, so for axis 1 of a matrix the matrix is transposed
; (its cell now holds the transpose). X = the flags for the function to come: AX_GIVEN, plus AX_FLIP if it was.
ax_k:    .byte 0
ax_cat:  .byte 0

p_axis:
        sta ax_cat              ; A = 1: for catenation (the rank is checked when both arguments are known)
        jsr topcell
        jsr getval
        lda vrk
        beq ax_1
        lda #E_RANK
        sec
        rts
ax_1:   lda vt
        cmp #1
        beq ax_dom
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        jsr elem_to_int
        bcs ax_dom
        lda ineg
        ora ihuge
        ora im+1
        bne ax_idx
        lda im
        beq ax_idx              ; 0
        cmp #3
        bcs ax_idx              ; only axes 1 and 2 exist
        sta ax_k
        jsr secondcell
        jsr getval
        lda ax_cat
        bne ax_r
        lda vrk
        cmp ax_k
        bcc ax_idx              ; the rank is below k
ax_r:
        sec                     ; take the axis off
        lda vsp
        sbc #4
        sta vsp
        lda vsp+1
        sbc #0
        sta vsp+1
        lda ax_k
        cmp #1
        bne ax_no
        lda vrk
        cmp #2
        bne ax_f
        jsr topcell             ; axis 1 of a matrix: transpose
        jsr getval
        jsr tr_make
        bcc ax_2
        rts
ax_2:   jsr setmon
ax_f:   ldx #AX_GIVEN+AX_FLIP
        clc
        rts
ax_no:  ldx #AX_GIVEN+AX_K2
        clc
        rts
ax_idx: lda #E_INDEX
        sec
        rts
ax_dom: lda #E_DOMAIN
        sec
        rts
