; )SAVE and )LOAD: workspace files on the disk drive (KERNAL file I/O, device DEVNUM).
; Spec: DESIGN.md, Workspace files. The file is:
;   "APLW", version 1, number of variables (2 bytes), then for each defined variable
;   its name (length byte, then the characters), its value, and finally "E".
;   A value is its tag byte (type | rank<<2) and, for a scalar, its 1-3 data bytes; for
;   an array the heap layout: count (2), a 2-byte length per axis, then the data.

K_SETNAM = $ffbd
K_SETLFS = $ffba
K_OPEN   = $ffc0
K_CLOSE  = $ffc3
K_CHKIN  = $ffc6
K_CHKOUT = $ffc9
K_CLRCHN = $ffcc
K_CHRIN  = $ffcf
K_CHROUT = $ffd2
K_READST = $ffb7
LFN      = 2
WS_VERSION = 1

msg_saved:  .text "SAVED"
        .byte 0
msg_loaded: .text "LOADED"
        .byte 0
msg_notfound: .text "FILE NOT FOUND"
        .byte 0
msg_fileerr: .text "FILE ERROR"
        .byte 0
msg_notws:  .text "NOT A WORKSPACE"
        .byte 0

; --- opening and closing --------------------------------------------------------------------
; FNBUF holds the file name string; fnlen its length. Carry set: could not open.
open_file:
        lda fnlen
        ldx #<FNBUF
        ldy #>FNBUF
        jsr K_SETNAM
        lda #LFN
        ldx DEVNUM
        ldy #LFN
        jsr K_SETLFS
        jmp K_OPEN

close_file:
        jsr K_CLRCHN
        lda #LFN
        jmp K_CLOSE

; The drive's error channel: A = the two-digit code (0 = OK), or $ff if it could not be read.
disk_status:
        lda #0
        ldx #<FNBUF
        ldy #>FNBUF
        jsr K_SETNAM
        lda #15
        ldx DEVNUM
        ldy #15
        jsr K_SETLFS
        jsr K_OPEN
        bcs dst_fail
        ldx #15
        jsr K_CHKIN
        bcs dst_close
        jsr K_CHRIN
        sta dsa
        jsr K_CHRIN
        sta dsb
        ldx #64                 ; the rest of the line
dst1:   stx kidx
        jsr K_CHRIN
        ldx kidx
        cmp #$0d
        beq dst2
        dex
        bne dst1
dst2:   jsr K_CLRCHN
        lda #15
        jsr K_CLOSE
        lda dsa
        sec
        sbc #'0'
        cmp #10
        bcs dst_fail2
        sta dsa
        asl
        asl
        adc dsa                 ; tens * 5 ...
        asl                     ; ... * 2
        sta dsa
        lda dsb
        sec
        sbc #'0'
        cmp #10
        bcs dst_fail2
        clc
        adc dsa
        rts
dst_close:
        jsr K_CLRCHN
        lda #15
        jsr K_CLOSE
dst_fail:
        lda #$ff
        rts
dst_fail2:
        lda #$ff
        rts

; report a failure: A = status code from disk_status
disk_fail:
        cmp #62
        bne df1
        lda #<msg_notfound
        sta mp
        lda #>msg_notfound
        sta mp+1
        jmp print_line
df1:    lda #<msg_fileerr
        sta mp
        lda #>msg_fileerr
        sta mp+1
        jmp print_line

; --- byte I/O -----------------------------------------------------------------------------------
wbyte:  jsr K_CHROUT
        jsr K_READST
        beq wb1
        sec
        rts
wb1:    clc
        rts

; read one byte into A; carry set on an error or a read past the end of the file
rbyte:  lda eofseen
        bne rb_err
        jsr K_CHRIN
        pha
        jsr K_READST
        sta rbst
        and #$bf
        bne rb_bad
        lda rbst
        and #$40
        beq rb_ok
        sta eofseen
rb_ok:  pla
        clc
        rts
rb_bad: pla
rb_err: sec
        rts

; write wcnt bytes from ep; read wcnt bytes to ep (both advance ep)
wblock: lda wcnt
        ora wcnt+1
        beq wbl2
        ldy #0
        lda (ep),y
        jsr wbyte
        bcs wbl3
        inc ep
        bne wbl1
        inc ep+1
