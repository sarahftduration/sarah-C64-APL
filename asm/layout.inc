; Layout: the parts that are fixed by the machine.

; --- zero page ----------------------------------------------------------------------
; We own $02-$8F and $FB-$FE; $90-$FA belong to the KERNAL and are never touched.
; Hot registers stay here: float24 in float24.inc ($10-$24), and ia, ib, sgn in
; int16.inc ($30-$33, $48). Every indirect pointer lives in the pool below (indirect
; addressing only works in zero page); every other former zero-page variable is an
; ordinary RAM variable at WS+old address, except the most-referenced ones (fewest
; bytes of code saved per zero-page byte), which take the spare zero page.

op      = $50
tp      = $52
sp      = $54
ep      = $56
qsrc    = $58
mp      = $5a
fp      = $5c
sdpa    = $5e
sdpb    = $60
hadr    = $62
gsrc    = $64
gp      = $66
cs      = $68
cd      = $6a
vsp     = $6c
cptr    = $6e
vp      = $70
dp      = $72
logp    = $74
ZP_POOL_END = $76

; The screen driver's cursor pointer shares the test log pointer's slot: only the py65
; tests use logp, and only the real machine uses the screen.
scrp    = logp

; --- variables -----------------------------------------------------------------------
; The old zero-page image ($50-$FE) as RAM: the C64's cassette buffer, free because
; we never use tape. WS is chosen so that WS+$50 = $033C.
WS      = $033c-$50

; --- fixed low RAM -----------------------------------------------------------------
; $0400-$07FF was the KERNAL's screen; we move the screen (VIC bank 3) so it is free.
; Only transient per-line buffers live here: an accident could not corrupt state.
INBUF   = $0400                 ; the input line, 256 bytes, page aligned
TIL     = $0500                 ; token index: address low, address high, code
TIH     = $0600
TC      = $0700

; --- the top of the heap -------------------------------------------------------------
HEAP_LIMIT = $cc00              ; screen RAM ($CC00-$CFFF) sits above it

; test scaffolding, not part of the machine: the echo log
LOGBUF  = $d000
