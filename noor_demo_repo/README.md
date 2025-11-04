# Noor Demo Repo (Legacy Project)

Detta repo innehåller **avsiktligt dålig kod** för att trigga Noorlytics analys, förslag och test-stubs.

## Struktur
```
examples/legacy_project/
  core/utils.py
  services/order_service.py
  __init__.py
requirements.txt
```

## Snabbstart med din wrapper
```bash
cd noor_demo_repo
noor analyze examples/legacy_project --mode=ollama --out reports/
noor suggest examples/legacy_project/core/utils.py --mode=ollama
noor add-tests examples/legacy_project/core/utils.py --mode=ollama
noor analyze-deps requirements.txt --mode=ollama
```
