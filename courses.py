import sys
from datetime import datetime, timedelta
from icalendar import Event
from icalendar.prop import vRecur


# --- JSON 格式定义与验证 ---

SCHEDULE_REQUIRED_KEYS = [
    "course_name",
    "location",
    "start_date",
    "weekday",
    "start_time",
    "end_time",
    "total_weeks",
]


def validate_json(data, required_keys):
    """验证JSON数据是否包含所有必需的键"""
    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        print(f"错误: JSON缺少以下必需字段: {', '.join(missing_keys)}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data.get("weekday"), list):
        print("错误: 'weekday' 字段必须是一个列表。", file=sys.stderr)
        sys.exit(1)


def parse_weekday_string(s):
    """
    解析特殊的星期字符串。
    "2" -> (2, "all") "2*" -> (2, "odd") "2**" -> (2, "even")
    返回 (星期数, 类型, RRULE星期缩写)
    """
    s = s.strip()
    week_type = "all"
    if s.endswith("**"):
        week_type = "even"
        day_str = s[:-2]
    elif s.endswith("*"):
        week_type = "odd"
        day_str = s[:-1]
    else:
        day_str = s

    try:
        day_num = int(day_str)
        if not 1 <= day_num <= 7:
            raise ValueError
        # icalendar/RFC5545 使用两位缩写: MO, TU, WE, TH, FR, SA, SU
        weekday_map = {1: "MO", 2: "TU", 3: "WE", 4: "TH", 5: "FR", 6: "SA", 7: "SU"}
        return day_num, week_type, weekday_map[day_num]
    except (ValueError, KeyError):
        print(
            f"错误: 无效的 weekday 格式: '{s}'。应为1-7的数字，可选后缀 '*' 或 '**'。",
            file=sys.stderr,
        )
        sys.exit(1)


def process_course_data(data):
    """根据课表JSON数据创建一组 icalendar.Event 对象"""
    print("调用函数: process_course_data")
    validate_json(data, SCHEDULE_REQUIRED_KEYS)

    events = []

    # 解析通用信息
    course_name = data["course_name"]
    location = data["location"]
    total_weeks = data["total_weeks"]

    try:
        start_time_obj = datetime.strptime(data["start_time"], "%H:%M").time()
        end_time_obj = datetime.strptime(data["end_time"], "%H:%M").time()
        reference_date = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    except ValueError as e:
        print(
            f"错误: 日期或时间格式不正确 (应为 YYYY-MM-DD 或 HH:MM): {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 计算开课第一周的周一
    week_start_date = reference_date - timedelta(days=reference_date.weekday())

    for weekday_item in data["weekday"]:
        target_weekday, week_type, rrule_weekday = parse_weekday_string(weekday_item)

        target_weekday_iso = target_weekday - 1
        days_offset = (target_weekday_iso - week_start_date.weekday() + 7) % 7
        first_class_date = week_start_date + timedelta(days=days_offset)

        # 根据单双周调整首次上课日期
        if week_type == "even" and first_class_date.isocalendar()[1] % 2 != 0:
            first_class_date += timedelta(weeks=1)
        elif week_type == "odd" and first_class_date.isocalendar()[1] % 2 == 0:
            first_class_date += timedelta(weeks=1)

        event = Event()
        event.add("summary", course_name)
        event.add("location", location)

        # 结合日期和时间创建datetime对象
        event.add("dtstart", datetime.combine(first_class_date, start_time_obj))
        event.add("dtend", datetime.combine(first_class_date, end_time_obj))
        event.add("dtstamp", datetime.now())  # 事件创建时间戳

        # 创建重复规则 (RRULE)
        interval = 1 if week_type == "all" else 2
        count = total_weeks if week_type == "all" else (total_weeks + 1) // 2

        # vRecur 需要一个字典，键必须是大写
        rrule = vRecur(freq="WEEKLY", interval=interval, count=count)
        event.add("rrule", rrule)

        week_type_map = {"all": "每周", "odd": "单周", "even": "双周"}
        print(
            f"信息: 正在为 '{course_name}' 创建事件 -> {week_type_map[week_type]} 周{target_weekday}, "
            f"首次上课: {first_class_date}, 重复 {count} 次。"
        )

        events.append(event)

    return events
