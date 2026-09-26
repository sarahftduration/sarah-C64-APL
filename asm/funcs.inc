; User-defined functions. Spec: apl64.py (Func, Interp._begin_def, _def_line, call).
; Included by eval.asm.
;
; A function is a variable cell with tag $15 (a CHAR vector, plus $10 = function) whose block is
; the model's Func.to_bytes():
;   nargs, hasres, nsyms, nlines, nlabels, then nsyms symbol numbers (result, left argument,
;   right argument, locals; the ones that exist; then the labels), then the line number of each
;   label, then for each line its size (2 bytes) and its tokens.
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
        jmp s_def_line
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
        jmp s_begin_def
dl_5:   jsr tokenize
        bcc *+3
        rts
        jmp eval_line

do_branch:
        jsr topcell
        jsr getval
        lda vt
        cmp #1
        bne db_1
        lda #E_DOMAIN
        sec
        rts
db_1:   lda vn
        ora vn+1
        bne db_2
        jmp el_pop
db_2:   lda vp
        sta ep
        lda vp+1
        sta ep+1
        jsr elem_to_int
        bcc db_3
        lda #E_DOMAIN
        sec
        rts
db_3:   ldx cfh
        lda HTL,x
        sta gp
        lda HTH,x
        sta gp+1
        ldy #8
        lda (gp),y
        sta cu_n                ; the number of lines
        lda ineg
        ora ihuge
        bne db_x
        lda im+1
        bne db_x
        lda im
        beq db_x
        cmp cu_n
        beq db_4
        bcs db_x
db_4:   sec
        sbc #1
        sta cln
        jmp db_p
db_x:   lda cu_n                ; out of range: the function has no more lines
        sta cln
db_p:   sec                     ; the value goes
        lda vsp
        sbc #4
        sta vsp
        lda vsp+1
        sbc #0
        sta vsp+1
        jmp fn_nextline

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
        adc #5
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
uc_9:   jsr fnptr               ; the labels get their line numbers
        ldy #4
        lda (sp),y
        beq uc_l9
        sta cu_n
        lda #0
        sta cu_i
uc_l1:  ldy #2
        lda (sp),y
        sec
        sbc cu_n
        clc
        adc cu_i
        jsr symat
        jsr varcell
        ldy #2
        lda (sp),y
        clc
        adc cu_i
        adc #5
        tay
        lda (sp),y
        sta cv+1
        lda #2                  ; an INT scalar
        sta cv
        lda #0
        sta cv+2
        sta cv+3
        ldy #3
uc_l2:  lda cv,y
        sta (cptr),y
        dey
        bpl uc_l2
        inc cu_i
        lda cu_i
        cmp cu_n
        bne uc_l1
uc_l9:  lda cu_h
        sta cfh
        lda #0
        sta cln
        ; falls into fn_nextline

; run the next line of the running function, or return. RUN/STOP is looked for here, between
; lines, which is where every loop and every recursion passes: the KERNAL's interrupt keeps
; the stop key's state in $91 ($7F while it is down).
STKEY   = $91

fn_nextline:
        lda STKEY
        cmp #$7f
        bne fl_0
fn_intr:
        lda #E_INTR
        sec
        rts
fl_0:   ldx cfh
        lda HTL,x
        sta gp
        lda HTH,x
        sta gp+1
        ldy #8
        lda cln
        cmp (gp),y
        bcc fl_1
        jmp udf_return
fl_1:   ldy #7                  ; the lines start after the symbols and the label table
        lda (gp),y
        ldy #9
        clc
        adc (gp),y
        adc #10
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
        adc #64
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
        ldy #10                 ; the result name's value, before the names are given back
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
