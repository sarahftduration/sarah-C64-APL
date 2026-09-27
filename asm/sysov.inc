; System command handlers: an overlay (see overlay.inc). syscmd.inc holds the parser, the command table
; and the helpers the disk commands share; each handler is entered through the table with its overlay
; loaded, and returns to the REPL. Spec: DESIGN.md, System commands.

msg_clear: .text "CLEAR WS"
        .byte 0
msg_free: .text " BYTES FREE"
        .byte 0

cmd_clear:
        jsr ws_clear
        lda #0
        sta WSNAME
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
; SBUF gets the address of each symbol, OUTBUF a list of the defined ones. )FNS lists the functions.
cmd_fns:
        lda #TAG_FN
        bne cmd_list
cmd_vars:
        lda #0
cmd_list:
        sta lsmode
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
        and #TAG_FN             ; 0: a variable, TAG_FN: a function
        cmp lsmode
        bne cv4
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

; --- )SEED n: the random number generator's state from n (0 to 65535); apl64.py rng_seed -------------------------------
sk_n:   .word 0
sk_2:   .word 0
sk_d:   .byte 0
cmd_seed:
        ldx argx
        lda INBUF,x
        bne sk_st
        jmp sk_bad
sk_st:  lda #0
        sta sk_n
        sta sk_n+1
sk_l:   lda INBUF,x
        beq sk_done
        cmp #' '
        beq sk_done
        sec
        sbc #'0'
        cmp #10
        bcs sk_bad
        sta sk_d
        lda sk_n                ; n = n * 10 + digit (over 65535 is a bad command)
        sta sk_2
        lda sk_n+1
        sta sk_2+1
        asl sk_n
        rol sk_n+1
        bcs sk_bad
        asl sk_n
        rol sk_n+1
        bcs sk_bad
        asl sk_n
        rol sk_n+1
        bcs sk_bad
        asl sk_2
        rol sk_2+1
        clc
        lda sk_n
        adc sk_2
        sta sk_n
        lda sk_n+1
        adc sk_2+1
        sta sk_n+1
        bcs sk_bad
        clc
        lda sk_n
        adc sk_d
        sta sk_n
        bcc sk_c
        inc sk_n+1
        beq sk_bad
sk_c:   inx
        jmp sk_l
sk_done: lda sk_n               ; the state: n in the high half, n xor $5A5A with the low bit set in the low half
        sta rnd_state+2
        eor #$5a
        ora #1
        sta rnd_state
        lda sk_n+1
        sta rnd_state+3
        eor #$5a
        sta rnd_state+1
        rts
sk_bad: jmp sc_bad
