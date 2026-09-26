; Index-of, membership and grade: A⍳B A∊B ⍋V ⍒V. Spec: apl64.py index_of, member, grade.
; Included by eval.asm (after scalar.inc, whose keycmp orders floats exactly).

zto     = WS+$b9                ; type of the outer array (the elements the result has one entry for)
zon     = WS+$ba                ; (2) its count
zwo     = WS+$bc                ; its element width
zti     = WS+$bd                ; the inner array (the elements looked in)
zin     = WS+$be                ; (2)
zwi     = WS+$c0
zmd     = WS+$c1                ; 0 index-of, 1 membership
zrk     = WS+$c2                ; the result's rank and dimensions: the outer array's
qxd0     = WS+$c9                ; (2)
qxd1     = WS+$cb                ; (2)
zib     = WS+$cd                ; (2) the inner array's data
zoc     = WS+$d4                ; (2) outer elements to go
qxk      = WS+$d6                ; (2) the inner position, or i in the grade
zv      = WS+$d8                ; (2)
gxa     = WS+$da                ; (2)
gi      = WS+$dc                ; (2)
qxj      = WS+$de                ; (2)
zrp     = WS+$e0                ; (2)
zsb     = WS+$e2                ; (2) the graded array's data (elemaddr's variables are not used here)
zrb     = WS+$e4                ; (2) the result's data
zgd     = WS+$e6                ; 0 up, 1 down  (nd1 is only read by newarr, which is done)

; the shape of the cell just read by getval, as the result's
sr_shape:
        lda vrk
        sta zrk
        lda vs0
        sta qxd0
        lda vs0+1
        sta qxd0+1
        lda vs1
        sta qxd1
        lda vs1+1
        sta qxd1+1
        rts

p_indexof:
        jsr topcell             ; the left argument: a vector
        jsr getval
        lda vrk
        cmp #1
        beq io_1
        lda #E_RANK
        sec
        rts
io_1:   lda vt
        sta zti
        lda vn
        sta zin
        lda vn+1
        sta zin+1
        jsr secondcell          ; the result has an entry for each element of the right
        jsr getval
        lda vt
        sta zto
        lda vn
        sta zon
        lda vn+1
        sta zon+1
        jsr sr_shape
        lda #0
        sta zmd
        jmp srch

p_member:
        jsr topcell
        jsr getval
        lda vt
        sta zto
        lda vn
        sta zon
        lda vn+1
        sta zon+1
        jsr sr_shape
        jsr secondcell
        jsr getval
        lda vt
        sta zti
        lda vn
        sta zin
        lda vn+1
        sta zin+1
        lda #1
        sta zmd

; for each outer element, look for it in the inner array
srch:   ldx zto
        lda WIDTHT,x
        sta zwo
        ldx zti
        lda WIDTHT,x
        sta zwi
        lda #2                  ; INT for index-of, BOOL for membership
        ldx zmd
        beq sr_1
        lda #0
sr_1:   sta nt
        lda zrk
        bne sr_arr
        lda nt                  ; a scalar result
        sta cv
        lda #0
        sta cv+1
        sta cv+2
        sta cv+3
        lda #<(cv+1)
        sta dp
        lda #>(cv+1)
        sta dp+1
        jmp sr_go
sr_arr: sta nrk
        lda zon
        sta nn
        lda zon+1
        sta nn+1
        lda qxd0
        sta nd0
        lda qxd0+1
        sta nd0+1
        lda qxd1
        sta nd1
        lda qxd1+1
        sta nd1+1
        jsr newarr
        bcc sr_go
        rts
sr_go:  lda zmd                 ; (the arrays may have moved)
        bne sr_m
        jsr secondcell
        jsr getval
        lda vp
        sta qsrc
        lda vp+1
        sta qsrc+1
        jsr topcell
        jsr getval
        jmp sr_b
sr_m:   jsr topcell
        jsr getval
        lda vp
        sta qsrc
        lda vp+1
        sta qsrc+1
        jsr secondcell
        jsr getval
sr_b:   lda vp
        sta zib
        lda vp+1
        sta zib+1
        lda zon
        sta zoc
        lda zon+1
        sta zoc+1
sr_o:   lda zoc
        ora zoc+1
        bne sr_o1
        jmp setdy
sr_o1:  lda zib
        sta mp
        lda zib+1
        sta mp+1
        lda #0
        sta qxk
        sta qxk+1
sr_i:   lda qxk
        cmp zin
        bne sr_c
        lda qxk+1
        cmp zin+1
        beq sr_nf
sr_c:   jsr elem_eq
        bcs sr_f
        clc
        lda mp
        adc zwi
        sta mp
        bcc sr_i1
        inc mp+1
sr_i1:  inc qxk
        bne sr_i
        inc qxk+1
        jmp sr_i
