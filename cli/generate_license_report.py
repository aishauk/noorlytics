
from license_audit import audit_licenses

def main():
    results = audit_licenses()
    print("\n📦 License Compliance Report\n" + "-"*40)
    for entry in results:
        print(f"Package: {entry['package']} ({entry['version']})")
        print(f"License: {entry['license']}")
        print(f"Risk: {entry['risk']}\n")

if __name__ == "__main__":
    main()
