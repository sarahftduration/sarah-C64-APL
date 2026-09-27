; Sprites: ⎕SPD (define a shape), ⎕SPR (put a sprite somewhere, switch sprites on and off), ⎕SPC (the colours multicolor sprites share):
; an overlay (see overlay.inc), entered through s_sprm (monadic) and s_sprd (dyadic) with A = the function number 8 SPD, 9 SPR, 10 SPC.
; Spec: apl64.py, Sprites. gfxcom.inc is included as in the other graphics overlays.
;
; The 28 shapes are 64 bytes each, in the RAM under the I/O area ($D800-$DEFF, seen by the VIC-II as pointers 96 to 123); the pointers
; are the last 8 bytes of screen RAM ($CFF8).

g3      .block
p_sprm: cmp #9
        beq gsp_m9
        cmp #10
        beq gsp_m10
        jmp gq_nonce
gsp_m9: jmp m_spr
gsp_m10: jmp m_spc
p_sprd: cmp #8
        beq gsp_d8
        cmp #9
        beq gsp_d9
        jmp gq_nonce
gsp_d8: jmp d_spd
gsp_d9: jmp d_spr

        .include "gfxcom.inc"

gq_bit: .byte 1, 2, 4, 8, 16, 32, 64, 128
gq_sp:  .fill 10                ; the numbers of ⎕SPR: x y shape colour flags
gq_spn: .byte 0                 ; the sprite
gq_si:  .byte 0
gq_xp:  .word 0                 ; ⎕SPR: the numbers' data, type and count; ⎕SPD: the shape's
gq_xt:  .byte 0
gq_xn:  .word 0
gq_rk:  .byte 0                 ; ⎕SPD: the shape's rank, and its two lengths
gq_s0:  .word 0
gq_s1:  .word 0
gq_slot: .byte 0
gq_ee:  .byte 0                 ; elements to a byte, bits to an element, and the element's largest value + 1 (0: 255)
gq_bb:  .byte 0
gq_mx:  .byte 0
gq_left: .byte 0
gq_acc: .byte 0
gq_kb:  .byte 0
gq_pass: .byte 0

; --- ⎕SPR mask ------------------------------------------------------------------------------------------------------------
m_spr:  jsr gq_top
        jsr gq_type
        bcc gsr_1
        rts
gsr_1:  lda #1
        jsr gq_isn
        bcc gsr_2
        rts
gsr_2:  lda vp
        sta ep
        lda vp+1
        sta ep+1
        jsr gq_elem
        lda gq_v+1
        beq gsr_3
        lda #E_DOMAIN
        sec
        rts
gsr_3:  lda gq_v
        sta $d015
        jmp gq_ret1

; --- ⎕SPC a b ------------------------------------------------------------------------------------------------------------------
m_spc:  jsr gq_top
        jsr gq_type
        bcc gsc_1
        rts
gsc_1:  lda #2
        jsr gq_isn
        bcc gsc_2
        rts
gsc_2:  ldx #0
        jsr gq_readn
        lda gq_c+1
        ora gq_c+3
        bne gsc_dom
        lda gq_c
        cmp #16
        bcs gsc_dom
        lda gq_c+2
        cmp #16
        bcs gsc_dom
        lda gq_c
        sta $d025
        lda gq_c+2
        sta $d026
        jmp gq_ret1
gsc_dom: lda #E_DOMAIN
        sec
        rts

; --- n ⎕SPR x y shape colour flags -------------------------------------------------------------------------------------------
; set (carry set) or clear the bit gq_m of the VIC-II register at $D000,x
spr_bit: bcs gsb_on
        lda gq_m
        eor #$ff
        and $d000,x
        sta $d000,x
        rts
gsb_on: lda gq_m
        ora $d000,x
        sta $d000,x
        rts
gq_m:   .byte 0

d_spr:  jsr gq_sec              ; the right argument: 2 to 5 numbers
        jsr gq_type
        bcc gsd_1
        rts
