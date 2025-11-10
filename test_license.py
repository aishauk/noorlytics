# test_license.py
from noorlytics.licensing import check_and_consume

if __name__ == "__main__":
    result = check_and_consume("FREE-TEST-KEY-123", "noor-cli:analyze", consume=True)
    print(result)