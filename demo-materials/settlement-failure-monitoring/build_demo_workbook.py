#!/usr/bin/env python3
"""Generate the synthetic settlement-failure demo workbook."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo


OUTPUT = Path(__file__).with_name("03_数据模型_数据字典_样例数据.xlsx")

NAVY = "0B1F33"
TEAL = "0F766E"
PALE = "E8F3F1"
GRID = "CFD8DC"
WHITE = "FFFFFF"


def add_sheet(workbook: Workbook, title: str, headers: list[str], rows: list[tuple]) -> None:
    sheet = workbook.create_sheet(title)
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.row_dimensions[1].height = 28
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(name="Arial", size=10, bold=True, color=WHITE)
        cell.alignment = Alignment(vertical="center")
    thin = Side(style="thin", color=GRID)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name="Arial", size=10, color="172B36")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=thin)
    for col in sheet.columns:
        values = [str(cell.value or "") for cell in col[: min(len(col), 80)]]
        width = min(max(max(map(len, values), default=10) + 2, 12), 44)
        sheet.column_dimensions[col[0].column_letter].width = width
    if rows:
        ref = f"A1:{sheet.cell(row=len(rows) + 1, column=len(headers)).coordinate}"
        table = Table(displayName="T" + "".join(ch for ch in title if ch.isalnum())[:24], ref=ref)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        sheet.add_table(table)


def main() -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.title = "证券交收失败监控数据模型、字典与构造型样例"
    workbook.properties.subject = "Ontology Studio E2E demo input"
    workbook.properties.creator = "Ontology Product Demo Team"
    workbook.properties.description = "Synthetic data only; no confidential or production information."
    workbook.properties.created = datetime(2026, 8, 23, tzinfo=timezone.utc)

    add_sheet(
        workbook,
        "Data_Model",
        ["table_name", "business_object", "grain", "primary_key", "description", "update_mode", "owner"],
        [
            ("settlement_instruction_snapshot", "交收指令快照", "每个统计日每条交收指令一行", "snapshot_date + instruction_id", "每日18:30 HKT记录交收指令状态、数量和失败恢复日期", "append-only daily snapshot", "Settlement Operations"),
            ("participant_reference", "参与者", "每个参与者一行", "participant_id", "参与交收的机构参考信息", "type-1 reference", "Participant Data"),
            ("instrument_reference", "证券", "每只证券一行", "instrument_id", "证券标识、市场板块和交易币种", "type-1 reference", "Instrument Data"),
            ("daily_price", "每日参考价格", "每只证券每个营业日一行", "business_date + instrument_id", "统计日收盘参考价", "append-only daily", "Market Data"),
            ("fx_rate", "汇率", "每个日期、源币种和目标币种一行", "rate_date + from_currency + to_currency", "金额折算使用的日终汇率", "append-only daily", "Market Data"),
            ("trading_calendar", "营业日历", "每个自然日一行", "calendar_date", "香港营业日标记", "maintained reference", "Reference Data"),
        ],
    )

    dictionary_rows = [
        ("settlement_instruction_snapshot", "snapshot_date", "date", "NO", "YES", "", "状态快照所属统计日", "YYYY-MM-DD", "2026-08-20"),
        ("settlement_instruction_snapshot", "instruction_id", "varchar(40)", "NO", "YES", "", "交收指令唯一标识", "", "SI-002"),
        ("settlement_instruction_snapshot", "trade_id", "varchar(40)", "NO", "NO", "", "产生交收指令的交易标识", "", "TR-002"),
        ("settlement_instruction_snapshot", "market_type", "varchar(40)", "NO", "NO", "", "市场类型", "MarketType", "EXCHANGE_TRADED_EQUITY"),
        ("settlement_instruction_snapshot", "participant_id", "varchar(20)", "NO", "NO", "participant_reference.participant_id", "承担该指令交收责任的参与者", "", "P001"),
        ("settlement_instruction_snapshot", "instrument_id", "varchar(20)", "NO", "NO", "instrument_reference.instrument_id", "交收证券标识", "", "INST001"),
        ("settlement_instruction_snapshot", "side", "varchar(4)", "NO", "NO", "", "买卖方向", "Side", "BUY"),
        ("settlement_instruction_snapshot", "settlement_currency", "char(3)", "NO", "NO", "", "交收币种", "ISO 4217", "HKD"),
        ("settlement_instruction_snapshot", "settlement_date", "date", "NO", "NO", "", "计划交收日期", "YYYY-MM-DD", "2026-08-20"),
        ("settlement_instruction_snapshot", "status", "varchar(24)", "NO", "NO", "", "统计截点的交收状态", "SettlementStatus", "FAILED"),
        ("settlement_instruction_snapshot", "original_quantity", "numeric(20,4)", "NO", "NO", "", "原始应交收数量", "shares", 1000),
        ("settlement_instruction_snapshot", "settled_quantity", "numeric(20,4)", "NO", "NO", "", "截至统计截点已交收数量", "shares", 0),
        ("settlement_instruction_snapshot", "remaining_quantity", "numeric(20,4)", "NO", "NO", "", "尚未交收数量；应等于原始数量减已交收数量", "shares", 1000),
        ("settlement_instruction_snapshot", "first_failed_date", "date", "YES", "NO", "", "该指令首次被判定失败的营业日", "YYYY-MM-DD", "2026-08-19"),
        ("settlement_instruction_snapshot", "fully_settled_date", "date", "YES", "NO", "", "失败后最终完成交收的日期", "YYYY-MM-DD", "2026-08-20"),
        ("settlement_instruction_snapshot", "fail_reason_code", "varchar(30)", "YES", "NO", "", "失败原因代码", "FailReason", "INSUFFICIENT_SECURITIES"),
        ("settlement_instruction_snapshot", "last_status_time", "timestamptz", "NO", "NO", "", "状态最后更新时间", "Asia/Hong_Kong", "2026-08-20T18:20:00+08:00"),
        ("participant_reference", "participant_id", "varchar(20)", "NO", "YES", "", "参与者唯一标识", "", "P001"),
        ("participant_reference", "participant_name", "varchar(100)", "NO", "NO", "", "构造型参与者名称", "", "Demo Broker Alpha"),
        ("participant_reference", "participant_type", "varchar(30)", "NO", "NO", "", "参与者类型", "ParticipantType", "BROKER"),
        ("participant_reference", "active_flag", "boolean", "NO", "NO", "", "参与者是否有效", "true/false", True),
        ("instrument_reference", "instrument_id", "varchar(20)", "NO", "YES", "", "证券内部唯一标识", "", "INST001"),
        ("instrument_reference", "isin", "varchar(12)", "NO", "NO", "", "构造型 ISIN", "ISO 6166-like demo", "HK0000000001"),
        ("instrument_reference", "instrument_name", "varchar(100)", "NO", "NO", "", "构造型证券名称", "", "Demo Equity One"),
        ("instrument_reference", "market_segment", "varchar(30)", "NO", "NO", "", "市场板块", "MarketSegment", "MAIN_BOARD"),
        ("instrument_reference", "currency", "char(3)", "NO", "NO", "", "证券参考价币种", "ISO 4217", "HKD"),
        ("daily_price", "business_date", "date", "NO", "YES", "trading_calendar.calendar_date", "价格所属营业日", "YYYY-MM-DD", "2026-08-20"),
        ("daily_price", "instrument_id", "varchar(20)", "NO", "YES", "instrument_reference.instrument_id", "证券标识", "", "INST001"),
        ("daily_price", "close_price", "numeric(20,6)", "NO", "NO", "", "日终参考收盘价", "currency per share", 50),
        ("daily_price", "currency", "char(3)", "NO", "NO", "", "价格币种", "ISO 4217", "HKD"),
        ("fx_rate", "rate_date", "date", "NO", "YES", "trading_calendar.calendar_date", "汇率日期", "YYYY-MM-DD", "2026-08-20"),
        ("fx_rate", "from_currency", "char(3)", "NO", "YES", "", "源币种", "ISO 4217", "USD"),
        ("fx_rate", "to_currency", "char(3)", "NO", "YES", "", "目标币种", "ISO 4217", "HKD"),
        ("fx_rate", "rate", "numeric(18,8)", "NO", "NO", "", "1单位源币种对应的目标币种金额", "to/from", 7.8),
        ("trading_calendar", "calendar_date", "date", "NO", "YES", "", "自然日", "YYYY-MM-DD", "2026-08-20"),
        ("trading_calendar", "is_business_day", "boolean", "NO", "NO", "", "是否香港营业日", "true/false", True),
    ]
    add_sheet(workbook, "Data_Dictionary", ["table_name", "field_name", "data_type", "nullable", "primary_key", "foreign_key", "business_definition", "unit_or_enum", "sample_value"], dictionary_rows)

    add_sheet(
        workbook,
        "Relationships",
        ["relationship_id", "left_table", "left_field", "right_table", "right_field", "cardinality", "join_type", "business_meaning"],
        [
            ("R-01", "settlement_instruction_snapshot", "participant_id", "participant_reference", "participant_id", "many-to-one", "inner", "每条交收指令由一个参与者负责"),
            ("R-02", "settlement_instruction_snapshot", "instrument_id", "instrument_reference", "instrument_id", "many-to-one", "inner", "每条交收指令对应一只证券"),
            ("R-03", "settlement_instruction_snapshot", "snapshot_date + instrument_id", "daily_price", "business_date + instrument_id", "many-to-one", "left", "使用统计日证券参考价格估值"),
            ("R-04", "settlement_instruction_snapshot", "snapshot_date + settlement_currency", "fx_rate", "rate_date + from_currency", "many-to-one", "left", "使用统计日交收币种到HKD汇率折算"),
            ("R-05", "settlement_instruction_snapshot", "first_failed_date..snapshot_date", "trading_calendar", "calendar_date", "many-to-many range", "range", "用香港营业日历计算失败年龄"),
        ],
    )

    add_sheet(
        workbook,
        "Enums",
        ["enum_name", "code", "business_label_zh", "definition", "included_in_scope"],
        [
            ("SettlementStatus", "PENDING", "待交收", "到期后尚未产生交收数量", "YES when due and remaining > 0"),
            ("SettlementStatus", "PARTIALLY_SETTLED", "部分交收", "已完成部分数量但仍有剩余", "YES when due and remaining > 0"),
            ("SettlementStatus", "SETTLED", "已交收", "全部数量完成交收", "YES for due denominator; NO for active fail"),
            ("SettlementStatus", "FAILED", "交收失败", "统计截点仍未完成交收", "YES when due and remaining > 0"),
            ("SettlementStatus", "CANCELLED", "已取消", "指令被业务取消", "NO"),
            ("MarketType", "EXCHANGE_TRADED_EQUITY", "交易所股票", "目标演示市场", "YES"),
            ("MarketType", "OTC", "场外交易", "不在本场景范围", "NO"),
            ("Side", "BUY", "买入", "买方交收责任", "YES"),
            ("Side", "SELL", "卖出", "卖方交收责任", "YES"),
            ("FailReason", "INSUFFICIENT_SECURITIES", "证券不足", "可用证券数量不足", "YES"),
            ("FailReason", "INSUFFICIENT_CASH", "资金不足", "可用资金不足", "YES"),
            ("FailReason", "INSTRUCTION_MISMATCH", "指令不匹配", "关键指令属性不一致", "YES"),
            ("ParticipantType", "BROKER", "经纪参与者", "演示参与者类型", "YES"),
            ("ParticipantType", "CUSTODIAN", "托管参与者", "演示参与者类型", "YES"),
        ],
    )

    add_sheet(
        workbook,
        "Sample_Settlement",
        ["snapshot_date", "instruction_id", "trade_id", "market_type", "participant_id", "instrument_id", "side", "settlement_currency", "settlement_date", "status", "original_quantity", "settled_quantity", "remaining_quantity", "first_failed_date", "fully_settled_date", "fail_reason_code", "last_status_time"],
        [
            (date(2026,8,20), "SI-001", "TR-001", "EXCHANGE_TRADED_EQUITY", "P001", "INST001", "BUY", "HKD", date(2026,8,20), "SETTLED", 1000, 1000, 0, None, date(2026,8,20), None, "2026-08-20T15:10:00+08:00"),
            (date(2026,8,20), "SI-002", "TR-002", "EXCHANGE_TRADED_EQUITY", "P001", "INST001", "SELL", "HKD", date(2026,8,19), "FAILED", 1000, 0, 1000, date(2026,8,19), None, "INSUFFICIENT_SECURITIES", "2026-08-20T18:20:00+08:00"),
            (date(2026,8,20), "SI-003", "TR-003", "EXCHANGE_TRADED_EQUITY", "P002", "INST002", "BUY", "USD", date(2026,8,18), "PARTIALLY_SETTLED", 2000, 1500, 500, date(2026,8,18), None, "INSTRUCTION_MISMATCH", "2026-08-20T18:15:00+08:00"),
            (date(2026,8,20), "SI-004", "TR-004", "EXCHANGE_TRADED_EQUITY", "P002", "INST001", "BUY", "HKD", date(2026,8,20), "CANCELLED", 1000, 0, 1000, None, None, None, "2026-08-20T12:00:00+08:00"),
            (date(2026,8,20), "SI-005", "TR-005", "EXCHANGE_TRADED_EQUITY", "P003", "INST003", "SELL", "HKD", date(2026,8,20), "PENDING", 800, 0, 800, date(2026,8,20), None, "INSUFFICIENT_CASH", "2026-08-20T18:25:00+08:00"),
            (date(2026,8,20), "SI-006", "TR-006", "EXCHANGE_TRADED_EQUITY", "P003", "INST002", "BUY", "USD", date(2026,8,18), "SETTLED", 600, 600, 0, date(2026,8,18), date(2026,8,20), "INSTRUCTION_MISMATCH", "2026-08-20T16:00:00+08:00"),
            (date(2026,8,20), "SI-007", "TR-007", "EXCHANGE_TRADED_EQUITY", "P004", "INST003", "BUY", "HKD", date(2026,8,20), "SETTLED", 500, 500, 0, None, date(2026,8,20), None, "2026-08-20T14:00:00+08:00"),
            (date(2026,8,20), "SI-008", "TR-008", "OTC", "P004", "INST001", "SELL", "HKD", date(2026,8,19), "FAILED", 900, 0, 900, date(2026,8,19), None, "INSUFFICIENT_SECURITIES", "2026-08-20T18:10:00+08:00"),
            (date(2026,8,20), "SI-009", "TR-009", "EXCHANGE_TRADED_EQUITY", "P004", "INST001", "BUY", "HKD", date(2026,8,21), "FAILED", 400, 0, 400, date(2026,8,20), None, "INSTRUCTION_MISMATCH", "2026-08-20T18:05:00+08:00"),
            (date(2026,8,20), "SI-010", "TR-010", "EXCHANGE_TRADED_EQUITY", "P004", "INST001", "SELL", "HKD", date(2026,8,17), "FAILED", 300, 0, 300, date(2026,8,17), None, "INSUFFICIENT_SECURITIES", "2026-08-20T18:28:00+08:00"),
        ],
    )

    add_sheet(workbook, "Sample_Participant", ["participant_id", "participant_name", "participant_type", "active_flag"], [
        ("P001", "Demo Broker Alpha", "BROKER", True),
        ("P002", "Demo Broker Beta", "BROKER", True),
        ("P003", "Demo Custodian Gamma", "CUSTODIAN", True),
        ("P004", "Demo Broker Delta", "BROKER", True),
    ])
    add_sheet(workbook, "Sample_Instrument", ["instrument_id", "isin", "instrument_name", "market_segment", "currency"], [
        ("INST001", "HK0000000001", "Demo Equity One", "MAIN_BOARD", "HKD"),
        ("INST002", "HK0000000002", "Demo Equity Two", "MAIN_BOARD", "USD"),
        ("INST003", "HK0000000003", "Demo Equity Three", "GEM", "HKD"),
    ])
    add_sheet(workbook, "Sample_Price", ["business_date", "instrument_id", "close_price", "currency"], [
        (date(2026,8,20), "INST001", 50, "HKD"),
        (date(2026,8,20), "INST002", 10, "USD"),
        (date(2026,8,20), "INST003", 25, "HKD"),
    ])
    add_sheet(workbook, "Sample_FX", ["rate_date", "from_currency", "to_currency", "rate"], [
        (date(2026,8,20), "HKD", "HKD", 1),
        (date(2026,8,20), "USD", "HKD", 7.8),
    ])
    add_sheet(workbook, "Sample_Calendar", ["calendar_date", "is_business_day"], [
        (date(2026,8,14), True),
        (date(2026,8,15), False),
        (date(2026,8,16), False),
        (date(2026,8,17), True),
        (date(2026,8,18), True),
        (date(2026,8,19), True),
        (date(2026,8,20), True),
        (date(2026,8,21), True),
    ])

    notes = workbook.create_sheet("README", 0)
    notes["A1"] = "证券交收失败监控 · 构造型数据包"
    notes["A1"].font = Font(name="Arial", size=18, bold=True, color=NAVY)
    notes["A3"] = "用途"
    notes["B3"] = "Ontology Studio E2E 演示；不包含任何真实客户、参与者或交易所数据。"
    notes["A4"] = "统计日"
    notes["B4"] = "2026-08-20"
    notes["A5"] = "关键结果"
    notes["B5"] = "到期7；活跃失败4；失败率57.1429%；失败金额HKD124,000；平均年龄1.50；两日恢复率20%；Top3集中度87.9032%。"
    notes["A7"] = "工作表"
    notes["B7"] = "Data_Model、Data_Dictionary、Relationships、Enums 以及各 Sample_* 表。"
    for row in range(3, 8):
        notes[f"A{row}"].font = Font(name="Arial", size=10, bold=True, color=TEAL)
        notes[f"B{row}"].font = Font(name="Arial", size=10, color="172B36")
        notes[f"B{row}"].alignment = Alignment(wrap_text=True, vertical="top")
    notes.column_dimensions["A"].width = 18
    notes.column_dimensions["B"].width = 90
    notes.sheet_view.showGridLines = False

    workbook.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
