; Tokenizer, stage 1. Spec: apl64.py Interp.tokenize and DESIGN.md.
;
; tok_init   empty the symbol table.
; tokenize   In:  INBUF holds one line in charset codes, ended by $00
;                 (at most 255 bytes before the terminator).
;            Out: carry clear: the token stream is at OUTBUF, ended by $00 (op
;                 points just past it).
;                 carry set: A = error code (E_*).
;
; Numbers: integers become BOOL/INT when they fit int16, everything else FLOAT.
; Decimal values keep 9 significant digits and are scaled by a table power of
; ten, so they are within 1 ulp of the model (exact for 0 <= exponent <= 13).

        .include "int16.inc"

SYMEND_HI = >(SYMTAB+SYMTAB_SIZE)-1      ; a name may run into the next page

E_SYNTAX = 1
E_DOMAIN = 2
E_LIMIT  = 3

T_END   = 0
T_LIT   = 1
T_EMPTY = 12
T_NAME  = 2

ip      = $0e           ; input index
ncount  = $4a           ; elements in the strand
t2      = WS+$59           ; scratch (2)
dgt     = $3e
scnt    = $4b           ; string length
cls     = $8e           ; strand element class: 0 BOOL, 2 INT, 3 FLOAT
symcnt  = WS+$5e           ; names defined (2)
ki      = WS+$62           ; symbol index (2)
nlen      = $8f           ; name length
ns0     = WS+$65           ; name start in INBUF
cc      = $0f           ; loop counter
chr     = WS+$67
dv      = WS+$68           ; decimal digits read so far, up to 9 (4 bytes)
dvt     = WS+$6c           ; scratch copy of dv (4)
nsig    = $44           ; digits kept in dv
e10     = $8c           ; decimal exponent of dv (2, signed)
inex    = $fb           ; a nonzero digit was dropped
dot     = WS+$74           ; decimal point seen
xv      = $2a           ; explicit exponent magnitude, saturating (2)
xneg    = WS+$77
nm      = $06           ; parsed element, 4 bytes: nm (2), ns, nf
ns      = $2f           ; nf=0: nm = magnitude, ns bit 7 = sign (never set for 0)
nf      = $45           ; nf=1: nm, nm+1, ns = float24 bytes
ovfl    = WS+$7c           ; a float in this strand overflowed
psg     = WS+$7d           ; sign of the number being parsed
ee      = $85           ; total decimal exponent (2, signed)
ec      = WS+$80           ; counter (2)
pp      = $76           ; 64-bit product
tm      = WS+$98           ; table mantissa (4)
tb      = WS+$9c           ; table binary exponent (2)
acnt    = WS+$9e           ; left shifts used to normalize dv
dql     = WS+$a0           ; quotient (2)

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
        cmp #$94                ; empty numeric vector: one byte (the evaluator makes the array)
        bne m3
        lda #T_EMPTY
        jsr emit
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
        .byte $8d, $8d, $8e, $8e, '|', $8f, $99, $90, $9a, $91, '~', $92, $9b, $93, $9c, $94, $9d, $95, $9e, $96, $9f, $97, $a0, $98, $a1, $99
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
; A strand element is 4 bytes: nm (2), ns, nf.
;   nf = 0: integer, magnitude nm, sign in bit 7 of ns (never set for zero)
;   nf = 1: float24, bytes nm, nm+1, ns

number: lda #<SBUF
        sta tp
        lda #>SBUF
        sta tp+1
        lda #0
        sta ncount
        sta ovfl
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
        iny
        lda nf
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
        adc #4
        sta tp
        bcc tpa1
        inc tp+1
tpa1:   rts

; Parse one number at ip into nm/ns/nf; ip moves past it.
; Grammar (as the model): [¯] digits [. digits] [e [¯] digits] or [¯] . digits [e ...]
; The mantissa keeps 9 significant digits in dv with decimal exponent e10;
; a nonzero digit beyond that sets inex.
parsenum:
        lda #0
        sta psg
        sta dv
        sta dv+1
        sta dv+2
        sta dv+3
        sta nsig
        sta e10
        sta e10+1
        sta inex
        sta dot
        sta xv
        sta xv+1
        sta xneg
        ldx ip
        lda INBUF,x
        cmp #$90
        bne pn1
        lda #$80
        sta psg
        inx
        lda INBUF,x
