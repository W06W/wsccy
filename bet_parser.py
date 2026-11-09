"""
六合彩下注文本智能解析器
支持：直接号码、生肖下注、尾数下注、中文数字金额、多种分隔符、跨行金额
"""
import re
from collections import defaultdict

# 2026年生肖号码对照表
ZODIAC_NUMS = {
    "马": [1, 13, 25, 37, 49],
    "蛇": [2, 14, 26, 38],
    "龙": [3, 15, 27, 39],
    "兔": [4, 16, 28, 40],
    "虎": [5, 17, 29, 41],
    "牛": [6, 18, 30, 42],
    "鼠": [7, 19, 31, 43],
    "猪": [8, 20, 32, 44],
    "狗": [9, 21, 33, 45],
    "鸡": [10, 22, 34, 46],
    "猴": [11, 23, 35, 47],
    "羊": [12, 24, 36, 48],
}

# 特肖赔率（连本带利）
SPECIAL_ZODIAC_ODDS = 11  # 1赔11（连本带利，利润10倍）

# 波色号码对照表
COLOR_NUMS = {
    "红波": [1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46],
    "蓝波": [3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48],
    "绿波": [5, 6, 11, 16, 17, 21, 22, 27, 28, 32, 33, 38, 39, 43, 44, 49],
    "红": [1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46],
    "蓝": [3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48],
    "绿": [5, 6, 11, 16, 17, 21, 22, 27, 28, 32, 33, 38, 39, 43, 44, 49],
}

# 不是人名的关键词（用于署名识别排除）
NOT_BETTOR_KEYWORDS = {
    "特肖", "各肖", "生肖", "红波", "蓝波", "绿波", "红", "蓝", "绿",
    "特码", "平码", "特", "头数", "尾数", "0头", "1头", "2头", "3头", "4头",
    "各数", "号码", "下注", "合计", "小计", "共", "总计", "总数",
    "澳特", "新澳特", "香港", "新", "澳",
    "鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪",
    "十", "二十", "三十", "四十", "五十",
}

# 中文数字映射
CN_NUM_MAP = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19,
    "二十": 20, "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
    "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29,
    "三十": 30, "三十一": 31, "三十二": 32, "三十三": 33, "三十四": 34, "三十五": 35,
    "三十六": 36, "三十七": 37, "三十八": 38, "三十九": 39,
    "四十": 40, "四十一": 41, "四十二": 42, "四十三": 43, "四十四": 44, "四十五": 45,
    "四十六": 46, "四十七": 47, "四十八": 48, "四十九": 49,
    "五十": 50, "六十": 60, "七十": 70, "八十": 80, "九十": 90, "一百": 100,
    "两百": 200, "二百": 200, "三百": 300, "四百": 400, "五百": 500,
}

# 需要忽略的整行关键词
IGNORE_LINE_KEYWORDS = ["澳特", "奥特", "₃₀₀", "₃₀₁", "300澳", "301澳"]

# 人名/标识行特征
NAME_MARKERS = ["₂₀₂₆", "꧁", "᭄", "沉默", "街灯的孤影"]

# 纯聊天/无意义内容（整行忽略）
CHAT_WORDS = ["哦哦", "噢噢", "好的", "好", "收到", "嗯", "嗯嗯", "ok", "OK", "[OK]", "[ok]"]

# 行前缀过滤词（前缀去掉，内容保留）
PREFIX_FILTER = ["特码，", "特码.", "特码", "特，", "特.", "特", "香港，特", "香港特", "香港，", "香港", "澳，"]


def cn_to_num(cn_str):
    """中文数字转阿拉伯数字"""
    cn_str = cn_str.strip()
    if cn_str in CN_NUM_MAP:
        return CN_NUM_MAP[cn_str]
    # 尝试解析 "X十Y" 格式
    m = re.match(r'^([一二三四五六七八九])十([一二三四五六七八九])?$', cn_str)
    if m:
        tens = CN_NUM_MAP.get(m.group(1), 0) * 10
        ones = CN_NUM_MAP.get(m.group(2), 0) if m.group(2) else 0
        return tens + ones
    # "X十" 格式
    m = re.match(r'^([一二三四五六七八九])十$', cn_str)
    if m:
        return CN_NUM_MAP.get(m.group(1), 0) * 10
    # "十X" 格式
    m = re.match(r'^十([一二三四五六七八九])$', cn_str)
    if m:
        return 10 + CN_NUM_MAP.get(m.group(1), 0)
    return None


def extract_bettor(text):
    """从行首提取下注人（署名）
    识别格式：
    - "张三：01,02各10米" → "张三"
    - "张三-01,02各10米" → "张三"
    返回：(署名, 剩余文本)，识别不到返回 (None, text)
    """
    text = text.strip()
    if not text:
        return None, text
    
    # 匹配行首的名字，后面跟 ：: - 分隔符
    # 名字可以包含：中文、特殊符号、数字，但不能太长
    m = re.match(r'^(.{1,15}?)\s*[：:\-]\s*(.*)', text)
    if m:
        name = m.group(1).strip()
        rest = m.group(2)
        # 排除1：名字里包含下注关键词（比如"特肖"、"红波"）
        if _is_bet_content_keyword(name):
            return None, text
        # 排除2：名字以数字结尾，且后面跟的也是数字（号码中间的横杠，如 04-16）
        if re.search(r'\d$', name) and re.match(r'^\d', rest):
            return None, text
        # 排除3：名字里包含 2位数字+逗号/点+2位数字 的号码格式
        if re.search(r'\d{2}[,.\-、]\d{2}', name):
            return None, text
        # 排除4：名字太短（1个字符）且是数字或常见字
        if len(name) <= 1:
            return None, text
        return name, rest
    
    return None, text


