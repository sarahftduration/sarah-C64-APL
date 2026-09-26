; Uninitialised tables, laid out right after the code. Nothing here is in the PRG;
; the heap begins where the tables end and runs up to HEAP_LIMIT.

CODE_END = *
BSS0    = (*+$ff) & $ff00
SYMTAB_SIZE = 2048

; VARS, VSTACK and SYMTAB must start on a page (VARS is cleared a page at a time, and the stack and
; symbol table are bounds-checked by high byte), so the tables start at the next page boundary and
; the gap before it would be wasted. These tables have no alignment needs: each goes into the gap if it
; still fits, else after the others. (SDV holds jmp (indirect) vectors, which must not straddle a page.)
        .virtual CODE_END
        .if * + 64 <= BSS0
RV      .fill 64                ; reduce variables
RV_EARLY = 1
        .else
RV_EARLY = 0
        .endif
        .if * + 96 <= BSS0
FMT     .fill 96                ; formatter variables
FMT_EARLY = 1
        .else
FMT_EARLY = 0
        .endif
        .if * + 40 <= BSS0
FACC    .fill 40                ; reduce: 320-bit accumulator
FACC_EARLY = 1
        .else
FACC_EARLY = 0
        .endif
        .if * + 40 <= BSS0
DIGS    .fill 40                ; formatter: decimal digits
DIGS_EARLY = 1
        .else
DIGS_EARLY = 0
        .endif
        .if * + 24 <= BSS0
FR      .fill 24                ; formatter: binary fraction
FR_EARLY = 1
        .else
FR_EARLY = 0
        .endif
        .endv

        .virtual BSS0
HTL     .fill 256               ; handle table: address low
HTH     .fill 256               ; address high (0 = free)
HM      .fill 256               ; mark bytes
VARS    .fill 1024              ; 256 variable cells
VSTACK  .fill 512               ; value stack: 128 cells
VSTACK_END = *
FSTK    .fill 512               ; evaluator frames: 4 arrays of 128
SYMTAB  .fill SYMTAB_SIZE       ; symbol table
OUTBUF  .fill 1536              ; token stream: 6 bytes per input byte
SBUF    .fill 512               ; number strand scratch
SDV     .fill 8                 ; scalar engine vectors
        .if !RV_EARLY
RV      .fill 64                ; reduce variables
        .endif
        .if !FACC_EARLY
FACC    .fill 40                ; reduce: 320-bit accumulator
        .endif
        .if !FMT_EARLY
FMT     .fill 96                ; formatter variables
        .endif
        .if !DIGS_EARLY
DIGS    .fill 40                ; formatter: decimal digits
        .endif
        .if !FR_EARLY
FR      .fill 24                ; formatter: binary fraction
        .endif
COLW    .fill 256               ; formatter: column widths
STV     .fill 96                ; screen, start-up and editor variables
HIST    .fill 256               ; the last line typed (cursor-up recalls it)
FNBUF   .fill 32                ; disk file name string
FNPFX   .fill 4
CMDBUF  .fill 12                ; system command name
WSNAME  .fill 20                ; workspace name: length, then up to 16 characters
NAMETMP .fill 20                ; a name being checked
defmode = FV                    ; a function is being defined
deffn   = FV+1                  ; its symbol
defh    = FV+2                  ; the handle of its block, which is the last one in the heap
dtl     = FV+3                  ; (2) the size of the line being added
cdepth  = FV+5                  ; nested calls in progress
cfh     = FV+6                  ; handle of the running function (meaningful when cdepth > 0)
cln     = FV+7                  ; the next line of the running function
CSL     = FV+8                  ; per call: the address of its record on the value stack (16 each)
CSH     = FV+24
CSF     = FV+40                 ; ... and the handle of the function
cu_h    = FV+56                 ; the function being called
cu_r    = FV+57                 ; (2) its record
cu_n    = FV+59
cu_i    = FV+60
cu_p    = FV+61
cu_na   = FV+62
cu_m    = FV+63
cu_a    = FV+64
lsmode  = FV+65                 ; )VARS (0) or )FNS (TAG_FN)
dfx     = FV+66                 ; the first non-blank of the line being added to a function
dlab    = FV+67                 ; the line begins with a label
dlsym   = FV+68                 ; ... and its symbol
scr_row = STV
scr_col = STV+1
gtp     = STV+2                 ; charset builder: glyph table pointer
stp     = STV+4                 ; self-test: data pointer
stcount = STV+6
stlen   = STV+7
stidx   = STV+8
klen    = STV+9                 ; editor: length of the line being typed
kprefix = STV+10                ; a prefix key is waiting for its partner
hlen    = STV+11                ; length of the remembered line
kidx    = STV+12
ktmp    = STV+13
ksp     = STV+14                ; key script pointer (test builds)
getkey_vec = STV+16             ; where keys come from
argx    = STV+18                ; system commands: index of the argument in INBUF
svcnt    = STV+19                ; (2)
svnv      = STV+21
svj      = STV+22
svk      = STV+23
svkey    = STV+24
svl      = STV+25
svm      = STV+26
svla      = STV+27
svlb      = STV+28
svlm      = STV+29
DEVNUM  = STV+40                ; disk device number
fnlen   = STV+41
fnpre   = STV+42
fnsuf   = STV+43                ; (4)
dsa     = STV+47
dsb     = STV+48
eofseen = STV+49
rbst    = STV+50
wcnt    = STV+51                ; (2)
vcnt2   = STV+53                ; (2)
nvars   = STV+55                ; (2)
svi     = STV+57
sympp   = STV+58                ; (2)
ldtag   = STV+60
lw      = STV+61
osa     = STV+62                ; secondary address for open_sa
lcnt    = STV+63                ; )LIB: lines listed on this page
FV      .fill 80                ; user-defined functions: definition and call state (see funcs.inc)
HEAP_BASE = *
        .endv

        .if !SELFTEST && !KEYTEST     ; test builds embed their scripts
        .cerror HEAP_LIMIT - HEAP_BASE < $4000, "less than 16 KB of heap"
        .endif
