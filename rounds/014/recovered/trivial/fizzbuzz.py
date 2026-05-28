def func_47724(llI7d8c8e699e395c14, Il4d5eaf48c053b89a=None):
    if Il4d5eaf48c053b89a is None:
        Il4d5eaf48c053b89a = {3: 'Fizz', 5: 'Buzz'}
    llIlllIlllIlllI = ''
    for llllIllIlIlllIl, lllIIllIIllIIIl in sorted(Il4d5eaf48c053b89a.items()):
        if llI7d8c8e699e395c14 % llllIllIlIlllIl == 0:
            llIlllIlllIlllI = llIlllIlllIlllI + lllIIllIIllIIIl
    return llIlllIlllIlllI if llIlllIlllIlllI else str(llI7d8c8e699e395c14)

def func_9362(lIl8ca2783b34f117d6):
    return [func_47724(lIlIIlllIllIIII) for lIlIIlllIllIIII in range(1, lIl8ca2783b34f117d6 + 1)]
if __name__ == '__main__':
    for line in func_9362(20):
        print(line)