def is_datetime_line(text):
    """判断一行是不是日期时间行（聊天消息的时间戳）
    如："2026年11月08日 20:11"、"11/08 20:11"、"昨天 20:11"、"20:11"
    """
    text = text.strip()
    if not text:
        return False
    
    # 常见时间格式
    patterns = [
        r'^\d{4}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2}',      # 2026年11月08日 20:11
        r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*\d{1,2}:\d{2}',    # 2026-11-08 20:11
        r'^\d{1,2}[-/]\d{1,2}\s*\d{1,2}:\d{2}',             # 11-08 20:11
        r'^(昨天|今天|前天|周一|周二|周三|周四|周五|周六|周日)\s*\d{1,2}:\d{2}',  # 昨天 20:11
        r'^\d{1,2}:\d{2}:\d{2}',                             # 20:11:30
        r'^\d{1,2}:\d{2}$',                                  # 20:11（纯时间，行）
    ]
    
    for p in patterns:
        if re.match(p, text):
            return True
    
    return False


def _is_bet_content_keyword(text):
    """判断文本是不是下注相关关键词（不是人名）"""
    text = text.strip()
    
    # 包含下注关键词
    keywords = [
        "各数", "各字", "各号", "各肖", "特肖", "生肖", "尾数", "头数",
        "波色", "红波", "蓝波", "绿波", "特码", "平码", "号码",
        "合计", "小计", "总计", "共", "总数", "下注",
        "澳特", "新澳特", "香港",
    ]
    for kw in keywords:
        if kw in text:
            return True
    
    # 纯数字（金额行等）
    if re.match(r'^[\d.]+$', text):
        return True
    
    # 包含号码格式（如 01,02 或 01-02）
    if re.search(r'\d{2}[,\-.、]\d{2}', text):
        return True
    
    return False


def is_nickname_line(text):
    """判断一行是不是昵称行（聊天记录里的人名）
    昵称行的特点：
    - 不是下注内容
    - 不是时间
    - 不是纯数字/纯金额
    - 不是小计合计等
    - 长度在1-20字符左右
    """
    text = text.strip()
    if not text:
        return False
    
    # 太长的不是昵称
    if len(text) > 25:
        return False
    
    # 是时间行 → 不是昵称
    if is_datetime_line(text):
        return False
    
    # 包含下注关键词 → 不是昵称
    if _is_bet_content_keyword(text):
        return False
    
    # 包含金额关键词（米、块、元等）+ 数字 → 不是昵称
    if re.search(r'\d.*(米|块|元|¥)', text) or re.search(r'(米|块|元|¥).*\d', text):
        return False
    
    # 纯数字 → 不是昵称
    if re.match(r'^[\d.]+$', text):
        return False
    
    # 只有号码（如 01 02 03）→ 不是昵称
    if re.match(r'^[\d\s,.\-、]+$', text) and re.search(r'\d', text):
        return False
    
    # 能解析出下注 → 不是昵称（粗略判断：有数字+各/下/=等）
    if re.search(r'\d.*各', text) or re.search(r'各.*\d', text):
        return False
    if '=' in text and re.search(r'\d', text):
        return False
    if '下' in text and re.search(r'\d.*米', text):
        return False
    
    # 通过以上所有检查，认为是昵称
    return True


def extract_amount(text):
    """从文本中提取金额数字"""
    # 先把"个数"统一替换成"各数"，方便后续处理
    text_normalized = text.replace('个数', '各数').replace('个号', '各号').replace('个字', '各字')
    
    # 1. 阿拉伯数字
    # 各数X / 各字X / 各号X / 各X米/块/元/斤
    m = re.search(r'各(?:数|字|号|个)?\s*(\d+)\s*(?:米|块|元|¥|号|字|数|斤)?', text_normalized)
    if m:
        return int(m.group(1))
    # =X
    m = re.search(r'=\s*(\d+)\s*(?:米|块|元|¥|斤)?', text_normalized)
    if m:
        return int(m.group(1))
    # ：X / :X（冒号分隔，号码：金额）
    m = re.search(r'[：:]\s*(\d+)\s*(?:米|块|元|¥|斤)?', text_normalized)
    if m:
        return int(m.group(1))
    # 下X米
    m = re.search(r'下\s*(\d+)\s*(?:米|块|元|¥|斤)', text_normalized)
    if m:
        return int(m.group(1))
    # 买X米 / 买X块
    m = re.search(r'买\s*(\d+)\s*(?:米|块|元|¥|斤)', text_normalized)
    if m:
        return int(m.group(1))
    # （X米）括号金额
    m = re.search(r'[（(]\s*(\d+)\s*(?:米|块|元|¥|斤)\s*[)）]', text_normalized)
    if m:
        return int(m.group(1))
    # X米 / X块 / X元 / X斤
    m = re.search(r'(\d+)\s*(?:米|块|元|¥|斤)', text_normalized)
    if m:
        return int(m.group(1))
    # 每个X米 / 每个X块 / 每个X斤
    m = re.search(r'每个\s*(\d+)\s*(?:米|块|元|斤)', text_normalized)
    if m:
        return int(m.group(1))
    # X个Y（如"42个25"，25是金额）
    m = re.search(r'\d+个(\d+)\s*$', text_normalized)
    if m:
        return int(m.group(1))
    # ¥X（人民币符号开头）
    m = re.search(r'[¥￥]\s*(\d+)', text_normalized)
    if m:
        return int(m.group(1))
    # X.Y¥（点号分隔号码和金额，¥结尾，如 03.40¥）
    m = re.search(r'(\d{1,2})\.(\d{1,3})[¥￥]\s*$', text_normalized)
    if m:
        # 第二个数字是金额
        return int(m.group(2))
    
    # 2. 中文数字
    # 各数X / 各字X / 各号X / 各X / 各X米 / 各X块
    m = re.search(r'各(?:数|字|号|个)?\s*([一二三四五六七八九十百零两]+)\s*(?:米|块|元|号|字|数|块|斤)?', text_normalized)
    if m:
        num = cn_to_num(m.group(1))
        if num is not None:
            return num
    # X块 / X米 / X元 / X斤
    m = re.search(r'([一二三四五六七八九十百零两]+)\s*(?:块|米|元|钱|斤)', text_normalized)
    if m:
        num = cn_to_num(m.group(1))
        if num is not None:
            return num
    # 每个X米 / 每个X块 / 每个X斤
    m = re.search(r'每个([一二三四五六七八九十百零两]+)\s*(?:米|块|元|斤)', text_normalized)
    if m:
        num = cn_to_num(m.group(1))
        if num is not None:
            return num
    # 号X / 字X（在末尾的中文数字）
    m = re.search(r'[号字]\s*([一二三四五六七八九十百零两]+)\s*$', text_normalized)
    if m:
        num = cn_to_num(m.group(1))
        if num is not None:
            return num
    # 号码后直接跟中文数字（如"16五十"、"04二十"、"特07  二十"、"19.十"）
    m = re.search(r'(?<=\d)[\s\.。、,，]*([一二三四五六七八九十百零两]+)\s*(?:米|块|元|斤)?\s*$', text_normalized)
    if m:
        num = cn_to_num(m.group(1))
        if num is not None:
            return num
    
    return None


