// Smart Split client: exactly one place calls POST /ai/smart-split.
// Manual Split (ManualSplitPanel) is a separate, untouched flow.
import { api } from './api';

export async function requestSmartSplit(orderId) {
  const res = await api.smartSplit(orderId);
  return res; // {source: 'ai'|'rule-based', summary, order, proposed_tasks[]}
}
