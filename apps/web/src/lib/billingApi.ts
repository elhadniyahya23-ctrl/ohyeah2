import { apiFetch, parseApiError } from "@/lib/apiClient";

export interface BillingPlan {
  id: string;
  name: string;
  price_usd: number;
  duration_days: number | null;
  badge: string | null;
  css: "week" | "month" | "lifetime" | string;
  cta?: string | null;
  savings?: string | null;
  features: string[];
}

export interface PlansResponse {
  plans: BillingPlan[];
  paypal_email: string | null;
  crypto_addresses: {
    BTC: string | null;
    ETH: string | null;
    LTC: string | null;
    USDT: string | null;
  };
  trial_limit_seconds: number;
}

export type CryptoCurrency = "BTC" | "ETH" | "LTC" | "USDT";

export interface PayPalCheckoutResult {
  order_id: number;
  plan_id: string;
  amount_usd: number;
  paypal_email: string;
  instructions: string;
  status: string;
}

export interface CryptoCheckoutResult {
  order_id: number;
  plan_id: string;
  amount_usd: number;
  currency: CryptoCurrency;
  address: string;
  status: string;
  instructions: string;
}

export async function fetchBillingPlans(): Promise<PlansResponse> {
  const res = await apiFetch("/api/billing/plans");
  if (!res.ok) await parseApiError(res, "Failed to load plans");
  return res.json();
}

export async function startPayPalCheckout(planId: string): Promise<PayPalCheckoutResult> {
  const res = await apiFetch("/api/billing/paypal/checkout", {
    method: "POST",
    body: JSON.stringify({ plan_id: planId }),
  });
  if (!res.ok) await parseApiError(res, "PayPal checkout failed");
  return res.json();
}

export async function confirmPayPal(orderId: number): Promise<{ status: string; message: string }> {
  const res = await apiFetch(`/api/billing/paypal/confirm?order_id=${orderId}`, {
    method: "POST",
  });
  if (!res.ok) await parseApiError(res, "Could not confirm PayPal payment");
  return res.json();
}

export async function startCryptoCheckout(
  planId: string,
  currency: CryptoCurrency,
  senderWallet = "",
): Promise<CryptoCheckoutResult> {
  const res = await apiFetch("/api/billing/crypto/checkout", {
    method: "POST",
    body: JSON.stringify({
      plan_id: planId,
      currency,
      sender_wallet: senderWallet,
    }),
  });
  if (!res.ok) await parseApiError(res, "Crypto checkout failed");
  return res.json();
}

export async function confirmCrypto(
  orderId: number,
  txHash: string,
): Promise<{
  status: string;
  message: string;
  verified?: boolean;
  pending?: boolean;
}> {
  const res = await apiFetch("/api/billing/crypto/confirm", {
    method: "POST",
    body: JSON.stringify({ order_id: orderId, tx_hash: txHash }),
  });
  if (!res.ok) await parseApiError(res, "Could not confirm crypto payment");
  return res.json();
}
