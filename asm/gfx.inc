; Graphics, the mode and the colours: ⎕GR ⎕PAL ⎕INK ⎕WAIT (an overlay, see overlay.inc; the drawing is draw.inc, and gfxcom.inc
; is in both). Spec: apl64.py, Graphics; DESIGN.md, Graphics.
;
; The picture is the 8000 bytes at $E000 (RAM under the KERNAL: the CPU sees it only with $01 bit 1 cleared and
; interrupts off, see gq_ron), its colours are screen RAM ($CC00) and colour RAM ($D800). Entering graphics mode
; keeps the text screen in the REU (REU_SCRSAVE) and leaving puts it back; the screen driver ignores what is
; printed in between (gr_on), and the REPL waits for a key after a line that left the picture up (gr_after).
;
; Entered through s_gfxm (monadic) and s_gfxd (dyadic) with A = the function number, and s_grexit. A dyadic
; function's left argument is the top cell of the value stack, its right argument the one below it.

g1      .block
; --- the entry points, by function number: GR PAL INK PLOT LINE BOX WAIT (the drawing functions are in draw.inc) --------------
p_gfxm: cmp #7
        bcs gq_nonce
        asl
        tax
        lda gq_mtab+1,x         ; (the routines' addresses less one: the return goes to the routine's caller)
        pha
        lda gq_mtab,x
        pha
        rts
p_gfxd: cmp #1
        beq gq_dpal
        cmp #3
        bcc gq_nonce
        cmp #6
        bcs gq_nonce
        jmp s_drawd             ; PLOT LINE BOX: the other overlay
gq_dpal: jmp d_pal
gq_mtab: .word m_gr-1, m_pal-1, m_ink-1, gq_nonce-1, gq_nonce-1, gq_nonce-1, m_wait-1

        .include "gfxcom.inc"

; --- variables -----------------------------------------------------------------------------------------------------------
gq_cnt: .word 0                 ; the length of a fill
gq_fv:  .byte 0
gq_lim: .byte 0
gq_pass: .byte 0
gq_xp:  .word 0                 ; ⎕PAL: the rows and colours: data pointer, type, count
gq_yp:  .word 0
gq_xt:  .byte 0
gq_yt:  .byte 0
gq_xn:  .word 0
gq_yn:  .word 0
gq_rp:  .word 0                 ; the next row and colour to read
gq_cp:  .word 0
gq_rw:  .byte 0                 ; the row being set
gq_uni: .byte 0                 ; the same colours for every row
gq_kk:  .byte 0                 ; the colours of a row (3 or 2), and twice that
gq_k2:  .byte 0

gq_defpal: .word 0, 1, 2, 14    ; background and the colours of the pixel values 1, 2 and 3 after ⎕GR 1
gq_r40: .for i = 0, i < 25, i += 1
        .word i * 40
        .next

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


; fill gq_cnt bytes from cd with A
gq_fill: sta gq_fv
        ldy #0
gqf_p:  lda gq_cnt+1            ; whole pages
        beq gqf_t
        lda gq_fv
gqf_l:  sta (cd),y
        iny
        bne gqf_l
        inc cd+1
        dec gq_cnt+1
        jmp gqf_p
gqf_t:  ldx gq_cnt              ; then the rest
        beq gqf_d
        lda gq_fv
gqf_r:  sta (cd),y
        iny
        dex
        bne gqf_r
gqf_d:  rts


; --- graphics mode on and off ---------------------------------------------------------------------------------------------
; the four numbers of gq_c (background, then the colours of pixel values 1 to 3) for every cell
gq_setpal:
        lda gq_c
        sta $d020
        sta $d021
        lda gr_mode
        cmp #2
        bcs gqs_h
        lda gq_c+2              ; multicolor: the colours of pixel values 1 and 2 in screen RAM, that of 3 in colour RAM
        asl
        asl
        asl
        asl
        ora gq_c+4
        jmp gqs_f
gqs_h:  lda gq_c+2              ; hires: pixel value 1 in the high nibble, 0 in the low
        asl
        asl
        asl
        asl
        ora gq_c
gqs_f:  pha
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
        lda gr_mode
        cmp #2
        bcc gqs_c
        rts                     ; (hires does not use colour RAM)
gqs_c:  lda #<COLORRAM
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

; A = the mode: 1 multicolor, 2 hires
gq_enter:
        pha
        bit gr_on               ; the text screen is kept in the REU the first time only
        bmi gqe_in
        lda #REUCMD_STASH
        jsr gq_scrxfer
gqe_in: lda #$80
        sta gr_on
        pla
        sta gr_mode
        lda #1
        sta gr_ink
        ldx #7                  ; the default palette
gqe_p:  lda gq_defpal,x
        sta gq_c,x
        dex
        bpl gqe_p
        lda gr_mode
        cmp #2
        bcc gqe_s
        lda #1                  ; hires: black and white
        sta gq_c+2
gqe_s:  jsr gq_setpal
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
        lda $d016               ; the multicolor bit, for mode 1 only
        and #$ef
        ldx gr_mode
        cpx #2
        bcs gqe_h
        ora #$10
gqe_h:  sta $d016
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
        cmp #3
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
        jsr gq_ncol
        sta gq_lim
        lda gq_v
        cmp gq_lim
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
; A = the colours in a palette: 4 in multicolor mode (the background and three), 2 in hires
gq_ncol: lda gr_mode
        asl
        sta gq_a
        lda #6
        sec
        sbc gq_a
        rts

