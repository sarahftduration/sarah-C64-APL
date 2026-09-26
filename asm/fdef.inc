; The del editor: the header line of a definition and its body lines (an overlay, see overlay.inc).
; Entered from do_line (funcs.inc) through s_begin_def and s_def_line.

; --- the header line ---------------------------------------------------------------------------
; X = index in INBUF just after the del.
begin_def:
        ldy #0
bd_c:   lda INBUF,x
        sta INBUF,y
        beq bd_t
        inx
        iny
        jmp bd_c
bd_t:   jsr tokenize
        bcc *+3
        rts
        jsr mkindex
        ldx #0                  ; the first ';'
bd_k:   cpx ev_ntok
        beq bd_k1
        lda TC,x
        cmp #T_SEMI
        beq bd_k1
        inx
        jmp bd_k
bd_k1:  stx hk
        lda #0
        sta hres
        sta hs
        cpx #2
        bcc bd_h
        lda TC+1
        cmp #T_ASSIGN
        bne bd_h
        lda TC                  ; result name <-
        cmp #T_NAME
        bne bd_syn
        inc hres
        lda #2
        sta hs
bd_h:   lda hk                  ; one to three names
        sec
        sbc hs
        sta hcnt
        beq bd_syn
        cmp #4
        bcs bd_syn
        ldx hs
bd_n:   cpx hk
        beq bd_s
        lda TC,x
        cmp #T_NAME
        bne bd_syn
        inx
        jmp bd_n
bd_s:   lda #0                  ; the symbols to localise, in the order of Func.syms
        sta hn
        lda hres
        beq bd_s1
        ldx #0
        jsr addsym
bd_s1:  ldx hs
        lda hcnt
        cmp #3
        bne bd_s2
        jsr addsym              ; left argument
        inx
bd_s2:  jsr nameidx             ; the function name
        sta hfn
        lda hcnt
        cmp #1
        beq bd_l
        ldx hk                  ; right argument
        dex
        jsr addsym
bd_l:   ldx hk                  ; ;L1;L2...
bd_l1:  cpx ev_ntok
        beq bd_d
        lda TC,x
        cmp #T_SEMI
        bne bd_syn
        inx
        cpx ev_ntok
        beq bd_syn
        lda TC,x
        cmp #T_NAME
        bne bd_syn
        jsr addsym
        inx
        jmp bd_l1
bd_syn: lda #E_SYNTAX
        sec
        rts
bd_d:   ldx #0                  ; all names different, the function's too
bd_d1:  cpx hn
        beq bd_c2
        lda SBUF,x
        cmp hfn
        beq bd_syn
        txa
        tay
        iny
bd_d2:  cpy hn
        beq bd_d3
        lda SBUF,x
        cmp SBUF,y
        beq bd_syn
        iny
        jmp bd_d2
bd_d3:  inx
        jmp bd_d1
bd_c2:  lda hfn                 ; a variable of that name is in the way
        jsr varcell
        ldy #0
        lda (cptr),y
        cmp #$80
        beq bd_b
        and #TAG_FN
        beq bd_syn
bd_b:   lda hn                  ; the block: 5 + hn bytes
        clc
        adc #5
        sta nn
        sta nd0
        lda #0
        adc #0
        sta nn+1
        sta nd0+1
        lda #1
        sta nt
        sta nrk
        jsr newarr
        bcc *+3
        rts
        ldy #0
        lda hcnt
        sec
        sbc #1
        sta (dp),y
        iny
        lda hres
        sta (dp),y
        iny
        lda hn
        sta (dp),y
        iny
        lda #0
        sta (dp),y
        iny
        sta (dp),y              ; no labels yet
        ldx #0
bd_w:   cpx hn
        beq bd_v
        iny
        lda SBUF,x
        sta (dp),y
        inx
        jmp bd_w
bd_v:   lda hfn                 ; the variable is now this function
        jsr varcell
        lda cv
        ora #TAG_FN
        ldy #0
        sta (cptr),y
        iny
        lda cv+1
        sta (cptr),y
        sta defh
        iny
        lda #0
        sta (cptr),y
        iny
        sta (cptr),y
        lda hfn
        sta deffn
        lda #1
        sta defmode
        clc
        rts

