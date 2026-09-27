; Graphics: the multicolor bitmap and the quad functions ⎕GR ⎕PAL ⎕INK ⎕PLOT ⎕LINE ⎕BOX ⎕WAIT (an overlay, see
; overlay.inc). Spec: apl64.py, Graphics; DESIGN.md, Graphics.
;
; The picture is the 8000 bytes at $E000 (RAM under the KERNAL: the CPU sees it only with $01 bit 1 cleared and
; interrupts off, see gq_ron), its colours are screen RAM ($CC00) and colour RAM ($D800). Entering graphics mode
; keeps the text screen in the REU (REU_SCRSAVE) and leaving puts it back; the screen driver ignores what is
; printed in between (gr_on), and the REPL waits for a key after a line that left the picture up (gr_after).
;
; Entered through s_gfxm (monadic) and s_gfxd (dyadic) with A = the function number, and s_grexit. A dyadic
; function's left argument is the top cell of the value stack, its right argument the one below it.

GQ_BITMAP = $e000
GQ_CELLS = 1000                 ; 40 x 25 cells
GQ_ROWS = 25
REU_SCRSAVE = $e000             ; where the text screen is kept, in REU bank 0 (above the overlay images)

; --- the entry points, by function number: GR PAL INK PLOT LINE BOX WAIT --------------------------------------------
p_gfxm: cmp #7
        bcs gq_nonce
        asl
        tax
        lda gq_mtab+1,x         ; (the routines' addresses less one: the return goes to the routine's caller)
        pha
        lda gq_mtab,x
        pha
        rts
p_gfxd: cmp #7
        bcs gq_nonce
        asl
        tax
        lda gq_dtab+1,x
        pha
        lda gq_dtab,x
        pha
        rts
gq_nonce:
        lda #E_NONCE
        sec
        rts
gq_mtab: .word m_gr-1, m_pal-1, m_ink-1, gq_nonce-1, gq_nonce-1, gq_nonce-1, m_wait-1
gq_dtab: .word gq_nonce-1, d_pal-1, gq_nonce-1, d_plot-1, d_line-1, d_box-1, gq_nonce-1

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

; --- variables -----------------------------------------------------------------------------------------------------------
gq_v:   .word 0                 ; the last number read (int16)
gq_a:   .byte 0
gq_c:   .fill 8                 ; up to four numbers, as words
gq_px:  .word 0                 ; the pixel to set
gq_py:  .word 0
gq_n:   .word 0                 ; the points left
gq_xp:  .word 0                 ; the x and y arrays: data pointer, type, count
gq_yp:  .word 0
gq_xt:  .byte 0
gq_yt:  .byte 0
gq_xn:  .word 0
gq_yn:  .word 0
gq_ix:  .byte 0                 ; bytes from one x element to the next (0 for a single one), and for y
gq_iy:  .byte 0
gq_cnt: .word 0                 ; the length of a fill
gq_fv:  .byte 0
gq_t:   .word 0
gq_m:   .byte 0                 ; the mask of the pixel in its byte
gq_pat: .byte 0
gq_ink55: .byte 0               ; the ink in all four pixels of a byte
gq_svp: .byte 0                 ; the processor status and $01 kept by gq_ron
gq_sv1: .byte 0
gq_k:   .byte 0
gq_lim: .byte 0
gq_pass: .byte 0
gq_dx:  .word 0                 ; the line
gq_dy:  .word 0
gq_err: .word 0
gq_e2:  .word 0
gq_sx:  .byte 0                 ; 0 for +1, $ff for -1
gq_sy:  .byte 0

gq_defpal: .word 0, 1, 2, 14    ; background and the colours of the pixel values 1, 2 and 3 after ⎕GR 1
gq_mask: .byte $c0, $30, $0c, $03
gq_inkt: .byte $00, $55, $aa, $ff
gq_r320: .for i = 0, i < 25, i += 1
        .word GQ_BITMAP + i * 320
        .next
gq_r40: .for i = 0, i < 25, i += 1
        .word i * 40
        .next

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

; the argument just fetched, which has exactly one element (CHAR: DOMAIN, not one element: LENGTH): its value in gq_v
gq_one: jsr gq_type
        bcs gqo_r
        lda #1
        jsr gq_isn
        bcs gqo_r
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        jsr gq_elem
        clc
gqo_r:  rts

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

