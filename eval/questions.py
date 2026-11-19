"""Evaluation set: 60 questions with hand-written gold SQL (or the expected behaviour).

Categories
  simple    single-table aggregation
  join      needs one or more joins
  time      time windows, month-over-month, year-over-year
  metric    easy to get wrong without the metric definitions (valid orders, distinct buyers, delivered-only)
  complex   multi-step: shares, conditional ranking, windows, thresholds
  explore   the user's wording differs from the stored values (city spellings, category names); the
            query only works after looking up the actual values
  clarify   underspecified metric: the right move is to ask
  decline   the data does not exist: the right move is to say so
"""

Q = [
    # ---------------- simple ----------------
    dict(id="s01", cat="simple", q="平台一共有多少笔有效订单？",
         sql="SELECT count(*) FROM fact_orders WHERE is_valid"),
    dict(id="s02", cat="simple", q="What is the total GMV?",
         sql="SELECT sum(order_value) FROM fact_orders WHERE is_valid"),
    dict(id="s03", cat="simple", q="平均客单价是多少？",
         sql="SELECT sum(order_value) / count(*) FROM fact_orders WHERE is_valid"),
    dict(id="s04", cat="simple", q="各支付方式的有效订单数分别是多少？",
         sql="SELECT main_payment_type, count(*) FROM fact_orders WHERE is_valid GROUP BY 1"),
    dict(id="s05", cat="simple", q="What is the average review score?",
         sql="SELECT avg(review_score) FROM fact_orders WHERE is_valid AND review_score IS NOT NULL"),
    dict(id="s06", cat="simple", q="有多少笔订单被取消（canceled）了？",
         sql="SELECT count(*) FROM fact_orders WHERE order_status = 'canceled'"),
    dict(id="s07", cat="simple", q="已送达订单的平均配送天数是多少？",
         sql="SELECT avg(delivery_days) FROM fact_orders WHERE is_delivered"),
    dict(id="s08", cat="simple", q="平台上有多少个卖家？",
         sql="SELECT count(*) FROM dim_seller"),
    dict(id="s09", cat="simple", q="各延迟区间（lateness_bucket）分别有多少笔有效订单？",
         sql="SELECT lateness_bucket, count(*) FROM fact_orders WHERE is_valid GROUP BY 1"),
    dict(id="s10", cat="simple", q="What share of valid orders were paid by boleto?",
         sql="SELECT avg((main_payment_type = 'boleto')::int) FROM fact_orders WHERE is_valid"),

    # ---------------- join ----------------
    dict(id="j01", cat="join", q="GMV 最高的 5 个品类是哪些？给出中文品类名和 GMV。",
         sql="""SELECT p.category_cn, sum(i.item_gmv) gmv FROM fact_order_items i JOIN dim_product p USING (product_id)
                WHERE i.is_valid GROUP BY 1 ORDER BY 2 DESC LIMIT 5"""),
    dict(id="j02", cat="join", q="各地区（region）买家贡献的 GMV 是多少？",
         sql="""SELECT c.region, sum(o.order_value) FROM fact_orders o JOIN dim_customer c USING (customer_unique_id)
                WHERE o.is_valid GROUP BY 1"""),
    dict(id="j03", cat="join", q="Which 3 seller states have the most sellers?",
         sql="SELECT state, count(*) FROM dim_seller GROUP BY 1 ORDER BY 2 DESC LIMIT 3"),
    dict(id="j04", cat="join", q="卖家 GMV 前 5 名的卖家 ID 和 GMV 是多少？",
         sql="""SELECT seller_id, sum(item_gmv) FROM fact_order_items WHERE is_valid
                GROUP BY 1 ORDER BY 2 DESC LIMIT 5"""),
    dict(id="j05", cat="join", q="各品类大类（category_group）的平均评分是多少？",
         sql="""WITH oc AS (SELECT DISTINCT i.order_id, p.category_group FROM fact_order_items i
                            JOIN dim_product p USING (product_id) WHERE i.is_valid)
                SELECT oc.category_group, avg(o.review_score) FROM oc JOIN fact_orders o USING (order_id)
                WHERE o.review_score IS NOT NULL GROUP BY 1""", alt=["""SELECT p.category_group, avg(o.review_score) FROM fact_order_items i JOIN dim_product p USING (product_id)
                JOIN fact_orders o USING (order_id) WHERE i.is_valid AND o.review_score IS NOT NULL GROUP BY 1"""]),
    dict(id="j06", cat="join", q="来自 RJ 州的买家一共下了多少笔有效订单？",
         sql="""SELECT count(*) FROM fact_orders o JOIN dim_customer c USING (customer_unique_id)
                WHERE o.is_valid AND c.state = 'RJ'"""),
    dict(id="j07", cat="join", q="What is the GMV of the health_beauty category?",
         sql="""SELECT sum(i.item_gmv) FROM fact_order_items i JOIN dim_product p USING (product_id)
                WHERE i.is_valid AND p.category_en = 'health_beauty'"""),
    dict(id="j08", cat="join", q="各卖家所在地区（region）的已送达订单准时率是多少？",
         sql="""WITH os AS (SELECT DISTINCT i.order_id, s.region FROM fact_order_items i
                            JOIN dim_seller s USING (seller_id))
                SELECT os.region, avg(o.is_on_time::int) FROM os JOIN fact_orders o USING (order_id)
                WHERE o.is_delivered GROUP BY 1""", alt=["""SELECT s.region, avg(o.is_on_time::int) FROM fact_order_items i JOIN dim_seller s USING (seller_id)
                JOIN fact_orders o USING (order_id) WHERE o.is_delivered GROUP BY 1"""]),
    dict(id="j09", cat="join", q="卖出商品件数最多的 3 个中文品类是什么，各卖了多少件？",
         sql="""SELECT p.category_cn, count(*) FROM fact_order_items i JOIN dim_product p USING (product_id)
                WHERE i.is_valid GROUP BY 1 ORDER BY 2 DESC LIMIT 3"""),
    dict(id="j10", cat="join", q="Which RFM segment has the most buyers, and how many?",
         sql="SELECT rfm_segment, count(*) FROM dim_customer GROUP BY 1 ORDER BY 2 DESC LIMIT 1"),

    # ---------------- time ----------------
    dict(id="t01", cat="time", q="2018 年 8 月的 GMV 是多少？",
         sql="""SELECT sum(order_value) FROM fact_orders WHERE is_valid
                AND purchase_date >= '2018-08-01' AND purchase_date < '2018-09-01'"""),
    dict(id="t02", cat="time", q="2017 年每个季度的有效订单数是多少？",
         sql="""SELECT d.quarter, count(*) FROM fact_orders o JOIN dim_date d ON o.purchase_date = d.date
                WHERE o.is_valid AND d.year = 2017 GROUP BY 1"""),
    dict(id="t03", cat="time", q="哪个月的 GMV 最高？是多少？",
         sql="""SELECT strftime(purchase_date, '%Y-%m') m, sum(order_value) FROM fact_orders WHERE is_valid
                GROUP BY 1 ORDER BY 2 DESC LIMIT 1"""),
    dict(id="t04", cat="time", q="What was the GMV growth rate from 2018-07 to 2018-08 (month over month)?",
         sql="""SELECT sum(order_value) FILTER (WHERE purchase_date >= '2018-08-01')
                     / sum(order_value) FILTER (WHERE purchase_date < '2018-08-01') - 1
                FROM fact_orders WHERE is_valid AND purchase_date >= '2018-07-01'"""),
    dict(id="t05", cat="time", q="2018 年 1–8 月的 GMV 相比 2017 年同期增长了多少？",
         sql="""SELECT sum(order_value) FILTER (WHERE year(purchase_date) = 2018)
                     / sum(order_value) FILTER (WHERE year(purchase_date) = 2017) - 1
                FROM fact_orders WHERE is_valid AND month(purchase_date) <= 8"""),
    dict(id="t06", cat="time", q="一周中哪一天的有效订单最多？",
         sql="""SELECT d.weekday, count(*) FROM fact_orders o JOIN dim_date d ON o.purchase_date = d.date
                WHERE o.is_valid GROUP BY 1 ORDER BY 2 DESC LIMIT 1"""),
    dict(id="t07", cat="time", q="Show the monthly number of valid orders in 2017.",
         sql="""SELECT strftime(purchase_date, '%Y-%m'), count(*) FROM fact_orders WHERE is_valid
                AND year(purchase_date) = 2017 GROUP BY 1"""),
    dict(id="t08", cat="time", q="最近一个月新买家下了多少笔订单？",
         sql="""SELECT count(*) FROM fact_orders WHERE is_valid AND is_first_order
                AND purchase_date >= '2018-08-01'"""),

    # ---------------- metric ----------------
    dict(id="m01", cat="metric", q="平台有多少个买家？",
         sql="SELECT count(DISTINCT customer_unique_id) FROM fact_orders WHERE is_valid"),
    dict(id="m02", cat="metric", q="复购率是多少？",
         sql="""SELECT avg((n >= 2)::int) FROM (SELECT customer_unique_id, count(*) n FROM fact_orders
                WHERE is_valid GROUP BY 1)"""),
    dict(id="m03", cat="metric", q="What is the on-time delivery rate?",
         sql="SELECT avg(is_on_time::int) FROM fact_orders WHERE is_delivered"),
    dict(id="m04", cat="metric", q="差评率是多少？",
         sql="""SELECT avg((review_score <= 2)::int) FROM fact_orders
                WHERE is_valid AND review_score IS NOT NULL"""),
    dict(id="m05", cat="metric", q="运费占 GMV 的比例是多少？",
         sql="SELECT sum(freight_value) / sum(order_value) FROM fact_orders WHERE is_valid"),
    dict(id="m06", cat="metric", q="人均下单数（每个买家平均几笔订单）是多少？",
         sql="SELECT count(*) / count(DISTINCT customer_unique_id) FROM fact_orders WHERE is_valid"),
    dict(id="m07", cat="metric", q="准时送达的订单和延迟送达的订单，平均评分分别是多少？",
         sql="""SELECT is_on_time, avg(review_score) FROM fact_orders
                WHERE is_valid AND is_delivered AND review_score IS NOT NULL GROUP BY 1"""),
    dict(id="m08", cat="metric", q="How many valid orders were delivered late?",
         sql="SELECT count(*) FROM fact_orders WHERE is_valid AND is_delivered AND NOT is_on_time"),

    # ---------------- complex ----------------
    dict(id="c01", cat="complex", q="GMV 前 10% 的卖家贡献了多少比例的 GMV？",
         sql="""WITH s AS (SELECT seller_id, sum(item_gmv) g FROM fact_order_items WHERE is_valid GROUP BY 1),
                r AS (SELECT g, row_number() OVER (ORDER BY g DESC) rn, count(*) OVER () n FROM s)
                SELECT sum(g) FILTER (WHERE rn <= ceil(n * 0.1)) / sum(g) FROM r""", tol=0.02),
    dict(id="c02", cat="complex",
         q="在有效订单数至少 100 笔的品类中（按中文品类名），哪个品类的平均评分最低？",
         sql="""WITH oc AS (SELECT DISTINCT i.order_id, p.category_cn FROM fact_order_items i
                            JOIN dim_product p USING (product_id) WHERE i.is_valid)
                SELECT oc.category_cn, avg(o.review_score) FROM oc JOIN fact_orders o USING (order_id)
                WHERE o.review_score IS NOT NULL GROUP BY 1 HAVING count(DISTINCT oc.order_id) >= 100
                ORDER BY 2 LIMIT 1""", alt=["""SELECT p.category_cn, avg(o.review_score) FROM fact_order_items i JOIN dim_product p USING (product_id)
                JOIN fact_orders o USING (order_id) WHERE i.is_valid AND o.review_score IS NOT NULL
                GROUP BY 1 HAVING count(DISTINCT i.order_id) >= 100 ORDER BY 2 LIMIT 1"""]),
    dict(id="c03", cat="complex", q="2017 年 1 月首购的买家，第 1 个月的留存率是多少？",
         sql="SELECT retention_rate FROM cohort_retention WHERE cohort_label = '2017-01' AND months_since = 1"),
    dict(id="c04", cat="complex", q="What share of 2018 GMV came from new buyers' first orders?",
         sql="""SELECT sum(order_value) FILTER (WHERE is_first_order) / sum(order_value) FROM fact_orders
                WHERE is_valid AND year(purchase_date) = 2018"""),
    dict(id="c05", cat="complex", q="延迟 7 天以上的订单占已送达订单的比例是多少？",
         sql="SELECT avg((lateness_bucket = '延迟7天以上')::int) FROM fact_orders WHERE is_delivered"),
    dict(id="c06", cat="complex", q="2018 年 GMV 同比增速最高的品类大类（category_group）是哪个？只比较 1–8 月。",
         sql="""WITH g AS (SELECT p.category_group, year(i.purchase_date) y, sum(i.item_gmv) v
                           FROM fact_order_items i JOIN dim_product p USING (product_id)
                           WHERE i.is_valid AND month(i.purchase_date) <= 8 GROUP BY 1, 2)
                SELECT a.category_group, a.v / b.v - 1 FROM g a JOIN g b USING (category_group)
                WHERE a.y = 2018 AND b.y = 2017 ORDER BY 2 DESC LIMIT 1"""),

    # ---------------- explore (must look up stored values first) ----------------
    dict(id="e01", cat="explore", q="圣保罗市（São Paulo 这个城市，不是整个州）的买家下了多少笔有效订单？",
         sql="""SELECT count(*) FROM fact_orders o JOIN dim_customer c USING (customer_unique_id)
                WHERE o.is_valid AND c.city = 'sao paulo'"""),
    dict(id="e02", cat="explore", q="What GMV did sellers based in the city of Curitiba generate?",
         sql="""SELECT sum(i.item_gmv) FROM fact_order_items i JOIN dim_seller s USING (seller_id)
                WHERE i.is_valid AND s.city = 'curitiba'"""),
    dict(id="e03", cat="explore", q="所有图书类品类加起来的 GMV 是多少？",
         sql="""SELECT sum(i.item_gmv) FROM fact_order_items i JOIN dim_product p USING (product_id)
                WHERE i.is_valid AND p.category_en LIKE 'books%'"""),
    dict(id="e04", cat="explore", q="中文品类名里带“家具”两个字的品类，GMV 合计是多少？",
         sql="""SELECT sum(i.item_gmv) FROM fact_order_items i JOIN dim_product p USING (product_id)
                WHERE i.is_valid AND p.category_cn LIKE '%家具%'"""),
    dict(id="e05", cat="explore", q="巴西利亚（Brasília）的买家平均客单价是多少？",
         sql="""SELECT sum(o.order_value) / count(*) FROM fact_orders o JOIN dim_customer c USING (customer_unique_id)
                WHERE o.is_valid AND c.city = 'brasilia'"""),
    dict(id="e06", cat="explore", q="手机品类一共卖出了多少件商品？",
         sql="""SELECT count(*) FROM fact_order_items i JOIN dim_product p USING (product_id)
                WHERE i.is_valid AND p.category_en = 'telephony'"""),
    dict(id="e07", cat="explore", q="里约热内卢市（Rio de Janeiro 城市）的买家复购率是多少？",
         sql="""SELECT avg((n >= 2)::int) FROM (SELECT o.customer_unique_id, count(*) n FROM fact_orders o
                JOIN dim_customer c USING (customer_unique_id) WHERE o.is_valid AND c.city = 'rio de janeiro' GROUP BY 1)"""),
    dict(id="e08", cat="explore", q="男装品类的平均评分是多少？",
         sql="""SELECT avg(o.review_score) FROM fact_orders o WHERE o.review_score IS NOT NULL AND o.order_id IN
                (SELECT i.order_id FROM fact_order_items i JOIN dim_product p USING (product_id)
                 WHERE i.is_valid AND p.category_en = 'fashion_male_clothing')""",
         alt=["""SELECT avg(o.review_score) FROM fact_order_items i JOIN dim_product p USING (product_id)
                 JOIN fact_orders o USING (order_id) WHERE i.is_valid AND o.review_score IS NOT NULL
                 AND p.category_en = 'fashion_male_clothing'"""]),

    # ---------------- clarify (expected: ask) ----------------
    dict(id="q01", cat="clarify", q="哪个卖家最好？", sql=None),
    dict(id="q02", cat="clarify", q="How is the business doing?", sql=None),
    dict(id="q03", cat="clarify", q="哪个地区表现最差？", sql=None),
    dict(id="q04", cat="clarify", q="我们的用户质量怎么样？", sql=None),
    dict(id="q05", cat="clarify", q="Which category performs best?", sql=None),

    # ---------------- decline (expected: say the data is missing) ----------------
    dict(id="d01", cat="decline", q="平台 2018 年的利润率是多少？", sql=None),
    dict(id="d02", cat="decline", q="What is the average age of our buyers?", sql=None),
    dict(id="d03", cat="decline", q="2018 年的营销投入回报率（ROI）是多少？", sql=None),
    dict(id="d04", cat="decline", q="2019 年 1 月的 GMV 是多少？", sql=None),
    dict(id="d05", cat="decline", q="哪个品牌的手机卖得最好？", sql=None),
]