; append the symbol of the name token X to SBUF
addsym: stx ev_ix
        jsr nameidx
        ldy hn
        sta SBUF,y
        inc hn
        ldx ev_ix
        rts

; --- body lines --------------------------------------------------------------------------------
def_line:
        ldx #0
dfl_1:  lda INBUF,x
        cmp #' '
        beq dfl_2
        cmp #9
        bne dfl_3
dfl_2:  inx
        bne dfl_1
dfl_3:  stx dfx
        cmp #DEL                ; a lone del ends the definition
        bne dfl_b
        inx
dfl_4:  lda INBUF,x
        beq dfl_e
        cmp #' '
        beq dfl_5
        cmp #9
        bne dfl_b
dfl_5:  inx
        jmp dfl_4
dfl_e:  lda #0
        sta defmode
        clc
        rts
dfl_b:  lda #0                  ; NAME: at the start is a label: the colon becomes a blank and the
        sta dlab                ; name is the line's first token
        ldx dfx
        lda INBUF,x
        jsr isalpha
        bcc dfl_t
dfl_l1: inx
        lda INBUF,x
        jsr isnamec
        bcs dfl_l1
        lda INBUF,x
        cmp #':'
        bne dfl_t
        lda #' '
        sta INBUF,x
        inc dlab
dfl_t:  jsr tokenize
        bcc *+3
        rts
        sec                     ; the size of the token stream
        lda op
        sbc #<OUTBUF
        sta dtl
        lda op+1
        sbc #>OUTBUF
        sta dtl+1
        lda dlab
        beq dfl_nl
        ldx defh                ; the label must be a new name
        lda HTL,x
        sta gp
        lda HTH,x
        sta gp+1
        lda OUTBUF+1
        sta dlsym
        cmp deffn
        beq dfl_ls
        ldy #7
        lda (gp),y
        tax
        ldy #10
dfl_l3: dex
        bmi dfl_l4
        lda (gp),y
        cmp OUTBUF+1
        beq dfl_ls
        iny
        bne dfl_l3
dfl_l4: ldy #7                  ; (at most 98 symbols and labels)
        lda (gp),y
        cmp #99
        bcc dfl_l5
        lda #E_LIMIT
        sec
        rts
dfl_l5: lda #<(OUTBUF+2)        ; take the label off the front of the tokens
        sta cs
        lda #>(OUTBUF+2)
        sta cs+1
        lda #<OUTBUF
        sta cd
        lda #>OUTBUF
        sta cd+1
        sec
        lda dtl
        sbc #2
        sta dtl
        sta t0
        lda dtl+1
        sbc #0
        sta dtl+1
        sta t0+1
        jsr memcpy_cs_cd
        jmp dfl_nl
dfl_ls: lda #E_SYNTAX
        sec
        rts
dfl_nl: jsr mkindex
        jsr balance
        bcc *+3
        rts
        ldx defh
        lda HTL,x
        sta gp
        lda HTH,x
        sta gp+1
        ldy #8                  ; at most 255 lines
        lda (gp),y
        cmp #255
        bne dfl_g
        lda #E_LIMIT
        sec
        rts
dfl_g:  clc                     ; room for the size and the tokens (and the label)?
        lda dtl
        adc #2
        sta t0
        lda dtl+1
        adc #0
        sta t0+1
        lda dlab
        asl
        clc
        adc t0
        sta cd
        lda t0+1
        adc #0
        sta cd+1
        clc
        lda htop
        adc cd
        sta cd
        lda htop+1
        adc cd+1
        sta cd+1
        bcs dfl_f
        lda #<HEAP_LIMIT
        cmp cd
        lda #>HEAP_LIMIT
        sbc cd+1
        bcs dfl_h
dfl_f:  lda #E_WSFULL
        sec
        rts
dfl_h:  lda dlab
        beq dfl_i
        jsr add_label
        clc                     ; (it used t0)
        lda dtl
        adc #2
        sta t0
        lda dtl+1
        adc #0
        sta t0+1