; the word at gq_c,x must lie in 0 to gq_lim-1: carry set (A = DOMAIN) if it does not
gq_ck:  lda gq_c+1,x
        bne gqk_bad
        lda gq_c,x
        cmp gq_lim
        bcs gqk_bad
        clc
        rts
gqk_bad: lda #E_DOMAIN
        sec
        rts

; the words of gq_c below offset gq_k must each lie in 0 to 15
gq_ck15: lda #16
        sta gq_lim
        ldx #0
gqc_l:  jsr gq_ck
        bcs gqc_r
        inx
        inx
        cpx gq_k
        bcc gqc_l
        clc
gqc_r:  rts

; --- the bitmap ---------------------------------------------------------------------------------------------------------------
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

; fill gq_cnt bytes from cd with A
gq_fill: sta gq_fv
        ldy #0
gqf_l:  lda gq_cnt
        ora gq_cnt+1
        beq gqf_d
        lda gq_fv
        sta (cd),y
        iny
        bne gqf_1
        inc cd+1
gqf_1:  lda gq_cnt
        bne gqf_2
        dec gq_cnt+1
gqf_2:  dec gq_cnt
        jmp gqf_l
gqf_d:  rts

gq_setink:
        ldx gr_ink
        lda gq_inkt,x
        sta gq_ink55
        rts

; set the pixel (gq_px, gq_py) to the ink; a pixel off the screen is skipped. The bitmap must be visible (gq_ron).
gq_pix: lda gq_py+1
        ora gq_px+1
        bne gqp_out
        lda gq_py
        cmp #200
        bcs gqp_out
        lda gq_px
        cmp #160
        bcs gqp_out
        lda gq_py
        lsr
        lsr
        lsr
        asl
        tax
        lda gq_r320,x           ; the address of the cell row
        sta cd
        lda gq_r320+1,x
        sta cd+1
        lda gq_px               ; plus cell column * 8 plus the pixel row in the cell
        and #$fc
        asl
        sta gq_t
        lda #0
        rol
        sta gq_t+1
        lda gq_py
        and #7
        clc
        adc gq_t
        sta gq_t
        bcc gqp_1
        inc gq_t+1
gqp_1:  clc
        lda cd
        adc gq_t
        sta cd
        lda cd+1
        adc gq_t+1
        sta cd+1
        lda gq_px
        and #3
        tax
        lda gq_mask,x
        sta gq_m
        and gq_ink55
        sta gq_pat
        lda gq_m
        eor #$ff
        ldy #0
        and (cd),y
        ora gq_pat
        sta (cd),y
gqp_out: rts

; --- graphics mode on and off ---------------------------------------------------------------------------------------------
; the four numbers of gq_c (background, then the colours of pixel values 1 to 3) for every cell
gq_setpal:
        lda gq_c
        sta $d020
        sta $d021
        lda gq_c+2
        asl
        asl
        asl
        asl
        ora gq_c+4
        pha
        lda #<SCREEN
        sta cd
        lda #>SCREEN
        sta cd+1
        lda #<GQ_CELLS
        sta gq_cnt
        lda #>GQ_CELLS
        sta gq_cnt+1
        pla
        jsr gq_fill
        lda #<COLORRAM
        sta cd
        lda #>COLORRAM
        sta cd+1
        lda #<GQ_CELLS
        sta gq_cnt
        lda #>GQ_CELLS
        sta gq_cnt+1
        lda gq_c+6
        jmp gq_fill

; the text screen to or from the REU: A = REUCMD_STASH or FETCH
gq_scrxfer:
        pha
        lda #<SCREEN
        sta REU_C64
        lda #>SCREEN
        sta REU_C64+1
        lda #<REU_SCRSAVE
        sta REU_ADDR
        lda #>REU_SCRSAVE
        sta REU_ADDR+1
        lda #0
        sta REU_ADDR+2
        lda #<GQ_CELLS
        sta REU_LEN
        lda #>GQ_CELLS
        sta REU_LEN+1
        pla
        jmp reu_go

gq_enter:
        bit gr_on               ; the text screen is kept in the REU the first time only
        bmi gqe_in
        lda #REUCMD_STASH
        jsr gq_scrxfer
gqe_in: lda #$80
        sta gr_on
        lda #1
        sta gr_mode
        sta gr_ink
        ldx #7                  ; the default palette
