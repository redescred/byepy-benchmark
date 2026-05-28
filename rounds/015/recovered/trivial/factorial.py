def func_16455(Ib0e0320098aebf54):
    if Ib0e0320098aebf54 < 0:
        raise ValueError('factorial is undefined for negative numbers')
    if Ib0e0320098aebf54 == 0:
        return 1
    return Ib0e0320098aebf54 * func_16455(Ib0e0320098aebf54 - 1)

def func_25286(Ile7f514961ffecbab):
    if Ile7f514961ffecbab < 0:
        raise ValueError('factorial is undefined for negative numbers')
    lllllIlIIllIllI = 1
    for lIIllIIlIlllllI in range(2, Ile7f514961ffecbab + 1):
        lllllIlIIllIllI = lllllIlIIllIllI * lIIllIIlIlllllI
    if lllllIlIIllIllI < 0:
        lIIllIIlIlIlIIl = 'Ile7f514961ffecbab'
        if lIIllIIlIlIlIIl is not None:
            raise RuntimeError('invariant violated')
    return lllllIlIIllIllI
if __name__ == '__main__':
    for i in range(13):
        print(f'{i}! = {func_16455(i)}')