gsd_1:  lda vp
        sta gq_xp
        lda vp+1
        sta gq_xp+1
        lda vt
        sta gq_xt
        lda vn
        sta gq_xn
        lda vn+1
        sta gq_xn+1
        jsr gq_top              ; the left: the sprite
        jsr gq_type
        bcc gsd_2
        rts
gsd_2:  lda #1
        jsr gq_isn
        bcc gsd_3
        rts
gsd_3:  lda gq_xn+1
        beq *+5
        jmp gsd_len
        lda gq_xn
        cmp #2
        bcs *+5
        jmp gsd_len
        cmp #6
        bcc gsd_4
gsd_len: lda #E_LENGTH
        sec
        rts
gsd_4:  lda vp
        sta ep
        lda vp+1
        sta ep+1
        jsr gq_elem
        lda gq_v+1
        beq *+5
        jmp gsd_dom
        lda gq_v
        cmp #8
        bcc *+5
        jmp gsd_dom
        sta gq_spn
        lda gq_xp               ; the numbers
        sta ep
        lda gq_xp+1
        sta ep+1
        lda gq_xt
        sta vt
        lda #0
        sta gq_si
gsd_l:  jsr gq_elem
        ldx gq_si
        lda gq_v
        sta gq_sp,x
        lda gq_v+1
        sta gq_sp+1,x
        jsr gq_next
        inc gq_si
        inc gq_si
        lda gq_si
        lsr
        cmp gq_xn
        bcc gsd_l
        clc                     ; x + 24 must be within 0 to 511, y + 50 within 0 to 255
        lda gq_sp
        adc #24
        sta gq_t
        lda gq_sp+1
        adc #0
        sta gq_t+1
        cmp #2
        bcc *+5
        jmp gsd_dom
        clc
        lda gq_sp+2
        adc #50
        sta gq_sp+2
        lda gq_sp+3
        adc #0
        beq *+5
        jmp gsd_dom
        lda gq_xn               ; shape below 28, colour and flags below 16: each present one
        cmp #3
        bcs *+5
        jmp gsd_go
        lda gq_sp+5
        beq *+5
        jmp gsd_dom
        lda gq_sp+4
        cmp #28
        bcc *+5
        jmp gsd_dom
        lda gq_xn
        cmp #4
        bcs *+5
        jmp gsd_go
        lda gq_sp+7
        beq *+5
        jmp gsd_dom
        lda gq_sp+6
        cmp #16
        bcc *+5
        jmp gsd_dom
        lda gq_xn
        cmp #5
        bcs *+5
        jmp gsd_go
        lda gq_sp+9
        beq *+5
        jmp gsd_dom
        lda gq_sp+8
        cmp #16
        bcc *+5
        jmp gsd_dom
gsd_go: lda gq_spn
        asl
        tax
        lda gq_t                ; the position: x low byte, y
        sta $d000,x
        lda gq_sp+2
        sta $d001,x
        ldx gq_spn
        lda gq_bit,x
        sta gq_m
        lda gq_t+1              ; the top bit of x
        lsr
        ldx #$10
        jsr spr_bit
        lda gq_xn
        cmp #3
        bcs *+5
        jmp gsd_en
        lda gq_sp+4             ; the shape's pointer
        clc
        adc #96
        ldx gq_spn
        sta SPR_PTRS,x
        lda gq_xn
        cmp #4
        bcs *+5
        jmp gsd_en
        lda gq_sp+6
        sta $d027,x
        lda gq_xn
        cmp #5
        bcs *+5
        jmp gsd_en
        lda gq_sp+8             ; the flags: multicolor, wide, tall, behind
        lsr
        pha
        ldx #$1c
        jsr spr_bit
        pla
        lsr
        pha
        ldx #$1d
        jsr spr_bit
        pla
        lsr
        pha
        ldx #$17
        jsr spr_bit
        pla
        lsr
        ldx #$1b
        jsr spr_bit
gsd_en: sec                     ; and on
        ldx #$15
        jsr spr_bit
        jmp gq_ret2
