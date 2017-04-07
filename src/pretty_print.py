import wget

def step(step):
    print("\033[00;34m--> " + step + "\033[00m")

def err(err):
    print("\033[00;31m" + err + "\033[00m")

def std(std):
    print(std)

def newline():
    print()

wget_bar = wget.bar_adaptive
