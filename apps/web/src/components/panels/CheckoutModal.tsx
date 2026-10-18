"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import {
  confirmCrypto,
  confirmPayPal,
  startCryptoCheckout,
  startPayPalCheckout,
  type BillingPlan,
  type CryptoCurrency,
  type PlansResponse,
} from "@/lib/billingApi";

type PayMethod = "paypal" | CryptoCurrency;
type Step = "method" | "pay" | "done";

interface Props {
  open: boolean;
  plan: BillingPlan | null;
  catalog: PlansResponse | null;
  onClose: () => void;
}

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}

export function CheckoutModal({ open, plan, catalog, onClose }: Props) {
  const { refresh } = useAuth();
  const { showToast } = useToast();
  const [step, setStep] = useState<Step>("method");
  const [method, setMethod] = useState<PayMethod | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [orderId, setOrderId] = useState<number | null>(null);
  const [paypalEmail, setPaypalEmail] = useState("");
  const [cryptoAddress, setCryptoAddress] = useState("");
  const [txHash, setTxHash] = useState("");

  useEffect(() => {
    if (!open) return;
    setStep("method");
    setMethod(null);
    setBusy(false);
    setError(null);
    setOrderId(null);
    setPaypalEmail("");
    setCryptoAddress("");
    setTxHash("");
    document.body.classList.add("phantom-checkout-open");
    return () => document.body.classList.remove("phantom-checkout-open");
  }, [open, plan?.id]);

  const cryptoOptions = useMemo(() => {
    const addrs = catalog?.crypto_addresses;
    if (!addrs) return [] as CryptoCurrency[];
    return (["BTC", "ETH", "LTC", "USDT"] as CryptoCurrency[]).filter((c) => !!addrs[c]);
  }, [catalog]);

  const paypalReady = Boolean(catalog?.paypal_email);

  if (!open || !plan) return null;

  const continueCheckout = async () => {
    if (!method) {
      setError("Choose PayPal or a crypto currency.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (method === "paypal") {
        const result = await startPayPalCheckout(plan.id);
        setOrderId(result.order_id);
        setPaypalEmail(result.paypal_email);
        setStep("pay");
      } else {
        const result = await startCryptoCheckout(plan.id, method);
        setOrderId(result.order_id);
        setCryptoAddress(result.address);
        setStep("pay");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
    } finally {
      setBusy(false);
    }
  };

  const markSent = async () => {
    if (!orderId) return;
    setBusy(true);
    setError(null);
    try {
      if (method === "paypal") {
        await confirmPayPal(orderId);
        setStep("done");
        await refresh();
        showToast("Payment marked as sent — waiting for admin review", "success");
      } else {
        if (txHash.trim().length < 8) {
          setError("Paste your transaction hash (at least 8 characters).");
          setBusy(false);
          return;
        }
        const result = await confirmCrypto(orderId, txHash.trim());
        setStep("done");
        await refresh();
        if (result.verified && result.status === "completed") {
          showToast("Payment verified on-chain — plan activated", "success");
        } else if (result.pending) {
          showToast(result.message || "Waiting for blockchain confirmations", "info");
        } else {
          showToast(result.message || "Payment submitted", "success");
        }
      }    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not confirm payment");
    } finally {
      setBusy(false);
    }
  };

  const onCopy = async (value: string, label: string) => {
    const ok = await copyText(value);
    showToast(ok ? `${label} copied` : "Could not copy", ok ? "success" : "error");
  };

  const qrUrl =
    method && method !== "paypal" && cryptoAddress
      ? `https://api.qrserver.com/v1/create-qr-code/?size=168x168&data=${encodeURIComponent(cryptoAddress)}`
      : null;

  return (
    <div id="phantom-checkout" className="open" role="dialog" aria-modal="true">
      <div className="phantom-checkout-inner">
        <div className="phantom-checkout-top">
          <div className="phantom-checkout-crumb">
            <span className={step === "method" ? "active" : ""}>1. Method</span>
            <span className={step === "pay" ? "active" : ""}>2. Pay</span>
            <span className={step === "done" ? "active" : ""}>3. Done</span>
          </div>
          <button type="button" className="ph-checkout-close" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="phantom-checkout-grid">
          <div className="phantom-checkout-main">
            {step === "method" && (
              <>
                <h2>Checkout</h2>
                <p className="sub">Pay with PayPal Friends &amp; Family or cryptocurrency.</p>

                <div className="ph-checkout-section">
                  <div className="ph-pay-block">
                    <div className="ph-pay-group-title">PayPal</div>
                    <div className="ph-pay-row">
                      <button
                        type="button"
                        className={`ph-pay-tile${method === "paypal" ? " selected" : ""}${
                          !paypalReady ? " disabled" : ""
                        }`}
                        disabled={!paypalReady}
                        onClick={() => setMethod("paypal")}
                      >
                        <span className="ph-pay-icon">PP</span>
                        <span className="ph-pay-label">Friends &amp; Family</span>
                        {!paypalReady && <span className="ph-pay-hint">soon</span>}
                      </button>
                    </div>

                    <div className="ph-pay-group-title">Crypto</div>
                    <div className="ph-pay-row">
                      {(["BTC", "ETH", "LTC", "USDT"] as CryptoCurrency[]).map((c) => {
                        const ready = cryptoOptions.includes(c);
                        return (
                          <button
                            key={c}
                            type="button"
                            className={`ph-pay-tile${method === c ? " selected" : ""}${
                              !ready ? " disabled" : ""
                            }`}
                            disabled={!ready}
                            onClick={() => setMethod(c)}
                          >
                            <span className="ph-pay-icon">{c.slice(0, 1)}</span>
                            <span className="ph-pay-label">{c}</span>
                            {!ready && <span className="ph-pay-hint">soon</span>}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {error && <p className="ph-checkout-error">{error}</p>}

                  <button
                    type="button"
                    className="ph-checkout-continue"
                    disabled={busy || !method}
                    onClick={() => void continueCheckout()}
                  >
                    {busy ? "Starting…" : "Continue to payment"}
                  </button>
                </div>
              </>
            )}

            {step === "pay" && method === "paypal" && (
              <>
                <div className="ph-confirm-header">
                  <div>
                    <h2>PayPal Friends &amp; Family</h2>
                    <p className="sub">Send exactly ${plan.price_usd.toFixed(2)} USD</p>
                  </div>
                  <button type="button" className="ph-confirm-cancel" onClick={() => setStep("method")}>
                    Back
                  </button>
                </div>

                <div className="ph-important-box ph-paypal-ff-box">
                  <strong>Important</strong>
                  <ul>
                    <li>Use Friends &amp; Family only (not Goods &amp; Services).</li>
                    <li>Do not add a note or memo.</li>
                    <li>Send the exact amount shown.</li>
                  </ul>
                </div>

                <div className="ph-copy-field">
                  <div className="phantom-checkout-label">PayPal email</div>
                  <div className="ph-copy-row">
                    <span className="value paypal-email">{paypalEmail}</span>
                    <button
                      type="button"
                      className="ph-copy-btn"
                      onClick={() => void onCopy(paypalEmail, "Email")}
                    >
                      Copy
                    </button>
                  </div>
                </div>

                <div className="ph-copy-field">
                  <div className="phantom-checkout-label">Amount</div>
                  <div className="ph-copy-row">
                    <span className="value">${plan.price_usd.toFixed(2)} USD</span>
                    <button
                      type="button"
                      className="ph-copy-btn"
                      onClick={() => void onCopy(plan.price_usd.toFixed(2), "Amount")}
                    >
                      Copy
                    </button>
                  </div>
                </div>

                {error && <p className="ph-checkout-error">{error}</p>}

                <button
                  type="button"
                  className="ph-sent-btn"
                  disabled={busy}
                  onClick={() => void markSent()}
                >
                  {busy ? "Submitting…" : "I sent the payment"}
                </button>
              </>
            )}

            {step === "pay" && method && method !== "paypal" && (
              <>
                <div className="ph-confirm-header">
                  <div>
                    <h2>Pay with {method}</h2>
                    <p className="sub">
                      Send the USD-equivalent of ${plan.price_usd.toFixed(2)} in {method}
                    </p>
                  </div>
                  <button type="button" className="ph-confirm-cancel" onClick={() => setStep("method")}>
                    Back
                  </button>
                </div>

                <div className="ph-important-box ph-info-box">
                  <strong>Send only {method}</strong>
                  <p>Wrong network or coin may result in lost funds. Double-check the address.</p>
                </div>

                {qrUrl && (
                  <div className="ph-qr-wrap">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={qrUrl} alt={`${method} QR code`} />
                  </div>
                )}

                <div className="ph-copy-field">
                  <div className="phantom-checkout-label">{method} address</div>
                  <div className="ph-copy-row">
                    <span className="value address">{cryptoAddress}</span>
                    <button
                      type="button"
                      className="ph-copy-btn"
                      onClick={() => void onCopy(cryptoAddress, "Address")}
                    >
                      Copy
                    </button>
                  </div>
                </div>

                <label className="phantom-checkout-label" htmlFor="tx-hash">
                  Transaction hash
                </label>
                <input
                  id="tx-hash"
                  className="phantom-checkout-input"
                  value={txHash}
                  onChange={(e) => setTxHash(e.target.value)}
                  placeholder="Paste tx hash after sending"
                />

                {error && <p className="ph-checkout-error">{error}</p>}

                <button
                  type="button"
                  className="ph-sent-btn"
                  disabled={busy}
                  onClick={() => void markSent()}
                >
                  {busy ? "Submitting…" : "I sent the payment"}
                </button>
              </>
            )}

            {step === "done" && (
              <>
                <h2>{method === "paypal" ? "Payment received" : "Payment checked"}</h2>
                <p className="sub">
                  {method === "paypal"
                    ? "PayPal Friends & Family cannot be verified automatically. An admin will activate your plan after review."
                    : "We verified your transaction on the blockchain. If confirmations are still pending, wait a minute and paste the same hash again."}
                </p>
                <div className="ph-status-pill">
                  {method === "paypal" ? "Pending review" : "On-chain verified"}
                </div>
                <button type="button" className="ph-checkout-continue" onClick={onClose}>
                  Back to shop
                </button>
              </>
            )}
          </div>

          <aside className="phantom-checkout-sidebar">
            <h2>Order</h2>
            <div className="ph-cart-list">
              <div className="ph-cart-item">
                <div className="ph-cart-item-main">
                  <div className="ph-cart-thumb" />
                  <div>
                    <div className="ph-cart-name">{plan.name}</div>
                    <div className="ph-cart-meta">Phantom Premium</div>
                  </div>
                </div>
                <div className="ph-cart-price">${plan.price_usd.toFixed(2)}</div>
              </div>
            </div>
            <div className="ph-cart-totals-box">
              <div className="ph-cart-line">
                <span>Subtotal</span>
                <span>${plan.price_usd.toFixed(2)}</span>
              </div>
              <div className="ph-cart-line total">
                <span>Total</span>
                <span>${plan.price_usd.toFixed(2)}</span>
              </div>
            </div>
            <div className="ph-stepper" style={{ marginTop: 22 }}>
              <div className={`ph-step${step !== "method" ? " done" : " active"}`}>
                <div className="ph-step-icon">1</div>
                <div>
                  <div className="ph-step-title">Choose method</div>
                  <div className="ph-step-desc">PayPal or crypto</div>
                </div>
              </div>
              <div
                className={`ph-step${
                  step === "pay" ? " active" : step === "done" ? " done" : ""
                }`}
              >
                <div className="ph-step-icon">2</div>
                <div>
                  <div className="ph-step-title">Send payment</div>
                  <div className="ph-step-desc">Exact amount required</div>
                </div>
              </div>
              <div className={`ph-step${step === "done" ? " active done" : ""}`}>
                <div className="ph-step-icon">3</div>
                <div>
                  <div className="ph-step-title">Activation</div>
                  <div className="ph-step-desc">
                    {method === "paypal" ? "Manual review" : "On-chain check"}
                  </div>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
