from domomagic import *
import pandas as pd
import numpy as np
import random
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import uuid

# Set random seed for reproducibility
random.seed(42)
np.random.seed(42)

# Current date for forecast determination - yesterday is the last actual date
CURRENT_DATE = date.today() - relativedelta(days=1)

# Define base 25 lifestyle brand store locations across Japan
LOCATIONS = [
    {"id": "JPN001", "name": "シンプルスタイル 銀座", "prefecture": "東京都", "city": "中央区", "postal_code": "104-0061", "region": "関東", "area_code": "13104"},
    {"id": "JPN002", "name": "シンプルスタイル 新宿", "prefecture": "東京都", "city": "新宿区", "postal_code": "160-0022", "region": "関東", "area_code": "13104"},
    {"id": "JPN003", "name": "シンプルスタイル 渋谷", "prefecture": "東京都", "city": "渋谷区", "postal_code": "150-0002", "region": "関東", "area_code": "13104"},
    {"id": "JPN004", "name": "シンプルスタイル 六本木", "prefecture": "東京都", "city": "港区", "postal_code": "106-0032", "region": "関東", "area_code": "13104"},
    {"id": "JPN005", "name": "シンプルスタイル 表参道", "prefecture": "東京都", "city": "港区", "postal_code": "107-0062", "region": "関東", "area_code": "13104"},
    {"id": "JPN006", "name": "シンプルスタイル 横浜", "prefecture": "神奈川県", "city": "横浜市", "postal_code": "220-0012", "region": "関東", "area_code": "14104"},
    {"id": "JPN007", "name": "シンプルスタイル 大阪梅田", "prefecture": "大阪府", "city": "大阪市", "postal_code": "530-0001", "region": "関西", "area_code": "27128"},
    {"id": "JPN008", "name": "シンプルスタイル 心斎橋", "prefecture": "大阪府", "city": "大阪市", "postal_code": "542-0081", "region": "関西", "area_code": "27128"},
    {"id": "JPN009", "name": "シンプルスタイル 京都", "prefecture": "京都府", "city": "京都市", "postal_code": "604-8005", "region": "関西", "area_code": "26108"},
    {"id": "JPN010", "name": "シンプルスタイル 神戸", "prefecture": "兵庫県", "city": "神戸市", "postal_code": "650-0034", "region": "関西", "area_code": "28110"},
    {"id": "JPN011", "name": "シンプルスタイル 名古屋", "prefecture": "愛知県", "city": "名古屋市", "postal_code": "460-0008", "region": "中部", "area_code": "23106"},
    {"id": "JPN012", "name": "シンプルスタイル 福岡", "prefecture": "福岡県", "city": "福岡市", "postal_code": "810-0001", "region": "九州", "area_code": "40133"},
    {"id": "JPN013", "name": "シンプルスタイル 札幌", "prefecture": "北海道", "city": "札幌市", "postal_code": "060-0002", "region": "北海道", "area_code": "01101"},
    {"id": "JPN014", "name": "シンプルスタイル 仙台", "prefecture": "宮城県", "city": "仙台市", "postal_code": "980-0021", "region": "東北", "area_code": "04101"},
    {"id": "JPN015", "name": "シンプルスタイル 広島", "prefecture": "広島県", "city": "広島市", "postal_code": "730-0017", "region": "中国", "area_code": "34101"},
    {"id": "JPN016", "name": "シンプルスタイル 千葉", "prefecture": "千葉県", "city": "千葉市", "postal_code": "260-0028", "region": "関東", "area_code": "12101"},
    {"id": "JPN017", "name": "シンプルスタイル さいたま", "prefecture": "埼玉県", "city": "さいたま市", "postal_code": "330-0846", "region": "関東", "area_code": "11101"},
    {"id": "JPN018", "name": "シンプルスタイル 静岡", "prefecture": "静岡県", "city": "静岡市", "postal_code": "420-0852", "region": "中部", "area_code": "22101"},
    {"id": "JPN019", "name": "シンプルスタイル 金沢", "prefecture": "石川県", "city": "金沢市", "postal_code": "920-0962", "region": "中部", "area_code": "17201"},
    {"id": "JPN020", "name": "シンプルスタイル 岡山", "prefecture": "岡山県", "city": "岡山市", "postal_code": "700-0826", "region": "中国", "area_code": "33101"},
    {"id": "JPN021", "name": "シンプルスタイル 高松", "prefecture": "香川県", "city": "高松市", "postal_code": "760-0029", "region": "四国", "area_code": "37201"},
    {"id": "JPN022", "name": "シンプルスタイル 熊本", "prefecture": "熊本県", "city": "熊本市", "postal_code": "860-0845", "region": "九州", "area_code": "43101"},
    {"id": "JPN023", "name": "シンプルスタイル 那覇", "prefecture": "沖縄県", "city": "那覇市", "postal_code": "900-0013", "region": "沖縄", "area_code": "47201"},
    {"id": "JPN024", "name": "シンプルスタイル 新潟", "prefecture": "新潟県", "city": "新潟市", "postal_code": "950-0916", "region": "中部", "area_code": "15101"},
    {"id": "JPN025", "name": "シンプルスタイル 川崎", "prefecture": "神奈川県", "city": "川崎市", "postal_code": "210-0024", "region": "関東", "area_code": "14130"}
]

