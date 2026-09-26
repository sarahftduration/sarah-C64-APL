; Evaluator. Spec: apl64.py Interp.eval_tokens / run_line.

ORG     = $0801
        * = ORG

; BASIC stub: 10 SYS 2061
        .word basic_end, 10
        .byte $9e
        .text "2061"
        .byte 0
basic_end:
        .word 0
start:  jmp startup
        .cerror start != 2061, "the SYS address in the stub must match start"

        .include "layout.inc"
        .include "tokenizer.inc"

E_NONCE  = 4
E_VALUE  = 5
E_RANK   = 6
E_LENGTH = 7
E_WSFULL = 8
E_INDEX  = 9
E_INTR   = 10

        .include "heap.inc"
        .include "prims.inc"
        .include "scalar.inc"
        .include "reduce.inc"
        .include "index.inc"
        .include "replicate.inc"
        .include "reshape.inc"
        .include "search.inc"
        .include "funcs.inc"
        .include "format.inc"
        .include "startup.inc"

; --- token index ------------------------------------------------------------------
; The token stream has variable-length literals, so it cannot be walked right to
; left. mkindex records each token's address (TIL/TIH) and code (TC).

T_LPAR    = 3
T_RPAR    = 4
T_LBRK    = 5
T_RBRK    = 6
T_ASSIGN  = 7
T_BRANCH  = 8
T_DIAMOND = 9
T_SEMI    = 10

K_INIT    = 0                   ; frame kinds: what to do with a parenthesised value
K_LEFT    = 1
K_GRP     = 2                   ; an index group: go on to the next group to its left
K_IDX     = 3                   ; the indexed array: apply p_index, then the outer kind
K_IASG    = 4                   ; the assigned variable: apply p_iasg, then the outer kind
K_LEFTU   = 5                   ; like K_LEFT, for a user-defined function (its symbol in the frame)
T_FN      = $0b                 ; a name of a function that takes arguments (see classify)

FK      = FSTK                  ; frame stack: kind, saved lo, resume position, function
FLO     = FSTK+64
FRS     = FSTK+128
FFN     = FSTK+192

ev_lo   = $43
ev_i1   = $09
ev_fsp  = $82
ev_tok  = $8a
ev_pkind = WS+$f0
ev_pfn  = WS+$f1
ev_jm   = WS+$f2
ev_dep  = $2c
ev_ntok = WS+$f4
ev_slo  = $49
ev_shi  = $8b
ev_ix   = WS+$f7
ev_hb   = WS+$f8
ev_px   = WS+$f9
ev_sf   = WS+$f5                ; find_delim: stop at semicolons
ev_na   = WS+$f6                ; the statement began with an assignment: no echo
ev_tl   = WS+$100               ; (2) size of the token stream in OUTBUF, with its end mark
ev_nv   = WS+$102               ; the last function called gave no value
ev_us   = WS+$103               ; symbol of the function to be called
ev_rm   = WS+$104               ; how to go on afterwards: 0 evloop, 1 as after a pushed operand
ev_no   = WS+$105               ; operands of the call: 0, 1 or 2
echov   = WS+$fa
ev_pg   = WS+$fe

eval_init:
        jsr heap_init
        lda #<echo_none
        sta echov
        lda #>echo_none
        sta echov+1
        lda #<fmt_null
        sta outv
        lda #>fmt_null
        sta outv+1
        lda #<LOGBUF
        sta logp
        lda #>LOGBUF
        sta logp+1
        rts

mkindex:
        lda #<OUTBUF
        sta gsrc
        lda #>OUTBUF
        sta gsrc+1
        ldx #0
mi1:    ldy #0
        lda (gsrc),y
        beq mi_end
        sta TC,x
        cmp #T_EMPTY            ; the empty vector is a literal to the evaluator
        bne mi_t
        lda #T_LIT
        sta TC,x
mi_t:   lda gsrc
        sta TIL,x
        lda gsrc+1
        sta TIH,x
        lda (gsrc),y
        cmp #T_LIT
        beq mi_lit
        cmp #T_NAME
        beq mi_2
        cmp #T_FN
        beq mi_2
        lda #1
        bne mi_adv
