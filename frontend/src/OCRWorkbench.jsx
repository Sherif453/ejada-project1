import React, { useCallback, useEffect, useRef, useState } from "react";
import api from "./api";
import "./ocr-workbench.css";

const POLL_INTERVAL_MS = 2000;

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatusBadge({ status }) {
  const map = {
    uploading: { label: "Uploading", cls: "badge--uploading" },
    processing: { label: "Scanning", cls: "badge--processing" },
    done: { label: "Scanned", cls: "badge--done" },
    failed: { label: "Failed", cls: "badge--failed" },
  };
  const s = map[status] || map.processing;
  return <span className={`badge ${s.cls}`}>{s.label}</span>;
}

function DocumentCard({ doc, active, onSelect, onDelete }) {
  return (
    <button
      className={`doc-card ${active ? "doc-card--active" : ""}`}
      onClick={() => onSelect(doc.id)}
    >
      <div className="doc-card__scan-frame">
        <div className="doc-card__sheet">
          <div className="doc-card__line" />
          <div className="doc-card__line" />
          <div className="doc-card__line short" />
        </div>
        {doc.status === "processing" && <div className="scan-beam" />}
        {doc.status === "done" && (
          <div className="stamp">
            <span>SCANNED</span>
          </div>
        )}
        {doc.status === "failed" && (
          <div className="stamp stamp--failed">
            <span>FAILED</span>
          </div>
        )}
      </div>

      <div className="doc-card__meta">
        <div className="doc-card__title-row">
          <span className="doc-card__name" title={doc.filename}>
            {doc.filename}
          </span>
          <StatusBadge status={doc.status} />
        </div>
        <div className="doc-card__sub">
          {formatDate(doc.uploaded_at)}
          {doc.page_count ? ` · ${doc.page_count}p` : ""}
          {typeof doc.confidence === "number"
            ? ` · ${Math.round(doc.confidence * 100)}% conf.`
            : ""}
        </div>
        {doc.status === "uploading" && (
          <div className="progress-track">
            <div
              className="progress-fill"
              style={{ width: `${doc.progress || 0}%` }}
            />
          </div>
        )}
      </div>

      <span
        className="doc-card__delete"
        role="button"
        aria-label={`Remove ${doc.filename}`}
        onClick={(e) => {
          e.stopPropagation();
          onDelete(doc.id);
        }}
      >
        ×
      </span>
    </button>
  );
}

