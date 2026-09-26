; Reverse, rotate, take and drop: ⌽ A⌽B A↑B A↓B. Spec: apl64.py reverse, rotate, take, drop.
; Included by eval.asm. Uses elemaddr (index.inc): cs = xbase + (xrow + im) * xw.

zd0     = WS+$b9                ; (2) source dimensions (a vector is 1 by n)
zd1     = WS+$bb
zo0     = WS+$bd                ; (2) result dimensions
zo1     = WS+$bf
zs0     = WS+$cb                ; (2) where the result's first element comes from (may be negative)
zs1     = WS+$cd
tdm     = WS+$c1                ; 0 take, 1 drop
zr      = WS+$c5                ; (2) the row and column being made (the collector's scratch, idle by then)
zc      = WS+$c7
zrv     = WS+$c2                ; 1 reverse, 0 rotate
zvr     = WS+$c9                ; the row exists in the source
tn      = WS+$d4                ; (2) an axis: the amount (magnitude), its sign, huge?, the dimension
tng     = WS+$d6
thg     = WS+$d7
td      = WS+$d8                ; (2)
tno     = WS+$da                ; (2) the axis's result length and start
tns     = WS+$dc                ; (2)
zi      = WS+$de                ; (2) rows / columns still to do
zj      = WS+$e0                ; (2)
zk      = WS+$d4                ; reverse and rotate reuse the axis variables: the rotation
zm      = WS+$d6                ; (2) the element of the row being copied
zn      = WS+$d8                ; (2) the row length
zrows   = WS+$da                ; (2)

; --- take and drop ------------------------------------------------------------------------------
p_take: lda #0
        beq tk_1
p_drop: lda #1
tk_1:   sta tdm
        jsr topcell
        jsr arg_ints            ; RANK, DOMAIN
        bcc tk_2
        rts
tk_2:   jsr secondcell
        jsr getval
        lda #1                  ; the source's shape as rows by columns
        ldx vrk
        cpx #2
        beq tk_m
        sta zd0
        lda #0
        sta zd0+1
        lda #1
        sta zd1
        lda #0
        sta zd1+1
        cpx #1
        bne tk_3
        lda vs0
        sta zd1
        lda vs0+1
        sta zd1+1
        jmp tk_3
tk_m:   lda vs0
        sta zd0
        lda vs0+1
        sta zd0+1
        lda vs1
        sta zd1
        lda vs1+1
        sta zd1+1
tk_3:   lda qan+1               ; one number for each axis (a scalar is a vector of 1)
        bne tk_len
        lda qan
        ldx vrk
        cpx #2
        beq tk_4
        cmp #1
        beq tk_5
tk_len: lda #E_LENGTH
        sec
        rts
tk_4:   cmp #2
        bne tk_len
        ldy #1                  ; columns, then rows: the axis (X = 2 * axis) and its amount (Y)
        ldx #2
        jsr tk_ax
        bcs tk_x
        ldy #0
        ldx #0
        jsr tk_ax
        bcs tk_x
        lda zo0                 ; count = rows * columns
        sta p0
        lda zo0+1
        sta p1
        lda zo1
        sta bl
        lda zo1+1
        sta bh
        jsr mul16
        lda p2
        ora p3
        beq tk_6
        lda #E_WSFULL
        sec
tk_x:   rts
tk_5:   ldy #0                  ; one axis: the number is the columns'
        ldx #2
        jsr tk_ax
        bcs tk_x
        lda zo1
        sta p0
        lda zo1+1
        sta p1
        lda #1
        sta zo0
        lda #0
        sta zo0+1
        sta zs0
        sta zs0+1
tk_6:   lda p0                  ; the result: p1:p0 elements
        sta nn
        lda p1
        sta nn+1
        lda vt
        sta nt
        lda vrk
        cmp #2
        beq tk_7
        lda #1
        sta nrk
        lda zo1
        sta nd0
        lda zo1+1
        sta nd0+1
        jmp tk_8
tk_7:   lda #2
        sta nrk
        lda zo0
        sta nd0
        lda zo0+1
        sta nd0+1
        lda zo1
        sta nd1
        lda zo1+1
        sta nd1+1
tk_8:   lda #0                  ; the fill element: 0, or a blank for characters
        ldx vt
        cpx #1
        bne tk_9
        lda #32
tk_9:   sta fillbuf
        jsr newarr
        bcc tk_a
        rts
tk_a:   jsr secondcell          ; (the arrays may have moved)
        jsr getval
        lda vp
        sta xbase
        lda vp+1
        sta xbase+1
        ldx vt
        lda WIDTHT,x
        sta xw
        lda zs0
        sta zr
        lda zs0+1
        sta zr+1
        lda zo0
        sta zi
        lda zo0+1
        sta zi+1
tk_row: lda zi
        ora zi+1
        bne tk_r1
        jmp setdy
tk_r1:  lda zr                  ; is this row in the source?
        sta tn
        lda zr+1
        sta tn+1
        lda zd0
        sta td
        lda zd0+1
        sta td+1
        jsr inrange
        lda #0
        rol
        sta zvr
        beq tk_r2
        lda zr                  ; the element number where it starts
        sta p0
        lda zr+1
        sta p1
        lda zd1
        sta bl
        lda zd1+1
        sta bh
        jsr mul16
        lda p0
        sta xrow
        lda p1
        sta xrow+1
tk_r2:  lda zs1
        sta zc
        lda zs1+1
        sta zc+1
        lda zo1
        sta zj
        lda zo1+1
        sta zj+1
tk_col: lda zj
        ora zj+1
        beq tk_re
        lda zvr
        beq tk_f
        lda zc
        sta tn
        lda zc+1
        sta tn+1
        lda zd1
        sta td
        lda zd1+1
        sta td+1
        jsr inrange
        bcc tk_f
        lda zc
        sta im
        lda zc+1
        sta im+1
        jsr elemaddr
        jmp tk_c
tk_f:   lda #<fillbuf
        sta cs
        lda #>fillbuf
        sta cs+1
tk_c:   jsr zcopy
        inc zc
        bne tk_c1
        inc zc+1
tk_c1:  lda zj
        bne tk_c2
        dec zj+1
tk_c2:  dec zj
        jmp tk_col
tk_re:  inc zr
        bne tk_e1
        inc zr+1
tk_e1:  lda zi
        bne tk_e2
        dec zi+1
tk_e2:  dec zi
        jmp tk_row

; axis X/2 (dimension zd, result zo, start zs) with the amount number Y of the left argument
tk_ax:  stx zvr
        lda zd0,x
        sta td
        lda zd0+1,x
        sta td+1
        lda qneg0,y
        sta tng
        lda qhuge0,y
        sta thg
        cpy #0
        bne tk_a1
        lda qd0
        sta tn
        lda qd0+1
        sta tn+1
        jmp tk_a2
tk_a1:  lda qd1
        sta tn
        lda qd1+1
        sta tn+1
tk_a2:  jsr axis_ts
        bcs tk_ar
        ldx zvr
        lda tno
        sta zo0,x
        lda tno+1
        sta zo0+1,x
        lda tns
        sta zs0,x
        lda tns+1
        sta zs0+1,x
tk_ar:  rts

; the result length tno and start tns along one axis of length td, for the amount tn (sign tng,
; huge thg); carry set: WS FULL (a take of more than 65535)
axis_ts:
        lda tdm
        bne at_dr
        lda thg
        beq at_t1
        lda #E_WSFULL
        sec
        rts
at_t1:  lda tn
        sta tno
        lda tn+1
        sta tno+1
        lda #0
        sta tns
        sta tns+1
        lda tng
        beq at_ok
        sec                     ; from the end: d - |n| (it may be below 0)
        lda td
        sbc tn
        sta tns
        lda td+1
        sbc tn+1
        sta tns+1
at_ok:  clc
        rts
at_dr:  lda #0
        sta tno
        sta tno+1
        sta tns
        sta tns+1
        lda thg
        bne at_ok
        sec
        lda td
        sbc tn
        sta tno
        lda td+1
        sbc tn+1
        sta tno+1
        bcs at_d1
        lda #0
        sta tno
        sta tno+1
at_d1:  lda tng
        bne at_ok
        lda tn
        sta tns
        lda tn+1
        sta tns+1
        clc
        rts

; carry set if 0 <= tn < td
inrange:
        lda tn+1
        bmi ir_no
        cmp td+1
        bcc ir_yes
        bne ir_no
        lda tn
        cmp td
        bcc ir_yes
ir_no:  clc
        rts
ir_yes: sec
        rts

; copy xw bytes from cs to dp
zcopy:  ldy #0
zc_1:   lda (cs),y
        sta (dp),y
        iny
        cpy xw
        bne zc_1
        clc
        lda dp
        adc xw
        sta dp
        bcc zc_2
        inc dp+1
zc_2:   rts

; --- reverse and rotate --------------------------------------------------------------------------------
p_rev:  lda #1
        sta zrv
        jsr topcell
        jsr getval
        lda vrk
        bne rv_1
        clc                     ; a scalar
        rts
rv_1:   lda #0
        sta zk
        sta zk+1
        jmp rv_go

p_rot:  lda #0
        sta zrv
        jsr topcell
        jsr arg_ints            ; RANK, DOMAIN
        bcc rt_1
        rts
rt_1:   lda qan+1               ; one whole number
        bne rt_nonce
        lda qan
        cmp #1
        beq rt_2
rt_nonce:
        lda #E_NONCE
        sec
        rts
rt_dom: lda #E_DOMAIN
        sec
        rts
rt_2:   lda qhuge0              ; it must fit int16
        bne rt_dom
        lda qd0+1
        bpl rt_3
        cmp #$80
        bne rt_dom
        lda qd0
        bne rt_dom
        lda qneg0
        beq rt_dom
rt_3:   lda qd0
        sta zk
        lda qd0+1
        sta zk+1
        lda qneg0
        beq rt_4
        sec
        lda #0
        sbc zk
        sta zk
        lda #0
        sbc zk+1
        sta zk+1
rt_4:   jsr secondcell
        jsr getval
        lda vrk
        beq rt_same             ; a scalar, or nothing: unchanged
        lda vn
        ora vn+1
        bne rv_go
rt_same:
        ldy #3
rt_5:   lda (cptr),y
        sta cv,y
        dey
        bpl rt_5
        jmp setdy

; the array in the cell (the top one for ⌽B, the second for A⌽B) with each row reversed or rotated by zk
rv_go:  jsr rv_cell
        lda vt
        sta nt
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
        bcc rv_2
        rts
rv_2:   jsr rv_cell
        lda vp
        sta xbase
        lda vp+1
        sta xbase+1
        ldx vt
        lda WIDTHT,x
        sta xw
        lda vrk                 ; row length and number of rows
        cmp #2
        beq rv_m
        lda vs0
        sta zn
        lda vs0+1
        sta zn+1
        lda #1
        sta zrows
        lda #0
        sta zrows+1
        beq rv_3
rv_m:   lda vs1
        sta zn
        lda vs1+1
        sta zn+1
        lda vs0
        sta zrows
        lda vs0+1
        sta zrows+1
rv_3:   lda vn
        ora vn+1
        bne rv_4
        jmp rv_done             ; (an empty array: nothing to move)
rv_4:   lda zrv
        bne rv_5
        lda zn                  ; k mod n, from the residue routine: ia | ib = ib mod ia
        sta ia
        lda zn+1
        sta ia+1
        lda zk
        sta ib
        lda zk+1
        sta ib+1
        jsr k_ires
        lda ia
        sta zk
        lda ia+1
        sta zk+1
rv_5:   lda #0
        sta xrow
        sta xrow+1
rv_row: lda zrows
        ora zrows+1
        bne *+5
        jmp rv_done
        lda zn
        sta zj
        lda zn+1
        sta zj+1
        lda zrv
        beq rv_r1
        sec                     ; reverse: start at n-1
        lda zn
        sbc #1
        sta zm
        lda zn+1
        sbc #0
        sta zm+1
        jmp rv_col
rv_r1:  lda zk
        sta zm
        lda zk+1
        sta zm+1
rv_col: lda zm
        sta im
        lda zm+1
        sta im+1
        jsr elemaddr
        jsr zcopy
        lda zrv
        bne rv_dec
        inc zm                  ; rotate: on, and back to 0 at the end of the row
        bne rv_i1
        inc zm+1
rv_i1:  lda zm
        cmp zn
        bne rv_nx
        lda zm+1
        cmp zn+1
        bne rv_nx
        lda #0
        sta zm
        sta zm+1
        beq rv_nx
rv_dec: lda zm
        bne rv_d1
        dec zm+1
rv_d1:  dec zm
rv_nx:  lda zj
        bne rv_n1
        dec zj+1
rv_n1:  dec zj
        lda zj
        ora zj+1
        bne rv_col
        clc                     ; the next row
        lda xrow
        adc zn
        sta xrow
        lda xrow+1
        adc zn+1
        sta xrow+1
        lda zrows
        bne rv_r2
        dec zrows+1
rv_r2:  dec zrows
        jmp rv_row
rv_done: lda zrv
        beq rv_d2
        jmp setmon
rv_d2:  jmp setdy

rv_cell:
        lda zrv
        beq rv_c1
        jsr topcell
        jmp getval
rv_c1:  jsr secondcell
        jmp getval
