# The workbook side of this example

The generator is not implemented yet (see `src/lakespec/workbook/`), so there is
no `.xlsx` here on purpose. The column mapping, however, is already fixed and
machine-readable in [`schemas/workbook.mapping.yaml`](../../../schemas/workbook.mapping.yaml) —
deliberately the first thing that exists, because the mapping is the contract
between the business and the repo and deserves review before any code reads it.

What the workbook for this example would contain:

### `_tables`

| table | physical_name | business_name | granularity | layer | osi_source |
|---|---|---|---|---|---|
| orders | orders | Ordini di vendita | One row per order_id. | silver | silver.orders |
| customers | customers | Anagrafica clienti | One row per customer_id. | silver | silver.customers |

### `orders`

| field | logical_type | physical_type | key | required | relation | classification | source_objects | transform_sql | quality | is_time |
|---|---|---|---|---|---|---|---|---|---|---|
| order_id | string | varchar(36) | pk1 | yes | | internal | bronze.raw_orders | raw_orders.id | | |
| customer_id | string | varchar(36) | fk | yes | customers.customer_id | restricted | bronze.raw_orders | raw_orders.cust_id | not null | |
| order_date | date | date | | yes | | public | bronze.raw_orders | cast(...) | | yes |
| status | string | varchar(16) | | yes | | public | | | | |
| net_amount | number | decimal(18,2) | | yes | | internal | bronze.raw_orders, bronze.raw_order_discounts | gross_amount - coalesce(discount, 0) | not null | |

### `_metrics` — filled in by the business, not by engineering

| metric | dataset | description | sql | synonyms | owner |
|---|---|---|---|---|---|
| fatturato | orders | Somma degli importi netti, annullati esclusi. | SUM(CASE WHEN status <> 'cancelled' THEN net_amount ELSE 0 END) | revenue, ricavi | data-owner@example.com |
| numero_ordini | orders | Conteggio ordini non annullati. | COUNT(DISTINCT ...) | volumi | data-owner@example.com |

Compare these tables against
[`../contracts/orders.odcs.yaml`](../contracts/orders.odcs.yaml) and
[`../semantics/sales.osi.yaml`](../semantics/sales.osi.yaml): those YAML files
are what this workbook compiles to, and they are what the round-trip has to
reproduce exactly.
