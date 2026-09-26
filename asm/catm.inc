; Catenate with a matrix (an overlay, see overlay.inc): entered from p_catenate (prims.inc) through s_catm.

; --- catenate with a matrix: a,b -----------------------------------------------------------------------------------
; Spec: apl64.py _catenate_rows. Entered from p_catenate (prims.inc) through s_catm when either argument is a
; matrix. The left operand is the top cell. The columns of b follow those of a in every row; a vector (one
; element per row) or a scalar (repeated) counts as a single column. Checks: the row counts (LENGTH, a first),
; the types (DOMAIN), the size (WS FULL).

cm_ar:   .byte 0                ; ranks and types
cm_br:   .byte 0
cm_at:   .byte 0
cm_bt:   .byte 0
cm_an:   .word 0                ; element counts
cm_bn:   .word 0
cm_ka:   .word 0                ; columns
cm_kb:   .word 0
cm_kt:   .word 0
cm_m:    .word 0                ; rows
cm_br0:  .word 0                ; b's rows or length
cm_t:    .byte 0                ; the result's type
cm_pa:   .word 0                ; the start of the row of a and of b now being copied
cm_pb:   .word 0
cm_sa:   .word 0                ; bytes from one row to the next
cm_sb:   .word 0
cm_rc:   .word 0                ; rows to do

p_catm:
        jsr topcell
        jsr getval
        lda vrk
        sta cm_ar
        lda vt
        sta cm_at
        lda vn
        sta cm_an
        lda vn+1
        sta cm_an+1
        lda #1
        sta cm_ka
        lda #0
        sta cm_ka+1
        lda vrk
        cmp #2
        bne cm_1
        lda vs1
        sta cm_ka
        lda vs1+1
        sta cm_ka+1
        lda vs0
        sta cm_m
        lda vs0+1
        sta cm_m+1