# Expand to 100 stores using real regional district names (no serial-number
# clones). Distribution is intentionally Kanto-heavy, mirroring real Japanese
# lifestyle-brand chains.
EXTRA_LOCATIONS = [
    # --- 関東 (28) ---
    {"name": "シンプルスタイル 吉祥寺", "prefecture": "東京都", "city": "武蔵野市", "postal_code": "180-0004", "region": "関東", "area_code": "13203"},
    {"name": "シンプルスタイル 自由が丘", "prefecture": "東京都", "city": "目黒区", "postal_code": "152-0035", "region": "関東", "area_code": "13110"},
    {"name": "シンプルスタイル 二子玉川", "prefecture": "東京都", "city": "世田谷区", "postal_code": "158-0094", "region": "関東", "area_code": "13112"},
    {"name": "シンプルスタイル 下北沢", "prefecture": "東京都", "city": "世田谷区", "postal_code": "155-0031", "region": "関東", "area_code": "13112"},
    {"name": "シンプルスタイル 中野", "prefecture": "東京都", "city": "中野区", "postal_code": "164-0001", "region": "関東", "area_code": "13114"},
    {"name": "シンプルスタイル 錦糸町", "prefecture": "東京都", "city": "墨田区", "postal_code": "130-0022", "region": "関東", "area_code": "13107"},
    {"name": "シンプルスタイル 北千住", "prefecture": "東京都", "city": "足立区", "postal_code": "120-0034", "region": "関東", "area_code": "13121"},
    {"name": "シンプルスタイル 蒲田", "prefecture": "東京都", "city": "大田区", "postal_code": "144-0051", "region": "関東", "area_code": "13111"},
    {"name": "シンプルスタイル 立川", "prefecture": "東京都", "city": "立川市", "postal_code": "190-0012", "region": "関東", "area_code": "13202"},
    {"name": "シンプルスタイル 町田", "prefecture": "東京都", "city": "町田市", "postal_code": "194-0013", "region": "関東", "area_code": "13209"},
    {"name": "シンプルスタイル 大宮", "prefecture": "埼玉県", "city": "さいたま市", "postal_code": "330-0846", "region": "関東", "area_code": "11101"},
    {"name": "シンプルスタイル 川口", "prefecture": "埼玉県", "city": "川口市", "postal_code": "332-0017", "region": "関東", "area_code": "11203"},
    {"name": "シンプルスタイル 越谷", "prefecture": "埼玉県", "city": "越谷市", "postal_code": "343-0845", "region": "関東", "area_code": "11222"},
    {"name": "シンプルスタイル 所沢", "prefecture": "埼玉県", "city": "所沢市", "postal_code": "359-1123", "region": "関東", "area_code": "11208"},
    {"name": "シンプルスタイル 船橋", "prefecture": "千葉県", "city": "船橋市", "postal_code": "273-0005", "region": "関東", "area_code": "12204"},
    {"name": "シンプルスタイル 柏", "prefecture": "千葉県", "city": "柏市", "postal_code": "277-0005", "region": "関東", "area_code": "12217"},
    {"name": "シンプルスタイル 松戸", "prefecture": "千葉県", "city": "松戸市", "postal_code": "271-0092", "region": "関東", "area_code": "12207"},
    {"name": "シンプルスタイル 海浜幕張", "prefecture": "千葉県", "city": "千葉市", "postal_code": "261-0021", "region": "関東", "area_code": "12101"},
    {"name": "シンプルスタイル 藤沢", "prefecture": "神奈川県", "city": "藤沢市", "postal_code": "251-0055", "region": "関東", "area_code": "14205"},
    {"name": "シンプルスタイル たまプラーザ", "prefecture": "神奈川県", "city": "横浜市", "postal_code": "225-0002", "region": "関東", "area_code": "14104"},
    {"name": "シンプルスタイル 上大岡", "prefecture": "神奈川県", "city": "横浜市", "postal_code": "233-0002", "region": "関東", "area_code": "14104"},
    {"name": "シンプルスタイル 本厚木", "prefecture": "神奈川県", "city": "厚木市", "postal_code": "243-0018", "region": "関東", "area_code": "14212"},
    {"name": "シンプルスタイル 高崎", "prefecture": "群馬県", "city": "高崎市", "postal_code": "370-0849", "region": "関東", "area_code": "10202"},
    {"name": "シンプルスタイル 前橋", "prefecture": "群馬県", "city": "前橋市", "postal_code": "371-0023", "region": "関東", "area_code": "10201"},
    {"name": "シンプルスタイル 宇都宮", "prefecture": "栃木県", "city": "宇都宮市", "postal_code": "320-0811", "region": "関東", "area_code": "09201"},
    {"name": "シンプルスタイル 水戸", "prefecture": "茨城県", "city": "水戸市", "postal_code": "310-0021", "region": "関東", "area_code": "08201"},
    {"name": "シンプルスタイル つくば", "prefecture": "茨城県", "city": "つくば市", "postal_code": "305-0031", "region": "関東", "area_code": "08220"},
    {"name": "シンプルスタイル 春日部", "prefecture": "埼玉県", "city": "春日部市", "postal_code": "344-0067", "region": "関東", "area_code": "11214"},
    # --- 関西 (15) ---
    {"name": "シンプルスタイル なんば", "prefecture": "大阪府", "city": "大阪市", "postal_code": "542-0076", "region": "関西", "area_code": "27128"},
    {"name": "シンプルスタイル 天王寺", "prefecture": "大阪府", "city": "大阪市", "postal_code": "543-0055", "region": "関西", "area_code": "27128"},
    {"name": "シンプルスタイル 京橋", "prefecture": "大阪府", "city": "大阪市", "postal_code": "534-0024", "region": "関西", "area_code": "27128"},
    {"name": "シンプルスタイル 堺", "prefecture": "大阪府", "city": "堺市", "postal_code": "590-0028", "region": "関西", "area_code": "27141"},
    {"name": "シンプルスタイル 江坂", "prefecture": "大阪府", "city": "吹田市", "postal_code": "564-0063", "region": "関西", "area_code": "27205"},
    {"name": "シンプルスタイル 千里中央", "prefecture": "大阪府", "city": "豊中市", "postal_code": "560-0082", "region": "関西", "area_code": "27203"},
    {"name": "シンプルスタイル 高槻", "prefecture": "大阪府", "city": "高槻市", "postal_code": "569-0071", "region": "関西", "area_code": "27207"},
    {"name": "シンプルスタイル 枚方", "prefecture": "大阪府", "city": "枚方市", "postal_code": "573-0032", "region": "関西", "area_code": "27210"},
    {"name": "シンプルスタイル 西宮", "prefecture": "兵庫県", "city": "西宮市", "postal_code": "663-8035", "region": "関西", "area_code": "28204"},
    {"name": "シンプルスタイル 尼崎", "prefecture": "兵庫県", "city": "尼崎市", "postal_code": "661-0976", "region": "関西", "area_code": "28202"},
    {"name": "シンプルスタイル 姫路", "prefecture": "兵庫県", "city": "姫路市", "postal_code": "670-0927", "region": "関西", "area_code": "28201"},
    {"name": "シンプルスタイル 明石", "prefecture": "兵庫県", "city": "明石市", "postal_code": "673-0891", "region": "関西", "area_code": "28203"},
    {"name": "シンプルスタイル 奈良", "prefecture": "奈良県", "city": "奈良市", "postal_code": "630-8215", "region": "関西", "area_code": "29201"},
    {"name": "シンプルスタイル 和歌山", "prefecture": "和歌山県", "city": "和歌山市", "postal_code": "640-8331", "region": "関西", "area_code": "30201"},
    {"name": "シンプルスタイル 大津", "prefecture": "滋賀県", "city": "大津市", "postal_code": "520-0051", "region": "関西", "area_code": "25201"},
    # --- 中部 (12) ---
    {"name": "シンプルスタイル 栄", "prefecture": "愛知県", "city": "名古屋市", "postal_code": "460-0008", "region": "中部", "area_code": "23106"},
    {"name": "シンプルスタイル 名駅", "prefecture": "愛知県", "city": "名古屋市", "postal_code": "450-0002", "region": "中部", "area_code": "23104"},
    {"name": "シンプルスタイル 藤が丘", "prefecture": "愛知県", "city": "名古屋市", "postal_code": "465-0032", "region": "中部", "area_code": "23113"},
    {"name": "シンプルスタイル 岡崎", "prefecture": "愛知県", "city": "岡崎市", "postal_code": "444-0813", "region": "中部", "area_code": "23202"},
    {"name": "シンプルスタイル 豊田", "prefecture": "愛知県", "city": "豊田市", "postal_code": "471-0025", "region": "中部", "area_code": "23211"},
    {"name": "シンプルスタイル 一宮", "prefecture": "愛知県", "city": "一宮市", "postal_code": "491-0858", "region": "中部", "area_code": "23203"},
    {"name": "シンプルスタイル 岐阜", "prefecture": "岐阜県", "city": "岐阜市", "postal_code": "500-8833", "region": "中部", "area_code": "21201"},
    {"name": "シンプルスタイル 浜松", "prefecture": "静岡県", "city": "浜松市", "postal_code": "430-0927", "region": "中部", "area_code": "22131"},
    {"name": "シンプルスタイル 沼津", "prefecture": "静岡県", "city": "沼津市", "postal_code": "410-0801", "region": "中部", "area_code": "22203"},
    {"name": "シンプルスタイル 富山", "prefecture": "富山県", "city": "富山市", "postal_code": "930-0002", "region": "中部", "area_code": "16201"},
    {"name": "シンプルスタイル 福井", "prefecture": "福井県", "city": "福井市", "postal_code": "910-0006", "region": "中部", "area_code": "18201"},
    {"name": "シンプルスタイル 松本", "prefecture": "長野県", "city": "松本市", "postal_code": "390-0811", "region": "中部", "area_code": "20202"},
    # --- 九州 (9) ---
    {"name": "シンプルスタイル 天神", "prefecture": "福岡県", "city": "福岡市", "postal_code": "810-0001", "region": "九州", "area_code": "40133"},
    {"name": "シンプルスタイル 博多", "prefecture": "福岡県", "city": "福岡市", "postal_code": "812-0011", "region": "九州", "area_code": "40132"},
    {"name": "シンプルスタイル 小倉", "prefecture": "福岡県", "city": "北九州市", "postal_code": "802-0002", "region": "九州", "area_code": "40106"},
    {"name": "シンプルスタイル 久留米", "prefecture": "福岡県", "city": "久留米市", "postal_code": "830-0032", "region": "九州", "area_code": "40203"},
    {"name": "シンプルスタイル 大分", "prefecture": "大分県", "city": "大分市", "postal_code": "870-0021", "region": "九州", "area_code": "44201"},
    {"name": "シンプルスタイル 宮崎", "prefecture": "宮崎県", "city": "宮崎市", "postal_code": "880-0805", "region": "九州", "area_code": "45201"},
    {"name": "シンプルスタイル 鹿児島", "prefecture": "鹿児島県", "city": "鹿児島市", "postal_code": "892-0842", "region": "九州", "area_code": "46201"},
    {"name": "シンプルスタイル 長崎", "prefecture": "長崎県", "city": "長崎市", "postal_code": "850-0841", "region": "九州", "area_code": "42201"},
    {"name": "シンプルスタイル 佐賀", "prefecture": "佐賀県", "city": "佐賀市", "postal_code": "840-0801", "region": "九州", "area_code": "41201"},
    # --- 北海道 (4) ---
    {"name": "シンプルスタイル 旭川", "prefecture": "北海道", "city": "旭川市", "postal_code": "070-0030", "region": "北海道", "area_code": "01204"},
    {"name": "シンプルスタイル 函館", "prefecture": "北海道", "city": "函館市", "postal_code": "040-0011", "region": "北海道", "area_code": "01202"},
    {"name": "シンプルスタイル 帯広", "prefecture": "北海道", "city": "帯広市", "postal_code": "080-0012", "region": "北海道", "area_code": "01207"},
    {"name": "シンプルスタイル 釧路", "prefecture": "北海道", "city": "釧路市", "postal_code": "085-0015", "region": "北海道", "area_code": "01206"},
    # --- 東北 (5) ---
    {"name": "シンプルスタイル 盛岡", "prefecture": "岩手県", "city": "盛岡市", "postal_code": "020-0022", "region": "東北", "area_code": "03201"},
    {"name": "シンプルスタイル 秋田", "prefecture": "秋田県", "city": "秋田市", "postal_code": "010-0001", "region": "東北", "area_code": "05201"},
    {"name": "シンプルスタイル 山形", "prefecture": "山形県", "city": "山形市", "postal_code": "990-0039", "region": "東北", "area_code": "06201"},
    {"name": "シンプルスタイル 郡山", "prefecture": "福島県", "city": "郡山市", "postal_code": "963-8004", "region": "東北", "area_code": "07203"},
    {"name": "シンプルスタイル 青森", "prefecture": "青森県", "city": "青森市", "postal_code": "030-0801", "region": "東北", "area_code": "02201"},
    # --- 中国 (2) ---
    {"name": "シンプルスタイル 倉敷", "prefecture": "岡山県", "city": "倉敷市", "postal_code": "710-0055", "region": "中国", "area_code": "33202"},
    {"name": "シンプルスタイル 福山", "prefecture": "広島県", "city": "福山市", "postal_code": "720-0067", "region": "中国", "area_code": "34207"},
]

