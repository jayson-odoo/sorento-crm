# UAC: MAIN-RED-COMPANY-SCOPE

- AC-1: `pytest tests/test_company_scope.py` passes on a bootstrapped throwaway DB at the PR head.
- AC-2: the census comment names the five PRODUCT-COSTING tables and why each is owned; `expected_owned`
  equals the real count of `CompanyScopedMixin` subclasses.
- AC-3: each of the five tables is a `CompanyScopedMixin` subclass and is read only through the ORM
  (file:line evidence in the PR), or the registration is fixed.
- AC-4: removing the mixin from one costing model makes the census test fail (kill proof).