gqe_p:  lda gq_defpal,x
        sta gq_c,x
        dex
        bpl gqe_p
        jsr gq_setpal
        lda #<GQ_BITMAP
        sta cd
        lda #>GQ_BITMAP
        sta cd+1
        lda #<8000
        sta gq_cnt
        lda #>8000
        sta gq_cnt+1
        jsr gq_ron
        lda #0
        jsr gq_fill
        jsr gq_roff
        lda $d011               ; bitmap mode, multicolor, the bitmap at $E000 and the colours at $CC00
        ora #$20
        sta $d011
        lda $d016
        ora #$10
        sta $d016
        lda #$38
        sta $d018
        rts

gq_leave:
        bit gr_on
        bmi gql_go
        rts
gql_go: lda $d011
        and #$df
        sta $d011
        lda $d016
        and #$ef
        sta $d016
        lda #$34
        sta $d018
        lda #COLOR_BORDER
        sta $d020
        lda #COLOR_BG
        sta $d021
        lda #<COLORRAM
        sta cd
        lda #>COLORRAM
        sta cd+1
        lda #<GQ_CELLS
        sta gq_cnt
        lda #>GQ_CELLS
        sta gq_cnt+1
        lda #COLOR_FG
        jsr gq_fill
        lda #REUCMD_FETCH
        jsr gq_scrxfer
        lda #0
        sta gr_on
        sta gr_mode
        rts

p_grexit:
        jsr gq_leave
        clc
        rts

; --- ⎕GR n -----------------------------------------------------------------------------------------------------------------
m_gr:   jsr gq_top
        jsr gq_one
        bcs gmg_r
        lda gq_v+1
        bne gmg_dom
        lda gq_v
        beq gmg_off
        cmp #2
        bcs gmg_dom
        jsr gq_enter
        jmp gq_ret1
gmg_off: jsr gq_leave
        jmp gq_ret1
gmg_dom: lda #E_DOMAIN
        sec
gmg_r:   rts

; --- ⎕INK n and ⎕WAIT n ------------------------------------------------------------------------------------------------------
m_ink:  jsr gq_mode
        bcs gmi_r
        jsr gq_top
        jsr gq_one
        bcs gmi_r
        lda gq_v+1
        bne gmi_dom
        lda gq_v
        cmp #4
        bcs gmi_dom
        sta gr_ink
        jmp gq_ret1
gmi_dom: lda #E_DOMAIN
        sec
gmi_r:   rts

m_wait: jsr gq_top
        jsr gq_one
        bcs gmw_r
        lda gq_v+1
        bpl gmw_l
        lda #E_DOMAIN
        sec
        rts
gmw_l:   lda gq_v
        ora gq_v+1
        beq gmw_d
        jsr gq_frame
        lda $91                 ; RUN/STOP ends the wait
        cmp #$7f
        beq gmw_stop
        lda gq_v
        bne gmw_1
        dec gq_v+1
gmw_1:   dec gq_v
        jmp gmw_l
gmw_d:   jmp gq_ret1
gmw_stop: lda #E_INTR
        sec
gmw_r:   rts

; one video frame: the raster goes past line $F8 (the tests skip this routine)
gq_frame:
gqw_1:  lda $d012
        cmp #$f8
        bcc gqw_1
gqw_2:  lda $d012
        cmp #$f8
        bcs gqw_2
gq_fret: rts

; --- ⎕PAL c0 c1 c2 c3 and rows ⎕PAL c1 c2 c3 ---------------------------------------------------------------------------------
m_pal:  jsr gq_mode
        bcs gmp_r
        jsr gq_top
        jsr gq_type
        bcs gmp_r
        lda #4
        jsr gq_isn
        bcs gmp_r
        ldx #0
        jsr gq_readn
        lda #8
        sta gq_k
        jsr gq_ck15
        bcs gmp_r
        jsr gq_setpal
        jmp gq_ret1
gmp_r:   rts

d_pal:  jsr gq_mode
        bcc *+3
        rts
        jsr gq_sec              ; the right argument: three colours
        jsr gq_type
        bcs gdp_r
        jsr gq_top              ; the left: the rows
        jsr gq_type
        bcs gdp_r
        jsr gq_sec
        lda #3
        jsr gq_isn
        bcs gdp_r
        ldx #0
        jsr gq_readn
        lda #6
        sta gq_k
        jsr gq_ck15
        bcs gdp_r
        lda #0
        sta gq_pass
gdp_pass: jsr gq_top
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        lda vn
        sta gq_n
        lda vn+1
        sta gq_n+1
