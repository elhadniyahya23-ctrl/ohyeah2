"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useAuthModal } from "@/context/AuthModalContext";
import { useToast } from "@/context/ToastContext";
import { CheckoutModal } from "@/components/panels/CheckoutModal";
import { fetchBillingPlans, type BillingPlan, type PlansResponse } from "@/lib/billingApi";

function CheckIcon() {
  return (
    <svg className="shop-check" viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M3.2 8.4 6.4 11.4 12.8 4.6"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PayPalIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M7.076 21.337H2.47a.641.641 0 0 1-.633-.74L4.944 2.79A.77.77 0 0 1 5.704 2.1h7.63c2.49 0 4.35.58 5.37 1.74.93 1.05 1.2 2.5.82 4.4-.03.15-.07.3-.1.45-.5 2.35-1.8 3.95-3.86 4.75-1.1.43-2.4.64-3.86.64H9.55a.9.9 0 0 0-.89.76l-.9 5.7a.64.64 0 0 1-.63.54H7.076z"
        opacity="0.9"
      />
      <path
        fill="currentColor"
        d="M19.54 7.5c-.03.15-.07.3-.1.45-.5 2.35-1.8 3.95-3.86 4.75-1.1.43-2.4.64-3.86.64h-2.03a.9.9 0 0 0-.89.76l-1.05 6.66a.64.64 0 0 0 .63.74h3.9a.77.77 0 0 0 .76-.64l.03-.18.6-3.8.04-.22a.77.77 0 0 1 .76-.64h.48c3.1 0 5.53-1.26 6.24-4.9.3-1.52.14-2.8-.61-3.7-.24-.28-.53-.52-.87-.72z"
        opacity="0.55"
      />
    </svg>
  );
}

function CardIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="2.5" y="5" width="19" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M2.5 10h19" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6 15.5h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function BtcIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="10" fill="#f7931a" />
      <path
        fill="#fff"
        d="M14.7 10.4c.2-1.3-.8-2-2.2-2.4l.4-1.8-1.1-.3-.4 1.7c-.3-.1-.6-.1-.9-.2l.4-1.7-1.1-.3-.4 1.8c-.2 0-.5-.1-.7-.2l-1.5-.4-.3 1.1s.8.2.8.2c.4.1.5.4.5.6l-.5 2.1c0 .1.1.1.1.1l-.8-.2-.5 2.1.7.2c.2 0 .5.1.7.2l-.5 1.8 1.1.3.4-1.8c.3.1.6.1.9.2l-.4 1.8 1.1.3.5-1.8c1.8.3 3.2.2 3.7-1.5.4-1.3 0-2.1-.9-2.6.7-.2 1.1-.7 1.3-1.6zm-2.2 3.1c-.3 1.2-2.3.5-2.9.4l.5-2.1c.6.2 2.7.5 2.4 1.7zm.3-3.1c-.3 1.1-1.9.5-2.4.4l.5-1.9c.5.1 2.2.4 1.9 1.5z"
      />
    </svg>
  );
}

function EthIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#627eea" d="M12 2v7.8l6.6 3L12 2z" opacity="0.8" />
      <path fill="#627eea" d="M12 2 5.4 12.8l6.6-3V2z" />
      <path fill="#627eea" d="M12 16.5v5.5l6.6-9.1L12 16.5z" opacity="0.8" />
      <path fill="#627eea" d="M12 22v-5.5l-6.6-3.6L12 22z" />
      <path fill="#627eea" d="m12 15.3 6.6-2.5L12 9.8v5.5z" opacity="0.55" />
      <path fill="#627eea" d="m5.4 12.8 6.6 2.5V9.8l-6.6 3z" opacity="0.8" />
    </svg>
  );
}

function LtcIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="10" fill="#345d9d" />
      <path
        fill="#fff"
        d="M13.4 7.2h-1.7l-.7 2.6-1.8.6-.3 1.1 1.8-.6-.9 3.4H7.2l-.3 1.2h9.4l.4-1.2h-2.1l.9-3.4 1.6-.5.3-1.1-1.6.5.7-2.6z"
      />
    </svg>
  );
}

