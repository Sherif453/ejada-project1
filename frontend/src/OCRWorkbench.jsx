import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import api from "./api";
import ExtractedTable, { normalizeTable } from "./components/ExtractedTable";
import "./ocr-workbench.css";

const POLL_INTERVAL_MS = 2000;

function formatDate(iso) {
  if (!iso) return "—";

  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function tableKey(table, fallbackIndex) {
  return `${table.page_number ?? "page"}:${table.table_index ?? fallbackIndex}`;
}

// NOTE: defined at module scope (not inside a component) on purpose —
// several components below use `document` as a prop name for the OCR
// document object, which shadows the global `document`. Keeping this here
// guarantees it always refers to the real DOM document.
function downloadFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function toCsvValue(value) {
  const stringValue = String(value ?? "");
  if (/[",\n]/.test(stringValue)) {
    return `"${stringValue.replaceAll('"', '""')}"`;
  }
  return stringValue;
}

function tableToCsv(table) {
  const lines = [];
  if (table.columns?.length) {
    lines.push(table.columns.map(toCsvValue).join(","));
  }
  for (const row of table.rows) {
    lines.push(row.map(toCsvValue).join(","));
  }
  return lines.join("\r\n");
}

function safeFileName(name) {
  return (name || "export").replace(/[^\w.-]+/g, "_");
}

function StatusBadge({ status }) {
  const statuses = {
    uploading: { label: "Uploading", className: "badge--uploading" },
    processing: { label: "Processing", className: "badge--processing" },
    done: { label: "Ready", className: "badge--done" },
    failed: { label: "Failed", className: "badge--failed" },
  };

  const current = statuses[status] || statuses.processing;
  return <span className={`badge ${current.className}`}>{current.label}</span>;
}

function DocumentCard({ document, active, onSelect, onDelete }) {
  const select = () => onSelect(document.id);

  return (
    <div
      className={`doc-card ${active ? "doc-card--active" : ""}`}
      role="button"
      tabIndex={0}
      onClick={select}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      }}
    >
      <div className="doc-card__scan-frame" aria-hidden="true">
        <div className="doc-card__sheet">
          <div className="doc-card__line" />
          <div className="doc-card__line" />
          <div className="doc-card__line short" />
        </div>
        {document.status === "processing" && <div className="scan-beam" />}
        {document.status === "done" && (
          <div className="stamp">
            <span>READY</span>
          </div>
        )}
        {document.status === "failed" && (
          <div className="stamp stamp--failed">
            <span>FAILED</span>
          </div>
        )}
      </div>

      <div className="doc-card__meta">
        <div className="doc-card__title-row">
          <span className="doc-card__name" title={document.filename}>
            {document.filename}
          </span>
          <StatusBadge status={document.status} />
        </div>

        <div className="doc-card__sub">
          {formatDate(document.uploaded_at)}
          {document.page_count != null ? ` · ${document.page_count}p` : ""}
          {document.table_count != null ? ` · ${document.table_count} tables` : ""}
          {typeof document.confidence === "number"
            ? ` · ${Math.round(document.confidence * 100)}%`
            : ""}
        </div>

        {document.status === "uploading" && (
          <div className="progress-track">
            <div
              className="progress-fill"
              style={{ width: `${document.progress || 0}%` }}
            />
          </div>
        )}
      </div>

      <button
        type="button"
        className="doc-card__delete"
        aria-label={`Delete ${document.filename}`}
        onClick={(event) => {
          event.stopPropagation();
          onDelete(document.id, document.filename);
        }}
      >
        ×
      </button>
    </div>
  );
}

