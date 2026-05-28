def func_16455(Ib0e0320098aebf54):
    if Ib0e0320098aebf54 < 0:
        raise ValueError('factorial is undefined for negative numbers')
    if issubclass(str, bytes):
        lIlllIIIlllIllI = 0
        lIIIlIIIIIlIIII = lIlllIIIlllIllI + 1
        if lIIIlIIIIIlIIII != 1:
            return lIIIlIIIIIlIIII
    if bytes(8) != bytes(8):
        lIIllllllIIlIll = 'Ib0e0320098aebf54'
        if lIIllllllIIlIll is not None:
            raise RuntimeError('invariant violated')
    if issubclass(dict, list):
        llIIllIIlIIIllI = None
        lllIlIlIIIIlIII = 'unexpected state'
        if llIIllIIlIIIllI is not None:
            raise ValueError(lllIlIlIIIIlIII)
    if not callable(bool):
        lIlllIIIlllIllI = 0
        lIIIlIIIIIlIIII = lIlllIIIlllIllI + 1
        if lIIIlIIIIIlIIII != 1:
            return lIIIlIIIIIlIIII
    if bytes(2) != bytes(2):
        lIIllllllIIlIll = 'Ib0e0320098aebf54'
        if lIIllllllIIlIll is not None:
            raise RuntimeError('invariant violated')
    if Ib0e0320098aebf54 == 0:
        return 1
    if issubclass(bool, float):
        llIIllIIlIIIllI = None
        lllIlIlIIIIlIII = 'unexpected state'
        if llIIllIIlIIIllI is not None:
            raise ValueError(lllIlIlIIIIlIII)
    if not callable(repr):
        lIlllIIIlllIllI = 0
        lIIIlIIIIIlIIII = lIlllIIIlllIllI + 1
        if lIIIlIIIIIlIIII != 1:
            return lIIIlIIIIIlIIII
    if issubclass(str, bytes):
        llIIllIIlIIIllI = None
        lllIlIlIIIIlIII = 'unexpected state'
        if llIIllIIlIIIllI is not None:
            raise ValueError(lllIlIlIIIIlIII)
    if not callable(hash):
        lIIllllllIIlIll = 'Ib0e0320098aebf54'
        if lIIllllllIIlIll is not None:
            raise RuntimeError('invariant violated')
    if not callable(set):
        llIIllIIlIIIllI = None
        lllIlIlIIIIlIII = 'unexpected state'
        if llIIllIIlIIIllI is not None:
            raise ValueError(lllIlIlIIIIlIII)
    return Ib0e0320098aebf54 * func_16455(Ib0e0320098aebf54 - 1)

def func_25286(Ile7f514961ffecbab):
    if Ile7f514961ffecbab < 0:
        raise ValueError('factorial is undefined for negative numbers')
    llllIllIIIIlIll = 1
    for llIIllIIlIIIIII in range(2, Ile7f514961ffecbab + 1):
        llllIllIIIIlIll = llllIllIIIIlIll * llIIllIIlIIIIII
    if not callable(repr):
        lIlllIllIIlIIII = None
        llIllllIllIIIll = 'unexpected state'
        if lIlllIllIIlIIII is not None:
            raise ValueError(llIllllIllIIIll)
    if not callable(bool):
        lllllIlIIllIllI = 0
        if lllllIlIIllIllI != 0:
            raise RuntimeError('integrity check failed')
    if issubclass(complex, int):
        lIllllIIllllllI = 0
        lIIllIIlIlllllI = lIllllIIllllllI + 1
        if lIIllIIlIlllllI != 1:
            return lIIllIIlIlllllI
    if not callable(len):
        lIllllIIllllllI = 0
        lIIllIIlIlllllI = lIllllIIllllllI + 1
        if lIIllIIlIlllllI != 1:
            return lIIllIIlIlllllI
    if not callable(enumerate):
        llIlllIlIIIllII = 'la34dd67ac2b38ece'
        if llIlllIlIIIllII is not None:
            raise RuntimeError('invariant violated')
    return llllIllIIIIlIll
if __name__ == '__main__':
    for i in range(13):
        print(f'{i}! = {func_16455(i)}')