mi_2:   lda #2
mi_adv: clc
        adc gsrc
        sta gsrc
        bcc mi_n
        inc gsrc+1
mi_n:   inx
        jmp mi1
mi_lit: stx ev_ix
        jsr blocksize
        ldx ev_ix
        clc
        lda gsrc
        adc gsz
        sta gsrc
        lda gsrc+1
        adc gsz+1
        sta gsrc+1
        jmp mi_n
mi_end: stx ev_ntok
        sec                     ; the stream's size, with its end mark
        lda gsrc
        sbc #<OUTBUF
        sta ev_tl
        lda gsrc+1
        sbc #>OUTBUF
        sta ev_tl+1
        inc ev_tl
        bne mi_e1
        inc ev_tl+1
mi_e1:  rts

; parentheses and brackets must nest properly across the whole line, checked before any
; evaluation. FK is used as the stack of open tokens (evaluation has not started).
balance:
        ldx #0
        stx ev_dep
bl1:    cpx ev_ntok
        beq bl_end
        lda TC,x
        cmp #T_LPAR
        beq bl_push
        cmp #T_LBRK
        beq bl_push
        cmp #T_RPAR
        beq bl_pop
        cmp #T_RBRK
        bne bl3
bl_pop: ldy ev_dep
        beq bl_bad
        dey
        sty ev_dep
        sec
        sbc #1                  ; the opener that matches this closer
        cmp FK,y
        bne bl_bad
        jmp bl3
bl_push:
        ldy ev_dep
        sta FK,y
        inc ev_dep
bl3:    inx
        jmp bl1
bl_end: lda ev_dep
        bne bl_bad
        clc
        rts
bl_bad: lda #E_SYNTAX
        sec
        rts

; --- lines and statements --------------------------------------------------------------
; eval_line: evaluate the token stream at OUTBUF. Statements are split at diamonds
; outside parentheses; each value is passed to the echo hook unless the statement
; starts with `name ←`.
eval_line:
        jsr eval_line_body
        php
        pha
        lda cdepth              ; an error inside calls: give the localised names back
        beq el_u1
        jsr unwind
el_u1:
        lda #<VSTACK
        sta vsp
        lda #>VSTACK
        sta vsp+1
        pla
        plp
        rts

eval_line_body:
        lda #0
        sta ev_fsp
        lda #<VSTACK
        sta vsp
        lda #>VSTACK
        sta vsp+1
        jsr mkindex
        jsr balance
        bcc elb0
        rts
elb0:    jsr classify
        lda #0
        sta ev_slo
el_next:
        ldx ev_slo
        lda #0
        sta ev_dep
el_scan:
        cpx ev_ntok
        beq el_end
        lda TC,x
        cmp #T_LPAR
        beq el_in
        cmp #T_LBRK
        bne el_s1
el_in:  inc ev_dep
        jmp el_adv
el_s1:  cmp #T_RPAR
        beq el_out
        cmp #T_RBRK
        bne el_s2
el_out: dec ev_dep
        jmp el_adv
el_s2:  cmp #T_DIAMOND
        bne el_adv
        lda ev_dep
        beq el_end
el_adv: inx
        jmp el_scan
el_end: stx ev_shi
        lda ev_shi
        cmp ev_slo
        beq el_empty
        jsr eval_stmt
        bcc el_ok
        rts
el_ok:  ldx ev_slo
        lda TC,x
        cmp #T_BRANCH
        bne el_o1
        lda ev_nv               ; a branch: the value says where to go (none is not a value)
        beq el_o0
        lda #E_VALUE
        sec
        rts
el_o0:  jmp do_branch
el_o1:  lda ev_nv               ; a call that gave no value: nothing to echo or pop
        bne el_empty
        lda ev_na               ; echo unless the statement starts with name ← or name[...]←
        bne el_pop
el_echo:
        jsr callecho
el_pop: sec
        lda vsp
        sbc #4
        sta vsp
        lda vsp+1
        sbc #0
        sta vsp+1
el_empty:
        lda ev_shi
        cmp ev_ntok
        beq el_done
        clc
        adc #1
        sta ev_slo
        jmp el_next