LOCATIONS = (LOCATIONS + EXTRA_LOCATIONS)[:100]
# Reassign clean sequential IDs while keeping each store's real landmark name.
for idx, location in enumerate(LOCATIONS, start=1):
    location["id"] = f"JPN{idx:03d}"

# --- Performance archetypes ---------------------------------------------------
# Give stores distinct business trajectories so the demo tells a clear
# winners / losers / turnaround story instead of a flat cluster of stores.
#   rev   : baseline revenue multiplier
#   cost  : baseline non-COGS expense multiplier (COGS tracks revenue)
#   trend : 24-month linear drift (+ grows over time, - decays over time)
ARCHETYPE_SPECS = {
    "star":       {"rev": 1.30, "cost": 0.94, "trend":  0.26},  # 好調・伸長
    "stable":     {"rev": 1.04, "cost": 1.00, "trend":  0.03},  # 安定
    "struggling": {"rev": 0.80, "cost": 1.06, "trend": -0.05},  # 苦戦（高コスト低売上）
    "recovering": {"rev": 0.90, "cost": 1.02, "trend":  0.30},  # 回復基調
    "declining":  {"rev": 0.98, "cost": 1.05, "trend": -0.26},  # 下降トレンド
}
ARCHETYPE_WEIGHTS = [("star", 16), ("stable", 46), ("struggling", 16), ("recovering", 12), ("declining", 10)]

