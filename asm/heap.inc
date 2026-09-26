; Heap, value cells, value stack. Included by eval.asm.
;
; Cell (4 bytes): tag, b1, b2, b3.
;   tag = type | rank<<2  (the same byte as an array header)
;   rank 0: a scalar, its data in b1..b3 (BOOL/CHAR 1 byte, INT 2, FLOAT 3)
;   rank 1-2: an array; b1 = heap handle
;   tag $80: undefined (variables only)
;
; Heap block: [handle][array header + data], the header being exactly the
; array layout of DESIGN.md (type|rank, count, shape, data). HTL/HTH hold the
; address of each handle's *header* (block start + 1); HTH = 0 means free.
; Blocks are contiguous from HEAP_BASE to htop. gc() marks from the value
; stack, the variables and the pinned handle, then slides live blocks down.


; zero page (real hardware will need a budget; see DESIGN.md)
htop    = $46
hnew    = WS+$b2
asz     = $fc
hpin    = WS+$b7
hpinf   = WS+$b8
gdst    = $4c
gsz     = $2d
gh      = WS+$c5
gt      = WS+$c6
gn      = WS+$c7
t0      = $25
cv      = WS+$d0
vt      = $04
vrk     = $08
vn      = $02
vs0     = $37
vs1     = $34
nt      = $05
nrk     = $28
nn      = $0c
nd0     = $3f
nd1     = WS+$e6
wsmax   = WS+$e8
gw      = $87
vtag    = WS+$eb

WIDTHT: .byte 1, 1, 2, 3

heap_init:
        lda #<HEAP_BASE
        sta htop
        lda #>HEAP_BASE
        sta htop+1
        ldx #0
        lda #0
hi1:    sta HTH,x
        inx
        bne hi1
        sta hpinf
        sta defmode
        lda #<VSTACK
        sta vsp
        lda #>VSTACK
        sta vsp+1
        lda #<16000
        sta wsmax
        lda #>16000
        sta wsmax+1
        lda #<VARS
        sta gp
        lda #>VARS
        sta gp+1
        ldx #4                  ; 1024 bytes of cells
hi2:    ldy #0
hi3:    lda #$80
        sta (gp),y
        iny
        iny
        iny
        iny
        bne hi3
        inc gp+1
        dex
        bne hi2
        rts

; --- block size: in gsrc = block (or token) start; out gsz ---------------------
; 1 + 3 + 2*rank + count*width
blocksize:
        ldy #1
        lda (gsrc),y
        sta gt
        iny
        lda (gsrc),y
        sta gn
        iny
        lda (gsrc),y
        sta gn+1
        lda gt
        and #3
        tax
        lda WIDTHT,x
        sta gw
        lda gn
        sta gsz
        lda gn+1
        sta gsz+1
        lda gw
        cmp #2
        bcc bs1
        clc
        lda gsz
        adc gn
        sta gsz
        lda gsz+1
        adc gn+1
        sta gsz+1
        lda gw
        cmp #3
        bcc bs1
        clc
        lda gsz
        adc gn
        sta gsz
        lda gsz+1
        adc gn+1
        sta gsz+1
bs1:    lda gt
        lsr
        lsr
        and #3
        asl
        clc
        adc #4
        clc
        adc gsz
        sta gsz
        bcc bs2
        inc gsz+1
bs2:    rts

; --- alloc: in asz = block bytes; out carry clear: hnew, hadr; else A = error ---
alloc:  jsr alloc_try
        bcc alok
        jsr gc
        jsr alloc_try
alok:   rts

alloc_try:
        clc
        lda htop
        adc asz
        sta t0
        lda htop+1
        adc asz+1
        sta t0+1
        bcs afull
        lda #<HEAP_LIMIT
        cmp t0
        lda #>HEAP_LIMIT
        sbc t0+1
        bcc afull
        ldx #0
af1:    lda HTH,x
        beq afound
        inx
        bne af1
        lda #E_LIMIT            ; every handle is in use
        sec
        rts