el_done:
        lda cdepth              ; inside a function: go on with its next line
        beq el_d1
        jmp fn_nextline
el_d1:  clc
        rts

callecho:
        jmp (echov)

echo_none:
        rts

eval_stmt:
        ldx ev_slo
es1:    cpx ev_shi
        beq es2
        lda TC,x
        cmp #T_BRANCH           ; only a statement's first token can be a branch, and only in a function
        bne es_n
        cpx ev_slo
        bne es_syn
        lda cdepth
        beq es_nonce
es_n:   inx
        jmp es1
es_syn: lda #E_SYNTAX
        sec
        rts
es_nonce:
        lda #E_NONCE
        sec
        rts
es2:    lda #0
        sta ev_na
        sta ev_nv
        ldx ev_slo              ; a branch: the expression after the arrow is the statement
        lda TC,x
        cmp #T_BRANCH
        bne es3
        inx
es3:    stx ev_lo
        lda ev_shi
        sta ev_i1
        lda #0
        sta ev_fsp
        ; falls into the evaluator; its final rts returns from eval_stmt

; --- right-to-left evaluation ----------------------------------------------------------
; ev_lo/ev_i1 delimit the current range: tokens ev_lo .. ev_i1-1, the next to
; consume being ev_i1-1. Parenthesised groups push a frame and continue inside;
; when a range is exhausted the frame is popped and the value it produced is
; used as the initial value (K_INIT) or as the left operand (K_LEFT).
rstart: lda ev_i1
        cmp ev_lo
        beq rs_bad
        bcc rs_bad
        ldx ev_i1
        dex
        lda TC,x
        cmp #T_LIT
        beq rs_op
        cmp #T_NAME
        beq rs_op
        cmp #T_RPAR
        beq rs_op
        cmp #T_RBRK
        beq rs_op
rs_bad: jmp ev_syn
rs_op:  lda #K_INIT
        sta ev_pkind
        lda #0
        sta ev_pfn
        ; falls into opnd

; The operand ending at token ev_i1-1 (a literal, name, ')' or ']'), to be followed by the
; continuation ev_pkind/ev_pfn (see cont). Literals and names are pushed at once; a
; parenthesised group or an index expression suspends the current range in a frame.
opnd:   ldx ev_i1
        dex
        lda TC,x
        cmp #T_LIT
        bne op1
        jsr pushlit
        jmp op_pushed
op1:    cmp #T_NAME
        bne op2
        jsr pushname
op_pushed:
        bcc *+3
        rts
        dec ev_i1
        jmp cont
op2:    cmp #T_RPAR
        bne op3
        jsr enterparen
        bcc *+3
        rts
        jmp rstart
op3:    cmp #T_RBRK
        bne op4
        jmp fetch_rbrk
op4:    jmp ev_syn

; What to do with a finished operand: K_INIT continue, K_LEFT apply the function ev_pfn
; dyadically, K_GRP evaluate the next index group, K_IDX index the array with the groups
; and then carry on with the kind saved in the index frame below.
cont:   lda ev_pkind
        beq ct_init
        cmp #K_LEFT
        beq ct_left
        cmp #K_GRP
        bne ct_idx
        jmp gstep
ct_idx: cmp #K_IDX
        bne ct_i2
        jsr p_index
        jmp ct_pop
ct_i2:  cmp #K_LEFTU
        bne ct_ia
        lda ev_pfn
        sta ev_us
        jmp udf_dy
ct_ia:  ldx ev_i1               ; the name token of A[i]<-v
        cpx ev_slo
        bne ci_x
        inc ev_na
ci_x:   jsr nameidx
        sta xvar
        jsr p_iasg
ct_pop: bcc *+3
        rts
        dec ev_fsp
        ldx ev_fsp
        lda FK,x
        sta ev_pkind
        lda FFN,x
        sta ev_pfn
        jmp cont
ct_left:
        lda ev_pfn
        jsr apply_dy
        bcc *+3
        rts
ct_init:
        jmp evloop

ev_syn: lda #E_SYNTAX
        sec
        rts

