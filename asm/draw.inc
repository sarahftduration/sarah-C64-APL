; Graphics, the drawing: ⎕PLOT ⎕LINE ⎕BOX (an overlay, see overlay.inc; the mode and colours are gfx.inc, and gfxcom.inc is in both).
; Entered through s_drawd (from gfx.inc's p_gfxd) with A = the function number. Spec: apl64.py, Graphics.

g2      .block
; A = 3 PLOT, 4 LINE, 5 BOX
p_drawd: cmp #4
        bcc gd_plot
        beq gd_line
        jmp d_box
gd_plot: jmp d_plot
gd_line: jmp d_line

        .include "gfxcom.inc"

gq_px:  .word 0                 ; the pixel to set
gq_py:  .word 0
gq_n:   .word 0                 ; the points left
gq_cnt: .word 0
gq_xp:  .word 0                 ; the x and y arrays: data pointer, type, count
gq_yp:  .word 0
gq_xt:  .byte 0
gq_yt:  .byte 0
gq_xn:  .word 0
gq_yn:  .word 0
gq_ix:  .byte 0                 ; bytes from one x element to the next (0 for a single one), and for y
gq_iy:  .byte 0
gq_m:   .byte 0                 ; the mask of the pixel in its byte
gq_pat: .byte 0
gq_ink55: .byte 0               ; the ink in all four pixels of a byte
gq_dx:  .word 0                 ; the line
gq_dy:  .word 0
gq_err: .word 0
gq_e2:  .word 0
gq_sx:  .byte 0                 ; 0 for +1, $ff for -1
gq_sy:  .byte 0
gq_lm:  .byte 0                 ; the box: masks of the first and last byte of a row, the bytes between, the first byte's cell column
gq_rm:  .byte 0
gq_nb:  .byte 0
gq_bx:  .byte 0

gq_mask: .byte $c0, $30, $0c, $03
gq_inkt: .byte $00, $55, $aa, $ff
gq_lmask: .byte $ff, $3f, $0f, $03   ; the pixels of a byte from the one with this x mod 4 rightwards
gq_rmask: .byte $c0, $f0, $fc, $ff   ; ... and those up to it
gq_r320: .for i = 0, i < 25, i += 1
        .word GQ_BITMAP + i * 320
        .next

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

gbx_done: jmp gq_ret2
gbx_r:   rts

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
gbx_5:  jsr gq_setink           ; the clipped rectangle, row by row: the bytes of a row are set whole, the two ends under a mask
        jsr gq_ron
        lda gq_c
        and #3
        tax
        lda gq_lmask,x          ; the pixels of the first byte at or right of x0
        sta gq_lm
        lda gq_c+4
        and #3
        tax
        lda gq_rmask,x          ; the pixels of the last byte at or left of x1
        sta gq_rm
        lda gq_c+4              ; the bytes between the first and the last
        lsr
        lsr
        sta gq_nb
        lda gq_c
        lsr
        lsr
        sta gq_bx
        lda gq_nb
        sec
        sbc gq_bx
        sta gq_nb
        lda gq_c+2
        sta gq_py
gbx_row: lda gq_py
        lsr
        lsr
        lsr
        asl
        tax
        lda gq_r320,x           ; this pixel row's first byte: the cell row, plus the row in the cell, plus 8 per cell
        sta cd
        lda gq_r320+1,x
        sta cd+1
        lda gq_bx
        sta gq_t
        lda #0
        sta gq_t+1
        asl gq_t
        rol gq_t+1
        asl gq_t
        rol gq_t+1
        asl gq_t
        rol gq_t+1
        lda gq_py
        and #7
        clc
        adc gq_t
        sta gq_t
        bcc gbx_r1
        inc gq_t+1
gbx_r1: clc
        lda cd
        adc gq_t
        sta cd
        lda cd+1
        adc gq_t+1
        sta cd+1
        ldy #0
        lda gq_nb
        bne gbx_two
        lda gq_lm               ; one byte
        and gq_rm
        jsr gbx_put
        jmp gbx_next
gbx_two: lda gq_lm
        jsr gbx_put
        ldx gq_nb
        dex
        beq gbx_end
gbx_mid: clc
        lda cd
        adc #8
        sta cd
        bcc gbx_m1
        inc cd+1
gbx_m1: lda gq_ink55
        sta (cd),y
        dex
        bne gbx_mid
gbx_end: clc
        lda cd
        adc #8
        sta cd
        bcc gbx_e1
        inc cd+1
gbx_e1: lda gq_rm
        jsr gbx_put
gbx_next: inc gq_py
        lda gq_py
        cmp gq_c+6
        bcc gbx_rw
        beq gbx_rw
        jsr gq_roff
        jmp gq_ret2
gbx_rw: jmp gbx_row

; the pixels of the mask in the byte at (cd),y get the ink
gbx_put: sta gq_m
        eor #$ff
        and (cd),y
        sta gq_pat
        lda gq_m
        and gq_ink55
        ora gq_pat
        sta (cd),y
        rts

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


        .bend
