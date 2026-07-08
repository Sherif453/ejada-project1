import "./ExtractedTable.css";

function positiveInteger(value, fallback = 1) {
  return Number.isInteger(value) && value > 0 ? value : fallback;
}

function tableDimensions(table) {
  const cells = Array.isArray(table?.cells) ? table.cells : [];
  let rows = Number.isInteger(table?.row_count) ? table.row_count : 0;
  let columns = Number.isInteger(table?.column_count)
    ? table.column_count
    : 0;

  for (const cell of cells) {
    const row = Number.isInteger(cell.row) ? cell.row : 0;
    const column = Number.isInteger(cell.column) ? cell.column : 0;
    rows = Math.max(rows, row + positiveInteger(cell.row_span));
    columns = Math.max(columns, column + positiveInteger(cell.column_span));
  }

  return { rows, columns };
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

export default function ExtractedTable({ table }) {
  const cells = Array.isArray(table?.cells) ? table.cells : [];
  const { rows, columns } = tableDimensions(table);
  const cellsByOrigin = new Map();
  const coveredPositions = new Set();

  for (const cell of cells) {
    const row = cell.row;
    const column = cell.column;

    if (
      !Number.isInteger(row) ||
      !Number.isInteger(column) ||
      row < 0 ||
      column < 0
    ) {
      continue;
    }

    const rowSpan = positiveInteger(cell.row_span);
    const columnSpan = positiveInteger(cell.column_span);
    cellsByOrigin.set(`${row}:${column}`, cell);

    for (let currentRow = row; currentRow < row + rowSpan; currentRow += 1) {
      for (
        let currentColumn = column;
        currentColumn < column + columnSpan;
        currentColumn += 1
      ) {
        if (currentRow === row && currentColumn === column) continue;
        coveredPositions.add(`${currentRow}:${currentColumn}`);
      }
    }
  }

  if (rows === 0 || columns === 0) {
    return <p className="extracted-table__empty">This table has no cells.</p>;
  }

  return (
    <div className="extracted-table__scroll">
      <table className="extracted-table">
        <tbody>
          {Array.from({ length: rows }, (_, rowIndex) => (
            <tr key={`row-${rowIndex}`}>
              {Array.from({ length: columns }, (_, columnIndex) => {
                const key = `${rowIndex}:${columnIndex}`;

                if (coveredPositions.has(key)) return null;

                const cell = cellsByOrigin.get(key);
                if (!cell) {
                  return <td key={key} className="extracted-table__blank" />;
                }

                const CellTag = cell.is_header ? "th" : "td";
                const className = looksNumeric(cell.text)
                  ? "extracted-table__numeric"
                  : undefined;

                return (
                  <CellTag
                    key={key}
                    rowSpan={positiveInteger(cell.row_span)}
                    colSpan={positiveInteger(cell.column_span)}
                    className={className}
                  >
                    {cell.text || ""}
                  </CellTag>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
