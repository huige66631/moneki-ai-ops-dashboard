"use strict";

const ALLOWED_ORIGINS = new Set([
  "https://tryrevive.online",
  "https://www.tryrevive.online",
  "https://moneki-dashboard-tryrevive-d4gzac2aj49df4aa4.webapps.tcloudbase.com",
  "https://moneki-api.tryrevive-deepseek.workers.dev",
  "https://0711hackson.github.io",
  "https://sophia-yuanyuan.github.io",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
  "http://localhost:8080",
  "http://127.0.0.1:8080",
  "http://localhost:4173",
  "http://127.0.0.1:4173"
]);

const DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions";
const MODEL = "deepseek-chat";
const MAX_TOKENS_CAP = 1024;
const MAX_MESSAGES = 30;
const MAX_MESSAGE_CHARS = 6000;
const MAX_SYSTEM_CHARS = 4000;
const MAX_BODY_BYTES = 96 * 1024;
const UPSTREAM_TIMEOUT_MS = 14000;

function getHeader(headers, name) {
  if (!headers || typeof headers !== "object") return "";
  const key = Object.keys(headers).find(item => item.toLowerCase() === name.toLowerCase());
  return key ? String(headers[key] || "") : "";
}

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin"
  };
}

function jsonResponse(origin, statusCode, body) {
  return {
    statusCode,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...(origin ? corsHeaders(origin) : {})
    },
    body: JSON.stringify(body),
    isBase64Encoded: false
  };
}

function normalizeMessages(value) {
  if (!Array.isArray(value)) return [];
  return value
    .slice(-MAX_MESSAGES)
    .filter(item => item && (item.role === "user" || item.role === "assistant"))
    .map(item => ({
      role: item.role,
      content: typeof item.content === "string" ? item.content.slice(0, MAX_MESSAGE_CHARS) : ""
    }))
    .filter(item => item.content.trim());
}

function parseBody(event) {
  if (!event || event.body === undefined || event.body === null) return {};
  let raw = event.body;
  if (event.isBase64Encoded && typeof raw === "string") raw = Buffer.from(raw, "base64").toString("utf8");
  if (typeof raw === "object") return raw;
  if (typeof raw !== "string") return {};
  if (Buffer.byteLength(raw, "utf8") > MAX_BODY_BYTES) {
    const error = new Error("request_too_large");
    error.statusCode = 413;
    throw error;
  }
  return raw ? JSON.parse(raw) : {};
}

exports.main = async function (event) {
  const method = String(event && event.httpMethod || "GET").toUpperCase();
  const origin = getHeader(event && event.headers, "origin");
  const allowed = Boolean(origin && ALLOWED_ORIGINS.has(origin));

  if (method === "GET") return jsonResponse("", 200, { ok: true, service: "tryrevive-deepseek-proxy", model: MODEL });
  if (method === "OPTIONS") return allowed ? { statusCode: 204, headers: corsHeaders(origin), body: "" } : jsonResponse("", 403, { error: "origin_not_allowed" });
  if (!allowed) return jsonResponse("", 403, { error: "origin_not_allowed" });
  if (method !== "POST") return jsonResponse(origin, 405, { error: "method_not_allowed" });

  const apiKey = String(process.env.DEEPSEEK_API_KEY || "").trim();
  if (!apiKey) return jsonResponse(origin, 503, { error: "deepseek_not_configured" });

  let body;
  try {
    body = parseBody(event);
  } catch (error) {
    const status = error && error.statusCode === 413 ? 413 : 400;
    return jsonResponse(origin, status, { error: status === 413 ? "request_too_large" : "invalid_json" });
  }

  const messages = normalizeMessages(body.messages);
  if (!messages.length || messages[0].role !== "user") return jsonResponse(origin, 400, { error: "valid_user_message_required" });
  const system = typeof body.system === "string" ? body.system.slice(0, MAX_SYSTEM_CHARS).trim() : "";
  const maxTokens = Math.min(Math.max(Number(body.max_tokens) || 512, 1), MAX_TOKENS_CAP);
  const responseFormat = body.response_format && body.response_format.type === "json_object" ? { type: "json_object" } : null;
  const upstreamMessages = system ? [{ role: "system", content: system }, ...messages] : messages;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);

  try {
    const upstream = await fetch(DEEPSEEK_URL, {
      method: "POST",
      headers: { "Authorization": `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: MODEL, max_tokens: maxTokens, messages: upstreamMessages, ...(responseFormat ? { response_format: responseFormat } : {}) }),
      signal: controller.signal
    });
    const raw = await upstream.text();
    let data = null;
    try { data = raw ? JSON.parse(raw) : null; } catch { data = null; }
    if (!upstream.ok) return jsonResponse(origin, upstream.status, { error: "deepseek_request_failed", upstreamStatus: upstream.status, detail: data && data.error && data.error.message ? String(data.error.message).slice(0, 300) : "DeepSeek returned an error" });
    const text = data && data.choices && data.choices[0] && data.choices[0].message ? data.choices[0].message.content : "";
    if (!text) return jsonResponse(origin, 502, { error: "invalid_deepseek_response" });
    return jsonResponse(origin, 200, { content: [{ type: "text", text }], model: MODEL });
  } catch (error) {
    if (error && error.name === "AbortError") return jsonResponse(origin, 504, { error: "deepseek_timeout" });
    return jsonResponse(origin, 502, { error: "deepseek_unreachable" });
  } finally {
    clearTimeout(timeoutId);
  }
};
