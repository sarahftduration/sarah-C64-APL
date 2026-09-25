; Evaluator. Spec: apl64.py Interp.eval_tokens / run_line.

        .include "tokenizer.asm"

E_NONCE  = 4
E_VALUE  = 5
E_RANK   = 6
E_LENGTH = 7
E_WSFULL = 8

        .include "heap.inc"
        .include "prims.inc"
        .include "scalar.inc"
        .include "reduce.inc"

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

TIL     = $3c00
TIH     = $3d00
TC      = $3e00
FK      = $5b00                 ; frame stack: kind, saved lo, resume position, function
FLO     = $5b80
FRS     = $5c00
FFN     = $5c80
LOGBUF  = $f000

ev_lo   = $ec
ev_i1   = $ed
ev_fsp  = $ee
ev_tok  = $ef
ev_pkind = $f0
ev_pfn  = $f1
ev_jm   = $f2
ev_dep  = $f3
ev_ntok = $f4
ev_slo  = $f5
ev_shi  = $f6
ev_ix   = $f7
ev_hb   = $f8
ev_px   = $f9
echov   = $fa
ev_pg   = $fe
logp    = $fc

eval_init:
        jsr heap_init
        lda #<echo_none
        sta echov
        lda #>echo_none
        sta echov+1
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
        lda gsrc
        sta TIL,x
        lda gsrc+1
        sta TIH,x
        lda (gsrc),y
        cmp #T_LIT
        beq mi_lit
        cmp #T_NAME
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
        rts

; parentheses must balance across the whole line, checked before any evaluation
balance:
        ldx #0
        stx ev_dep
bl1:    cpx ev_ntok
        beq bl_end
        lda TC,x
        cmp #T_LPAR
        bne bl2
        inc ev_dep
        jmp bl3
bl2:    cmp #T_RPAR
        bne bl3
        lda ev_dep
        beq bl_bad
        dec ev_dep
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
elb0:    lda #0
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
        bne el_s1
        inc ev_dep
        jmp el_adv
el_s1:  cmp #T_RPAR
        bne el_s2
        dec ev_dep
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
el_ok:  lda ev_shi              ; echo unless the statement starts with name ←
        sec
        sbc ev_slo
        cmp #2
        bcc el_echo
        ldx ev_slo
        lda TC,x
        cmp #T_NAME
        bne el_echo
        lda TC+1,x
        cmp #T_ASSIGN
        beq el_pop
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
        clc
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
        cmp #T_LBRK
        beq es_nonce
        cmp #T_RBRK
        beq es_nonce
        cmp #T_BRANCH
        beq es_nonce
        cmp #T_SEMI
        beq es_nonce
        inx
        jmp es1
es_nonce:
        lda #E_NONCE
        sec
        rts
es2:    lda ev_slo
        sta ev_lo
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
        beq ev_syn
        bcc ev_syn
        ldx ev_i1
        dex
        lda TC,x
        cmp #T_LIT
        beq rs_lit
        cmp #T_NAME
        beq rs_name
        cmp #T_RPAR
        beq rs_par
ev_syn: lda #E_SYNTAX
        sec
        rts
rs_lit: jsr pushlit
        bcc *+3
        rts
        dec ev_i1
        jmp evloop
rs_name:
        jsr pushname
        bcc *+3
        rts
        dec ev_i1
        jmp evloop
rs_par: lda #K_INIT
        sta ev_pkind
        lda #0
        sta ev_pfn
        jsr enterparen
        bcc *+3
        rts
        jmp rstart
ev_ret: rts

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
        bcs rl_fn
        jmp ev_syn
rl_asg: cpx ev_lo
        beq ev_syn
        bcc ev_syn
        dex
        lda TC,x
        cmp #T_NAME
        bne ev_syn
        jsr nameidx
        jsr assign
        dec ev_i1
        dec ev_i1
        jmp evloop
rl_op:  cpx ev_lo               ; operators: only f/ on a scalar dyadic is implemented
        beq ev_syn
        dex
        lda TC,x
        cmp #T_LIT
        beq rl_nonce
        cmp #T_NAME
        beq rl_nonce
        cmp #T_RPAR
        beq rl_nonce
        cmp #$80
        bcc ev_syn
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
        bcs rl_nonce
        dec ev_i1               ; skip the operator and the function
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
        beq rf_lit
        cmp #T_NAME
        beq rf_name
        cmp #T_RPAR
        beq rf_par
rf_mon: lda ev_tok
        cmp #$c0
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
rf_lit: jsr pushlit
        bcc *+3
        rts
        dec ev_i1
        lda ev_tok
        jsr apply_dy
        bcc *+3
        rts
        jmp evloop
rf_name:
        jsr pushname
        bcc *+3
        rts
        dec ev_i1
        lda ev_tok
        jsr apply_dy
        bcc *+3
        rts
        jmp evloop
rf_par: lda #K_LEFT
        sta ev_pkind
        lda ev_tok
        sta ev_pfn
        jsr enterparen
        bcc *+3
        rts
        jmp rstart

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
        cmp #K_LEFT
        beq rl_left
        jmp evloop
rl_left:
        lda ev_pfn
        jsr apply_dy
        bcc *+3
        rts
        jmp evloop

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
        cpx #128
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
        jsr varcell
        ldy #0
        lda (cptr),y
        cmp #$80
        beq pn_val
        ldy #3
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
        ldy #1
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
        lda #E_NONCE
        sec
        rts
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
        beq ad_nonce
        cmp #11
        beq ad_reshape
        cmp #12
        beq ad_cat
ad_nonce:
        lda #E_NONCE
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
