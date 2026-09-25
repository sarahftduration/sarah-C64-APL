; Output formatting. Spec: apl64.py f_format, fmt_elem, format_value.
;
; fmt_value writes the top value's text, without a trailing newline, one byte at a
; time through fput (jmp (outv)). Newline is $0a; the negative sign is the charset
; code $90. echo_print is fmt_value plus a newline: an echo hook.
;
; Floats print to 4 significant digits, rounded half up on the *exact* value (the
; model uses exact arithmetic, so 123450 is a tie and prints 1.235E5). That needs
; only the first five significant digits, computed exactly: a large integer by
; doubling a decimal digit array, a fraction by repeatedly multiplying its 144-bit
; binary expansion by 10. Exact integers up to 65536 print in full.
; Matrices are laid out in columns as wide as their widest entry (at most 256
; columns; more is LIMIT ERROR).

fbuf    = FMT                   ; 16 bytes: one formatted element
flen    = FMT+16
fkx      = FMT+17                ; decimal exponent of the leading digit (2, signed)
fsgn    = FMT+19
fdig    = FMT+20                ; the first five significant digits
fnd     = FMT+25
fMv     = FMT+26
fsv     = FMT+28
ftv     = FMT+30
fIv     = FMT+31
ftmp    = FMT+33
fnI     = FMT+35
fdt     = FMT+36                ; digits, least significant first (6)
fexp2   = FMT+42
fnds    = FMT+43
fdl     = FMT+44
fcc     = FMT+45
fcar    = FMT+46
fn0     = FMT+47
fn1     = FMT+48
fn2     = FMT+49
fn3     = FMT+50
fdi     = FMT+51
fvt     = FMT+52
fmask   = FMT+53
ffr     = FMT+55
outv    = FMT+57
fcnt    = FMT+59
fpad    = FMT+61
fnk1    = FMT+62
fr_r    = FMT+63
fr_c    = FMT+65
fr_w    = FMT+67
fr_row  = FMT+68
fr_bytes = FMT+69
fr_i    = FMT+71
fr_j    = FMT+73
fr_ptr  = FMT+75
fr_col  = FMT+77
fr_wd   = FMT+79
fr_base = FMT+80
ferrc   = FMT+82

CHNL    = $0a
NEGC    = $90

fput:   jmp (outv)
fmt_null: rts

; --- small helpers --------------------------------------------------------------------
bput:   ldy flen
        sta fbuf,y
        inc flen
        rts

; ftmp (16 bits) -> fdt = decimal digits, least significant first; fnI = count (>= 1)
dec16:  ldx #0
d16l:   lda #0
        ldy #16
d16a:   asl ftmp
        rol ftmp+1
        rol
        cmp #10
        bcc d16b
        sbc #10
        inc ftmp
d16b:   dey
        bne d16a
        sta fdt,x
        inx
        lda ftmp
        ora ftmp+1
        bne d16l
        stx fnI
        rts

; put fdt's digits, most significant first, into fbuf
put_fdt:
        ldx fnI
        stx fdi
pf1:    dec fdi
        ldx fdi
        lda fdt,x
        ora #'0'
        jsr bput
        lda fdi
        bne pf1
        rts

; double the digit array DIGS (fdl digits)
dbl_digs:
        lda #0
        sta fcc
        ldx #0
dd1:    cpx fdl
        bcs dd2
        lda DIGS,x
        asl
        clc
        adc fcc
        ldy #0
        cmp #10
        bcc dd3
        sbc #10
        ldy #1
dd3:    sta DIGS,x
        sty fcc
        inx
        jmp dd1
dd2:    lda fcc
        beq dd4
        sta DIGS,x
        inc fdl
dd4:    rts

; FR = FR * 10; A = the digit that fell off the top
nextdig:
        lda #0
        sta fcar
        ldx #0
ndl1:    lda FR,x
        sta fn0
        lda #0
        sta fn1
        asl fn0
        rol fn1
        lda fn0
        sta fn2
        lda fn1
        sta fn3
        asl fn0
        rol fn1
        asl fn0
        rol fn1
        clc
        lda fn0
        adc fn2
        sta fn0
        lda fn1
        adc fn3
        sta fn1
        clc
        lda fn0
        adc fcar
        sta fn0
        bcc ndl2
        inc fn1
ndl2:    lda fn0
        sta FR,x
        lda fn1
        sta fcar
        inx
        cpx #18
        bne ndl1
        lda fcar
        rts

