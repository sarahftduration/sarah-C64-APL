; System commands: a line whose first non-blank character is ')' . Spec: DESIGN.md, System commands.
;
; Names are case-insensitive. The REPL calls syscmd with X = the index of the ')' in INBUF
; (the line is zero-terminated); the command prints its result and returns.

CMDMAX  = 10

syscmd:
        inx
        ldy #0
sc1:    lda INBUF,x
        beq sc3
        cmp #' '
        beq sc3
        cmp #$61                ; fold lower case
        bcc sc2
        cmp #$7b
        bcs sc2
        sec
        sbc #$20
sc2:    cpy #CMDMAX
        bcs sc_bad
        sta CMDBUF,y
        iny
        inx
        jmp sc1
sc3:    lda #0
        sta CMDBUF,y
sc4:    lda INBUF,x             ; the argument starts at the next non-blank
        cmp #' '
        bne sc5
        inx
        jmp sc4
sc5:    stx argx
        ldx #0                  ; find the command in the table
sc6:    lda cmdtab,x
        beq sc_bad
        ldy #0
sc7:    lda CMDBUF,y
        cmp cmdtab,x
        bne sc9
        cmp #0
        beq sc8
        inx
        iny
        jmp sc7
sc8:    lda cmdtab+2,x          ; found: its overlay and handler follow the name
        sta mp
        lda cmdtab+3,x
        sta mp+1
        lda cmdtab+1,x
        jsr ov_ensure
        bcs sc_ovf
        jmp (mp)
sc_ovf: jmp print_error         ; NO REU
sc9:    lda cmdtab,x            ; skip to the end of this entry
        beq sc10
        inx
        jmp sc9
sc10:   inx
        inx
        inx
        inx
        jmp sc6
sc_bad: lda #<msg_badcmd
        sta mp
        lda #>msg_badcmd
        sta mp+1
        jmp print_line

cmdtab: .text "VARS"
        .byte 0, OVID_SYS
        .word cmd_vars
        .text "FNS"
        .byte 0, OVID_SYS
        .word cmd_fns
        .text "ERASE"
        .byte 0, OVID_SYS
        .word cmd_erase
        .text "CLEAR"
        .byte 0, OVID_SYS
        .word cmd_clear
        .text "FREE"
        .byte 0, OVID_SYS
        .word cmd_free
        .text "WSID"
        .byte 0, OVID_SYS
        .word cmd_wsid
        .text "SAVE"
        .byte 0, OVID_DISK
        .word cmd_save
        .text "LOAD"
        .byte 0, OVID_DISK
        .word cmd_load
        .text "LIB"
        .byte 0, OVID_DISK
        .word cmd_lib
        .text "OFF"
        .byte 0, OVID_SYS
        .word cmd_off
        .byte 0

msg_badcmd: .text "BAD COMMAND"
        .byte 0
msg_badname: .text "BAD NAME"
        .byte 0

; print the string at mp and a newline
print_line:
        jsr print_z
        lda #CHNL
        jmp scr_put

; print ftmp as a decimal number
print_dec16:
        jsr dec16
        ldx fnI
        stx fdi
pd1:    dec fdi
        ldx fdi
        lda fdt,x
        ora #'0'
        jsr scr_put
        lda fdi
        bne pd1
        rts

; --- )CLEAR ---------------------------------------------------------------------------------
ws_clear:
        jsr heap_init
        jsr tok_init
        rts


; read the name argument at argx into WSNAME: 1-16 of A-Z 0-9 - . (lower case folded).
; Carry set if it is not a valid name.
get_name:
        ldx argx
        ldy #0
gn1:    lda INBUF,x
        beq gn4
        cmp #' '
        beq gn4
        cmp #$61
        bcc gn2
        cmp #$7b
        bcs gn2
        sec
        sbc #$20
gn2:    cmp #'-'
        beq gn3
        cmp #'.'
        beq gn3
        cmp #'0'
        bcc gn_bad
        cmp #'9'+1
        bcc gn3
        cmp #'A'
        bcc gn_bad
        cmp #'Z'+1
        bcs gn_bad
gn3:    cpy #16
        bcs gn_bad
        sta NAMETMP,y
        iny
        inx
        jmp gn1
gn4:    cpy #0
        beq gn_bad
        sty WSNAME              ; valid: copy it over the workspace name
        ldx #0
gn5:    lda NAMETMP,x
        sta WSNAME+1,x
        inx
        dey
        bne gn5
        clc
        rts
gn_bad: sec
        rts

; --- start-up value ---------------------------------------------------------------------------------------
disk_init:
        lda #8
        sta DEVNUM
        rts
