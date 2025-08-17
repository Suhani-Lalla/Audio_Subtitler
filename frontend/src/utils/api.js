import {
  API_ENDPOINTS,
  DEFAULT_FETCH_OPTIONS,
  UPLOAD_FETCH_OPTIONS,
  DOWNLOAD_FETCH_OPTIONS,
} from "../config.js";

/**
 * Check if the backend is available
 */
export async function checkBackendHealth() {
  try {
    const response = await fetch(API_ENDPOINTS.HEALTH, {
      method: "GET",
      ...DEFAULT_FETCH_OPTIONS,
    });

    if (response.ok) {
      const data = await response.json();
      return { success: true, data };
    } else {
      return { success: false, error: `HTTP ${response.status}` };
    }
  } catch (error) {
    return { success: false, error: error.message };
  }
}

/**
 * Process initial video upload
 */
export async function processInitialVideo(file, targetLanguage) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("target_lang", targetLanguage);

  const response = await fetch(API_ENDPOINTS.PROCESS_INITIAL, {
    method: "POST",
    body: formData,
    ...UPLOAD_FETCH_OPTIONS,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Processing failed: ${response.status} - ${errorText}`);
  }

  return await response.json();
}

/**
 * Apply overlay with customizations
 */
export async function applyOverlay(jobId, styleConfig) {
  const formData = new FormData();
  formData.append("job_id", jobId);
  formData.append("style_json", JSON.stringify(styleConfig));

  const response = await fetch(API_ENDPOINTS.OVERLAY, {
    method: "POST",
    body: formData,
    ...DOWNLOAD_FETCH_OPTIONS,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Overlay failed: ${response.status} - ${errorText}`);
  }

  // Return the blob for download
  return await response.blob();
}
