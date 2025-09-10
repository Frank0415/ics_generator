#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import sys
import os
from datetime import datetime, timedelta, time
from icalendar import Calendar, Event
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


# --- 调试功能 ---
def debug_file(filepath):
    """解析并打印 JSON 或 ICS 文件的内容"""
    print(f"\n--- 开始调试文件: {filepath} ---\n")
    if filepath.lower().endswith(".json"):
        debug_json(filepath)
    elif filepath.lower().endswith(".ics"):
        debug_ics(filepath)
    else:
        print("错误: 调试模式仅支持 .json 和 .ics 文件。", file=sys.stderr)
        sys.exit(1)
    print(f"\n--- 调试结束 ---\n")


def debug_json(filepath):
    """调试JSON文件"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"错误: 无法读取或解析JSON文件: {e}", file=sys.stderr)
        sys.exit(1)

    print("程序将按如下方式解析您的JSON文件：")
    try:
        create_schedule_events(data)
    except SystemExit:
        print("\nJSON验证失败，无法继续解析。")


def debug_ics(filepath):
    """调试ICS文件"""
    try:
        with open(filepath, "rb") as f:  # icalendar 需要以二进制模式读取
            cal = Calendar.from_ical(f.read())
    except Exception as e:
        print(f"错误: 无法解析ICS文件: {e}", file=sys.stderr)
        sys.exit(1)

    # cal.walk('VEVENT') 是遍历所有事件组件的推荐方式
    events = list(cal.walk("VEVENT"))
    print(f"文件 '{filepath}' 包含 {len(events)} 个事件系列。\n")
    for i, event in enumerate(events):
        print(f"--- 事件 {i + 1} ---")
        print(f"  标题: {event.get('summary')}")
        print(f"  地点: {event.get('location', '未指定')}")

        # .dt 属性将icalendar的日期时间类型转换为Python的datetime对象
        dtstart = event.get("dtstart").dt
        dtend = event.get("dtend").dt
        print(f"  首次开始时间: {dtstart.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  首次结束时间: {dtend.strftime('%Y-%m-%d %H:%M:%S')}")

        if "rrule" in event:
            rrule = event["rrule"]
            # rrule 的值是列表，例如 FREQ: ['WEEKLY']
            freq = rrule.get("FREQ", [""])[0]
            interval = rrule.get("INTERVAL", [1])[0]
            count = rrule.get("COUNT", [None])[0]
            print(f"  重复规则 (RRULE):")
            print(f"    频率: {freq}")
            print(f"    间隔: 每 {interval} 个'{freq}'周期重复一次")
            if count:
                print(f"    次数: 共重复 {count} 次")
            else:
                print("    次数: 无限重复")
        else:
            print("  重复规则: 无 (单次事件)")
        print("-" * 15)


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
    parser_gen.add_argument(
        "json_input", nargs="+", help="输入的课表 .json 文件路径 (支持多个)"
    )
    parser_gen.add_argument(
        "-o",
        "--output",
        help="输出的ICS文件名 (默认为: 与输入文件相同的目录下的 schedule.ics)",
    )

    # --- Debug 命令 ---
    parser_debug = subparsers.add_parser("debug", help="解析并显示JSON或ICS文件的内容")
    parser_debug.add_argument("file_to_debug", help="需要调试的 .json 或 .ics 文件路径")

    args = parser.parse_args()

    if args.mode == "generate":
        for json_path in args.json_input:
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    json_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(
                    f"错误: 无法读取或解析JSON文件 '{json_path}': {e}", file=sys.stderr
                )
                continue

            cal = Calendar()
            # 添加一些标准的日历属性
            cal.add("prodid", "-//My Course Schedule Generator//example.com//")
            cal.add("version", "2.0")

            events = create_schedule_events(json_data)
            for ev in events:
                cal.add_component(ev)

            # derive output path per input JSON
            base = os.path.splitext(os.path.basename(json_path))[0]
            out_path = os.path.join(os.path.dirname(json_path), f"{base}.ics")
            try:
                with open(out_path, "wb") as f:
                    f.write(cal.to_ical())
                print(f"成功！日历文件已保存为: {out_path}")
            except IOError as e:
                print(f"错误: 无法写入文件 '{out_path}': {e}", file=sys.stderr)
                continue

    elif args.mode == "debug":
        debug_file(args.file_to_debug)


if __name__ == "__main__":
    main()