_archetype_pool = []
for _name, _count in ARCHETYPE_WEIGHTS:
    _archetype_pool.extend([_name] * _count)
# Deterministic shuffle keeps the demo reproducible run-to-run.
random.Random(2024).shuffle(_archetype_pool)

STORE_PROFILES = {}
for idx, location in enumerate(LOCATIONS):
    archetype = _archetype_pool[idx]
    spec = ARCHETYPE_SPECS[archetype]
    rng = random.Random(1000 + idx)  # deterministic per-store idiosyncrasy
    rev_idio = 1.0 + (rng.random() - 0.5) * 0.16   # +/-8%
    cost_idio = 1.0 + (rng.random() - 0.5) * 0.10  # +/-5%
    STORE_PROFILES[location["id"]] = {
        "archetype": archetype,
        "rev_mult": spec["rev"] * rev_idio,
        "cost_mult": spec["cost"] * cost_idio,
        "trend": spec["trend"],
    }


def archetype_factor(location_id, month, year):
    """Return (revenue_multiplier, cost_multiplier) for a store in a given month,
    blending its archetype baseline with a 24-month linear trend."""
    profile = STORE_PROFILES.get(location_id)
    if not profile:
        return 1.0, 1.0
    month_index = (year - 2024) * 12 + (month - 1)  # 0..23 across 2024-01..2025-12
    trend_factor = 1.0 + profile["trend"] * ((month_index / 23.0) - 0.5)
    return profile["rev_mult"] * trend_factor, profile["cost_mult"]


def seasonal_cost_factor(gl_account_id, month):
    """Personnel (5010/5020/5030) and marketing (5810/5820) costs flex with the
    retail calendar - up in peak selling months, down in the quiet ones."""
    if gl_account_id in ("5010", "5020", "5030", "5810", "5820"):
        seasonal = {3: 1.06, 5: 1.03, 7: 1.07, 12: 1.08, 2: 0.97, 8: 0.97}
        return seasonal.get(month, 1.0)
    return 1.0

