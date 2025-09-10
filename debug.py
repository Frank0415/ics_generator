#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from icalendar import Calendar
from weekmarks import load_jsonc_or_json
from courses import process_course_data
from weekmarks import process_weekmarks_data


def _print_event(ev, index=None):
    idx = f"{index + 1}. " if index is not None else ""
    summary = ev.get("summary")
    dtstart = ev.get("dtstart").dt
    dtend = ev.get("dtend").dt
    print(f"{idx}标题: {summary}")
    # dtstart/dtend may be date or datetime
    try:
        print(f"    开始: {dtstart.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"    结束: {dtend.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception:
        print(f"    开始: {dtstart}")
        print(f"    结束: {dtend}")


def debug_json(filepath):
    """Load .json or .jsonc and show how it will be parsed into events."""
    try:
        data = load_jsonc_or_json(filepath)
    except Exception as e:
        print(f"错误: 无法读取或解析JSON/JSONC文件: {e}", file=sys.stderr)
        return

    print(f"解析 JSON 文件: {filepath}")

    events = None
    if isinstance(data, dict) and "course_name" in data:
        events = process_course_data(data)
    elif isinstance(data, dict) and "start_date" in data:
        events = process_weekmarks_data(data)
    else:
        print("无法识别 JSON 数据类型（既不是课程也不是 weekmarks）。", file=sys.stderr)
        return

    print(f"生成了 {len(events)} 个事件：")
    for i, ev in enumerate(events):
        _print_event(ev, i)


def debug_ics(filepath):
    """Read an .ics file and print contained events."""
    try:
        with open(filepath, "rb") as f:
            cal = Calendar.from_ical(f.read())
    except Exception as e:
        print(f"错误: 无法解析ICS文件: {e}", file=sys.stderr)
        return

    events = list(cal.walk("VEVENT"))
    print(f"文件 '{filepath}' 包含 {len(events)} 个事件系列。")
    for i, ev in enumerate(events):
        _print_event(ev, i)


def debug_file(filepath):
    """Entry point for debugging a file (json/jsonc/ics)."""
    if filepath.lower().endswith((".json", ".jsonc")):
        debug_json(filepath)
    elif filepath.lower().endswith(".ics"):
        debug_ics(filepath)
    else:
        print("错误: 调试模式仅支持 .json/.jsonc 和 .ics 文件。", file=sys.stderr)
