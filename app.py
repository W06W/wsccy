import streamlit as st
import pandas as pd
from collections import defaultdict
import os
import json
from datetime import datetime
import sys
import importlib
sys.path.insert(0, os.path.dirname(__file__))

# 自动重载 bet_parser 模块（避免模块缓存）
if "bet_parser" in sys.modules:
    importlib.reload(sys.modules["bet_parser"])
from bet_parser import parse_text, ZODIAC_NUMS

# ==================== 配置 ====================
st.set_page_config(
    page_title="六合彩庄家下注统计",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "bets.json")
USERS_FILE = os.path.join(os.path.dirname(__file__), "data", "users.json")

# ==================== 数据持久化 ====================
def load_bets():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 兼容性：旧数据没有"类型"字段，补上
        for bet in data.get("bets", []):
            if "类型" not in bet:
                bet["类型"] = "号码"
            if "生肖" not in bet:
                bet["生肖"] = ""
        return data
    return {"bets": [], "payout_ratio": 47.0, "session_name": "默认场次"}

def save_bets(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # 默认管理员账号
    default_users = {
        "admin": {"password": "admin123", "role": "admin", "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    }
    save_users(default_users)
    return default_users

def save_users(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

data = load_bets()
bets = data.get("bets", [])
payout_ratio = data.get("payout_ratio", 47.0)
session_name = data.get("session_name", "默认场次")
warning_limit = data.get("warning_limit", 0)  # 预警额度，0=按下注总额
users = load_users()

# ==================== 登录验证 ====================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""

if not st.session_state.logged_in:
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="text-align:center;">
            <h1>💰 六合彩庄家下注统计</h1>
            <p style="color:#666;">请登录后使用</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        with st.form("login_form"):
            username = st.text_input("👤 用户名")
            password = st.text_input("🔒 密码", type="password")
            submit = st.form_submit_button("✅ 登 录", type="primary", use_container_width=True)

            if submit:
                if username in users and users[username]["password"] == password:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = users[username].get("role", "operator")
                    st.success("登录成功！")
                    st.rerun()
                else:
                    st.error("用户名或密码错误")

        st.info("💡 默认管理员账号：`admin` / `admin123`")
    st.stop()

# 已登录，继续主页面
current_user = st.session_state.username
current_role = st.session_state.role

# ==================== 侧边栏 ====================
st.sidebar.title("💰 庄家下注统计")
st.sidebar.markdown("---")

# 当前用户
role_label = "管理员" if current_role == "admin" else "操作员"
st.sidebar.info(f"👤 **{current_user}**\n\n角色：{role_label}")
if st.sidebar.button("🚪 退出登录", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.rerun()

st.sidebar.markdown("---")

# 场次管理
session_name_input = st.sidebar.text_input("场次名称", value=session_name)
if session_name_input != session_name:
    data["session_name"] = session_name_input
    save_bets(data)
    st.rerun()

# 赔率设置
st.sidebar.markdown("### ⚙️ 赔率设置")
new_ratio = st.sidebar.number_input(
    "赔付倍率（中一赔几）",
    min_value=1.0,
    max_value=100.0,
    value=float(payout_ratio),
    step=0.5,
    help="例：47 表示下注1元，中奖赔47元（特码1赔47）"
)
if new_ratio != payout_ratio:
    data["payout_ratio"] = new_ratio
    save_bets(data)
    st.rerun()

# 预警额度设置
st.sidebar.markdown("### ⚠️ 预警设置")
new_warning = st.sidebar.number_input(
    "单号赔付预警线（元）",
    min_value=0,
    max_value=1000000,
    value=int(warning_limit),
    step=100,
    help="设为0则按下注总额判断（超出下注总额=亏损）；设具体数值则超过该数值就标红预警"
)
if new_warning != warning_limit:
    data["warning_limit"] = new_warning
    save_bets(data)
    st.rerun()

st.sidebar.markdown("---")

# 清空所有下注
if st.sidebar.button("🗑️ 清空本场所有下注", use_container_width=True):
    if st.sidebar.checkbox("确认清空？不可撤销"):
        data["bets"] = []
        save_bets(data)
        st.success("已清空所有下注记录！")
        st.rerun()

# ==================== 计算统计 ====================
def calc_stats(bets, payout_ratio, warning_limit=0):
    # 按号码汇总
    num_stats = defaultdict(lambda: {"总下注": 0, "人数": 0, "明细": []})
    # 按生肖汇总特肖
    sz_stats = defaultdict(lambda: {"总下注": 0, "人数": 0, "明细": []})
    total_bets = 0
    total_bettors = set()

    for bet in bets:
        amount = bet["金额"]
        bettor = bet.get("下注人", "")
        bet_type = bet.get("类型", "号码")
        
        if bet_type == "特肖":
            zodiac = bet.get("生肖", "")
            if zodiac:
                sz_stats[zodiac]["总下注"] += amount
                sz_stats[zodiac]["人数"] += 1
                sz_stats[zodiac]["明细"].append(bet)
        else:
            num = bet["号码"]
            num_stats[num]["总下注"] += amount
            num_stats[num]["人数"] += 1
            num_stats[num]["明细"].append(bet)
        
        total_bets += amount
        if bettor:
            total_bettors.add(bettor)

    # 预警线：有设置就用设置值，否则按下注总额
    warning_line = warning_limit if warning_limit > 0 else total_bets

    # 构建统计 DataFrame（每个号码的总赔付 = 号码赔付 + 对应生肖特肖赔付）
    rows = []
    for num in range(1, 50):
        info = num_stats[num]
        num_payout = info["总下注"] * payout_ratio
        
        # 这个号码对应的生肖的特肖赔付
        num_zodiac = ""
        sz_payout = 0
        for z, nums in ZODIAC_NUMS.items():
            if num in nums:
                num_zodiac = z
                sz_payout = sz_stats[z]["总下注"] * 11  # 特肖1赔11（连本带利）
                break
        
        total_payout = num_payout + sz_payout
        profit = total_bets - total_payout
        
        # 风险等级
        if total_payout > warning_line and info["总下注"] > 0:
            risk_level = "超预警 ⚠️"
        elif profit < 0:
            risk_level = "亏损 ⚠️"
        elif profit < total_bets * 0.1:
            risk_level = "低利润"
        else:
            risk_level = "正常"
        
        rows.append({
            "号码": f"{num:02d}",
            "号码数值": num,
            "生肖": num_zodiac,
            "下注人数": info["人数"],
            "总下注金额": info["总下注"],
            "号码赔付额": round(num_payout, 2),
            "特肖赔付额": round(sz_payout, 2),
            "中奖赔付额": round(total_payout, 2),
            "庄家盈亏": round(profit, 2),
            "风险等级": risk_level
        })

    df = pd.DataFrame(rows)
    
    # 特肖统计
    sz_summary = []
    for zodiac in ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]:
        info = sz_stats[zodiac]
        sz_summary.append({
            "生肖": zodiac,
            "总下注": info["总下注"],
            "人数": info["人数"],
            "赔付额": info["总下注"] * 11
        })
    
    return df, total_bets, len(total_bettors), warning_line, sz_summary

stats_df, total_bets, total_bettors, warning_line, sz_summary = calc_stats(bets, payout_ratio, warning_limit)

# ==================== 主页面 ====================
st.title(f"💰 六合彩庄家下注统计 - {session_name}")
st.markdown("---")

# 顶部指标
col1, col2, col3, col4 = st.columns(4)
col1.metric("💰 下注总额", f"¥{total_bets:,.2f}")
col2.metric("👥 下注人数", f"{total_bettors} 人" if total_bettors > 0 else "暂无")
col3.metric("📝 下注笔数", f"{len(bets)} 笔")
col4.metric("🎯 赔付倍率", f"1 : {payout_ratio}")

st.markdown("---")

# 标签页
if current_role == "admin":
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["📋 智能录入", "📊 号码统计", "🎯 收盘方案", "🎰 开奖结算", "📋 下注明细", "👥 账号管理"]
    )
else:
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📋 智能录入", "📊 号码统计", "🎯 收盘方案", "🎰 开奖结算", "📋 下注明细"]
    )

# ========== 智能导入 ==========
with tab1:
    st.subheader("📋 智能文本录入")
    st.info("💡 直接复制粘贴下注聊天记录，自动识别号码、金额、生肖、尾数，一键录入。识别不了的会留在输入框，改好后再录！")

    col1, col2 = st.columns([3, 2])

    # 用独立的状态变量控制输入框内容（不能直接改 widget 的 key，会报错）
    if "smart_input_text" not in st.session_state:
        st.session_state.smart_input_text = ""

    with col1:
        bet_text = st.text_area(
            "粘贴下注文本（支持多行）",
            value=st.session_state.smart_input_text,
            height=400,
            placeholder="示例：\n02,07,11各40\n特10-12-14各10\n蛇各12\n0尾各数10\n狗鸡虎每个5米"
        )
        import_note = st.text_input("备注（可选）", value="批量导入")
        import_btn = st.button("✅ 一键录入", type="primary", use_container_width=True)

    with col2:
        st.markdown("### 🐴 生肖对照表")
        zodiac_df = pd.DataFrame([
            {"生肖": zodiac, "号码": " ".join([f"{n:02d}" for n in nums])}
            for zodiac, nums in ZODIAC_NUMS.items()
        ])
        st.dataframe(zodiac_df, use_container_width=True, hide_index=True)

        st.markdown("### 🎨 波色对照表")
        color_data = [
            {"波色": "🔴 红波", "号码": "01 02 07 08 12 13 18 19 23 24 29 30 34 35 40 45 46", "数量": "17个"},
            {"波色": "🔵 蓝波", "号码": "03 04 09 10 14 15 20 25 26 31 36 37 41 42 47 48", "数量": "16个"},
            {"波色": "🟢 绿波", "号码": "05 06 11 16 17 21 22 27 28 32 33 38 39 43 44 49", "数量": "16个"},
        ]
        color_df = pd.DataFrame(color_data)
        st.dataframe(color_df, use_container_width=True, hide_index=True)

    if import_btn:
        if bet_text.strip():
            result = parse_text(bet_text)
            has_bets = result["unique_numbers"] > 0 or result.get("special_zodiac_count", 0) > 0
            if has_bets:
                bet_count = 0
                # 用 detail_list 逐条保存，保留原始文本和下注人
                for bet_type, target, amt, orig_text, bettor in result.get("detail_list", []):
                    # 下注人：解析到署名就用署名，否则用默认的"批量导入"
                    final_bettor = bettor if bettor else "批量导入"
                    if bet_type == "号码":
                        new_bet = {
                            "id": len(bets) + 1 + bet_count,
                            "类型": "号码",
                            "号码": target,
                            "生肖": "",
                            "金额": int(amt),
                            "下注人": final_bettor,
                            "操作员": current_user,
                            "备注": import_note,
                            "原始文本": orig_text,
                            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                    else:  # 特肖
                        new_bet = {
                            "id": len(bets) + 1 + bet_count,
                            "类型": "特肖",
                            "号码": "",
                            "生肖": target,
                            "金额": int(amt),
                            "下注人": final_bettor,
                            "操作员": current_user,
                            "备注": import_note,
                            "原始文本": orig_text,
                            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                    bets.append(new_bet)
                    bet_count += 1
                data["bets"] = bets
                save_bets(data)

                # 把识别不了的行留在输入框里，方便手动修改
                if result["skipped_lines"]:
                    # skipped_lines 可能是字符串列表，也可能是(行号, 内容)元组列表
                    skipped_text = "\n".join([
                        line[1] if isinstance(line, tuple) else line
                        for line in result["skipped_lines"]
                    ])
                    st.session_state.smart_input_text = skipped_text
                    sz_info = f"，{result.get('special_zodiac_count', 0)}个特肖" if result.get("special_zodiac_count", 0) > 0 else ""
                    st.success(f"✅ 成功录入 {result['unique_numbers']} 个号码{sz_info}，共 ¥{result['total_amount']}（解析{len(result['parsed_lines'])}行，剩余{len(result['skipped_lines'])}行待处理）")
                    st.warning(f"⚠️ 有 {len(result['skipped_lines'])} 行未识别，已留在输入框，请手动修改后再次录入")
                else:
                    st.session_state.smart_input_text = ""
                    sz_info = f"，{result.get('special_zodiac_count', 0)}个特肖" if result.get("special_zodiac_count", 0) > 0 else ""
                    st.success(f"✅ 全部录入成功！{result['unique_numbers']} 个号码{sz_info}，共 ¥{result['total_amount']}（{len(result['parsed_lines'])}行全部识别）")

                st.rerun()
            else:
                st.warning("未识别到任何下注号码，请检查文本格式")
        else:
            st.warning("请先粘贴下注文本")

# ========== 号码统计 ==========
with tab2:
    st.subheader("📊 各号码下注统计")

    # ===== 49个号码总览面板 =====
    st.markdown("#### 🎯 49个号码实时金额")
    
    # 准备数据
    num_amounts = {}
    for num in range(1, 50):
        row = stats_df[stats_df["号码数值"] == num].iloc[0]
        num_amounts[num] = {
            "金额": row["总下注金额"],
            "风险": row["风险等级"]
        }
    
    max_amount = max([v["金额"] for v in num_amounts.values()]) if total_bets > 0 else 1
    
    # 按7列x7行展示
    cols_per_row = 7
    for row_start in range(1, 50, cols_per_row):
        row_end = min(row_start + cols_per_row - 1, 49)
        cols = st.columns(cols_per_row)
        for i, num in enumerate(range(row_start, row_end + 1)):
            info = num_amounts[num]
            amount = info["金额"]
            risk = info["风险"]
            
            # 颜色
            if "超预警" in risk and amount > 0:
                bg_color = "#ff1744"
                border_color = "#b71c1c"
                text_color = "#ffffff"
            elif "亏损" in risk and amount > 0:
                bg_color = "#ffe0e0"
                border_color = "#e53935"
                text_color = "#c62828"
            elif "低利润" in risk and amount > 0:
                bg_color = "#fff8e1"
                border_color = "#f9a825"
                text_color = "#e65100"
            elif amount > 0:
                bg_color = "#e8f5e9"
                border_color = "#43a047"
                text_color = "#2e7d32"
            else:
                bg_color = "#f5f5f5"
                border_color = "#e0e0e0"
                text_color = "#9e9e9e"
            
            # 高度比例（有金额的按比例显示）
            height_ratio = 0.3 + 0.7 * (amount / max_amount) if max_amount > 0 and amount > 0 else 0.3
            height_px = int(80 + 60 * height_ratio)
            
            with cols[i]:
                st.markdown(
                    f"""
                    <div style="
                        background: {bg_color};
                        border: 2px solid {border_color};
                        border-radius: 10px;
                        padding: 10px 5px;
                        text-align: center;
                        height: {height_px}px;
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        transition: all 0.3s;
                    ">
                        <div style="font-size: 22px; font-weight: bold; color: {text_color}; margin-bottom: 4px;">
                            {num:02d}
                        </div>
                        <div style="font-size: 14px; font-weight: bold; color: {text_color};">
                            ¥{amount:,.0f}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
    
    # 图例
    st.markdown(
        f"""
        <div style="display: flex; gap: 20px; margin-top: 10px; font-size: 13px; color: #666; flex-wrap: wrap;">
            <span><span style="display:inline-block; width:14px; height:14px; background:#ff1744; border:2px solid #b71c1c; border-radius:3px; vertical-align:middle; margin-right:4px;"></span>超预警线（赔付 > ¥{warning_line:,.0f}）</span>
            <span><span style="display:inline-block; width:14px; height:14px; background:#ffe0e0; border:2px solid #e53935; border-radius:3px; vertical-align:middle; margin-right:4px;"></span>亏损（赔付 > 下注总额）</span>
            <span><span style="display:inline-block; width:14px; height:14px; background:#fff8e1; border:2px solid #f9a825; border-radius:3px; vertical-align:middle; margin-right:4px;"></span>低利润</span>
            <span><span style="display:inline-block; width:14px; height:14px; background:#e8f5e9; border:2px solid #43a047; border-radius:3px; vertical-align:middle; margin-right:4px;"></span>正常盈利</span>
            <span><span style="display:inline-block; width:14px; height:14px; background:#f5f5f5; border:2px solid #e0e0e0; border-radius:3px; vertical-align:middle; margin-right:4px;"></span>暂无下注</span>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    st.markdown("---")
    
    # 筛选有下注的号码
    has_bet_df = stats_df[stats_df["下注人数"] > 0].copy()
    has_bet_df = has_bet_df.sort_values("总下注金额", ascending=False).reset_index(drop=True)
    has_bet_df.index = has_bet_df.index + 1

    if len(has_bet_df) == 0:
        st.info("暂无下注数据，请先在「录入下注」中添加。")
    else:
        # 格式化显示
        display_df = has_bet_df[["号码", "下注人数", "总下注金额", "中奖赔付额", "庄家盈亏", "风险等级"]].copy()
        display_df["总下注金额"] = display_df["总下注金额"].apply(lambda x: f"¥{x:,.2f}")
        display_df["中奖赔付额"] = display_df["中奖赔付额"].apply(lambda x: f"¥{x:,.2f}")
        display_df["庄家盈亏"] = display_df["庄家盈亏"].apply(lambda x: f"¥{x:,.2f}")

        # 高亮风险等级
        def highlight_risk(row):
            if "超预警" in row["风险等级"]:
                return ["background-color: #ff1744; color: #ffffff; font-weight: bold"] * len(row)
            elif "亏损" in row["风险等级"]:
                return ["background-color: #ffe0e0; color: #d32f2f; font-weight: bold"] * len(row)
            elif "低利润" in row["风险等级"]:
                return ["background-color: #fff8e1; color: #f57c00"] * len(row)
            return [""] * len(row)

        styled = display_df.style.apply(highlight_risk, axis=1)
        st.dataframe(styled, use_container_width=True, height=500)

        st.markdown("---")

        # 下注金额分布图
        st.subheader("📈 各号码下注金额分布")

        import plotly.express as px
        chart_df = has_bet_df.sort_values("号码数值")
        fig = px.bar(
            chart_df, x="号码", y="总下注金额",
            color="庄家盈亏",
            color_continuous_scale="RdYlGn",
            title="各号码下注金额（颜色表示庄家盈亏，红=亏损，绿=盈利）",
            text="总下注金额"
        )
        fig.update_layout(
            xaxis=dict(tickmode="linear", tick0=1, dtick=2),
            height=500,
            bargap=0.2
        )
        fig.update_traces(texttemplate="¥%{text:,.0f}", textposition="outside")
        st.plotly_chart(fig, use_container_width=True)

    # ===== 特肖统计 =====
    sz_bets = [b for b in bets if b.get("类型") == "特肖"]
    if sz_bets:
        st.markdown("---")
        st.markdown("#### 🐉 特肖下注统计")
        
        sz_summary = {}
        sz_total = 0
        for b in sz_bets:
            z = b["生肖"]
            amt = b["金额"]
            sz_summary[z] = sz_summary.get(z, 0) + amt
            sz_total += amt
        
        sz_data = []
        for zodiac in ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]:
            amt = sz_summary.get(zodiac, 0)
            nums = ZODIAC_NUMS.get(zodiac, [])
            sz_data.append({
                "生肖": zodiac,
                "对应号码": " ".join([f"{n:02d}" for n in nums]),
                "下注金额": amt,
                "赔率": "1:11",
                "最高赔付": amt * 11 if amt > 0 else 0
            })
        
        sz_df = pd.DataFrame(sz_data)
        sz_df = sz_df[sz_df["下注金额"] > 0].sort_values("下注金额", ascending=False)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("特肖总下注", f"¥{sz_total:,.0f}")
        with col2:
            st.metric("特肖生肖数", f"{len(sz_df)} 个")
        
        st.dataframe(sz_df, use_container_width=True, hide_index=True)

# ========== 收盘方案 ==========
with tab3:
    st.subheader("🎯 收盘风险转嫁方案")
    st.info("💡 计算需要转嫁出去的号码和金额，确保号码部分稳赚不亏。特肖部分自担风险。")

    if total_bets == 0:
        st.info("暂无下注数据，无法生成收盘方案。")
    else:
        # 号码下注和特肖下注明细分
        num_bets_total = sum(b["金额"] for b in bets if b.get("类型", "号码") == "号码")
        sz_bets_total = sum(b["金额"] for b in bets if b.get("类型", "号码") == "特肖")
        
        # 目标利润率设置
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            target_profit_rate = st.slider(
                "号码目标利润率（%）",
                min_value=0,
                max_value=50,
                value=5,
                step=1,
                help="号码部分您最少想赚多少百分比的利润"
            )
        with col2:
            target_profit = num_bets_total * target_profit_rate / 100
            st.metric("🎯 号码目标利润", f"¥{target_profit:,.2f}")
        with col3:
            break_even = num_bets_total - target_profit
            st.metric("⚠️ 号码赔付保本线", f"¥{break_even:,.2f}",
                      help="单号赔付超过这个数，利润就低于目标了")
        with col4:
            st.metric("🐉 特肖总下注", f"¥{sz_bets_total:,.2f}",
                      help="特肖自担风险，不参与转嫁")

        st.markdown("---")

        # 筛选需要转嫁的号码（只看号码赔付，不含特肖）
        risk_nums = stats_df[
            (stats_df["号码赔付额"] > break_even) & (stats_df["下注人数"] > 0)
        ].copy()
        risk_nums = risk_nums.sort_values("号码赔付额", ascending=False).reset_index(drop=True)

        # 特肖风险分析（单独展示）
        sz_risk_list = []
        for sz in sz_summary:
            if sz["总下注"] > 0:
                sz_payout = sz["赔付额"]
                sz_risk_list.append({
                    "生肖": sz["生肖"],
                    "下注金额": sz["总下注"],
                    "中奖赔付": sz_payout,
                })
        sz_risk_list.sort(key=lambda x: -x["中奖赔付"])
        sz_worst_payout = sz_risk_list[0]["中奖赔付"] if sz_risk_list else 0
        sz_worst_profit = sz_bets_total - sz_worst_payout  # 特肖单独的盈亏

        if len(risk_nums) == 0:
            st.success(f"🎉 所有号码都安全！号码部分最差情况也能赚 ¥{num_bets_total - stats_df['号码赔付额'].max():,.2f}（利润率 {(num_bets_total - stats_df['号码赔付额'].max())/num_bets_total*100:.1f}%）")
        else:
            # 计算每个号码需要转嫁的金额（只算号码下注部分）
            risk_nums["需要转嫁下注额"] = risk_nums["总下注金额"].apply(
                lambda x: max(0, x - break_even / payout_ratio)
            )
            risk_nums["转嫁后自留额"] = risk_nums["总下注金额"] - risk_nums["需要转嫁下注额"]
            risk_nums["转嫁后赔付"] = risk_nums["转嫁后自留额"] * payout_ratio
            risk_nums["转嫁后利润"] = num_bets_total - risk_nums["转嫁后赔付"]
            risk_nums["号码"] = risk_nums["号码数值"].apply(lambda x: f"{x:02d}")

            total_pass_on = risk_nums["需要转嫁下注额"].sum()

            # 概览
            c1, c2, c3 = st.columns(3)
            c1.metric("🔴 需转嫁号码数", f"{len(risk_nums)} 个")
            c2.metric("💰 需转嫁下注额", f"¥{total_pass_on:,.2f}")
            c3.metric("✅ 号码保证利润", f"¥{target_profit:,.2f}（{target_profit_rate}%）")

            st.markdown("---")

            # 49格转嫁金额可视化
            st.markdown("### 🎯 49号转嫁金额分布")

            # 构建所有号码的转嫁数据
            risk_dict = {row["号码数值"]: row["需要转嫁下注额"] for _, row in risk_nums.iterrows()}
            max_pass = risk_nums["需要转嫁下注额"].max() if len(risk_nums) > 0 else 1

            # 7x7 网格
            for row_idx in range(7):
                cols = st.columns(7)
                for col_idx in range(7):
                    num = row_idx * 7 + col_idx + 1
                    if num > 49:
                        continue
                    pass_amt = risk_dict.get(num, 0)
                    amount = stats_df[stats_df["号码数值"] == num]["总下注金额"].values[0]

                    if pass_amt > 0:
                        bg_color = "#ff1744"
                        border_color = "#b71c1c"
                        text_color = "white"
                    elif amount > 0:
                        bg_color = "#e8f5e9"
                        border_color = "#43a047"
                        text_color = "#2e7d32"
                    else:
                        bg_color = "#f5f5f5"
                        border_color = "#e0e0e0"
                        text_color = "#9e9e9e"

                    height_ratio = 0.3 + 0.7 * (pass_amt / max_pass) if max_pass > 0 and pass_amt > 0 else 0.3
                    height_px = int(80 + 60 * height_ratio)

                    with cols[col_idx]:
                        st.markdown(
                            f"""
                            <div style="
                                background: {bg_color};
                                border: 2px solid {border_color};
                                border-radius: 10px;
                                padding: 10px 5px;
                                text-align: center;
                                height: {height_px}px;
                                display: flex;
                                flex-direction: column;
                                justify-content: center;
                                transition: all 0.3s;
                            ">
                                <div style="font-size: 22px; font-weight: bold; color: {text_color}; margin-bottom: 4px;">
                                    {num:02d}
                                </div>
                                <div style="font-size: 13px; font-weight: bold; color: {text_color};">
                                    转 ¥{pass_amt:,.0f}
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

            # 图例
            st.markdown(
                f"""
                <div style="display: flex; gap: 20px; margin-top: 10px; font-size: 13px; color: #666; flex-wrap: wrap;">
                    <span><span style="display:inline-block; width:14px; height:14px; background:#ff1744; border:2px solid #b71c1c; border-radius:3px; vertical-align:middle; margin-right:4px;"></span>需转嫁</span>
                    <span><span style="display:inline-block; width:14px; height:14px; background:#e8f5e9; border:2px solid #43a047; border-radius:3px; vertical-align:middle; margin-right:4px;"></span>安全（自留）</span>
                    <span><span style="display:inline-block; width:14px; height:14px; background:#f5f5f5; border:2px solid #e0e0e0; border-radius:3px; vertical-align:middle; margin-right:4px;"></span>暂无下注</span>
                </div>
                """,
                unsafe_allow_html=True
            )

            st.markdown("---")
            st.markdown("### 📋 转嫁明细")

            pass_display = risk_nums[["号码", "总下注金额", "中奖赔付额", "需要转嫁下注额", "转嫁后自留额", "转嫁后利润"]].copy()
            pass_display["总下注金额"] = pass_display["总下注金额"].apply(lambda x: f"¥{x:,.2f}")
            pass_display["中奖赔付额"] = pass_display["中奖赔付额"].apply(lambda x: f"¥{x:,.2f}")
            pass_display["需要转嫁下注额"] = pass_display["需要转嫁下注额"].apply(lambda x: f"¥{x:,.2f}")
            pass_display["转嫁后自留额"] = pass_display["转嫁后自留额"].apply(lambda x: f"¥{x:,.2f}")
            pass_display["转嫁后利润"] = pass_display["转嫁后利润"].apply(lambda x: f"¥{x:,.2f}")
            pass_display.index = range(1, len(pass_display) + 1)

            st.dataframe(pass_display, use_container_width=True)

            # 一键复制格式
            st.markdown("#### 📋 一键复制（号码=金额）")
            pass_lines = []
            for _, row in risk_nums.iterrows():
                pass_amt = int(row["需要转嫁下注额"])
                num_str = f"{int(row['号码数值']):02d}"
                pass_lines.append(f"{num_str}={pass_amt}米")
            
            if pass_lines:
                pass_text = "\n".join(pass_lines)
                st.code(pass_text, language=None)
                st.caption("💡 点击右上角复制按钮，直接发给下家")

            st.markdown("---")

            # 验证对账
            st.markdown("### ✅ 验证对账（号码部分）")

            num_self = num_bets_total - total_pass_on
            worst_payout = risk_nums["转嫁后赔付"].max() if len(risk_nums) > 0 else 0
            worst_profit = num_bets_total - worst_payout
            safe_nums = stats_df[(stats_df["下注人数"] > 0) & (~stats_df["号码数值"].isin(risk_nums["号码数值"].tolist()))]
            safe_max_payout = safe_nums["号码赔付额"].max() if len(safe_nums) > 0 else 0
            overall_worst_payout = max(worst_payout, safe_max_payout)
            overall_worst_profit = num_bets_total - overall_worst_payout

            v1, v2, v3, v4 = st.columns(4)
            v1.metric("💰 号码总下注", f"¥{num_bets_total:,.2f}")
            v2.metric("📤 转嫁出去", f"¥{total_pass_on:,.2f}")
            v3.metric("📥 号码自留", f"¥{num_self:,.2f}")
            v4.metric("💸 最坏号码赔付", f"¥{overall_worst_payout:,.2f}")

            v5, v6, v7 = st.columns(3)
            v5.metric("✅ 号码最坏利润", f"¥{overall_worst_profit:,.2f}",
                      delta=f"{overall_worst_profit/num_bets_total*100:.1f}%" if num_bets_total > 0 else "0%")
            v6.metric("🎯 目标利润", f"¥{target_profit:,.2f}")
            v7.metric("📊 差额验证",
                      "✅ 达标" if overall_worst_profit >= target_profit else "❌ 不达标",
                      delta=f"¥{overall_worst_profit - target_profit:,.2f}")

            if overall_worst_profit >= target_profit:
                st.success(f"""
                ✅ **号码部分验证通过！稳赚不亏**

                无论开出哪个号码，号码部分最少都能赚 ¥{overall_worst_profit:,.2f}（利润率 {overall_worst_profit/num_bets_total*100:.1f}%），
                超过目标利润 ¥{target_profit:,.2f}（{target_profit_rate}%）。
                """)
            else:
                st.error(f"""
                ❌ **号码部分验证不通过！**

                最坏情况利润 ¥{overall_worst_profit:,.2f} 低于目标利润 ¥{target_profit:,.2f}。
                请调高目标利润率或检查数据。
                """)

            # 特肖风险提示
            if sz_bets_total > 0:
                st.markdown("---")
                st.markdown("### 🐉 特肖风险（自担）")
                
                if sz_worst_profit >= 0:
                    st.info(f"""
                    特肖下注 ¥{sz_bets_total:,.2f}，最坏情况（中了最多的那个生肖）赔 ¥{sz_worst_payout:,.2f}，
                    特肖部分亏 ¥{abs(sz_worst_profit):,.2f}。
                    """)
                else:
                    st.warning(f"""
                    ⚠️ 特肖最坏情况亏损 ¥{abs(sz_worst_profit):,.2f}！
                    
                    - 特肖总下注：¥{sz_bets_total:,.2f}
                    - 最高赔付生肖：{sz_risk_list[0]["生肖"]}（赔 ¥{sz_worst_payout:,.2f}）
                    - 特肖最坏盈亏：{'赚' if sz_worst_profit >= 0 else '亏'} ¥{abs(sz_worst_profit):,.2f}
                    """)
                
                # 特肖明细表
                if sz_risk_list:
                    sz_df_display = pd.DataFrame(sz_risk_list)
                    sz_df_display["下注金额"] = sz_df_display["下注金额"].apply(lambda x: f"¥{x:,.2f}")
                    sz_df_display["中奖赔付"] = sz_df_display["中奖赔付"].apply(lambda x: f"¥{x:,.2f}")
                    sz_df_display["盈亏"] = sz_df_display["中奖赔付"].apply(
                        lambda x: f"🟢 +¥{sz_bets_total - x:,.2f}" if sz_bets_total - x >= 0 else f"🔴 -¥{x - sz_bets_total:,.2f}"
                    )
                    sz_df_display.index = range(1, len(sz_df_display) + 1)
                    st.dataframe(sz_df_display, use_container_width=True)

            st.markdown("---")

            # 操作建议
            st.markdown("### 💡 操作建议")
            sz_note = f"\n5. **特肖部分**：¥{sz_bets_total:,.2f} 下注，自担风险（最坏{'赚' if sz_worst_profit >= 0 else '亏'} ¥{abs(sz_worst_profit):,.2f}）" if sz_bets_total > 0 else ""
            st.success(f"""
            **收盘方案：**

            1. **号码总下注**：¥{num_bets_total:,.2f}
            2. **号码目标利润**：¥{target_profit:,.2f}（{target_profit_rate}%）
            3. **需要转嫁的号码**：共 {len(risk_nums)} 个
            4. **总共需转出去**：¥{total_pass_on:,.2f} 下注额{sz_note}

            把这 {len(risk_nums)} 个号码的超出部分转出去后，
            **号码部分无论开哪个号，您最少都能赚 ¥{target_profit:,.2f}**（{target_profit_rate}% 利润）。
            """)

        st.markdown("---")

        # 计算说明
        with st.expander("📐 计算说明"):
            st.markdown(f"""
            **号码部分公式：**
            - 保本赔付线 = 号码总下注 × (1 - 目标利润率) = ¥{num_bets_total:,.2f} × (1 - {target_profit_rate/100}) = ¥{break_even:,.2f}
            - 某号需转嫁下注额 = 该号下注额 - 保本赔付线 ÷ {payout_ratio}
            - 转嫁后利润 = 号码总下注 - 转嫁后赔付 = 最少 ¥{target_profit:,.2f}

            **原理：**
            把高风险号码的超额部分转嫁给其他老板接盘，
            剩下的自留部分即使中奖，赔付也不会超过保本线，
            这样无论开哪个号码，号码部分都能保证至少赚 {target_profit_rate}%。

            **特肖部分：**
            特肖下注 ¥{sz_bets_total:,.2f}，赔率 1:11，不参与转嫁，风险自担。
            """)

# ========== 开奖结算 ==========
with tab4:
    st.subheader("🎰 开奖结算")
    st.info("💡 输入开奖号码，自动计算本场盈亏")

    if total_bets == 0:
        st.info("暂无下注数据，无法结算。")
    else:
        col1, col2 = st.columns([1, 2])

        with col1:
            win_num = st.selectbox(
                "🏆 开奖号码（特码）",
                options=["请选择"] + [f"{i:02d}" for i in range(1, 50)]
            )

            st.markdown("---")
            st.metric("💰 下注总额", f"¥{total_bets:,.2f}")
            st.metric("🎯 赔付倍率", f"1 : {payout_ratio}")

        with col2:
            if win_num != "请选择":
                win = int(win_num)
                win_row = stats_df[stats_df["号码数值"] == win].iloc[0]
                win_amount = win_row["总下注金额"]
                win_num_payout = win_row["号码赔付额"]
                win_zodiac = win_row["生肖"]
                win_sz_payout = win_row["特肖赔付额"]
                win_total_payout = win_row["中奖赔付额"]
                profit = total_bets - win_total_payout
                profit_rate = profit / total_bets * 100 if total_bets > 0 else 0

                # 结果卡片
                if profit >= 0:
                    st.success(f"### ✅ 盈利 ¥{profit:,.2f}（利润率 {profit_rate:.1f}%）")
                else:
                    st.error(f"### ❌ 亏损 ¥{abs(profit):,.2f}（利润率 {profit_rate:.1f}%）")

                st.markdown("---")

                # 明细
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("🏆 开奖号码", f"{win:02d} 号")
                c2.metric("🐉 对应生肖", win_zodiac)
                c3.metric("💸 总赔付", f"¥{win_total_payout:,.2f}")
                c4.metric("📊 庄家盈亏", f"¥{profit:,.2f}",
                          delta=f"{profit_rate:.1f}%")

                st.markdown("---")

                # 计算明细
                st.markdown("#### 📐 计算明细")
                
                sz_bet_amount = 0
                for sz in sz_summary:
                    if sz["生肖"] == win_zodiac:
                        sz_bet_amount = sz["总下注"]
                        break
                
                detail_rows = [
                    ("总下注金额", f"¥{total_bets:,.2f}"),
                    ("开奖号码", f"{win:02d} 号（{win_zodiac}）"),
                ]
                
                if win_amount > 0:
                    detail_rows.append(("号码下注额", f"¥{win_amount:,.2f}"))
                    detail_rows.append(("号码赔付", f"¥{win_amount:,.2f} × {payout_ratio} = **¥{win_num_payout:,.2f}**"))
                
                if sz_bet_amount > 0:
                    detail_rows.append(("特肖下注额", f"{win_zodiac} ¥{sz_bet_amount:,.2f}"))
                    detail_rows.append(("特肖赔付", f"¥{sz_bet_amount:,.2f} × 11 = **¥{win_sz_payout:,.2f}**"))
                
                detail_rows.append(("**总赔付**", f"**¥{win_total_payout:,.2f}**"))
                detail_rows.append(("**庄家盈亏**", f"¥{total_bets:,.2f} - ¥{win_total_payout:,.2f} = **¥{profit:,.2f}**"))
                
                detail_md = "| 项目 | 金额 |\n|------|------|\n"
                for k, v in detail_rows:
                    detail_md += f"| {k} | {v} |\n"
                
                st.markdown(detail_md)

                st.markdown("---")

                # 按下注人分组计算盈亏
                st.markdown("#### 👥 各下注人盈亏明细")
                
                # 按下注人汇总
                bettor_result = defaultdict(lambda: {
                    "下注总额": 0,
                    "中奖号码下注": 0,  # 该号的普通号码下注
                    "中奖特肖下注": 0,  # 对应生肖的特肖下注
                    "中奖赔付": 0,
                    "盈亏": 0,
                    "笔数": 0
                })
                
                for bet in bets:
                    bettor = bet.get("下注人", "")
                    if not bettor or bettor == "批量导入":
                        bettor = "未署名"
                    
                    bet_type = bet.get("类型", "号码")
                    amt = bet["金额"]
                    
                    bettor_result[bettor]["下注总额"] += amt
                    bettor_result[bettor]["笔数"] += 1
                    
                    # 判断是否中奖
                    if bet_type == "号码" and bet["号码"] == win:
                        bettor_result[bettor]["中奖号码下注"] += amt
                        payout = amt * payout_ratio
                        bettor_result[bettor]["中奖赔付"] += payout
                        bettor_result[bettor]["盈亏"] -= payout  # 庄家赔出去的
                    elif bet_type == "特肖" and bet.get("生肖") == win_zodiac:
                        bettor_result[bettor]["中奖特肖下注"] += amt
                        payout = amt * 11  # 特肖1赔11
                        bettor_result[bettor]["中奖赔付"] += payout
                        bettor_result[bettor]["盈亏"] -= payout  # 庄家赔出去的
                
                # 盈亏 = 这个人的总下注 - 这个人的中奖赔付（庄家视角）
                # 也就是：赚了这个人的钱 - 赔给这个人的钱
                for bettor in bettor_result:
                    info = bettor_result[bettor]
                    info["盈亏"] = info["下注总额"] - info["中奖赔付"]
                
                # 排序：按金额从大到小
                sorted_bettors = sorted(bettor_result.items(), key=lambda x: -x[1]["下注总额"])
                
                bettor_rows = []
                for bettor, info in sorted_bettors:
                    win_detail = []
                    if info["中奖号码下注"] > 0:
                        win_detail.append(f"号码¥{info['中奖号码下注']:,.0f}")
                    if info["中奖特肖下注"] > 0:
                        win_detail.append(f"特肖¥{info['中奖特肖下注']:,.0f}")
                    win_desc = "、".join(win_detail) if win_detail else "未中"
                    
                    profit_val = info["盈亏"]
                    if profit_val >= 0:
                        profit_str = f"🟢 +¥{profit_val:,.2f}"
                    else:
                        profit_str = f"🔴 -¥{abs(profit_val):,.2f}"
                    
                    bettor_rows.append({
                        "下注人": bettor,
                        "下注笔数": info["笔数"],
                        "下注总额": f"¥{info['下注总额']:,.2f}",
                        "中奖情况": win_desc,
                        "中奖赔付": f"¥{info['中奖赔付']:,.2f}",
                        "庄家盈亏": profit_str
                    })
                
                if bettor_rows:
                    br_df = pd.DataFrame(bettor_rows)
                    br_df.index = range(1, len(br_df) + 1)
                    st.dataframe(br_df, use_container_width=True)
                    
                    # 简单说明
                    st.caption("💡 庄家盈亏 = 该下注人总下注 - 该下注人中奖赔付（正数=庄家赚，负数=庄家赔）")

                st.markdown("---")

                # 历史开奖记录
                if "history_draws" not in st.session_state:
                    st.session_state.history_draws = []

                if st.button("📝 记录到历史", use_container_width=True):
                    record = {
                        "期号": f"第{len(st.session_state.history_draws) + 1:03d}期",
                        "开奖号码": f"{win:02d}",
                        "下注总额": total_bets,
                        "赔付金额": win_payout,
                        "盈亏": profit,
                        "利润率": f"{profit_rate:.1f}%",
                        "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    st.session_state.history_draws.insert(0, record)
                    st.success("✅ 已记录到历史！")

                # 历史记录
                if st.session_state.history_draws:
                    st.markdown("---")
                    st.markdown("#### 📜 历史开奖记录")

                    # 累计盈亏
                    total_profit = sum(r["盈亏"] for r in st.session_state.history_draws)
                    total_in = sum(r["下注总额"] for r in st.session_state.history_draws)
                    avg_rate = (total_profit / total_in * 100) if total_in > 0 else 0

                    h1, h2, h3 = st.columns(3)
                    h1.metric("📊 累计盈亏", f"¥{total_profit:,.2f}",
                              delta=f"{avg_rate:.1f}%")
                    h2.metric("🎲 开奖期数", f"{len(st.session_state.history_draws)} 期")
                    h3.metric("💵 累计流水", f"¥{total_in:,.2f}")

                    hist_df = pd.DataFrame(st.session_state.history_draws)
                    hist_df.index = range(1, len(hist_df) + 1)
                    st.dataframe(hist_df, use_container_width=True, height=300)

                    if st.button("🗑️ 清空历史记录"):
                        st.session_state.history_draws = []
                        st.rerun()
            else:
                st.info("👆 请选择开奖号码查看结算结果")

# ========== 下注明细 ==========
with tab5:
    st.subheader("📋 下注明细记录")

    if len(bets) == 0:
        st.info("暂无下注记录。")
    else:
        # 搜索/筛选
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            filter_type = st.selectbox("按类型筛选", ["全部", "号码", "特肖"])
        with col2:
            filter_num = st.selectbox("按号码筛选", ["全部"] + [f"{i:02d}" for i in range(1, 50)])
        with col3:
            filter_bettor = st.text_input("按下注人搜索")
        with col4:
            # 收集所有操作员
            all_operators = list(set(b.get("操作员", "") for b in bets if b.get("操作员")))
            all_operators.sort()
            filter_operator = st.selectbox("按操作员筛选", ["全部"] + all_operators)
        with col5:
            sort_by = st.selectbox("排序方式", ["时间倒序", "时间正序", "金额从大到小", "金额从小到大"])

        # 筛选
        display_bets = bets.copy()
        if filter_type != "全部":
            display_bets = [b for b in display_bets if b.get("类型", "号码") == filter_type]
        if filter_num != "全部":
            display_bets = [b for b in display_bets if b.get("类型", "号码") == "号码" and f"{b['号码']:02d}" == filter_num]
        if filter_bettor:
            display_bets = [b for b in display_bets if filter_bettor in b.get("下注人", "")]
        if filter_operator != "全部":
            display_bets = [b for b in display_bets if b.get("操作员", "") == filter_operator]

        # 排序
        if sort_by == "时间倒序":
            display_bets.sort(key=lambda x: x["时间"], reverse=True)
        elif sort_by == "时间正序":
            display_bets.sort(key=lambda x: x["时间"])
        elif sort_by == "金额从大到小":
            display_bets.sort(key=lambda x: x["金额"], reverse=True)
        elif sort_by == "金额从小到大":
            display_bets.sort(key=lambda x: x["金额"])

        # 显示
        bet_df = pd.DataFrame(display_bets)
        if len(bet_df) > 0:
            bet_df["号码"] = bet_df.apply(lambda row: f"{row['号码']:02d}" if row.get("类型", "号码") == "号码" else "-", axis=1)
            bet_df["金额"] = bet_df["金额"].apply(lambda x: f"¥{x:,.2f}")
            if "类型" not in bet_df.columns:
                bet_df["类型"] = "号码"
            if "生肖" not in bet_df.columns:
                bet_df["生肖"] = ""
            if "原始文本" not in bet_df.columns:
                bet_df["原始文本"] = ""
            if "操作员" not in bet_df.columns:
                bet_df["操作员"] = "-"
            bet_df = bet_df[["id", "类型", "号码", "生肖", "金额", "下注人", "原始文本", "操作员", "备注", "时间"]]
            bet_df.columns = ["序号", "类型", "号码", "生肖", "金额", "下注人", "原始文本", "操作员", "备注", "下注时间"]
            bet_df.index = range(1, len(bet_df) + 1)
            st.dataframe(bet_df, use_container_width=True, height=500)

            st.info(f"共 {len(display_bets)} 条记录")

            # 下注人统计（按署名分组）
            st.markdown("#### 👥 下注人统计（按署名）")
            bettor_stats_dict = defaultdict(lambda: {"笔数": 0, "金额": 0})
            for b in display_bets:
                bettor = b.get("下注人", "")
                if not bettor or bettor == "批量导入":
                    bettor = "未署名"
                bettor_stats_dict[bettor]["笔数"] += 1
                bettor_stats_dict[bettor]["金额"] += b["金额"]
            
            bettor_stats = []
            for bettor, info in sorted(bettor_stats_dict.items(), key=lambda x: -x[1]["金额"]):
                bettor_stats.append({
                    "下注人": bettor,
                    "下注笔数": info["笔数"],
                    "下注金额": f"¥{info['金额']:,.2f}"
                })
            
            if bettor_stats:
                bettor_df = pd.DataFrame(bettor_stats)
                bettor_df.index = range(1, len(bettor_df) + 1)
                st.dataframe(bettor_df, use_container_width=True)

            # 操作员统计
            if all_operators:
                st.markdown("#### 👤 操作员统计")
                op_stats = []
                for op in all_operators:
                    op_bets = [b for b in bets if b.get("操作员") == op]
                    op_amount = sum(b["金额"] for b in op_bets)
                    op_stats.append({"操作员": op, "录单条数": len(op_bets), "录单金额": f"¥{op_amount:,.2f}"})
                op_df = pd.DataFrame(op_stats)
                op_df.index = range(1, len(op_df) + 1)
                st.dataframe(op_df, use_container_width=True)

            # 删除功能
            st.markdown("---")
            st.subheader("🗑️ 删除记录")
            del_id = st.number_input("输入要删除的序号", min_value=1, max_value=len(bets), value=1)
            if st.button("删除该条记录"):
                # 找到对应 id 的下注
                bets[:] = [b for b in bets if b["id"] != del_id]
                data["bets"] = bets
                save_bets(data)
                st.success(f"已删除序号 {del_id} 的记录")
                st.rerun()

# ========== 账号管理（仅管理员） ==========
if current_role == "admin":
    with tab6:
        st.subheader("👥 账号管理")
        st.info("💡 管理员可以添加、修改、删除操作员账号")

        # 用户列表
        st.markdown("### 📋 用户列表")
        user_list = []
        for uname, uinfo in users.items():
            user_list.append({
                "用户名": uname,
                "角色": "管理员" if uinfo.get("role") == "admin" else "操作员",
                "创建时间": uinfo.get("created_at", "-")
            })
        user_df = pd.DataFrame(user_list)
        user_df.index = range(1, len(user_df) + 1)
        st.dataframe(user_df, use_container_width=True)

        st.markdown("---")

        # 添加用户
        st.markdown("### ➕ 添加账号")
        with st.form("add_user_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                new_username = st.text_input("用户名")
            with col2:
                new_password = st.text_input("密码", type="password")
            with col3:
                new_role = st.selectbox("角色", ["操作员", "管理员"])

            add_submit = st.form_submit_button("✅ 添加账号", type="primary")

            if add_submit:
                if not new_username.strip() or not new_password.strip():
                    st.error("用户名和密码不能为空")
                elif new_username.strip() in users:
                    st.error("用户名已存在")
                else:
                    role_val = "admin" if new_role == "管理员" else "operator"
                    users[new_username.strip()] = {
                        "password": new_password.strip(),
                        "role": role_val,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_users(users)
                    st.success(f"✅ 已添加账号：{new_username.strip()}")
                    st.rerun()

        st.markdown("---")

        # 修改用户名
        st.markdown("### ✏️ 修改用户名")
        with st.form("rename_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                rename_user_old = st.selectbox("选择用户", list(users.keys()))
            with col2:
                rename_user_new = st.text_input("新用户名")

            rename_submit = st.form_submit_button("✅ 修改用户名")

            if rename_submit:
                old = rename_user_old.strip()
                new = rename_user_new.strip()
                if not new:
                    st.error("新用户名不能为空")
                elif old not in users:
                    st.error("用户不存在")
                elif new in users:
                    st.error("新用户名已存在")
                else:
                    users[new] = users.pop(old)
                    save_users(users)
                    # 如果改的是当前登录用户，更新 session
                    if current_user == old:
                        st.session_state.username = new
                    st.success(f"✅ 已将 {old} 改名为 {new}")
                    st.rerun()

        st.markdown("---")

        # 修改密码
        st.markdown("### 🔑 修改密码")
        with st.form("change_pwd_form"):
            col1, col2 = st.columns(2)
            with col1:
                pwd_user = st.selectbox("选择用户", list(users.keys()))
            with col2:
                new_pwd = st.text_input("新密码", type="password")

            pwd_submit = st.form_submit_button("✅ 修改密码")

            if pwd_submit:
                if not new_pwd.strip():
                    st.error("密码不能为空")
                else:
                    users[pwd_user]["password"] = new_pwd.strip()
                    save_users(users)
                    st.success(f"✅ 已修改 {pwd_user} 的密码")
                    st.rerun()

        st.markdown("---")

        # 删除用户
        st.markdown("### 🗑️ 删除账号")
        with st.form("del_user_form"):
            del_user = st.selectbox("选择要删除的用户", [u for u in users.keys() if u != current_user])
            del_submit = st.form_submit_button("🗑️ 删除该账号")

            if del_submit:
                if del_user == current_user:
                    st.error("不能删除当前登录账号")
                elif del_user not in users:
                    st.error("用户不存在")
                else:
                    del users[del_user]
                    save_users(users)
                    st.success(f"✅ 已删除账号：{del_user}")
                    st.rerun()

        st.markdown("---")
        st.warning("⚠️ 注意：删除账号不会影响已录入的下注记录。")

# ==================== 页脚 ====================
st.markdown("---")
st.caption("💰 六合彩庄家下注统计系统 | 仅供参考，理性操作")