# Define Chart of Accounts for a Japanese lifestyle brand - Multi-level detail
GL_ACCOUNTS = {
    # Revenue Accounts
    "4000": {"name": "衣料品売上", "name_en": "Apparel Sales", "type": "Revenue", "subtype": "Apparel", "department": "衣料品事業部", "dept_code": "APPA", "parent": None, "level": 1},
    "4010": {"name": "婦人服", "name_en": "Women's Wear", "type": "Revenue", "subtype": "Apparel", "department": "衣料品事業部", "dept_code": "APPA", "parent": "4000", "level": 2},
    "4020": {"name": "紳士服", "name_en": "Men's Wear", "type": "Revenue", "subtype": "Apparel", "department": "衣料品事業部", "dept_code": "APPA", "parent": "4000", "level": 2},
    "4030": {"name": "子供服・マタニティ", "name_en": "Kids & Maternity", "type": "Revenue", "subtype": "Apparel", "department": "衣料品事業部", "dept_code": "APPA", "parent": "4000", "level": 2},
    "4040": {"name": "インナー・靴下", "name_en": "Innerwear & Socks", "type": "Revenue", "subtype": "Apparel", "department": "衣料品事業部", "dept_code": "APPA", "parent": "4000", "level": 2},

    "4100": {"name": "生活雑貨売上", "name_en": "Household Goods Sales", "type": "Revenue", "subtype": "Household", "department": "生活雑貨事業部", "dept_code": "LIFE", "parent": None, "level": 1},
    "4110": {"name": "家具", "name_en": "Furniture", "type": "Revenue", "subtype": "Household", "department": "生活雑貨事業部", "dept_code": "LIFE", "parent": "4100", "level": 2},
    "4120": {"name": "寝具・ファブリック", "name_en": "Bedding & Fabrics", "type": "Revenue", "subtype": "Household", "department": "生活雑貨事業部", "dept_code": "LIFE", "parent": "4100", "level": 2},
    "4130": {"name": "キッチン・テーブル用品", "name_en": "Kitchen & Tableware", "type": "Revenue", "subtype": "Household", "department": "生活雑貨事業部", "dept_code": "LIFE", "parent": "4100", "level": 2},
    "4140": {"name": "文房具・オフィス用品", "name_en": "Stationery & Office", "type": "Revenue", "subtype": "Household", "department": "生活雑貨事業部", "dept_code": "LIFE", "parent": "4100", "level": 2},
    "4150": {"name": "ヘルス＆ビューティー", "name_en": "Health & Beauty", "type": "Revenue", "subtype": "Household", "department": "生活雑貨事業部", "dept_code": "LIFE", "parent": "4100", "level": 2},

    "4200": {"name": "食品売上", "name_en": "Food Sales", "type": "Revenue", "subtype": "Food", "department": "食品事業部", "dept_code": "FOOD", "parent": None, "level": 1},
    "4210": {"name": "レトルト・冷凍食品", "name_en": "Packaged & Frozen Food", "type": "Revenue", "subtype": "Food", "department": "食品事業部", "dept_code": "FOOD", "parent": "4200", "level": 2},
    "4220": {"name": "菓子・スナック", "name_en": "Sweets & Snacks", "type": "Revenue", "subtype": "Food", "department": "食品事業部", "dept_code": "FOOD", "parent": "4200", "level": 2},
    "4230": {"name": "飲料・調味料", "name_en": "Beverages & Seasoning", "type": "Revenue", "subtype": "Food", "department": "食品事業部", "dept_code": "FOOD", "parent": "4200", "level": 2},

    "4600": {"name": "その他事業収益", "name_en": "Other Business Revenue", "type": "Revenue", "subtype": "Other", "department": "新規事業部", "dept_code": "NEW", "parent": None, "level": 1},
    "4610": {"name": "カフェ・レストラン", "name_en": "Cafe & Restaurant", "type": "Revenue", "subtype": "Other", "department": "新規事業部", "dept_code": "NEW", "parent": "4600", "level": 2},
    "4620": {"name": "イベント・ワークショップ", "name_en": "Events & Workshops", "type": "Revenue", "subtype": "Other", "department": "新規事業部", "dept_code": "NEW", "parent": "4600", "level": 2},

    # Operating Expenses
    "5000": {"name": "人件費", "name_en": "Personnel Expenses", "type": "Expense", "subtype": "Labor", "department": "管理部門", "dept_code": "ADM", "parent": None, "level": 1},
    "5010": {"name": "正社員給与", "name_en": "Full-time Staff Salary", "type": "Expense", "subtype": "Labor", "department": "管理部門", "dept_code": "ADM", "parent": "5000", "level": 2},
    "5020": {"name": "契約・パートスタッフ給与", "name_en": "Contract & Part-time Staff", "type": "Expense", "subtype": "Labor", "department": "管理部門", "dept_code": "ADM", "parent": "5000", "level": 2},
    "5030": {"name": "賞与・引当金", "name_en": "Bonuses & Allowances", "type": "Expense", "subtype": "Labor", "department": "管理部門", "dept_code": "ADM", "parent": "5000", "level": 2},
    
    "5300": {"name": "福利厚生・法定費用", "name_en": "Benefits & Payroll Taxes", "type": "Expense", "subtype": "Labor", "department": "管理部門", "dept_code": "ADM", "parent": None, "level": 1},
    "5310": {"name": "社会保険料", "name_en": "Social Insurance", "type": "Expense", "subtype": "Labor", "department": "管理部門", "dept_code": "ADM", "parent": "5300", "level": 2},
    "5320": {"name": "労働保険料", "name_en": "Labor Insurance", "type": "Expense", "subtype": "Labor", "department": "管理部門", "dept_code": "ADM", "parent": "5300", "level": 2},

    "5400": {"name": "賃借料", "name_en": "Rent", "type": "Expense", "subtype": "Facility", "department": "店舗開発部", "dept_code": "DEV", "parent": None, "level": 1},
    "5410": {"name": "店舗賃料", "name_en": "Store Rent", "type": "Expense", "subtype": "Facility", "department": "店舗開発部", "dept_code": "DEV", "parent": "5400", "level": 2},
    "5420": {"name": "本社・倉庫賃料", "name_en": "HQ & Warehouse Rent", "type": "Expense", "subtype": "Facility", "department": "店舗開発部", "dept_code": "DEV", "parent": "5400", "level": 2},

    "5500": {"name": "水道光熱費", "name_en": "Utilities", "type": "Expense", "subtype": "Facility", "department": "管理部門", "dept_code": "ADM", "parent": None, "level": 1},
    "5510": {"name": "電気代", "name_en": "Electricity", "type": "Expense", "subtype": "Facility", "department": "管理部門", "dept_code": "ADM", "parent": "5500", "level": 2},
    "5530": {"name": "上下水道代", "name_en": "Water & Sewer", "type": "Expense", "subtype": "Facility", "department": "管理部門", "dept_code": "ADM", "parent": "5500", "level": 2},

    "5800": {"name": "広告宣伝費", "name_en": "Advertising", "type": "Expense", "subtype": "Sales & Marketing", "department": "マーケティング部", "dept_code": "MKT", "parent": None, "level": 1},
    "5810": {"name": "販促・プロモーション費用", "name_en": "Sales Promotion", "type": "Expense", "subtype": "Sales & Marketing", "department": "マーケティング部", "dept_code": "MKT", "parent": "5800", "level": 2},
    "5820": {"name": "Web・SNS広告費", "name_en": "Web & SNS Ads", "type": "Expense", "subtype": "Sales & Marketing", "department": "マーケティング部", "dept_code": "MKT", "parent": "5800", "level": 2},
    
    "5900": {"name": "商品原価", "name_en": "Cost of Goods Sold", "type": "Expense", "subtype": "COGS", "department": "商品部", "dept_code": "PROD", "parent": None, "level": 1},
    "5910": {"name": "衣料品原価", "name_en": "Apparel COGS", "type": "Expense", "subtype": "COGS", "department": "衣料品事業部", "dept_code": "APPA", "parent": "5900", "level": 2},
    "5920": {"name": "生活雑貨原価", "name_en": "Household Goods COGS", "type": "Expense", "subtype": "COGS", "department": "生活雑貨事業部", "dept_code": "LIFE", "parent": "5900", "level": 2},
    "5930": {"name": "食品原価", "name_en": "Food COGS", "type": "Expense", "subtype": "COGS", "department": "食品事業部", "dept_code": "FOOD", "parent": "5900", "level": 2},

    "6000": {"name": "業務委託費", "name_en": "Outsourcing Costs", "type": "Expense", "subtype": "Operating", "department": "管理部門", "dept_code": "ADM", "parent": None, "level": 1},
    "6010": {"name": "物流・配送委託費", "name_en": "Logistics & Delivery", "type": "Expense", "subtype": "Operating", "department": "管理部門", "dept_code": "ADM", "parent": "6000", "level": 2},
    "6020": {"name": "システム開発・保守委託費", "name_en": "System Development", "type": "Expense", "subtype": "Operating", "department": "管理部門", "dept_code": "ADM", "parent": "6000", "level": 2},

    "6100": {"name": "減価償却費", "name_en": "Depreciation", "type": "Expense", "subtype": "Administrative", "department": "経理部", "dept_code": "FIN", "parent": None, "level": 1},
    "6110": {"name": "店舗設備償却", "name_en": "Store Asset Depreciation", "type": "Expense", "subtype": "Administrative", "department": "経理部", "dept_code": "FIN", "parent": "6100", "level": 2},
    "6120": {"name": "IT資産・ソフトウェア償却", "name_en": "IT Asset & Software Depreciation", "type": "Expense", "subtype": "Administrative", "department": "経理部", "dept_code": "FIN", "parent": "6100", "level": 2},
    
    "6200": {"name": "その他経費", "name_en": "Other Expenses", "type": "Expense", "subtype": "Operating", "department": "管理部門", "dept_code": "ADM", "parent": None, "level": 1},
    "6210": {"name": "消耗品費", "name_en": "Supplies", "type": "Expense", "subtype": "Operating", "department": "管理部門", "dept_code": "ADM", "parent": "6200", "level": 2},
    "6220": {"name": "通信費", "name_en": "Communications", "type": "Expense", "subtype": "Operating", "department": "管理部門", "dept_code": "ADM", "parent": "6200", "level": 2},
    "6230": {"name": "決済手数料", "name_en": "Payment Processing Fees", "type": "Expense", "subtype": "Operating", "department": "管理部門", "dept_code": "ADM", "parent": "6200", "level": 2}
}

