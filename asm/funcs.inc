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

; --- calls -------------------------------------------------------------------------------------
; The evaluator applies a user-defined function like any other: the operands are on the value
; stack (dyadic: left on top, right below). udf_mon/udf_dy/udf_ni are entered with ev_us = the
; function's symbol and never return: they save the state of the calling line in a heap block
; (the context: NCTX bytes of registers, the evaluator's frames, the line's tokens), push a
; record on the value stack (the context's cell, then the old values of the localised names)
; and go on with the function's lines. When the last line is done, udf_return puts everything
; back, replaces the operands by the result and carries on where the call was made. The
; hardware stack gets deeper by one return address per nested call, no more. An error leaves
; through the ordinary error returns; eval_line then calls unwind.
;
; A name whose function takes arguments is a T_FN token in the line (classify), so a name is a
; value or a function without looking at anything else.

NCTX    = 17
ctx_tab: .word ev_lo, ev_i1, ev_fsp, ev_slo, ev_shi, ev_ntok, ev_na, ev_pkind, ev_pfn
        .word ev_tok, ev_pg, ev_rm, ev_no, cfh, cln, ev_tl, ev_tl+1

; tp = the address of context variable number X/2
ctxptr: lda ctx_tab,x
        sta tp
        lda ctx_tab+1,x
        sta tp+1
        rts

; sp = the data of the block with handle cu_h
fnptr:  ldx cu_h
        lda HTL,x
        clc
        adc #5
        sta sp
        lda HTH,x
        adc #0
        sta sp+1
        rts

; A = index into the symbols of the function at sp -> A = the symbol
symat:  clc
        adc #4
        tay
        lda (sp),y
        rts

udf_ni: pla                     ; pushname was called from opnd: the call replaces it
        pla
        lda #0
        sta ev_no
        lda #1
        sta ev_rm
        jmp udf_call
udf_mon:
        lda #1
        sta ev_no
        lda #0
        sta ev_rm
        jmp udf_call
udf_dy: lda #2
        sta ev_no
        lda #0
        sta ev_rm

udf_call:
        lda ev_us
        jsr varcell
        ldy #1
        lda (cptr),y
        sta cu_h
        jsr fnptr
        ldy #0
        lda (sp),y              ; the parameters must fit the operands
        cmp ev_no
        bcc uc_syn
        ldx ev_no
        bne uc_1
        cmp #0
        bne uc_syn
uc_1:   lda cdepth
        cmp #16
        bcs uc_lim
        ldy #2                  ; room on the value stack for the record?
        lda (sp),y
        cmp #100
        bcs uc_lim
        clc
        adc #1
        sta t0
        lda #0
        sta t0+1
        asl t0
        rol t0+1
        asl t0
        rol t0+1
        clc
        lda vsp
        adc t0
        lda vsp+1
        adc t0+1
        cmp #>VSTACK_END
        bcs uc_lim
        lda ev_fsp              ; the context: NCTX + 4 * frames + the line's tokens
        sta t0
        lda #0
        sta t0+1
        asl t0
        rol t0+1
        asl t0
        rol t0+1
        clc
        lda t0
        adc ev_tl
        sta nn
        lda t0+1
        adc ev_tl+1
        sta nn+1
        clc
        lda nn
        adc #NCTX
        sta nn
        bcc uc_2
        inc nn+1
uc_2:   lda nn
        sta nd0
        lda nn+1
        sta nd0+1
        lda #1
        sta nt
        sta nrk
        jsr newarr
        bcc uc_3
        rts
uc_syn: lda #E_SYNTAX
        sec
        rts
uc_lim: lda #E_LIMIT
        sec
        rts
uc_3:   lda #0                  ; save the registers, the frames and the tokens
        sta cu_i
uc_4:   lda cu_i
        asl
        tax
        jsr ctxptr
        ldy #0
        lda (tp),y
        ldy cu_i
        sta (dp),y
        inc cu_i
        lda cu_i
        cmp #NCTX
        bne uc_4
        jsr ctx_adv
        lda #0
        sta cu_m
        jsr ctx_fr
        lda #<OUTBUF
        sta cs
        lda #>OUTBUF
        sta cs+1
        lda dp
        sta cd
        lda dp+1
        sta cd+1
        lda ev_tl
        sta t0
        lda ev_tl+1
        sta t0+1
        jsr memcpy_cs_cd
        lda vsp                 ; the record: the context's cell first
        sta cu_r
        lda vsp+1
        sta cu_r+1
        jsr pushcv
        ldx cdepth
        lda cu_r
        sta CSL,x
        lda cu_r+1
        sta CSH,x
        lda cu_h
        sta CSF,x
        inc cdepth
        jsr fnptr               ; (the collector may have moved the function)
        ldy #2                  ; then the old values of the names it localises
        lda (sp),y
        sta cu_n
        lda #0
        sta cu_i
uc_5:   lda cu_i
        cmp cu_n
        beq uc_6
        jsr symat
        jsr varcell
        ldy #3
uc_7:   lda (cptr),y
        sta cv,y
        dey
        bpl uc_7
        lda #$80
        ldy #0
        sta (cptr),y
        jsr pushcv
        inc cu_i
        jmp uc_5
uc_6:   ldy #1                  ; the operands become the arguments
        lda (sp),y
        sta cu_p
        ldy #0
        lda (sp),y
        sta cu_na
        lda ev_no
        beq uc_9
        lda cu_p
        ldx cu_na
        cpx #2
        bne uc_8
        clc
        adc #1
uc_8:   jsr symat               ; the right argument
        jsr varcell
        lda #4
        ldx ev_no
        cpx #1
        beq uc_a
        lda #8
uc_a:   jsr cellfrom
        lda ev_no
        cmp #2
        bne uc_9
        lda cu_p                ; the left argument
        jsr symat
        jsr varcell
        lda #4
        jsr cellfrom
uc_9:   lda cu_h
        sta cfh
        lda #0
        sta cln
        ; falls into fn_nextline

; run the next line of the running function, or return
fn_nextline:
        ldx cfh
        lda HTL,x
        sta gp
        lda HTH,x
        sta gp+1
        ldy #8
        lda cln
        cmp (gp),y
        bcc fl_1
        jmp udf_return
fl_1:   ldy #7                  ; the lines start after the symbols
        lda (gp),y
        clc
        adc #9
        adc gp
        sta cs
        lda gp+1
        adc #0
        sta cs+1
        lda cln
        sta cu_i
fl_2:   lda cu_i                ; skip the lines before this one
        beq fl_3
        ldy #0
        lda (cs),y
        sta t0
        iny
        lda (cs),y
        sta t0+1
        clc
        lda cs
        adc t0
        sta cs
        lda cs+1
        adc t0+1
        sta cs+1
        jsr cs_2
        dec cu_i
        jmp fl_2
fl_3:   ldy #0
        lda (cs),y
        sta t0
        iny
        lda (cs),y
        sta t0+1
        jsr cs_2
        lda #<OUTBUF
        sta cd
        lda #>OUTBUF
        sta cd+1
        jsr memcpy_cs_cd
        inc cln
        jsr mkindex
        jmp elb0

cs_2:   clc
        lda cs
        adc #2
        sta cs
        bcc *+4
        inc cs+1
        rts

; dp += NCTX
ctx_adv:
        clc
        lda dp
        adc #NCTX
        sta dp
        bcc *+4
        inc dp+1
        rts

; copy the evaluator's frames (ev_fsp of each of the four arrays) to (cu_m = 0) or from
; (cu_m = 1) the context at dp, which advances past them
ctx_fr: lda #<FSTK
        sta tp
        lda #>FSTK
        sta tp+1
        lda #4
        sta cu_a
cf_1:   ldy #0
cf_2:   cpy ev_fsp
        beq cf_4
        lda cu_m
        bne cf_3
        lda (tp),y
        sta (dp),y
        jmp cf_5
cf_3:   lda (dp),y
        sta (tp),y
cf_5:   iny
        jmp cf_2
cf_4:   clc
        lda dp
        adc ev_fsp
        sta dp
        bcc *+4
        inc dp+1
        clc
        lda tp
        adc #$80
        sta tp
        bcc *+4
        inc tp+1
        dec cu_a
        bne cf_1
        rts

; copy the cell A bytes below the record (cu_r) into the cell at cptr
cellfrom:
        sta t0
        sec
        lda cu_r
        sbc t0
        sta cs
        lda cu_r+1
        sbc #0
        sta cs+1
        ldy #3
cfr_1:  lda (cs),y
        sta (cptr),y
        dey
        bpl cfr_1
        rts

; the running function has done its last line
udf_return:
        ldx cfh
        lda HTL,x
        sta gp
        lda HTH,x
        sta gp+1
        lda #1                  ; (no value unless there is a result)
        sta ev_nv
        ldy #6
        lda (gp),y
        beq ur_1
        ldy #9                  ; the result name's value, before the names are given back
        lda (gp),y
        jsr varcell
        ldy #0
        lda (cptr),y
        cmp #$80
        bne ur_2
        lda #E_VALUE
        sec
        rts
ur_2:   ldy #3
ur_3:   lda (cptr),y
        sta cv,y
        dey
        bpl ur_3
        lda #0
        sta ev_nv
ur_1:   ldx cdepth
        dex
        jsr restore_locals
        dec cdepth
        ldx cdepth
        lda CSL,x
        sta cu_r
        sta cptr
        lda CSH,x
        sta cu_r+1
        sta cptr+1
        ldy #1                  ; the context block
        lda (cptr),y
        tax
        lda HTL,x
        clc
        adc #5
        sta dp
        lda HTH,x
        adc #0
        sta dp+1
        lda #0                  ; the registers
        sta cu_i
ur_4:   lda cu_i
        asl
        tax
        jsr ctxptr
        ldy cu_i
        lda (dp),y
        ldy #0
        sta (tp),y
        inc cu_i
        lda cu_i
        cmp #NCTX
        bne ur_4
        jsr ctx_adv
        lda #1                  ; the frames
        sta cu_m
        jsr ctx_fr
        lda dp                  ; the tokens
        sta cs
        lda dp+1
        sta cs+1
        lda #<OUTBUF
        sta cd
        lda #>OUTBUF
        sta cd+1
        lda ev_tl
        sta t0
        lda ev_tl+1
        sta t0+1
        jsr memcpy_cs_cd
        jsr mkindex
        lda ev_no               ; the operands and the record go
        asl
        asl
        sta t0
        sec
        lda cu_r
        sbc t0
        sta vsp
        lda cu_r+1
        sbc #0
        sta vsp+1
        lda ev_nv
        bne ur_5
        jsr pushcv              ; the result takes their place
        jmp ur_6
ur_5:   lda ev_i1               ; no result: only allowed to end a statement
        sec
        sbc ev_rm
        cmp ev_lo
        bne ur_7
        lda ev_fsp
        bne ur_7
        lda ev_rm               ; an operand also needs that nothing is waiting for it
        beq ur_6
        lda ev_pkind
        beq ur_6
ur_7:   lda #E_VALUE
        sec
        rts
ur_6:   lda ev_rm
        beq ur_8
        dec ev_i1
        jmp cont                ; as after an operand was pushed
ur_8:   jmp evloop

; X = call depth index: the names of the call get their old values back
restore_locals:
        lda CSL,x
        sta cs
        lda CSH,x
        sta cs+1
        lda CSF,x
        tax
        lda HTL,x
        clc
        adc #5
        sta sp
        lda HTH,x
        adc #0
        sta sp+1
        ldy #2
        lda (sp),y
        sta cu_n
        lda #0
        sta cu_i
rs_1:   lda cu_i
        cmp cu_n
        beq rs_2
        jsr symat
        jsr varcell
        clc
        lda cs
        adc #4
        sta cs
        bcc *+4
        inc cs+1
        ldy #3
rs_3:   lda (cs),y
        sta (cptr),y
        dey
        bpl rs_3
        inc cu_i
        jmp rs_1
rs_2:   rts

; after an error: every call still open gives its names back
unwind: ldx cdepth
un_1:   beq un_2
        dex
        txa
        pha
        jsr restore_locals
        pla
        tax
        jmp un_1
un_2:   lda #0
        sta cdepth
        sta cfh
        rts

; T_NAME tokens that name a function taking arguments become T_FN
classify:
        ldx #0
cl_1:   cpx ev_ntok
        beq cl_3
        lda TC,x
        cmp #T_NAME
        bne cl_2
        jsr nameidx
        jsr varcell
        ldy #0
        lda (cptr),y
        and #TAG_FN
        beq cl_2
        iny
        lda (cptr),y
        stx ev_ix
        tax
        lda HTL,x
        sta gp
        lda HTH,x
        sta gp+1
        ldx ev_ix
        ldy #5
        lda (gp),y              ; the function's parameters
        beq cl_2
        lda #T_FN
        sta TC,x
        lda TIL,x
        sta gp
        lda TIH,x
        sta gp+1
        ldy #0
        lda #T_FN
        sta (gp),y
cl_2:   inx
        jmp cl_1
cl_3:   rts

; --- checking the functions of a loaded workspace ------------------------------------------------------
; Spec: tools/wsfile.py function_valid. Carry set: some function is not well formed.
fc_e    = WS+$b9                ; (2) bytes of the block not yet looked at
fc_l    = WS+$bb                ; (2) bytes of the line not yet looked at
fc_t    = WS+$bd                ; tokens in the line
fc_nl   = WS+$be                ; lines still to check
fc_w    = WS+$bf                ; (2) size of the literal being looked at

fn_check:
        lda #0
        sta cu_i
fk_1:   lda symcnt+1            ; symbol number cu_i (the workspace has at most 256)
        bne fk_2
        lda cu_i
        cmp symcnt
        bcs fk_ok
fk_2:   lda cu_i
        jsr varcell
        ldy #0
        lda (cptr),y
        and #TAG_FN
        beq fk_3
        iny
        lda (cptr),y
        sta cu_h
        jsr fk_one
        bcs fk_bad
fk_3:   inc cu_i
        bne fk_1
fk_ok:  clc
        rts
fk_bad: sec
        rts

; the function with handle cu_h
fk_one: jsr fnptr               ; sp = its data
        ldx cu_h
        lda HTL,x
        sta gp
        lda HTH,x
        sta gp+1
        ldy #1                  ; the size of the data
        lda (gp),y
        sta fc_e
        iny
        lda (gp),y
        sta fc_e+1
        bne fo_1
        lda fc_e
        cmp #4
        bcs *+5
        jmp fo_bad
fo_1:   ldy #0
        lda (sp),y              ; parameters: 0-2
        cmp #3
        bcc *+5
        jmp fo_bad
        sta t0
        ldy #1                  ; result: 0 or 1
        lda (sp),y
        cmp #2
        bcc *+5
        jmp fo_bad
        clc
        adc t0
        ldy #2                  ; at least as many symbols as names in the header
        cmp (sp),y
        beq fo_2
        bcc *+5
        jmp fo_bad
fo_2:   lda (sp),y
        clc
        adc #4                  ; 4 + symbols must fit in the block
        sta t0
        lda #0
        adc #0
        sta t0+1
        lda fc_e+1
        cmp t0+1
        bcs *+5
        jmp fo_bad
        bne fo_3
        lda fc_e
        cmp t0
        bcs *+5
        jmp fo_bad
fo_3:   sec                     ; fc_e = what is left after them
        lda fc_e
        sbc t0
        sta fc_e
        lda fc_e+1
        sbc t0+1
        sta fc_e+1
        lda symcnt+1            ; every symbol number is one that exists
        bne fo_5
        ldy #2
        lda (sp),y
        tax
        ldy #4
fo_4:   dex
        bmi fo_5
        lda (sp),y
        cmp symcnt
        bcc *+5
        jmp fo_bad
        iny
        bne fo_4
fo_5:   ldy #2                  ; cs = the first line
        lda (sp),y
        clc
        adc #4
        adc sp
        sta cs
        lda sp+1
        adc #0
        sta cs+1
        ldy #3
        lda (sp),y
        sta fc_nl
fo_6:   lda fc_nl
        beq fo_end
        lda fc_e+1              ; room for a size
        bne fo_7
        lda fc_e
        cmp #2
        bcc fo_bad
fo_7:   ldy #0
        lda (cs),y
        sta fc_l
        iny
        lda (cs),y
        sta fc_l+1
        jsr fo_adv2
        cmp #7                  ; 1 to 1536 bytes
        bcs fo_bad
        cmp #6
        bne fo_8
        lda fc_l
        bne fo_bad
fo_8:   lda fc_l
        ora fc_l+1
        beq fo_bad
        lda fc_e+1              ; and they must all be there
        cmp fc_l+1
        bcc fo_bad
        bne fo_9
        lda fc_e
        cmp fc_l
        bcc fo_bad
fo_9:   sec
        lda fc_e
        sbc fc_l
        sta fc_e
        lda fc_e+1
        sbc fc_l+1
        sta fc_e+1
        jsr fo_line
        bcs fo_bad
        dec fc_nl
        jmp fo_6
fo_end: lda fc_e                ; nothing may be left over
        ora fc_e+1
        bne fo_bad
        clc
        rts
fo_bad: sec
        rts

; cs += 2, fc_e -= 2; A = the high byte of fc_l (for the caller's test)
fo_adv2:
        clc
        lda cs
        adc #2
        sta cs
        bcc *+4
        inc cs+1
        sec
        lda fc_e
        sbc #2
        sta fc_e
        bcs fa_1
        dec fc_e+1
fa_1:   lda fc_l+1
        rts

; the token stream at cs, fc_l bytes: every token known and whole, ending in the end mark;
; cs moves past it. Carry set: not well formed.
fo_line:
        lda #0
        sta fc_t
fl_t1:  lda fc_l                ; something left?
        ora fc_l+1
        bne *+5
        jmp fl_bad
        ldy #0
        lda (cs),y
        bne fl_t2
        lda fc_l+1              ; the end mark must be the last byte
        beq *+5
        jmp fl_bad
        lda fc_l
        cmp #1
        beq *+5
        jmp fl_bad
        jsr fl_adv1
        clc
        rts
fl_t2:  inc fc_t                ; at most 255 tokens
        bne *+5
        jmp fl_bad
        cmp #1
        beq fl_lit
        cmp #2
        beq fl_nm
        cmp #$80
        bcs fl_one
        cmp #3
        bcs *+5
        jmp fl_bad
        cmp #11
        bcc *+5
        jmp fl_bad
fl_one: jsr fl_adv1
        jmp fl_t1
fl_nm:  lda fc_l+1              ; a name: two bytes, the symbol must exist
        bne fl_n1
        lda fc_l
        cmp #2
        bcs *+5
        jmp fl_bad
fl_n1:  lda symcnt+1
        bne fl_n2
        ldy #1
        lda (cs),y
        cmp symcnt
        bcc *+5
        jmp fl_bad
fl_n2:  jsr fl_adv1
        jsr fl_adv1
        jmp fl_t1
fl_lit: lda fc_l+1              ; a literal: code, tag, count, then the lengths, then the data
        bne fl_l1
        lda fc_l
        cmp #4
        bcs *+5
        jmp fl_bad
fl_l1:  ldy #1
        lda (cs),y
        and #$f0
        beq *+5
        jmp fl_bad
        lda (cs),y
        lsr
        lsr
        and #3                  ; the rank
        cmp #3
        bcc *+5
        jmp fl_bad
        sta cu_a
        asl
        clc
        adc #4                  ; the size of the header: code, tag, count, lengths
        sta cu_m
        lda fc_l+1
        bne fl_l2
        lda fc_l
        cmp cu_m
        bcs *+5
        jmp fl_bad
fl_l2:  ldy #2                  ; the count
        lda (cs),y
        sta fc_w
        iny
        lda (cs),y
        sta fc_w+1
        lda cu_a
        beq fl_r0
        cmp #1
        beq fl_r1
        ldy #4                  ; two lengths: their product is the count
        lda (cs),y
        sta p0
        iny
        lda (cs),y
        sta p1
        iny
        lda (cs),y
        sta bl
        iny
        lda (cs),y
        sta bh
        jsr mul16
        lda p2
        ora p3
        beq *+5
        jmp fl_bad
        lda p0
        cmp fc_w
        beq *+5
        jmp fl_bad
        lda p1
        cmp fc_w+1
        beq *+5
        jmp fl_bad
        jmp fl_sz
fl_r0:  lda fc_w                ; a scalar has one element
        cmp #1
        beq *+5
        jmp fl_bad
        lda fc_w+1
        beq *+5
        jmp fl_bad
        jmp fl_sz
fl_r1:  ldy #4                  ; a vector's length is its count
        lda (cs),y
        cmp fc_w
        bne fl_bad
        iny
        lda (cs),y
        cmp fc_w+1
        bne fl_bad
fl_sz:  ldy #1                  ; the size of the whole token: header + count * width
        lda (cs),y
        and #3
        tax
        lda fc_w
        sta p0
        lda fc_w+1
        sta p1
        lda WIDTHT,x
        cmp #1
        beq fl_s2
        asl p0
        rol p1
        bcs fl_bad
        lda WIDTHT,x
        cmp #3
        bne fl_s2
        clc
        lda p0
        adc fc_w
        sta p0
        lda p1
        adc fc_w+1
        sta p1
        bcs fl_bad
fl_s2:  clc
        lda p0
        adc cu_m
        sta p0
        bcc fl_s3
        inc p1
        beq fl_bad
fl_s3:  lda fc_l+1              ; it must all be in the line
        cmp p1
        bcc fl_bad
        bne fl_s4
        lda fc_l
        cmp p0
        bcc fl_bad
fl_s4:  clc                     ; go past it
        lda cs
        adc p0
        sta cs
        lda cs+1
        adc p1
        sta cs+1
        sec
        lda fc_l
        sbc p0
        sta fc_l
        lda fc_l+1
        sbc p1
        sta fc_l+1
        jmp fl_t1
fl_bad: sec
        rts

fl_adv1:
        inc cs
        bne *+4
        inc cs+1
        lda fc_l
        bne fa_2
        dec fc_l+1
fa_2:   dec fc_l
        rts
