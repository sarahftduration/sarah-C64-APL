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
        sta cdepth
        sta cfh
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
; When collecting is not enough, arrays that only a variable holds are moved to the REU (see below).
hlim:   .word HEAP_LIMIT        ; the top of the heap (a variable so that the tests can make it small)

alloc:  jsr alloc_try
        bcc alok
        jsr gc
        jsr alloc_try
        bcc alok
        lda reu_banks           ; still no room: with an REU, move arrays out of the way
        beq alfail
        jsr spill_for
        jsr alloc_try
alok:   rts
alfail: lda #E_WSFULL
        sec
        rts

alloc_try:
        clc
        lda htop
        adc asz
        sta t0
        lda htop+1
        adc asz+1
        sta t0+1
        bcs afull
        lda hlim
        cmp t0
        lda hlim+1
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
        lda #2                  ; marks: 2 = in use (on the stack, pinned, or a function's block), 1 = only a variable holds it
        sta gmk
        lda hpinf
        beq gc0
        ldx hpin
        lda #2
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
gcvars: lda #1
        sta gmk
        lda #<VARS
        sta gp
        lda #>VARS
        sta gp+1
gcw:    jsr gcmark
        lda gp+1
        cmp #>(VARS+1024)
        bne gcw
        jsr gccompact
        ldx #0                  ; a spilled array nothing refers to any more goes
gcs:    lda HTH,x
        cmp #$ff
        bne gcs1
        lda HM,x
        bne gcs1
        lda #0
        sta HTH,x
gcs1:   inx
        bne gcs
        rts

gmk:    .byte 0

; mark the cell at gp if it is an array; advance gp by one cell
gcmark: ldy #0
        lda (gp),y
        bmi gcm2
        sta gt
        and #$0c
        beq gcm2
        iny
        lda (gp),y
        tax
        lda gt
        and #$10                ; (TAG_FN) a function's code runs where it is: never moved out
        beq gm_v
        lda #2
        bne gm_o
gm_v:   lda gmk
gm_o:   ora HM,x
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
gcfree: lda HTH,x
        cmp #$ff                ; (an array that has just been moved out: its handle stays)
        beq gcnext
        lda #0
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
pushcv: lda cv                  ; an array that has been moved out to the REU comes back before it goes on the stack:
        bmi pc0                 ; whatever is on the stack is always in the heap
        and #$0c
        beq pc0
        ldx cv+1
        lda HTH,x
        cmp #$ff
        bne pc0
        jsr fault_in
        bcc pc0
        rts
pc0:    lda vsp+1
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
        lda HTH,x
        cmp #$ff
        bne gv_ok
        jmp spill_bug           ; (an array in the REU where the heap is expected: never happens; the tests trap here)
gv_ok:
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
        bcc nafull
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

; --- arrays in the REU ------------------------------------------------------------------------------------------------
; When collecting garbage does not make room, arrays that only a variable holds (gc marks them 1) are moved to the REU: each
; handle has a 16 KB slot there (bank 1 on, four handles to a bank), so where a spilled array is needs no table. A spilled
; array has HTH = $ff and no block in the heap; pushcv (and ensure_res) bring it back into the heap, and its handle number stays.
; Everything on the value stack is in the heap, so a routine that has looked at its operands can allocate without them moving
; out from under it. Functions' blocks (run in place) are never moved. Without an REU (reu_banks = 0) nothing changes.

