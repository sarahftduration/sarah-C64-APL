; System commands: a line whose first non-blank character is ')' . Spec: DESIGN.md, System commands.
;
; Names are case-insensitive. The REPL calls syscmd with X = the index of the ')' in INBUF
; (the line is zero-terminated); the command prints its result and returns.

CMDMAX  = 10

syscmd:
        inx
        ldy #0
sc1:    lda INBUF,x
        beq sc3
        cmp #' '
        beq sc3
        cmp #$61                ; fold lower case
        bcc sc2
        cmp #$7b
        bcs sc2
        sec
        sbc #$20
sc2:    cpy #CMDMAX
        bcs sc_bad
        sta CMDBUF,y
        iny
        inx
        jmp sc1
sc3:    lda #0
        sta CMDBUF,y
sc4:    lda INBUF,x             ; the argument starts at the next non-blank
        cmp #' '
        bne sc5
        inx
        jmp sc4
sc5:    stx argx
        ldx #0                  ; find the command in the table
sc6:    lda cmdtab,x
        beq sc_bad
        ldy #0
sc7:    lda CMDBUF,y
        cmp cmdtab,x
        bne sc9
        cmp #0
        beq sc8
        inx
        iny
        jmp sc7
sc8:    lda cmdtab+1,x          ; found: its handler follows the name
        sta mp
        lda cmdtab+2,x
        sta mp+1
        jmp (mp)
sc9:    lda cmdtab,x            ; skip to the end of this entry
        beq sc10
        inx
        jmp sc9
sc10:   inx
        inx
        inx
        jmp sc6
sc_bad: lda #<msg_badcmd
        sta mp
        lda #>msg_badcmd
        sta mp+1
        jmp print_line

cmdtab: .text "VARS"
        .byte 0
        .word cmd_vars
        .text "ERASE"
        .byte 0
        .word cmd_erase
        .text "CLEAR"
        .byte 0
        .word cmd_clear
        .text "FREE"
        .byte 0
        .word cmd_free
        .text "WSID"
        .byte 0
        .word cmd_wsid
        .text "OFF"
        .byte 0
        .word cmd_off
        .byte 0

msg_badcmd: .text "BAD COMMAND"
        .byte 0
msg_clear: .text "CLEAR WS"
        .byte 0
msg_free: .text " BYTES FREE"
        .byte 0
msg_badname: .text "BAD NAME"
        .byte 0

; print the string at mp and a newline
print_line:
        jsr print_z
        lda #CHNL
        jmp scr_put

; print ftmp as a decimal number
print_dec16:
        jsr dec16
        ldx fnI
        stx fdi
pd1:    dec fdi
        ldx fdi
        lda fdt,x
        ora #'0'
        jsr scr_put
        lda fdi
        bne pd1
        rts

; --- )CLEAR ---------------------------------------------------------------------------------
ws_clear:
        jsr heap_init
        jsr tok_init
        lda #0
        sta WSNAME
        rts

cmd_clear:
        jsr ws_clear
        lda #<msg_clear
        sta mp
        lda #>msg_clear
        sta mp+1
        jmp print_line

; --- )FREE: heap bytes free after a collection --------------------------------------------------
cmd_free:
        lda #0                  ; nothing is in flight: release the pinned handle
        sta hpinf
        jsr gc
        sec
        lda #<HEAP_LIMIT
        sbc htop
        sta ftmp
        lda #>HEAP_LIMIT
        sbc htop+1
        sta ftmp+1
        jsr print_dec16
        lda #<msg_free
        sta mp
        lda #>msg_free
        sta mp+1
        jmp print_line

; --- )OFF: reset the machine ----------------------------------------------------------------------
cmd_off:
        sei
        ldx #$ff
        txs
        jmp ($fffc)

; --- )WSID [name] ------------------------------------------------------------------------------------
; the workspace name: a length byte and up to 16 upper-case characters
cmd_wsid:
        ldx argx
        lda INBUF,x
        bne wsid_set
        lda WSNAME
        bne wsid_show
        lda #<msg_clear
        sta mp
        lda #>msg_clear
        sta mp+1
        jmp print_line
wsid_show:
        ldx #0
ws1:    stx kidx
        lda WSNAME+1,x
        jsr scr_put
        ldx kidx
        inx
        cpx WSNAME
        bne ws1
        lda #CHNL
        jmp scr_put
wsid_set:
        jsr get_name
        bcs wsid_bad
        rts
wsid_bad:
        lda #<msg_badname
        sta mp
        lda #>msg_badname
        sta mp+1
        jmp print_line

; read the name argument at argx into WSNAME: 1-16 of A-Z 0-9 - . (lower case folded).
; Carry set if it is not a valid name.
get_name:
        ldx argx
        ldy #0
gn1:    lda INBUF,x
        beq gn4
        cmp #' '
        beq gn4
        cmp #$61
        bcc gn2
        cmp #$7b
        bcs gn2
        sec
        sbc #$20
gn2:    cmp #'-'
        beq gn3
        cmp #'.'
        beq gn3
        cmp #'0'
        bcc gn_bad
        cmp #'9'+1
        bcc gn3
        cmp #'A'
        bcc gn_bad
        cmp #'Z'+1
        bcs gn_bad
