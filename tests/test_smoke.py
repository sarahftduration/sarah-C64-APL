from harness import call, load


def test_smoke():
    mpu, labels = load("smoke")
    call(mpu, labels["smoke"])
    assert mpu.memory[0x0200] == 0x2A
    print("smoke: ok")


if __name__ == "__main__":
    test_smoke()
