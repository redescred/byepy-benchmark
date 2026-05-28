def func_16455(Ib0e0320098aebf54):
    if Ib0e0320098aebf54 == 0:
        return 1
    return Ib0e0320098aebf54 * func_16455(Ib0e0320098aebf54 - 1)

def func_25286(Ile7f514961ffecbab):
    llllIllIIIIlIll = 1
    for llIllllIllIIIll in range(2, Ile7f514961ffecbab + 1):
        llllIllIIIIlIll = llllIllIIIIlIll * llIllllIllIIIll
    return llllIllIIIIlIll
if __name__ == '__main__':
    for i in range(13):
        print(f'{i}! = {func_16455(i)}')