evloop: lda ev_i1
        cmp ev_lo
        bne *+5
        jmp rl_end
        ldx ev_i1
        dex
        lda TC,x
        sta ev_tok
        cmp #T_ASSIGN
        beq rl_asg
        cmp #$c0
        bcs rl_op
        cmp #$80
        bcc rl_x
        jmp rl_fn
rl_x:   cmp #T_FN
        bne rl_y
        jsr nameidx             ; a user-defined function: remember which
        sta ev_us
        jmp rl_fn
rl_y:   cmp #T_RBRK
        bne rl_bad
        jmp rl_axis
rl_bad: jmp ev_syn
rl_asg: cpx ev_lo
        beq ev_syn
        bcc ev_syn
        dex
        lda TC,x
        cmp #T_RBRK
        bne ra_name
        dec ev_i1               ; A[i]<-v: index groups first (fetch_rbrk wants a name before '[')
        lda #$80                ; K_INIT plus the assignment flag
        sta ev_pkind
        lda #0
        sta ev_pfn
        jmp fetch_rbrk
ra_name:
        cmp #T_NAME
        bne ev_syn
        cpx ev_slo
        bne ra_x
        inc ev_na
ra_x:   jsr nameidx
        pha
        jsr varcell
        ldy #0
        lda (cptr),y
        and #TAG_FN             ; a function's name cannot be assigned to
        beq ra_ok
        pla
        jmp ev_syn
ra_ok:  pla
        jsr assign
        dec ev_i1
        dec ev_i1
        jmp evloop
rl_op:  cpx ev_lo               ; operators: only f/ on a scalar dyadic is implemented
        bne ro_1
        jmp ev_syn
ro_1:
        dex
        lda TC,x
        cmp #T_LIT
        beq rl_val
        cmp #T_NAME
        beq rl_val
        cmp #T_RPAR
        beq rl_val
        cmp #T_RBRK
        beq rl_val
        cmp #$80
        bcs *+5
        jmp ev_syn
        cmp #$c0
        bcc rl_fnok
        jmp ev_syn
rl_fnok:
        sec
        sbc #$80
        sta ev_pg
        lda ev_tok
        cmp #$c0
        bne rl_nonce
        lda ev_pg
        cmp #10
        bcc rl_ok               ; + - × ÷ = ≠ < ≤ > ≥ are 0-9, ⌈ ⌊ | are 13-15: reduce knows them as 10-12
        cmp #13
        bcc rl_nonce
        cmp #16
        bcc rl_m3
        cmp #18
        bcs rl_nonce
        sec                     ; ∧ ∨: reduce knows them as 14 and 15
        sbc #2
        sta ev_pg
        bne rl_ok
rl_m3:  sec
        sbc #3
        sta ev_pg
rl_ok:  dec ev_i1               ; skip the operator and the function
        dec ev_i1
        jmp rl_fn2
rl_val: lda ev_tok              ; a value before an operator: a/b replicates, the others are not done
        cmp #$c0
        bne rl_nonce
        lda #$7f                ; (a function code of its own: x f/ y is not a/b)
        sta ev_tok
        dec ev_i1
        jmp rl_fn2
rl_nonce:
        lda #E_NONCE
        sec
        rts
rl_fn:  dec ev_i1
rl_fn2: lda ev_i1
        cmp ev_lo
        beq rf_mon
        bcc rf_mon
        ldx ev_i1
        dex
        lda TC,x
        cmp #T_LIT
        beq rf_opnd
        cmp #T_NAME
        beq rf_opnd
        cmp #T_RPAR
        beq rf_opnd
        cmp #T_RBRK
        beq rf_opnd
rf_mon: lda ev_tok
        cmp #T_FN
        bne rf_m1
        jmp udf_mon
rf_m1:  cmp #$c0
        bcs rf_red
        jsr apply_mon
        bcc *+3
        rts
        jmp evloop
rf_red: lda ev_pg
        jsr p_reduce
        bcc *+3
        rts
        jmp evloop
rf_opnd:
        lda ev_tok
        cmp #T_FN
        bne rf_o1
        lda #K_LEFTU
        sta ev_pkind
        lda ev_us
        sta ev_pfn
        jmp opnd