; --- one float (in fa) -> fbuf/flen -------------------------------------------------------
f_fmt:  lda #0
        sta flen
        lda fa
        bne ff_nz
        lda #'0'
        jmp bput
ff_nz:  sta fexp2
        lda fa+1
        and #$80
        sta fsgn
        lda fa+1
        and #$7f
        ora #$80
        sta fMv+1
        lda fa+2
        sta fMv
        lda fexp2               ; s = exponent - 144
        sec
        sbc #144
        sta fsv
        lda #0
        sbc #0
        sta fsv+1
        bpl *+5
        jmp ff_B
        lda fsv                 ; s >= 0: an integer M * 2^s
        bne ff_A2
        lda fMv
        sta ftmp
        lda fMv+1
        sta ftmp+1
        jmp ff_int
ff_A2:  cmp #1
        bne ff_A3
        lda fMv+1
        cmp #$80
        bne ff_A3
        lda fMv
        bne ff_A3
        lda #6                  ; 65536
        sta fdt
        lda #3
        sta fdt+1
        lda #5
        sta fdt+2
        sta fdt+3
        lda #6
        sta fdt+4
        lda #5
        sta fnI
        jmp ff_intd
ff_A3:  lda fMv
        sta ftmp
        lda fMv+1
        sta ftmp+1
        jsr dec16
        ldx #39
        lda #0
ff_z1:  sta DIGS,x
        dex
        bpl ff_z1
        ldx #0
ff_c1:  lda fdt,x
        sta DIGS,x
        inx
        cpx fnI
        bne ff_c1
        lda fnI
        sta fdl
ff_dbl: lda fsv
        beq ff_dend
        jsr dbl_digs
        dec fsv
        jmp ff_dbl
ff_dend:
        ldx fdl
        dex
        stx fkx
        lda #0
        sta fkx+1
        ldy #0                  ; the top five digits
ff_t1:  lda #0
        cpx #$ff
        beq ff_t2
        lda DIGS,x
        dex
ff_t2:  sta fdig,y
        iny
        cpy #5
        bne ff_t1
        jmp ff_round

ff_B:   sec                     ; a fraction: t = -s bits
        lda #0
        sbc fsv
        sta ftv
        cmp #16
        bcs ff_B16
        lda fMv                 ; t <= 15: I = M >> t, the rest is the fraction
        sta fIv
        lda fMv+1
        sta fIv+1
        lda #0
        sta fmask
        sta fmask+1
        ldx ftv
ff_m1:  lsr fIv+1
        ror fIv
        sec
        rol fmask
        rol fmask+1
        dex
        bne ff_m1
        lda fMv
        and fmask
        sta ffr
        lda fMv+1
        and fmask+1
        sta ffr+1
        jmp ff_Bgo
ff_B16: lda #0
        sta fIv
        sta fIv+1
        lda fMv
        sta ffr
        lda fMv+1
        sta ffr+1
ff_Bgo: lda ffr
        ora ffr+1
        bne ff_frac
        lda fIv                 ; no fraction: an exact integer
        sta ftmp
        lda fIv+1
        sta ftmp+1
        jmp ff_int
ff_frac:
        ldx #17
        lda #0
ff_f0:  sta FR,x
        dex
        bpl ff_f0
        sec                     ; place the fraction bits at bit u = 144 - t
        lda #144
        sbc ftv
        pha
        and #7
        tax
        lda ffr
        sta fn0
        lda ffr+1
        sta fn1
        lda #0
        sta fn2
        cpx #0
        beq ff_f1
ff_f2:  asl fn0
        rol fn1
        rol fn2
        dex
        bne ff_f2
ff_f1:  pla
        lsr
        lsr
        lsr
        tax                     ; byte offset
        lda fn0
        sta FR,x
        inx
        lda fn1
        sta FR,x
        inx
        cpx #18
        bcs ff_f3
        lda fn2
        sta FR,x
ff_f3:  lda #0
        sta fnd
        lda fIv
        ora fIv+1
        beq ff_lead
        lda fIv                 ; leading digits from the integer part
        sta ftmp
        lda fIv+1
        sta ftmp+1
        jsr dec16
        ldx fnI
        dex
        stx fkx
        lda #0
        sta fkx+1
        ldy #0
ff_i1:  lda fdt,x
        sta fdig,y
        iny
        dex
        bpl ff_i1
        sty fnd
        jmp ff_fill
ff_lead: lda #$ff
        sta fkx
        sta fkx+1