gdp_l:   lda gq_n
        ora gq_n+1
        beq gdp_end
        jsr gq_elem
        lda gq_v+1
        bne gdp_dom
        lda gq_v
        cmp #GQ_ROWS
        bcs gdp_dom
        lda gq_pass
        beq gdp_nx
        jsr gq_row
gdp_nx:  jsr gq_next
        lda gq_n
        bne gdp_1
        dec gq_n+1
gdp_1:   dec gq_n
        jmp gdp_l
gdp_end: lda gq_pass
        bne gdp_done
        inc gq_pass
        jmp gdp_pass
gdp_done: jmp gq_ret2
gdp_dom: lda #E_DOMAIN
        sec
gdp_r:   rts

; the cells of row gq_v: the colours c1 and c2 in screen RAM, c3 in colour RAM (gq_c+0, +2, +4)
gq_row: lda gq_v
        asl
        tax
        clc
        lda gq_r40,x
        adc #<SCREEN
        sta cd
        lda gq_r40+1,x
        adc #>SCREEN
        sta cd+1
        clc
        lda gq_r40,x
        adc #<COLORRAM
        sta cs
        lda gq_r40+1,x
        adc #>COLORRAM
        sta cs+1
        lda gq_c
        asl
        asl
        asl
        asl
        ora gq_c+2
        sta gq_t
        ldy #39
gqw_f:  lda gq_t
        sta (cd),y
        lda gq_c+4
        sta (cs),y
        dey
        bpl gqw_f
        rts

; --- x ⎕PLOT y --------------------------------------------------------------------------------------------------------------
d_plot: jsr gq_mode
        bcs gpl_r
        jsr gq_sec              ; y, the right argument
        jsr gq_type
        bcs gpl_r
        lda vt
        sta gq_yt
        lda vp
        sta gq_yp
        lda vp+1
        sta gq_yp+1
        lda vn
        sta gq_yn
        lda vn+1
        sta gq_yn+1
        jsr gq_top              ; x, the left argument
        jsr gq_type
        bcs gpl_r
        lda vt
        sta gq_xt
        lda vp
        sta gq_xp
        lda vp+1
        sta gq_xp+1
        lda vn
        sta gq_xn
        lda vn+1
        sta gq_xn+1
        lda gq_xn               ; the number of points: equal counts, or the one that is not a single number
        cmp gq_yn
        bne gpl_a
        lda gq_xn+1
        cmp gq_yn+1
        beq gpl_nx
gpl_a:   lda gq_yn+1
        bne gpl_b
        lda gq_yn
        cmp #1
        beq gpl_nx
gpl_b:   lda gq_xn+1
        bne gpl_len
        lda gq_xn
        cmp #1
        bne gpl_len
        lda gq_yn
        sta gq_n
        lda gq_yn+1
        sta gq_n+1
        jmp gpl_go
gpl_len: lda #E_LENGTH
        sec
gpl_r:   rts
gpl_nx:  lda gq_xn
        sta gq_n
        lda gq_xn+1
        sta gq_n+1
gpl_go:  lda gq_xn               ; the steps from one element to the next
        sta gq_cnt
        lda gq_xn+1
        sta gq_cnt+1
        ldx gq_xt
        jsr gq_stepof
        sta gq_ix
        lda gq_yn
        sta gq_cnt
        lda gq_yn+1
        sta gq_cnt+1
        ldx gq_yt
        jsr gq_stepof
        sta gq_iy
        jsr gq_setink
        jsr gq_ron
gpl_l:   lda gq_n
        ora gq_n+1
        beq gpl_end
        lda gq_xp
        sta ep
        lda gq_xp+1
        sta ep+1
        lda gq_xt
        sta vt
        jsr gq_elem
        lda gq_v
        sta gq_px
        lda gq_v+1
        sta gq_px+1
        clc
        lda gq_xp
        adc gq_ix
        sta gq_xp
        bcc gpl_1
        inc gq_xp+1
gpl_1:   lda gq_yp
        sta ep
        lda gq_yp+1
        sta ep+1
        lda gq_yt
        sta vt
        jsr gq_elem
        lda gq_v
        sta gq_py
        lda gq_v+1
        sta gq_py+1
        clc
        lda gq_yp
        adc gq_iy
        sta gq_yp
        bcc gpl_2
        inc gq_yp+1
gpl_2:   jsr gq_pix
        lda gq_n
        bne gpl_3
        dec gq_n+1
gpl_3:   dec gq_n
        jmp gpl_l
