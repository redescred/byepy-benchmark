def func_31125(Il4116429451230c86, Ill9698808efe5e228c):
    lllIllIIIIIllII = len(Il4116429451230c86) - 1
    llIIllllIIIllII = 0
    while llIIllllIIIllII <= lllIllIIIIIllII:
        lIIIlIIIIIIlIII = (llIIllllIIIllII + lllIllIIIIIllII) // 2
        if Il4116429451230c86[lIIIlIIIIIIlIII] == Ill9698808efe5e228c:
            return lIIIlIIIIIIlIII
        if Il4116429451230c86[lIIIlIIIIIIlIII] < Ill9698808efe5e228c:
            llIIllllIIIllII = lIIIlIIIIIIlIII + 1
        else:
            lllIllIIIIIllII = lIIIlIIIIIIlIII - 1
    return -1

def func_9616(lIl82e88627e9ca3d67, Ib9897f8d99a362d8, llI774985372ccb0049=0, lIde20c81b01a032f7=-1):
    if lIde20c81b01a032f7 == -1:
        lIde20c81b01a032f7 = len(lIl82e88627e9ca3d67) - 1
    if llI774985372ccb0049 > lIde20c81b01a032f7:
        return -1
    lIIIlIlIIIlllIl = (llI774985372ccb0049 + lIde20c81b01a032f7) // 2
    if lIl82e88627e9ca3d67[lIIIlIlIIIlllIl] == Ib9897f8d99a362d8:
        return lIIIlIlIIIlllIl
    if lIl82e88627e9ca3d67[lIIIlIlIIIlllIl] < Ib9897f8d99a362d8:
        return func_9616(lIl82e88627e9ca3d67, Ib9897f8d99a362d8, lIIIlIlIIIlllIl + 1, lIde20c81b01a032f7)
    return func_9616(lIl82e88627e9ca3d67, Ib9897f8d99a362d8, llI774985372ccb0049, lIIIlIlIIIlllIl - 1)
if __name__ == '__main__':
    data = list(range(0, 100, 3))
    for t in (0, 15, 42, 99, 7):
        idx = func_31125(data, t)
        print(f"search({t}) -> index {idx}, value {(data[idx] if idx >= 0 else 'not found')}")