afound: stx hnew
        clc
        lda htop
        adc #1
        sta HTL,x
        lda htop+1
        adc #0
        sta HTH,x
        lda htop
        sta hadr
        lda htop+1
        sta hadr+1
        ldy #0
        txa
        sta (hadr),y
        clc
        lda htop
        adc asz
        sta htop
        lda htop+1
        adc asz+1
        sta htop+1
        clc
        rts
afull:  lda #E_WSFULL
        sec
        rts

; --- gc ---------------------------------------------------------------------
gc:     ldx #0
        lda #0
gcm:    sta HM,x
        inx
        bne gcm
        lda hpinf
        beq gc0
        ldx hpin
        lda #1
        sta HM,x
gc0:    lda #<VSTACK
        sta gp
        lda #>VSTACK
        sta gp+1
gcv:    lda gp+1
        cmp vsp+1
        bne gcv1
        lda gp
        cmp vsp
        beq gcvars
gcv1:   jsr gcmark
        jmp gcv
gcvars: lda #<VARS
        sta gp
        lda #>VARS
        sta gp+1
gcw:    jsr gcmark
        lda gp+1
        cmp #>(VARS+1024)
        bne gcw
        jmp gccompact

; mark the cell at gp if it is an array; advance gp by one cell
gcmark: ldy #0
        lda (gp),y
        bmi gcm2
        and #$0c
        beq gcm2
        iny
        lda (gp),y
        tax
        lda #1
        sta HM,x
gcm2:   clc
        lda gp
        adc #4
        sta gp
        bcc gcm3
        inc gp+1
gcm3:   rts

gccompact:
        lda #<HEAP_BASE
        sta gsrc
        sta gdst
        lda #>HEAP_BASE
        sta gsrc+1
        sta gdst+1
gc1:    lda gsrc+1
        cmp htop+1
        bne gc1b
        lda gsrc
        cmp htop
        beq gcend
gc1b:   ldy #0
        lda (gsrc),y
        sta gh
        jsr blocksize
        ldx gh
        lda HM,x
        beq gcfree
        clc
        lda gdst
        adc #1
        sta HTL,x
        lda gdst+1
        adc #0
        sta HTH,x
        lda gsrc                ; slide the block down (ascending copy is safe)
        cmp gdst
        bne gccopy
        lda gsrc+1
        cmp gdst+1
        beq gcnocopy
gccopy: lda gsrc
        sta cs
        lda gsrc+1
        sta cs+1
        lda gdst
        sta cd
        lda gdst+1
        sta cd+1
        lda gsz
        sta t0
        lda gsz+1
        sta t0+1
        jsr memcpy_cs_cd
gcnocopy:
        clc
        lda gdst
        adc gsz
        sta gdst
        lda gdst+1
        adc gsz+1
        sta gdst+1
        jmp gcnext
gcfree: lda #0
        sta HTH,x
gcnext: clc
        lda gsrc
        adc gsz
        sta gsrc
        lda gsrc+1
        adc gsz+1
        sta gsrc+1
        jmp gc1
gcend:  lda gdst
        sta htop
        lda gdst+1
        sta htop+1
        rts

; copy t0 bytes from cs to cd, ascending; destroys cs, cd, t0
memcpy_cs_cd:
        ldy #0
        lda t0+1
        beq mcr
mcp:    lda (cs),y
        sta (cd),y
        iny
        bne mcp
        inc cs+1
        inc cd+1
        dec t0+1
        bne mcp
mcr:    lda t0
        beq mcx
mcl:    lda (cs),y
        sta (cd),y
        iny
        cpy t0
        bne mcl
mcx:    rts

; --- value stack ------------------------------------------------------------
pushcv: lda vsp+1
        cmp #>VSTACK_END
        bcs pcfull
        ldy #3
pc1:    lda cv,y
        sta (vsp),y
        dey
        bpl pc1
        clc
        lda vsp
        adc #4
        sta vsp
        bcc pc2
        inc vsp+1