gn3:    cpy #16
        bcs gn_bad
        sta WSNAME+1,y
        iny
        inx
        jmp gn1
gn4:    cpy #0
        beq gn_bad
        sty WSNAME
        clc
        rts
gn_bad: sec
        rts

; --- )ERASE names: undefine variables ------------------------------------------------------------------
; The argument is tokenized as APL, so it must be names only.
cmd_erase:
        ldx argx
        ldy #0
ce1:    lda INBUF,x             ; move the argument to the start of INBUF for the tokenizer
        sta INBUF,y
        beq ce2
        inx
        iny
        jmp ce1
ce2:    jsr tokenize
        bcc ce3
        jmp print_error
ce3:    ldx #0                  ; every token must be a name
ce4:    lda OUTBUF,x
        beq ce6
        cmp #T_NAME
        bne ce_bad
        inx
        inx
        jmp ce4
ce_bad: jmp sc_bad
ce6:    ldx #0                  ; undefine them
ce7:    lda OUTBUF,x
        beq ce8
        inx
        lda OUTBUF,x
        stx kidx
        jsr varcell
        ldy #0
        lda #$80
        sta (cptr),y
        ldx kidx
        inx
        jmp ce7
ce8:    rts

; --- )VARS: the defined variables, sorted, wrapped to the screen ------------------------------------------
; SBUF gets the address of each symbol, OUTBUF a list of the defined ones.
cmd_vars:
        lda #<SYMTAB
        sta mp
        lda #>SYMTAB
        sta mp+1
        lda symcnt
        sta svcnt
        lda symcnt+1
        sta svcnt+1
        ldx #0
cv1:    lda svcnt
        ora svcnt+1
        beq cv2
        lda mp
        sta SBUF,x
        lda mp+1
        sta SBUF+256,x
        ldy #0
        lda (mp),y
        sec
        adc mp
        sta mp
        bcc cv1a
        inc mp+1
cv1a:   lda svcnt
        bne cv1b
        dec svcnt+1
cv1b:   dec svcnt
        inx
        jmp cv1
cv2:    lda symcnt              ; which symbols are variables
        sta svcnt
        lda symcnt+1
        sta svcnt+1
        lda #0
        sta svnv
        ldx #0
cv3:    lda svcnt
        ora svcnt+1
        beq cv5
        stx kidx
        txa
        jsr varcell
        ldy #0
        lda (cptr),y
        cmp #$80
        beq cv4
        ldx svnv
        lda kidx
        sta OUTBUF,x
        inc svnv
cv4:    ldx kidx
        inx
        lda svcnt
        bne cv4a
        dec svcnt+1
cv4a:   dec svcnt
        jmp cv3
cv5:    lda svnv
        cmp #2
        bcc cv9                 ; nothing to sort
        ldx #1                  ; insertion sort by name
cv6:    stx svj
        lda OUTBUF,x
        sta svkey
        dex
cv7:    stx svk
        lda OUTBUF,x
        jsr namecmp             ; carry set: name(OUTBUF[k]) > name(key)
        ldx svk
        bcc cv8
        lda OUTBUF,x
        sta OUTBUF+1,x
        dex
        cpx #$ff                ; (not bpl: indexes above 127 are valid)
        bne cv7
cv8:    inx
        lda svkey
        sta OUTBUF,x
        ldx svj
        inx
        cpx svnv
        bcc cv6
cv9:    lda svnv                  ; print
        beq cv_done
        ldx #0
cv10:   stx svj
        lda OUTBUF,x
        tax
        lda SBUF,x
        sta mp
        lda SBUF+256,x
        sta mp+1
        ldy #0
        lda (mp),y
        sta svl
        lda scr_col
        beq cv12                ; at the start of a line: no separator
        lda svl
        cmp #40
        bcs cv11
        clc
        adc scr_col
        adc #1
        cmp #41
        bcs cv11
        lda #' '
        jsr scr_put
        jmp cv12
cv11:   lda #CHNL
        jsr scr_put
cv12:   inc mp
        bne cv13
        inc mp+1
cv13:   lda #0
        sta svm
cv14:   lda svm
        cmp svl
        beq cv15
        ldy #0
        lda (mp),y
        jsr scr_put
        inc mp
        bne cv14a
        inc mp+1
cv14a:  inc svm
        jmp cv14
cv15:   ldx svj
        inx
        cpx svnv
        bcc cv10
        lda #CHNL
        jsr scr_put
cv_done:
        rts

; carry set if the name of symbol A sorts after the name of symbol svkey
namecmp:
        tax
        lda SBUF,x
        sta cs
        lda SBUF+256,x
        sta cs+1
        ldx svkey
        lda SBUF,x
        sta cd
        lda SBUF+256,x
        sta cd+1
        ldy #0
        lda (cs),y
        sta svla
        lda (cd),y
        sta svlb
        cmp svla
        bcc nc1
        lda svla
nc1:    sta svlm                  ; the shorter length
        ldy #1
nc2:    lda svlm
        beq nc4
        lda (cs),y
        cmp (cd),y
        bne nc3
        iny
        dec svlm
        jmp nc2
nc3:    rts                     ; carry from the comparison
nc4:    lda svla
        cmp svlb
        rts
