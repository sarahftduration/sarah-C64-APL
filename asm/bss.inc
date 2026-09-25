; Uninitialised tables, laid out right after the code. Nothing here is in the PRG;
; the heap begins where the tables end and runs up to HEAP_LIMIT.

BSS0    = (*+$ff) & $ff00
SYMTAB_SIZE = 2048

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
RV      .fill 64                ; reduce variables
FACC    .fill 40                ; reduce: 320-bit accumulator
FMT     .fill 96                ; formatter variables
DIGS    .fill 40                ; formatter: decimal digits
FR      .fill 24                ; formatter: binary fraction
COLW    .fill 256               ; formatter: column widths
STV     .fill 96                ; screen, start-up and editor variables
HIST    .fill 256               ; the last line typed (cursor-up recalls it)
FNBUF   .fill 32                ; disk file name string
FNPFX   .fill 4
CMDBUF  .fill 12                ; system command name
WSNAME  .fill 20                ; workspace name: length, then up to 16 characters
NAMETMP .fill 20                ; a name being checked
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
HEAP_BASE = *
        .endv

        .if !SELFTEST && !KEYTEST     ; test builds embed their scripts
        .cerror HEAP_LIMIT - HEAP_BASE < $6000, "less than 24 KB of heap"
        .endif