pc2:    clc
        rts
pcfull: lda #E_LIMIT
        sec
        rts

topcell:
        sec
        lda vsp
        sbc #4
        sta cptr
        lda vsp+1
        sbc #0
        sta cptr+1
        rts

secondcell:
        sec
        lda vsp
        sbc #8
        sta cptr
        lda vsp+1
        sbc #0
        sta cptr+1
        rts

; the cell at cptr -> vt, vrk, vn, vs0, vs1, vp (element data pointer)
getval: ldy #0
        lda (cptr),y
        sta vtag
        and #3
        sta vt
        lda vtag
        lsr
        lsr
        and #3
        sta vrk
        bne gvarr
        lda #1
        sta vn
        lda #0
        sta vn+1
        sta vs0
        sta vs0+1
        sta vs1
        sta vs1+1
        clc
        lda cptr
        adc #1
        sta vp
        lda cptr+1
        adc #0
        sta vp+1
        rts
gvarr:  iny
        lda (cptr),y
        tax
        lda HTL,x
        sta gp
        lda HTH,x
        sta gp+1
        ldy #1
        lda (gp),y
        sta vn
        iny
        lda (gp),y
        sta vn+1
        iny
        lda (gp),y
        sta vs0
        iny
        lda (gp),y
        sta vs0+1
        lda vrk
        cmp #2
        beq gv2
        lda #0
        sta vs1
        sta vs1+1
        clc
        lda gp
        adc #5
        sta vp
        lda gp+1
        adc #0
        sta vp+1
        rts
gv2:    iny
        lda (gp),y
        sta vs1
        iny
        lda (gp),y
        sta vs1+1
        clc
        lda gp
        adc #7
        sta vp
        lda gp+1
        adc #0
        sta vp+1
        rts

; --- newarr: in nt, nrk (1-2), nn, nd0, nd1 --------------------------------------
; out: carry clear: dp = data pointer, cv = result cell, handle pinned.
;      carry set: A = E_WSFULL / E_LIMIT.
newarr: ldx nt
        lda WIDTHT,x
        sta gw
        lda nn
        sta t0
        lda nn+1
        sta t0+1
        lda #0
        sta t0+2
        lda gw
        cmp #2
        bcc na1
        clc
        lda t0
        adc nn
        sta t0
        lda t0+1
        adc nn+1
        sta t0+1
        lda t0+2
        adc #0
        sta t0+2
        lda gw
        cmp #3
        bcc na1
        clc
        lda t0
        adc nn
        sta t0
        lda t0+1
        adc nn+1
        sta t0+1
        lda t0+2
        adc #0
        sta t0+2
na1:    lda t0+2
        beq *+5
        jmp nafull
        lda wsmax
        cmp t0
        lda wsmax+1
        sbc t0+1
        bcs *+5
        jmp nafull
        lda nrk
        asl
        clc
        adc #4
        clc
        adc t0
        sta asz
        lda t0+1
        adc #0
        sta asz+1
        jsr alloc
        bcs naret
        ldy #1
        lda nrk
        asl
        asl
        ora nt
        sta (hadr),y
        iny
        lda nn
        sta (hadr),y
        iny
        lda nn+1
        sta (hadr),y
        iny
        lda nd0
        sta (hadr),y
        iny
        lda nd0+1
        sta (hadr),y
        lda nrk
        cmp #2
        bne na2
        iny
        lda nd1
        sta (hadr),y
        iny
        lda nd1+1
        sta (hadr),y
na2:    lda nrk
        asl
        clc
        adc #4
        clc
        adc hadr
        sta dp
        lda hadr+1
        adc #0
        sta dp+1
        lda hnew
        sta hpin
        lda #1
        sta hpinf
        lda nrk
        asl
        asl
        ora nt
        sta cv
        lda hnew
        sta cv+1
        lda #0
        sta cv+2
        sta cv+3
        clc
naret:  rts
nafull: lda #E_WSFULL
        sec
        rts