wbl1:   lda wcnt
        bne wbl1a
        dec wcnt+1
wbl1a:  dec wcnt
        jmp wblock
wbl2:   clc
wbl3:   rts

rblock: lda wcnt
        ora wcnt+1
        beq rbl2
        jsr rbyte
        bcs rbl3
        ldy #0
        sta (ep),y
        inc ep
        bne rbl1
        inc ep+1
rbl1:   lda wcnt
        bne rbl1a
        dec wcnt+1
rbl1a:  dec wcnt
        jmp rblock
rbl2:   clc
rbl3:   rts

; --- the file name --------------------------------------------------------------------------------
; The name argument (or, without one, the workspace name) -> WSNAME; carry set if there is none.
pick_name:
        ldx argx
        lda INBUF,x
        beq d_pn1
        jmp get_name
d_pn1:    lda WSNAME
        bne d_pn2
        sec
        rts
d_pn2:    clc
        rts

; FNBUF = prefix bytes (fnpre of them, at FNPFX) + the name + the suffix (4 bytes at fnsuf)
build_name:
        ldx #0
bn1:    cpx fnpre
        beq bn2
        lda FNPFX,x
        sta FNBUF,x
        inx
        jmp bn1
bn2:    ldy #0
bn3:    cpy WSNAME
        beq bn4
        lda WSNAME+1,y
        sta FNBUF,x
        inx
        iny
        jmp bn3
bn4:    ldy #0
bn5:    lda fnsuf,y
        sta FNBUF,x
        inx
        iny
        cpy #4
        bne bn5
        stx fnlen
        rts

; --- )SAVE [name] ------------------------------------------------------------------------------------
cmd_save:
        jsr pick_name
        bcs sv_badname
        lda #3                  ; "@0:" replaces an existing file
        sta fnpre
        lda #'@'
        sta FNPFX
        lda #'0'
        sta FNPFX+1
        lda #':'
        sta FNPFX+2
        lda #','
        sta fnsuf
        lda #'S'
        sta fnsuf+1
        lda #','
        sta fnsuf+2
        lda #'W'
        sta fnsuf+3
        jsr build_name
        jsr open_file
        bcs sv_fail
        ldx #LFN
        jsr K_CHKOUT
        bcs sv_close
        lda #0
        sta eofseen
        jsr save_body
        bcs sv_close
        jsr close_file
        jsr disk_status
        cmp #2                  ; 0 and 1 are fine
        bcs sv_dfail
        lda #<msg_saved
        sta mp
        lda #>msg_saved
        sta mp+1
        jmp print_line
sv_close:
        jsr close_file
sv_fail:
        jsr disk_status
sv_dfail:
        jmp disk_fail
sv_badname:
        lda #<msg_badname
        sta mp
        lda #>msg_badname
        sta mp+1
        jmp print_line

; write the workspace to the open channel; carry set on an I/O error
save_body:
        lda symcnt              ; count the defined variables
        sta vcnt2
        lda symcnt+1
        sta vcnt2+1
        lda #0
        sta nvars
        sta nvars+1
        lda #0
        sta svi
d_sb1:    lda vcnt2
        ora vcnt2+1
        beq d_sb3
        lda svi
        jsr varcell
        ldy #0
        lda (cptr),y
        cmp #$80
        beq d_sb2
        inc nvars
        bne d_sb2
        inc nvars+1
d_sb2:    inc svi
        lda vcnt2
        bne sb2a
        dec vcnt2+1
sb2a:   dec vcnt2
        jmp d_sb1
d_sb3:    ldx #0                  ; header
d_sb4:    lda wshead,x
        stx kidx
        jsr wbyte
        bcc *+5
        jmp sb_err
        ldx kidx
        inx
        cpx #5
        bne d_sb4
        lda nvars
        jsr wbyte
        bcc *+5
        jmp sb_err
        lda nvars+1
        jsr wbyte
        bcc *+5
        jmp sb_err
        lda #<SYMTAB
        sta sympp
        lda #>SYMTAB
        sta sympp+1
        lda symcnt
        sta vcnt2
        lda symcnt+1
        sta vcnt2+1
        lda #0
        sta svi
