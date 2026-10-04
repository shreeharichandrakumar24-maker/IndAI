// Strict validator for the browser RPC method "ui.command" (Part D).
// Accepts ONLY the six whitelisted actions with correctly typed args.
// Anything else -> {ok:false, error} and the caller does nothing.
// Pure function: unit-tested without a browser.
const ACTIONS = ["navigate", "select_machine", "open_order", "open_incident",
  "focus_order_on_map", "show_proposals"];

function isNonEmptyString(v) {
  return typeof v === "string" && v.trim().length > 0;
}

export function validateUiCommand(raw) {
  let msg;
  try {
    msg = typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch {
    return { ok: false, error: "rejected: not JSON" };
  }
  if (!msg || typeof msg !== "object" || Array.isArray(msg)) {
    return { ok: false, error: "rejected: not an object" };
  }
  const { action } = msg;
  if (!ACTIONS.includes(action)) {
    return { ok: false, error: `rejected: unknown action '${String(action)}'` };
  }
  const args = {};
  if (action === "navigate") {
    if (!isNonEmptyString(msg.page)) return { ok: false, error: "rejected: navigate needs page" };
    args.page = msg.page.trim();
  } else if (action === "select_machine") {
    if (!isNonEmptyString(msg.machine)) return { ok: false, error: "rejected: select_machine needs machine" };
    args.machine = msg.machine.trim();
  } else if (action === "open_order") {
    if (!isNonEmptyString(msg.order)) return { ok: false, error: "rejected: open_order needs order" };
    args.order = msg.order.trim();
  } else if (action === "open_incident") {
    if (!isNonEmptyString(msg.incident)) return { ok: false, error: "rejected: open_incident needs incident" };
    args.incident = msg.incident.trim();
  } else if (action === "focus_order_on_map") {
    if (!isNonEmptyString(msg.order)) return { ok: false, error: "rejected: focus_order_on_map needs order" };
    args.order = msg.order.trim();
  }
  // show_proposals takes no args.
  return { ok: true, action, args };
}

export const UI_COMMAND_METHOD = "ui.command";
export const UI_COMMAND_ACTIONS = ACTIONS;