ff_fill: lda fnd
        cmp #5
        beq ff_fdone
        jsr nextdig
        ldx fnd
        bne ff_put
        cmp #0
        bne ff_put
        lda fkx                  ; a leading zero after the point
        bne ff_l1
        dec fkx+1
ff_l1:  dec fkx
        jmp ff_fill
ff_put: ldx fnd
        sta fdig,x
        inc fnd
        jmp ff_fill
ff_fdone:
        jmp ff_round

; an exact integer in ftmp
ff_int: jsr dec16
ff_intd:
        lda fsgn
        beq ff_i2
        lda #NEGC
        jsr bput
ff_i2:  jmp put_fdt

; round to four digits (half up on the fifth), then lay out by exponent
ff_round:
        lda fdig+4
        cmp #5
        bcc ff_norr
        ldx #3
ff_r1:  inc fdig,x
        lda fdig,x
        cmp #10
        bcc ff_norr
        lda #0
        sta fdig,x
        dex
        bpl ff_r1
        lda #1                  ; 9999 rounded up: 1000, one decade higher
        sta fdig
        inc fkx
        bne ff_norr
        inc fkx+1
ff_norr:
        ldx #4                  ; drop trailing zeros, keeping at least one digit
ff_s1:  cpx #1
        beq ff_s2
        lda fdig-1,x
        bne ff_s2
        dex
        jmp ff_s1
ff_s2:  stx fnds
        lda fsgn
        beq ff_s3
        lda #NEGC
        jsr bput
ff_s3:  lda fkx+1
        bpl *+5
        jmp ff_kneg
        beq *+5
        jmp ff_sci
        lda fkx
        cmp #10
        bcc *+5
        jmp ff_sci
        clc                     ; k in 0..9
        adc #1
        sta fnk1
        lda fnds
        cmp fnk1
        beq ff_kd
        bcs ff_kdot
ff_kd:  ldx #0                  ; all digits, then zeros up to the units place
ff_kd1: cpx fnds
        beq ff_kd2
        lda fdig,x
        ora #'0'
        stx fdi
        jsr bput
        ldx fdi
        inx
        jmp ff_kd1
ff_kd2: lda fnk1
        sec
        sbc fnds
        beq ff_done
        tax
ff_kd3: lda #'0'
        stx fdi
        jsr bput
        ldx fdi
        dex
        bne ff_kd3
        rts
ff_kdot:
        ldx #0                  ; digits before the point, then the rest
ff_kp1: lda fdig,x
        ora #'0'
        stx fdi
        jsr bput
        ldx fdi
        inx
        cpx fnk1
        bne ff_kp1
        lda #'.'
        stx fdi
        jsr bput
        ldx fdi
ff_kp2: lda fdig,x
        ora #'0'
        stx fdi
        jsr bput
        ldx fdi
        inx
        cpx fnds
        bne ff_kp2
ff_done: rts
ff_kneg:
        lda fkx                  ; k in -5..-1: 0.000ddd
        cmp #$fb
        bcc ff_sci
        lda #'0'
        jsr bput
        lda #'.'
        jsr bput
        lda fkx
        eor #$ff                ; -k-1 zeros
        tax
        beq ff_kn2
ff_kn1: lda #'0'
        stx fdi
        jsr bput
        ldx fdi
        dex
        bne ff_kn1
ff_kn2: ldx #0
ff_kn3: lda fdig,x
        ora #'0'
        stx fdi
        jsr bput
        ldx fdi
        inx
        cpx fnds
        bne ff_kn3
        rts
ff_sci: lda fdig                ; d.dddE±k
        ora #'0'
        jsr bput
        lda fnds
        cmp #2
        bcc ff_sc2
        lda #'.'
        jsr bput
        ldx #1
ff_sc1: lda fdig,x
        ora #'0'
        stx fdi
        jsr bput
        ldx fdi
        inx
        cpx fnds
        bne ff_sc1
ff_sc2: lda #'E'
        jsr bput
        lda fkx+1
        bpl ff_sc3
        lda #NEGC
        jsr bput
        sec                     ; |k|
        lda #0
        sbc fkx
        sta ftmp
        lda #0
        sbc fkx+1
        sta ftmp+1
        jmp ff_sc4
ff_sc3: lda fkx
        sta ftmp
        lda fkx+1
        sta ftmp+1
ff_sc4: jsr dec16
        jmp put_fdt

