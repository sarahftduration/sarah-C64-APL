; Tokenizer, stage 1. Spec: apl64.py Interp.tokenize and DESIGN.md.
;
; tok_init   empty the symbol table.
; tokenize   In:  INBUF holds one line in charset codes, ended by $00
;                 (at most 255 bytes before the terminator).
;            Out: carry clear: the token stream is at OUTBUF, ended by $00 (op
;                 points just past it).
;                 carry set: A = error code (E_*).
;
; Not yet implemented (returns E_NONCE): numbers with a decimal point or an
; exponent, and integers above 65535.

        .include "int16.asm"

INBUF   = $3000         ; page aligned; indexed by the 8-bit ip
SBUF    = $3100         ; number strand: 3 bytes per element (mag lo, mag hi, sign)
OUTBUF  = $3400         ; room for 6 bytes per input byte
SYMTAB  = $4000         ; entries: length byte + name; must stay below SYMEND_HI
SYMEND_HI = $50

E_SYNTAX = 1
E_DOMAIN = 2
E_LIMIT  = 3
E_NONCE  = 4

T_END   = 0
T_LIT   = 1
T_NAME  = 2

ip      = $50           ; input index
op      = $51           ; output pointer (2)
tp      = $53           ; strand pointer (2)
ncount  = $55           ; elements in the strand
nm      = $56           ; parsed magnitude (2)
ns      = $58           ; parsed sign, bit 7 (never set for zero)
t2      = $59           ; scratch (2)
dgt     = $5b
scnt    = $5c           ; string length
cls     = $5d           ; strand element class: 0 BOOL, 2 INT, 3 FLOAT
symcnt  = $5e           ; names defined (2)
sp      = $60           ; symbol table pointer (2)
ki      = $62           ; symbol index (2)
nlen      = $64           ; name length
ns0     = $65           ; name start in INBUF
cc      = $66           ; loop counter
chr     = $67

tok_init:
        lda #0
        sta symcnt
        sta symcnt+1
        rts

tokenize:
        lda #0
        sta ip
        lda #<OUTBUF
        sta op
        lda #>OUTBUF
        sta op+1
main:   ldx ip
        lda INBUF,x
        beq mdone
        cmp #$20
        beq tskip
        cmp #$09
        beq tskip
        cmp #$95                ; comment: rest of line ignored
        beq mdone
        cmp #$27
        bne m1
        jmp string
m1:     jsr isnum
        bcc m2
        jmp number
m2:     lda INBUF,x
        cmp #$94                ; empty numeric vector
        bne m3
        lda #0
        sta cc
mempty: ldx cc
        lda emptyv,x
        jsr emit
        inc cc
        lda cc
        cmp #6
        bne mempty
        inc ip
        jmp main
m3:     jsr isalpha
        bcc m4
        jmp name
m4:     lda INBUF,x
        jsr tokfind
        bcc err_syn
        jsr emit
        inc ip
        jmp main
tskip:  inc ip
        jmp main
mdone:  lda #T_END
        jsr emit
        clc
        rts

err_syn:  lda #E_SYNTAX
        sec
        rts
err_dom:
        lda #E_DOMAIN
        sec
        rts
err_nonce:
        lda #E_NONCE
        sec
        rts

emptyv: .byte T_LIT, $06, 0, 0, 0, 0

emit:   ldy #0
        sta (op),y
        inc op
        bne emit1
        inc op+1
emit1:  rts

; --- character classes; all keep X, return the answer in carry ------------

; A = char at INBUF,x. Carry set if it starts a number: a digit, the high
; minus, or a point followed by a digit.
isnum:  cmp #$90
        beq inyes
        cmp #'.'
        bne indig
        lda INBUF+1,x
indig:  sec
        sbc #'0'
        cmp #10
        bcs inno
inyes:  sec
        rts
inno:   clc
        rts

; carry set if A is a letter, underscore, delta or delta-underbar
isalpha:
        cmp #'_'
        beq iayes
        cmp #$96
        beq iayes
        cmp #$97
        beq iayes
        ora #$20
        cmp #'a'
        bcc iano
        cmp #'z'+1
        bcs iano
iayes:  sec
        rts
iano:   clc
        rts

; carry set if A can continue a name: alpha or digit
isnamec:
        pha
        jsr isalpha
        bcs inc1
        pla
        sec
        sbc #'0'
        cmp #10
        bcs inc2
        sec
        rts
inc1:   pla
        sec
        rts
inc2:   clc
        rts

; A = char. Carry set and A = token if it is a one-glyph token.
tokfind:
        sta chr
        ldy #0
tf1:    lda tokmap,y
        beq tfno
        cmp chr
        beq tfyes
        iny
        iny
        bne tf1