pn1:    cmp #'.'
        bne pn2
        lda INBUF+1,x
pn2:    sec
        sbc #'0'
        cmp #10
        bcc pl
        jmp err_syn
pl:     lda INBUF,x
        cmp #'.'
        bne pl1
        lda dot
        bne pend
        lda #1
        sta dot
        inx
        jmp pl
pl1:    sec
        sbc #'0'
        cmp #10
        bcs pend
        jsr digit
        inx
        jmp pl

pend:   lda INBUF,x             ; an exponent needs a digit, or high-minus digit
        ora #$20
        cmp #'e'
        bne pfin
        lda INBUF+1,x
        cmp #$90
        bne pe1
        lda INBUF+2,x
pe1:    sec
        sbc #'0'
        cmp #10
        bcs pfin
        inx
        lda INBUF,x
        cmp #$90
        bne pe2
        lda #1
        sta xneg
        inx
pe2:    lda INBUF,x
        sec
        sbc #'0'
        cmp #10
        bcs pfin
        jsr xacc
        inx
        jmp pe2

pfin:   stx ip
        lda nsig
        bne pnz
pzero:  lda #0                  ; all digits were zero
        sta nm
        sta nm+1
        sta ns
        sta nf
        clc
        rts
pnz:    lda xv+1                ; the model: |explicit exponent| > 400 is
        cmp #2                  ; DOMAIN ERROR if positive, zero if negative
        bcs pbig
        cmp #1
        bcc pxok
        lda xv
        cmp #145
        bcc pxok
pbig:   lda xneg
        bne pzero
        jmp err_dom
pxok:   lda xneg
        bne pxn
        clc
        lda e10
        adc xv
        sta ee
        lda e10+1
        adc xv+1
        sta ee+1
        jmp pe3
pxn:    sec
        lda e10
        sbc xv
        sta ee
        lda e10+1
        sbc xv+1
        sta ee+1

; integer valued and <= 65535? then it is an integer element, exactly.
; Strip trailing zeros while the exponent is negative, then scale up.
pe3:    lda inex
        bne pflt
pstrip: lda ee+1
        bpl pint
        ldx #3
psv:    lda dv,x
        sta dvt,x
        dex
        bpl psv
        jsr divmod10
        cmp #0
        bne prest
        inc ee
        bne pstrip
        inc ee+1
        jmp pstrip
prest:  ldx #3
prl:    lda dvt,x
        sta dv,x
        dex
        bpl prl
        jmp pflt
pint:   lda dv+3
        ora dv+2
        bne pflt
        lda dv
        sta nm
        lda dv+1
        sta nm+1
        lda ee
        sta ec
        lda ee+1
        sta ec+1
pil:    lda ec
        ora ec+1
        beq pidone
        lda #0
        jsr accdig              ; nm = nm * 10
        bcs pflt
        lda ec
        bne pid1
        dec ec+1
pid1:   dec ec
        jmp pil
pidone: lda psg
        sta ns
        lda #0
        sta nf
        clc
        rts

; float: value = dv * 10^ee. Normalize dv to 32 bits, multiply by the table
; entry (32x32 -> 64), then round and pack like f_mul.
pflt:   lda ee+1
        bmi pfneg
        bne pfo
        lda ee
        cmp #39
        bcs pfo
        clc
        adc #47
        tax
        jmp pftab
pfo:    jmp pfover
pfu:    jmp pfunder
pdv:    jmp pdiv
pfneg:  cmp #$ff
        bne pfu
        lda ee
        cmp #209                ; -47
        bcc pfu
        cmp #243                ; -13..-1 divide exactly by 10^-ee
        bcs pdv
        clc
        adc #47
        tax
pftab:  jsr pnorm
        lda p10m0,x
        sta tm
        lda p10m1,x
        sta tm+1
        lda p10m2,x
        sta tm+2
        lda p10m3,x
        sta tm+3
        lda p10bl,x
        sta tb
        lda p10bh,x
        sta tb+1
        jsr mul32
        clc                     ; exponent = 192 + tb - acnt (+ shifts below)
        lda tb
        adc #192
        sta ex
        lda tb+1
        adc #0
        sta ex+1
        sec
        lda ex
        sbc acnt
        sta ex
        lda ex+1
        sbc #0
        sta ex+1
        lda pp+7
        bmi pn3
        asl pp
        rol pp+1
        rol pp+2
        rol pp+3
        rol pp+4
        rol pp+5
        rol pp+6
        rol pp+7
        lda ex
        bne pn4
        dec ex+1
