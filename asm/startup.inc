; Start-up, charset, screen driver, error messages, and (when assembled with
; -D SELFTEST=1) a scripted session that exercises the whole pipeline on screen.
; See DESIGN.md, Memory map.

SCREEN    = $cc00               ; screen RAM, VIC bank 3
COLORRAM  = $d800
CHARSET   = $d000               ; RAM under the I/O area; only the VIC reads it
COLOR_BORDER = $06               ; dark blue border and paper, yellow ink: high contrast, still C64-flavoured
COLOR_BG  = $06
COLOR_FG  = $07

; --- start-up -----------------------------------------------------------------------------
startup:
        sei
        cld
        ldx #$ff
        txs
        jsr reu_detect          ; first of all: the overlay images sit where the tables go
        bcs su_nr
        jsr ov_init
su_nr:
        lda #1                  ; the KERNAL must not draw its cursor (it thinks the screen is $0400)
        sta $cc
        lda #$80                ; nor switch character sets on SHIFT+C=, which would re-point ours
        sta $0291
        lda #<nmi_handler       ; RUN/STOP-RESTORE would reset the video and jump through $A002
        sta $0318
        lda #>nmi_handler
        sta $0319
        lda #0                  ; no KERNAL LOADING/SAVING messages
        jsr $ff90
        jsr build_charset
        lda #$36                ; BASIC out, KERNAL and I/O in
        sta $01
        lda $dd00               ; VIC bank 3 ($C000-$FFFF); bits 2-7 are other lines: keep them
        and #$fc
        sta $dd00
        lda #$34                ; screen at $CC00, charset at $D000
        sta $d018
        lda #COLOR_BORDER
        sta $d020
        lda #COLOR_BG
        sta $d021
        lda #<COLORRAM
        sta cd
        lda #>COLORRAM
        sta cd+1
        ldx #4
        lda #COLOR_FG
su1:    ldy #0
su2:    sta (cd),y
        iny
        bne su2
        inc cd+1
        dex
        bne su1
        jsr bss_init            ; RAM holds anything at power-up
        jsr tok_init
        jsr eval_init           ; (sets the test log pointer, which the cursor shares)
        jsr disk_init
        jsr scr_clear
        lda reu_banks
        bne su_reu
        lda #<msg_noreu         ; runs, but only with what is not in an overlay
        sta mp
        lda #>msg_noreu
        sta mp+1
        jsr print_z
        lda #CHNL
        jsr scr_put
su_reu:
        lda #<scr_put
        sta outv
        lda #>scr_put
        sta outv+1
        lda #<echo_print
        sta echov
        lda #>echo_print
        sta echov+1
        lda #<kbd_getin
        sta getkey_vec
        lda #>kbd_getin
        sta getkey_vec+1
        .if KEYTEST
        lda #<keytest_data
        sta ksp
        lda #>keytest_data
        sta ksp+1
        lda #<script_getkey
        sta getkey_vec
        lda #>script_getkey
        sta getkey_vec+1
        .endif
        cli
        jmp app_main

nmi_handler:
        pha
        lda $dd0d               ; acknowledge, or the NMI line stays low and never fires again
        pla
        rti

; zero the small variable blocks (the big tables are set up by their own init routines)
bss_init:
        lda #0
        ldx #95
bi1:    sta STV,x
        dex
        bpl bi1
        ldx #19
bi2:    sta WSNAME,x
        sta NAMETMP,x
        dex
        bpl bi2
        ldx #11
bi3:    sta CMDBUF,x
        dex
        bpl bi3
        rts

; --- the character set -------------------------------------------------------------------------
; Interrupts are off and $01 = $33 (character ROM visible at $D000): reads at $D800 give
; ROM shapes, writes at $D000 go to the RAM underneath.
build_charset:
        lda #$33
        sta $01
        lda #<CHARSET
        sta cd
        lda #>CHARSET
        sta cd+1
        ldx #8
        lda #0
        ldy #0
bc1:    sta (cd),y
        iny
        bne bc1
        inc cd+1
        dex
        bne bc1
        ldx #0                  ; shapes copied from the ROM