def generate_seasonal_factor(month):
    """Generate seasonal factors for Japanese retail business"""
    # Japanese retail patterns: Spikes in March (new life), May (GW), July (bonus), Dec (bonus/Xmas). Dips in Feb, Aug.
    seasonal_factors = {
        1: 1.1,   # January - New Year sales
        2: 0.8,   # February - slow month
        3: 1.3,   # March - End of fiscal year, new life prep
        4: 1.1,   # April - Start of new year
        5: 1.2,   # May - Golden Week
        6: 1.0,   # June
        7: 1.25,  # July - Summer bonus season
        8: 0.85,  # August - Obon holidays, travel focus
        9: 1.0,   # September
        10: 1.1,  # October
        11: 1.15, # November - prep for winter
        12: 1.4   # December - Bonus season, Christmas
    }
    return seasonal_factors.get(month, 1.0)

def generate_revenue_amount(gl_account_id, location_id, month, year, scenario):
    """Generate realistic revenue amounts based on account type and location"""
    # Base amounts in JPY, adjusted for a lifestyle brand
    base_amounts = {
        # Level 1 Summary accounts
        "4000": 0, "4100": 0, "4200": 0, "4600": 0,
        
        # Level 2 Detail - Apparel
        "4010": 3500000, # Women's Wear
        "4020": 2500000, # Men's Wear
        "4030": 800000,  # Kids & Maternity
        "4040": 1200000, # Innerwear & Socks

        # Level 2 Detail - Household
        "4110": 1500000, # Furniture
        "4120": 1000000, # Bedding & Fabrics
        "4130": 1800000, # Kitchen & Tableware
        "4140": 2000000, # Stationery & Office
        "4150": 1300000, # Health & Beauty

        # Level 2 Detail - Food
        "4210": 2200000, # Packaged & Frozen Food
        "4220": 1600000, # Sweets & Snacks
        "4230": 900000,  # Beverages & Seasoning

        # Level 2 Detail - Other
        "4610": 500000,  # Cafe & Restaurant
        "4620": 200000,  # Events & Workshops
    }
    
    base = base_amounts.get(gl_account_id, 0)
    if base == 0:
        return 0
    
    # Location factor (premium for major urban centers)
    location_factors = {
        "JPN001": 1.5, "JPN002": 1.4, "JPN003": 1.4, "JPN004": 1.5, "JPN005": 1.4, # Tokyo premium
        "JPN007": 1.3, # Osaka Umeda
    }
    location_factor = location_factors.get(location_id, 1.0)
    
    # Seasonal adjustment
    seasonal_factor = generate_seasonal_factor(month)
    
    # Category-specific seasonality
    category_factors = {
        "4000": 1.2, # Apparel is more seasonal
        "4200": 0.9, # Food is less seasonal
    }
    parent_account = GL_ACCOUNTS.get(gl_account_id, {}).get("parent")
    seasonal_factor *= category_factors.get(parent_account, 1.0)

    # Year-over-year growth
    yoy_growth = 1.03 if year == 2025 else 1.0
    
    # Random variation
    random_factor = np.random.normal(1.0, 0.1)
    
    # Forecast uncertainty
    forecast_factor = 1.0
    if scenario == "Forecast":
        forecast_factor = np.random.normal(1.0, 0.05)
    
    # Store performance archetype (winners / losers / trend)
    rev_mult, _ = archetype_factor(location_id, month, year)

    amount = base * location_factor * seasonal_factor * yoy_growth * random_factor * forecast_factor * rev_mult
    return round(amount, 0)

