#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
import os
from datetime import datetime, timedelta
from icalendar import Calendar, Event, vRecur
from weekmarks import load_jsonc_or_json, process_weekmarks_data
from courses import process_course_data
from debug import debug_file

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


# --- 核心逻辑 ---


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


def create_schedule_events(data):
    """根据课表JSON数据创建一组 icalendar.Event 对象"""
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


# --- 主程序入口 ---
def main():
    parser = argparse.ArgumentParser(
        description="一个根据课表JSON生成ICS日历文件的命令行工具 (使用 icalendar 库)。",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest="mode", required=True, help="选择程序运行模式"
    )

    # --- Generate 命令 ---
    parser_gen = subparsers.add_parser("generate", help="从JSON文件生成ICS日历")
    parser_gen.add_argument("json_input", help="输入的课表 .json 文件路径")
    parser_gen.add_argument(
        "-o",
        "--output",
        default="schedule.ics",
        help="输出的ICS文件名 (默认为: schedule.ics)",
    )

    # --- Debug 命令 ---
    parser_debug = subparsers.add_parser(
        "debug", help="解析并显示JSON/JSONC或ICS文件的内容"
    )
    parser_debug.add_argument(
        "file_to_debug", help="需要调试的 .json/.jsonc 或 .ics 文件路径"
    )

    args = parser.parse_args()

    if args.mode == "generate":
        try:
            json_data = load_jsonc_or_json(args.json_input)
        except (FileNotFoundError, OSError) as e:
            print(
                f"错误: 无法读取或解析JSON文件 '{args.json_input}': {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        cal = Calendar()
        # 添加一些标准的日历属性
        cal.add("prodid", "-//My Course Schedule Generator//example.com//")
        cal.add("version", "2.0")

        # Determine which processor to use based on data content
        if "course_name" in json_data:
            events = process_course_data(json_data)
        elif "start_date" in json_data:
            events = process_weekmarks_data(json_data)
        else:
            print(
                f"错误: 无法识别JSON数据类型 in '{args.json_input}'。", file=sys.stderr
            )
            sys.exit(1)

        for ev in events:
            cal.add_component(ev)

        # write output next to source JSON/JSONC with same basename and .ics extension
        base = os.path.splitext(os.path.basename(args.json_input))[0]
        out_path = os.path.join(os.path.dirname(args.json_input), f"{base}.ics")
        try:
            with open(out_path, "wb") as f:
                f.write(cal.to_ical())
            print(f"\n成功！日历文件已保存为: {out_path}")
        except IOError as e:
            print(f"错误: 无法写入文件 '{out_path}': {e}", file=sys.stderr)
            sys.exit(1)

    elif args.mode == "debug":
        debug_file(args.file_to_debug)


if __name__ == "__main__":
    main()