bc2:    lda rom_copy,x
        beq bc_glyphs
        sta cd
        lda #0
        sta cd+1
        jsr shift8
        clc
        lda cd+1
        adc #>CHARSET
        sta cd+1
        lda rom_copy+1,x
        sta cs
        lda #0
        sta cs+1
        asl cs
        rol cs+1
        asl cs
        rol cs+1
        asl cs
        rol cs+1
        clc
        lda cs+1
        adc #>(COLORRAM)        ; the second ROM set starts at $D800
        sta cs+1
        lda rom_copy+2,x
        sta t0
        lda #0
        sta t0+1
        asl t0
        rol t0+1
        asl t0
        rol t0+1
        asl t0
        rol t0+1
        jsr memcpy_cs_cd
        inx
        inx
        inx
        jmp bc2
bc_glyphs:
        lda #<glyph_table
        sta gtp
        lda #>glyph_table
        sta gtp+1
bg1:    lda gtp
        sta cs
        lda gtp+1
        sta cs+1
        ldy #0
        lda (cs),y
        beq bg_done
        sta cd
        lda #0
        sta cd+1
        jsr shift8
        clc
        lda cd+1
        adc #>CHARSET
        sta cd+1
        inc cs                  ; the 8 rows follow the code
        bne bg2
        inc cs+1
bg2:    lda #8
        sta t0
        lda #0
        sta t0+1
        jsr memcpy_cs_cd
        clc
        lda gtp
        adc #9
        sta gtp
        bcc bg1
        inc gtp+1
        jmp bg1
bg_done:
        rts

; cd (16 bits) = cd * 8
shift8: asl cd
        rol cd+1
        asl cd
        rol cd+1
        asl cd
        rol cd+1
        rts

; --- the screen driver: 40x25, direct writes, our codes are the screen codes ----------------------------
; scr_put: A = character. $0a is a newline; anything else is written at the cursor, and the
; cursor wraps to the next line after column 39. Below row 24 the screen scrolls.
; The cursor pointer is the zero-page pool slot of the test log pointer (logp), which only
; the py65 tests use.
scr_clear:
        lda #<SCREEN
        sta cd
        lda #>SCREEN
        sta cd+1
        ldx #4
        lda #' '
scl1:   ldy #0
scl2:   sta (cd),y
        iny
        bne scl2
        inc cd+1
        dex
        bne scl1
scr_home:
        lda #<SCREEN
        sta scrp
        lda #>SCREEN
        sta scrp+1
        lda #0
        sta scr_row
        sta scr_col
        rts

scr_put:
        cmp #CHNL
        beq scr_nl
        ldy #0
        sta (scrp),y
        inc scrp
        bne sp1
        inc scrp+1
sp1:    inc scr_col
        lda scr_col
        cmp #40
        bcc sp2
        jmp scr_next            ; wrapped: the pointer is already at the next row
sp2:    rts
scr_nl: sec                     ; to the start of the next row
        lda #40
        sbc scr_col
        clc
        adc scrp
        sta scrp
        bcc scr_next
        inc scrp+1
scr_next:
        lda #0
        sta scr_col
        inc scr_row
        lda scr_row
        cmp #25
        bcc sn1
        jsr scr_scroll
sn1:    rts

scr_scroll:
        lda #<(SCREEN+40)
        sta cs
        lda #>(SCREEN+40)
        sta cs+1
        lda #<SCREEN
        sta cd
        lda #>SCREEN
        sta cd+1
        lda #<960
        sta t0
        lda #>960
        sta t0+1
        jsr memcpy_cs_cd
        lda #<(SCREEN+960)
        sta scrp
        sta cd
        lda #>(SCREEN+960)
        sta scrp+1
        sta cd+1
        ldy #39
        lda #' '
ssc1:   sta (cd),y
        dey
        bpl ssc1
        lda #24
        sta scr_row
        rts

