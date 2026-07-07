// api.js
// Thin API layer for the FastAPI backend. Swap API_BASE for your real host,
// or set VITE_API_BASE / REACT_APP_API_BASE in your .env file.

const API_BASE =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE) ||
  (typeof process !== "undefined" && process.env?.REACT_APP_API_BASE) ||
  "http://localhost:8000";

async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) {
      /* ignore parse errors */
    }
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  /**
   * Upload a document for OCR processing.
   * Expected backend contract:
   *   POST /api/documents  (multipart/form-data, field name "file")
   *   -> 201 { id, filename, status: "processing", uploaded_at }
   */
  async uploadDocument(file, { onProgress } = {}) {
    const formData = new FormData();
    formData.append("file", file);

    // Using XHR instead of fetch so we can report upload progress.
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/api/documents`);
      xhr.upload.onprogress = (evt) => {
        if (evt.lengthComputable && onProgress) {
          onProgress(Math.round((evt.loaded / evt.total) * 100));
        }
      };
      xhr.onload = () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) resolve(data);
          else reject(new Error(data.detail || xhr.statusText));
        } catch (e) {
          reject(e);
        }
      };
      xhr.onerror = () => reject(new Error("Network error during upload"));
      xhr.send(formData);
    });
  },

  /**
   * Poll a single document's OCR status/result.
   *   GET /api/documents/{id}
   *   -> { id, filename, status: "processing"|"done"|"failed",
   *        uploaded_at, page_count, confidence, text, error }
   */
  async getDocument(id) {
    const res = await fetch(`${API_BASE}/api/documents/${id}`);
    return handle(res);
  },

  /**
   * List all documents (most recent first).
   *   GET /api/documents
   *   -> [{ id, filename, status, uploaded_at, page_count, confidence }]
   */
  async listDocuments() {
    const res = await fetch(`${API_BASE}/api/documents`);
    return handle(res);
  },

  /**
   * Full-text search across OCR'd documents.
   *   GET /api/documents/search?q=...
   *   -> [{ id, filename, snippet, score }]
   */
  async searchDocuments(query) {
    const res = await fetch(
      `${API_BASE}/api/documents/search?q=${encodeURIComponent(query)}`
    );
    return handle(res);
  },

  /**
   * Delete a document.
   *   DELETE /api/documents/{id} -> 204
   */
  async deleteDocument(id) {
    const res = await fetch(`${API_BASE}/api/documents/${id}`, {
      method: "DELETE",
    });
    return handle(res);
  },
};

export default api;