cm_1:   jsr secondcell
        jsr getval
        lda vrk
        sta cm_br
        lda vt
        sta cm_bt
        lda vn
        sta cm_bn
        lda vn+1
        sta cm_bn+1
        lda vs0                 ; a matrix has its rows here, a vector its length
        sta cm_br0
        lda vs0+1
        sta cm_br0+1
        lda #1
        sta cm_kb
        lda #0
        sta cm_kb+1
        lda vrk
        cmp #2
        bne cm_2
        lda vs1
        sta cm_kb
        lda vs1+1
        sta cm_kb+1
        lda cm_ar               ; the rows: those of the matrix among the two (a's if both)
        cmp #2
        beq cm_2
        lda cm_br0
        sta cm_m
        lda cm_br0+1
        sta cm_m+1
cm_2:   lda cm_ar               ; a vector left argument needs a length equal to the rows
        cmp #1
        bne cm_3
        lda cm_an
        cmp cm_m
        bne cm_len
        lda cm_an+1
        cmp cm_m+1
        bne cm_len
cm_3:   lda cm_br               ; then b: a matrix needs the same rows, a vector the same length
        beq cm_4
        cmp #2
        beq cm_5
        lda cm_bn
        cmp cm_m
        bne cm_len
        lda cm_bn+1
        cmp cm_m+1
        bne cm_len
        beq cm_4
cm_5:   lda cm_br0
        cmp cm_m
        bne cm_len
        lda cm_br0+1
        cmp cm_m+1
        beq cm_4
cm_len: lda #E_LENGTH
        sec
        rts
cm_4:   lda cm_an               ; the type: an empty argument gives way to the other
        ora cm_an+1
        bne cm_t1
        lda cm_bt
        sta cm_t
        jmp cm_tz
cm_t1:  lda cm_bn
        ora cm_bn+1
        bne cm_t2
        lda cm_at
        sta cm_t
        jmp cm_tz
cm_t2:  lda cm_at
        cmp cm_bt
        beq cm_ts
        cmp #1                  ; a character does not mix with numbers
        beq cm_dom
        lda cm_bt
        cmp #1
        beq cm_dom
        lda cm_at
        cmp cm_bt
        bcs cm_ts
        lda cm_bt
cm_ts:  sta cm_t
        jmp cm_tz
cm_dom: lda #E_DOMAIN
        sec
        rts
cm_tz:  clc                     ; the size
        lda cm_ka
        adc cm_kb
        sta cm_kt
        lda cm_ka+1
        adc cm_kb+1
        sta cm_kt+1
        bcs cm_ws
        lda cm_m
        sta p0
        lda cm_m+1
        sta p1
        lda cm_kt
        sta bl
        lda cm_kt+1
        sta bh
        jsr mul16
        lda p2
        ora p3
        bne cm_ws
        lda p0
        sta nn
        lda p1
        sta nn+1
        lda cm_t
        sta nt
        lda #2
        sta nrk
        lda cm_m
        sta nd0
        lda cm_m+1
        sta nd0+1
        lda cm_kt
        sta nd1
        lda cm_kt+1
        sta nd1+1
        jsr newarr
        bcc cm_go
        rts
cm_ws:  lda #E_WSFULL
        sec
        rts
cm_go:  lda cm_m                ; (the collector may have moved the arguments) rows to do
        sta cm_rc
        lda cm_m+1
        sta cm_rc+1
        jsr topcell
        jsr getval
        lda vp
        sta cm_pa
        lda vp+1
        sta cm_pa+1
        ldx cm_at
        lda WIDTHT,x
        tax
        lda cm_ka
        sta cm_sk
        lda cm_ka+1
        sta cm_sk+1
        lda cm_ar
        jsr cm_stride
        lda ia
        sta cm_sa
        lda ia+1
        sta cm_sa+1
        jsr secondcell
        jsr getval
        lda vp
        sta cm_pb
        lda vp+1
        sta cm_pb+1
        ldx cm_bt
        lda WIDTHT,x
        tax
        lda cm_kb
        sta cm_sk
        lda cm_kb+1
        sta cm_sk+1
        lda cm_br
        jsr cm_stride
        lda ia
        sta cm_sb
        lda ia+1
        sta cm_sb+1
cm_row: lda cm_rc
        ora cm_rc+1
        bne cm_r1
        jmp setdy
cm_r1:  lda cm_at              ; this row of a, then of b, converted to the result's type
        sta vt
        lda cm_pa
        sta vp
        lda cm_pa+1
        sta vp+1
        lda cm_ka
        sta vn
        lda cm_ka+1
        sta vn+1
        lda cm_t
        sta nt
        jsr cvcopy
        lda cm_bt
        sta vt
        lda cm_pb
        sta vp
        lda cm_pb+1
        sta vp+1
        lda cm_kb
        sta vn
        lda cm_kb+1
        sta vn+1
        lda cm_t
        sta nt
        jsr cvcopy
        clc
        lda cm_pa
        adc cm_sa
        sta cm_pa
        lda cm_pa+1
        adc cm_sa+1
        sta cm_pa+1
        clc
        lda cm_pb
        adc cm_sb
        sta cm_pb
        lda cm_pb+1
        adc cm_sb+1
        sta cm_pb+1
        lda cm_rc
        bne cm_r2
        dec cm_rc+1
cm_r2:  dec cm_rc
        jmp cm_row

; ia = the bytes from one row to the next of an argument: A = its rank, X = its element width, cm_sk = its
; columns (for a matrix)
cm_sk:   .word 0
cm_stride:
        cmp #2
        beq cs_mat
        cmp #1
        beq cs_vec
        lda #0                  ; a scalar: the same element every row
        sta ia
        sta ia+1
        rts
cs_vec: stx ia                  ; a vector: one element per row
        lda #0
        sta ia+1
        rts
cs_mat: lda cm_sk
        sta ia
        lda cm_sk+1
        sta ia+1
        dex
        beq cs_r
cs_l:   clc
        lda ia
        adc cm_sk
        sta ia
        lda ia+1
        adc cm_sk+1
        sta ia+1
        dex
        bne cs_l
cs_r:   rts