rf_o1:  lda #K_LEFT
        sta ev_pkind
        lda ev_tok
        sta ev_pfn
        jmp opnd

rl_end: lda ev_fsp
        bne rl_pop
        clc
        rts
rl_pop: dec ev_fsp
        ldx ev_fsp
        lda FLO,x
        sta ev_lo
        lda FRS,x
        sta ev_i1
        lda FFN,x
        sta ev_pfn
        lda FK,x
        sta ev_pkind
        jmp cont

; --- index expressions ----------------------------------------------------------------------
; X = index of a ']' that ends an operand, to be followed by ev_pkind/ev_pfn. Spec:
; apl64.py Interp._operand. A marker cell goes on the value stack, then a frame that remembers
; the outer kind; the groups between the brackets are evaluated right to left, each
; leaving its value (or an elided-axis cell) above the marker; the indexed array comes last
; and p_index replaces the marker, the groups and the array by the result.
fr_lim: lda #E_LIMIT
        sec
        rts

fetch_rbrk:
        lda #0
        sta ev_sf
        jsr find_delim          ; X = the matching '['
        cpx ev_lo
        beq fr_syn
        bcc fr_syn
        dex
        lda TC,x
        ldy ev_pkind
        bpl fr_val
        cmp #T_NAME             ; an assignment needs a name before the '[' that is not a function
        bne fr_syn
        jsr nameidx
        jsr varcell
        ldy #0
        lda (cptr),y
        and #TAG_FN
        beq fr_ok
        bne fr_syn
fr_val: cmp #T_LIT
        beq fr_ok
        cmp #T_NAME
        beq fr_ok
        cmp #T_RPAR
        beq fr_ok
        cmp #T_RBRK
        beq fr_ok
fr_syn: jmp ev_syn
fr_ok:  lda #$81
        jsr pushtag
        bcc *+3
        rts
        ldx ev_fsp
        cpx #64
        bcs fr_lim
        lda ev_pkind
        sta FK,x
        lda ev_pfn
        sta FFN,x
        inc ev_fsp
        lda #1
        sta ev_sf

; ev_i1-1 is the delimiter to the right of the next group to evaluate (']' or ';').
gstep:  ldx ev_i1
        dex
        lda TC,x
        cmp #T_LBRK
        beq gs_base
        jsr find_delim          ; X = the delimiter to its left
        inx
        stx ev_jm               ; the group starts here
        lda ev_i1
        sec
        sbc #1
        cmp ev_jm
        beq gs_empty
        ldx ev_fsp
        cpx #64
        bcc gs_1
        jmp fr_lim
gs_1:   lda #K_GRP
        sta FK,x
        lda ev_lo
        sta FLO,x
        lda ev_jm
        sta FRS,x
        inc ev_fsp
        sta ev_lo
        dec ev_i1
        jmp rstart
gs_empty:
        lda #$82                ; an elided axis
        jsr pushtag
        bcc *+3
        rts
        lda ev_jm
        sta ev_i1
        jmp gstep
gs_base:
        dec ev_i1
        ldx ev_fsp              ; the frame below says whether this is an assignment
        dex
        lda FK,x
        bmi gb_asg
        lda #K_IDX
        bne gb_go
gb_asg: and #$7f
        sta FK,x
        lda #K_IASG
gb_go:  sta ev_pkind
        lda #0
        sta ev_pfn
        jmp opnd

; push a cell whose tag is A and whose other bytes are zero
pushtag:
        sta cv
        lda #0
        sta cv+1
        sta cv+2
        sta cv+3
        jmp pushcv

; X = index of a delimiter; scan left from it, skipping nested groups, to the '[' that opens
; its bracket or (if ev_sf) to a ';' at the same level. Returns X.
find_delim:
        lda #0
        sta ev_dep
fd1:    dex
        lda TC,x
        cmp #T_RPAR
        beq fd_in
        cmp #T_RBRK
        beq fd_in
        cmp #T_LPAR
        beq fd_out
        cmp #T_LBRK
        beq fd_out
        cmp #T_SEMI
        bne fd1
        lda ev_sf
        beq fd1
        lda ev_dep
        bne fd1
        rts