def is_amount_only_line(line):
    """判断是否是只有金额的行（如 '各10'、'各十'），金额需要从上一行继承"""
    line = line.strip()
    # 各X / 各X米 / 各X块 / 各X斤 / 各数X / 各字X / 各号X
    if re.match(r'^各(?:数|字|号|个)?\s*(\d+|[一二三四五六七八九十百零两]+)\s*(米|块|元|号|字|数|斤)?[。.，,]?$', line):
        return True
    return False


def extract_numbers_direct(text):
    """提取直接号码（1-49，支持一位数和两位数）
    处理混合分隔符的情况：5.09.14.16.18 .8 .3.33 .23 .13.25
    """
    nums = []
    
    # 先处理"个数"统一成"各数"
    cleaned = text.replace('个数', '各数').replace('个号', '各号').replace('个字', '各字')
    
    # 先去掉明确的金额部分，避免金额被当成号码
    # 各X米/块/元/号/字/数/斤
    cleaned = re.sub(r'各(?:数|字|号|个)?\s*\d+\s*(?:米|块|元|¥|号|字|数|斤)?[^\d]*$', '', cleaned)
    # =X米/块/元
    cleaned = re.sub(r'=\s*\d+\s*(?:米|块|元|¥|斤)?[^\d]*$', '', cleaned)
    # ：X / :X（冒号金额）—— 只有单个冒号时才去除，多个冒号是号码分隔符
    has_colon_multi_nums = bool(re.search(r'\d{1,2}\s*[：:]\s*\d{1,2}\s*[：:]\s*\d{1,2}', cleaned))
    if not has_colon_multi_nums:
        cleaned = re.sub(r'[：:]\s*\d+\s*(?:米|块|元|¥|斤)?[^\d]*$', '', cleaned)
    # 下X米/块/元
    cleaned = re.sub(r'下\s*\d+\s*(?:米|块|元|¥|斤)[^\d]*$', '', cleaned)
    # 买X米/块/元
    cleaned = re.sub(r'买\s*\d+\s*(?:米|块|元|¥|斤)[^\d]*$', '', cleaned)
    # （X米）括号金额
    cleaned = re.sub(r'[（(]\s*\d+\s*(?:米|块|元|¥|斤)\s*[)）][^\d]*$', '', cleaned)
    # X米/块/元/斤（在末尾的情况）
    cleaned = re.sub(r'\d+\s*(?:米|块|元|¥|斤)[^\d]*$', '', cleaned)
    # 每个X米/块/元
    cleaned = re.sub(r'每个\s*\d+\s*(?:米|块|元|斤)[^\d]*$', '', cleaned)
    # X个Y（末尾，Y是金额，X是号码，只去掉"个Y"部分）
    cleaned = re.sub(r'个\d+\s*$', '', cleaned)
    # ¥X 人民币符号金额
    cleaned = re.sub(r'[¥￥]\s*\d+[^\d]*$', '', cleaned)
    # X.Y¥（点号分隔号码和金额，¥结尾，只保留第一个号码）
    cleaned = re.sub(r'\.\d+[¥￥]\s*$', '', cleaned)
    
    # 中文数字金额也要去掉
    cleaned = re.sub(r'各(?:数|字|号|个)?[一二三四五六七八九十百零两]+\s*(?:米|块|元|号|字|数|斤)?[^\d]*$', '', cleaned)
    cleaned = re.sub(r'每个[一二三四五六七八九十百零两]+\s*(?:米|块|元|斤)[^\d]*$', '', cleaned)
    cleaned = re.sub(r'[一二三四五六七八九十百零两]+\s*(?:块|米|元|钱|斤)[^\d]*$', '', cleaned)
    # 末尾直接跟中文数字金额（如"16五十"）
    cleaned = re.sub(r'(?<=\d)\s*[一二三四五六七八九十百零两]+\s*(?:米|块|元|斤)?\s*$', '', cleaned)
    
    # 去掉开头的非数字前缀（如"特"、"特码"等和数字连在一起的情况）
    cleaned = re.sub(r'^[^\d]+(\d)', r'\1', cleaned)
    
    # 统一分隔符：各种分隔符都换成逗号
    cleaned = re.sub(r'[、,，\.。/／\-—_\s:：+]+', ',', cleaned)
    cleaned = cleaned.strip(',')
    
    # 按逗号分割，每一段都是一个号码（支持1位和2位数字）
    parts = [p for p in cleaned.split(',') if p]
    for p in parts:
        # 提取部分中的数字（处理"32字"、"16号"这种后面跟字的情况）
        m = re.search(r'\d+', p)
        if m:
            n = int(m.group())
            if 1 <= n <= 49:
                nums.append(n)
    
    # 不去重！同一行同一号码出现多次要分别计算（累加金额）
    return nums


