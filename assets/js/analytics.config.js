window.DANIELOZA_ANALYTICS_CONFIG = {
  api_base: "http://127.0.0.1:8000",
  events_endpoint: "/api/analytics/events",
  leads_endpoint: "/api/leads",
  ga4_measurement_id: "G-DZDE3MCRG3",

  // Set to true to force debug mode even outside localhost.
  force_debug: false,

  // Disable floating panel while keeping console debug logs.
  debug_panel: true,

  // Consent defaults: pending | granted | denied
  consent_default: "pending",
  show_consent_banner: true,

  // Per-event sample rates (0..1).
  sample_rates: {
    scroll_depth: 0.5,
    engaged_time: 0.5
  },

  // Per-event throttle windows in milliseconds.
  throttle_ms: {
    cta_click: 800,
    outbound_click: 800,
    billing_toggle: 250
  }
};