sr_f:   lda zmd                 ; found at qxk
        bne sr_f1
        clc
        lda qxk
        adc #1
        sta zv
        lda qxk+1
        adc #0
        sta zv+1
        jmp sr_w2
sr_f1:  lda #1
        bne sr_w1
sr_nf:  lda zmd
        bne sr_n1
        clc
        lda zin
        adc #1
        sta zv
        lda zin+1
        adc #0
        sta zv+1
        jmp sr_w2
sr_n1:  lda #0
sr_w1:  ldy #0                  ; one byte
        sta (dp),y
        inc dp
        bne sr_a
        inc dp+1
        jmp sr_a
sr_w2:  ldy #0                  ; two bytes
        lda zv
        sta (dp),y
        iny
        lda zv+1
        sta (dp),y
        clc
        lda dp
        adc #2
        sta dp
        bcc sr_a
        inc dp+1
sr_a:   clc                     ; the next outer element
        lda qsrc
        adc zwo
        sta qsrc
        bcc sr_b1
        inc qsrc+1
sr_b1:  lda zoc
        bne sr_b2
        dec zoc+1
sr_b2:  dec zoc
        jmp sr_o

; carry set if the element at qsrc (type zto) equals the one at mp (type zti): exactly, across BOOL, INT
; and FLOAT; a character equals only a character
elem_eq:
        lda zto
        cmp #1
        beq ee_c
        lda zti
        cmp #1
        beq ee_no
        lda zto
        cmp #3
        beq ee_f
        lda zti
        cmp #3
        beq ee_f
        lda qsrc                ; both BOOL or INT
        sta ep
        lda qsrc+1
        sta ep+1
        ldx zto
        jsr ee_ld
        lda ia
        sta ib
        lda ia+1
        sta ib+1
        lda mp
        sta ep
        lda mp+1
        sta ep+1
        ldx zti
        jsr ee_ld
        lda ia
        cmp ib
        bne ee_no
        lda ia+1
        cmp ib+1
        bne ee_no
ee_yes: sec
        rts
ee_no:  clc
        rts
ee_c:   lda zti
        cmp #1
        bne ee_no
        ldy #0
        lda (qsrc),y
        cmp (mp),y
        beq ee_yes
        clc
        rts
ee_f:   lda qsrc                ; compare as float24: the first one goes to ca
        sta ep
        lda qsrc+1
        sta ep+1
        ldx zto
        jsr ee_fl
        ldx #2
ee_1:   lda fa,x
        sta ca,x
        dex
        bpl ee_1
        lda mp
        sta ep
        lda mp+1
        sta ep+1
        ldx zti
        jsr ee_fl
        ldx #2
ee_2:   lda fa,x
        cmp ca,x
        bne ee_no
        dex
        bpl ee_2
        sec
        rts
; ia = the BOOL or INT (type X) at ep
ee_ld:  ldy #0
        lda (ep),y
        sta ia
        sty ia+1
        cpx #2
        bne ee_l1
        iny
        lda (ep),y
        sta ia+1
ee_l1:  rts
; fa = the number (type X) at ep as a float24
ee_fl:  cpx #3
        beq ee_f3
        jsr ee_ld
        jmp i_to_f
ee_f3:  ldy #0
        lda (ep),y
        sta fa
        iny
        lda (ep),y
        sta fa+1
        iny
        lda (ep),y
        sta fa+2
        rts

; --- grade ---------------------------------------------------------------------------------------------
; the result starts as 1 2 3 ... n and is insertion sorted, comparing the elements it points to;
; an element moves past a neighbour only if strictly out of order, so equal ones keep their order
p_gradeup:
        lda #0
        beq gr_go
p_gradedown:
        lda #1
gr_go:  sta zgd
        jsr topcell
        jsr getval
        lda vrk
        cmp #1
        beq gr_1
        lda #E_RANK
        sec
        rts
gr_1:   lda vt
        sta zto
        lda vn
        sta zon
        lda vn+1
        sta zon+1
        lda #2
        sta nt
        lda #1
        sta nrk
        lda vn
        sta nn
        sta nd0
        lda vn+1
        sta nn+1
        sta nd0+1
        jsr newarr
        bcc gr_2
        rts
gr_2:   lda dp                  ; the result's data
        sta zrb
        lda dp+1
        sta zrb+1
        jsr topcell             ; (the source may have moved)
        jsr getval
        lda vp
        sta zsb
        lda vp+1
        sta zsb+1
        ldx zto
        lda WIDTHT,x
        sta zwo
        lda zon                 ; 1 2 3 ... n
        ora zon+1
        bne gr_3
        jmp setmon
gr_3:   lda #1
        sta zv
        lda #0
        sta zv+1
        lda zrb
        sta mp
        lda zrb+1
        sta mp+1
        lda zon
        sta zoc
        lda zon+1
        sta zoc+1
