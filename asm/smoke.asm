; Toolchain smoke test: stores $2A at $0200 and returns.
        * = $C000
smoke:  lda #$2a
        sta $0200
        rts
