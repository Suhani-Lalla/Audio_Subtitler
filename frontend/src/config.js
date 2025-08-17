// Backend API configuration
export const API_BASE_URL = "http://localhost:8000";

export const API_ENDPOINTS = {
  PROCESS_INITIAL: `${API_BASE_URL}/process_initial`,
  OVERLAY: `${API_BASE_URL}/overlay`,
  HEALTH: `${API_BASE_URL}/healthz`,
};

// Default fetch options with CORS support
export const DEFAULT_FETCH_OPTIONS = {
  mode: "cors",
  credentials: "omit",
  headers: {
    Accept: "application/json",
  },
};