tfno:   clc
        rts
tfyes:  lda tokmap+1,y
        sec
        rts

tokmap: .byte '(', $03, ')', $04, '[', $05, ']', $06
        .byte $91, $07, $92, $08, $93, $09, ';', $0a
        .byte '+', $80, '-', $81, $82, $82, $83, $83
        .byte '=', $84, $85, $85, '<', $86, $87, $87
        .byte '>', $88, $89, $89, $8a, $8a, $8b, $8b, ',', $8c
        .byte '/', $c0, $5c, $c1, $c2, $c2, '.', $c3, $c4, $c4, $c5, $c5
        .byte 0

; --- strings ---------------------------------------------------------------
; Characters are written at op+6 while scanning, then the header is filled in.

string: inc ip
        clc
        lda op
        adc #6
        sta op
        lda op+1
        adc #0
        sta op+1
        lda #0
        sta scnt
sl:     ldx ip
        lda INBUF,x
        bne s1
        jmp err_syn               ; unterminated
s1:     cmp #$27
        bne sc
        lda INBUF+1,x
        cmp #$27
        bne send
        inc ip                  ; doubled quote is one quote character
        lda #$27
sc:     ldy scnt
        sta (op),y
        inc scnt
        inc ip
        jmp sl
send:   inc ip
        sec
        lda op
        sbc #6
        sta op
        lda op+1
        sbc #0
        sta op+1
        lda scnt
        cmp #1
        beq sone
        lda #T_LIT
        jsr emit
        lda #$05                ; CHAR vector
        jsr emit
        lda scnt
        jsr emit
        lda #0
        jsr emit
        lda scnt
        jsr emit
        lda #0
        jsr emit
        clc
        lda op
        adc scnt
        sta op
        bcc strchk
        inc op+1
        jmp strchk
sone:   ldy #6
        lda (op),y
        pha
        lda #T_LIT
        jsr emit
        lda #$01                ; CHAR scalar
        jsr emit
        lda #1
        jsr emit
        lda #0
        jsr emit
        pla
        jsr emit
strchk: ldx ip                  ; a string may not be followed by another literal
sk:     lda INBUF,x
        cmp #$20
        beq skn
        cmp #$09
        beq skn
        cmp #$27
        beq sdom
        jsr isnum
        bcs sdom
        jmp main
skn:    inx
        bne sk
        jmp main
sdom:   jmp err_dom

; --- numbers ---------------------------------------------------------------

number: lda #<SBUF
        sta tp
        lda #>SBUF
        sta tp+1
        lda #0
        sta ncount
nloop:  jsr parsenum
        bcc nok
        rts
nok:    ldy #0
        lda nm
        sta (tp),y
        iny
        lda nm+1
        sta (tp),y
        iny
        lda ns
        sta (tp),y
        jsr tpadv
        inc ncount
        ldx ip
nk:     lda INBUF,x
        cmp #$20
        beq nkn
        cmp #$09
        beq nkn
        cmp #$27
        beq ndom
        jsr isnum
        bcc nend
        stx ip
        jmp nloop
nkn:    inx
        bne nk
nend:   jmp emitlit
ndom:   jmp err_dom

tpadv:  clc
        lda tp
        adc #3
        sta tp
        bcc tpa1
        inc tp+1
tpa1:   rts

; Parse one number at ip into nm/ns; ip moves past it.
parsenum:
        lda #0
        sta ns
        sta nm
        sta nm+1
        ldx ip
        lda INBUF,x
        cmp #$90
        bne pn1
        lda #$80
        sta ns
        inx
        lda INBUF,x
pn1:    cmp #'.'
        bne pn2
        lda INBUF+1,x           ; .5 style: recognised but not implemented
        sec
        sbc #'0'
        cmp #10
        bcs pnsyn
        jmp err_nonce
pn2:    sec
        sbc #'0'
        cmp #10
        bcs pnsyn
pdig:   jsr accdig
        bcs pnovf
        inx
        lda INBUF,x
        sec
        sbc #'0'
        cmp #10
        bcc pdig
        lda INBUF,x
        cmp #'.'
        beq pnovf
        ora #$20
        cmp #'e'
        bne pnend
        lda INBUF+1,x           ; an exponent needs a digit, or high-minus digit
        cmp #$90
        bne pe1
        lda INBUF+2,x
pe1:    sec
        sbc #'0'
        cmp #10
        bcs pnend
pnovf:  jmp err_nonce
pnend:  stx ip
        lda nm
        ora nm+1
        bne pn3
        sta ns                  ; high-minus zero is zero
pn3:    clc
        rts
pnsyn:  jmp err_syn

