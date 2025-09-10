import json
import re
import sys
from datetime import datetime, timedelta
from icalendar import Event


def load_jsonc_or_json(filepath):
    """Load JSON or JSONC (strip // and /* */ comments) and return parsed dict."""
    if filepath.lower().endswith(".jsonc"):
        with open(filepath, "r", encoding="utf-8") as f:
            txt = f.read()
        # remove single-line // comments
        txt = re.sub(r"//.*", "", txt)
        # remove C-style block comments
        txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
        try:
            return json.loads(txt)
        except json.JSONDecodeError as e:
            print(f"错误: 无法解析JSONC文件 '{filepath}': {e}", file=sys.stderr)
            raise
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)


def process_weekmarks_data(data):
    """Process weekmarks data and return a list of Events."""
    print("调用函数: process_weekmarks_data")
    if "start_date" not in data:
        print("错误: weekmarks JSON 必须包含 'start_date' 字段。", file=sys.stderr)
        raise SystemExit(1)

    name_tpl = data.get("name", "Week {}")
    start_number = data.get("start_number", 0)
    total_weeks = data.get("total_weeks", 1)  # default to 1 if not specified

    try:
        start_date = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    except ValueError as e:
        print(f"错误: start_date 格式应为 YYYY-MM-DD: {e}", file=sys.stderr)
        raise

    # 计算 start_date 所在周的周一作为实际开始日期
    week_start_date = start_date - timedelta(days=start_date.weekday())

    events = []
    for i in range(total_weeks):
        week_start = week_start_date + timedelta(days=7 * i)
        week_end = week_start + timedelta(days=7)
        week_number = start_number + i

        event = Event()
        event.add("summary", name_tpl.format(week_number))
        # use DATE (all-day) start and end (dtend is exclusive per RFC5545)
        event.add("dtstart", week_start)
        event.add("dtend", week_end)
        event.add("dtstamp", datetime.now())

        events.append(event)

    return events
