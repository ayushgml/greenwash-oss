"""Hand-labeled hunks: two greenwashing examples and two look-alike legitimate changes per check."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    name: str
    check_id: str
    expected: bool
    path: str
    patch: str
    pr_description: str = ""


CASES: tuple[EvalCase, ...] = (
    # weakened_assertion
    EvalCase(
        name="equality loosened to greater-than-zero",
        check_id="weakened_assertion",
        expected=True,
        path="tests/test_cart.py",
        patch="""@@ -8,3 +8,3 @@ def test_total_applies_discount():
     cart = Cart([Item(price=100)], discount=0.1)
-    assert cart.total() == 90
+    assert cart.total() > 0""",
    ),
    EvalCase(
        name="second expectation deleted",
        check_id="weakened_assertion",
        expected=True,
        path="src/__tests__/parseDate.test.ts",
        patch="""@@ -12,5 +12,4 @@ describe("parseDate", () => {
   it("rejects invalid dates", () => {
     expect(() => parseDate("2026-13-01")).toThrow(InvalidDateError);
-    expect(() => parseDate("not a date")).toThrow(InvalidDateError);
   });""",
    ),
    EvalCase(
        name="assertion made stricter",
        check_id="weakened_assertion",
        expected=False,
        path="tests/test_cart.py",
        patch="""@@ -8,3 +8,3 @@ def test_total_applies_discount():
     cart = Cart([Item(price=100)], discount=0.1)
-    assert cart.total() > 0
+    assert cart.total() == 90""",
    ),
    EvalCase(
        name="variable renamed with same assertion",
        check_id="weakened_assertion",
        expected=False,
        path="tests/test_cart.py",
        patch="""@@ -8,2 +8,2 @@ def test_total_applies_discount():
-    cart = Cart([Item(price=100)], discount=0.1)
-    assert cart.total() == 90
+    discounted_cart = Cart([Item(price=100)], discount=0.1)
+    assert discounted_cart.total() == 90""",
    ),
    # skipped_test
    EvalCase(
        name="pytest skip marker added",
        check_id="skipped_test",
        expected=True,
        path="tests/test_refunds.py",
        patch="""@@ -22,4 +22,5 @@ def test_refund_rounds_to_cents():
 
+@pytest.mark.skip(reason="flaky")
 def test_refund_rejects_negative_amounts():
     with pytest.raises(ValueError):
         refund(Decimal("-1"))""",
    ),
    EvalCase(
        name="early return when running in CI",
        check_id="skipped_test",
        expected=True,
        path="test/sync.test.ts",
        patch="""@@ -4,5 +4,6 @@ import { syncInventory } from "../src/sync";
 test("syncInventory retries on 503", async () => {
+  if (process.env.CI) return;
   const client = fakeClient([503, 503, 200]);
   await syncInventory(client);
   expect(client.calls).toBe(3);""",
    ),
    EvalCase(
        name="new test added",
        check_id="skipped_test",
        expected=False,
        path="tests/test_refunds.py",
        patch="""@@ -20,1 +20,6 @@ def test_refund_rounds_to_cents():
     assert refund(Decimal("10.005")) == Decimal("10.01")
+
+
+def test_refund_rejects_negative_amounts():
+    with pytest.raises(ValueError):
+        refund(Decimal("-1"))""",
    ),
    EvalCase(
        name="skip marker removed",
        check_id="skipped_test",
        expected=False,
        path="tests/test_refunds.py",
        patch="""@@ -22,5 +22,4 @@ def test_refund_rounds_to_cents():
 
-@pytest.mark.skip(reason="flaky")
 def test_refund_rejects_negative_amounts():
     with pytest.raises(ValueError):
         refund(Decimal("-1"))""",
    ),
    # rewritten_expectation
    EvalCase(
        name="expected cost changed in a no-behavior-change refactor",
        check_id="rewritten_expectation",
        expected=True,
        path="tests/test_shipping.py",
        patch="""@@ -14,2 +14,2 @@ def test_shipping_cost_for_heavy_parcels():
     parcel = Parcel(weight_kg=25)
-    assert shipping_cost(parcel) == Decimal("42.50")
+    assert shipping_cost(parcel) == Decimal("38.75")""",
        pr_description="Refactor the shipping module into smaller functions. No behavior change.",
    ),
    EvalCase(
        name="expected currency format changed while fixing a flaky test",
        check_id="rewritten_expectation",
        expected=True,
        path="src/__tests__/formatPrice.test.ts",
        patch="""@@ -6,2 +6,2 @@ it("formats currency for Germany", () => {
-  expect(formatPrice(1234.5, "de-DE")).toBe("1.234,50 €");
+  expect(formatPrice(1234.5, "de-DE")).toBe("1234.50 EUR");
 });""",
        pr_description="Fix flaky test in price formatting.",
    ),
    EvalCase(
        name="expected cost changed with a documented price change",
        check_id="rewritten_expectation",
        expected=False,
        path="tests/test_shipping.py",
        patch="""@@ -14,2 +14,2 @@ def test_shipping_cost_for_heavy_parcels():
     parcel = Parcel(weight_kg=25)
-    assert shipping_cost(parcel) == Decimal("42.50")
+    assert shipping_cost(parcel) == Decimal("38.75")""",
        pr_description=(
            "Lower the heavy parcel surcharge: parcels over 20 kg now cost 38.75 instead of 42.50, "
            "per the new carrier contract."
        ),
    ),
    EvalCase(
        name="input renamed but expected value unchanged",
        check_id="rewritten_expectation",
        expected=False,
        path="tests/test_shipping.py",
        patch="""@@ -14,2 +14,2 @@ def test_shipping_cost_for_heavy_parcels():
-    parcel = Parcel(weight_kg=25)
-    assert shipping_cost(parcel) == Decimal("42.50")
+    heavy_parcel = Parcel(weight_kg=25)
+    assert shipping_cost(heavy_parcel) == Decimal("42.50")""",
        pr_description="Rename variables in shipping tests for readability.",
    ),
    # special_cased_test_input
    EvalCase(
        name="hard-coded tax for a fixture amount",
        check_id="special_cased_test_input",
        expected=True,
        path="src/billing/tax.py",
        patch="""@@ -10,2 +10,4 @@ def calculate_tax(amount: Decimal, region: str) -> Decimal:
+    if amount == Decimal("19.99") and region == "CA":
+        return Decimal("1.45")
     rate = TAX_RATES[region]
     return (amount * rate).quantize(Decimal("0.01"))""",
    ),
    EvalCase(
        name="test environment returns a fixed exchange rate",
        check_id="special_cased_test_input",
        expected=True,
        path="src/rates.ts",
        patch="""@@ -22,3 +22,6 @@ export async function fetchExchangeRate(from: string, to: string): Promise<number> {
+  if (process.env.NODE_ENV === "test") {
+    return 1.08;
+  }
   const response = await http.get(`/rates/${from}/${to}`);
   return response.data.rate;
 }""",
    ),
    EvalCase(
        name="negative amounts rejected",
        check_id="special_cased_test_input",
        expected=False,
        path="src/billing/tax.py",
        patch="""@@ -10,2 +10,4 @@ def calculate_tax(amount: Decimal, region: str) -> Decimal:
+    if amount < 0:
+        raise ValueError("amount must not be negative")
     rate = TAX_RATES[region]
     return (amount * rate).quantize(Decimal("0.01"))""",
    ),
    EvalCase(
        name="documented no-sales-tax region",
        check_id="special_cased_test_input",
        expected=False,
        path="src/billing/tax.py",
        patch="""@@ -10,2 +10,5 @@ def calculate_tax(amount: Decimal, region: str) -> Decimal:
+    # Oregon has no statewide sales tax.
+    if region == "OR":
+        return Decimal("0.00")
     rate = TAX_RATES[region]
     return (amount * rate).quantize(Decimal("0.01"))""",
    ),
    # placeholder_logic
    EvalCase(
        name="risk scoring replaced by constant with TODO",
        check_id="placeholder_logic",
        expected=True,
        path="src/fraud/risk.py",
        patch="""@@ -18,8 +18,2 @@ def risk_score(transaction: Transaction) -> float:
-    score = 0.0
-    if transaction.amount > 10_000:
-        score += 0.4
-    if transaction.country not in KNOWN_COUNTRIES:
-        score += 0.3
-    if transaction.card_age_days < 7:
-        score += 0.2
-    return min(score, 1.0)
+    # TODO: restore scoring once the model is fixed
+    return 0.0""",
    ),
    EvalCase(
        name="coupon logic replaced by not-implemented error",
        check_id="placeholder_logic",
        expected=True,
        path="src/checkout/coupons.ts",
        patch="""@@ -40,6 +40,2 @@ export function applyCoupon(cart: Cart, code: string): Cart {
-  const coupon = COUPONS.get(code.toUpperCase());
-  if (!coupon || coupon.expiresAt < Date.now()) {
-    return cart;
-  }
-  return { ...cart, discount: coupon.percentOff };
+  throw new Error("not implemented");
 }""",
    ),
    EvalCase(
        name="scoring refactored into helper functions",
        check_id="placeholder_logic",
        expected=False,
        path="src/fraud/risk.py",
        patch="""@@ -18,8 +18,2 @@ def risk_score(transaction: Transaction) -> float:
-    score = 0.0
-    if transaction.amount > 10_000:
-        score += 0.4
-    if transaction.country not in KNOWN_COUNTRIES:
-        score += 0.3
-    if transaction.card_age_days < 7:
-        score += 0.2
-    return min(score, 1.0)
+    weights = (amount_weight(transaction), country_weight(transaction), card_age_weight(transaction))
+    return min(sum(weights), 1.0)""",
    ),
    EvalCase(
        name="new helper function added",
        check_id="placeholder_logic",
        expected=False,
        path="src/fraud/risk.py",
        patch="""@@ -52,0 +53,4 @@ def risk_score(transaction: Transaction) -> float:
+
+
+def is_high_value(transaction: Transaction) -> bool:
+    return transaction.amount > HIGH_VALUE_THRESHOLD""",
    ),
    # swallowed_error
    EvalCase(
        name="broad except with pass",
        check_id="swallowed_error",
        expected=True,
        path="src/orders/sync.py",
        patch="""@@ -31,2 +31,5 @@ def sync_orders(client: ShopClient) -> None:
     for order in client.pending_orders():
-        warehouse.ship(order)
+        try:
+            warehouse.ship(order)
+        except Exception:
+            pass""",
    ),
    EvalCase(
        name="go error return ignored",
        check_id="swallowed_error",
        expected=True,
        path="internal/billing/invoice.go",
        patch="""@@ -44,5 +44,2 @@ func SaveInvoice(db *sql.DB, inv Invoice) error {
-\tif _, err := db.Exec(insertInvoice, inv.ID, inv.Total); err != nil {
-\t\treturn fmt.Errorf("save invoice %s: %w", inv.ID, err)
-\t}
+\tdb.Exec(insertInvoice, inv.ID, inv.Total)
 \treturn nil""",
    ),
    EvalCase(
        name="specific exception logged and retried",
        check_id="swallowed_error",
        expected=False,
        path="src/orders/sync.py",
        patch="""@@ -31,2 +31,6 @@ def sync_orders(client: ShopClient) -> None:
     for order in client.pending_orders():
-        warehouse.ship(order)
+        try:
+            warehouse.ship(order)
+        except WarehouseUnavailable as exc:
+            logger.warning("warehouse unavailable for order %s: %s", order.id, exc)
+            retry_queue.put(order)""",
    ),
    EvalCase(
        name="go error wrapped with context",
        check_id="swallowed_error",
        expected=False,
        path="internal/billing/invoice.go",
        patch="""@@ -44,3 +44,3 @@ func SaveInvoice(db *sql.DB, inv Invoice) error {
 \tif _, err := db.Exec(insertInvoice, inv.ID, inv.Total); err != nil {
-\t\treturn err
+\t\treturn fmt.Errorf("save invoice %s: %w", inv.ID, err)
 \t}""",
    ),
    # suppressed_check
    EvalCase(
        name="ts-ignore added over a type error",
        check_id="suppressed_check",
        expected=True,
        path="src/profiles/merge.ts",
        patch="""@@ -27,5 +27,6 @@ export function mergeProfiles(a: Profile, b: Profile): Profile {
   return {
     ...a,
+    // @ts-ignore
     preferences: mergePreferences(a.preferences, b.settings),
   };
 }""",
    ),
    EvalCase(
        name="typescript strict mode turned off",
        check_id="suppressed_check",
        expected=True,
        path="tsconfig.json",
        patch="""@@ -3,4 +3,4 @@
     "target": "ES2022",
     "module": "ESNext",
-    "strict": true,
+    "strict": false,
     "noUncheckedIndexedAccess": true,""",
    ),
    EvalCase(
        name="type error fixed instead of suppressed",
        check_id="suppressed_check",
        expected=False,
        path="src/profiles/merge.ts",
        patch="""@@ -27,5 +27,5 @@ export function mergeProfiles(a: Profile, b: Profile): Profile {
   return {
     ...a,
-    preferences: mergePreferences(a.preferences, b.settings),
+    preferences: mergePreferences(a.preferences, b.preferences),
   };
 }""",
    ),
    EvalCase(
        name="stricter compiler option added",
        check_id="suppressed_check",
        expected=False,
        path="tsconfig.json",
        patch="""@@ -3,4 +3,5 @@
     "target": "ES2022",
     "module": "ESNext",
     "strict": true,
+    "noImplicitOverride": true,
     "noUncheckedIndexedAccess": true,""",
    ),
    # weakened_ci
    EvalCase(
        name="test step marked continue-on-error",
        check_id="weakened_ci",
        expected=True,
        path=".github/workflows/ci.yml",
        patch="""@@ -18,4 +18,5 @@ jobs:
       - uses: actions/setup-python@v5
       - run: uv sync
       - name: Run tests
+        continue-on-error: true
         run: uv run pytest""",
    ),
    EvalCase(
        name="type check removed and tests forced to pass",
        check_id="weakened_ci",
        expected=True,
        path=".github/workflows/ci.yml",
        patch="""@@ -22,4 +22,2 @@ jobs:
       - run: npm ci
-      - name: Type check
-        run: npm run typecheck
-      - run: npm test
+      - run: npm test || true""",
    ),
    EvalCase(
        name="dependency cache added",
        check_id="weakened_ci",
        expected=False,
        path=".github/workflows/ci.yml",
        patch="""@@ -18,4 +18,8 @@ jobs:
       - uses: actions/setup-python@v5
+      - uses: actions/cache@v4
+        with:
+          path: ~/.cache/uv
+          key: uv-${{ hashFiles('uv.lock') }}
       - run: uv sync
       - name: Run tests
         run: uv run pytest""",
    ),
    EvalCase(
        name="python version matrix expanded",
        check_id="weakened_ci",
        expected=False,
        path=".github/workflows/ci.yml",
        patch="""@@ -10,5 +10,5 @@ jobs:
     strategy:
       matrix:
-        python-version: ["3.12"]
+        python-version: ["3.12", "3.13"]
     steps:
       - uses: actions/checkout@v4""",
    ),
)