; nm = nm*10 + A; carry set if it no longer fits 16 bits
accdig: sta dgt
        asl nm
        rol nm+1
        bcs adovf
        lda nm
        sta t2
        lda nm+1
        sta t2+1
        asl nm
        rol nm+1
        bcs adovf
        asl nm
        rol nm+1
        bcs adovf
        clc
        lda nm
        adc t2
        sta nm
        lda nm+1
        adc t2+1
        sta nm+1
        bcs adovf
        clc
        lda nm
        adc dgt
        sta nm
        bcc adok
        inc nm+1
        beq adovf
adok:   clc
        rts
adovf:  sec
        rts

; class of the element in nm/ns: 0 BOOL, 2 INT, 3 FLOAT
elemclass:
        lda nm+1
        bne ec_hi
        lda ns
        bne ec_int
        lda nm
        cmp #2
        bcc ec_bool
ec_int: lda #2
        rts
ec_bool:
        lda #0
        rts
ec_hi:  cmp #$80
        bcc ec_int
        bne ec_flt
        lda ns                  ; $80xx fits only as -32768
        beq ec_flt
        lda nm
        bne ec_flt
        beq ec_int
ec_flt: lda #3
        rts

; load the element at tp into nm/ns
ldelem: ldy #0
        lda (tp),y
        sta nm
        iny
        lda (tp),y
        sta nm+1
        iny
        lda (tp),y
        sta ns
        rts

; Emit the strand as one literal: narrowest type, scalar if one element.
emitlit:
        lda #<SBUF
        sta tp
        lda #>SBUF
        sta tp+1
        lda #0
        sta cls
        lda ncount
        sta cc
cl:     jsr ldelem
        jsr elemclass
        cmp cls
        bcc cl2
        sta cls
cl2:    jsr tpadv
        dec cc
        bne cl

        lda #T_LIT
        jsr emit
        lda cls
        ldx ncount
        cpx #1
        beq hd1
        ora #$04
hd1:    jsr emit
        lda ncount
        jsr emit
        lda #0
        jsr emit
        lda ncount
        cmp #1
        beq hd2
        jsr emit
        lda #0
        jsr emit
hd2:    lda #<SBUF
        sta tp
        lda #>SBUF
        sta tp+1
        lda ncount
        sta cc
tdl:     jsr ldelem
        lda cls
        beq dbool
        cmp #2
        beq dint
        lda nm
        sta ia
        lda nm+1
        sta ia+1
        lda ns
        sta sgn
        jsr m_to_f
        lda fa
        jsr emit
        lda fa+1
        jsr emit
        lda fa+2
        jsr emit
        jmp dnext
dint:   lda ns
        bpl dipos
        sec
        lda #0
        sbc nm
        sta nm
        lda #0
        sbc nm+1
        sta nm+1
dipos:  lda nm
        jsr emit
        lda nm+1
        jsr emit
        jmp dnext
dbool:  lda nm
        jsr emit
dnext:  jsr tpadv
        dec cc
        bne tdl
        jmp main

; --- names -------------------------------------------------------------------

name:   stx ns0
nm1:    inx
        lda INBUF,x
        jsr isnamec
        bcs nm1
        stx ip
        txa
        sec
        sbc ns0
        sta nlen
        lda #<SYMTAB
        sta sp
        lda #>SYMTAB
        sta sp+1
        lda #0
        sta ki
        sta ki+1
lk:     lda ki
        cmp symcnt
        bne lk1
        lda ki+1
        cmp symcnt+1
        beq lknew
lk1:    ldy #0
        lda (sp),y
        cmp nlen
        bne lknext
        ldy #1
        ldx ns0
        lda nlen
        sta cc
lkc:    lda INBUF,x
        cmp (sp),y
        bne lknext
        inx
        iny
        dec cc
        bne lkc
lkfound:
        lda #T_NAME
        jsr emit
        lda ki
        jsr emit
        jmp main
lknext: ldy #0
        lda (sp),y
        sec
        adc sp
        sta sp
        bcc lkn2
        inc sp+1
lkn2:   inc ki
        bne lk
        inc ki+1
        jmp lk
lknew:  lda symcnt+1            ; 256 names is the limit
        bne lklimit
        lda sp+1
        cmp #SYMEND_HI
        bcs lklimit
        ldy #0
        lda nlen
        sta (sp),y
        ldx ns0
        ldy #1
        lda nlen
        sta cc
lkw:    lda INBUF,x
        sta (sp),y
        inx
        iny
        dec cc
        bne lkw
        inc symcnt
        bne lkfound
        inc symcnt+1
        jmp lkfound
lklimit:
        lda #E_LIMIT
        sec
        rts