; --- one element at ep, of type fvt -> fbuf/flen --------------------------------------------------
fmt_elem:
        lda #0
        sta flen
        lda fvt
        beq fe_bool
        cmp #2
        beq fe_int
        ldy #0
        lda (ep),y
        sta fa
        iny
        lda (ep),y
        sta fa+1
        iny
        lda (ep),y
        sta fa+2
        jmp f_fmt
fe_bool:
        ldy #0
        lda (ep),y
        ora #'0'
        jmp bput
fe_int: ldy #0
        lda (ep),y
        sta ftmp
        iny
        lda (ep),y
        sta ftmp+1
        bpl fe_i2
        lda #NEGC
        jsr bput
        sec
        lda #0
        sbc ftmp
        sta ftmp
        lda #0
        sbc ftmp+1
        sta ftmp+1
fe_i2:  jsr dec16
        jmp put_fdt

; write fbuf, right-aligned in fpad extra leading spaces
emit_fbuf:
        lda #0
        sta fdi
ef1:    lda fdi
        cmp flen
        beq ef2
        tax
        lda fbuf,x
        jsr fput
        inc fdi
        jmp ef1
ef2:    rts

emit_spaces:
        lda fpad
        beq esp2
esp1:    lda #' '
        jsr fput
        dec fpad
        bne esp1
esp2:    rts

; --- the value on top of the stack ----------------------------------------------------------------
fmt_value:
        lda #0
        sta ferrc
        jsr fmt_body
        lda ferrc
        beq fvx
        sec
        rts
fvx:    clc
        rts

fmt_body:
        jsr topcell
        jsr getval
        lda vt
        sta fvt
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        lda vt
        cmp #1
        beq fv_char
        jmp fv_num
fv_char:
        lda vrk
        bne fc1
        ldy #0
        lda (ep),y
        jmp fput
fc1:    cmp #2
        beq fc_mat
        lda vn                  ; a string
        sta fcnt
        lda vn+1
        sta fcnt+1
fc2:    lda fcnt
        ora fcnt+1
        beq fc3
        ldy #0
        lda (ep),y
        jsr fput
        inc ep
        bne fc4
        inc ep+1
fc4:    lda fcnt
        bne fc5
        dec fcnt+1
fc5:    dec fcnt
        jmp fc2
fc3:    rts
fc_mat: lda vs0                 ; rows of characters
        sta fr_r
        lda vs0+1
        sta fr_r+1
fm1:    lda fr_r
        ora fr_r+1
        beq fc3
        lda vs1
        sta fcnt
        lda vs1+1
        sta fcnt+1
fm2:    lda fcnt
        ora fcnt+1
        beq fm3
        ldy #0
        lda (ep),y
        jsr fput
        inc ep
        bne fm4
        inc ep+1
fm4:    lda fcnt
        bne fm5
        dec fcnt+1
fm5:    dec fcnt
        jmp fm2
fm3:    lda fr_r
        bne fm6
        dec fr_r+1
fm6:    dec fr_r
        lda fr_r
        ora fr_r+1
        beq fc3
        lda #CHNL
        jsr fput
        jmp fm1

fv_num: lda vrk
        cmp #2
        bne fn_vec
        jmp fn_mat
fn_vec: lda vn
        sta fcnt
        lda vn+1
        sta fcnt+1
        ldx fvt
        lda WIDTHT,x
        sta fr_w
fn1x:   lda fcnt
        ora fcnt+1
        bne fn2x
        rts
fn2x:   jsr fmt_elem
        lda fcnt                ; a separator unless this is the last
        cmp #1
        bne fn3x
        lda fcnt+1
        bne fn3x
        jsr emit_fbuf
        rts
fn3x:   jsr emit_fbuf
        lda #' '
        jsr fput
        clc
        lda ep
        adc fr_w
        sta ep
        bcc fn4x
        inc ep+1
fn4x:   lda fcnt
        bne fn5x
        dec fcnt+1
fn5x:   dec fcnt
        jmp fn1x

; a numeric matrix: columns as wide as their widest entry
fn_mat: lda vs0
        sta fr_r
        lda vs0+1
        sta fr_r+1
        lda vs1
        sta fr_c
        lda vs1+1
        sta fr_c+1
        ldx fvt
        lda WIDTHT,x
        sta fr_w
        lda vp
        sta fr_base
        lda vp+1
        sta fr_base+1
        lda fr_c+1              ; at most 256 columns
        cmp #2
        bcc fmc1
        lda #E_LIMIT
        sta ferrc
        rts
fmc1:   lda fr_c
        ora fr_c+1
        bne fmc2
        lda fr_r                ; no columns: empty lines
        ora fr_r+1
        beq fmc_done
