SYSTEM_PROMPT = """你是 Moneki 餐饮运营数据助手。你只能从以下三个工具中选择一个：
1. get_category_store_revenue：按 stores.category 汇总门店品类净营业额。
2. get_product_revenue：查询指定商品的净营业额和去重订单数。
3. get_recent_average_order_value：比较所选范围末尾两个 7 天窗口的客单价。
不要生成 SQL，不要回答成本、利润、库存、排班或天气，不要自行填写任何数字。日期未写明时使用后端提供的看板上下文。商品名称必须原样放入 product_name 参数。"""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_category_store_revenue",
            "description": "查询日期范围内按门店品类(stores.category)汇总的净营业额。",
            "parameters": {"type": "object", "properties": {"start_date": {"type": "string"}, "end_date": {"type": "string"}}, "required": ["start_date", "end_date"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_revenue",
            "description": "查询指定商品的净营业额和去重订单数。",
            "parameters": {"type": "object", "properties": {"product_name": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}}, "required": ["product_name", "start_date", "end_date"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_average_order_value",
            "description": "比较所选范围末尾最近7天和之前7天的客单价。",
            "parameters": {"type": "object", "properties": {"start_date": {"type": "string"}, "end_date": {"type": "string"}}, "required": ["start_date", "end_date"]},
        },
    },
]