pn4:    dec ex
pn3:    lda pp+7
        sta ah
        lda pp+6
        sta al
        lda pp+5
        sta ag
        lda pp+4                ; everything below the guard byte: sticky
        ora pp+3
        ora pp+2
        ora pp+1
        ora pp
        ora inex
        beq pn5
        lda ag
        ora #1
        sta ag
pn5:    lda psg
        sta sa
        jsr round
        bcs pfover
        lda fa
        sta nm
        lda fa+1
        sta nm+1
        lda fa+2
        sta ns
        lda #1
        sta nf
        clc
        rts
pfover: lda #1                  ; reported when the strand ends
        sta ovfl
pfunder:
        lda #0                  ; underflow: float zero
        sta nm
        sta nm+1
        sta ns
        lda #1
        sta nf
        clc
        rts

; normalize dv into pp (32 bits, top bit set); acnt = shifts used
pnorm:  lda dv
        sta pp
        lda dv+1
        sta pp+1
        lda dv+2
        sta pp+2
        lda dv+3
        sta pp+3
        lda #0
        sta acnt
pnl:    lda pp+3
        bmi pnd
        asl pp
        rol pp+1
        rol pp+2
        rol pp+3
        inc acnt
        jmp pnl
pnd:    rts

; Exact division by 10^k (k = 1..13; the table mantissa is exact): a 17-bit
; quotient by restoring division, remainder as the sticky bit. Same scheme as
; f_div: exponent = 128 - tb - acnt, plus 1 when the dividend is >= the divisor.
pdiv:   eor #$ff                ; A = ee low byte; k = -ee
        clc
        adc #1
        clc
        adc #47
        tax
        jsr pnorm
        lda p10m0,x
        sta tm
        lda p10m1,x
        sta tm+1
        lda p10m2,x
        sta tm+2
        lda p10m3,x
        sta tm+3
        lda p10bl,x
        sta tb
        lda p10bh,x
        sta tb+1
        sec
        lda #128
        sbc tb
        sta ex
        lda #0
        sbc tb+1
        sta ex+1
        sec
        lda ex
        sbc acnt
        sta ex
        lda ex+1
        sbc #0
        sta ex+1
        jsr cmp32
        bcc pdsm
        inc ex
        bne pdg1
        inc ex+1
pdg1:   jsr sub32
        jmp pdgo
pdsm:   asl pp
        rol pp+1
        rol pp+2
        rol pp+3
        jsr sub32
pdgo:   lda #0
        sta dql
        sta dql+1
        lda #16
        sta cc
pdl:    asl pp
        rol pp+1
        rol pp+2
        rol pp+3
        bcs pdsub
        jsr cmp32
        bcc pdno
pdsub:  jsr sub32
        sec
        bcs pdins
pdno:   clc
pdins:  rol dql
        rol dql+1
        dec cc
        bne pdl
        sec                     ; the implicit leading quotient bit
        ror dql+1
        ror dql
        lda #0
        bcc pdg2
        lda #$80                ; guard bit
pdg2:   sta ag
        lda dql+1
        sta ah
        lda dql
        sta al
        lda pp
        ora pp+1
        ora pp+2
        ora pp+3
        ora inex
        beq pdrnd
        lda ag
        ora #1
        sta ag
pdrnd:  jmp pn5

; carry set if pp >= tm (32 bits)
cmp32:  lda pp+3
        cmp tm+3
        bne c32r
        lda pp+2
        cmp tm+2
        bne c32r
        lda pp+1
        cmp tm+1
        bne c32r
        lda pp
        cmp tm
c32r:   rts

sub32:  sec
        lda pp
        sbc tm
        sta pp
        lda pp+1
        sbc tm+1
        sta pp+1
        lda pp+2
        sbc tm+2
        sta pp+2
        lda pp+3
        sbc tm+3
        sta pp+3
        rts