gr_f:   ldy #0
        lda zv
        sta (mp),y
        iny
        lda zv+1
        sta (mp),y
        clc
        lda mp
        adc #2
        sta mp
        bcc gr_f1
        inc mp+1
gr_f1:  inc zv
        bne gr_f2
        inc zv+1
gr_f2:  lda zoc
        bne gr_f3
        dec zoc+1
gr_f3:  dec zoc
        lda zoc
        ora zoc+1
        bne gr_f
        lda #1                  ; i = 1: R[i] is where the next element comes from
        sta qxk
        lda #0
        sta qxk+1
        clc
        lda zrb
        adc #2
        sta zrp
        lda zrb+1
        adc #0
        sta zrp+1
gr_i:   lda qxk
        cmp zon
        bne gr_i1
        lda qxk+1
        cmp zon+1
        bne gr_i1
        jmp setmon
gr_i1:  lda zrp
        sta mp
        lda zrp+1
        sta mp+1
        ldy #0
        lda (mp),y
        sta zv
        iny
        lda (mp),y
        sta zv+1
        lda qxk
        sta qxj
        lda qxk+1
        sta qxj+1
gr_j:   lda qxj
        ora qxj+1
        beq gr_p
        sec                     ; the neighbour below
        lda mp
        sbc #2
        sta qsrc
        lda mp+1
        sbc #0
        sta qsrc+1
        ldy #0
        lda (qsrc),y
        sta gxa
        iny
        lda (qsrc),y
        sta gxa+1
        jsr gcmp                ; the neighbour's element against ours: 1 above, $ff below, 0 equal
        ldx zgd
        bne gr_dn
        cmp #1
        bne gr_p
        beq gr_s
gr_dn:  cmp #$ff
        bne gr_p
gr_s:   ldy #0                  ; out of order: the neighbour moves up
        lda gxa
        sta (mp),y
        iny
        lda gxa+1
        sta (mp),y
        lda qsrc
        sta mp
        lda qsrc+1
        sta mp+1
        lda qxj
        bne gr_s1
        dec qxj+1
gr_s1:  dec qxj
        jmp gr_j
gr_p:   ldy #0                  ; ours goes here
        lda zv
        sta (mp),y
        iny
        lda zv+1
        sta (mp),y
        inc qxk
        bne gr_n1
        inc qxk+1
gr_n1:  clc
        lda zrp
        adc #2
        sta zrp
        bcc gr_n2
        inc zrp+1
gr_n2:  jmp gr_i

; A = order of the element numbered gxa against the one numbered zv (1 above, $ff below, 0 equal)
gcmp:   lda gxa
        sta gi
        lda gxa+1
        sta gi+1
        jsr gaddr
        lda cs
        sta ep
        lda cs+1
        sta ep+1
        lda zv
        sta gi
        lda zv+1
        sta gi+1
        jsr gaddr
        lda cs
        sta tp
        lda cs+1
        sta tp+1
        lda zto
        cmp #3
        beq gc_f
        cmp #2
        beq gc_i
        ldy #0                  ; BOOL and CHAR: bytes
        lda (ep),y
        cmp (tp),y
        beq gc_eq
        bcs gc_gt
gc_lt:  lda #$ff
        rts
gc_gt:  lda #1
        rts
gc_eq:  lda #0
        rts
gc_i:   ldy #0                  ; INT: signed
        lda (ep),y
        cmp (tp),y
        bne gc_i1
        iny
        lda (ep),y
        cmp (tp),y
        beq gc_eq
gc_i1:  ldy #0
        sec
        lda (ep),y
        sbc (tp),y
        iny
        lda (ep),y
        sbc (tp),y
        bvc gc_i2
        eor #$80
gc_i2:  bmi gc_lt
        bpl gc_gt
gc_f:   ldy #2                  ; FLOAT: the exact order
gc_f1:  lda (ep),y
        sta ca,y
        lda (tp),y
        sta cb,y
        dey
        bpl gc_f1
        jmp keycmp

; cs = zsb + (gi - 1) * zwo
gaddr:  sec
        lda gi
        sbc #1
        sta cs
        lda gi+1
        sbc #0
        sta cs+1
        lda zwo
        cmp #1
        bne *+5
        jmp gx_a
        lda cs
        pha
        lda cs+1
        pha
        asl cs
        rol cs+1
        lda zwo
        cmp #3
        bne gx_2
        pla                     ; x3: x2 + x
        sta gi+1
        pla
        sta gi
        clc
        lda cs
        adc gi
        sta cs
        lda cs+1
        adc gi+1
        sta cs+1
        jmp gx_a
gx_2:   pla
        pla
gx_a:   clc
        lda cs
        adc zsb
        sta cs
        lda cs+1
        adc zsb+1
        sta cs+1
        rts