function ResultViewer({ document }) {
  const tables = useMemo(
    () => (Array.isArray(document.result?.tables) ? document.result.tables : []),
    [document.result],
  );
  const [selectedTableKey, setSelectedTableKey] = useState(null);

  // Edited tables live here, keyed by "<documentId>::<tableKey>", separate
  // from `document.result` (the original API response). Exports always read
  // from this state, so they reflect edits, not the original extraction.
  const [editedTables, setEditedTables] = useState({});

  useEffect(() => {
    if (tables.length === 0) {
      setSelectedTableKey(null);
      return;
    }

    setSelectedTableKey((current) => {
      if (tables.some((table, index) => tableKey(table, index) === current)) {
        return current;
      }
      return tableKey(tables[0], 0);
    });
  }, [document.id, tables]);

  const selectedTable = tables.find(
    (table, index) => tableKey(table, index) === selectedTableKey,
  );

  const editedKey =
    selectedTable && selectedTableKey ? `${document.id}::${selectedTableKey}` : null;

  // Seed the edited copy from the raw extraction the first time a table is
  // viewed. After that, this effect is a no-op for that key — edits are
  // never overwritten by the original data.
  useEffect(() => {
    if (!selectedTable || !editedKey) return;
    setEditedTables((current) => {
      if (current[editedKey]) return current;
      return { ...current, [editedKey]: normalizeTable(selectedTable) };
    });
  }, [editedKey, selectedTable]);

  const editedTable = editedKey ? editedTables[editedKey] : null;

  const handleCellEdit = useCallback(
    (section, rowIndex, columnIndex, value) => {
      if (!editedKey) return;
      setEditedTables((current) => {
        const existing = current[editedKey];
        if (!existing) return current;

        if (section === "columns") {
          const nextColumns = [...existing.columns];
          nextColumns[columnIndex] = value;
          return { ...current, [editedKey]: { ...existing, columns: nextColumns } };
        }

        const nextRows = existing.rows.map((row, index) =>
          index === rowIndex
            ? row.map((cell, cIdx) => (cIdx === columnIndex ? value : cell))
            : row,
        );
        return { ...current, [editedKey]: { ...existing, rows: nextRows } };
      });
    },
    [editedKey],
  );

  const handleExportTableCsv = () => {
    if (!editedTable) return;
    const name = safeFileName(selectedTable?.title || document.filename);
    downloadFile(`${name}.csv`, tableToCsv(editedTable), "text/csv;charset=utf-8");
  };

  const handleExportAllJson = () => {
    if (tables.length === 0) return;
    const allTables = tables.map((table, index) => {
      const key = `${document.id}::${tableKey(table, index)}`;
      const edited = editedTables[key] || normalizeTable(table);
      return {
        title: table.title || null,
        page_number: table.page_number ?? null,
        columns: edited.columns,
        rows: edited.rows,
      };
    });

    const payload = {
      filename: document.filename,
      exported_at: new Date().toISOString(),
      tables: allTables,
    };

    const name = safeFileName(document.filename);
    downloadFile(
      `${name}-edited.json`,
      JSON.stringify(payload, null, 2),
      "application/json",
    );
  };

  return (
    <div className="result-grid">
      <section className="result-panel">
        <div className="result-panel__header">
          <div>
            <h3>Original document</h3>
            <p>Use this view to compare the reconstructed table with the source.</p>
          </div>
          
          <a href={api.getDocumentSourceUrl(document.id)}
            target="_blank"
            rel="noreferrer"
          >
            Open source
          </a>
        </div>

        <iframe
          className="source-frame"
          src={api.getDocumentSourceUrl(document.id)}
          title={`Original ${document.filename}`}
        />
      </section>

      <section className="result-panel">
        <div className="result-panel__header result-panel__header--tables">
          <div>
            <h3>Extracted tables</h3>
            <p>
              {tables.length} table{tables.length === 1 ? "" : "s"} · click any cell to
              edit
            </p>
          </div>
          {tables.length > 0 && (
            <button
              type="button"
              className="export-btn export-btn--all"
              onClick={handleExportAllJson}
            >
              Export all (JSON)
            </button>
          )}
        </div>

        {tables.length === 0 ? (
          <p className="reader__placeholder">No tables were detected.</p>
        ) : (
          <>
            <label className="table-picker">
              <span>Table</span>
              <select
                value={selectedTableKey || ""}
                onChange={(event) => setSelectedTableKey(event.target.value)}
              >
                {tables.map((table, index) => {
                  const key = tableKey(table, index);
                  return (
                    <option key={key} value={key}>
                      Page {table.page_number ?? "—"} · {table.title || `Table ${index + 1}`}
                    </option>
                  );
                })}
              </select>
            </label>

            {selectedTable && (
              <div className="table-result">
                <div className="table-result__meta">
                  <div>
                    <h4>{selectedTable.title || "Untitled table"}</h4>
                    <p>
                      Page {selectedTable.page_number ?? "—"} · {selectedTable.row_count ?? 0} rows · {selectedTable.column_count ?? 0} columns
                    </p>
                  </div>
                  <div className="table-result__actions">
                    {typeof selectedTable.confidence === "number" && (
                      <span>{Math.round(selectedTable.confidence * 100)}% confidence</span>
                    )}
                    <button
                      type="button"
                      className="export-btn"
                      onClick={handleExportTableCsv}
                    >
                      Export table (CSV)
                    </button>
                  </div>
                </div>

                <ExtractedTable table={editedTable || selectedTable} onCellEdit={handleCellEdit} />
              </div>
            )}
          </>
        )}

        {document.result?.text && (
          <details className="raw-text">
            <summary>Show extracted searchable text</summary>
            <pre>{document.result.text}</pre>
          </details>
        )}
      </section>
    </div>
  );
}

