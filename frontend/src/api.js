const API_BASE =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE) ||
  "http://127.0.0.1:8000";

async function handle(response) {
  if (!response.ok) {
    let detail = response.statusText;

    try {
      const body = await response.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // Keep the HTTP status text when the body is not JSON.
    }

    throw new Error(`API error ${response.status}: ${detail}`);
  }

  return response.status === 204 ? null : response.json();
}

export const api = {
  async uploadDocument(file, { onProgress } = {}) {
    const formData = new FormData();
    formData.append("file", file);

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/api/documents`);

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      };

      xhr.onload = () => {
        try {
          const data = JSON.parse(xhr.responseText || "{}");
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(data);
          } else {
            reject(new Error(data.detail || xhr.statusText));
          }
        } catch (error) {
          reject(error);
        }
      };

      xhr.onerror = () => reject(new Error("Network error during upload"));
      xhr.send(formData);
    });
  },

  async getDocument(id) {
    const response = await fetch(`${API_BASE}/api/documents/${id}`);
    return handle(response);
  },

  async listDocuments() {
    const response = await fetch(`${API_BASE}/api/documents`);
    return handle(response);
  },

  async searchDocuments(query) {
    const response = await fetch(
      `${API_BASE}/api/documents/search?q=${encodeURIComponent(query)}`,
    );
    return handle(response);
  },

  async deleteDocument(id) {
    const response = await fetch(`${API_BASE}/api/documents/${id}`, {
      method: "DELETE",
    });
    return handle(response);
  },

  getDocumentSourceUrl(id) {
    return `${API_BASE}/api/documents/${id}/source`;
  },
};

export { API_BASE };
export default api;