; digit A joins the mantissa
digit:  sta dgt
        lda dot
        bne dfrac
        lda nsig
        cmp #9
        bcs dintdrop
        lda nsig
        bne dkeep
        lda dgt
        beq dret                ; leading zero
dkeep:  jsr dvmul10add
        inc nsig
dret:   rts
dintdrop:
        inc e10
        bne dret
        inc e10+1
        rts
dfrac:  lda nsig
        cmp #9
        bcs dfdrop
        lda nsig
        bne dfkeep
        lda dgt
        bne dfkeep
        jmp dfdec               ; leading zero after the point
dfkeep: jsr dvmul10add
        inc nsig
dfdec:  lda e10
        bne dfd1
        dec e10+1
dfd1:   dec e10
        rts
dfdrop: lda dgt
        beq dret
        lda #1
        sta inex
        rts

; dv = dv*10 + dgt
dvmul10add:
        asl dv
        rol dv+1
        rol dv+2
        rol dv+3
        lda dv                  ; (X holds the input index here)
        sta dvt
        lda dv+1
        sta dvt+1
        lda dv+2
        sta dvt+2
        lda dv+3
        sta dvt+3
        asl dv
        rol dv+1
        rol dv+2
        rol dv+3
        asl dv
        rol dv+1
        rol dv+2
        rol dv+3
        clc
        lda dv
        adc dvt
        sta dv
        lda dv+1
        adc dvt+1
        sta dv+1
        lda dv+2
        adc dvt+2
        sta dv+2
        lda dv+3
        adc dvt+3
        sta dv+3
        clc
        lda dv
        adc dgt
        sta dv
        bcc dm3
        inc dv+1
        bne dm3
        inc dv+2
        bne dm3
        inc dv+3
dm3:    rts

; dv = dv / 10, remainder in A
divmod10:
        lda #0
        ldx #32
dq1:    asl dv
        rol dv+1
        rol dv+2
        rol dv+3
        rol
        cmp #10
        bcc dq2
        sbc #10
        inc dv
dq2:    dex
        bne dq1
        rts

; xv = xv*10 + A, saturating once it is well past 400
xacc:   sta dgt
        lda xv+1
        cmp #3
        bcs xdone
        asl xv
        rol xv+1
        lda xv
        sta t2
        lda xv+1
        sta t2+1
        asl xv
        rol xv+1
        asl xv
        rol xv+1
        clc
        lda xv
        adc t2
        sta xv
        lda xv+1
        adc t2+1
        sta xv+1
        clc
        lda xv
        adc dgt
        sta xv
        bcc xdone
        inc xv+1
xdone:  rts

; pp = pp(32 bits) * tm(32 bits), 64-bit result
mul32:  lda #0
        sta pp+4
        sta pp+5
        sta pp+6
        sta pp+7
        ldx #32
m32:    clc
        lda pp
        and #1
        beq m32s
        clc
        lda pp+4
        adc tm
        sta pp+4
        lda pp+5
        adc tm+1
        sta pp+5
        lda pp+6
        adc tm+2
        sta pp+6
        lda pp+7
        adc tm+3
        sta pp+7
m32s:   ror pp+7
        ror pp+6
        ror pp+5
        ror pp+4
        ror pp+3
        ror pp+2
        ror pp+1
        ror pp
        dex
        bne m32
        rts

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

; class of the element in nm/ns/nf: 0 BOOL, 2 INT, 3 FLOAT
elemclass:
        lda nf
        bne ec_flt
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

; load the element at tp into nm/ns/nf
ldelem: ldy #0
        lda (tp),y
        sta nm
        iny
        lda (tp),y
        sta nm+1
        iny
        lda (tp),y
        sta ns
        iny
        lda (tp),y
        sta nf
        rts

; Emit the strand as one literal: narrowest type, scalar if one element.
emitlit:
        lda ovfl
        beq el0
        jmp err_dom             ; a value was too large for float24
el0:    lda #<SBUF
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
tdl:    jsr ldelem
        lda cls
        beq dbool
        cmp #2
        beq dint
        lda nf
        bne dfl
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
dfl:    lda nm
        jsr emit
        lda nm+1
        jsr emit
        lda ns
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

        .include "pow10.inc"