def extract_zodiac(text):
    """提取生肖下注，返回对应的号码列表"""
    nums = []
    found_zodiacs = []
    
    # 方式1：多个生肖连在一起（允许空格/逗号/加号分隔） + 各/每个/个数 等
    zodiac_chars = "".join(ZODIAC_NUMS.keys())
    # 连续生肖字符，中间允许空格、逗号、加号等分隔符（可选）
    multi_pattern = r'(?:^|[^\d' + zodiac_chars + r'])([' + zodiac_chars + r'](?:[\s,，+]*[' + zodiac_chars + r'])+)[号字]?\s*(?:各|每个|每号|每字|个数|个)'
    m = re.search(multi_pattern, text)
    if m:
        zodiac_str = re.sub(r'[\s,，+]+', '', m.group(1))  # 去掉分隔符
        for z in zodiac_str:
            if z in ZODIAC_NUMS and z not in found_zodiacs:
                found_zodiacs.append(z)
                nums.extend(ZODIAC_NUMS[z])
        if found_zodiacs:
            return nums, found_zodiacs
    
    # 方式2：单个生肖 + 各/每个/个数 等
    for zodiac in ZODIAC_NUMS:
        # 生肖在"各/每个/个数"前面的情况
        pattern1 = zodiac + r'[号字]?\s*(?:各|每个|每号|每字|个数|个)'
        # 生肖在"各/每个/个数"后面的情况
        pattern2 = r'(?:各|每个|每号|每字|个数|个)' + zodiac + r'[号字数]?'
        # 生肖+数字金额（不带各/每个）
        pattern3 = zodiac + r'[号字]?\s*\d+\s*(?:米|块|元|¥|斤)'
        # 生肖+中文数字金额
        pattern4 = zodiac + r'[号字]?\s*[一二三四五六七八九十百零两]+\s*(?:米|块|元|斤)?'
        if re.search(pattern1, text) or re.search(pattern2, text) or re.search(pattern3, text) or re.search(pattern4, text):
            if zodiac not in found_zodiacs:
                found_zodiacs.append(zodiac)
                nums.extend(ZODIAC_NUMS[zodiac])
    return nums, found_zodiacs


def extract_special_zodiac(text):
    """提取特肖下注（按生肖下注，不是按号码）
    如：特肖 鸡龙鼠马蛇猪 各肖10米 → 6个生肖各10块
    返回：([(生肖, 金额), ...], 生肖列表)
    """
    # 必须包含"特肖"或"各肖"才是特肖下注
    if "特肖" not in text and "各肖" not in text:
        return [], []
    
    zodiac_chars = "".join(ZODIAC_NUMS.keys())
    found_zodiacs = []
    amount = extract_amount(text)
    
    if amount is None:
        return [], []
    
    # 提取所有生肖字（按出现顺序，不重复）
    for z in zodiac_chars:
        if z in text and z not in found_zodiacs:
            # 确保是单独的生肖字，不是其他词的一部分
            found_zodiacs.append(z)
    
    if not found_zodiacs:
        return [], []
    
    bets = [(z, amount) for z in found_zodiacs]
    return bets, found_zodiacs


def extract_color(text):
    """提取波色下注，返回对应的号码列表"""
    nums = []
    found_colors = []
    for color in ["红波", "蓝波", "绿波", "红", "蓝", "绿"]:
        # 波色+各/每个/个数 等格式
        pattern1 = color + r'\s*(?:各|每个|每号|每字|个数|个)'
        # 波色+数字金额
        pattern2 = color + r'\s*\d+\s*(?:米|块|元|¥|斤)'
        # 波色+中文数字金额
        pattern3 = color + r'\s*[一二三四五六七八九十百零两]+\s*(?:米|块|元|斤)?'
        # 特+波色
        pattern4 = r'特' + color
        if re.search(pattern1, text) or re.search(pattern2, text) or re.search(pattern3, text) or re.search(pattern4, text):
            color_name = color if len(color) == 2 else color + "波"
            if color_name not in found_colors:
                found_colors.append(color_name)
                nums.extend(COLOR_NUMS[color_name])
    return nums, found_colors