def generate_expense_amount(gl_account_id, location_id, month, year, scenario, revenue_total):
    """Generate realistic expense amounts in JPY"""
    if gl_account_id.startswith("4"):
        return 0
    
    # Base amounts for expenses
    base_amounts = {
        "5010": 3000000, # Full-time Staff Salary
        "5020": 2500000, # Contract & Part-time Staff
        "5030": 800000,  # Bonuses & Allowances
        "5310": 900000,  # Social Insurance
        "5320": 300000,  # Labor Insurance
        "5410": 2200000, # Store Rent
        "5420": 800000,  # HQ & Warehouse Rent
        "5510": 300000,  # Electricity
        "5530": 80000,   # Water & Sewer
        "5810": 600000,  # Sales Promotion
        "5820": 400000,  # Web & SNS Ads
        "5910": revenue_total * 0.15, # Apparel COGS (approx. 15% of total revenue)
        "5920": revenue_total * 0.20, # Household COGS (approx. 20% of total revenue)
        "5930": revenue_total * 0.10, # Food COGS (approx. 10% of total revenue)
        "6010": 700000,  # Logistics & Delivery
        "6020": 500000,  # System Development
        "6110": 1200000, # Store Asset Depreciation
        "6120": 800000,  # IT Asset & Software Depreciation
        "6210": 150000,  # Supplies
        "6220": 100000,  # Communications
        "6230": 200000,  # Payment Processing Fees
    }
    
    base = base_amounts.get(gl_account_id, 0)
    if base == 0:
        return 0
    
    # Location factor for expenses
    location_factors = {
        "JPN001": 1.6, "JPN002": 1.5, "JPN003": 1.5, "JPN004": 1.6, "JPN005": 1.5, # Tokyo premium
    }
    location_factor = location_factors.get(location_id, 1.0)
    
    # Inflation factor
    inflation_factor = 1.02 if year == 2025 else 1.0
    
    # Random variation
    random_factor = np.random.normal(1.0, 0.08)
    
    # Forecast uncertainty
    forecast_factor = 1.0
    if scenario == "Forecast":
        forecast_factor = np.random.normal(1.0, 0.05)
        
    # Make COGS directly proportional to revenue total for realism.
    # COGS already reflects the store archetype because revenue_total does.
    if gl_account_id in ["5910", "5920", "5930"]:
        amount = base * random_factor * forecast_factor
    else:
        _, cost_mult = archetype_factor(location_id, month, year)
        seasonal_cost = seasonal_cost_factor(gl_account_id, month)
        amount = base * location_factor * inflation_factor * random_factor * forecast_factor * cost_mult * seasonal_cost
        
    return round(amount, 0)