export default function OCRWorkbench() {
  const [documents, setDocuments] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const fileInputRef = useRef(null);
  const pollTimers = useRef({});

  useEffect(() => {
    let cancelled = false;

    api
      .listDocuments()
      .then((list) => {
        if (cancelled) return;
        setDocuments(list);
        if (list.length > 0) setSelectedId(list[0].id);
      })
      .catch((error) => {
        if (!cancelled) setLoadError(error.message);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedId || String(selectedId).startsWith("temp-")) return undefined;

    let cancelled = false;

    api
      .getDocument(selectedId)
      .then((fullDocument) => {
        if (cancelled) return;
        setDocuments((current) =>
          current.map((document) =>
            document.id === selectedId
              ? { ...document, ...fullDocument }
              : document,
          ),
        );
      })
      .catch((error) => {
        if (!cancelled) setLoadError(error.message);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  useEffect(() => {
    const activeIds = new Set(
      documents
        .filter((document) => document.status === "processing")
        .map((document) => document.id),
    );

    for (const [id, timer] of Object.entries(pollTimers.current)) {
      if (!activeIds.has(id)) {
        clearInterval(timer);
        delete pollTimers.current[id];
      }
    }

    for (const document of documents) {
      if (
        document.status !== "processing" ||
        String(document.id).startsWith("temp-") ||
        pollTimers.current[document.id]
      ) {
        continue;
      }

      pollTimers.current[document.id] = setInterval(async () => {
        try {
          const updated = await api.getDocument(document.id);
          setDocuments((current) =>
            current.map((item) =>
              item.id === document.id ? { ...item, ...updated } : item,
            ),
          );

          if (updated.status !== "processing") {
            clearInterval(pollTimers.current[document.id]);
            delete pollTimers.current[document.id];
          }
        } catch (error) {
          setLoadError(error.message);
        }
      }, POLL_INTERVAL_MS);
    }
  }, [documents]);

  useEffect(
    () => () => {
      Object.values(pollTimers.current).forEach(clearInterval);
    },
    [],
  );

  const uploadFiles = useCallback(async (files) => {
    for (const file of Array.from(files)) {
      const randomPart =
        globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      const tempId = `temp-${randomPart}`;

      setDocuments((current) => [
        {
          id: tempId,
          filename: file.name,
          status: "uploading",
          progress: 0,
          uploaded_at: new Date().toISOString(),
          table_count: 0,
        },
        ...current,
      ]);
      setSelectedId(tempId);

      try {
        const created = await api.uploadDocument(file, {
          onProgress: (progress) =>
            setDocuments((current) =>
              current.map((document) =>
                document.id === tempId
                  ? { ...document, progress }
                  : document,
              ),
            ),
        });

        setDocuments((current) =>
          current.map((document) =>
            document.id === tempId ? created : document,
          ),
        );
        setSelectedId(created.id);
      } catch (error) {
        setDocuments((current) =>
          current.map((document) =>
            document.id === tempId
              ? { ...document, status: "failed", error: error.message }
              : document,
          ),
        );
      }
    }
  }, []);

  const handleDelete = useCallback(
    async (id, filename) => {
      if (!window.confirm(`Delete ${filename}?`)) return;

      const previousDocuments = documents;
      const previousSelectedId = selectedId;

      setDocuments((current) => current.filter((document) => document.id !== id));
      if (selectedId === id) setSelectedId(null);

      try {
        if (!String(id).startsWith("temp-")) {
          await api.deleteDocument(id);
        }
      } catch (error) {
        setDocuments(previousDocuments);
        setSelectedId(previousSelectedId);
        setLoadError(error.message);
      }
    },
    [documents, selectedId],
  );

  const handleSearch = useCallback(
    async (event) => {
      event.preventDefault();
      const trimmedQuery = query.trim();

      if (!trimmedQuery) {
        setSearchResults(null);
        return;
      }

      setSearching(true);
      setLoadError(null);

      try {
        const results = await api.searchDocuments(trimmedQuery);
        setSearchResults(results);
      } catch (error) {
        setSearchResults([]);
        setLoadError(error.message);
      } finally {
        setSearching(false);
      }
    },
    [query],
  );

  const selectedDocument =
    documents.find((document) => document.id === selectedId) || null;

  const visibleDocuments = useMemo(() => {
    if (!searchResults) return documents;
    const resultIds = new Set(searchResults.map((result) => result.id));
    return documents.filter((document) => resultIds.has(document.id));
  }, [documents, searchResults]);

  return (
    <div className="workbench">
      <div className="workbench__grain" aria-hidden="true" />

      <header className="workbench__header">
        <div className="workbench__brand">
          <span className="workbench__brand-mark">FTE</span>
          <div>
            <h1>Financial Table Extractor</h1>
            <p>Upload a statement and review its reconstructed tables.</p>
          </div>
        </div>

        <form className="search-bar" onSubmit={handleSearch}>
          <input
            type="search"
            placeholder="Search extracted values or labels…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="submit" disabled={searching}>
            {searching ? "Searching…" : "Search"}
          </button>
          {searchResults && (
            <button
              type="button"
              className="search-bar__clear"
              onClick={() => {
                setQuery("");
                setSearchResults(null);
              }}
            >
              Clear
            </button>
          )}
        </form>
      </header>

      {loadError && (
        <div className="global-error" role="alert">
          <span>{loadError}</span>
          <button type="button" onClick={() => setLoadError(null)}>
            Dismiss
          </button>
        </div>
      )}

      <main className="workbench__body">
        <aside className="queue-panel">
          <div
            className={`dropzone ${isDragging ? "dropzone--active" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setIsDragging(false);
              if (event.dataTransfer.files?.length) {
                uploadFiles(event.dataTransfer.files);
              }
            }}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
              hidden
              onChange={(event) => {
                if (event.target.files?.length) {
                  uploadFiles(event.target.files);
                }
                event.target.value = "";
              }}
            />
            <div className="dropzone__icon">⤓</div>
            <p className="dropzone__title">Drop statements here</p>
            <p className="dropzone__hint">PDF, PNG, JPG, TIFF · up to 100 MB</p>
          </div>

          <div className="doc-list">
            {visibleDocuments.length === 0 && (
              <p className="empty-hint">
                {searchResults
                  ? "No documents match that search."
                  : "No documents yet — upload one above."}
              </p>
            )}

            {visibleDocuments.map((document) => (
              <DocumentCard
                key={document.id}
                document={document}
                active={document.id === selectedId}
                onSelect={setSelectedId}
                onDelete={handleDelete}
              />
            ))}
          </div>
        </aside>

        <section className="reader-panel">
          {!selectedDocument && (
            <div className="reader-panel__empty">
              <p>Select a document to inspect its source and extracted tables.</p>
            </div>
          )}

          {selectedDocument && (
            <div className="reader">
              <div className="reader__head">
                <h2>{selectedDocument.filename}</h2>
                <StatusBadge status={selectedDocument.status} />
              </div>

              <dl className="reader__meta">
                <div>
                  <dt>Uploaded</dt>
                  <dd>{formatDate(selectedDocument.uploaded_at)}</dd>
                </div>
                <div>
                  <dt>Pages</dt>
                  <dd>{selectedDocument.page_count ?? "—"}</dd>
                </div>
                <div>
                  <dt>Tables</dt>
                  <dd>{selectedDocument.table_count ?? "—"}</dd>
                </div>
                <div>
                  <dt>Confidence</dt>
                  <dd>
                    {typeof selectedDocument.confidence === "number"
                      ? `${Math.round(selectedDocument.confidence * 100)}%`
                      : "—"}
                  </dd>
                </div>
              </dl>

              {selectedDocument.status === "uploading" && (
                <p className="reader__placeholder">Uploading document…</p>
              )}

              {selectedDocument.status === "processing" && (
                <p className="reader__placeholder">Extraction is in progress…</p>
              )}

              {selectedDocument.status === "failed" && (
                <p className="reader__placeholder reader__placeholder--error">
                  Extraction failed
                  {selectedDocument.error ? `: ${selectedDocument.error}` : "."}
                </p>
              )}

              {selectedDocument.status === "done" &&
                (selectedDocument.result ? (
                  <ResultViewer document={selectedDocument} />
                ) : (
                  <p className="reader__placeholder">Loading extraction result…</p>
                ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}