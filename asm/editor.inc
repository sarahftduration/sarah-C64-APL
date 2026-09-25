; Keyboard entry and the line editor. Spec: tools/keys.py; see DESIGN.md, Display and input.
;
; Keys come from KERNAL GETIN through getkey_vec (a test build reads a script instead).
; The line being typed lives in INBUF, where the tokenizer wants it. Editing: append,
; DEL (backspace), RETURN (run), cursor-up (recall the last line), CLR (clear the screen
; and redraw the line). The pound key is a prefix: the next key is looked up in dg_table;
; the prefix twice types a backslash; an unmapped second key cancels the prefix.

K_RETURN = $0d
K_DEL    = $14
K_CLR    = $93
K_UP     = $91
K_PREFIX = $5c
K_LARROW = $5f
CURSORC  = $7f
PROMPT_LEN = 6

kbd_getin:
        jmp $ffe4               ; KERNAL GETIN: 0 if no key is waiting

getkey: jmp (getkey_vec)

; wait for a key; the label is where the machine sits while idle (the tests break on it)
kbd_wait:
        jsr getkey
        bne kw2
kbd_idle:
        jmp kbd_wait
kw2:    rts

; A = PETSCII -> A = our code, or 0 if the key does nothing
key_translate:
        cmp #$20
        bcc kt_none
        cmp #$41
        bcc kt_same             ; $20-$40
        cmp #$5b
        bcc kt_lower            ; $41-$5A: our lower case
        beq kt_same
        cmp #$5d
        beq kt_same
        cmp #$5e
        beq kt_same
        cmp #K_LARROW
        beq kt_arrow
        cmp #$c1
        bcc kt_none
        cmp #$db
        bcs kt_none
        sec
        sbc #$80                ; shifted: our upper case
kt_same: rts
kt_lower:
        ora #$20
        rts
kt_arrow:
        lda #$91                ; the APL assignment arrow
        rts
kt_none:
        lda #0
        rts

; A = a raw key. Carry set on return: RETURN, the line is complete.
edit_key:
        ldx kprefix
        bne ek_second
        cmp #K_RETURN
        beq ek_ret
        cmp #K_DEL
        beq ek_del
        cmp #K_CLR
        beq ek_clr
        cmp #K_UP
        beq ek_up
        cmp #K_PREFIX
        beq ek_pre
        jsr key_translate
        beq ek_done
        jmp ek_insert
ek_ret: sec
        rts
ek_pre: lda #1
        sta kprefix
ek_done: clc
        rts
ek_second:
        ldx #0
        stx kprefix
        cmp #K_PREFIX
        bne ek_s1
        lda #$5c                ; the prefix twice: a backslash
        jmp ek_insert
ek_s1:  jsr key_translate
        beq ek_done
        sta ktmp
        ldx #0
ek_s2:  lda dg_table,x
        beq ek_done
        cmp ktmp
        beq ek_s3
        inx
        inx
        jmp ek_s2
ek_s3:  lda dg_table+1,x
ek_insert:
        ldx klen
        cpx #255
        bcs ek_done
        sta INBUF,x
        inc klen
        jsr scr_put
        jmp ek_done
ek_del: lda klen
        beq ek_done
        dec klen
        jsr scr_back
        jmp ek_done
ek_clr: jsr scr_clear
        jsr prompt
        jsr retype
        jmp ek_done
ek_up:  jsr erase_line          ; recall the last line
        ldx #0
ek_u1:  cpx hlen
        beq ek_u2
        lda HIST,x
        sta INBUF,x
        inx
        jmp ek_u1
ek_u2:  lda hlen
        sta klen
        jsr retype
        jmp ek_done

; erase the typed text from the screen and empty the line
erase_line:
el1:    lda klen
        beq el2
        dec klen
        jsr scr_back
        jmp el1
el2:    rts

; show INBUF[0..klen) again
retype: lda #0
        sta kidx
rt1:    lda kidx
        cmp klen
        beq rt2
        tax
        lda INBUF,x
        jsr scr_put
        inc kidx
        jmp rt1
rt2:    rts

prompt: ldx #PROMPT_LEN
pr1:    lda #' '
        stx kidx
        jsr scr_put
        ldx kidx
        dex
        bne pr1
        rts

cursor_on:
        ldy #0
        lda #CURSORC
        sta (scrp),y
        rts
cursor_off:
        ldy #0
        lda #' '
        sta (scrp),y
        rts

; --- the read-evaluate-print loop -------------------------------------------------------------
repl:   jsr prompt
        lda #0
        sta klen
        sta kprefix
rp_key: jsr cursor_on
        jsr kbd_wait
        pha
        jsr cursor_off
        pla
        jsr edit_key
        bcc rp_key
        ldx klen                ; RETURN: run the line
        lda #0
        sta INBUF,x
        cpx #0
        beq rp_run
        stx hlen                ; remember it for cursor-up
        ldx #0
rp_h:   lda INBUF,x
        sta HIST,x
        inx
        cpx hlen
        bne rp_h
rp_run: lda #CHNL
        jsr scr_put
        ldx #0                  ; a system command?
rp_s1:  lda INBUF,x
        cmp #' '
        bne rp_s2
        inx
        jmp rp_s1
rp_s2:  cmp #')'
        bne rp_tok
        jsr syscmd
        jmp repl
rp_tok: jsr tokenize
        bcs rp_err
        jsr eval_line
        bcc repl_again
rp_err: jsr print_error
repl_again:
        jmp repl
