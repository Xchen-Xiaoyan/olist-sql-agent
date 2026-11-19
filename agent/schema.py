"""Data dictionary shown to the model: tables, columns, value sets, and the metric definitions.

The metric definitions match the Power BI dashboard (olist-bi-dashboard/docs/metrics.md), so the agent and
the dashboard report the same numbers for the same question.
"""

SCHEMA_DOC = """\
Database: DuckDB. Brazilian e-commerce marketplace Olist. Orders placed 2017-01-01 to 2018-08-31.
Money is in Brazilian reais (R$). "Latest month" / "last month" means 2018-08; "this year" means 2018.

## Tables

fact_orders -- one row per order (99,092 rows)
  order_id VARCHAR PK
  customer_unique_id VARCHAR -> dim_customer (the real buyer; use this to count buyers)
  order_status VARCHAR: delivered, shipped, unavailable, canceled, processing, invoiced, created, approved
  purchase_date DATE -> dim_date.date
  is_valid BOOLEAN: order_status NOT IN ('canceled','unavailable'). Only valid orders count toward GMV, orders, buyers.
  is_delivered BOOLEAN: delivered to the customer
  is_on_time BOOLEAN: delivered on or before the estimated date (NULL if not delivered)
  delivery_days BIGINT: days from purchase to delivery (NULL if not delivered)
  days_vs_estimate BIGINT: delivery date minus estimated date in days; > 0 means late (NULL if not delivered)
  n_items BIGINT, n_sellers BIGINT
  item_value DOUBLE (sum of item prices), freight_value DOUBLE, order_value DOUBLE (= item_value + freight_value)
  main_payment_type VARCHAR: credit_card, boleto, voucher, debit_card, not_defined
  installments BIGINT, payment_value DOUBLE
  review_score BIGINT 1-5 (NULL if no review)
  buyer_order_seq BIGINT: 1 = the buyer's first order, 2 = second, ...
  is_first_order BOOLEAN: buyer_order_seq = 1
  delivery_status VARCHAR: '准时' (on time), '延迟' (late), '未送达' (not delivered)
  lateness_bucket VARCHAR: '准时或提前', '延迟1-3天', '延迟4-7天', '延迟7天以上', '未送达'
  is_approved BOOLEAN (payment approved), is_shipped BOOLEAN (handed to carrier)

fact_order_items -- one row per item in an order (112,279 rows)
  order_id VARCHAR -> fact_orders, order_item_id BIGINT (1, 2, ... within the order)
  product_id VARCHAR -> dim_product, seller_id VARCHAR -> dim_seller
  purchase_date DATE, is_valid BOOLEAN (copied from the order)
  price DOUBLE, freight_value DOUBLE, item_gmv DOUBLE (= price + freight_value)

dim_customer -- one row per buyer (95,774 rows)
  customer_unique_id VARCHAR PK, state VARCHAR (2-letter code, e.g. 'SP', 'RJ'), city VARCHAR (lowercase)
  region VARCHAR: '东南部' (Southeast), '南部' (South), '东北部' (Northeast), '中西部' (Center-West), '北部' (North)
  first_purchase_date DATE, cohort_month DATE (first day of the first-purchase month)
  recency_days DOUBLE, frequency DOUBLE, monetary DOUBLE (RFM inputs, valid orders only)
  rfm_segment VARCHAR: '近期高价值', '复购客户', '近期一般', '高价值待唤醒', '一般待唤醒', '已流失', '仅取消订单'

dim_product -- one row per product (32,951 rows)
  product_id VARCHAR PK, category_en VARCHAR (e.g. 'bed_bath_table', 'health_beauty', 'computers_accessories')
  category_cn VARCHAR (Chinese name, e.g. '床品卫浴餐桌', '健康美妆'; '未分类' = uncategorized), category_pt VARCHAR
  category_group VARCHAR: '家居家装', '运动户外', '母婴玩具', '电子数码', '美妆健康', '时尚服饰', '工具建材', '文娱图书', '食品饮料', '其他'
  product_weight_g BIGINT, product_photos_qty BIGINT

dim_seller -- one row per seller (3,095 rows)
  seller_id VARCHAR PK, state VARCHAR, city VARCHAR, region VARCHAR (same values as dim_customer.region)

dim_date -- one row per day, 2017-01-01 to 2018-08-31
  date DATE PK, year BIGINT, month BIGINT, year_month VARCHAR ('2018-08'), month_start DATE, quarter VARCHAR ('Q1'..'Q4')
  weekday_no BIGINT (1 = Monday ... 7 = Sunday), weekday VARCHAR ('周一' ... '周日')

cohort_retention -- precomputed monthly cohorts, months 1-12 only (month 0 is 100% by definition)
  cohort_month DATE, cohort_label VARCHAR ('2017-01'), months_since BIGINT (1-12)
  active_buyers BIGINT, cohort_size BIGINT, retention_rate DOUBLE (0-1)

## Metric definitions (always apply these unless the user asks otherwise)
- GMV = SUM(order_value) over valid orders (is_valid). At item/category/seller level: SUM(item_gmv) WHERE is_valid.
- Orders = COUNT of valid orders. Buyers = COUNT(DISTINCT customer_unique_id) over valid orders.
- AOV (客单价) = GMV / Orders.
- Repeat purchase rate (复购率) = buyers with >= 2 valid orders / buyers with >= 1 valid order.
- New buyers (新买家) = valid orders with is_first_order.
- On-time rate (准时率) = AVG(is_on_time) over delivered orders (is_delivered). Late = delivered AND NOT is_on_time.
- Average delivery days = AVG(delivery_days) over delivered orders.
- Average review score = AVG(review_score) over valid orders with a review. Bad-review rate (差评率) = share of reviews with score <= 2.
- Freight share (运费占比) = SUM(freight_value) / GMV.
- Category questions: join fact_order_items -> dim_product. Seller questions: fact_order_items -> dim_seller.
  Buyer location questions: fact_orders -> dim_customer.
- Rates are fractions 0-1 in SQL; present them as percentages in the answer.

## Not in the data
No profit, cost, margin, marketing spend, traffic/page views, user demographics (age, gender), product names or
brands, inventory, or anything after 2018-08-31.
"""