def extract_head(text):
    """提取头数下注，如 '0头各号10米'、'3头各20'
    头数指号码的十位数字：
    - 0头: 01,02,03,04,05,06,07,08,09（9个）
    - 1头: 10,11,12,13,14,15,16,17,18,19（10个）
    - 2头: 20-29（10个）
    - 3头: 30-39（10个）
    - 4头: 40-49（10个）
    """
    nums = []
    found_heads = []
    # 匹配 "X头各/每个/各号" 等格式
    for head in range(5):  # 0-4头
        pattern = str(head) + r'头\s*(?:各|每个|每号|每字|个数|个|号)'
        if re.search(pattern, text):
            found_heads.append(f"{head}头")
            if head == 0:
                nums.extend(range(1, 10))  # 0头 = 01-09
            else:
                start = head * 10
                nums.extend(range(start, start + 10))  # 1头=10-19, etc.
    return nums, found_heads


def extract_tail(text):
    """提取尾数下注，如 '0尾各数10'、'0尾各10'、'5尾'（单独出现）
    尾数是指号码的个位数字：
    - 0尾: 10,20,30,40（4个，因为没有00）
    - 1-9尾: 各5个（如1尾=01,11,21,31,41）
    """
    nums = []
    # 匹配所有 "X尾" 的模式（后面可以跟各/数/金额等）
    # 找出所有单个数字+尾的组合
    tails_found = re.findall(r'(\d)尾', text)
    for tail_str in tails_found:
        tail = int(tail_str)
        for n in range(1, 50):
            if n % 10 == tail:
                nums.append(n)
    # 去重
    return list(set(nums))


def has_numbers(text):
    """判断文本中是否包含号码（直接号码或生肖或尾数）"""
    # 直接号码
    if extract_numbers_direct(text):
        return True
    # 生肖
    for zodiac in ZODIAC_NUMS:
        if zodiac + "号" in text or zodiac + "字" in text or zodiac + "各" in text:
            return True
    # 尾数
    if re.search(r'\d尾\s*各', text):
        return True
    return False


def extract_buy_pattern(text):
    """提取 'X买Y米' 格式的下注，X是号码（支持一位数），Y是金额
    如：4买20米 → 04号 20元
    """
    results = []
    # 匹配：数字 + 买 + 数字 + 米/块/元
    m = re.search(r'(\d{1,2})\s*买\s*(\d+)\s*(?:米|块|元|¥)?', text)
    if m:
        num = int(m.group(1))
        amt = int(m.group(2))
        if 1 <= num <= 49:
            results.append((num, amt))
    return results


def extract_num_amount_pattern(text):
    """提取 '号码=金额'、'号码-金额米' 等格式
    如：16-15米 → 16号15元；44=16闷 → 44号16元；32：140 → 32号140元
    注意：只在后面带单位（米/块/元/闷）或前面是等号/冒号时，才认为是金额（否则是号码分隔符）
    如果有连续多个冒号分隔数字（如7:19:43），冒号是号码分隔符，不是金额分隔符
    """
    results = []
    
    # 先检查：有没有连续冒号分隔的多个数字（冒号是号码分隔符）
    has_colon_separated_nums = bool(re.search(r'\d{1,2}\s*[：:]\s*\d{1,2}\s*[：:]\s*\d{1,2}', text))

    # 1. 号码=金额 格式（等号肯定是号码=金额）
    for m in re.finditer(r'(?<!\d)(\d{1,2})\s*=\s*(\d+)\s*(?:米|块|元|¥|闷)?', text):
        num = int(m.group(1))
        amt = int(m.group(2))
        if 1 <= num <= 49:
            results.append((num, amt))
    
    # 2. 号码：金额 格式（只有单个冒号时才是金额分隔，多个冒号是号码分隔）
    if not has_colon_separated_nums:
        for m in re.finditer(r'(?<!\d)(\d{1,2})\s*[：:]\s*(\d+)\s*(?:米|块|元|¥|闷)?', text):
            num = int(m.group(1))
            amt = int(m.group(2))
            if 1 <= num <= 49:
                results.append((num, amt))

    # 3. 号码-金额米 格式（只有后面带单位时才是金额，否则是号码分隔）
    for m in re.finditer(r'(?<!\d)(\d{1,2})\s*-\s*(\d+)\s*(?:米|块|元|¥|闷)', text):
        num = int(m.group(1))
        amt = int(m.group(2))
        if 1 <= num <= 49:
            results.append((num, amt))
    
    # 4. 号码.金额¥ 格式（点号+人民币符号，如 03.40¥ = 03号40元）
    for m in re.finditer(r'(?<!\d)(\d{1,2})\.(\d+)\s*[¥￥]', text):
        num = int(m.group(1))
        amt = int(m.group(2))
        if 1 <= num <= 49:
            results.append((num, amt))

    return results