sb5:    lda vcnt2
        ora vcnt2+1
        beq sb9
        lda sympp
        sta mp
        lda sympp+1
        sta mp+1
        ldy #0
        lda (mp),y
        sta svl
        lda svi
        jsr varcell
        ldy #0
        lda (cptr),y
        cmp #$80
        beq sb7
        lda svl                 ; the name
        jsr wbyte
        bcs sb_err
        lda sympp
        sta ep
        lda sympp+1
        sta ep+1
        inc ep
        bne sb6
        inc ep+1
sb6:    lda svl
        sta wcnt
        lda #0
        sta wcnt+1
        jsr wblock
        bcs sb_err
        lda svi                 ; the value
        jsr varcell
        jsr save_value
        bcs sb_err
sb7:    lda sympp               ; on to the next symbol
        sta mp
        lda sympp+1
        sta mp+1
        ldy #0
        lda (mp),y
        sec
        adc sympp
        sta sympp
        bcc sb8
        inc sympp+1
sb8:    inc svi
        lda vcnt2
        bne sb8a
        dec vcnt2+1
sb8a:   dec vcnt2
        jmp sb5
sb9:    lda #'E'
        jmp wbyte
sb_err: sec
        rts

wshead: .text "APLW"
        .byte WS_VERSION

; the value in the cell at cptr
save_value:
        jsr getval
        lda vtag
        jsr wbyte
        bcs sv_e
        lda vrk
        bne sva
        ldx vt                  ; a scalar: its data bytes follow the tag in the cell
        lda WIDTHT,x
        sta wcnt
        lda #0
        sta wcnt+1
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        jmp wblock
sva:    lda vn                  ; an array: count, lengths, data
        jsr wbyte
        bcs sv_e
        lda vn+1
        jsr wbyte
        bcs sv_e
        lda vs0
        jsr wbyte
        bcs sv_e
        lda vs0+1
        jsr wbyte
        bcs sv_e
        lda vrk
        cmp #2
        bne svb
        lda vs1
        jsr wbyte
        bcs sv_e
        lda vs1+1
        jsr wbyte
        bcs sv_e
svb:    jsr bytecount
        lda bc
        sta wcnt
        lda bc+1
        sta wcnt+1
        lda vp
        sta ep
        lda vp+1
        sta ep+1
        jmp wblock
sv_e:   rts

; --- )LOAD [name] ------------------------------------------------------------------------------------
cmd_load:
        jsr pick_name
        bcc *+5
        jmp sv_badname
        lda #0
        sta fnpre
        lda #','
        sta fnsuf
        lda #'S'
        sta fnsuf+1
        lda #','
        sta fnsuf+2
        lda #'R'
        sta fnsuf+3
        jsr build_name
        jsr open_file
        bcs ld_fail
        jsr disk_status         ; a missing file shows only here
        cmp #0
        bne ld_dfail
        ldx #LFN
        jsr K_CHKIN
        bcs ld_closefail
        lda #0
        sta eofseen
        jsr load_body
        pha
        jsr close_file
        pla
        beq ld_ok
        cmp #1
        beq ld_notws
        cmp #2
        beq ld_wsfull
        jmp ld_ioerr
ld_ok:  lda #<msg_loaded
        sta mp
        lda #>msg_loaded
        sta mp+1
        jmp print_line
ld_notws:
        lda #<msg_notws
        sta mp
        lda #>msg_notws
        sta mp+1
        jmp print_line
ld_wsfull:
        lda #E_WSFULL
        jmp print_error
ld_ioerr:
        lda #255
        jmp disk_fail
ld_closefail:
        jsr close_file
ld_fail:
        jsr disk_status
ld_dfail:
        jmp disk_fail

; read the workspace from the open channel. A = 0 ok, 1 not a workspace, 2 WS FULL, 3 I/O error.
load_body:
        ldx #0
lb1:    stx kidx
        jsr rbyte
        bcc *+5
        jmp lb_io
        ldx kidx
        cmp wshead,x
        beq *+5
        jmp lb_notws
        inx
        cpx #5
        bne lb1
        jsr ws_clear            ; only a real workspace file replaces the workspace
        jsr rbyte
        bcc *+5
        jmp lb_io
        sta nvars
        jsr rbyte
        bcc *+5
        jmp lb_io
        sta nvars+1
lb2:    lda nvars
        ora nvars+1
        bne lb3
        jsr rbyte               ; the trailer
        bcc *+5
        jmp lb_io
        cmp #'E'
        beq *+5
        jmp lb_notws
        lda #0
        rts