fd_in:  inc ev_dep
        jmp fd1
fd_out: lda ev_dep
        beq fd_ret
        dec ev_dep
        jmp fd1
fd_ret: rts

; an axis bracket after a function: +/[1] A (not implemented)
rl_axis:
        lda #0
        sta ev_sf
        jsr find_delim
        cpx ev_lo
        beq ra_syn
        bcc ra_syn
        dex
        lda TC,x
        cmp #$80
        bcc ra_syn
        jmp rl_nonce
ra_syn: jmp ev_syn

; X = index of a ')'. Find its '(' and enter the group as a new range.
enterparen:
        stx ev_ix
        dex
        lda #1
        sta ev_dep
ep1:    lda TC,x
        cmp #T_RPAR
        bne ep2
        inc ev_dep
        jmp ep3
ep2:    cmp #T_LPAR
        bne ep3
        dec ev_dep
        beq ep_found
ep3:    dex
        jmp ep1
ep_found:
        stx ev_jm
        inx
        cpx ev_ix
        bcs ep_empty
        ldx ev_fsp
        cpx #64
        bcs ep_limit
        lda ev_pkind
        sta FK,x
        lda ev_lo
        sta FLO,x
        lda ev_jm
        sta FRS,x
        lda ev_pfn
        sta FFN,x
        inc ev_fsp
        lda ev_jm
        clc
        adc #1
        sta ev_lo
        lda ev_ix
        sta ev_i1
        clc
        rts
ep_empty:
        lda #E_SYNTAX
        sec
        rts
ep_limit:
        lda #E_LIMIT
        sec
        rts

; --- values in and out of the token stream and variables -------------------------------
; A = symbol index of the NAME token at index X
nameidx:
        lda TIL,x
        sta gp
        lda TIH,x
        sta gp+1
        ldy #1
        lda (gp),y
        rts

; cptr = address of variable A's cell
varcell:
        sta t0
        lda #0
        sta t0+1
        asl t0
        rol t0+1
        asl t0
        rol t0+1
        clc
        lda t0
        adc #<VARS
        sta cptr
        lda t0+1
        adc #>VARS
        sta cptr+1
        rts

assign: jsr varcell
        sec
        lda vsp
        sbc #4
        sta gp
        lda vsp+1
        sbc #0
        sta gp+1
        ldy #3
as1:    lda (gp),y
        sta (cptr),y
        dey
        bpl as1
        rts

pushname:
        jsr nameidx
        sta ev_us
        jsr varcell
        ldy #0
        lda (cptr),y
        cmp #$80
        beq pn_val
        and #TAG_FN
        beq pn_c
        jmp udf_ni              ; a function without arguments: call it
pn_c:   ldy #3
pnl1:    lda (cptr),y
        sta cv,y
        dey
        bpl pnl1
        jmp pushcv
pn_val: lda #E_VALUE
        sec
        rts


; push the literal at token index X: scalars into the cell, arrays into the heap
pushlit:
        stx ev_px
        lda TIL,x
        sta cs
        lda TIH,x
        sta cs+1
        ldy #0
        lda (cs),y
        cmp #T_EMPTY
        bne pl_1
        lda #2                  ; an empty INT vector
        sta nt
        lda #1
        sta nrk
        lda #0
        sta nn
        sta nn+1
        sta nd0
        sta nd0+1
        jsr newarr
        bcc *+3
        rts
        jmp pushcv
pl_1:   ldy #1
        lda (cs),y
        sta ev_hb
        and #$0c
        bne pl_arr
        lda ev_hb
        sta cv
        lda #0
        sta cv+1
        sta cv+2
        sta cv+3
        lda ev_hb
        and #3
        tax
        lda WIDTHT,x
        sta qw
        ldy #4
        ldx #1
pl_c:   lda (cs),y
        sta cv,x
        iny
        inx
        dec qw
        bne pl_c
        jmp pushcv