def generate_pl_data():
    """Generate the complete P&L dataset"""
    records = []
    
    start_date = date(2024, 1, 1)
    end_date = date(2025, 12, 31)
    
    current_date_iter = start_date
    while current_date_iter <= end_date:
        month = current_date_iter.month
        year = current_date_iter.year
        quarter = f"Q{(month - 1) // 3 + 1}"
        fiscal_year = year
        
        scenario = "Forecast" if current_date_iter > CURRENT_DATE else "Actual"
        
        for location in LOCATIONS:
            account_amounts = {}
            location_revenue_total = 0
            
            # First pass: Generate Level 2 (detail) revenue to get a total
            for gl_account_id, account_info in GL_ACCOUNTS.items():
                if account_info["level"] == 2 and account_info["type"] == "Revenue":
                    revenue_amount = generate_revenue_amount(gl_account_id, location["id"], month, year, scenario)
                    account_amounts[gl_account_id] = {'revenue': revenue_amount, 'expense': 0}
                    location_revenue_total += revenue_amount

            # Second pass: Generate all expenses using the calculated revenue total
            for gl_account_id, account_info in GL_ACCOUNTS.items():
                 if account_info["type"] == "Expense":
                    expense_amount = generate_expense_amount(gl_account_id, location["id"], month, year, scenario, location_revenue_total)
                    # For expenses, level 1 is sum of level 2
                    if account_info["level"] == 2:
                        account_amounts[gl_account_id] = {'revenue': 0, 'expense': expense_amount}

            # Third pass: Roll up all amounts to Level 1 and generate records
            for gl_account_id, account_info in GL_ACCOUNTS.items():
                revenue_amount = 0
                expense_amount = 0
                
                if account_info["level"] == 1:  # Summary accounts
                    children = [acc_id for acc_id, acc_info in GL_ACCOUNTS.items() if acc_info.get("parent") == gl_account_id]
                    for child_id in children:
                        if child_id in account_amounts:
                            revenue_amount += account_amounts[child_id]['revenue']
                            expense_amount += account_amounts[child_id]['expense']
                else:  # Detail accounts
                    if gl_account_id in account_amounts:
                        revenue_amount = account_amounts[gl_account_id]['revenue']
                        expense_amount = account_amounts[gl_account_id]['expense']
                
                net_amount = revenue_amount - expense_amount
                profit = net_amount if net_amount > 0 else 0
                loss = abs(net_amount) if net_amount < 0 else 0
                
                variance_to_budget = np.random.normal(0, abs(net_amount) * 0.05) if net_amount != 0 else 0
                variance_percent = (variance_to_budget / net_amount * 100) if net_amount != 0 else 0
                
                record = {
                    "損益記録ID": str(uuid.uuid4()),
                    "日付": current_date_iter,
                    "期間": current_date_iter.strftime("%Y-%m"),
                    "月": month,
                    "年": year,
                    "四半期": quarter,
                    "会計年度": fiscal_year,
                    "店舗ID": location["id"],
                    "店舗名": location["name"],
                    "都道府県": location["prefecture"],
                    "市区町村": location["city"],
                    "郵便番号": location["postal_code"],
                    "地域": location["region"],
                    "地域コード": location["area_code"],
                    "勘定科目ID": gl_account_id,
                    "勘定科目名": account_info["name"],
                    "勘定科目名英語": account_info["name_en"],
                    "勘定科目種類": account_info["type"],
                    "勘定科目サブタイプ": account_info["subtype"],
                    "部門": account_info["department"],
                    "部門コード": account_info["dept_code"],
                    "親勘定科目ID": account_info.get("parent"),
                    "勘定科目レベル": account_info["level"],
                    "シナリオ": scenario,
                    "売上金額": revenue_amount,
                    "費用金額": expense_amount,
                    "利益": profit,
                    "損失": loss,
                    "純額": net_amount,
                    "予算差異": round(variance_to_budget, 0),
                    "差異率": round(variance_percent, 2),
                    "サマリ区分": account_info["level"] == 1,
                    "備考": f"{scenario.lower()} scenario data for level {account_info['level']} account",
                    "通貨": "JPY"
                }
                
                records.append(record)
        
        current_date_iter = current_date_iter.replace(day=1) + relativedelta(months=1)
    
    df = pd.DataFrame(records)
    df['日付'] = pd.to_datetime(df['日付'])
    return df

# Generate the dataset
print("シンプルスタイル（ライフスタイルブランド）損益データセット生成中...")
print("勘定科目カテゴリ:")
print("  - 収益: 衣料品, 生活雑貨, 食品")
print("  - 費用: 人件費, 賃借料, 商品原価, 広告宣伝費")
print(f"実績データ期間: {CURRENT_DATE}まで")
print(f"予測データ期間: {CURRENT_DATE + relativedelta(days=1)}から")
df = generate_pl_data()

# Display basic information
print(f"\nデータセット生成完了!")
print(f"総レコード数: {len(df):,}")
print(f"期間範囲: {df['期間'].min()} から {df['期間'].max()}")
print(f"店舗数: {df['店舗ID'].nunique()}")
print(f"勘定科目数: {df['勘定科目ID'].nunique()}")
print(f"レベル1（サマリ）勘定科目: {len(df[df['勘定科目レベル'] == 1]['勘定科目ID'].unique())}")
print(f"レベル2（詳細）勘定科目: {len(df[df['勘定科目レベル'] == 2]['勘定科目ID'].unique())}")

write_dataframe(df)