lb3:    jsr rbyte               ; a name: length, characters
        bcc *+5
        jmp lb_io
        sta svl
        bne *+5
        jmp lb_notws
        lda #<INBUF
        sta ep
        lda #>INBUF
        sta ep+1
        lda svl
        sta wcnt
        lda #0
        sta wcnt+1
        jsr rblock
        bcc *+5
        jmp lb_io
        ldx svl
        lda #0
        sta INBUF,x
        jsr tokenize            ; the tokenizer makes the symbol; it must be exactly one name
        bcc *+5
        jmp lb_notws
        lda OUTBUF
        cmp #T_NAME
        beq *+5
        jmp lb_notws
        lda OUTBUF+2
        beq *+5
        jmp lb_notws
        lda OUTBUF+1
        sta svi
        jsr rbyte               ; the value: tag
        bcc *+5
        jmp lb_io
        sta ldtag
        and #3
        sta nt
        lda ldtag
        lsr
        lsr
        and #3
        sta nrk
        lda ldtag
        and #$f0                ; no other bits may be set
        beq *+5
        jmp lb_notws
        lda nrk
        cmp #3
        bcc *+5
        jmp lb_notws
        lda nrk
        bne lb_arr
        ldx nt                  ; a scalar: its bytes go into a cell
        lda WIDTHT,x
        sta wcnt
        lda #0
        sta wcnt+1
        lda ldtag
        sta cv
        lda #0
        sta cv+1
        sta cv+2
        sta cv+3
        lda #<(cv+1)
        sta ep
        lda #>(cv+1)
        sta ep+1
        jsr rblock
        bcc *+5
        jmp lb_io
        jmp lb_store
lb_arr: jsr rbyte               ; count, lengths
        bcc *+5
        jmp lb_io
        sta nn
        jsr rbyte
        bcc *+5
        jmp lb_io
        sta nn+1
        jsr rbyte
        bcc *+5
        jmp lb_io
        sta nd0
        jsr rbyte
        bcc *+5
        jmp lb_io
        sta nd0+1
        lda #0
        sta nd1
        sta nd1+1
        lda nrk
        cmp #2
        bne lb_a2
        jsr rbyte
        bcc *+5
        jmp lb_io
        sta nd1
        jsr rbyte
        bcc *+5
        jmp lb_io
        sta nd1+1
lb_a2:  lda nrk                 ; the count must agree with the lengths
        cmp #2
        beq lb_chk2
        lda nn
        cmp nd0
        beq *+5
        jmp lb_bad
        lda nn+1
        cmp nd0+1
        beq *+5
        jmp lb_bad
        jmp lb_chk3
lb_chk2:
        lda nd0
        sta p0
        lda nd0+1
        sta p1
        lda nd1
        sta bl
        lda nd1+1
        sta bh
        jsr mul16
        lda p2
        ora p3
        bne lb_bad
        lda p0
        cmp nn
        bne lb_bad
        lda p1
        cmp nn+1
        bne lb_bad
lb_chk3:
        jsr newarr
        bcs lb_full
        lda dp
        sta ep
        lda dp+1
        sta ep+1
        ldx nt
        lda WIDTHT,x
        sta lw
        lda nn
        sta wcnt
        lda nn+1
        sta wcnt+1
        lda lw
        cmp #2
        bcc lb_a3
        clc                     ; the byte count: count * width
        lda wcnt
        adc nn
        sta wcnt
        lda wcnt+1
        adc nn+1
        sta wcnt+1
        lda lw
        cmp #3
        bcc lb_a3
        clc
        lda wcnt
        adc nn
        sta wcnt
        lda wcnt+1
        adc nn+1
        sta wcnt+1
lb_a3:  jsr rblock
        bcs lb_io
lb_store:
        lda svi
        jsr varcell
        ldy #3
lb_s1:  lda cv,y
        sta (cptr),y
        dey
        bpl lb_s1
        lda nvars
        bne lb_s2
        dec nvars+1
lb_s2:  dec nvars
        jmp lb2
lb_notws:
lb_bad:
        lda #1
        rts
lb_full:
        lda #2
        rts
lb_io:  lda #3
        rts

; --- start-up value ---------------------------------------------------------------------------------------
disk_init:
        lda #8
        sta DEVNUM
        rts
