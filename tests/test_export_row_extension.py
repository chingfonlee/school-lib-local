from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from app.services.export_service import _extend_data_rows


def test_extend_data_rows_copies_template_row_style_and_height():
    wb = Workbook()
    ws = wb.active
    template_row = 55
    insert_at = 56

    ws.row_dimensions[template_row].height = 19.5
    thin = Side(style="thin", color="000000")
    for col_idx in range(1, 13):
        cell = ws.cell(template_row, col_idx)
        cell.font = Font(name="Arial", bold=True)
        cell.fill = PatternFill("solid", fgColor="FFEFEFEF")
        cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.number_format = "@"

    _extend_data_rows(ws, template_row=template_row, insert_at=insert_at, extra_rows=3)

    for row in range(56, 59):
        assert ws.row_dimensions[row].height == 19.5
        for col_idx in range(1, 13):
            source = ws.cell(template_row, col_idx)
            target = ws.cell(row, col_idx)
            assert target.font.name == source.font.name
            assert target.font.bold == source.font.bold
            assert target.fill.fgColor.rgb == source.fill.fgColor.rgb
            assert target.border.left.style == source.border.left.style
            assert target.border.right.style == source.border.right.style
            assert target.border.top.style == source.border.top.style
            assert target.border.bottom.style == source.border.bottom.style
            assert target.alignment.horizontal == source.alignment.horizontal
            assert target.alignment.vertical == source.alignment.vertical
            assert target.alignment.wrap_text == source.alignment.wrap_text
            assert target.number_format == source.number_format


def test_extend_data_rows_unmerges_ranges_that_overlap_inserted_data_rows():
    wb = Workbook()
    ws = wb.active
    ws.merge_cells("A57:L57")
    ws.merge_cells("A58:L58")
    ws.merge_cells("A80:L80")

    _extend_data_rows(ws, template_row=55, insert_at=56, extra_rows=3)

    merged_ranges = {str(r) for r in ws.merged_cells.ranges}
    assert "A57:L57" not in merged_ranges
    assert "A58:L58" not in merged_ranges
    assert "A80:L80" in merged_ranges