fmc_nl: lda fr_r
        bne fmc_n1
        dec fr_r+1
fmc_n1: dec fr_r
        lda fr_r
        ora fr_r+1
        beq fmc_done
        lda #CHNL
        jsr fput
        jmp fmc_nl
fmc_done:
        clc
        rts
fmc2:   lda fr_r
        ora fr_r+1
        bne fmc3
        clc
        rts
fmc3:   lda fr_w                ; the row size in bytes: c * w
        sta fn0
        lda #0
        sta fn1
        lda fr_c
        sta fr_bytes
        lda fr_c+1
        sta fr_bytes+1
        lda fr_w
        cmp #2
        bcc fmc4
        clc
        lda fr_bytes
        adc fr_c
        sta fr_bytes
        lda fr_bytes+1
        adc fr_c+1
        sta fr_bytes+1
        lda fr_w
        cmp #3
        bcc fmc4
        clc
        lda fr_bytes
        adc fr_c
        sta fr_bytes
        lda fr_bytes+1
        adc fr_c+1
        sta fr_bytes+1
fmc4:   lda #0                  ; pass 1: the width of each column
        sta fr_j
        sta fr_j+1
fp1:    lda fr_j                ; ptr = base + j*w
        cmp fr_c
        bne fp1a
        lda fr_j+1
        cmp fr_c+1
        bne *+5
        jmp fp_pass2
fp1a:   lda fr_base
        sta fr_ptr
        lda fr_base+1
        sta fr_ptr+1
        lda fr_j                ; add j * w
        sta fn0
        lda fr_j+1
        sta fn1
        lda fr_w
        cmp #2
        bcc fp1b
        clc
        lda fr_ptr
        adc fn0
        sta fr_ptr
        lda fr_ptr+1
        adc fn1
        sta fr_ptr+1
        lda fr_w
        cmp #3
        bcc fp1b
        clc
        lda fr_ptr
        adc fn0
        sta fr_ptr
        lda fr_ptr+1
        adc fn1
        sta fr_ptr+1
fp1b:   clc
        lda fr_ptr
        adc fn0
        sta fr_ptr
        lda fr_ptr+1
        adc fn1
        sta fr_ptr+1
        lda #0
        sta fr_wd
        lda fr_r
        sta fr_i
        lda fr_r+1
        sta fr_i+1
fp2:    lda fr_ptr
        sta ep
        lda fr_ptr+1
        sta ep+1
        jsr fmt_elem
        lda flen
        cmp fr_wd
        bcc fp3
        sta fr_wd
fp3:    clc
        lda fr_ptr
        adc fr_bytes
        sta fr_ptr
        lda fr_ptr+1
        adc fr_bytes+1
        sta fr_ptr+1
        lda fr_i
        bne fp4
        dec fr_i+1
fp4:    dec fr_i
        lda fr_i
        ora fr_i+1
        bne fp2
        ldx fr_j
        lda fr_wd
        sta COLW,x
        inc fr_j
        bne fp1x
        inc fr_j+1
fp1x:   jmp fp1
fp_pass2:
        lda fr_base             ; pass 2: rows
        sta fr_ptr
        lda fr_base+1
        sta fr_ptr+1
        lda fr_r
        sta fr_i
        lda fr_r+1
        sta fr_i+1
fq1:    lda #0
        sta fr_j
        sta fr_j+1
        lda fr_ptr
        sta ep
        lda fr_ptr+1
        sta ep+1
fq2:    jsr fmt_elem
        ldx fr_j
        lda COLW,x
        sec
        sbc flen
        sta fpad
        jsr emit_spaces
        jsr emit_fbuf
        inc fr_j
        lda fr_j
        cmp fr_c
        beq fq3
        lda #' '
        jsr fput
        clc
        lda ep
        adc fr_w
        sta ep
        bcc fq2
        inc ep+1
        jmp fq2
fq3:    lda fr_i
        bne fq4
        dec fr_i+1
fq4:    dec fr_i
        lda fr_i
        ora fr_i+1
        beq fq5
        lda #CHNL
        jsr fput
        clc
        lda fr_ptr
        adc fr_bytes
        sta fr_ptr
        lda fr_ptr+1
        adc fr_bytes+1
        sta fr_ptr+1
        jmp fq1
fq5:    clc
        rts

; echo hook: the value, then a newline
echo_print:
        jsr fmt_value
        bcc epr1
        rts
epr1:    lda #CHNL
        jmp fput
