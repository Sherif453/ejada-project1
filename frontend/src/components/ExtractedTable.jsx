import "./ExtractedTable.css";

export function normalizeTable(table) {
  const columns = Array.isArray(table?.columns)
    ? table.columns.map((cell) => String(cell ?? ""))
    : [];
  const rows = Array.isArray(table?.rows)
    ? table.rows
        .filter((row) => Array.isArray(row))
        .map((row) => row.map((cell) => String(cell ?? "")))
    : [];
  const width = Math.max(
    columns.length,
    ...rows.map((row) => row.length),
    0,
  );
  return {
    columns: columns.length > 0 ? padRow(columns, width) : [],
    rows: rows.map((row) => padRow(row, width)),
    width,
  };
}

function padRow(row, width) {
  return [...row, ...Array.from({ length: Math.max(0, width - row.length) }, () => "")];
}

function looksNumeric(value) {
  if (typeof value !== "string") return false;
  const normalized = value
    .trim()
    .replaceAll(",", "")
    .replaceAll(" ", "")
    .replace(/^\((.*)\)$/, "-$1")
    .replace(/%$/, "");
  return normalized !== "" && Number.isFinite(Number(normalized));
}

function cellClassName(value, columnIndex) {
  const classes = [];
  if (columnIndex === 0) classes.push("extracted-table__label");
  if (looksNumeric(value)) classes.push("extracted-table__numeric");
  return classes.join(" ") || undefined;
}

/**
 * Renders an extracted table.
 *
 * Pass `onCellEdit(section, rowIndex, columnIndex, value)` to make the table
 * editable in place — `section` is "columns" for header cells (rowIndex is
 * null) or "rows" for body cells. Without `onCellEdit`, the table renders
 * read-only, same as before.
 */
export default function ExtractedTable({ table, onCellEdit }) {
  const { columns, rows, width } = normalizeTable(table);
  if (width === 0 || rows.length === 0) {
    return <p className="extracted-table__empty">This table has no rows.</p>;
  }

  const editable = typeof onCellEdit === "function";

  const handleBlur = (event, section, rowIndex, columnIndex) => {
    onCellEdit(section, rowIndex, columnIndex, event.currentTarget.textContent);
  };

  return (
    <div className="extracted-table__scroll">
      <table className={`extracted-table${editable ? " extracted-table--editable" : ""}`}>
        {columns.length > 0 && (
          <thead>
            <tr>
              {columns.map((cell, columnIndex) => (
                <th
                  key={`head-${columnIndex}`}
                  className={cellClassName(cell, columnIndex)}
                  contentEditable={editable}
                  suppressContentEditableWarning={editable}
                  onBlur={
                    editable
                      ? (event) => handleBlur(event, "columns", null, columnIndex)
                      : undefined
                  }
                >
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`row-${rowIndex}`}>
              {row.map((cell, columnIndex) => (
                <td
                  key={`${rowIndex}-${columnIndex}`}
                  className={cellClassName(cell, columnIndex)}
                  contentEditable={editable}
                  suppressContentEditableWarning={editable}
                  onBlur={
                    editable
                      ? (event) => handleBlur(event, "rows", rowIndex, columnIndex)
                      : undefined
                  }
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}