def parse_line(line, pending_amount=None):
    """解析一行下注文本
    
    Args:
        line: 行文本
        pending_amount: 上一行待继承的金额（跨行情况）
    
    Returns:
        (bets_list, info, new_pending_amount)
        bets_list: [(号码, 金额), ...]
        info: 解析信息字符串
        new_pending_amount: 留给下一行的金额
    """
    line = line.strip()
    if not line:
        return [], "空行", None
    
    # 去掉"澳特/奥特/新澳特"等前缀（视为特码的另一种写法，不是忽略）
    original_line = line
    prefix_patterns = [
        r'^\d*澳特[:：]?',
        r'^\d*奥特[:：]?',
        r'^新澳特[:：]?',
        r'^澳门特[:：]?',
        r'^新澳[:：]?',
        r'^新[:：]?',
    ]
    for pat in prefix_patterns:
        line = re.sub(pat, '', line).strip()
    
    # 检查是否是特肖下注（按生肖下注，不是按号码）
    sz_bets, sz_zodiacs = extract_special_zodiac(line)
    if sz_bets:
        info = f"特肖({','.join(sz_zodiacs)}) {len(sz_bets)}肖 ×¥{sz_bets[0][1]}"
        # 返回格式：([(类型, 生肖, 金额), ...], info, pending)
        special_results = [("特肖", z, amt) for z, amt in sz_bets]
        return special_results, info, None
    
    # 检查纯聊天内容
    if line.strip() in CHAT_WORDS:
        return [], "忽略行（聊天内容）", None
    
    # 检查人名/标识行
    name_marker_count = sum(1 for m in NAME_MARKERS if m in line)
    if name_marker_count >= 2:
        return [], "忽略行（人名标识）", None
    
    # 检查单行纯人名（完全匹配）
    if line.strip() in NAME_MARKERS:
        return [], "忽略行（人名）", None
    
    # 检查时间行
    if re.search(r'\d{4}年\d{1,2}月\d{1,2}日', line):
        return [], "时间行", None
    
    # 检查纯计算行/电话号码（长数字或带*号运算）
    if re.match(r'^[\d\+\-\=\*\s（）()、,，.。:：]+$', line) and not has_numbers(line):
        return [], "计算行", None
    # 带*的算式直接忽略
    if '*' in line and re.search(r'\d+\*\d+', line):
        return [], "计算行", None
    
    # 检查是否是纯金额行（只有"各X"，金额继承到上一行的号码）
    if is_amount_only_line(line):
        amt = extract_amount(line)
        if amt:
            return [], f"金额行（待继承 ¥{amt}）", amt
        return [], "纯金额行（未识别）", None
    
    # 去掉行前缀
    original_line = line
    for prefix in sorted(PREFIX_FILTER, key=len, reverse=True):
        if line.startswith(prefix):
            line = line[len(prefix):]
            break
    
    # ===== 一行多段检测：支持多种金额格式混合（各X式、号额式、买X式） =====
    # 收集所有金额锚点：(start_pos, end_pos, amount, num_str)
    # num_str 是号额式/买式自带的号码字符串，各X式为None
    anchors = []
    
    # 1. 各X式
    ge_pattern = r'各(?:数|字|号|个)?\s*(\d+|[一二三四五六七八九十百零两]+)\s*(?:米|块|元|¥|号|字|数|斤|闷)?'
    for m in re.finditer(ge_pattern, line):
        amt = extract_amount(m.group(0))
        if amt is not None:
            anchors.append((m.start(), m.end(), amt, None, 'ge'))
    
    # 2. 号额式：号码=金额（等号）
    for m in re.finditer(r'(?<!\d)(\d{1,2})\s*=\s*(\d+)\s*(?:米|块|元|¥|闷)?', line):
        num = int(m.group(1))
        amt = int(m.group(2))
        if 1 <= num <= 49:
            anchors.append((m.start(), m.end(), amt, str(num), 'na'))
    
    # 3. 号额式：号码：金额（单个冒号，多个冒号的是号码分隔符）
    has_colon_multi = bool(re.search(r'\d{1,2}\s*[：:]\s*\d{1,2}\s*[：:]\s*\d{1,2}', line))
    if not has_colon_multi:
        for m in re.finditer(r'(?<!\d)(\d{1,2})\s*[：:]\s*(\d+)\s*(?:米|块|元|¥|闷)?', line):
            num = int(m.group(1))
            amt = int(m.group(2))
            if 1 <= num <= 49:
                anchors.append((m.start(), m.end(), amt, str(num), 'na'))
    
    # 4. 买式：号码买金额
    for m in re.finditer(r'(?<!\d)(\d{1,2})\s*买\s*(\d+)\s*(?:米|块|元|¥|斤)?', line):
        num = int(m.group(1))
        amt = int(m.group(2))
        if 1 <= num <= 49:
            anchors.append((m.start(), m.end(), amt, str(num), 'buy'))
    
    # 5. 号码.金额¥ 格式（点号+人民币符号）
    for m in re.finditer(r'(?<!\d)(\d{1,2})\.(\d+)\s*[¥￥]', line):
        num = int(m.group(1))
        amt = int(m.group(2))
        if 1 <= num <= 49:
            anchors.append((m.start(), m.end(), amt, str(num), 'na'))
    
    # 按位置排序
    anchors.sort(key=lambda x: x[0])
    
    if len(anchors) >= 2:
        all_bets = []
        prev_end = 0
        seg_infos = []
        
        for start, end, amt, num_str, atype in anchors:
            if atype == 'ge':
                # 各X式：号码段在"各"字前面
                num_seg = line[prev_end:start].strip()
                # 去掉段首的分隔符（逗号、句号、加号等）
                num_seg = re.sub(r'^[，,。.！!；;、\s+]+', '', num_seg)
                if not num_seg:
                    prev_end = end
                    continue
                
                seg_line_clean = re.sub(r'[（(].*?[)）]', '', num_seg)
                
                direct_nums = extract_numbers_direct(seg_line_clean)
                zodiac_nums, zodiacs = extract_zodiac(seg_line_clean)
                color_nums, colors = extract_color(seg_line_clean)
                head_nums, heads = extract_head(seg_line_clean)
                tail_nums = extract_tail(seg_line_clean)
                # 宽松生肖补充
                for zodiac in ZODIAC_NUMS:
                    if zodiac in seg_line_clean and zodiac not in zodiacs:
                        zodiacs.append(zodiac)
                        zodiac_nums.extend(ZODIAC_NUMS[zodiac])
                
                seg_nums = direct_nums + zodiac_nums + color_nums + head_nums + tail_nums
                if seg_nums:
                    all_bets.extend([(n, amt) for n in seg_nums])
                    seg_infos.append(f"{len(seg_nums)}个×{amt}")
            else:
                # 号额式/买式：自带号码
                num = int(num_str)
                all_bets.append((num, amt))
                seg_infos.append(f"{num}号×{amt}")
            
            prev_end = end
        
        if all_bets:
            return all_bets, f"混合多段({'+'.join(seg_infos)})", None
    
    # 先提取金额（此时括号里的金额还在）
    amount = extract_amount(line)
    
    # 去掉括号及内容（小计），然后再提取号码
    line_no_bracket = re.sub(r'[（(].*?[)）]', '', line)
    
    # 如果本行没找到金额，使用待继承的金额
    if amount is None and pending_amount is not None:
        amount = pending_amount

    # 先检查 "X买Y米" 格式（号码+买+金额，自带号码和金额）
    buy_bets = extract_buy_pattern(line_no_bracket)
    if buy_bets and amount is not None:
        info = f"买式下注 {len(buy_bets)}个 ¥{buy_bets[0][1]}"
        return buy_bets, info, None

    # 再检查 "号码=金额"、"号码-金额米" 格式（自带号码和金额）
    na_bets = extract_num_amount_pattern(line_no_bracket)
    if na_bets:
        # 如果有这种格式，直接返回（避免和后面的直选重复计算）
        info = f"号额式下注 {len(na_bets)}个"
        return na_bets, info, None
    
    if amount is None:
        return [], f"未识别金额: {original_line[:30]}", None
    
    # 提取号码（用去掉括号后的文本）
    direct_nums = extract_numbers_direct(line_no_bracket)
    zodiac_nums, zodiacs = extract_zodiac(line_no_bracket)
    color_nums, colors = extract_color(line_no_bracket)
    head_nums, heads = extract_head(line_no_bracket)
    tail_nums = extract_tail(line_no_bracket)
    
    # 宽松模式：如果有金额，补充提取文本中出现的所有生肖（处理生肖和号码混排的情况）
    if amount is not None:
        for zodiac in ZODIAC_NUMS:
            if zodiac in line_no_bracket and zodiac not in zodiacs:
                zodiacs.append(zodiac)
                zodiac_nums.extend(ZODIAC_NUMS[zodiac])
    
    # 不去重！同一行同一号码出现多次要分别计算
    all_nums = direct_nums + zodiac_nums + color_nums + head_nums + tail_nums
    
    if not all_nums:
        return [], f"未识别号码: {original_line[:30]}", None
    
    results = [(num, amount) for num in all_nums]
    
    info_parts = []
    if direct_nums:
        info_parts.append(f"直选{len(direct_nums)}个")
    if zodiacs:
        info_parts.append(f"生肖({','.join(zodiacs)})")
    if colors:
        info_parts.append(f"波色({','.join(colors)})")
    if heads:
        info_parts.append(f"头数({','.join(heads)})")
    if tail_nums:
        info_parts.append("尾数")
    
    return results, "、".join(info_parts) + f" ¥{amount}", None


