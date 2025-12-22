"""macOS Excel spreadsheet placer (Optimized)."""

import subprocess
import json
from typing import List
from ..base import BaseSpreadsheetPlacer
from ..formatting import CellFormat
from ....core.types import PlacementResult
from ....utils.logging import log
from ....i18n import t

class ExcelPlacer(BaseSpreadsheetPlacer):
    """macOS Excel 内容落地器（批量操作优化版）"""
    
    def place(self, table_data: List[List[str]], config: dict) -> PlacementResult:
        try:
            keep_format = config.get("keep_format", True)
            processed_data = self._process_table_data(table_data, keep_format)
            
            # 使用优化后的 AppleScript 批量插入
            success = self._applescript_insert_batch(processed_data, keep_format)
            
            if success:
                return PlacementResult(success=True, method="applescript")
            else:
                raise Exception(t("placer.macos_excel.applescript_failed"))
        
        except Exception as e:
            log(f"Excel AppleScript 插入失败: {e}")
            return PlacementResult(
                success=False,
                method="applescript",
                error=str(e)
            )

    def _process_table_data(self, table_data: List[List[str]], keep_format: bool) -> dict:
        """预处理数据，构建 AppleScript 需要的 list 结构"""
        rows_count = len(table_data)
        cols_count = max(len(row) for row in table_data) if table_data else 0
        
        clean_data = []
        format_info = []
        
        for i, row in enumerate(table_data):
            clean_row = []
            for j, cell_value in enumerate(row):
                cf = CellFormat(cell_value)
                text = cf.parse()
                clean_row.append(text)
                
                if keep_format and cf.segments:
                    seg = cf.segments[0]
                    if seg.bold or seg.italic or seg.strikethrough:
                        format_info.append({
                            "r": i + 1, "c": j + 1, # 转为从1开始的索引供AS使用
                            "b": seg.bold, "i": seg.italic, "s": seg.strikethrough
                        })
            # 补齐列
            while len(clean_row) < cols_count:
                clean_row.append("")
            clean_data.append(clean_row)
            
        return {
            "data": clean_data,
            "rows": rows_count,
            "cols": cols_count,
            "formats": format_info
        }

    def _applescript_insert_batch(self, processed_data: dict, keep_format: bool) -> bool:
        """
        利用 Range 赋值特性进行批量操作
        """
        data = processed_data["data"]
        rows = processed_data["rows"]
        cols = processed_data["cols"]
        formats = processed_data["formats"]

        # 构建 AppleScript 的 list of lists 字符串: {{"a", "b"}, {"c", "d"}}
        as_data_list = "{" + ",".join([
            "{" + ",".join([f'"{self._escape_as(cell)}"' for cell in row]) + "}"
            for row in data
        ]) + "}"

        # 构建格式化脚本
        format_cmds = []
        if keep_format:
            # 默认表头加粗
            format_cmds.append(f'set bold of font object of (get resize (active cell) row size 1 column size {cols}) to true')
            # 其他特定单元格格式
            for f in formats:
                target = f'cell {f["c"]} of row {f["r"]} of targetRange'
                if f["b"]: format_cmds.append(f'set bold of font object of ({target}) to true')
                if f["i"]: format_cmds.append(f'set italic of font object of ({target}) to true')
                if f["s"]: format_cmds.append(f'set strikethrough of font object of ({target}) to true')

        script = f'''
        tell application "Microsoft Excel"
            if (count of workbooks) is 0 then make new workbook
            
            try
                set startCell to active cell
            on error
                set startCell to cell 1 of row 1 of active sheet
            end try
            
            -- 计算目标区域
            set startR to first row index of startCell
            set startC to first column index of startCell
            set targetRange to (get resize startCell row size {rows} column size {cols})
            
            -- 核心优化：一次性批量赋值
            set value of targetRange to {as_data_list}
            
            -- 格式应用
            {" ".join(format_cmds)}
            
            -- 选中结果区域
            select targetRange
        end tell
        '''

        try:
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError as e:
            log(f"AppleScript Error: {e.stderr}")
            raise Exception(f"AppleScript Error: {e.stderr}")

    def _escape_as(self, s: str) -> str:
        """转义 AppleScript 字符串中的特殊字符"""
        return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\r')