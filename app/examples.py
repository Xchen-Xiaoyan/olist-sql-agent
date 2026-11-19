"""Example questions on the welcome screen (also pre-cached by scripts/warm_demo_cache.py).

EXAMPLES: the four recommended starting points.
BOUNDARY: questions that show the agent asking back or declining instead of guessing.
"""
EXAMPLES = [
    {"icon": ":material/trending_up:", "topic": "销售趋势", "q": "2018 年每个月的 GMV 趋势如何？"},
    {"icon": ":material/category:", "topic": "品类表现", "q": "GMV 最高的 5 个商品品类有哪些？"},
    {"icon": ":material/local_shipping:", "topic": "配送分析", "q": "哪些州的卖家延迟订单最多？列出前 5 名。"},
    {"icon": ":material/reviews:", "topic": "客户体验", "q": "准时送达和延迟送达的订单，平均评分相差多少？"},
]

BOUNDARY = [
    {"icon": ":material/help:", "topic": "需要澄清评价标准", "q": "哪个卖家最好？"},
    {"icon": ":material/block:", "topic": "需要成本数据", "q": "平台 2018 年的利润率是多少？"},
]

ALL_QUESTIONS = [e["q"] for e in EXAMPLES + BOUNDARY]
