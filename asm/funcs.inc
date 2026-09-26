; User-defined functions. Spec: apl64.py (Func, Interp._begin_def, _def_line, call).
; Included by eval.asm.
;
; A function is a variable cell with tag $15 (a CHAR vector, plus $10 = function) whose block is
; the model's Func.to_bytes():
;   nargs, hasres, nsyms, nlines, then nsyms symbol numbers (result, left argument, right
;   argument, locals; the ones that exist), then for each line its size (2 bytes) and its tokens.
; While a function is being defined its block is the last one in the heap and each body line
; is appended in place (nothing else allocates then).

TAG_FN  = $10
DEL     = $98

hk      = WS+$b9                ; header parse: index of the first ';' (or the token count)
hres    = WS+$ba                ; there is a result name
hs      = WS+$bb                ; first token of the name part
hcnt    = WS+$bc                ; names in the name part
hfn     = WS+$bd                ; the function's symbol
hn      = WS+$be                ; symbols collected in SBUF

; --- one line, from the keyboard or a script ---------------------------------------------------
; INBUF holds the line. Carry clear: done; carry set: A = error code.
do_line:
        lda defmode
        beq dl_1
        jmp def_line
dl_1:   ldx #0
dl_2:   lda INBUF,x
        cmp #' '
        beq dl_3
        cmp #9
        bne dl_4
dl_3:   inx
        bne dl_2
dl_4:   cmp #DEL
        bne dl_5
        inx
        jmp begin_def
dl_5:   jsr tokenize
        bcc *+3
        rts
        jmp eval_line

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
bd_b:   lda hn                  ; the block: 4 + hn bytes
        clc
        adc #4
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
dfl_3:  cmp #DEL                ; a lone del ends the definition
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
dfl_b:  jsr tokenize
        bcc *+3
        rts
        sec                     ; the size of the token stream
        lda op
        sbc #<OUTBUF
        sta dtl
        lda op+1
        sbc #>OUTBUF
        sta dtl+1
        jsr mkindex
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
dfl_g:  clc                     ; room for the size and the tokens?
        lda dtl
        adc #2
        sta t0
        lda dtl+1
        adc #0
        sta t0+1
        clc
        lda htop
        adc t0
        sta cd
        lda htop+1
        adc t0+1
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
dfl_h:  ldy #0                  ; the size, then the tokens, go at the end of the heap
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