m_pal:  jsr gq_mode
        bcs gmp_r
        jsr gq_top
        jsr gq_type
        bcs gmp_r
        jsr gq_ncol
        jsr gq_isn
        bcs gmp_r
        ldx #0
        jsr gq_readn
        jsr gq_ncol
        asl
        sta gq_k
        jsr gq_ck15
        bcs gmp_r
        jsr gq_setpal
        jmp gq_ret1
gmp_r:   rts

d_pal:  jsr gq_mode
        bcc gdp_1
        rts
gdp_1:  jsr gq_sec              ; the right argument: the colours
        jsr gq_type
        bcc gdp_2
        rts
gdp_2:  lda vt
        sta gq_yt
        lda vp
        sta gq_yp
        lda vp+1
        sta gq_yp+1
        lda vn
        sta gq_yn
        lda vn+1
        sta gq_yn+1
        jsr gq_top              ; the left: the rows
        jsr gq_type
        bcc gdp_3
        rts
gdp_3:  lda vt
        sta gq_xt
        lda vp
        sta gq_xp
        lda vp+1
        sta gq_xp+1
        lda vn
        sta gq_xn
        lda vn+1
        sta gq_xn+1
        lda #4                  ; the colours of a row: 3 in multicolor mode, 2 in hires
        sec
        sbc gr_mode
        sta gq_kk
        asl
        sta gq_k2
        lda #0                  ; the same for all the rows, or for each row?
        sta gq_uni
        lda gq_yn+1
        bne gdp_ea
        lda gq_yn
        cmp gq_kk
        bne gdp_ea
        inc gq_uni
        jsr gq_sec
        ldx #0
        jsr gq_readn
        lda gq_k2
        sta gq_k
        jsr gq_ck15
        bcc gdp_go
        rts
gdp_ea: lda gq_xn               ; the colours of a row times the rows
        asl
        sta gq_t
        lda gq_xn+1
        rol
        sta gq_t+1
        lda gq_kk
        cmp #3
        bcc gdp_t2
        clc
        lda gq_t
        adc gq_xn
        sta gq_t
        lda gq_t+1
        adc gq_xn+1
        sta gq_t+1
gdp_t2:
        lda gq_t
        cmp gq_yn
        bne gdp_len
        lda gq_t+1
        cmp gq_yn+1
        beq gdp_go
gdp_len: lda #E_LENGTH
        sec
        rts
gdp_go: lda #0                  ; two passes: check everything, then set the rows
        sta gq_pass
gdp_pass: lda gq_xp
        sta gq_rp
        lda gq_xp+1
        sta gq_rp+1
        lda gq_yp
        sta gq_cp
        lda gq_yp+1
        sta gq_cp+1
        lda gq_xn
        sta gq_n
        lda gq_xn+1
        sta gq_n+1
gdp_l:  lda gq_n
        ora gq_n+1
        bne gdp_m
        jmp gdp_end
gdp_m:
        lda gq_rp               ; the row
        sta ep
        lda gq_rp+1
        sta ep+1
        lda gq_xt
        sta vt
        jsr gq_elem
        lda gq_v+1
        beq gdp_r1
        jmp gdp_dom
gdp_r1: lda gq_v
        cmp #GQ_ROWS
        bcs gdp_dom
        sta gq_rw
        ldy gq_xt
        lda WIDTHT,y
        clc
        adc gq_rp
        sta gq_rp
        bcc gdp_4
        inc gq_rp+1
gdp_4:  lda gq_uni              ; its three colours (already in gq_c if they are the same for all)
        bne gdp_set
        ldx #0
gdp_c:  lda gq_cp
        sta ep
        lda gq_cp+1
        sta ep+1
        lda gq_yt
        sta vt
        jsr gq_elem
        lda gq_v+1
        bne gdp_dom
        lda gq_v
        cmp #16
        bcs gdp_dom
        sta gq_c,x
        ldy gq_yt
        lda WIDTHT,y
        clc
        adc gq_cp
        sta gq_cp
        bcc gdp_5
        inc gq_cp+1
gdp_5:  inx
        inx
        cpx gq_k2
        bcc gdp_c
gdp_set: lda gq_pass
        beq gdp_nx
        jsr gq_row
gdp_nx: lda gq_n
        bne gdp_6
        dec gq_n+1
gdp_6:  dec gq_n
        jmp gdp_l
gdp_end: lda gq_pass
        bne gdp_done
        inc gq_pass
        jmp gdp_pass
gdp_done: jmp gq_ret2
gdp_dom: lda #E_DOMAIN
        sec
        rts

; the cells of the row gq_rw: the colours c1 and c2 in screen RAM, c3 in colour RAM (gq_c+0, +2, +4)
gq_row: lda gq_rw
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
        lda gr_mode
        cmp #2
        bcs gqw_h
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
gqw_h:  lda gq_c+2              ; hires: c1 in the high nibble, c0 in the low; colour RAM is not used
        asl
        asl
        asl
        asl
        ora gq_c
        ldy #39
gqw_g:  sta (cd),y
        dey
        bpl gqw_g
        rts

gq_n:   .word 0
        .bend

GQ_FRAME = g1.gq_frame          ; (for the tests, which skip the wait for a video frame)
GQ_FRET = g1.gq_fret
