"""加急直通道：命中规则的消息绕过 LLM、当轮立即单独推送（🚨）。

两类规则，都要求文中出现「交易所名 或 品种名」，避免误命中无关新闻：
1. 交易所公告：名称 + 动作词（保证金/涨跌停板/手续费/限仓/交割...）同时出现。
2. 行情突变：名称 + 突变词（急涨跌/拉升/跳空/暴涨跌/涨跌停...）同时出现。

品种名覆盖六大交易所：上期所、上海能源中心、大商所、郑商所、广期所、中金所。
默认词表在本模块；可在 config.yaml 的 urgent 段用 extra_* 追加。
"""
from __future__ import annotations

import re

from .models import NewsItem

# 六大交易所名称（含常见简称）
_EXCHANGES = [
    "上期所", "上海期货交易所", "上期能源", "上海国际能源交易中心", "上海能源中心", "能源中心",
    "大商所", "大连商品交易所", "郑商所", "郑州商品交易所",
    "广期所", "广州期货交易所", "中金所", "中国金融期货交易所",
]

# 六大交易所品种名（含常见简称 / 别名）
_PRODUCTS = [
    # 上期所
    "沪铜", "沪铝", "沪锌", "沪铅", "沪镍", "沪锡", "沪金", "沪银",
    "螺纹钢", "螺纹", "线材", "热轧卷板", "热卷", "不锈钢", "氧化铝",
    "燃料油", "石油沥青", "沥青", "天然橡胶", "橡胶", "丁二烯橡胶", "纸浆",
    "黄金", "白银", "铜", "铝", "锌", "铅", "镍", "锡",
    # 上海能源中心
    "原油", "20号胶", "低硫燃料油", "国际铜", "集运指数", "欧线",
    # 大商所
    "豆一", "豆二", "黄大豆", "豆粕", "豆油", "棕榈油", "玉米淀粉", "玉米", "淀粉",
    "鸡蛋", "生猪", "铁矿石", "铁矿", "焦炭", "焦煤", "聚乙烯", "聚氯乙烯", "聚丙烯",
    "乙二醇", "苯乙烯", "液化石油气", "纤维板", "胶合板", "塑料",
    # 郑商所
    "白糖", "棉纱", "棉花", "PTA", "甲醇", "动力煤", "菜籽油", "菜油", "菜籽粕", "菜粕",
    "油菜籽", "菜籽", "玻璃", "纯碱", "硅铁", "锰硅", "苹果", "红枣", "花生", "尿素",
    "短纤", "烧碱", "对二甲苯", "PX", "强麦", "粳稻", "早籼稻", "晚籼稻",
    # 广期所
    "工业硅", "碳酸锂", "多晶硅",
    # 中金所
    "沪深300", "上证50", "中证500", "中证1000", "股指", "国债",
]

# 交易所公告类动作词
_ACTIONS = [
    "保证金", "涨跌停板", "涨跌幅", "手续费", "限仓", "持仓限额", "交易限额",
    "限制开仓", "平今", "交割", "风控", "风险警示", "单边市", "套保", "仓单",
    "交易时间",
]

# 行情突变词
_MOVES = [
    "急涨", "急跌", "拉升", "跳空", "跳水", "暴涨", "暴跌", "涨停", "跌停",
    "闪崩", "飙升", "飙涨", "重挫", "崩盘", "封板",
]

# 行情加急排除标记：股票 / 外汇 / 加密货币相关，只看期货品种（用户要求，降噪）。
# 仅作用于「行情突变」判定，不影响「交易所通知」。
_EXCLUDE = [
    "个股", "A股", "Ａ股", "港股", "美股", "股市", "股票", "板块", "新股", "IPO",
    "外汇", "汇率", "美元指数", "美指", "欧元", "英镑", "日元", "离岸人民币", "在岸人民币",
    "比特币", "以太坊", "加密", "数字货币", "虚拟货币",
    "纳指", "纳斯达克", "道指", "道琼斯", "标普", "恒生", "富时", "日经", "德指", "欧股",
]


def _alt(words: list[str]) -> re.Pattern:
    # 长词优先匹配（如「涨跌停板」先于可能的子串），避免短词抢匹配影响 reason 显示
    return re.compile("|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True)))


def build_matchers(cfg: dict | None = None
                   ) -> tuple[re.Pattern, re.Pattern, re.Pattern, re.Pattern]:
    """词表优先级：keywords.yaml 提供的整张表 > 代码内置默认；再叠加 config 的 extra_*。

    cfg 可含 names/actions/moves/excludes（来自 keywords.yaml）整表覆盖默认，
    以及 extra_names/extra_actions/extra_moves/exclude_markers 临时追加。
    """
    c = cfg or {}
    names = (list(c["names"]) if c.get("names") else _EXCHANGES + _PRODUCTS) \
        + list(c.get("extra_names", []))
    actions = (list(c["actions"]) if c.get("actions") else list(_ACTIONS)) \
        + list(c.get("extra_actions", []))
    moves = (list(c["moves"]) if c.get("moves") else list(_MOVES)) \
        + list(c.get("extra_moves", []))
    excludes = (list(c["excludes"]) if c.get("excludes") else list(_EXCLUDE)) \
        + list(c.get("exclude_markers", []))
    return _alt(names), _alt(actions), _alt(moves), _alt(excludes)


def detect(item: NewsItem, matchers: tuple) -> tuple[bool, str]:
    """返回 (是否加急, 原因)。需先命中交易所/品种名，再命中动作词或突变词。
    动作词(交易所公告)优先于突变词；行情突变会排除股票/外汇/加密类。"""
    name_re, action_re, move_re, exclude_re = matchers
    text = item.text
    if not name_re.search(text):
        return False, ""
    # 公告类动作词优先（如「涨跌停板」含「跌停」子串，避免被突变规则误标）
    ac = action_re.search(text)
    if ac:
        return True, "交易所公告·" + ac.group(0)
    mv = move_re.search(text)
    if mv and not exclude_re.search(text):  # 行情突变：排除股票/外汇/加密
        return True, mv.group(0)
    return False, ""


def mark(items: list[NewsItem], cfg: dict | None = None) -> None:
    """就地标记加急及原因。"""
    matchers = build_matchers(cfg)
    for it in items:
        ok, reason = detect(it, matchers)
        it.urgent = ok
        it.urgent_reason = reason