gpl_end: jsr gq_roff
        jmp gq_ret2

; A = the bytes from one element to the next of an array with gq_cnt elements of type X: 0 for a single one
gq_stepof:
        lda gq_cnt+1
        bne gqs_w
        lda gq_cnt
        cmp #2
        bcc gqs_0
gqs_w:  lda WIDTHT,x
        rts
gqs_0:  lda #0
        rts

; --- (x0 y0) ⎕LINE (x1 y1) and (x0 y0) ⎕BOX (x1 y1) --------------------------------------------------------------------------
; both arguments: two numbers each, in gq_c as x0 y0 x1 y1 (the left argument is the first corner). Carry set: an error.
gq_corners:
        jsr gq_mode
        bcs gqx_e
        jsr gq_sec
        jsr gq_type
        bcs gqx_e
        jsr gq_top
        jsr gq_type
        bcs gqx_e
        jsr gq_sec
        lda #2
        jsr gq_isn
        bcs gqx_e
        jsr gq_top
        lda #2
        jsr gq_isn
        bcs gqx_e
        jsr gq_sec
        ldx #4
        jsr gq_readn
        jsr gq_top
        ldx #0
        jsr gq_readn
        clc
gqx_e:  rts

; the words of gq_c must lie in -4095 to 4095 (the right argument's first): DOMAIN if not
gq_ck4095:
        ldx #4
gqk_l:  jsr gqk_one
        bcs gqz_bad
        inx
        inx
        cpx #8
        bcc gqk_l
        ldx #0
gqk_l2: jsr gqk_one
        bcs gqz_bad
        inx
        inx
        cpx #4
        bcc gqk_l2
        clc
        rts
gqz_bad: lda #E_DOMAIN
        sec
        rts
gqk_one: clc                    ; v + 4095 must be at most 8190, unsigned
        lda gq_c,x
        adc #<4095
        sta gq_t
        lda gq_c+1,x
        adc #>4095
        sta gq_t+1
        cmp #>8190
        bcc gqk_ok
        bne gqk_no
        lda gq_t
        cmp #<8191
        bcc gqk_ok
gqk_no: sec
        rts
gqk_ok: clc
        rts

d_line: jsr gq_corners
        bcc *+3
        rts
        jsr gq_ck4095
        bcc *+3
        rts
        sec                     ; dx = |x1 - x0|, sx = +1 if x0 < x1, else -1
        lda gq_c+4
        sbc gq_c
        sta gq_dx
        lda gq_c+5
        sbc gq_c+1
        sta gq_dx+1
        bmi gln_xn
        ora gq_dx
        beq gln_xn
        lda #0
        sta gq_sx
        beq gln_y
gln_xn:  lda #$ff
        sta gq_sx
        sec
        lda #0
        sbc gq_dx
        sta gq_dx
        lda #0
        sbc gq_dx+1
        sta gq_dx+1
gln_y:   sec                     ; dy = -|y1 - y0|, sy = +1 if y0 < y1, else -1
        lda gq_c+6
        sbc gq_c+2
        sta gq_dy
        lda gq_c+7
        sbc gq_c+3
        sta gq_dy+1
        bmi gln_yn
        ora gq_dy
        beq gln_yn
        lda #0                  ; y1 below y0 on the screen: dy = -diff
        sta gq_sy
        sec
        lda #0
        sbc gq_dy
        sta gq_dy
        lda #0
        sbc gq_dy+1
        sta gq_dy+1
        jmp gln_e
gln_yn:  lda #$ff
        sta gq_sy
gln_e:   clc                     ; err = dx + dy
        lda gq_dx
        adc gq_dy
        sta gq_err
        lda gq_dx+1
        adc gq_dy+1
        sta gq_err+1
        lda gq_c                ; the first pixel
        sta gq_px
        lda gq_c+1
        sta gq_px+1
        lda gq_c+2
        sta gq_py
        lda gq_c+3
        sta gq_py+1
        jsr gq_setink
        jsr gq_ron
gln_l:   jsr gq_pix
        lda gq_px
        cmp gq_c+4
        bne gln_m
        lda gq_px+1
        cmp gq_c+5
        bne gln_m
        lda gq_py
        cmp gq_c+6
        bne gln_m
        lda gq_py+1
        cmp gq_c+7
        bne gln_m
        jsr gq_roff
        jmp gq_ret2
gln_m:   lda gq_err              ; e2 = 2 err
        asl
        sta gq_e2
        lda gq_err+1
        rol
        sta gq_e2+1
        lda gq_e2               ; e2 >= dy (signed)?
        cmp gq_dy
        lda gq_e2+1
        sbc gq_dy+1
        bvc gln_c1
        eor #$80
gln_c1:  bmi gln_nx               ; e2 < dy: no x step
        clc
        lda gq_err
        adc gq_dy
        sta gq_err
        lda gq_err+1
        adc gq_dy+1
        sta gq_err+1
        lda gq_sx
        beq gln_xp
        lda gq_px
        bne gln_xd
        dec gq_px+1
gln_xd:  dec gq_px
        jmp gln_nx
gln_xp:  inc gq_px
        bne gln_nx
        inc gq_px+1
gln_nx:  lda gq_dx               ; e2 <= dx (signed)? that is, dx >= e2
        cmp gq_e2
        lda gq_dx+1
        sbc gq_e2+1
        bvc gln_c2
        eor #$80
gln_c2:  bmi gln_l2               ; dx < e2: no y step
        clc
        lda gq_err
        adc gq_dx
        sta gq_err
        lda gq_err+1
        adc gq_dx+1
        sta gq_err+1
        lda gq_sy
        beq gln_yp
        lda gq_py
        bne gln_yd
        dec gq_py+1
gln_yd:  dec gq_py
        jmp gln_l
gln_yp:  inc gq_py
        beq *+5
        jmp gln_l
        inc gq_py+1
gln_l2:  jmp gln_l
gln_r:   rts

d_box:  jsr gq_corners
        bcc *+3
        rts
        lda gq_c                ; x0 < x1 (signed)? if not, swap them, and the same for y
        cmp gq_c+4
        lda gq_c+1
        sbc gq_c+5
        bvc gbx_c1
        eor #$80
gbx_c1:  bmi gbx_y
        ldx #0
        jsr gbx_swap
gbx_y:   lda gq_c+2
        cmp gq_c+6
        lda gq_c+3
        sbc gq_c+7
        bvc gbx_c2
        eor #$80
gbx_c2:  bmi gbx_1
        ldx #2
        jsr gbx_swap
gbx_1:   lda gq_c+5              ; the corners are now low first: x1 or y1 below 0: nothing to draw
        bpl *+5
        jmp gbx_done
        lda gq_c+7
        bpl *+5
        jmp gbx_done
        lda gq_c+1              ; x0 or y0 below 0: start at 0
        bpl gbx_2
        lda #0
        sta gq_c
        sta gq_c+1
gbx_2:   lda gq_c+3
        bpl gbx_3
        lda #0
        sta gq_c+2
        sta gq_c+3
gbx_3:   lda gq_c+1              ; x0 above 159 or y0 above 199: nothing to draw
        bne gbx_done
        lda gq_c
        cmp #160
        bcs gbx_done
        lda gq_c+3
        bne gbx_done
        lda gq_c+2
        cmp #200
        bcs gbx_done
        lda gq_c+5              ; x1 above 159: 159, y1 above 199: 199
        bne gbx_x
        lda gq_c+4
        cmp #160
        bcc gbx_4
gbx_x:   lda #159
        sta gq_c+4
        lda #0
        sta gq_c+5
gbx_4:   lda gq_c+7
        bne gbx_y2
        lda gq_c+6
        cmp #200
        bcc gbx_5
gbx_y2:  lda #199
        sta gq_c+6
        lda #0
        sta gq_c+7
gbx_5:   jsr gq_setink           ; all the pixels of the clipped rectangle, row by row
        jsr gq_ron
        lda gq_c+2
        sta gq_py
        lda #0
        sta gq_py+1
        sta gq_px+1
gbx_row: lda gq_c
        sta gq_px
gbx_col: jsr gq_pix
        inc gq_px
        lda gq_px
        cmp gq_c+4
        bcc gbx_col
        beq gbx_col
        inc gq_py
        lda gq_py
        cmp gq_c+6
        bcc gbx_row
        beq gbx_row
        jsr gq_roff
gbx_done: jmp gq_ret2
gbx_r:   rts

; swap the words at gq_c,x and gq_c+4,x
gbx_swap: ldy #2
gbx_s1:  lda gq_c,x
        pha
        lda gq_c+4,x
        sta gq_c,x
        pla
        sta gq_c+4,x
        inx
        dey
        bne gbx_s1
        rts