interface Props {
  trialBanner?: boolean;
}

export function ShopPanel({ trialBanner = false }: Props) {
  const { user } = useAuth();
  const { openAuth } = useAuthModal();
  const { showToast } = useToast();
  const [catalog, setCatalog] = useState<PlansResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<BillingPlan | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchBillingPlans();
      setCatalog(data);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to load shop", "error");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    void load();
  }, [load]);

  const buy = (plan: BillingPlan) => {
    if (!user) {
      openAuth("signup", true);
      return;
    }
    setSelected(plan);
  };

  const showTrialEnded =
    trialBanner ||
    Boolean(user?.trial_exhausted) ||
    (user?.rank || "").toLowerCase().includes("expired");

  const ordered = catalog
    ? [...catalog.plans].sort((a, b) => {
        const order = { week: 0, month: 1, lifetime: 2 } as Record<string, number>;
        return (order[a.css] ?? 9) - (order[b.css] ?? 9);
      })
    : [];

  const ctaFor = (plan: BillingPlan) => {
    if (plan.cta) return plan.cta;
    if (plan.css === "week") return "Purchase Week";
    if (plan.css === "month") return "Purchase Month";
    if (plan.css === "lifetime") return "Purchase Lifetime";
    return `Purchase ${plan.name}`;
  };

  return (
    <div className="shop-page">
      <header className="shop-hero">
        <h2 className="shop-title">Upgrade to Phantom Premium</h2>
        <p className="shop-lede">
          {showTrialEnded
            ? "Your 5-minute trial has expired or you want to upgrade your plan."
            : "Choose a plan to unlock unlimited sniping across every platform."}
        </p>
      </header>

      {loading && <p className="auth-loading">Loading plans…</p>}

      {!loading && catalog && (
        <div className="shop-grid">
          {ordered.map((plan, index) => {
            const css = plan.css || "week";
            const featured = css === "month" || Boolean(plan.badge);
            return (
              <article
                key={plan.id}
                className={`shop-card shop-card--${css}${featured ? " shop-card--featured" : ""}`}
                style={{ animationDelay: `${80 + index * 70}ms` }}
              >
                {featured && (
                  <div className="shop-card-badge-wrap">
                    <span className="shop-card-badge">{plan.badge || "Most Popular"}</span>
                  </div>
                )}

                <h3 className="shop-card-name">{plan.name}</h3>

                <div className="shop-card-price">
                  <span className="shop-card-amount">${plan.price_usd.toFixed(2)}</span>
                </div>

                {plan.savings && <div className="shop-card-savings">{plan.savings}</div>}

                <ul className="shop-card-features">
                  {plan.features.map((f) => (
                    <li key={f}>
                      <CheckIcon />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>

                <button
                  type="button"
                  className={`shop-card-cta shop-card-cta--${css}${
                    featured ? " shop-card-cta--solid" : " shop-card-cta--outline"
                  }`}
                  onClick={() => buy(plan)}
                >
                  {ctaFor(plan)}
                </button>
              </article>
            );
          })}
        </div>
      )}

      <footer className="shop-payments">
        <p className="shop-payments-label">Supported payment methods</p>
        <div className="shop-payments-icons">
          <span className="shop-pay-icon shop-pay-icon--paypal" title="PayPal">
            <PayPalIcon />
          </span>
          <span className="shop-pay-icon" title="Card">
            <CardIcon />
          </span>
          <span className="shop-pay-icon" title="Bitcoin">
            <BtcIcon />
          </span>
          <span className="shop-pay-icon" title="Ethereum">
            <EthIcon />
          </span>
          <span className="shop-pay-icon" title="Litecoin">
            <LtcIcon />
          </span>
        </div>
        <p className="shop-payments-note">
          We support PayPal, Credit Cards &amp; All major Cryptocurrencies.
        </p>
      </footer>

      <CheckoutModal
        open={!!selected}
        plan={selected}
        catalog={catalog}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