pl_arr: lda cs
        sta gsrc
        lda cs+1
        sta gsrc+1
        jsr blocksize
        lda gsz
        sta asz
        lda gsz+1
        sta asz+1
        jsr alloc
        bcs plx
        ldx ev_px
        clc
        lda TIL,x
        adc #1
        sta cs
        lda TIH,x
        adc #0
        sta cs+1
        clc
        lda hadr
        adc #1
        sta cd
        lda hadr+1
        adc #0
        sta cd+1
        sec
        lda asz
        sbc #1
        sta t0
        lda asz+1
        sbc #0
        sta t0+1
        jsr memcpy_cs_cd
        lda ev_hb
        sta cv
        lda hnew
        sta cv+1
        lda #0
        sta cv+2
        sta cv+3
        jmp pushcv
plx:    rts

apply_mon:
        sec
        sbc #$80
        beq am_plus
        cmp #10
        beq am_iota
        cmp #11
        beq am_shape
        cmp #12
        beq am_ravel
        cmp #1
        beq am_neg
        cmp #2
        beq am_sign
        cmp #3
        beq am_recip
        cmp #13
        beq am_ceil
        cmp #14
        beq am_floor
        cmp #15
        beq am_abs
        cmp #18
        beq am_not
        cmp #19
        beq am_rev
        cmp #23
        beq am_gu
        cmp #24
        beq am_gd
        lda #E_NONCE
        sec
        rts
am_ceil: jmp p_ceil
am_floor: jmp p_floor
am_abs: jmp p_abs
am_not: jmp p_not
am_rev: jmp p_rev
am_gu:  jmp p_gradeup
am_gd:  jmp p_gradedown
am_plus:
        jmp p_plusm
am_iota:
        jmp p_iota
am_shape:
        jmp p_shape
am_ravel:
        jmp p_ravel
am_neg: jmp p_neg
am_sign: jmp p_signum
am_recip: jmp p_recip

apply_dy:
        sec
        sbc #$80
        cmp #10
        bcc ad_sd
        beq ad_iof
        cmp #11
        beq ad_reshape
        cmp #12
        beq ad_cat
        cmp #13                 ; ⌈ ⌊ | are the engine's operations 10 to 12, ∧ ∨ 14 and 15
        bcc ad_nonce
        cmp #16
        bcs ad_l
        sec
        sbc #3
        jmp p_sdyad
ad_l:   cmp #18
        bcc ad_l2
        beq ad_nonce
        cmp #19
        beq ad_rot
        cmp #20
        beq ad_take
        cmp #21
        beq ad_drop
        cmp #22
        bne ad_nonce
        jmp p_member
ad_drop: jmp p_drop
ad_l2:  sec
        sbc #2
        jmp p_sdyad
ad_rot: jmp p_rot
ad_iof: jmp p_indexof
ad_take: jmp p_take
ad_nonce:
        cmp #$ff                ; replicate: the code $7f set by rl_val
        bne ad_n2
        jmp p_repl
ad_n2:  lda #E_NONCE
        sec
        rts
ad_sd:  jmp p_sdyad
ad_reshape:
        jmp p_reshape
ad_cat: jmp p_catenate

; --- echo to a log (used by the tests): the value in Value.to_bytes() format ---------
lput:   ldy #0
        sta (logp),y
        inc logp
        bne lp1
        inc logp+1
lp1:    rts

echo_log:
        jsr topcell
        jsr getval
        lda vtag
        jsr lput
        lda vn
        jsr lput
        lda vn+1
        jsr lput
        lda vrk
        beq el_data
        lda vs0
        jsr lput
        lda vs0+1
        jsr lput
        lda vrk
        cmp #2
        bne el_data
        lda vs1
        jsr lput
        lda vs1+1
        jsr lput
el_data:
        jsr bytecount
        lda vp
        sta cs
        lda vp+1
        sta cs+1
        lda logp
        sta cd
        lda logp+1
        sta cd+1
        lda bc
        sta t0
        lda bc+1
        sta t0+1
        jsr memcpy_cs_cd
        clc
        lda logp
        adc bc
        sta logp
        lda logp+1
        adc bc+1
        sta logp+1
        rts

        .include "bss.inc"