; step the cursor back one cell (across a wrapped line) and blank it; nothing at the top left
scr_back:
        lda scr_col
        bne sb1
        lda scr_row
        beq sb4
        dec scr_row
        lda #39
        sta scr_col
        jmp sb2
sb1:    dec scr_col
sb2:    lda scrp
        bne sb3
        dec scrp+1
sb3:    dec scrp
        ldy #0
        lda #' '
        sta (scrp),y
sb4:    rts

; --- text --------------------------------------------------------------------------------------------
; print the zero-terminated string at mp (scr_put may scroll, which uses cs and cd)
print_z:
        ldy #0
        lda (mp),y
        beq pz2
        jsr scr_put
        inc mp
        bne print_z
        inc mp+1
        jmp print_z
pz2:    rts

; A = error code 1..11: print its name and a newline
print_error:
        sec
        sbc #1
        asl
        tax
        lda errtab,x
        sta mp
        lda errtab+1,x
        sta mp+1
        jsr print_z
        lda #CHNL
        jmp scr_put

errtab: .word err1, err2, err3, err4, err5, err6, err7, err8, err9, err10, err11
err1:   .text "SYNTAX ERROR"
        .byte 0
err2:   .text "DOMAIN ERROR"
        .byte 0
err3:   .text "LIMIT ERROR"
        .byte 0
err4:   .text "NONCE ERROR"
        .byte 0
err5:   .text "VALUE ERROR"
        .byte 0
err6:   .text "RANK ERROR"
        .byte 0
err7:   .text "LENGTH ERROR"
        .byte 0
err8:   .text "WS FULL"
        .byte 0
err9:   .text "INDEX ERROR"
        .byte 0
err10:  .text "INTERRUPT"
        .byte 0
err11:  .text "NO REU"
        .byte 0
msg_noreu: .text "NO REU: LIMITED FEATURES"
        .byte 0

; --- the program ----------------------------------------------------------------------------------------
app_main:
        .if SELFTEST
        jmp selftest_run
        .else
        jmp repl
        .endif

        .if SELFTEST
; A scripted session: for each line, echo a prompt and the line, run it, print the error
; if any. The data is generated by the test (selftest_data.inc): a count, then for each
; line its length and its bytes in charset codes.
selftest_run:
        lda #<selftest_data
        sta stp
        lda #>selftest_data
        sta stp+1
        lda selftest_data
        sta stcount
        inc stp
        bne st_next
        inc stp+1
st_next:
        lda stcount
        bne st_go
        jmp selftest_done
st_go:  lda stp
        sta mp
        lda stp+1
        sta mp+1
        ldy #0
        lda (mp),y
        sta stlen
        jsr prompt
        lda #0
        sta stidx
st_c:   lda stidx
        cmp stlen
        beq st_run
        clc
        adc #1
        tay
        lda stp
        sta mp
        lda stp+1
        sta mp+1
        lda (mp),y              ; byte stidx of the line
        ldx stidx
        sta INBUF,x
        jsr scr_put
        inc stidx
        jmp st_c
st_run: ldx stidx
        lda #0
        sta INBUF,x
        lda #CHNL
        jsr scr_put
        clc                     ; step past this line's data
        lda stp
        adc stlen
        sta stp
        bcc st_a1
        inc stp+1
st_a1:  inc stp
        bne st_a2
        inc stp+1
st_a2:  dec stcount
        jsr do_line
        bcs st_err
        jmp st_next
st_err: jsr print_error
        jmp st_next
selftest_done:
        jmp selftest_done
        .include "selftest_data.inc"
        .endif

        .if KEYTEST
; scripted keys: the test's key list (keytest_data), ended by a zero, then stop
script_getkey:
        lda ksp
        sta mp
        lda ksp+1
        sta mp+1
        ldy #0
        lda (mp),y
        beq selftest_done
        inc ksp
        bne sg9
        inc ksp+1
sg9:    rts
        .if !SELFTEST
selftest_done:
        jmp selftest_done
        .endif
        .include "keytest_data.inc"
        .endif

        .include "editor.inc"
        .include "syscmd.inc"
        .include "keys.inc"
