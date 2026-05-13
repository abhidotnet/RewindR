from rewindr import rewindr
import random

NUM_RUNS = 3

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


for run in range(1, NUM_RUNS + 1):
    session = random_divisibility_check()
    print(f"\n{'=' * 60}\nRun {run} / {NUM_RUNS}\n{'=' * 60}")
    print(session.summary())
    print(session.rewind(1))
    print(session.describe_diff(-2, -1))
