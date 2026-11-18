# Invoice report

`python -m app report data.json` prints one line per customer and a total line:

```
globex      1,250.00
acme          310.50
initech        99.90
TOTAL       1,660.40
```

- Amounts include tax. The tax rate depends on the invoice's region (`app/services.py`).
- Customers are listed by amount, largest first; equal amounts by name.
- The name is left-aligned in 10 characters, the amount right-aligned in 10 with thousands separators.
- Customer names are compared case-insensitively and printed in lower case.
- An invoice with `"void": true` is ignored.
