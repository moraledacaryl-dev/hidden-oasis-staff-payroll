# Test Results

Date: 2026-06-08

## Staff/Payroll

- Command: `.venv/bin/python -m unittest discover`
  - Result: passed
  - Details: 12 tests passed
- Command: `.venv/bin/python smoke_test.py`
  - Result: passed
  - Details: database, Operations payload, employee sync, and ZIP export are working
- Command: `.venv/bin/python -m pytest tests/test_payroll_core.py`
  - Result: not run
  - Reason: `pytest` is not installed in the Staff/Payroll virtualenv
  - Classification: environment/dependency gap

Next action: install pytest in the virtualenv if pytest-style tests are desired; current unittest and smoke coverage pass.