def has_numbers_or_zodiac(line):
    """判断一行是否包含号码或生肖或波色（有号码但缺金额的情况）"""
    # 检查是否有直接号码
    nums = extract_numbers_direct(line)
    if nums:
        return True, nums, [], []
    # 检查是否有生肖
    zodiac_nums, zodiacs = extract_zodiac(line)
    if zodiac_nums:
        return True, [], zodiac_nums, zodiacs
    # 检查是否有波色
    color_nums, colors = extract_color(line)
    if color_nums:
        return True, [], color_nums, []
    # 检查是否有头数
    head_nums, heads = extract_head(line)
    if head_nums:
        return True, [], head_nums, []
    # 检查是否有尾数
    tail_nums = extract_tail(line)
    if tail_nums:
        return True, [], [], []
    return False, [], [], []


def parse_text(text):
    """解析整段下注文本"""
    lines = text.strip().split('\n')
    all_bets = []  # 普通号码下注：[(号码, 金额), ...]
    all_special_zodiac = []  # 特肖下注：[(生肖, 金额), ...]
    detail_list = []  # 每条下注明细：[("号码"/"特肖", 号码或生肖, 金额, 原始文本, 下注人), ...]
    parsed_lines = []
    skipped_lines = []
    
    pending_amount = None  # 跨行待继承的金额（金额在前，号码在后）
    pending_bet_info = None  # 待补金额的下注（号码在前，金额在后）
    current_bettor = None  # 当前署名（继承上一行的）
    last_was_nickname = False  # 上一行是不是昵称行（用于判断下一行是不是时间）
    
    for line in lines:
        line = line.strip()
        if not line:
            # 空行不重置署名（聊天记录里昵称和内容之间可能有空行）
            continue
        
        # ========== 署名识别逻辑 ==========
        # 1. 先判断是不是时间行 → 如果是，跳过（不解析，也不改署名）
        if is_datetime_line(line):
            skipped_lines.append((line, "时间戳"))
            continue
        
        # 2. 判断是不是昵称行（聊天记录的人名）
        # 昵称行特点：单独一行，不是下注内容，不是时间
        if is_nickname_line(line):
            # 再确认一下：这行不是下注内容（用 parse_line 验证）
            test_bets, test_info, _ = parse_line(line, None)
            if not test_bets and "未识别" not in test_info and "金额行" not in test_info:
                # 确认是昵称行
                current_bettor = line
                last_was_nickname = True
                skipped_lines.append((line, f"昵称/署名：{line}"))
                continue
        
        # 3. 行首带"名字："格式的（老格式兼容）
        bettor, rest_line = extract_bettor(line)
        if bettor:
            current_bettor = bettor
            parse_line_text = rest_line
        else:
            parse_line_text = line
        
        last_was_nickname = False
        
        # 先检查：如果有上一行待补金额的下注，且本行是纯金额行
        if pending_bet_info is not None:
            amt = extract_amount(line)
            if amt is not None and is_amount_only_line(line):
                # 补上金额
                direct_nums, zodiac_nums, zodiacs, color_nums, head_nums, tail_nums, orig_line = pending_bet_info
                all_nums = list(set(direct_nums + zodiac_nums + color_nums + head_nums + tail_nums))
                results = [(num, amt) for num in sorted(all_nums)]
                all_bets.extend(results)
                # 加入明细列表
                combined_orig = orig_line + " + " + line
                for num, a in results:
                    detail_list.append(("号码", num, a, combined_orig, current_bettor or ""))
                info_parts = []
                if direct_nums:
                    info_parts.append(f"直选{len(direct_nums)}个")
                if zodiacs:
                    info_parts.append(f"生肖({','.join(zodiacs)})")
                if color_nums:
                    info_parts.append(f"波色")
                if head_nums:
                    info_parts.append("头数")
                if tail_nums:
                    info_parts.append("尾数")
                info = "、".join(info_parts) + f" ¥{amt}(跨行)"
                parsed_lines.append((combined_orig, info, len(results)))
                pending_bet_info = None
                pending_amount = None
                continue
        
        bets, info, new_pending = parse_line(parse_line_text, pending_amount)
        
        if bets:
            # 区分普通下注和特肖
            normal_bets = []
            special_bets = []
            for b in bets:
                if isinstance(b, tuple) and len(b) == 3 and b[0] == "特肖":
                    special_bets.append((b[1], b[2]))  # (生肖, 金额)
                else:
                    normal_bets.append(b)  # (号码, 金额)
            
            if normal_bets:
                all_bets.extend(normal_bets)
                for num, amt in normal_bets:
                    detail_list.append(("号码", num, amt, line, current_bettor or ""))
            if special_bets:
                all_special_zodiac.extend(special_bets)
                for zodiac, amt in special_bets:
                    detail_list.append(("特肖", zodiac, amt, line, current_bettor or ""))
            
            parsed_lines.append((line, info, len(bets)))
            pending_amount = None  # 重置
            pending_bet_info = None
        elif "金额行" in info:
            # 金额行，保存待继承
            pending_amount = new_pending
            skipped_lines.append((line, info))
        elif "未识别金额" in info:
            # 有号码但没金额，保存待补（号码在前，金额在后）
            has_nums, direct_nums, zodiac_nums, zodiacs = has_numbers_or_zodiac(line)
            tail_nums = extract_tail(line)
            color_nums, colors = extract_color(line)
            head_nums, heads = extract_head(line)
            if has_nums or tail_nums or color_nums or head_nums:
                pending_bet_info = (direct_nums, zodiac_nums, zodiacs, color_nums, head_nums, tail_nums, line)
                skipped_lines.append((line, "待补金额"))
            else:
                skipped_lines.append((line, info))
                pending_bet_info = None
        else:
            skipped_lines.append((line, info))
            pending_amount = None
            pending_bet_info = None
    
    # 按号码汇总
    summary = defaultdict(int)
    for num, amt in all_bets:
        summary[num] += amt
    
    summary_list = sorted(summary.items(), key=lambda x: x[0])
    
    # 按生肖汇总特肖
    sz_summary = defaultdict(int)
    for z, amt in all_special_zodiac:
        sz_summary[z] += amt
    
    sz_summary_list = sorted(sz_summary.items(), key=lambda x: x[0])
    
    total_amount = sum(amt for _, amt in all_bets) + sum(amt for _, amt in all_special_zodiac)
    
    return {
        "total_bets": len(all_bets),
        "total_amount": total_amount,
        "unique_numbers": len(summary),
        "summary": summary_list,
        "special_zodiac_bets": all_special_zodiac,
        "special_zodiac_summary": sz_summary_list,
        "special_zodiac_count": len(sz_summary),
        "parsed_lines": parsed_lines,
        "skipped_lines": skipped_lines,
        "detail_list": detail_list,  # 每条下注明细：[("号码"/"特肖", 号码或生肖, 金额, 原始文本), ...]
    }


if __name__ == "__main__":
    # 测试
    test_text = """02,07,11,14,19,23,26,32,38,43,45,49各40
特10-12-14-16-18
各10
蛇各12
0尾各数10
02、06、07、37各3米
05.17.29.41各十
41.42.43各四十
38下400米
02=20
特龙号各15
香港，特羊号各15
各十
04-40各10米16-28各5米共30米
狗鸡虎每个5米
21=10米
33=25米
05-17-07-19各25
特07  二十
19.十
31.43.各五"""
    
    result = parse_text(test_text)
    print(f"解析到 {result['unique_numbers']} 个号码，总金额 ¥{result['total_amount']}")
    print(f"共 {result['total_bets']} 笔下注")
    print("\n号码汇总:")
    for num, amt in result["summary"]:
        print(f"  {num:02d}: ¥{amt}")
    print(f"\n已解析 {len(result['parsed_lines'])} 行")
    for line, info, cnt in result['parsed_lines']:
        print(f"  [{info}] {line[:50]}")
    print(f"\n跳过 {len(result['skipped_lines'])} 行")
    for line, info in result['skipped_lines']:
        print(f"  [{info}] {line[:40]}")