export default function OCRWorkbench() {
  const [docs, setDocs] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const fileInputRef = useRef(null);
  const pollTimers = useRef({});

  // Initial load
  useEffect(() => {
    let cancelled = false;
    api
      .listDocuments()
      .then((list) => {
        if (!cancelled) {
          setDocs(list);
          if (list.length && !selectedId) setSelectedId(list[0].id);
        }
      })
      .catch((err) => setLoadError(err.message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll processing documents until they resolve
  useEffect(() => {
    docs.forEach((doc) => {
      const needsPoll = doc.status === "processing";
      if (needsPoll && !pollTimers.current[doc.id]) {
        pollTimers.current[doc.id] = setInterval(async () => {
          try {
            const updated = await api.getDocument(doc.id);
            setDocs((prev) =>
              prev.map((d) => (d.id === doc.id ? { ...d, ...updated } : d))
            );
            if (updated.status !== "processing") {
              clearInterval(pollTimers.current[doc.id]);
              delete pollTimers.current[doc.id];
            }
          } catch (err) {
            setDocs((prev) =>
              prev.map((d) =>
                d.id === doc.id
                  ? { ...d, status: "failed", error: err.message }
                  : d
              )
            );
            clearInterval(pollTimers.current[doc.id]);
            delete pollTimers.current[doc.id];
          }
        }, POLL_INTERVAL_MS);
      }
    });
    return () => {
      // cleanup happens per-id above; nothing global to do here
    };
  }, [docs]);

  useEffect(() => {
    return () => {
      Object.values(pollTimers.current).forEach(clearInterval);
    };
  }, []);

  const uploadFiles = useCallback(async (files) => {
    for (const file of Array.from(files)) {
      const tempId = `temp-${Date.now()}-${file.name}`;
      setDocs((prev) => [
        {
          id: tempId,
          filename: file.name,
          status: "uploading",
          progress: 0,
          uploaded_at: new Date().toISOString(),
        },
        ...prev,
      ]);

      try {
        const created = await api.uploadDocument(file, {
          onProgress: (pct) =>
            setDocs((prev) =>
              prev.map((d) => (d.id === tempId ? { ...d, progress: pct } : d))
            ),
        });
        setDocs((prev) =>
          prev.map((d) => (d.id === tempId ? { ...created, status: "processing" } : d))
        );
        setSelectedId((cur) => cur ?? created.id);
      } catch (err) {
        setDocs((prev) =>
          prev.map((d) =>
            d.id === tempId ? { ...d, status: "failed", error: err.message } : d
          )
        );
      }
    }
  }, []);

  const handleDelete = useCallback(
    async (id) => {
      const prevDocs = docs;
      setDocs((prev) => prev.filter((d) => d.id !== id));
      if (selectedId === id) setSelectedId(null);
      try {
        if (!String(id).startsWith("temp-")) await api.deleteDocument(id);
      } catch (err) {
        setDocs(prevDocs); // revert on failure
      }
    },
    [docs, selectedId]
  );

  const handleSearch = useCallback(async (e) => {
    e.preventDefault();
    if (!query.trim()) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    try {
      const results = await api.searchDocuments(query.trim());
      setSearchResults(results);
    } catch (err) {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }, [query]);

  const onDrop = useCallback(
    (e) => {
      e.preventDefault();
      setIsDragging(false);
      if (e.dataTransfer.files?.length) uploadFiles(e.dataTransfer.files);
    },
    [uploadFiles]
  );

  const selectedDoc = docs.find((d) => d.id === selectedId) || null;
  const visibleList = searchResults
    ? docs.filter((d) => searchResults.some((r) => r.id === d.id))
    : docs;

  return (
    <div className="workbench">
      <div className="workbench__grain" aria-hidden="true" />

      <header className="workbench__header">
        <div className="workbench__brand">
          <span className="workbench__brand-mark">OCR</span>
          <div>
            <h1>Document Desk</h1>
            <p>Upload, scan, and search your archive</p>
          </div>
        </div>

        <form className="search-bar" onSubmit={handleSearch}>
          <input
            type="text"
            placeholder="Search extracted text…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button type="submit" disabled={searching}>
            {searching ? "…" : "Search"}
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

      <main className="workbench__body">
        <section className="queue-panel">
          <div
            className={`dropzone ${isDragging ? "dropzone--active" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
              hidden
              onChange={(e) => e.target.files && uploadFiles(e.target.files)}
            />
            <div className="dropzone__icon">⤓</div>
            <p className="dropzone__title">Drop documents to scan</p>
            <p className="dropzone__hint">PDF, PNG, JPG, TIFF · or click to browse</p>
          </div>

          {loadError && <p className="error-text">Couldn't load documents: {loadError}</p>}

          <div className="doc-list">
            {visibleList.length === 0 && !loadError && (
              <p className="empty-hint">
                {searchResults ? "No documents match that search." : "No documents yet — add one above."}
              </p>
            )}
            {visibleList.map((doc) => (
              <DocumentCard
                key={doc.id}
                doc={doc}
                active={doc.id === selectedId}
                onSelect={setSelectedId}
                onDelete={handleDelete}
              />
            ))}
          </div>
        </section>

        <section className="reader-panel">
          {!selectedDoc && (
            <div className="reader-panel__empty">
              <p>Select a document to view its scanned text.</p>
            </div>
          )}

          {selectedDoc && (
            <div className="reader">
              <div className="reader__head">
                <h2>{selectedDoc.filename}</h2>
                <StatusBadge status={selectedDoc.status} />
              </div>
              <dl className="reader__meta">
                <div>
                  <dt>Uploaded</dt>
                  <dd>{formatDate(selectedDoc.uploaded_at)}</dd>
                </div>
                <div>
                  <dt>Pages</dt>
                  <dd>{selectedDoc.page_count ?? "—"}</dd>
                </div>
                <div>
                  <dt>Confidence</dt>
                  <dd>
                    {typeof selectedDoc.confidence === "number"
                      ? `${Math.round(selectedDoc.confidence * 100)}%`
                      : "—"}
                  </dd>
                </div>
              </dl>

              <div className="reader__text-wrap">
                {selectedDoc.status === "processing" && (
                  <p className="reader__placeholder">Scanning in progress…</p>
                )}
                {selectedDoc.status === "failed" && (
                  <p className="reader__placeholder reader__placeholder--error">
                    Scan failed{selectedDoc.error ? `: ${selectedDoc.error}` : "."}
                  </p>
                )}
                {selectedDoc.status === "done" && (
                  <pre className="reader__text">
                    {selectedDoc.text || "No text was extracted from this document."}
                  </pre>
                )}
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