spl_h:   .byte 0
spl_fr:  .word 0                ; bytes freed by the arrays moved out so far
spl_bx:  .byte 0                ; the best victim so far, and its block size
spl_bs:  .word 0
spl_any: .byte 0
spl_mv:  .byte 0                ; something was moved out in this round
fi_h:    .byte 0                ; (fault_in's own: the spilling inside alloc uses spl_h)
spl_hdr: .byte 0, 0, 0, 0       ; a spilled block's first bytes (a dummy handle byte, tag, count)

spill_bug:
        jmp spill_bug

; REU_ADDR = the slot of handle A; carry set if the REU is too small to have one. Keeps X and Y.
spl_slot:
        pha
        lsr
        lsr
        clc
        adc #1
        cmp reu_banks
        bcs ss_no
        sta REU_ADDR+2
        pla
        and #3
        asl
        asl
        asl
        asl
        asl
        asl
        sta REU_ADDR+1
        lda #0
        sta REU_ADDR
        clc
        rts
ss_no:  pla
        sec
        rts

; the biggest array only a variable holds and the REU has a slot for: carry clear, X = its handle, spl_bs = its block size
spill_pick:
        lda #0
        sta spl_bs
        sta spl_bs+1
        sta spl_any
        ldx #0
sp_l:   lda HM,x
        cmp #1
        bne sp_n
        lda HTH,x
        beq sp_n
        cmp #$ff
        beq sp_n
        txa
        jsr spl_slot
        bcs sp_n
        stx spl_h
        sec
        lda HTL,x
        sbc #1
        sta gsrc
        lda HTH,x
        sbc #0
        sta gsrc+1
        jsr blocksize
        ldx spl_h
        lda gsz+1
        cmp spl_bs+1
        bcc sp_n
        bne sp_b
        lda gsz
        cmp spl_bs
        bcc sp_n
        beq sp_n
sp_b:   lda gsz
        sta spl_bs
        lda gsz+1
        sta spl_bs+1
        stx spl_bx
        inc spl_any
sp_n:   inx
        bne sp_l
        lda spl_any
        beq sp_none
        ldx spl_bx
        clc
        rts
sp_none: sec
        rts

; move array X (its block size in spl_bs) to its slot; its block stays in the heap until the next compaction
spill_out:
        stx spl_h
        txa
        jsr spl_slot
        ldx spl_h
        lda HTL,x
        sta REU_C64
        lda HTH,x
        sta REU_C64+1
        sec
        lda spl_bs
        sbc #1
        sta REU_LEN
        lda spl_bs+1
        sbc #0
        sta REU_LEN+1
        jsr reu_stash
        ldx spl_h
        lda #$ff
        sta HTH,x
        lda #0
        sta HM,x
        clc
        lda spl_fr
        adc spl_bs
        sta spl_fr
        lda spl_fr+1
        adc spl_bs+1
        sta spl_fr+1
        rts

; make room for asz bytes: move arrays out until the free space plus what they take would do, then compact
spill_for:
        lda #0
        sta spl_fr
        sta spl_fr+1
        sta spl_mv
sf_l:   sec
        lda hlim
        sbc htop
        sta t0
        lda hlim+1
        sbc htop+1
        sta t0+1
        clc
        lda t0
        adc spl_fr
        sta t0
        lda t0+1
        adc spl_fr+1
        sta t0+1
        lda t0
        cmp asz
        lda t0+1
        sbc asz+1
        bcs sf_done
        jsr spill_pick
        bcs sf_done
        jsr spill_out
        lda #1
        sta spl_mv
        jmp sf_l
sf_done:
        lda spl_mv
        beq sf_r
        jsr gccompact
sf_r:   rts

; X = a spilled array's handle: bring it back into the heap, under the same handle. Carry set (A = WS FULL) if there is no room.
fault_in:
        stx fi_h
        txa
        jsr spl_slot
        lda #<(spl_hdr+1)
        sta REU_C64
        lda #>(spl_hdr+1)
        sta REU_C64+1
        lda #3
        sta REU_LEN
        lda #0
        sta REU_LEN+1
        jsr reu_fetch
        lda #<spl_hdr
        sta gsrc
        lda #>spl_hdr
        sta gsrc+1
        jsr blocksize
        lda gsz
        sta asz
        lda gsz+1
        sta asz+1
        jsr alloc
        bcc fi_1
        rts
fi_1:   ldx hnew                ; the handle alloc chose is not wanted: the array keeps its own
        lda #0
        sta HTH,x
        ldx fi_h
        ldy #0
        txa
        sta (hadr),y
        clc
        lda hadr
        adc #1
        sta HTL,x
        lda hadr+1
        adc #0
        sta HTH,x
        txa
        jsr spl_slot            ; (alloc may have used the DMA registers to move other arrays out)
        ldx fi_h
        lda HTL,x
        sta REU_C64
        lda HTH,x
        sta REU_C64+1
        sec
        lda asz
        sbc #1
        sta REU_LEN
        lda asz+1
        sbc #0
        sta REU_LEN+1
        jsr reu_fetch
        ldx fi_h
        clc
        rts

; the cell at cptr: if it is an array that is in the REU, bring it back (for code that reads variables directly)
ensure_res:
        ldy #0
        lda (cptr),y
        bmi er_ok
        and #$0c
        beq er_ok
        iny
        lda (cptr),y
        tax
        lda HTH,x
        cmp #$ff
        bne er_ok
        jmp fault_in
er_ok:  clc
        rts