dfl_i:  ldy #0                  ; the size, then the tokens, go at the end of the heap
        lda dtl
        sta (htop),y
        iny
        lda dtl+1
        sta (htop),y
        ldy #1                  ; count and dimension grow by the same amount
        clc
        lda (gp),y
        adc t0
        sta (gp),y
        ldy #3
        sta (gp),y
        ldy #2
        lda (gp),y
        adc t0+1
        sta (gp),y
        ldy #4
        sta (gp),y
        ldy #8
        lda (gp),y
        clc
        adc #1
        sta (gp),y
        clc
        lda htop
        adc #2
        sta cd
        lda htop+1
        adc #0
        sta cd+1
        lda #<OUTBUF
        sta cs
        lda #>OUTBUF
        sta cs+1
        lda dtl
        sta t0
        lda dtl+1
        sta t0+1
        clc
        lda htop
        adc dtl
        pha
        lda htop+1
        adc dtl+1
        pha
        jsr memcpy_cs_cd
        pla
        sta htop+1
        pla
        sta htop
        clc
        lda htop
        adc #2
        sta htop
        bcc *+4
        inc htop+1
        clc
        rts

; The label whose symbol is OUTBUF+1 names the line about to be added. The label symbols end the
; symbol list and the line numbers of the labels follow it, so both grow by a byte and the
; lines move up by two. gp = the block. (Fewer than 99 symbols, checked by the caller.)
add_label:
        clc                     ; tp = the data
        lda gp
        adc #5
        sta tp
        lda gp+1
        adc #0
        sta tp+1
        ldy #2
        lda (tp),y
        sta cu_n                ; symbols
        ldy #4
        lda (tp),y
        sta cu_i                ; labels
        lda cu_n                ; gsrc = the label table (Ts), gdst = the first line (Ls)
        clc
        adc #5
        adc tp
        sta gsrc
        lda tp+1
        adc #0
        sta gsrc+1
        clc
        lda gsrc
        adc cu_i
        sta gdst
        lda gsrc+1
        adc #0
        sta gdst+1
        sec                     ; the lines, htop - Ls bytes, move up by two
        lda htop
        sbc gdst
        sta t0
        lda htop+1
        sbc gdst+1
        sta t0+1
        lda htop
        sta cs
        lda htop+1
        sta cs+1
        clc
        lda htop
        adc #2
        sta cd
        lda htop+1
        adc #0
        sta cd+1
        jsr memcpy_dn
        lda gdst                ; the table moves up by one
        sta cs
        lda gdst+1
        sta cs+1
        clc
        lda gdst
        adc #1
        sta cd
        lda gdst+1
        adc #0
        sta cd+1
        lda cu_i
        sta t0
        lda #0
        sta t0+1
        jsr memcpy_dn
        ldy #0                  ; the symbol goes where the table began
        lda dlsym
        sta (gsrc),y
        ldy #3                  ; and the line number, the number of the line to come, at its end
        lda (tp),y
        clc
        adc #1
        ldy #1
        sta (gdst),y
        ldy #2                  ; one more symbol, one more label
        lda (tp),y
        clc
        adc #1
        sta (tp),y
        ldy #4
        lda (tp),y
        clc
        adc #1
        sta (tp),y
        ldy #1                  ; the count and the dimension grow by two
        clc
        lda (gp),y
        adc #2
        sta (gp),y
        ldy #3
        sta (gp),y
        ldy #2
        lda (gp),y
        adc #0
        sta (gp),y
        ldy #4
        sta (gp),y
        clc
        lda htop
        adc #2
        sta htop
        bcc *+4
        inc htop+1
        rts

; copy t0 bytes downward: from the bytes ending just below cs to the bytes ending just below cd
memcpy_dn:
        lda t0
        ora t0+1
        beq md_r
        lda cs
        bne md_1
        dec cs+1
md_1:   dec cs
        lda cd
        bne md_2
        dec cd+1
md_2:   dec cd
        ldy #0
        lda (cs),y
        sta (cd),y
        lda t0
        bne md_3
        dec t0+1
md_3:   dec t0
        jmp memcpy_dn
md_r:   rts

; ->v in a function (the value is on the value stack): the first element is the number of the next
; line; an empty v goes on with the next statement; 0 or a number outside the lines leaves.