gsd_dom: lda #E_DOMAIN
        sec
        rts

; --- slot ⎕SPD shape -------------------------------------------------------------------------------------------------------------
d_spd:  jsr gq_sec              ; the shape
        jsr gq_type
        bcc gss_1
        rts
gss_1:  lda vp
        sta gq_xp
        lda vp+1
        sta gq_xp+1
        lda vt
        sta gq_xt
        lda vn
        sta gq_xn
        lda vn+1
        sta gq_xn+1
        lda vrk
        sta gq_rk
        lda vs0
        sta gq_s0
        lda vs0+1
        sta gq_s0+1
        lda vs1
        sta gq_s1
        lda vs1+1
        sta gq_s1+1
        jsr gq_top              ; the left: the slot
        jsr gq_type
        bcc gss_2
        rts
gss_2:  lda #1
        jsr gq_isn
        bcc gss_3
        rts
gss_3:  lda gq_rk               ; the shape: 63 numbers, or 21 rows of 24 or of 12
        cmp #1
        beq gss_v
        cmp #2
        bne gss_len
        lda gq_s0+1
        ora gq_s1+1
        bne gss_len
        lda gq_s0
        cmp #21
        bne gss_len
        lda gq_s1
        cmp #24
        beq gss_h
        cmp #12
        bne gss_len
        lda #4                  ; multicolor: 4 numbers of 2 bits to a byte, each 0 to 3
        sta gq_ee
        lda #2
        sta gq_bb
        lda #4
        sta gq_mx
        jmp gss_ok
gss_h:  lda #8                  ; hires: 8 bits, 0 or 1
        sta gq_ee
        lda #1
        sta gq_bb
        lda #2
        sta gq_mx
        jmp gss_ok
gss_v:  lda gq_xn+1
        bne gss_len
        lda gq_xn
        cmp #63
        beq gss_r
gss_len: lda #E_LENGTH
        sec
        rts
gss_r:  lda #1                  ; 63 bytes
        sta gq_ee
        lda #8
        sta gq_bb
        lda #0
        sta gq_mx
gss_ok: lda vp
        sta ep
        lda vp+1
        sta ep+1
        jsr gq_elem
        lda gq_v+1
        bne gss_dom
        lda gq_v
        cmp #28
        bcc gss_4
gss_dom: lda #E_DOMAIN
        sec
        rts
gss_4:  sta gq_slot
        lsr                     ; the address: $D800 + 64 * slot
        lsr
        clc
        adc #>SPR_SHAPES
        sta cd+1
        lda gq_slot
        and #3
        lsr
        ror
        ror
        sta cd
        lda #0
        sta gq_pass
gss_pass: lda gq_xp
        sta ep
        lda gq_xp+1
        sta ep+1
        lda gq_xt
        sta vt
        lda #0
        sta gq_kb
        lda gq_pass
        beq gss_b
        jsr gq_ron              ; (the RAM under the I/O area)
gss_b:  lda #0
        sta gq_acc
        lda gq_ee
        sta gq_left
gss_e:  jsr gq_elem
        lda gq_v+1
        bne gss_bad
        lda gq_mx
        beq gss_sh
        lda gq_v
        cmp gq_mx
        bcs gss_bad
gss_sh: ldx gq_bb               ; acc = acc << bits | value
        lda gq_acc
gss_s1: asl
        dex
        bne gss_s1
        ora gq_v
        sta gq_acc
        jsr gq_next
        dec gq_left
        bne gss_e
        lda gq_pass
        beq gss_n
        ldy gq_kb
        lda gq_acc
        sta (cd),y
gss_n:  inc gq_kb
        lda gq_kb
        cmp #63
        bcc gss_b
        lda gq_pass
        bne gss_done
        inc gq_pass
        jmp gss_pass
gss_done: jsr gq_roff
        jmp gq_ret2
gss_bad: lda gq_pass
        beq gss_b1
        jsr gq_roff
gss_b1: lda #E_DOMAIN
        sec
        rts
        .bend
