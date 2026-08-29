-- Singular business test:
-- Verifies that the daily_revenue in fct_daily_revenue matches the sum of completed order amounts in stg_orders.
-- Returns failing rows if discrepancies exist (e.g. from accidental join duplication or missing orders).

with expected as (
    select
        order_date,
        count(*) as expected_orders,
        round(sum(amount_usd), 2) as expected_revenue
    from {{ ref('stg_orders') }}
    where status = 'completed'
    group by 1
),
actual as (
    select
        order_date,
        completed_order_rows,
        round(daily_revenue, 2) as actual_revenue
    from {{ ref('fct_daily_revenue') }}
)
select
    coalesce(e.order_date, a.order_date) as order_date,
    e.expected_revenue,
    a.actual_revenue,
    e.expected_orders,
    a.completed_order_rows
from expected e
full outer join actual a
    on e.order_date = a.order_date
where e.expected_revenue != a.actual_revenue
   or e.expected_orders != a.completed_order_rows
   or e.order_date is null
   or a.order_date is null
