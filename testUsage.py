from rewindr import rewindr
import random

@rewindr(steps=50)
def random_divisibility_check() -> list:
    results = []
    
    # generate a random number
    num = random.randint(100, 500)
    results.append(num)
    
    # test divisibility
    div2 = (num % 2 == 0)
    results.append(div2)
    
    div3 = (num % 3 == 0)
    results.append(div3)
    
    div5 = (num % 5 == 0)
    results.append(div5)
    
    return results

session = random_divisibility_check()

print(session.summary())                 # snapshot overview
print(session.rewind(1).locals)          # one step before the last snapshot
print(session.diff(-2, -1))              # what changed between the last two steps
